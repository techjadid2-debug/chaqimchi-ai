"""ONVIF orqali kamera qo'shish va brendni aniqlash.

Nega bu testlar bor.  ONVIF ilgari faqat qurilmani *topish* uchun
ishlatilardi, RTSP yo'li esa qattiq ro'yxatdan **taxmin** qilinardi.
Ro'yxatda bo'lmagan kamera "tasvir kelmadi" bilan tugardi va mijozda
tuzatishning imkoni yo'q edi.

Shu sababli bu yerda haqiqiy SOAP javoblari (real kameralardan olingan
shakl) ishlatiladi: mock qilingan funksiya emas, aynan XML ni o'qish
tekshiriladi — chunki xato aynan o'sha yerda bo'lgan.
"""

from __future__ import annotations

import re
from typing import List

import httpx
import pytest

from chaqimchi_ai import discovery
from chaqimchi_ai.local import camera_probe, onvif_client

# ── Real kameralar qaytaradigan javoblar ─────────────────────────────────
#
# Prefikslar ataylab har xil (`tds:`, `trt:`, `tt:` va prefiksi:z):
# har ishlab chiqaruvchi o'zicha yozadi va qat'iy nom bo'shlig'i bilan
# qidirish real qurilmalarda ishlamaydi.

DEVICE_INFO_XML = """<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope"
              xmlns:tds="http://www.onvif.org/ver10/device/wsdl">
 <env:Body>
  <tds:GetDeviceInformationResponse>
   <tds:Manufacturer>Hangzhou Hikvision Digital Technology Co.,Ltd.</tds:Manufacturer>
   <tds:Model>DS-2CD2043G0-I</tds:Model>
   <tds:FirmwareVersion>V5.6.3</tds:FirmwareVersion>
   <tds:SerialNumber>DS-2CD2043G0</tds:SerialNumber>
  </tds:GetDeviceInformationResponse>
 </env:Body>
</env:Envelope>"""

CAPABILITIES_XML = """<?xml version="1.0"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">
 <s:Body><GetCapabilitiesResponse><Capabilities>
   <Media><XAddr>http://192.168.1.64/onvif/media_service</XAddr></Media>
 </Capabilities></GetCapabilitiesResponse></s:Body>
</s:Envelope>"""

PROFILES_XML = """<?xml version="1.0"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
            xmlns:trt="http://www.onvif.org/ver10/media/wsdl"
            xmlns:tt="http://www.onvif.org/ver10/schema">
 <s:Body><trt:GetProfilesResponse>
  <trt:Profiles token="Profile_1">
    <tt:Name>mainStream</tt:Name>
    <tt:VideoEncoderConfiguration>
      <tt:Encoding>H265</tt:Encoding>
      <tt:Resolution><tt:Width>1920</tt:Width><tt:Height>1080</tt:Height></tt:Resolution>
      <tt:RateControl><tt:FrameRateLimit>25</tt:FrameRateLimit></tt:RateControl>
    </tt:VideoEncoderConfiguration>
  </trt:Profiles>
  <trt:Profiles token="Profile_2">
    <tt:Name>subStream</tt:Name>
    <tt:VideoEncoderConfiguration>
      <tt:Encoding>H264</tt:Encoding>
      <tt:Resolution><tt:Width>640</tt:Width><tt:Height>360</tt:Height></tt:Resolution>
      <tt:RateControl><tt:FrameRateLimit>12</tt:FrameRateLimit></tt:RateControl>
    </tt:VideoEncoderConfiguration>
  </trt:Profiles>
 </trt:GetProfilesResponse></s:Body>
</s:Envelope>"""


def _stream_uri(token: str) -> str:
    suffix = "101" if token == "Profile_1" else "102"
    return f"""<?xml version="1.0"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">
 <s:Body><GetStreamUriResponse><MediaUri>
  <Uri>rtsp://192.168.1.64:554/Streaming/Channels/{suffix}</Uri>
 </MediaUri></GetStreamUriResponse></s:Body>
</s:Envelope>"""


