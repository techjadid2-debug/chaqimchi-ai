"""Kamera oqimida ovoz bormi — SDP javobidan o'qish.

Nega bu test bor: ovoz bilan ishlaydigan funksiyalarni rejalashtirishda
birinchi savol "mijozning kamerasi umuman ovoz beradimi".  Javob
`DESCRIBE` javobida allaqachon bor edi, lekin o'qilmasdi.  Har xil
ishlab chiqaruvchi SDP'ni biroz boshqacha yozadi, shuning uchun
haqiqiy kameralardan olingan namunalar qulflanadi.
"""

from __future__ import annotations

from chaqimchi_ai.local.camera_probe import audio_track

# Hikvision: G.711 A-law, rtpmap bilan.
HIKVISION = """v=0
o=- 1109162014219182 0 IN IP4 0.0.0.0
s=Media Presentation
m=video 0 RTP/AVP 96
a=rtpmap:96 H264/90000
m=audio 0 RTP/AVP 8
a=rtpmap:8 PCMA/8000
a=control:trackID=2
"""

# Dahua: AAC.
DAHUA = """v=0
o=- 2890844526 2890842807 IN IP4 192.168.1.10
m=video 0 RTP/AVP 96
a=rtpmap:96 H264/90000
m=audio 0 RTP/AVP 97
a=rtpmap:97 MPEG4-GENERIC/16000/1
"""

# Ovozsiz kamera — faqat video yo'lagi.
VIDEO_ONLY = """v=0
o=- 0 0 IN IP4 0.0.0.0
m=video 0 RTP/AVP 96
a=rtpmap:96 H264/90000
a=control:trackID=1
"""

# Statik payload turi: RFC 3551 bo'yicha 0 = PCMU va rtpmap shart emas.
STATIC_PAYLOAD = """v=0
m=audio 0 RTP/AVP 0
a=control:trackID=2
"""


def test_hikvision_g711_is_detected() -> None:
    track = audio_track(HIKVISION)
    assert track.present
    assert track.codec == "PCMA"
    assert track.sample_rate == 8000


def test_dahua_aac_is_detected() -> None:
    track = audio_track(DAHUA)
    assert track.present
    assert track.codec == "MPEG4-GENERIC"
    assert track.sample_rate == 16000


def test_video_only_camera_reports_no_audio() -> None:
    assert not audio_track(VIDEO_ONLY).present


def test_static_payload_type_needs_no_rtpmap() -> None:
    """`a=rtpmap` yo'q bo'lsa ham 0 va 8 ma'lum (RFC 3551).

    Bu ataylab qulflanadi: eski NVR'lar rtpmap yozmaydi va soddaroq
    parser ularni "ovozsiz" deb belgilab qo'yardi.
    """
    track = audio_track(STATIC_PAYLOAD)
    assert track.present
    assert track.codec == "PCMU"


def test_empty_response_is_not_a_crash() -> None:
    """Ulanmagan kamerada `rtsp_describe` bo'sh matn qaytaradi."""
    assert not audio_track("").present
