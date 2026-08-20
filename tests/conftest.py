"""Umumiy test sozlamalari.

Rate-limiter jarayon ichida global (`cloud/ratelimit.py`) va TestClient'da
hamma so'rov bitta "IP" dan keladi.  Tozalanmasa bir testning so'rovlari
keyingi testning limitini yeb qo'yadi va to'plam tasodifiy joyda 429 bilan
qulaydi — sababi esa qulagan testda umuman ko'rinmaydi.  Shu fixture har
testni toza hisoblagich bilan boshlaydi; limitni ataylab tekshiradigan
testlar o'z ichida baribir ishlayveradi.
"""

from __future__ import annotations

import pytest

from cloud import ratelimit


@pytest.fixture(autouse=True)
def _fresh_ratelimit():
    ratelimit.limiter().reset()
    yield


@pytest.fixture(autouse=True)
def _no_alert_snapshot_wait(monkeypatch):
    """Rasmli alert snapshot kutishi testlarda 0 bo'lsin.

    Aks holda `has_snapshot=True` hodisali har bir test 20 soniyagacha
    uxlab, butun to'plamni sekinlashtirardi (TestClient background
    tasklarni sinxron bajaradi).
    """
    import cloud.main as main

    monkeypatch.setattr(main, "ALERT_SNAPSHOT_WAIT_SEC", 0)
    yield