class FakeCamera:
    """ONVIF so'rovlariga javob beradigan soxta kamera."""

    def __init__(self, *, require_auth: bool = True) -> None:
        self.require_auth = require_auth
        self.calls: List[str] = []
        self.paths: List[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = request.content.decode("utf-8", "replace")
        self.paths.append(request.url.path)

        if self.require_auth and "UsernameToken" not in body:
            return httpx.Response(401)

        for name in ("GetDeviceInformation", "GetCapabilities", "GetProfiles", "GetStreamUri"):
            if name in body:
                self.calls.append(name)
                break

        if "GetDeviceInformation" in body:
            return httpx.Response(200, text=DEVICE_INFO_XML)
        if "GetCapabilities" in body:
            return httpx.Response(200, text=CAPABILITIES_XML)
        if "GetProfiles" in body:
            return httpx.Response(200, text=PROFILES_XML)
        if "GetStreamUri" in body:
            match = re.search(r"<ProfileToken>([^<]+)</ProfileToken>", body)
            return httpx.Response(200, text=_stream_uri(match.group(1) if match else ""))
        return httpx.Response(400)


@pytest.fixture
def camera(monkeypatch: pytest.MonkeyPatch) -> FakeCamera:
    fake = FakeCamera()
    transport = httpx.MockTransport(fake.handler)
    original = httpx.Client

    def _client(*args, **kwargs):
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr(onvif_client.httpx, "Client", _client)
    return fake


# ── Asosiy oqim: kamera manzilni o'zi beradi ─────────────────────────────


def test_onvif_returns_the_real_stream_url(camera: FakeCamera) -> None:
    """Eng muhim tekshiruv: manzil **taxmin qilinmaydi**, so'raladi."""
    result = onvif_client.describe("192.168.1.64", username="admin", password="parol")

    assert result.ok
    assert len(result.profiles) == 2
    uris = {profile.uri for profile in result.profiles}
    assert "rtsp://192.168.1.64:554/Streaming/Channels/102" in uris


def test_brand_comes_from_the_camera_itself(camera: FakeCamera) -> None:
    """«Avtomatik brendni topmayapti» — sabab shu chaqiruv yo'qligida edi."""
    result = onvif_client.describe("192.168.1.64", username="admin", password="parol")

    assert result.device.manufacturer.startswith("Hangzhou Hikvision")
    assert result.device.model == "DS-2CD2043G0-I"
    # Panelga uzun rasmiy nom emas, qisqasi chiqadi.
    assert onvif_client.normalise_brand(result.device.brand) == "Hikvision"


def test_substream_is_preferred_over_main(camera: FakeCamera) -> None:
    """1080p H.265 ni tanlash eski kompyuterda tahlilni to'xtatardi."""
    result = onvif_client.describe("192.168.1.64", username="admin", password="parol")
    best = onvif_client.pick_best_profile(result.profiles)

    assert best is not None
    assert best.encoding == "H264"
    assert (best.width, best.height) == (640, 360)


def test_credentials_are_added_to_the_stream_url() -> None:
    """`GetStreamUri` parolsiz manzil qaytaradi — OpenCV uni ocholmaydi."""
    url = onvif_client.with_credentials(
        "rtsp://192.168.1.64:554/Streaming/Channels/102", "admin", "p@rol"
    )
    assert url.startswith("rtsp://admin:p%40rol@192.168.1.64:554/")


def test_internal_host_is_replaced_with_the_reachable_one() -> None:
    """Kamera o'zining ichki manzilini qaytarishi mumkin — u yerga
    ulanib bo'lmaydi va sabab mutlaqo tushunarsiz bo'lardi."""
    url = onvif_client.with_credentials(
        "rtsp://10.0.0.5:554/live", "admin", "parol", host="192.168.1.64"
    )
    assert "192.168.1.64:554" in url
    assert "10.0.0.5" not in url


def test_media_service_keeps_the_reachable_host(camera: FakeCamera) -> None:
    """`GetCapabilities` ichki manzil bersa ham so'rov yetib borishi kerak."""
    media = onvif_client.get_media_service(
        "http://192.168.1.99/onvif/device_service", "admin", "parol"
    )
    assert media.startswith("http://192.168.1.99/")


# ── Autentifikatsiya ─────────────────────────────────────────────────────


def test_password_is_never_sent_in_the_clear(camera: FakeCamera) -> None:
    """ONVIF PasswordDigest talab qiladi: parol ochiq ketmasligi kerak."""
    sent: List[str] = []
    original = onvif_client._envelope

    def _spy(body: str, username: str, password: str) -> str:
        envelope = original(body, username, password)
        sent.append(envelope)
        return envelope

    onvif_client._envelope = _spy
    try:
        onvif_client.describe("192.168.1.64", username="admin", password="MaxfiyParol")
    finally:
        onvif_client._envelope = original

    assert sent, "hech qanday so'rov yuborilmadi"
    assert all("MaxfiyParol" not in envelope for envelope in sent)
    assert any("PasswordDigest" in envelope for envelope in sent)


def test_wrong_credentials_give_an_actionable_message(monkeypatch) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(401))
    original = httpx.Client
    monkeypatch.setattr(
        onvif_client.httpx,
        "Client",
        lambda *a, **k: original(*a, **{**k, "transport": transport}),
    )

    result = onvif_client.describe("192.168.1.64", username="admin", password="xato")

    assert not result.ok
    assert "ONVIF" in result.error
    assert result.hint, "mijozga nima qilish kerakligi aytilishi shart"


