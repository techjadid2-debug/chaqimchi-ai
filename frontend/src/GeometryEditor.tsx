import { useCallback, useEffect, useRef, useState } from "react";
import { api, tokenFor } from "./api";
import { Card, EmptyState, PageHeader, Pill } from "./components";
import { t } from "./i18n";
import { Icon } from "./icons";
import type { LineShape, ZoneEditorInstance, ZoneShape } from "./zone-editor";

/* Chiziq va zonalarni do'kon egasi o'zi chizadi.
 *
 * Chiziqsiz hech narsa sanalmaydi — bu sozlashning eng muhim, lekin
 * eng qo'rqinchli qadami.  Shuning uchun bo'sh kanvas ko'rsatilmaydi:
 * kamera birinchi ochilganda tayyor kirish chizig'i o'zi qo'yiladi va
 * egaga faqat uni eshik oldiga surish qoladi.
 */

//: Muharrir ish vaqtida yuklanadi va bundle'ga kirmaydi — manba
//: qurilmadagi bilan bitta bo'lib qolishi uchun (`zone-editor.d.ts`
//: izohiga qarang).  `?v=` — kesh uchun.
const EDITOR_URL = "/vendor/zone-editor.js?v=4";
let loader: Promise<void> | null = null;

function loadEditor(): Promise<void> {
  if (window.ZoneEditor) return Promise.resolve();
  loader ??= new Promise((resolve, reject) => {
    const tag = document.createElement("script");
    tag.src = EDITOR_URL;
    tag.onload = () => resolve();
    tag.onerror = () => {
      loader = null;
      reject(new Error(t("panel.geometry.editor_load_failed")));
    };
    document.head.appendChild(tag);
  });
  return loader;
}

type Camera = { camera_id: string; label?: string };
type SiteConfig = Record<string, unknown> & { zones?: ZoneShape[]; lines?: LineShape[] };

/** Kadrni yuklaydi.
 *
 * `<img src=…>` ishlamaydi: preview endpointi Bearer token talab
 * qiladi, `<img>` esa sarlavha yubora olmaydi va 401 oladi.  Shuning
 * uchun kadr `fetch` bilan olinib, blob URL sifatida beriladi —
 * `CameraImage` dagi bilan bir xil yechim.
 */
type Kind = "owner" | "admin";

/** Bir xil muharrir ikki panel uchun.  Farq faqat manzil va tokenda:
 *  admin do'konni MASOFADAN tuzatadi (2026-08-21 qarori — jonli
 *  do'konda `lines: []` bo'lib qolgan va kuniga 5 ta kirish sanalgan),
 *  ega esa o'zinikini.  Server tomonda tekshiruv va saqlash bitta. */
function paths(kind: Kind, siteId: string) {
  const site = encodeURIComponent(siteId);
  return kind === "admin"
    ? { config: `/api/v1/admin/sites/${site}/config`, preview: (id: string) => `/api/v1/admin/sites/${site}/cameras/${encodeURIComponent(id)}/preview` }
    : { config: "/api/v1/owner/config", preview: (id: string) => `/api/v1/owner/cameras/${encodeURIComponent(id)}/preview` };
}

async function loadFrame(cameraId: string, siteId: string, kind: Kind = "owner"): Promise<HTMLImageElement | null> {
  try {
    const headers: Record<string, string> = { Authorization: `Bearer ${tokenFor(kind)}` };
    if (kind === "owner") headers["X-Owner-Site-Id"] = siteId;
    const response = await fetch(`${paths(kind, siteId).preview(cameraId)}?t=${Date.now()}`, { headers });
    if (!response.ok) return null;
    const url = URL.createObjectURL(await response.blob());
    return await new Promise(resolve => {
      const image = new Image();
      image.onload = () => resolve(image);
      image.onerror = () => { URL.revokeObjectURL(url); resolve(null); };
      image.src = url;
    });
  } catch {
    return null;
  }
}

// Yorliq matn emas, katalog KALITI: modul yuklanganda til hali
// tanlanmagan (`initLang()` keyinroq), shuning uchun `t()` faqat
// render paytida chaqiriladi.
const PRESETS: { type: "entrance" | "queue" | "shelf" | "restricted"; key: string }[] = [
  { type: "entrance", key: "panel.geometry.preset.entrance" },
  { type: "queue", key: "panel.geometry.preset.queue" },
  { type: "shelf", key: "panel.geometry.preset.shelf" },
  { type: "restricted", key: "panel.geometry.preset.restricted" },
];

