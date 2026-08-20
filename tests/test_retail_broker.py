"""Inferens byudjeti va Frame Broker.

Bu modul apparatsiz sinaladi: vaqt tashqaridan beriladi, shuning uchun natija
har ishga tushirishda bir xil.  "8 kamera N100 da ishlaydi" degan va'daning
butun mantig'i shu yerda tekshiriladi.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import pytest

from chaqimchi_ai.retail import FrameBroker, InferenceBudget, Priority


def budget(**overrides) -> InferenceBudget:
    defaults = dict(target_fps=30.0, min_fps=1.0, max_fps=60.0, burst=2.0)
    defaults.update(overrides)
    return InferenceBudget(**defaults)  # type: ignore[arg-type]


# ── InferenceBudget ──────────────────────────────────────────────────────


def test_token_bucket_grants_at_target_rate() -> None:
    limiter = budget(target_fps=10.0, burst=1.0)  # burst=1 — sof tezlik ko'rinsin
    now = 0.0
    assert limiter.take(now) is True  # dastlabki burst
    assert limiter.take(now) is False  # bir zumda ikkinchisi yo'q

    # 10 FPS = har 0.1 s da bitta.
    now += 0.1
    assert limiter.take(now) is True
    now += 0.05
    assert limiter.take(now) is False
    now += 0.05
    assert limiter.take(now) is True


def test_burst_is_capped_so_idle_time_does_not_bank_unlimited_work() -> None:
    limiter = budget(target_fps=10.0, burst=2.0)
    limiter.take(0.0)
    # Bir daqiqa jim turdi — lekin faqat `burst` qadar to'planadi.
    granted = sum(1 for _ in range(10) if limiter.take(60.0))
    assert granted == 2


def test_budget_drops_when_inference_is_slower_than_target() -> None:
    limiter = budget(target_fps=30.0)
    # Har inferens 100 ms — qurilma sekundiga ko'pi bilan 10 ta ulguradi.
    for index in range(20):
        limiter.observe(0.100, now=index * 1.0)
    assert limiter.target_fps < 30.0
    assert limiter.target_fps == pytest.approx(8.0, rel=0.05)  # 10 × 0.8 zaxira


def test_budget_climbs_back_when_headroom_appears() -> None:
    limiter = budget(target_fps=5.0)
    # Har inferens 10 ms — qurilma 100 ta ulguradi, 5 juda past.
    for index in range(40):
        limiter.observe(0.010, now=index * 1.0)
    assert limiter.target_fps > 5.0


def test_budget_never_leaves_its_bounds() -> None:
    limiter = budget(target_fps=30.0, min_fps=4.0, max_fps=50.0)
    for index in range(60):
        limiter.observe(2.0, now=index * 1.0)  # dahshatli sekin
    assert limiter.target_fps == 4.0

    fast = budget(target_fps=30.0, min_fps=4.0, max_fps=50.0)
    for index in range(200):
        fast.observe(0.001, now=index * 1.0)
    assert fast.target_fps == 50.0


def test_external_pressure_lowers_budget_before_latency_shows_it() -> None:
    limiter = budget(target_fps=30.0)
    limiter.set_pressure(0.9)  # CPU/harorat chegarada
    for index in range(20):
        # Latency hali yaxshi — faqat bosim signali bor.
        limiter.observe(0.010, now=index * 1.0)
    assert limiter.target_fps < 30.0


def test_slow_polling_costs_throughput_by_design() -> None:
    """Chaqiruv halqasi sekin aylansa, to'planmagan token yo'qoladi.

    Bu kamchilik emas, ataylab: ishlatilmagan quvvatni yig'ib, keyin qurilmani
    bir zumda bosib qo'yish mumkin emas.  Chaqiruv oralig'i `burst/target_fps`
    dan kichik bo'lishi kerak — 30 FPS va burst=2 uchun 66 ms.
    """

    def granted_per_second(step: float) -> float:
        limiter = budget(target_fps=30.0, min_fps=30.0, max_fps=30.0, burst=2.0)
        now, granted = 0.0, 0
        while now < 10.0:
            while limiter.take(now):
                granted += 1
            now = round(now + step, 6)
        return granted / 10.0

    assert granted_per_second(0.01) == pytest.approx(30.0, rel=0.02)  # 10 ms < 66 ms
    assert granted_per_second(0.2) == pytest.approx(10.0, rel=0.05)  # 200 ms — yo'qotish


def test_budget_rejects_impossible_configuration() -> None:
    with pytest.raises(ValueError):
        InferenceBudget(target_fps=5.0, min_fps=10.0, max_fps=60.0)
    with pytest.raises(ValueError):
        InferenceBudget(target_fps=30.0, min_fps=0.0, max_fps=60.0)


# ── FrameBroker: asosiy xatti-harakat ────────────────────────────────────


def test_no_pending_frame_means_no_claim_and_no_wasted_token() -> None:
    limiter = budget(target_fps=10.0)
    broker = FrameBroker(limiter)
    broker.register("camera-01", priority=Priority.RETAIL, now=0.0)

    assert broker.acquire(now=0.0) is None
    # Token sarflanmagan bo'lishi kerak — kadr kelganda darhol ishlasin.
    broker.submit("camera-01", "kadr", now=0.0)
    claim = broker.acquire(now=0.0)
    assert claim is not None and claim.camera_id == "camera-01"


def test_latest_frame_wins_and_stale_frame_is_counted_as_dropped() -> None:
    broker = FrameBroker(budget(target_fps=10.0))
    broker.register("camera-01", now=0.0)

    assert broker.submit("camera-01", "eski", now=0.0) is True
    assert broker.submit("camera-01", "yangi", now=0.1) is False  # eskisi tashlandi

    claim = broker.acquire(now=0.2)
    assert claim is not None
    assert claim.frame == "yangi"
    assert broker.stats()["dropped"] == 1
    # Navbatda bitta kadrdan ortiq turmaydi.
    assert broker.acquire(now=0.3) is None


def test_camera_in_flight_is_not_handed_out_twice() -> None:
    broker = FrameBroker(budget(target_fps=50.0, max_fps=50.0, burst=5.0))
    broker.register("camera-01", now=0.0)
    broker.submit("camera-01", "a", now=0.0)

    assert broker.acquire(now=0.0) is not None
    broker.submit("camera-01", "b", now=0.01)
    # Tahlil hali tugamagan — ikkinchi worker shu kamerani olmasin.
    assert broker.acquire(now=0.02) is None

    broker.complete("camera-01", latency_sec=0.03, now=0.03)
    assert broker.acquire(now=0.04) is not None


def test_unregistered_camera_is_rejected_loudly() -> None:
    broker = FrameBroker(budget())
    with pytest.raises(KeyError, match="camera-99"):
        broker.submit("camera-99", "kadr", now=0.0)
    with pytest.raises(KeyError):
        broker.complete("camera-99", latency_sec=0.01, now=0.0)


# ── FrameBroker: taqsimot ────────────────────────────────────────────────


def run_simulation(
    broker: FrameBroker,
    cameras: List[str],
    *,
    seconds: float,
    step: float = 0.01,
    latency_sec: float = 0.01,
    motion: Optional[Dict[str, float]] = None,
) -> Tuple[Dict[str, int], float]:
    """Hamma kamera doim kadr beradigan holat — byudjet to'yingan.

    Har qadamda kadr yuboriladi, keyin byudjet ruxsat berguncha da'volar
    olinadi.  Tahlil bir zumda tugaydi deb hisoblanadi (bitta worker).
    """
    motion = motion or {}
    served: Dict[str, int] = {camera: 0 for camera in cameras}
    now = 0.0
    while now < seconds:
        for camera in cameras:
            broker.submit(
                camera, f"{camera}@{now:.2f}", motion_score=motion.get(camera, 1.0), now=now
            )
        while True:
            claim = broker.acquire(now=now)
            if claim is None:
                break
            served[claim.camera_id] += 1
            broker.complete(claim.camera_id, latency_sec=latency_sec, now=now)
        now = round(now + step, 6)
    return served, now


def test_budget_is_shared_in_proportion_to_priority() -> None:
    # Byudjet qotirilgan: bu test taqsimotni tekshiradi, adaptatsiyani emas.
    broker = FrameBroker(budget(target_fps=30.0, min_fps=30.0, max_fps=30.0))
    broker.register("cam-sec", priority=Priority.SECURITY, now=0.0)
    broker.register("cam-retail", priority=Priority.RETAIL, now=0.0)
    broker.register("cam-bg", priority=Priority.BACKGROUND, now=0.0)

    served, elapsed = run_simulation(broker, ["cam-sec", "cam-retail", "cam-bg"], seconds=60.0)

    total = sum(served.values())
    # Byudjetdan oshib ketmasin — asosiy kafolat.
    assert total == pytest.approx(30.0 * elapsed, rel=0.02)
    # Og'irlik 4 : 2 : 1.
    assert served["cam-sec"] / total == pytest.approx(4 / 7, rel=0.08)
    assert served["cam-retail"] / total == pytest.approx(2 / 7, rel=0.08)
    assert served["cam-bg"] / total == pytest.approx(1 / 7, rel=0.08)
    # Quvvat yetarli — hech kim kafolat chegarasiga tushmagan.
    assert broker.stats()["floor_violations"] == 0
    assert broker.stats()["rescued"] == 0


def test_motion_score_shifts_share_between_equal_priority_cameras() -> None:
    broker = FrameBroker(budget(target_fps=20.0, min_fps=20.0, max_fps=20.0))
    broker.register("cam-busy", priority=Priority.RETAIL, now=0.0)
    broker.register("cam-quiet", priority=Priority.RETAIL, now=0.0)

    served, _ = run_simulation(
        broker,
        ["cam-busy", "cam-quiet"],
        seconds=60.0,
        motion={"cam-busy": 1.0, "cam-quiet": 0.0},
    )

    # Harakat ko'p kamera ko'proq oladi, lekin jim kamera yo'qolmaydi:
    # og'irlik 1.0 ga 0.5, ya'ni 2 : 1.
    assert served["cam-busy"] > served["cam-quiet"]
    assert served["cam-busy"] / served["cam-quiet"] == pytest.approx(2.0, rel=0.1)


def test_low_priority_camera_still_gets_its_guaranteed_floor_under_overload() -> None:
    # Byudjet ataylab kichik: talab quvvatdan katta.
    broker = FrameBroker(budget(target_fps=2.0, min_fps=2.0, max_fps=2.0))
    broker.register("cam-sec", priority=Priority.SECURITY, now=0.0)
    broker.register("cam-bg", priority=Priority.BACKGROUND, floor_fps=0.5, now=0.0)

    served, elapsed = run_simulation(broker, ["cam-sec", "cam-bg"], seconds=120.0)

    # Ulush bo'yicha cam-bg 2.0 × 1/5 = 0.4/s olardi — kafolatdan past.
    # Ochlik kafolati uni 0.5/s ga ko'taradi.
    bg_rate = served["cam-bg"] / elapsed
    assert bg_rate >= 0.5 * 0.9
    assert broker.stats()["rescued"] > 0
    # Muhim kamera baribir ko'pchilikni oladi.
    assert served["cam-sec"] > served["cam-bg"]


def test_quiet_camera_is_not_reported_as_starved() -> None:
    """Kechasi ombor eshigi harakatsiz turadi — bu yetishmovchilik emas.

    Kafolat "oxirgi ko'rilgandan beri" emas, "kutayotgan kadr bor bo'lgandan
    beri" o'lchanadi.  Aks holda har harakatsiz kamera harakat boshlanishi bilan
    yolg'on ogohlantirish berardi va metrika ishonchini yo'qotardi.
    """
    broker = FrameBroker(budget(target_fps=30.0, min_fps=30.0, max_fps=30.0))
    broker.register("ombor-eshik", priority=Priority.SECURITY, now=0.0)

    now = 0.0
    while now < 120.0:
        # Har 20 sekundda bir marta harakat — qolgan vaqtda motion gate yopiq.
        if round(now, 3) % 20.0 == 0.0:
            broker.submit("ombor-eshik", "odam", now=now)
        claim = broker.acquire(now=now)
        if claim is not None:
            broker.complete(claim.camera_id, latency_sec=0.03, now=now)
        now = round(now + 0.01, 6)

    stats = broker.stats()
    assert stats["cameras"]["ombor-eshik"]["served"] == 6
    assert stats["floor_violations"] == 0
    assert stats["rescued"] == 0


def test_overloaded_device_reports_floor_violations_instead_of_hiding_them() -> None:
    """Qurilma kam quvvatli bo'lsa buni metrika ko'rsatsin, jim qolmasin."""
    broker = FrameBroker(budget(target_fps=1.0, min_fps=1.0, max_fps=1.0))
    for index in range(1, 9):
        broker.register(f"camera-{index:02d}", priority=Priority.SECURITY, now=0.0)

    cameras = [f"camera-{index:02d}" for index in range(1, 9)]
    served, elapsed = run_simulation(broker, cameras, seconds=60.0)

    stats = broker.stats()
    # 8 ta kamera × 1.0 FPS kafolat = 8/s kerak, byudjet esa 1/s.
    assert stats["floor_violations"] > 0
    assert stats["starved_at_capacity"] > 0
    assert sum(served.values()) == pytest.approx(1.0 * elapsed, rel=0.05)


def test_idle_camera_gets_a_small_burst_when_motion_starts() -> None:
    """Jim turgan kamera kredit yig'adi — harakat boshlanganda tez javob beradi."""
    broker = FrameBroker(budget(target_fps=10.0, min_fps=10.0, max_fps=10.0, burst=5.0))
    broker.register("cam-door", priority=Priority.RETAIL, now=0.0)
    broker.register("cam-hall", priority=Priority.RETAIL, now=0.0)

    # 10 sekund faqat cam-hall ishlaydi; cam-door jim.
    now = 0.0
    while now < 10.0:
        broker.submit("cam-hall", "kadr", now=now)
        while broker.acquire(now=now) is not None:
            pass
        now = round(now + 0.1, 6)

    # Endi eshik ochildi.
    broker.submit("cam-door", "odam", now=now)
    claim = broker.acquire(now=now)
    assert claim is not None
    assert claim.camera_id == "cam-door"