# ── Protokol mosligi ─────────────────────────────────────────────────────
#
# Mijoz kamerani qo'shishdan **oldin** bilishi kerak.  Ilgari H.265
# kamera muammosiz qo'shilardi va faqat hisobot bo'sh chiqqanda,
# bir necha kundan keyin bilinardi.


def test_h265_is_flagged_before_the_camera_is_added() -> None:
    profile = onvif_client.StreamProfile(
        token="1", name="main", encoding="H265", width=1920, height=1080
    )
    warning, advice = onvif_client.compatibility_note(profile)

    assert "H.265" in warning
    assert "H.264" in advice


def test_h264_substream_raises_no_warning() -> None:
    profile = onvif_client.StreamProfile(
        token="2", name="sub", encoding="H264", width=640, height=360
    )
    assert onvif_client.compatibility_note(profile) == ("", "")


def test_oversized_stream_is_flagged() -> None:
    profile = onvif_client.StreamProfile(
        token="3", name="main", encoding="H264", width=1920, height=1080
    )
    warning, _advice = onvif_client.compatibility_note(profile)
    assert "1920" in warning


def test_mjpeg_is_flagged() -> None:
    profile = onvif_client.StreamProfile(
        token="4", name="mjpeg", encoding="JPEG", width=640, height=480
    )
    warning, _ = onvif_client.compatibility_note(profile)
    assert "MJPEG" in warning


# ── Xavfsizlik: kamera ishonchsiz manba ──────────────────────────────────


def test_entity_expansion_is_refused() -> None:
    """XML bomba: kichik javob xotirada gigabaytga yoyilishi mumkin."""
    bomb = (
        b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">'
        b'<!ENTITY lol2 "&lol;&lol;&lol;">]><Envelope>&lol2;</Envelope>'
    )
    assert onvif_client._parse(bomb) is None


def test_oversized_response_is_refused() -> None:
    assert onvif_client._parse(b"<a/>" * onvif_client.MAX_RESPONSE_BYTES) is None


def test_malformed_xml_does_not_raise() -> None:
    assert onvif_client._parse(b"<Envelope><unclosed>") is None


# ── Brendni ONVIF'siz aniqlash ───────────────────────────────────────────
#
# ONVIF o'chirilgan yoki parol noma'lum bo'lsa ham qurilma har javobda
# o'zini tanitadi.  Bu bepul ma'lumot ilgari umuman ishlatilmasdi va
# panelda hamma narsa "IP Camera / NVR" bo'lib turardi.


