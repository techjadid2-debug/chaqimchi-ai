import numpy as np

from chaqimchi_ai import scene_analytics as scene
from chaqimchi_ai.scene_analytics import SceneAnalyzer
from chaqimchi_ai.settings import SceneSettings


class FakeDetector:
    def detect(self, frame):
        return [{"bbox": [20.0, 20.0, 80.0, 90.0], "score": 0.9}]


def test_scene_analyzer_emits_four_core_event_types() -> None:
    settings = SceneSettings.model_validate(
        {
            "enabled": True,
            "burst_fps": 5,
            "loitering_sec": 5,
            "occupancy_limit": 1,
            "event_debounce_sec": 1,
            "zones": [
                {
                    "name": "ombor",
                    "camera_id": "cam-1",
                    "restricted": True,
                    "polygon": [[0, 0], [1, 0], [1, 1], [0, 1]],
                }
            ],
        }
    )
    analyzer = SceneAnalyzer("cam-1", FakeDetector(), settings)
    analyzer.motion.has_motion = lambda _frame: True
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    first = analyzer.process(frame, now=10)
    assert {event.event_type for event in first} == {
        "person_detected",
        "zone_entered",
        "occupancy_exceeded",
    }
    assert next(e for e in first if e.event_type == "zone_entered").severity == "warning"

    later = analyzer.process(frame, now=16)
    assert "loitering" in {event.event_type for event in later}


def test_scene_analyzer_motion_gate_skips_detector() -> None:
    class ExplodingDetector:
        def detect(self, frame):
            raise AssertionError("detector chaqirilmasligi kerak")

    analyzer = SceneAnalyzer("cam", ExplodingDetector(), SceneSettings())
    analyzer.motion.has_motion = lambda _frame: False
    assert analyzer.process(np.zeros((10, 10, 3), dtype=np.uint8), now=1) == []


# ── Davomat: yuz kadri produseri ─────────────────────────────────────────
#
# Qurilma yuzni tanimaydi — faqat yaqin kelgan odamdan `face_captured`
# chiqaradi.  Moslash cloudda (cloud/faces.py, tests/test_cloud_faces.py).


def face_events(events):
    return [event for event in events if event.event_type == "face_captured"]


def _attendance_analyzer(bbox):
    class Detector:
        def detect(self, frame):
            return [{"bbox": list(bbox), "score": 0.9}]

    analyzer = SceneAnalyzer(
        "cam-1", Detector(), SceneSettings(event_debounce_sec=1), attendance=True
    )
    analyzer.motion.has_motion = lambda _frame: True
    return analyzer


def test_attendance_camera_emits_a_face_capture() -> None:
    analyzer = _attendance_analyzer([20.0, 10.0, 80.0, 90.0])  # bo'yi 80% — yaqin
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    events = face_events(analyzer.analyze(frame, now=10))

    assert len(events) == 1
    assert events[0].camera_id == "cam-1"
    assert events[0].metadata["bbox"] == [20.0, 10.0, 80.0, 90.0]


def test_ordinary_cameras_never_emit_face_captures() -> None:
    class Detector:
        def detect(self, frame):
            return [{"bbox": [20.0, 10.0, 80.0, 90.0], "score": 0.9}]

    analyzer = SceneAnalyzer("cam-1", Detector(), SceneSettings(event_debounce_sec=1))
    analyzer.motion.has_motion = lambda _frame: True

    events = face_events(analyzer.analyze(np.zeros((100, 100, 3), dtype=np.uint8), now=10))

    assert events == []


def test_far_away_person_is_skipped() -> None:
    """Kichik ramka = mayda yuz — cloud bekorga ishlamasin."""
    analyzer = _attendance_analyzer([20.0, 40.0, 40.0, 60.0])  # bo'yi 20% < 28%

    events = face_events(analyzer.analyze(np.zeros((100, 100, 3), dtype=np.uint8), now=10))

    assert events == []


def test_one_track_sends_at_most_two_captures_with_a_pause() -> None:
    """Eshik oldida turgan odam oqimni to'ldirmasin: 2 ta kadr, orasi 60 s."""
    analyzer = _attendance_analyzer([20.0, 10.0, 80.0, 90.0])
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    assert len(face_events(analyzer.analyze(frame, now=10))) == 1
    assert face_events(analyzer.analyze(frame, now=30)) == [], "60 s o'tmadi"
    assert len(face_events(analyzer.analyze(frame, now=75))) == 1
    assert face_events(analyzer.analyze(frame, now=200)) == [], "limit 2 ta"


# ── Yolg'on aniqlashdan himoya ───────────────────────────────────────────
#
# Ikkalasi ham jonli do'kon ma'lumotidan chiqqan (2026-08-21, Do'kon 5070).


class TinyBlobDetector:
    """Jonli do'kondagi haqiqiy yolg'on aniqlash: 6x12 piksel, qimirlamaydi."""

    def detect(self, frame):
        return [{"bbox": [150.7, 14.7, 156.9, 26.8], "score": 0.9}]


class StaticPersonDetector:
    """Odam o'lchamida, lekin bir joyda qotib turgan (maneken, plakat)."""

    def detect(self, frame):
        return [{"bbox": [20.0, 20.0, 80.0, 200.0], "score": 0.9}]


