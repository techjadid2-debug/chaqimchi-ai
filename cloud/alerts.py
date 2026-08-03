"""Telegram ogohlantirishlari — mijoz tizimi o‘chganda o‘zi xabar beradi.

Panelda aloqa holati ko‘rinadi (7.9), lekin uni ko‘rish uchun panelni ochish
kerak. Kunda bir marta ochilsa ham, do‘kon ertalab soat 9 da o‘chsa siz buni
kechqurun bilasiz. Shuning uchun cloud o‘zi Telegramga yozadi.

**Faqat holat o‘zgarganda** xabar ketadi (`alert_state` jadvali) — aks holda
har 15 daqiqada o‘sha xabar takrorlanib, siz uni o‘qishni tashlab qo‘yasiz.

Yoqish:

```bash
export CHAQIMCHI_CLOUD_TELEGRAM_TOKEN="123456:ABC..."
export CHAQIMCHI_CLOUD_TELEGRAM_CHAT_ID="-1001234567890"
make run-cloud
```

Ikkalasi ham bo‘lmasa modul jim turadi — cloud oddiy ishlashda davom etadi.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

#: Aloqa nazorati qanchalik tez-tez tekshiriladi (standart 15 daqiqa).
DEFAULT_INTERVAL_SEC = 900

#: Yangi ochilgan mijoz shu muddat ichida juftlanmasa — ogohlantiriladi.
#: Pairing kod 48 soat amal qiladi; shundan oldin xabar berish erta bo‘lardi
#: (o‘rnatuvchi hali yo‘lda).
PAIRING_GRACE_HOURS = 48

#: Ogohlantirish talab qiladigan holatlar.
PROBLEM_STATES = ("offline", "not_paired")

STATE_LABEL = {
    "online": "ishlayapti",
    "stale": "aloqa uzilgan",
    "offline": "ishlamayapti",
    "not_paired": "juftlanmagan",
}


@dataclass
class AlertConfig:
    token: Optional[str] = None
    chat_id: Optional[str] = None
    interval_sec: int = DEFAULT_INTERVAL_SEC

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    @staticmethod
    def from_env() -> "AlertConfig":
        raw_interval = os.environ.get("CHAQIMCHI_CLOUD_ALERT_INTERVAL_SEC", "").strip()
        try:
            interval = int(raw_interval) if raw_interval else DEFAULT_INTERVAL_SEC
        except ValueError:
            logger.warning("CHAQIMCHI_CLOUD_ALERT_INTERVAL_SEC son emas — standart qiymat")
            interval = DEFAULT_INTERVAL_SEC
        return AlertConfig(
            token=os.environ.get("CHAQIMCHI_CLOUD_TELEGRAM_TOKEN", "").strip() or None,
            chat_id=os.environ.get("CHAQIMCHI_CLOUD_TELEGRAM_CHAT_ID", "").strip() or None,
            interval_sec=max(60, interval),
        )


@dataclass
class Alert:
    """Bitta yuboriladigan xabar."""

    site_id: str
    state: str
    text: str
    #: `alert_state` ga yoziladigan qiymat. `None` — yozuvni o‘chirish.
    remember: Optional[str]
    #: Ogohlantirish turi — har biri mustaqil kuzatiladi.
    kind: str = "connection"


@dataclass
class AlertRun:
    """Bitta tekshiruv natijasi — `GET /api/v1/admin/alerts` shuni ko‘rsatadi."""

    checked: int = 0
    sent: int = 0
    failed: int = 0
    ran_at: Optional[str] = None
    messages: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "checked": self.checked,
            "sent": self.sent,
            "failed": self.failed,
            "ran_at": self.ran_at,
            "messages": self.messages,
        }


def _since_label(minutes: Optional[int]) -> str:
    if minutes is None:
        return "hech qachon"
    if minutes < 60:
        return f"{minutes} daqiqa oldin"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} soat oldin"
    return f"{hours // 24} kun oldin"


def _site_age_hours(created_at: Optional[str], now: datetime) -> Optional[float]:
    if not created_at:
        return None
    try:
        created = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return (now - created).total_seconds() / 3600


def _problem_text(site: Dict[str, Any]) -> str:
    name = site.get("name", "?")
    phone = site.get("contact_phone")
    plan = str(site.get("plan", "")).capitalize()
    tail = f"\n📞 {phone}" if phone else ""

    if site["connection"] == "not_paired":
        return (
            f"⚠️ <b>{name}</b> — o‘rnatish tugallanmagan\n"
            f"Qurilma juftlanmagan (tarif: {plan}).\n"
            f"O‘rnatuvchi bilan bog‘laning.{tail}"
        )
    return (
        f"🔴 <b>{name}</b> — tizim ishlamayapti\n"
        f"Oxirgi aloqa: {_since_label(site.get('minutes_since_seen'))} "
        f"(tarif: {plan}).\n"
        f"Tok, internet yoki Mini PC ni tekshiring.{tail}"
    )


def _recovery_text(site: Dict[str, Any]) -> str:
    return (
        f"✅ <b>{site.get('name', '?')}</b> — qayta ishga tushdi\n"
        f"Aloqa tiklandi."
    )


def _camera_text(site: Dict[str, Any]) -> str:
    active = site.get("cameras_active", 0)
    expected = site.get("cameras_expected", 0)
    phone = site.get("contact_phone")
    tail = f"\n📞 {phone}" if phone else ""
    lost = expected - active
    return (
        f"📹 <b>{site.get('name', '?')}</b> — {lost} ta kamera ishlamayapti\n"
        f"{expected} tadan {active} tasi ulangan.\n"
        f"Kamera tokini, tarmoq kabelini yoki RTSP manzilini tekshiring.{tail}"
    )


def _camera_recovery_text(site: Dict[str, Any]) -> str:
    return (
        f"✅ <b>{site.get('name', '?')}</b> — kameralar tiklandi\n"
        f"Barcha {site.get('cameras_expected', 0)} kamera ishlayapti."
    )


def plan_camera_alerts(
    sites: List[Dict[str, Any]], previous: Dict[str, str]
) -> Tuple[List[Alert], List[str]]:
    """Kamera yo‘qolganini aniqlaydi.

    Mijoz 3 kamerali tarif uchun pul to‘lab, bittasi o‘chib qolsa — tizim
    “ishlayapti” bo‘lib turadi va buni hech kim sezmaydi. Bu jimgina buzilish
    aloqa uzilishidan ham xavfliroq: mijoz o‘zi ham bilmaydi.

    Faqat aloqasi bor saytlar tekshiriladi — tizim butunlay o‘chgan bo‘lsa
    kameralar haqida alohida yozish shovqin (aloqa ogohlantirishi allaqachon
    ketgan).
    """
    alerts: List[Alert] = []
    forget: List[str] = []

    for site in sites:
        site_id = site["id"]
        prev = previous.get(site_id)

        watched = site.get("license_status") in ("active", "grace") and site.get(
            "connection"
        ) in ("online", "stale")
        if not watched:
            if prev is not None:
                forget.append(site_id)
            continue

        expected = int(site.get("cameras_expected") or 0)
        active = int(site.get("cameras_active") or 0)
        if not expected:
            continue

        state = "ok" if active >= expected else f"missing:{expected - active}"

        if state.startswith("missing"):
            if prev != state:
                alerts.append(
                    Alert(site_id, state, _camera_text(site), remember=state, kind="cameras")
                )
        elif prev is not None:
            alerts.append(
                Alert(site_id, state, _camera_recovery_text(site), remember=None, kind="cameras")
            )

    return alerts, forget


def plan_alerts(
    sites: List[Dict[str, Any]],
    previous: Dict[str, str],
    *,
    now: Optional[datetime] = None,
) -> Tuple[List[Alert], List[str]]:
    """Qaysi xabarlar yuborilishi kerakligini hisoblaydi (tarmoqsiz, sof funksiya).

    Qaytaradi: (yuboriladigan xabarlar, holati tozalanishi kerak bo‘lgan sayt ID lari).

    Qoidalar:

    - Faqat **to‘lovi joyida** (active/grace) mijozlar kuzatiladi. O‘zimiz
      to‘xtatgan sayt jim turishi — normal holat, u haqda yozish shovqin.
    - Xabar faqat holat **o‘zgarganda** ketadi.
    - Yangi mijoz `PAIRING_GRACE_HOURS` ichida juftlanmasa ham jim — o‘rnatuvchi
      hali bormagan bo‘lishi mumkin.
    - `stale` (1–24 soat) uchun xabar yo‘q: internet qisqa uzilishi odatiy hol.
    """
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    alerts: List[Alert] = []
    forget: List[str] = []

    for site in sites:
        site_id = site["id"]
        prev = previous.get(site_id)

        if site.get("license_status") not in ("active", "grace"):
            # Kuzatuvdan chiqadi. Keyin qayta yoqilganda toza sahifadan
            # boshlanadi — eski holat bo'yicha yolg'on "tiklandi" ketmaydi.
            if prev is not None:
                forget.append(site_id)
            continue

        state = site.get("connection", "offline")

        if state == "not_paired":
            age = _site_age_hours(site.get("created_at"), now)
            if age is not None and age < PAIRING_GRACE_HOURS:
                continue

        if state in PROBLEM_STATES:
            if prev != state:
                alerts.append(
                    Alert(site_id, state, _problem_text(site), remember=state)
                )
        elif prev in PROBLEM_STATES:
            # Muammo hal bo'ldi. `stale` ham tiklanish deb qaraladi: tizim
            # yana xabar bera boshlagan.
            alerts.append(Alert(site_id, state, _recovery_text(site), remember=None))
        elif prev is not None:
            forget.append(site_id)

    return alerts, forget


class TelegramSender:
    """Telegramga xabar yuborish. Xato bo‘lsa cloud to‘xtamaydi — log yoziladi."""

    def __init__(self, config: AlertConfig) -> None:
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None

    async def send(self, text: str) -> bool:
        if not self.config.enabled:
            return False
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=15.0)
        url = f"https://api.telegram.org/bot{self.config.token}/sendMessage"
        try:
            resp = await self._client.post(
                url,
                json={
                    "chat_id": self.config.chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
            if resp.status_code != 200:
                logger.warning("Telegram javobi %s: %s", resp.status_code, resp.text[:200])
                return False
            return True
        except Exception as e:
            logger.warning("Telegram xabar yuborilmadi: %s", e)
            return False

    async def aclose(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            finally:
                self._client = None


async def run_check(store: Any, sender: TelegramSender) -> AlertRun:
    """Bir marta tekshirish: holatlarni solishtirib, o‘zgarganlarini yuboradi."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    run = AlertRun(ran_at=now.strftime("%Y-%m-%d %H:%M:%S"))

    sites = store.list_sites()
    run.checked = len(sites)

    conn_alerts, conn_forget = plan_alerts(
        sites, store.alert_states("connection"), now=now
    )
    cam_alerts, cam_forget = plan_camera_alerts(sites, store.alert_states("cameras"))

    for site_id in conn_forget:
        store.clear_alert_state(site_id, kind="connection")
    for site_id in cam_forget:
        store.clear_alert_state(site_id, kind="cameras")

    for alert in conn_alerts + cam_alerts:
        if await sender.send(alert.text):
            run.sent += 1
            run.messages.append(alert.text)
            # Holat faqat xabar **yetib borgandan keyin** yoziladi: aks holda
            # tarmoq uzilganda muammo "xabar berilgan" deb belgilanib,
            # ogohlantirish butunlay yo'qolardi.
            if alert.remember is None:
                store.clear_alert_state(alert.site_id, kind=alert.kind)
            else:
                store.set_alert_state(alert.site_id, alert.remember, kind=alert.kind)
        else:
            run.failed += 1

    if run.sent or run.failed:
        logger.info(
            "Aloqa ogohlantirishi: %d yuborildi, %d xato", run.sent, run.failed
        )
    return run