@pytest.mark.parametrize(
    "banner,expected",
    [
        ('WWW-Authenticate: Digest realm="IP Camera(43297)"', "Hikvision"),
        ("Server: Dahua Rtsp Server", "Dahua"),
        ("Server: Hipcam RealServer/V1.0", "Xiongmai"),
        ("Server: App-webs/", "Hikvision"),
        ("Server: H264DVRRtspServer", "Xiongmai / DVR"),
        ("RTSP/1.0 200 OK\r\nServer: UNIVIEW RTSP", "Uniview"),
        ("Server: nginx/1.18", ""),
        ("", ""),
    ],
)
def test_brand_is_read_from_the_banner(banner: str, expected: str) -> None:
    assert onvif_client.brand_from_banner(banner) == expected


def test_known_brand_paths_are_tried_first() -> None:
    """Brend ma'lum bo'lsa o'nta variantni sinash shart emas."""
    ordered = camera_probe.order_paths("Dahua")
    assert "Dahua" in ordered[0][0]
    # Hech bir yo'l yo'qolmasligi kerak — faqat tartib o'zgaradi.
    assert set(ordered) == set(camera_probe.KNOWN_PATHS)


def test_unknown_brand_keeps_the_original_order() -> None:
    assert camera_probe.order_paths("Noma'lum brend") == camera_probe.KNOWN_PATHS
    assert camera_probe.order_paths("") == camera_probe.KNOWN_PATHS


# ── WS-Discovery ─────────────────────────────────────────────────────────


def test_probe_uses_a_fresh_message_id() -> None:
    """Takrorlangan MessageID ni kameralar «javob berdim» deb tashlaydi —
    shu sabab qidiruv faqat birinchi marta ishlardi."""
    ids = set()
    for _ in range(3):
        for packet in discovery._probe_packets():
            found = re.search(rb"uuid:([0-9a-f-]+)", packet)
            assert found is not None
            ids.add(found.group(1))
    assert len(ids) > 1, "har paketda yangi MessageID bo'lishi kerak"


def test_probe_is_not_filtered_to_device_type() -> None:
    """Kameralar o'zini `NetworkVideoTransmitter` deb e'lon qiladi va
    `tds:Device` filtriga javob bermaydi."""
    packets = [packet.decode() for packet in discovery._probe_packets()]
    assert any("<Types>" not in packet for packet in packets), "filtrsiz Probe bo'lishi shart"
    assert not any("tds:Device" in packet for packet in packets)


def test_probe_is_repeated() -> None:
    """UDP paketi yo'qolishi odatiy hol."""
    assert len(discovery._probe_packets()) >= 4


def test_probe_match_is_parsed() -> None:
    reply = (
        '<?xml version="1.0"?><Envelope><Body><ProbeMatches><ProbeMatch>'
        "<XAddrs>http://192.168.1.64:80/onvif/device_service</XAddrs>"
        "<Scopes>onvif://www.onvif.org/name/HIKVISION "
        "onvif://www.onvif.org/hardware/DS-2CD2043 "
        "onvif://www.onvif.org/location/city/hangzhou</Scopes>"
        "</ProbeMatch></ProbeMatches></Body></Envelope>"
    )
    device = discovery._parse_probe_match(reply, "192.168.1.64")

    assert device is not None
    assert device["ip"] == "192.168.1.64"
    assert device["has_onvif"] is True
    # Joylashuv scope'i qurilma nomini bosib ketmasligi kerak.
    assert "HIKVISION" in device["vendor_hint"]
    assert "hangzhou" not in device["vendor_hint"].lower()


def test_vendor_prefers_name_over_location() -> None:
    scopes = (
        "onvif://www.onvif.org/location/country/uz "
        "onvif://www.onvif.org/name/DahuaNVR "
        "onvif://www.onvif.org/Profile/Streaming"
    )
    assert discovery.vendor_from_scopes(scopes) == "DahuaNVR"


def test_scopes_without_a_name_still_return_something() -> None:
    assert discovery.vendor_from_scopes("") == "ONVIF qurilma"


def test_all_interfaces_are_considered() -> None:
    """NVR ko'pincha internetdan alohida kabelda turadi — faqat standart
    yo'nalishni tekshirish uni ko'rmasdan qoldirardi."""
    addresses = discovery.local_ipv4_addresses()
    assert all(not a.startswith("127.") for a in addresses)
    assert all(not a.startswith("169.254.") for a in addresses)