def test_kichkina_dog_odam_deb_sanalmaydi() -> None:
    """6x12 pikselli dog' kuzatuvchiga UMUMAN tushmasin.

    Jonli do'konda aynan shunday ramka `track=16604` bo'lib abadiy
    kuzatilgan va har sovish oralig'ida "uzoq turish" bergan: bir
    kechada 48 ta yolg'on hodisa, do'kon yopiq bo'lsa ham.

    Filtr kuzatuvchidan OLDIN turishi shart — aks holda track ochiladi
    va navbat, bandlik, xarita hisobi ham buziladi.
    """
    settings = SceneSettings.model_validate({"enabled": True, "loitering_sec": 5})
    analyzer = SceneAnalyzer("cam-1", TinyBlobDetector(), settings)
    analyzer.motion.has_motion = lambda _frame: True
    frame = np.zeros((320, 544, 3), dtype=np.uint8)  # haqiqiy model o'lchami

    for step in range(6):
        events = analyzer.process(frame, now=10 + step * 5)

    assert events == [], f"kichkina dog'dan hodisa chiqdi: {events}"
    assert analyzer.tracker.active == 0, "kichkina dog' kuzatuvga tushmasligi kerak"


def test_qimirlamaydigan_obyekt_uzoq_turish_bermaydi() -> None:
    """Odam o'lchamidagi, lekin qotib turgan obyekt loitering bermasin.

    `MotionTracker.is_static()` allaqachon yozilgan va sinalgan edi —
    izohida "maneken, plakat" deb yozilgan.  Lekin u hech qayerda
    chaqirilmagan, ya'ni himoya amalda yo'q edi.

    Jonli do'konda `track=3920` bir joyda 6354 soniya "turgan".
    """
    settings = SceneSettings.model_validate(
        {"enabled": True, "loitering_sec": 15, "event_debounce_sec": 1}
    )
    analyzer = SceneAnalyzer("cam-1", StaticPersonDetector(), settings)
    analyzer.motion.has_motion = lambda _frame: True
    frame = np.zeros((320, 544, 3), dtype=np.uint8)

    # `is_static` kamida 40 ta MOSLIKNI talab qiladi (`min_hits=40`), va
    # kuzatuvchi har kadrda emas, taxminan yarmida moslik hisoblaydi —
    # ya'ni ~100 kadr kerak.  10 kadr/sekundda bu 10 soniya, production
    # dagi 300 soniyalik chegaradan ancha oldin.  Shu sabab bu yerda
    # chegara 15 soniya olindi: himoya undan oldin ishga tushishi shart.
    loitering = []
    for step in range(200):
        for event in analyzer.process(frame, now=100 + step * 0.1):
            if event.event_type == "loitering":
                loitering.append(event)

    assert analyzer.tracker.active == 1, "odam o'lchamidagi ramka kuzatilishi kerak"
    assert analyzer.tracker.is_static(1), "60 kadr qimirlamagan — statik deb tanilsin"
    assert loitering == [], f"qimirlamaydigan obyekt uzoq turish berdi: {len(loitering)} ta"


def test_camera_hour_ceiling_survives_track_churn() -> None:
    """Track almashuvi yuz kadri byudjetini noldan boshlab yubormasin.

    2026-08-26 jonli nosozligi: `FACE_EMITS_PER_TRACK` faqat `track_id` ga
    bog'langan edi.  Tracker odamni yo'qotib qayta topganda YANGI track
    tug'ilardi va byudjet qaytadan ochilardi — atigi 9 ta tashrifchidan
    45 daqiqada 399 ta `face_captured` chiqdi, cloud'dagi kunlik byudjet
    tugadi va do'konning HAMMA hodisasi rasmsiz qoldi.

    Bu yerda eng yomon holat takrorlanadi: har kadrda ramka uzoqqa
    sakraydi, ya'ni IoU hech qachon mos kelmaydi va har safar yangi track.
    """

    analyzer = _attendance_analyzer([20.0, 10.0, 80.0, 90.0])
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    emitted = 0
    for step in range(200):
        # Tracker odamni yo'qotdi — keyingi kadrda u YANGI track bo'ladi.
        # Aynan shu jonli do'konda 200 marta takrorlangan.
        analyzer.tracker._tracks.clear()
        emitted += len(face_events(analyzer.analyze(frame, now=10 + step)))

    assert emitted == scene.FACE_EMITS_PER_HOUR, (
        f"soatlik shift ushlab qolishi kerak edi, {emitted} ta chiqdi"
    )
    assert analyzer.face_emits_suppressed > 0, "to'xtatilganlar sanalsin"


def test_hour_ceiling_reopens_in_the_next_window() -> None:
    """Shift — sirpanuvchi oyna, abadiy qulf emas."""
    analyzer = _attendance_analyzer([20.0, 10.0, 80.0, 90.0])
    frame = np.zeros((100, 100, 3), dtype=np.uint8)

    # Oynani sun'iy to'ldiramiz: soat oldin yuborilgan kadrlar.
    analyzer._face_emit_times = [1000.0] * scene.FACE_EMITS_PER_HOUR

    assert face_events(analyzer.analyze(frame, now=1500.0)) == [], "oyna hali to'la"
    # Bir soatdan keyin eski yozuvlar oynadan chiqadi.
    assert len(face_events(analyzer.analyze(frame, now=1000.0 + scene.FACE_HOUR_WINDOW_SEC + 1))) == 1


def test_hour_ceiling_does_not_stop_heatmap_and_zones() -> None:
    """Yuz kadri to'xtaganda issiqlik xaritasi va zona ishlashda davom etsin.

    Shift `continue` bilan qilinsa kadrning qolgan tahlili — issiqlik
    xaritasi, zona, demografiya — jimgina o'chib qolardi.
    """
    analyzer = _attendance_analyzer([20.0, 10.0, 80.0, 90.0])
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    analyzer._face_emit_times = [1000.0] * scene.FACE_EMITS_PER_HOUR

    events = analyzer.analyze(frame, now=1500.0)

    assert face_events(events) == [], "yuz kadri to'xtagan bo'lsin"
    _cells, _frames, points = analyzer.heatmap.drain()
    assert points > 0, "issiqlik xaritasi ishlashda davom etsin"