export function GeometryEditor({ siteId, cameras, kind = "owner", onSaved }: { siteId: string; cameras: Camera[]; kind?: Kind; onSaved?: () => void }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const url = paths(kind, siteId);
  const siteHeader = kind === "owner" ? { siteId } : {};
  const editor = useRef<ZoneEditorInstance | null>(null);
  const [cameraId, setCameraId] = useState(() => cameras[0]?.camera_id || "");
  const [shapes, setShapes] = useState<{ zones: ZoneShape[]; lines: LineShape[] }>({ zones: [], lines: [] });
  const [config, setConfig] = useState<SiteConfig | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const sync = useCallback(() => {
    if (!editor.current) return;
    setShapes(editor.current.serialise());
    setSaved(false);
  }, []);

  // Muharrirni bir marta yaratamiz.
  useEffect(() => {
    let stopped = false;
    loadEditor()
      .then(() => {
        if (stopped || !canvas.current || !window.ZoneEditor) return;
        editor.current = new window.ZoneEditor(canvas.current, {
          askName: (title, fallback) => window.prompt(title, fallback),
          confirm: message => window.confirm(message),
          onChange: sync,
        });
        setReady(true);
      })
      .catch(reason => setError(reason instanceof Error ? reason.message : t("panel.geometry.editor_failed")));
    return () => { stopped = true; };
  }, [sync]);

  // Saqlangan konfiguratsiya.
  useEffect(() => {
    let stopped = false;
    api<{ config: SiteConfig }>(url.config, kind, siteHeader)
      .then(result => { if (!stopped) setConfig(result.config || {}); })
      .catch(reason => { if (!stopped) setError(reason instanceof Error ? reason.message : t("panel.geometry.config_failed")); });
    return () => { stopped = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteId, kind]);

  // Kamera almashganda: shakllarni yuklaymiz va kadrni tortamiz.
  useEffect(() => {
    if (!ready || !config || !cameraId || !editor.current) return;
    const instance = editor.current;
    instance.load({ zones: config.zones || [], lines: config.lines || [] }, cameraId);

    // Bu kamerada hali hech narsa yo'q bo'lsa — tayyor kirish chizig'i.
    // Bo'sh kanvas eng ko'p tashlab ketiladigan qadam edi.
    if (!instance.visibleLines().length && !instance.visibleZones().length) {
      instance.setMode("line");
      instance.addPreset("entrance", t("panel.geometry.default_line"));
    }
    setShapes(instance.serialise());

    let stopped = false;
    void loadFrame(cameraId, siteId, kind).then(image => {
      if (!stopped) instance.setImage(image);
    });
    return () => { stopped = true; };
  }, [ready, config, cameraId, siteId, kind]);

  const addPreset = (type: (typeof PRESETS)[number]["type"], label: string) => {
    if (!editor.current) return;
    editor.current.setMode(type === "entrance" ? "line" : "zone");
    editor.current.addPreset(type, label);
    sync();
  };

  const refreshFrame = async () => {
    if (!cameraId) return;
    setError("");
    try {
      await api(url.preview(cameraId), kind, { method: "POST", ...siteHeader });
      // Qurilma kadrni yuborishiga vaqt beramiz.
      window.setTimeout(() => {
        void loadFrame(cameraId, siteId, kind).then(image => {
          if (image) editor.current?.setImage(image);
        });
      }, 2500);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("panel.geometry.frame_request_failed"));
    }
  };

  const save = async () => {
    if (!editor.current || !config) return;
    setSaving(true);
    setError("");
    const current = editor.current.serialise();
    try {
      // `...config` SHART: usiz ish vaqti, odam chegarasi va davomat
      // sozlamalari standart qiymatga qaytardi — validator to'liq
      // hujjatni kutadi.
      await api(url.config, kind, {
        method: "PUT",
        ...siteHeader,
        body: JSON.stringify({ ...config, zones: current.zones, lines: current.lines }),
      });
      setConfig({ ...config, zones: current.zones, lines: current.lines });
      setSaved(true);
      onSaved?.();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("panel.geometry.save_failed"));
    } finally {
      setSaving(false);
    }
  };

  if (!cameras.length) {
    return <>
      <PageHeader title={t("panel.geometry.title")} subtitle={t("panel.geometry.no_camera.subtitle")} />
      <Card>
        <EmptyState
          icon="camera"
          title={t("panel.geometry.no_camera.title")}
          detail={t("panel.geometry.no_camera.detail")}
        />
      </Card>
    </>;
  }

  const total = shapes.lines.length + shapes.zones.length;

  return <>
    <PageHeader
      title={t("panel.geometry.title")}
      subtitle={t("panel.geometry.subtitle")}
      actions={
        <select className="select" value={cameraId} onChange={event => setCameraId(event.target.value)} aria-label={t("panel.common.camera")}>
          {cameras.map(camera => (
            <option key={camera.camera_id} value={camera.camera_id}>
              {camera.label || camera.camera_id}
            </option>
          ))}
        </select>
      }
    />

    <Card>
      <div className="card-head">
        <div>
          <h2>{t("panel.geometry.draw.title")}</h2>
          <p>{t("panel.geometry.draw.subtitle")}</p>
        </div>
        <div className="page-actions">
          <button className="btn" onClick={() => void refreshFrame()}><Icon name="camera" />{t("panel.geometry.refresh_frame")}</button>
        </div>
      </div>
      <div className="card-body">
        {error ? <div className="form-error" role="alert">{error}</div> : null}
        <div className="page-actions preset-names">
          {PRESETS.map(preset => (
            <button key={preset.type} className="btn" onClick={() => addPreset(preset.type, t(preset.key))}>
              {t(preset.key)}
            </button>
          ))}
        </div>
        <canvas ref={canvas} className="geometry-canvas" width={960} height={540} />
        <p className="metric-note">
          {t("panel.geometry.draw.hint")}
        </p>

        <div className="shape-summary">
          {shapes.lines.map(line => (
            <Pill key={`line-${line.name}`} state="active">{line.name || t("panel.geometry.line")}</Pill>
          ))}
          {shapes.zones.map(zone => (
            <Pill key={`zone-${zone.name}`} state={zone.restricted ? "offline" : zone.queue ? "grace" : undefined}>
              {zone.name || t("panel.geometry.zone")}
            </Pill>
          ))}
          {!total ? <span className="metric-note">{t("panel.geometry.nothing_drawn")}</span> : null}
        </div>

        <button className="btn btn-primary btn-wide" disabled={saving || !total} onClick={() => void save()}>
          {saving ? t("panel.common.saving") : saved ? `${t("panel.common.saved")} ✓` : t("panel.geometry.save_and_start")}
        </button>
        {/* Matn kamera sehrgaridagi bilan bir xil — bitta kalit, ikki
            joyda takrorlanmaydi. */}
        <p className="metric-note">
          {t("panel.setup.applies_soon")}
        </p>
      </div>
    </Card>
  </>;
}
