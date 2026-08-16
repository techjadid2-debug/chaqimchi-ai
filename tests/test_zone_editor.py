"""Chiziq/zona chizish vositasi.

Bu tekshiruvning sababi: `scene.lines` va `scene.zones` har bir profilda
bo'sh, va ularni kiritishning yagona yo'li owner panelidagi xom JSON maydoni
edi — normallashtirilgan 0..1 koordinatalar bilan. Uni na do'kon egasi, na
o'rnatuvchi to'ldirardi, ya'ni sotiladigan uchta funksiyadan ikkitasi
(`person_count`, `queue_length`) hech qachon ishlamasdi.

Muharrir chiqishi cloud validatsiyasidan o'tishi shart — shakl `pydantic`
modeli bilan bir xil bo'lmasa saqlash 422 beradi va o'rnatuvchi sababini
bilmaydi.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from chaqimchi_ai.settings import SceneLineSettings, SceneZoneSettings

ROOT = Path(__file__).resolve().parents[1]
#: Muharrir cloud'dan tashqarida turadi: uni ham o'rnatuvchi paneli, ham
#: mijozning lokal sozlash ustasi ishlatadi va Windows paketiga `cloud/`
#: ko'chirilmaydi.
EDITOR = ROOT / "chaqimchi_ai" / "local" / "static" / "zone-editor.js"


def _node(script: str) -> dict:
    """Muharrirni Node ichida yuklab, berilgan kodni bajaradi."""
    if shutil.which("node") is None:
        pytest.skip("node topilmadi")
    harness = f"""
    const window = {{}};
    {EDITOR.read_text(encoding="utf-8")}
    const ZoneEditor = window.ZoneEditor;
    {script}
    """
    result = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_editor_file_parses() -> None:
    if shutil.which("node") is None:
        pytest.skip("node topilmadi")
    result = subprocess.run(
        ["node", "--check", str(EDITOR)], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr


def test_serialised_shapes_pass_cloud_validation() -> None:
    """Muharrir chiqishi aynan `SceneZoneSettings`/`SceneLineSettings`.

    Aks holda saqlash 422 bilan yiqilardi va o'rnatuvchi nima
    noto'g'riligini bilmasdi.
    """
    payload = _node(
        """
        const editor = Object.create(ZoneEditor.prototype);
        editor.zones = [{
          name: 'kassa', camera_id: 'camera-01',
          polygon: [[0.1234567, 0.2], [0.9, 0.2], [0.9, 0.98765], [0.1, 0.9]],
          restricted: false, queue: true, dwell_sec: 120,
        }];
        editor.lines = [{
          name: 'kirish', camera_id: 'camera-01',
          start: [0.0011, 0.5], end: [0.9999, 0.5], swap_direction: true,
        }];
        console.log(JSON.stringify(editor.serialise()));
        """
    )

    zone = SceneZoneSettings.model_validate(payload["zones"][0])
    line = SceneLineSettings.model_validate(payload["lines"][0])

    assert zone.name == "kassa" and zone.queue is True and zone.dwell_sec == 120
    assert line.swap_direction is True
    # Uch xona 640 px kadrda yarim pikseldan aniq; JSON esa ancha kichik.
    assert zone.polygon[0] == (0.123, 0.2)
    assert line.start == (0.001, 0.5)


def test_coordinates_stay_inside_the_frame() -> None:
    """Kadr chetidan tashqarida bosilsa ham 0..1 dan chiqmasin —
    `SceneZoneSettings` bunday nuqtani rad etadi."""
    payload = _node(
        """
        const editor = Object.create(ZoneEditor.prototype);
        editor.canvas = { getBoundingClientRect: () => ({left: 0, top: 0, width: 640, height: 360}) };
        console.log(JSON.stringify([
          editor._point({clientX: -50, clientY: -50}),
          editor._point({clientX: 9999, clientY: 9999}),
          editor._point({clientX: 320, clientY: 180}),
        ]));
        """
    )

    assert payload == [[0, 0], [1, 1], [0.5, 0.5]]
    SceneZoneSettings.model_validate({"name": "z", "camera_id": "camera-01", "polygon": payload})


def test_only_the_selected_cameras_shapes_are_shown() -> None:
    """Boshqa kameraning chizig'i bu kadr ustida ma'nosiz — va uni sudrab
    ko'chirish jimgina noto'g'ri kameraning sozlamasini buzardi."""
    payload = _node(
        """
        const editor = Object.create(ZoneEditor.prototype);
        editor.cameraId = 'camera-02';
        editor.zones = [
          {name: 'a', camera_id: 'camera-01', polygon: []},
          {name: 'b', camera_id: 'camera-02', polygon: []},
        ];
        editor.lines = [
          {name: 'x', camera_id: 'camera-02'},
          {name: 'y', camera_id: 'camera-03'},
        ];
        console.log(JSON.stringify({
          zones: editor.visibleZones().map(z => z.name),
          lines: editor.visibleLines().map(l => l.name),
        }));
        """
    )

    assert payload == {"zones": ["b"], "lines": ["x"]}


