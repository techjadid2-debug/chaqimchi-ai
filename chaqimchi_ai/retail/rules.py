"""Deklarativ qoida dvigateli.

Qoidalar kodda emas, JSON/YAML da turadi.  Sabab tijoriy: har do'konning
qoidasi boshqacha (birining kassasi 3 kishida uzun, boshqasiniki 8 kishida),
va har o'zgarish uchun yangi reliz chiqarib, 8/128 qurilmalarga OTA yuborish
mumkin emas.  Qoida cloud'dan config sifatida keladi va keyingi poll'da
kuchga kiradi.

Dvigatel `SceneAnalyzer` chiqargan hodisani **qabul qiladi** va uch narsani
hal qiladi:

1. hodisa saqlanadimi yoki bostiriladimi (`suppress`);
2. jiddiyligi qanday (`severity`);
3. qanday harakat qilinadi (`actions`) — klip saqlash, Telegram, cloud.

Ya'ni analitika "nima ko'rdim" deydi, qoida esa "bu muhimmi va nima qilamiz"
deydi.  Ikkalasini ajratish sotuvchiga kod tegmasdan sozlash imkonini beradi.

Namuna:

```yaml
rules:
  - name: Kassada uzun navbat
    event_type: queue_threshold_exceeded
    camera_id: kassa-01
    zone: kassa
    conditions: {min_queue_length: 5}
    schedule: ish-vaqti
    severity: warning
    cooldown_sec: 300
    actions: [save_clip, telegram_alert]
schedules:
  ish-vaqti: {start: "09:00", end: "21:00"}
```
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time as clock_time
from typing import Any, Dict, List, Mapping, Optional, Sequence

from chaqimchi_ai.event_models import EdgeEvent

#: Qoida buyura oladigan harakatlar.  Ro'yxat yopiq: config'dan kelgan
#: noma'lum harakat jimgina e'tiborsiz qolmasin, xato bersin.
ACTIONS = frozenset({"save_clip", "telegram_alert", "cloud_sync", "ignore"})

#: Qoida topilmagan hodisa uchun standart xatti-harakat.
DEFAULT_ACTIONS = ("cloud_sync",)

SEVERITIES = ("info", "warning", "critical")


@dataclass(frozen=True)
class Schedule:
    """Kun ichidagi vaqt oynasi.

    `start > end` bo'lsa oyna yarim tundan o'tadi (masalan 22:00–06:00) —
    "ish vaqtidan tashqari" qoidasi aynan shunday yoziladi.
    """

    start: clock_time
    end: clock_time

    @classmethod
    def parse(cls, start: str, end: str) -> "Schedule":
        return cls(start=_parse_time(start), end=_parse_time(end))

    def contains(self, moment: clock_time) -> bool:
        if self.start <= self.end:
            return self.start <= moment < self.end
        return moment >= self.start or moment < self.end


def _parse_time(value: str) -> clock_time:
    parts = str(value).strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"Vaqt 'HH:MM' ko'rinishida bo'lishi kerak: {value}")
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Vaqt noto'g'ri: {value}")
    return clock_time(hour=hour, minute=minute)


@dataclass(frozen=True)
class Rule:
    name: str
    event_type: str
    camera_id: Optional[str] = None
    zone: Optional[str] = None
    conditions: Mapping[str, Any] = field(default_factory=dict)
    schedule: Optional[str] = None
    #: `True` bo'lsa qoida jadval **tashqarisida** ishlaydi.  "Ish vaqtidan
    #: tashqari harakat" uchun alohida jadval yozish shart bo'lmasin.
    outside_schedule: bool = False
    severity: Optional[str] = None
    cooldown_sec: int = 0
    actions: Sequence[str] = DEFAULT_ACTIONS
    #: Mos kelgan hodisani butunlay bostiradi (masalan xodimlar zonasidagi
    #: harakatni hisobga olmaslik).
    suppress: bool = False

    def __post_init__(self) -> None:
        if self.severity is not None and self.severity not in SEVERITIES:
            raise ValueError(f"{self.name}: noma'lum severity {self.severity}")
        unknown = set(self.actions) - ACTIONS
        if unknown:
            raise ValueError(f"{self.name}: noma'lum harakat {sorted(unknown)}")
        if self.cooldown_sec < 0:
            raise ValueError(f"{self.name}: cooldown_sec manfiy bo'lmasin")
        unsupported = set(self.conditions) - set(_CONDITIONS)
        if unsupported:
            raise ValueError(f"{self.name}: noma'lum shart {sorted(unsupported)}")


def _at_least(event: EdgeEvent, attribute: str, threshold: Any) -> bool:
    value = getattr(event, attribute, None)
    return value is not None and value >= threshold


#: Qo'llab-quvvatlanadigan shartlar.  Yangi shart qo'shish — shu lug'atga
#: bitta qator; qoidalarni tekshirish avtomatik kuchga kiradi.
_CONDITIONS = {
    "min_queue_length": lambda event, value: _at_least(event, "queue_length", value),
    "min_dwell_sec": lambda event, value: _at_least(event, "dwell_sec", value),
    "min_occupancy": lambda event, value: _at_least(event, "occupancy", value),
    "min_score": lambda event, value: _at_least(event, "score", value),
    "direction": lambda event, value: event.direction == value,
}


@dataclass(frozen=True)
class Decision:
    """Qoida chiqargan qaror."""

    event: EdgeEvent
    actions: Sequence[str]
    rule_name: Optional[str]

    @property
    def suppressed(self) -> bool:
        return not self.actions or "ignore" in self.actions


class RuleEngine:
    def __init__(
        self,
        rules: Sequence[Rule] = (),
        *,
        schedules: Optional[Mapping[str, Schedule]] = None,
    ) -> None:
        self.schedules = dict(schedules or {})
        for rule in rules:
            if rule.schedule and rule.schedule not in self.schedules:
                raise ValueError(f"{rule.name}: '{rule.schedule}' jadvali topilmadi")
        self.rules = list(rules)
        self._last_fired: Dict[tuple, float] = {}

    # ── Yuklash ──────────────────────────────────────────────────────────

    @classmethod
    def from_config(cls, payload: Mapping[str, Any]) -> "RuleEngine":
        schedules = {
            name: Schedule.parse(window["start"], window["end"])
            for name, window in (payload.get("schedules") or {}).items()
        }
        rules = []
        for raw in payload.get("rules") or []:
            data = dict(raw)
            if "actions" in data:
                data["actions"] = tuple(data["actions"])
            rules.append(Rule(**data))
        return cls(rules, schedules=schedules)

    # ── Baholash ─────────────────────────────────────────────────────────

    def evaluate(
        self, event: EdgeEvent, *, now: float, local_time: Optional[clock_time] = None
    ) -> Decision:
        """Hodisa uchun qaror.  Mos qoida bo'lmasa standart yo'l bilan o'tadi."""
        for rule in self.rules:
            if not self._matches(rule, event, local_time):
                continue
            if rule.suppress:
                return Decision(event=event, actions=(), rule_name=rule.name)
            if not self._cooldown_passed(rule, event, now):
                return Decision(event=event, actions=(), rule_name=rule.name)
            decided = event
            if rule.severity is not None and rule.severity != event.severity:
                decided = event.model_copy(update={"severity": rule.severity})
            return Decision(event=decided, actions=tuple(rule.actions), rule_name=rule.name)
        return Decision(event=event, actions=DEFAULT_ACTIONS, rule_name=None)

    def _matches(
        self, rule: Rule, event: EdgeEvent, local_time: Optional[clock_time]
    ) -> bool:
        if rule.event_type != event.event_type:
            return False
        if rule.camera_id is not None and rule.camera_id != event.camera_id:
            return False
        if rule.zone is not None and rule.zone not in {event.zone, event.line}:
            return False
        if rule.schedule is not None:
            if local_time is None:
                # Vaqt noma'lum bo'lsa jadvalli qoida ishlamaydi.  Jim
                # o'tkazib yuborish "qoida yozdim, lekin ishlamadi" degan eng
                # yomon holatga olib keladi, shuning uchun bu ataylab qat'iy.
                return False
            inside = self.schedules[rule.schedule].contains(local_time)
            if inside == rule.outside_schedule:
                return False
        for name, expected in rule.conditions.items():
            if not _CONDITIONS[name](event, expected):
                return False
        return True

    def _cooldown_passed(self, rule: Rule, event: EdgeEvent, now: float) -> bool:
        if rule.cooldown_sec <= 0:
            return True
        key = (rule.name, event.camera_id, event.zone or event.line)
        previous = self._last_fired.get(key)
        if previous is not None and now - previous < rule.cooldown_sec:
            return False
        self._last_fired[key] = now
        return True

    def decisions(
        self,
        events: Sequence[EdgeEvent],
        *,
        now: float,
        local_time: Optional[clock_time] = None,
    ) -> List[Decision]:
        """Bir nechta hodisani baholaydi va bostirilganlarini tashlaydi."""
        results = [
            self.evaluate(event, now=now, local_time=local_time) for event in events
        ]
        return [decision for decision in results if not decision.suppressed]
