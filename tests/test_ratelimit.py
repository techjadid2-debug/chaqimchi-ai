"""Tezlik cheklovi: bitta buzuq mijoz cloud'ni yiqita olmasin."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from cloud import ratelimit
from cloud.ratelimit import RateLimiter


@pytest.fixture(autouse=True)
def clean_limiter():
    ratelimit.limiter().reset()
    yield
    ratelimit.limiter().reset()


def test_limit_allows_up_to_threshold_then_blocks() -> None:
    limiter = RateLimiter()
    assert all(limiter.hit("leads", "1.2.3.4", limit=3, window_sec=60) for _ in range(3))
    assert not limiter.hit("leads", "1.2.3.4", limit=3, window_sec=60)


def test_keys_and_buckets_are_independent() -> None:
    limiter = RateLimiter()
    for _ in range(3):
        limiter.hit("leads", "1.2.3.4", limit=3, window_sec=60)
    # Boshqa IP va boshqa bucket o'z hisobiga ega.
    assert limiter.hit("leads", "9.9.9.9", limit=3, window_sec=60)
    assert limiter.hit("otp", "1.2.3.4", limit=3, window_sec=60)


def test_window_expiry_restores_quota(monkeypatch) -> None:
    limiter = RateLimiter()
    clock = {"now": 1_000.0}
    monkeypatch.setattr("cloud.ratelimit.time.monotonic", lambda: clock["now"])

    assert limiter.hit("events", "dev-1", limit=1, window_sec=60)
    assert not limiter.hit("events", "dev-1", limit=1, window_sec=60)

    clock["now"] += 61
    assert limiter.hit("events", "dev-1", limit=1, window_sec=60)


def test_a_long_window_survives_the_memory_sweep(monkeypatch) -> None:
    """Kunlik chegara kun bo'yi ushlab tursin.

    Xotira tozalash har 5 daqiqada eskirgan kalitlarni o'chirardi, lekin
    "eskirgan"ni oynaning **o'z** muddati bilan emas, tozalash oralig'i
    bilan o'lchardi.  Ya'ni kunlik 500 ta rasm chegarasi amalda 5 daqiqada
    500 ta bo'lardi — kuniga ~1 TB, disk to'lsa baza ishlamay qoladi.

    `RateLimiter()` ataylab yangidan yaratiladi: `_last_sweep` konstruktorda
    HAQIQIY soatdan olinadi, monkeypatch esa undan keyin qo'yiladi — eski
    test aynan shu sabab tozalashni umuman ishga tushira olmasdi.
    """
    clock = {"now": 1_000.0}
    monkeypatch.setattr("cloud.ratelimit.time.monotonic", lambda: clock["now"])
    limiter = RateLimiter()

    day = 86_400
    assert limiter.hit("snapshots", "dev-1", limit=2, window_sec=day)
    assert limiter.hit("snapshots", "dev-1", limit=2, window_sec=day)
    assert not limiter.hit("snapshots", "dev-1", limit=2, window_sec=day)

    # Tozalash oralig'idan o'tdi, lekin sutkalik oyna hali tugamadi.
    clock["now"] += ratelimit._SWEEP_EVERY_SEC * 3
    assert not limiter.hit("snapshots", "dev-1", limit=2, window_sec=day), (
        "kunlik chegara 5 daqiqadan keyin qayta ochilmasin"
    )

    # Sutka o'tgach kvota tiklanadi.
    clock["now"] += day
    assert limiter.hit("snapshots", "dev-1", limit=2, window_sec=day)


def test_the_sweep_still_frees_memory_for_finished_windows(monkeypatch) -> None:
    """Tozalashning maqsadi saqlanib qolsin: tugagan oynalar o'chirilsin,
    aks holda har IP uchun yozuv abadiy yig'ilardi."""
    clock = {"now": 1_000.0}
    monkeypatch.setattr("cloud.ratelimit.time.monotonic", lambda: clock["now"])
    limiter = RateLimiter()

    limiter.hit("leads", "1.2.3.4", limit=3, window_sec=60)
    assert limiter.size() == 1

    clock["now"] += ratelimit._SWEEP_EVERY_SEC + 1
    limiter.hit("leads", "9.9.9.9", limit=3, window_sec=60)

    assert limiter.size() == 1, "tugagan oyna xotirada qolmasin"


def test_check_raises_429_with_retry_after() -> None:
    ratelimit.check("otp", "555", limit=1, window_sec=600, message="Kod juda ko'p so'raldi")
    with pytest.raises(HTTPException) as exc:
        ratelimit.check("otp", "555", limit=1, window_sec=600, message="Kod juda ko'p so'raldi")
    assert exc.value.status_code == 429
    assert exc.value.headers["Retry-After"] == "600"


# ── Rad etishlar KO'RINSIN ───────────────────────────────────────────────
#
# 2026-08-26: jonli do'konda 3 soat davomida 6 315 ta rasm rad etildi va
# buni hech kim sezmadi.  429 qaytarilib UNUTILARDI: ERROR log yo'q,
# panelda son yo'q, `/health` esa "hammasi joyida" derdi.  Nosozlikni
# mijoz aytdi, biz emas.


def test_rejections_are_counted_per_bucket_and_key() -> None:
    limiter = RateLimiter()
    for _ in range(5):
        limiter.hit("snapshots", "site-1", limit=3, window_sec=3600)

    # 3 tasi o'tdi, 2 tasi rad etildi.
    assert limiter.rejections("site-1") == {"snapshots": 2}
    assert limiter.used("snapshots", "site-1") == 5


def test_rejections_do_not_leak_between_sites() -> None:
    limiter = RateLimiter()
    for _ in range(4):
        limiter.hit("snapshots", "site-1", limit=1, window_sec=3600)
    limiter.hit("snapshots", "site-2", limit=10, window_sec=3600)

    assert limiter.rejections("site-1") == {"snapshots": 3}
    assert limiter.rejections("site-2") == {}
    # Kalitsiz chaqiruv — butun platforma bo'yicha yig'indi.
    assert limiter.rejections() == {"snapshots": 3}


def test_clean_limiter_reports_nothing() -> None:
    """Hech narsa rad etilmagan bo'lsa panel bo'sh ko'rsatsin — nol emas."""
    limiter = RateLimiter()
    limiter.hit("snapshots", "site-1", limit=10, window_sec=3600)
    assert limiter.rejections() == {}


def test_used_forgets_an_expired_window() -> None:
    limiter = RateLimiter()
    limiter.hit("snapshots", "site-1", limit=10, window_sec=0)
    assert limiter.used("snapshots", "site-1") == 0