def test_scheduling_is_deterministic() -> None:
    def run() -> List[str]:
        broker = FrameBroker(budget(target_fps=6.0, min_fps=6.0, max_fps=6.0))
        broker.register("cam-a", priority=Priority.SECURITY, now=0.0)
        broker.register("cam-b", priority=Priority.RETAIL, now=0.0)
        broker.register("cam-c", priority=Priority.RETAIL, now=0.0)
        order: List[str] = []
        now = 0.0
        while now < 20.0:
            for camera in ("cam-a", "cam-b", "cam-c"):
                broker.submit(camera, "kadr", now=now)
            while True:
                claim = broker.acquire(now=now)
                if claim is None:
                    break
                order.append(claim.camera_id)
                broker.complete(claim.camera_id, latency_sec=0.01, now=now)
            now = round(now + 0.05, 6)
        return order

    assert run() == run()


def test_reregistering_a_camera_updates_priority_without_losing_history() -> None:
    broker = FrameBroker(budget(target_fps=10.0))
    broker.register("camera-01", priority=Priority.BACKGROUND, now=0.0)
    broker.submit("camera-01", "kadr", now=0.0)
    broker.acquire(now=0.0)

    # Cloud config o'zgardi — kamera endi xavfsizlik vazifasida.
    broker.register("camera-01", priority=Priority.SECURITY, now=5.0)

    camera_stats = broker.stats()["cameras"]["camera-01"]
    assert camera_stats["priority"] == "SECURITY"
    assert camera_stats["floor_fps"] == 1.0
    assert camera_stats["served"] == 1  # tarix saqlandi


def test_unregister_removes_the_camera_from_scheduling() -> None:
    broker = FrameBroker(budget(target_fps=10.0))
    broker.register("camera-01", now=0.0)
    assert broker.unregister("camera-01") is True
    assert broker.unregister("camera-01") is False
    assert broker.camera_ids() == []