class AlertService:
    """Fon vazifasi + oxirgi natija (admin panel uchun)."""

    def __init__(self, store: Any, config: Optional[AlertConfig] = None) -> None:
        self.store = store
        self.config = config or AlertConfig.from_env()
        self.sender = TelegramSender(self.config)
        self.last_run: Optional[AlertRun] = None
        self._task: Optional[asyncio.Task] = None

    async def check_once(self) -> AlertRun:
        self.last_run = await run_check(self.store, self.sender)
        return self.last_run

    async def _loop(self) -> None:
        while True:
            try:
                await self.check_once()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.warning("Aloqa tekshiruvida xato", exc_info=True)
            await asyncio.sleep(self.config.interval_sec)

    def start(self) -> None:
        if not self.config.enabled:
            logger.info(
                "Telegram ogohlantirishi o‘chiq "
                "(CHAQIMCHI_CLOUD_TELEGRAM_TOKEN / _CHAT_ID berilmagan)"
            )
            return
        if self._task is None:
            self._task = asyncio.create_task(self._loop())
            logger.info(
                "Aloqa nazorati yoqildi — har %d soniyada", self.config.interval_sec
            )

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
        await self.sender.aclose()

    def status(self) -> Dict[str, Any]:
        return {
            "enabled": self.config.enabled,
            "interval_sec": self.config.interval_sec,
            "chat_id_set": bool(self.config.chat_id),
            "token_set": bool(self.config.token),
            "pairing_grace_hours": PAIRING_GRACE_HOURS,
            "running": self._task is not None,
            "last_run": self.last_run.to_dict() if self.last_run else None,
        }


def test_message() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        "🔔 <b>Chaqimchi Cloud</b>\n"
        "Ogohlantirish sozlandi — mijoz tizimi o‘chsa shu yerga xabar keladi.\n"
        f"<i>{stamp}</i>"
    )


__all__ = [
    "Alert",
    "AlertConfig",
    "AlertRun",
    "AlertService",
    "PAIRING_GRACE_HOURS",
    "TelegramSender",
    "plan_alerts",
    "plan_camera_alerts",
    "run_check",
    "test_message",
]