def test_point_in_polygon_matches_the_drawn_shape() -> None:
    """O'ng tugma bilan o'chirish shu testga tayanadi."""
    payload = _node(
        """
        const square = [[0.2,0.2],[0.8,0.2],[0.8,0.8],[0.2,0.8]];
        console.log(JSON.stringify([
          ZoneEditor.inside([0.5,0.5], square),
          ZoneEditor.inside([0.1,0.5], square),
          ZoneEditor.inside([0.5,0.9], square),
        ]));
        """
    )

    assert payload == [True, False, False]


def test_loading_an_empty_config_does_not_crash() -> None:
    """Yangi obyektda `zones`/`lines` umuman yo'q bo'ladi."""
    payload = _node(
        """
        const editor = Object.create(ZoneEditor.prototype);
        editor.draw = () => {};
        editor.load({}, 'camera-01');
        console.log(JSON.stringify(editor.serialise()));
        """
    )

    assert payload == {"zones": [], "lines": []}


def test_panels_load_the_editor_and_owner_cannot_edit_raw_json() -> None:
    """O'rnatuvchi chizadi, ega esa faqat ko'radi.

    Chiziq kadr ustida, kamera o'rnatilgan joydan turib chiziladi — bu ish
    do'kon egasiga tushmasligi kerak.
    """
    installer = (ROOT / "cloud" / "static" / "installer.html").read_text(encoding="utf-8")
    owner = (ROOT / "cloud" / "static" / "owner.html").read_text(encoding="utf-8")

    assert "zone-editor.js" in installer
    assert 'id="geoCanvas"' in installer
    assert "installer/sites/${activeSite}/config" in installer

    # Yangi panelda (2026-08-17) ega geometriyani UMUMAN ko'rmaydi: JSON
    # textarealar oddiy mijozni cho'chitardi.  Chiziq/zona faqat o'rnatuvchi
    # vositasida; ega sozlamalarni saqlaganda mavjud geometriya o'zgarmasdan
    # qaytariladi (`...currentConfig` spread).
    assert "linesJson" not in owner
    assert "zonesJson" not in owner
    assert "<textarea" not in owner
    assert "...currentConfig" in owner, "saqlashda geometriya yo'qolmasin"


def test_wizard_offers_one_click_presets_and_camera_roles() -> None:
    """Sehrgar qulayligi (2026-08-17): bir-bosim shablonlar va kamera roli.

    `addPreset()` allaqachon bor edi — tugmasi yo'q edi; `priority` server
    tomonda bor edi — UI yo'q edi.  Bu test ular qaytib yo'qolib
    qolmasligini qo'riqlaydi.
    """
    setup_html = (ROOT / "chaqimchi_ai" / "local" / "static" / "setup.html").read_text(
        encoding="utf-8"
    )
    setup_js = (ROOT / "chaqimchi_ai" / "local" / "static" / "setup.js").read_text(
        encoding="utf-8"
    )

    for button in ("presetLineBtn", "presetQueueBtn", "presetRestrictedBtn"):
        assert button in setup_html, f"shablon tugmasi yo'q: {button}"
    assert "addPreset" in setup_js, "tugmalar addPreset'ga ulanmagan"
    assert 'id="cameraRole"' in setup_html, "kamera roli tanlovi yo'q"
    assert "ROLE_PRESETS" in setup_js
    assert '"security"' in setup_js and '"background"' in setup_js, (
        "rol -> priority mapping saqlansin"
    )
    assert 'id="hoursHint"' in setup_html, "ish soatlari bo'sh qolsa ogohlantirish joyi"
