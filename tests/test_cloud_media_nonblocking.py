"""Media bilan ishlash hodisa halqasini bloklamasligi kerak.

Server bitta uvicorn ishchisida ishlaydi.  Ilgari 50 MB klip MinIO'ga
`async def` ichidan to'g'ridan-to'g'ri yozilardi — yozuv tugaguncha BUTUN
bulut (barcha do'konning heartbeat'i, panel, Telegram bot) javob bermay
turardi.  Ikkala test shu holatning qaytib kelishini to'sadi.
"""

from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path

import httpx
import pytest

# ── 1. Statik qo'riqchi: bloklovchi chaqiruv qaytib kelmasin ─────────────


def test_no_async_endpoint_touches_the_blocking_store_directly() -> None:
    """`async def` ichida `get_snapshot_store().put/get/delete` bo'lmasin.

    To'g'ri yo'l — `media_put` / `media_get` / `media_delete`, ular
    `asyncio.to_thread` orqali o'tadi.  Sinxron funksiyalarda
    (`_purge_expired_events`) to'g'ridan-to'g'ri chaqirish joiz: ular
    allaqachon alohida oqimda ishlaydi.
    """
    lines = (Path(__file__).resolve().parent.parent / "cloud" / "main.py").read_text().splitlines()
    offenders = []
    for index, line in enumerate(lines):
        if "get_snapshot_store()" not in line:
            continue
        if not re.search(r"\.(put|get|delete)\(", line):
            continue
        for back in range(index, -1, -1):
            found = re.match(r"^(async def|def) (\w+)", lines[back])
            if found:
                if found.group(1) == "async def":
                    offenders.append(f"{index + 1}-qator ({found.group(2)}): {line.strip()}")
                break
    assert not offenders, "async yo'lda bloklovchi media chaqiruvi:\n" + "\n".join(offenders)


# ── 2. Xulq: sekin yuklash boshqa so'rovni ushlab qolmasin ───────────────


@pytest.fixture
def cloud_app(tmp_path, monkeypatch):
    monkeypatch.setenv("CHAQIMCHI_CLOUD_ADMIN_KEY", "test-admin")
    monkeypatch.setattr("cloud.main.DB_PATH", tmp_path / "c.db")
    monkeypatch.setattr("cloud.main._store", None)
    from cloud.main import app

    return app


def test_a_slow_upload_does_not_freeze_the_rest_of_the_server(cloud_app, monkeypatch) -> None:
    """Sekin `put` ketayotganda `/health` darhol javob berishi kerak."""
    import cloud.main as main

    upload_seconds = 0.6

    class SlowStore:
        bucket = "test"

        def put(self, key, data, *, content_type="application/octet-stream"):
            # Bloklovchi (sinxron) yozuv — aynan MinIO mijoziday.
            time.sleep(upload_seconds)

    monkeypatch.setattr(main, "get_snapshot_store", lambda: SlowStore())

    async def exercise() -> float:
        transport = httpx.ASGITransport(app=cloud_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Vaqt yuklash BOSHLANISHIDAN o'lchanadi.  Ilgari u `sleep`
            # dan keyin olinardi — bloklovchi yozuv o'sha paytda allaqachon
            # tugagan bo'lardi va test buzuq kodni ham yashil o'tkazardi.
            started = time.monotonic()
            slow = asyncio.create_task(main.media_put("k", b"x" * 1024, content_type="video/mp4"))
            await asyncio.sleep(0.05)  # yuklash boshlanib ulgursin
            response = await client.get("/health")
            elapsed = time.monotonic() - started
            assert response.status_code == 200
            await slow
            return elapsed

    elapsed = asyncio.run(exercise())
    assert elapsed < upload_seconds / 2, (
        f"/health {elapsed:.2f}s kutdi — media yuklash hodisa halqasini bloklayapti"
    )
