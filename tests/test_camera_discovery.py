"""Kamera kashfiyoti (Discovery) va ZoneEditor funksiyalari uchun testlar."""

import socket
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from chaqimchi_ai.discovery import (
    COMMON_RTSP_TEMPLATES,
    discover_cameras_all,
    get_local_ip_range,
    onvif_ws_discovery,
    probe_ip_camera_services,
    scan_local_network_for_cameras,
)


def test_rtsp_templates_contain_standard_vendors():
    names = [t["name"] for t in COMMON_RTSP_TEMPLATES]
    assert any("Hikvision" in n for n in names)
    assert any("Dahua" in n for n in names)
    assert any("XM" in n or "Xiongmai" in n for n in names)
    assert any("Uniview" in n for n in names)


def test_get_local_ip_range_returns_tuple():
    local_ip, candidate_ips = get_local_ip_range()
    assert isinstance(local_ip, str)
    assert isinstance(candidate_ips, list)


@pytest.mark.asyncio
async def test_probe_ip_camera_services_mock():
    with patch("chaqimchi_ai.discovery._probe_tcp_port", new_callable=AsyncMock) as mock_probe:
        # Port 554 ochiq
        mock_probe.side_effect = lambda ip, port, timeout=0.5: port == 554
        res = await probe_ip_camera_services("192.168.1.120")
        assert res is not None
        assert res["ip"] == "192.168.1.120"
        assert res["has_rtsp"] is True
        assert res["rtsp_port"] == 554

        # Portlar yopiq
        mock_probe.side_effect = lambda ip, port, timeout=0.5: False
        res_none = await probe_ip_camera_services("192.168.1.99")
        assert res_none is None


@pytest.mark.asyncio
async def test_scan_local_network_mock():
    # Skanerlash endi **barcha** interfeysdan boradi: NVR ko'pincha
    # internetdan alohida kabelda turadi va faqat standart yo'nalishni
    # tekshirish uni ko'rmasdan qoldirardi.
    with patch(
        "chaqimchi_ai.discovery.local_ipv4_addresses",
        return_value=["192.168.1.10"],
    ):
        with patch(
            "chaqimchi_ai.discovery.probe_ip_camera_services", new_callable=AsyncMock
        ) as mock_probe:
            mock_probe.side_effect = lambda ip: (
                {"ip": ip, "has_rtsp": True, "rtsp_port": 554} if ip == "192.168.1.20" else None
            )
            devices = await scan_local_network_for_cameras()
            assert len(devices) == 1
            assert devices[0]["ip"] == "192.168.1.20"
            # O'z manzilini so'ramaslik kerak.
            assert "192.168.1.10" not in {call.args[0] for call in mock_probe.call_args_list}


@pytest.mark.asyncio
async def test_scan_covers_every_interface():
    """Ikkita tarmoq bo'lsa ikkalasi ham skanerlanadi."""
    with patch(
        "chaqimchi_ai.discovery.local_ipv4_addresses",
        return_value=["192.168.1.10", "10.10.0.5"],
    ):
        with patch(
            "chaqimchi_ai.discovery.probe_ip_camera_services", new_callable=AsyncMock
        ) as mock_probe:
            mock_probe.return_value = None
            await scan_local_network_for_cameras()

    asked = {call.args[0] for call in mock_probe.call_args_list}
    assert "192.168.1.20" in asked
    assert "10.10.0.20" in asked


def test_onvif_ws_discovery_mock():
    with patch("socket.socket") as mock_sock_cls:
        mock_sock = MagicMock()
        mock_sock_cls.return_value = mock_sock

        sample_response = b"""<Envelope>
            <Body>
                <ProbeMatches>
                    <ProbeMatch>
                        <XAddrs>http://192.168.1.60:80/onvif/device_service</XAddrs>
                        <Scopes>onvif://www.onvif.org/hardware/Hikvision-DS2CD onvif://www.onvif.org/name/FrontEntrance</Scopes>
                    </ProbeMatch>
                </ProbeMatches>
            </Body>
        </Envelope>"""

        # 1-marta javob, 2-marta timeout
        mock_sock.recvfrom.side_effect = [
            (sample_response, ("192.168.1.60", 3702)),
            socket.timeout("timed out"),
        ]

        found = onvif_ws_discovery(timeout_sec=0.1)
        assert len(found) == 1
        assert found[0]["ip"] == "192.168.1.60"
        assert (
            "Hikvision-DS2CD" in found[0]["vendor_hint"]
            or "FrontEntrance" in found[0]["vendor_hint"]
            or found[0]["has_onvif"]
        )


