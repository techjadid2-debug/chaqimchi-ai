import { useCallback, useEffect, useState } from "react";
import { api, mediaObjectUrl } from "./api";
import { Card, EmptyState, ErrorStrip, PasswordInput, Pill, Skeleton, useConfirm, useToast } from "./components";
import { t } from "./i18n";
import { Icon } from "./icons";

/* Kameralarni OBYEKTDA sozlash — usta ishining eng uzun qadami.
 *
 * Nega alohida fayl: ega paneli kamerani tarmoq SKANERI bilan topadi
 * (`SetupCameras.tsx` — qidiruv do'kon kompyuterida bajariladi), usta
 * esa NVR oldida turadi va manzilni o'zi yig'adi.  Ikki oqim bir-biriga
 * o'xshamaydi: skaner qurilma tirik bo'lganda ishlaydi, usta esa aynan
 * qurilma hali ulanmagan paytda kelib, kamerani BIRINCHI marta kiritadi.
 */

type CameraRow = {
  camera_id: string;
  label?: string;
  role?: string;
  enabled?: boolean;
  probe_status?: string;
  codec?: string;
  width?: number | null;
  height?: number | null;
  has_preview?: boolean;
  preview_requested?: boolean;
  /* Yuz tanish yaroqliligi — QAROR serverda bir marta chiqadi
     (`enes/camera_roles.py: face_id_state`).  Panel chegarani QAYTA
     HISOBLAMAYDI: ikki manba bir-biridan ajralib ketishi bu loyihada
     allaqachon bir marta qimmatga tushgan (`FACE_MIN_BBOX_RATIO`). */
  face_id_state?: "unknown" | "ok" | "edge" | "low";
};

/* Kamera o'rinlari.  Server ID ni `camera-01..camera-04` bilan qattiq
   cheklaydi (`cloud/store.py: _camera_id_is_valid` → `enes/limits.py:
   SHOP_MAX_CAMERAS`), shuning uchun ro'yxat panelda ham qotib turadi —
   naqsh `SetupCameras.tsx` dagi bilan bir xil. */
const CAMERA_SLOTS = [1, 2, 3, 4];

/* Yorliq matn emas, katalog KALITI: modul yuklanganda til hali
   tanlanmagan (`initLang()` keyinroq chaqiriladi) — `SetupCameras.tsx:
   ROLE_CHOICES` bilan bir xil sabab. */
const ROLE_CHOICES = [
  { role: "entrance", key: "panel.setup.role.entrance" },
  { role: "checkout", key: "panel.setup.role.checkout" },
  { role: "sales", key: "panel.setup.role.sales" },
  { role: "storage", key: "panel.setup.role.storage" },
];

const BRANDS = [
  { id: "hikvision", key: "panel.installer.cameras.brand_hikvision" },
  { id: "dahua", key: "panel.installer.cameras.brand_dahua" },
  { id: "manual", key: "panel.installer.cameras.brand_manual" },
];

/** Brend shabloni bo'yicha substream manzili.
 *
 * Xuddi shu qoida qurilmada ham bor
 * (`enes/local/camera_probe.py: rtsp_url`) — mijoz o'zi sozlaganda
 * o'sha yerdan foydalanadi.  Ikki nusxa ATAYLAB: bu yerdagi hisob
 * brauzerda bajariladi va NVR paroli serverga faqat tayyor manzil
 * tarkibida (shifrlangan holda saqlanadi) boradi.
 *
 * Substream ham ataylab: 640×360 oqim oddiy ofis kompyuterida ham
 * dekodlanadi, main stream esa yo'q.
 */
