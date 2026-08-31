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


# ── Mijoz portreti va tarif qulfi ────────────────────────────────────


def test_a_locked_section_shows_an_offer_not_an_error() -> None:
    """Boshlang'ich tarifda karta YO'QOLMAYDI.

    Yo'q bo'lgan karta «buzilibdi» degan taassurot beradi, qulf esa
    «ko'tarish mumkin» degani — bu tarif ko'tarishning eng tabiiy
    joyi.
    """
    demo = read("Demography.tsx")

    assert 'hasFeature(dashboard, "demografiya")' in demo
    assert "PlanLock" in demo
    assert 'onNavigate("billing")' in demo


def test_a_missing_feature_list_never_locks_a_paying_customer() -> None:
    """Ro'yxat kelmagan bo'lsa bo'lim OCHIQ.

    Teskarisi yomonroq: sekin internetda to'lagan mijoz o'z kartasini
    bir zumga «tarifda yo'q» holida ko'rardi.
    """
    assert "!Array.isArray(list)" in read("api.ts")


def test_the_plan_lock_reads_the_same_snapshot_as_the_rest_of_the_panel() -> None:
    """Alohida so'rov bo'lsa ikki javob turli vaqtda kelib, karta bir
    zumga qulfsiz, keyin qulfli bo'lib chaqnab ketardi."""
    assert "panel_features" in read("types.ts")
    assert "/api/v1/owner/health" not in read("Demography.tsx")


def test_the_age_bands_keep_a_fixed_order() -> None:
    """Songa qarab saralansa ustunlar har kuni joyini almashtirardi
    va o'q o'z ma'nosini yo'qotardi."""
    demo = read("Demography.tsx")

    assert '["<18", "18-30", "31-45", "46-60", "60+"]' in demo


def test_the_youngest_band_is_explained_in_words() -> None:
    """«<18» do'kon egasiga hech narsa aytmaydi.

    0-12 va 13-17 ga ATAYLAB bo'linmagan: model yoshni ~7 yil xato
    bilan baholaydi, ya'ni bunday bo'linish aniqdek ko'rinib,
    ishonchsiz bo'lardi.
    """
    demo = read("Demography.tsx")

    assert "Bolalar va o‘smirlar" in demo
    assert '"0-12"' not in demo


def test_the_card_promises_anonymity_where_the_owner_reads_it() -> None:
    """Do'kon egasi mijozga tushuntira olishi kerak.

    Va'da faqat maxfiylik sahifasida turgan bo'lsa, u savol
    berilganda uni topa olmasdi.
    """
    demo = read("Demography.tsx")

    assert "Rasm saqlanmaydi" in demo
    assert "Xodimlar hisobga kirmaydi" in demo


def test_a_locked_heatmap_looks_like_an_offer_not_a_breakage() -> None:
    """Bungacha Boshlang'ich egasi serverning 403 matnini «Xarita
    hozir ochilmadi» ko'rinishida olardi — ya'ni nosozlikdek.

    Ekran `owner.tsx` dan `Heatmap.tsx` ga ko'chdi (soat rejimi bilan u
    o'sha faylning eng zich qismiga aylanardi); kafolat o'zgarmadi.
    """
    heatmap = read("Heatmap.tsx")

    assert 'hasFeature(dashboard, "xarita")' in heatmap
    assert "Issiqlik xaritasi Biznes tarifida" in heatmap


def test_the_owner_can_switch_between_day_week_month_and_year() -> None:
    """Xom hodisalar tarif muddatida o'chiriladi — ya'ni o'tgan oy va
    yil FAQAT kunlik yig'indi jadvalidan kelishi mumkin."""
    demo = read("Demography.tsx")

    assert "/api/v1/owner/demography?period=" in demo
    for period in ("week", "month", "year"):
        assert f'id: "{period}"' in demo


def test_today_comes_from_the_live_report_not_the_rollup() -> None:
    """Bugun hali tugamagan.  Yig'indidan olinsa panel kun davomida
    eskirgan raqamni ko'rsatardi va hisobot bilan farq qilardi."""
    demo = read("Demography.tsx")

    assert 'period === "today" ? dashboard.today.demografiya' in demo