@pytest.mark.asyncio
async def test_discover_cameras_all():
    with patch(
        "chaqimchi_ai.discovery.onvif_ws_discovery",
        return_value=[{"ip": "192.168.1.55", "has_onvif": True}],
    ):
        with patch(
            "chaqimchi_ai.discovery.scan_local_network_for_cameras", new_callable=AsyncMock
        ) as mock_scan:
            mock_scan.return_value = [{"ip": "192.168.1.55", "has_rtsp": True, "rtsp_port": 554}]
            devices = await discover_cameras_all(timeout_sec=0.1)
            assert len(devices) == 1
            assert devices[0]["ip"] == "192.168.1.55"
            assert "suggested_urls" in devices[0]
            assert len(devices[0]["suggested_urls"]) > 0


# ── Endpoint haqiqatan qidiruvni chaqiradimi ─────────────────────────────
#
# Tarixiy xato: cloud'dagi `/api/v1/agent/discovery/scan` mavjud bo'lmagan
# `discover_network_cameras` nomini import qilardi, `except Exception` esa
# `ImportError` ni yutib **doim** bo'sh ro'yxat qaytarardi.  O'sha paytdagi
# test faqat `ok is True` va ro'yxat turini tekshirgani uchun yashil turardi,
# saytda esa "kameralarni 2 daqiqada avtomatik topadi" deb yozilgan edi.
#
# Shuning uchun endi ikki narsa tekshiriladi: (1) endpoint haqiqiy funksiyani
# chaqiradi, (2) xato bo'lsa uni **yutmaydi**.


@pytest.fixture
def local_client(tmp_path, monkeypatch):
    monkeypatch.setenv("CHAQIMCHI_LOCAL_DIR", str(tmp_path))
    import importlib

    from fastapi.testclient import TestClient

    from chaqimchi_ai.local import app as app_module
    from chaqimchi_ai.local import config_store, paths, supervisor

    importlib.reload(paths)
    importlib.reload(config_store)
    importlib.reload(supervisor)
    importlib.reload(app_module)
    return TestClient(app_module.app)


def test_scan_endpoint_calls_the_real_discovery(local_client):
    with patch(
        "chaqimchi_ai.discovery.discover_cameras_all", new_callable=AsyncMock
    ) as mock_discover:
        mock_discover.return_value = [
            {
                "ip": "192.168.1.64",
                "vendor_hint": "Hikvision",
                "has_rtsp": True,
                "has_onvif": True,
                "rtsp_port": 554,
                "suggested_urls": [{"name": "Hikvision Substream", "url": "rtsp://…", "path": "/x"}],
            }
        ]
        response = local_client.post("/api/setup/scan")

    assert mock_discover.await_count == 1, "endpoint haqiqiy qidiruvni chaqirishi shart"
    body = response.json()
    assert body["count"] == 1
    assert body["devices"][0]["ip"] == "192.168.1.64"
    assert body["devices"][0]["vendor"] == "Hikvision"


def test_scan_endpoint_does_not_swallow_failures(local_client):
    """Xato yutilsa mijoz "kamera yo'q" deb o'ylaydi va qo'lda kiritishga
    ham o'tmaydi — eng yomon holat."""
    with patch(
        "chaqimchi_ai.discovery.discover_cameras_all", new_callable=AsyncMock
    ) as mock_discover:
        mock_discover.side_effect = OSError("tarmoq yopiq")
        with pytest.raises(OSError):
            local_client.post("/api/setup/scan")


def test_main_stream_is_suggested_for_known_brands() -> None:
    """Klip uchun asosiy oqim substream manzilidan chiqariladi."""
    from chaqimchi_ai.local.camera_probe import suggest_record_url

    cases = {
        "rtsp://u:p@h:554/Streaming/Channels/102": "rtsp://u:p@h:554/Streaming/Channels/101",
        "rtsp://u:p@h:554/cam/realmonitor?channel=1&subtype=1":
            "rtsp://u:p@h:554/cam/realmonitor?channel=1&subtype=0",
        "rtsp://u:p@h:554/unicast/c2/s1/live": "rtsp://u:p@h:554/unicast/c2/s0/live",
        "rtsp://u:p@h:554/stream2": "rtsp://u:p@h:554/stream1",
    }
    for sub, main in cases.items():
        assert suggest_record_url(sub) == main, sub
    # Notanish yo'l uchun taxmin qilinmaydi — noto'g'ri taxmin ffmpeg'ni
    # abadiy xatoga aylantirardi.
    assert suggest_record_url("rtsp://u:p@h:554/qandaydir/yol") is None
