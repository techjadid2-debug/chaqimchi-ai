"""Panel ekranlari to'g'ri endpointlarga bog'langanmi.

Bu testlar brauzerni ishga tushirmaydi — ular manba matnini o'qiydi.
Maqsad: bulut tomonida endpoint qayta nomlanganda yoki maydon
o'zgarganda panel jimgina sinib qolmasin.

Chegara aniq: bu yerda ko'rinish emas, SHARTNOMA tekshiriladi.
"""

from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "frontend" / "src"


def read(name: str) -> str:
    path = SRC / name
    assert path.is_file(), f"{name} topilmadi"
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/v1/public/device-connect",
        "/api/v1/public/quick-trial",
        "/api/v1/owner/devices/claim",
    ],
)
def test_the_connect_screen_uses_the_real_endpoints(endpoint: str) -> None:
    assert endpoint in read("api.ts")


def test_the_connect_token_is_removed_from_the_address_bar() -> None:
    """Token tarixda, skrinshotda va `Referer` sarlavhasida qolmasin."""
    source = read("api.ts")

    assert "takeConnectToken" in source
    assert 'params.delete("connect")' in source
    assert "history.replaceState" in source


def test_the_owner_confirms_with_a_code_shown_on_both_screens() -> None:
    """Kodni solishtirish — "qo'shnining kompyuterini tasdiqlab
    yubordim" xatosining yagona to'sig'i."""
    connect = read("Connect.tsx")

    assert "verify_code" in connect
    assert "verify-code" in connect


def test_the_connect_flow_runs_before_the_login_screen() -> None:
    """Dastur o'rnatilgach brauzer aynan shu havolani ochadi va odam
    hali hisobga ega bo'lmasligi mumkin."""
    owner = read("owner.tsx")

    connect_at = owner.index("<Connect")
    login_at = owner.index("<LoginScreen")
    assert connect_at < login_at


def test_the_camera_wizard_drives_the_device_from_the_cloud() -> None:
    setup = read("SetupCameras.tsx")
    api = read("api.ts")

    assert "/api/v1/owner/scan" in api
    assert "startScan" in setup and "pollScan" in setup
    # Sinov kadri — egasi uchun "ishladi" degan yagona isbot.
    assert "/frame" in setup


def test_the_geometry_editor_is_loaded_at_runtime_not_bundled() -> None:
    """Muharrir manbasi qurilmadagi bilan BITTA bo'lib qolishi kerak.

    Windows payload `cloud/` ni ko'chirmaydi, shuning uchun bundle
    qilingan nusxa bir kun qurilmadagidan ajralib ketardi.
    """
    editor = read("GeometryEditor.tsx")

    assert "/vendor/zone-editor.js" in editor
    assert "document.createElement" in editor
    # `import type` — Vite uni o'chiradi, ya'ni bundle'ga tushmaydi.
    # Qiymat sifatida import qilinsa esa muharrir nusxasi bundle'ga
    # tortilardi.
    for line in editor.splitlines():
        if './zone-editor"' in line:
            assert line.strip().startswith("import type"), line


def test_the_owner_is_never_shown_an_empty_canvas() -> None:
    """Chiziqsiz hech narsa sanalmaydi — bu eng ko'p tashlab
    ketiladigan qadam edi, shuning uchun tayyor chiziq o'zi qo'yiladi."""
    editor = read("GeometryEditor.tsx")

    assert 'addPreset("entrance"' in editor
    assert "visibleLines().length" in editor


def test_saving_geometry_keeps_the_rest_of_the_config() -> None:
    """Usiz ish vaqti, odam chegarasi va davomat sozlamalari standart
    qiymatga qaytardi — validator to'liq hujjatni kutadi."""
    editor = read("GeometryEditor.tsx")

    assert "...config" in editor
    assert "/api/v1/owner/config" in editor


def test_the_frame_is_fetched_with_the_token_not_an_img_tag() -> None:
    """`<img src>` sarlavha yubora olmaydi va 401 oladi."""
    editor = read("GeometryEditor.tsx")

    assert "createObjectURL" in editor
    assert "Authorization" in editor


def test_the_browser_never_handles_the_nvr_password() -> None:
    """Sinash va saqlash INDEKS bilan ishlaydi.

    To'liq RTSP manzili (u parol bilan keladi) shifrlangan natijada
    qoladi va uni faqat server ocha oladi.
    """
    setup = read("SetupCameras.tsx")
    api = read("api.ts")

    assert "stream_ref" in setup
    assert "from_job" in setup
    assert "saveCameraFromScan" in api
    # Skaner natijasidan olingan manzil o'zgaruvchiga solinmasin.
    assert "rtsp_url: item" not in setup
    assert "item.uri" not in setup
