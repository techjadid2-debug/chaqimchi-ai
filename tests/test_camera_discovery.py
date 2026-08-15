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
    with patch(
        "chaqimchi_ai.discovery.get_local_ip_range",
        return_value=("192.168.1.10", ["192.168.1.20", "192.168.1.30"]),
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