function buildRtsp(form: { brand: string; host: string; port: string; user: string; password: string; channel: string }): string {
  /* «Boshqa / qo'lda» — shablon YO'Q va yig'ib bo'lmaydi.  Ilgari bu
     tarmoq tekshirilmasdi va tanlov Dahua yo'lini jimgina yasardi:
     manzil to'g'ri ko'rinardi, kamera esa hech qachon ochilmasdi. */
  if (form.brand === "manual") return "";
  const host = form.host.trim().replace(/^rtsps?:\/\//i, "").replace(/\/.*$/, "");
  const port = Number(form.port || 554);
  const channel = Number(form.channel || 1);
  if (!host || !form.user || !form.password) return "";
  if (!Number.isInteger(port) || port < 1 || port > 65535) return "";
  if (!Number.isInteger(channel) || channel < 1 || channel > 64) return "";
  const auth = `${encodeURIComponent(form.user)}:${encodeURIComponent(form.password)}@`;
  const path = form.brand === "hikvision"
    ? `/Streaming/Channels/${channel}02`
    : `/cam/realmonitor?channel=${channel}&subtype=1`;
  return `rtsp://${auth}${host}:${port}${path}`;
}

/** Kadr — Bearer token bilan olinadi.
 *
 * `<img src=…>` ishlamaydi: endpoint avtorizatsiya talab qiladi,
 * `<img>` esa sarlavha yubora olmaydi va 401 oladi (`Cameras.tsx` va
 * `GeometryEditor.tsx` dagi bilan bir xil yechim). */
function CameraFrame({ siteId, cameraId, nonce }: { siteId: string; cameraId: string; nonce: number }) {
  const [url, setUrl] = useState("");
  const [missing, setMissing] = useState(false);
  useEffect(() => {
    let current = "";
    let stopped = false;
    setMissing(false);
    void mediaObjectUrl(
      `/api/v1/installer/sites/${encodeURIComponent(siteId)}/cameras/${encodeURIComponent(cameraId)}/preview?t=${nonce}`,
      "installer",
    )
      .then(next => {
        // Komponent yopilgach kelgan javob darhol bo'shatiladi — aks
        // holda blob URL brauzer xotirasida osilib qolardi.
        if (stopped) { URL.revokeObjectURL(next); return; }
        current = next;
        setUrl(next);
      })
      .catch(() => { if (!stopped) setMissing(true); });
    return () => { stopped = true; if (current) URL.revokeObjectURL(current); };
  }, [siteId, cameraId, nonce]);
  return <div className="camera-frame">
    {url
      ? <img src={url} alt={t("panel.cameras.image_alt", { name: cameraId })} />
      : <div className="camera-empty"><Icon name="camera" size={28}/><span>{missing ? t("panel.cameras.frame_missing") : t("panel.cameras.frame_loading")}</span></div>}
  </div>;
}

/** Qurilma aytgan kamera holati — odam o'qiydigan matn.
 *
 * Kalitlar ega paneli bilan BITTA (`panel.cameras.state_*`): usta va
 * ega bitta kamera haqida bir xil so'z bilan gapirishi kerak.
 * `pending` — qurilma hali tekshirmagan; u «aloqa yo'q» EMAS. */
function probeText(status?: string): string {
  const key = `panel.cameras.state_${status || "unknown"}`;
  const text = t(key);
  return text === key ? t("panel.cameras.state_loading") : text;
}

/** Yuz tanish belgisi — FAQAT kirish kamerasida.
 *
 * Omborga «720p kerak» yozish shovqin: davomat u yerda ishlatilmaydi.
 * Matn `CameraDetail.tsx: FaceIdNote` bilan bitta kalitdan keladi, ya'ni
 * usta va ega bir xil gapni o'qiydi. */
function FaceIdBadge({ camera }: { camera: CameraRow }) {
  const state = camera.face_id_state;
  if (camera.role !== "entrance" || !state) return null;
  if (state === "unknown") return <Pill>{t("panel.cameras.face_id_unknown")}</Pill>;
  if (state === "ok") return <Pill state="online">{t("panel.cameras.face_id_ok")}</Pill>;
  return <Pill state={state === "low" ? "offline" : "grace"}>
    {t(state === "low" ? "panel.cameras.face_id_low" : "panel.cameras.face_id_edge")}
  </Pill>;
}

export function InstallerCamera({ siteId, onChanged }: { siteId: string; onChanged: () => void }) {
  /* `null` — hali yuklanmoqda, `[]` — ro'yxat bo'sh YOKI so'rov
     yiqildi.  Xatoda `null` qoldirilsa skelet abadiy aylanardi va
     yonida xato matni turardi (2026-09-11 QA). */
  const [cameras, setCameras] = useState<CameraRow[] | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");
  /* Kadrni qayta so'rashda `<img>` manzili o'zgarishi kerak — aks holda
     brauzer eski rasmni keshdan beradi va usta «kamera qaratildi, rasm
     esa o'sha» deb o'ylaydi. */
  const [nonce, setNonce] = useState(() => Date.now());
  const [template, setTemplate] = useState({ brand: "hikvision", host: "", port: "554", user: "", password: "", channel: "1" });
  const [rtsp, setRtsp] = useState("");
  const [confirm, confirmDialog] = useConfirm();
  const [toast, toastNode] = useToast();

  const load = useCallback(async () => {
    setError("");
    try {
      const result = await api<{ cameras: CameraRow[] }>(`/api/v1/installer/sites/${encodeURIComponent(siteId)}/cameras`, "installer");
      setCameras(result.cameras || []);
    } catch (reason) {
      setCameras([]);
      setError(reason instanceof Error ? reason.message : t("panel.installer.cameras.load_failed"));
    }
  }, [siteId]);

  useEffect(() => { void load(); }, [load]);

  const fillFromTemplate = () => {
    if (template.brand === "manual") { setFormError(t("panel.installer.cameras.rtsp_required")); return; }
    const built = buildRtsp(template);
    if (!built) { setFormError(t("panel.installer.cameras.build_failed")); return; }
    setFormError("");
    setRtsp(built);
  };

  const save = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const address = rtsp.trim() || buildRtsp(template);
    if (!address) { setFormError(t("panel.installer.cameras.rtsp_required")); return; }
    setSaving(true);
    setFormError("");
    try {
      await api(`/api/v1/installer/sites/${encodeURIComponent(siteId)}/cameras/${encodeURIComponent(String(data.get("camera_id") || "camera-01"))}`, "installer", {
        method: "PUT",
        body: JSON.stringify({
          label: String(data.get("label") || t("panel.common.camera")),
          rtsp_url: address,
          enabled: true,
          role: String(data.get("role") || ""),
        }),
      });
      /* Parol, manzil VA nom formada qolmaydi: usta keyingi kamerani
         kiritayotganda eski parol jimgina yopishib ketmasin, nom esa
         ikkinchi kameraga «Kirish eshigi» bo'lib ko'chib o'tmasin —
         2026-08-22 da hamma kamera aynan shunday bir xil bo'lib
         qolgan edi. */
      form.reset();
      setTemplate(current => ({ ...current, password: "" }));
      setRtsp("");
      toast(t("panel.installer.cameras.saved"));
      await load();
      onChanged();
    } catch (reason) {
      setFormError(reason instanceof Error ? reason.message : t("panel.installer.cameras.save_failed"));
    } finally {
      setSaving(false);
    }
  };

  const remove = async (camera: CameraRow) => {
    const ok = await confirm({
      title: t("panel.installer.cameras.delete_title"),
      text: t("panel.installer.cameras.delete_text", { name: camera.label || camera.camera_id }),
      danger: true,
      confirmLabel: t("panel.common.delete"),
    });
    if (!ok) return;
    try {
      await api(`/api/v1/installer/sites/${encodeURIComponent(siteId)}/cameras/${encodeURIComponent(camera.camera_id)}`, "installer", { method: "DELETE" });
      toast(t("panel.installer.cameras.deleted"));
      await load();
      onChanged();
    } catch (reason) {
      toast(reason instanceof Error ? reason.message : t("panel.installer.cameras.delete_failed"), false);
    }
  };

  const askFrame = async (camera: CameraRow) => {
    try {
      const result = await api<{ wait_sec?: number }>(`/api/v1/installer/sites/${encodeURIComponent(siteId)}/cameras/${encodeURIComponent(camera.camera_id)}/preview`, "installer", { method: "POST" });
      // Aniq vaqt aytiladi: «biroz kuting» desak usta dastur
      // ishlamayapti deb o'ylaydi va kamerani qayta terib ko'radi.
      toast(t("panel.installer.cameras.frame_asked", { sec: result.wait_sec ?? 60 }));
      setNonce(Date.now());
      await load();
    } catch (reason) {
      toast(reason instanceof Error ? reason.message : t("panel.installer.cameras.frame_failed"), false);
    }
  };

  return <>
    <Card>
      <div className="card-head">
        <div><h2>{t("panel.installer.cameras.title")}</h2><p>{t("panel.installer.cameras.subtitle")}</p></div>
        <div className="page-actions">
          <button className="btn" onClick={() => { setNonce(Date.now()); void load(); }}><Icon name="pulse"/>{t("panel.common.refresh")}</button>
        </div>
      </div>
      {error ? <div className="card-body"><ErrorStrip detail={error} onRetry={() => void load()}/></div> : null}
      {/* Plitkalar to'ri `Card` ning BEVOSITA bolasi — `live-grid` o'z
          paddingi bilan keladi (`Cameras.tsx` dagi bilan bir xil). */}
      {cameras === null
          ? <div className="card-body"><Skeleton height={120}/></div>
          : cameras.length
            ? <div className="live-grid">{cameras.map(camera => <article className="camera-tile" key={camera.camera_id}>
              {camera.has_preview ? <CameraFrame siteId={siteId} cameraId={camera.camera_id} nonce={nonce}/> : null}
              <div className="camera-meta is-stacked">
                <div className="camera-name"><span>{camera.label || camera.camera_id}</span></div>
                <small>{camera.camera_id}{camera.codec ? ` · ${camera.codec}` : ""}{camera.width && camera.height ? ` · ${camera.width}×${camera.height}` : ""}</small>
                {/* Holat XOM KOD bo'lib chiqmasin: server `online` /
                    `offline` / `pending` yuboradi va eski panel aynan
                    shu inglizcha so'zni ekranga chiqarardi. */}
                <small>{probeText(camera.probe_status)}{camera.preview_requested ? ` · ${t("panel.cameras.frame_requested")}` : ""}</small>
                <div className="shape-summary">
                  {/* Rol nomi RO'YXATDAN: serverdan kutilmagan qiymat
                      kelsa `t()` kalitning o'zini ekranga chiqarardi. */}
                  {ROLE_CHOICES.filter(choice => choice.role === camera.role).map(choice => <Pill key={choice.role}>{t(choice.key)}</Pill>)}
                  <FaceIdBadge camera={camera}/>
                </div>
                <div className="page-actions">
                  <button className="btn btn-small" onClick={() => void askFrame(camera)}><Icon name="camera"/>{t("panel.installer.cameras.ask_frame")}</button>
                  <button className="btn btn-small" onClick={() => void remove(camera)}>{t("panel.common.delete")}</button>
                </div>
              </div>
            </article>)}</div>
            : <div className="card-body"><EmptyState icon="camera" title={t("panel.installer.cameras.empty_title")} detail={t("panel.installer.cameras.empty_detail")}/></div>}
    </Card>

    <Card className="section-gap">
      <div className="card-head">
        <div><h2>{t("panel.installer.cameras.template_title")}</h2><p>{t("panel.installer.cameras.template_subtitle")}</p></div>
      </div>
      <form className="card-body" onSubmit={save}>
        <div className="form-grid">
          <label>{t("panel.installer.cameras.brand")}
            <select className="select" value={template.brand} onChange={event => setTemplate(current => ({ ...current, brand: event.target.value }))}>
              {BRANDS.map(brand => <option key={brand.id} value={brand.id}>{t(brand.key)}</option>)}
            </select>
          </label>
          <label>{t("panel.installer.cameras.host")}
            <input className="input" inputMode="decimal" placeholder="192.168.1.64" value={template.host} onChange={event => setTemplate(current => ({ ...current, host: event.target.value }))}/>
          </label>
          <label>{t("panel.installer.cameras.port")}
            <input className="input" inputMode="numeric" value={template.port} onChange={event => setTemplate(current => ({ ...current, port: event.target.value }))}/>
          </label>
          <label>{t("panel.installer.cameras.channel")}
            <input className="input" inputMode="numeric" value={template.channel} onChange={event => setTemplate(current => ({ ...current, channel: event.target.value }))}/>
          </label>
          <label>{t("panel.setup.field.username")}
            <input className="input" autoComplete="off" placeholder="enes-view" value={template.user} onChange={event => setTemplate(current => ({ ...current, user: event.target.value }))}/>
          </label>
          <label>{t("panel.setup.field.password")}
            <PasswordInput className="input" autoComplete="new-password" value={template.password} onChange={event => setTemplate(current => ({ ...current, password: event.target.value }))}/>
          </label>
        </div>
        <div className="page-actions">
          <button type="button" className="btn" onClick={fillFromTemplate}>{t("panel.installer.cameras.build")}</button>
        </div>
        <p className="metric-note">{t("panel.installer.cameras.account_note")}</p>

        <div className="form-grid">
          <label>{t("panel.setup.field.slot")}
            <select className="select" name="camera_id" defaultValue="camera-01">
              {CAMERA_SLOTS.map(index => <option key={index} value={`camera-0${index}`}>{`camera-0${index}`}</option>)}
            </select>
          </label>
          <label>{t("panel.setup.field.name")}
            {/* Bo'sh boshlanadi: «Kirish eshigi» jim standarti hamma
                kamerani kirish qilib ko'rsatib qo'yardi (2026-08-22). */}
            <input className="input" name="label" required placeholder={t("panel.setup.name_placeholder")}/>
          </label>
          <label>{t("panel.setup.field.role")}
            <select className="select" name="role" defaultValue="">
              <option value="">{t("panel.setup.role.none")}</option>
              {ROLE_CHOICES.map(choice => <option key={choice.role} value={choice.role}>{t(choice.key)}</option>)}
            </select>
          </label>
        </div>
        <label className="field-label">{t("panel.setup.field.rtsp")}
          {/* Ko'z tugmasi bilan: manzil ichida NVR paroli bor, lekin
              uni KO'RMASDAN xatoni tuzatib bo'lmaydi. */}
          <PasswordInput className="input" value={rtsp} onChange={event => setRtsp(event.target.value)} placeholder="rtsp://foydalanuvchi:parol@192.168.1.64:554/..."/>
        </label>
        {formError ? <div className="form-error" role="alert">{formError}</div> : null}
        <button className="btn btn-primary btn-wide" disabled={saving}>{saving ? t("panel.common.saving") : t("panel.common.save")}</button>
        <p className="metric-note">{t("panel.setup.applies_soon")}</p>
      </form>
    </Card>
    {confirmDialog}
    {toastNode}
  </>;
}
