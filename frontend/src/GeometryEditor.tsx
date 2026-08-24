import { useCallback, useEffect, useRef, useState } from "react";
import { api, tokenFor } from "./api";
import { Card, EmptyState, PageHeader, Pill } from "./components";
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
const EDITOR_URL = "/vendor/zone-editor.js?v=3";
let loader: Promise<void> | null = null;

function loadEditor(): Promise<void> {
  if (window.ZoneEditor) return Promise.resolve();
  loader ??= new Promise((resolve, reject) => {
    const tag = document.createElement("script");
    tag.src = EDITOR_URL;
    tag.onload = () => resolve();
    tag.onerror = () => {
      loader = null;
      reject(new Error("Chizish muharriri yuklanmadi"));
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
async function loadFrame(cameraId: string, siteId: string): Promise<HTMLImageElement | null> {
  try {
    const response = await fetch(
      `/api/v1/owner/cameras/${encodeURIComponent(cameraId)}/preview?t=${Date.now()}`,
      { headers: { Authorization: `Bearer ${tokenFor("owner")}`, "X-Owner-Site-Id": siteId } },
    );
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

const PRESETS: { type: "entrance" | "queue" | "shelf" | "restricted"; label: string }[] = [
  { type: "entrance", label: "Kirish eshigi" },
  { type: "queue", label: "Kassa navbati" },
  { type: "shelf", label: "Javon" },
  { type: "restricted", label: "Taqiqlangan zona" },
];

export function GeometryEditor({ siteId, cameras }: { siteId: string; cameras: Camera[] }) {
  const canvas = useRef<HTMLCanvasElement>(null);
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
      .catch(reason => setError(reason instanceof Error ? reason.message : "Muharrir yuklanmadi"));
    return () => { stopped = true; };
  }, [sync]);

  // Saqlangan konfiguratsiya.
  useEffect(() => {
    let stopped = false;
    api<{ config: SiteConfig }>("/api/v1/owner/config", "owner", { siteId })
      .then(result => { if (!stopped) setConfig(result.config || {}); })
      .catch(reason => { if (!stopped) setError(reason instanceof Error ? reason.message : "Sozlama olinmadi"); });
    return () => { stopped = true; };
  }, [siteId]);

  // Kamera almashganda: shakllarni yuklaymiz va kadrni tortamiz.
  useEffect(() => {
    if (!ready || !config || !cameraId || !editor.current) return;
    const instance = editor.current;
    instance.load({ zones: config.zones || [], lines: config.lines || [] }, cameraId);

    // Bu kamerada hali hech narsa yo'q bo'lsa — tayyor kirish chizig'i.
    // Bo'sh kanvas eng ko'p tashlab ketiladigan qadam edi.
    if (!instance.visibleLines().length && !instance.visibleZones().length) {
      instance.setMode("line");
      instance.addPreset("entrance", "Kirish");
    }
    setShapes(instance.serialise());

    let stopped = false;
    void loadFrame(cameraId, siteId).then(image => {
      if (!stopped) instance.setImage(image);
    });
    return () => { stopped = true; };
  }, [ready, config, cameraId, siteId]);

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
      await api(`/api/v1/owner/cameras/${encodeURIComponent(cameraId)}/preview`, "owner", {
        method: "POST",
        siteId,
      });
      // Qurilma kadrni yuborishiga vaqt beramiz.
      window.setTimeout(() => {
        void loadFrame(cameraId, siteId).then(image => {
          if (image) editor.current?.setImage(image);
        });
      }, 2500);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Kadr so‘ralmadi");
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
      await api("/api/v1/owner/config", "owner", {
        method: "PUT",
        siteId,
        body: JSON.stringify({ ...config, zones: current.zones, lines: current.lines }),
      });
      setConfig({ ...config, zones: current.zones, lines: current.lines });
      setSaved(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Saqlanmadi");
    } finally {
      setSaving(false);
    }
  };

  if (!cameras.length) {
    return <>
      <PageHeader title="Chiziq va zonalar" subtitle="Avval kamerani ulang." />
      <Card>
        <EmptyState
          icon="camera"
          title="Kamera ulanmagan"
          detail="«Kamerani ulash» bo‘limidan birinchi kamerani qo‘shing, so‘ng shu yerda kirish chizig‘ini chizasiz."
        />
      </Card>
    </>;
  }

  const total = shapes.lines.length + shapes.zones.length;

  return <>
    <PageHeader
      title="Chiziq va zonalar"
      subtitle="Chiziqsiz hech narsa sanalmaydi — kirish eshigidan boshlang."
      actions={
        <select className="select" value={cameraId} onChange={event => setCameraId(event.target.value)} aria-label="Kamera">
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
          <h2>Kadr ustida chizing</h2>
          <p>Yashil chiziqni eshik oldiga surib qo‘ying — nuqtalarni sudrab ko‘chirasiz.</p>
        </div>
        <div className="page-actions">
          <button className="btn" onClick={() => void refreshFrame()}><Icon name="camera" />Kadrni yangilash</button>
        </div>
      </div>
      <div className="card-body">
        {error ? <div className="form-error" role="alert">{error}</div> : null}
        <div className="page-actions preset-names">
          {PRESETS.map(preset => (
            <button key={preset.type} className="btn" onClick={() => addPreset(preset.type, preset.label)}>
              {preset.label}
            </button>
          ))}
        </div>
        <canvas ref={canvas} className="geometry-canvas" width={960} height={540} />
        <p className="metric-note">
          Bir marta bosib nuqta qo‘yasiz, ikki marta bosib yakunlaysiz. O‘ng tugma — o‘chiradi.
        </p>

        <div className="shape-summary">
          {shapes.lines.map(line => (
            <Pill key={`line-${line.name}`} state="active">{line.name || "Chiziq"}</Pill>
          ))}
          {shapes.zones.map(zone => (
            <Pill key={`zone-${zone.name}`} state={zone.restricted ? "offline" : zone.queue ? "grace" : undefined}>
              {zone.name || "Zona"}
            </Pill>
          ))}
          {!total ? <span className="metric-note">Hali hech narsa chizilmagan</span> : null}
        </div>

        <button className="btn btn-primary btn-wide" disabled={saving || !total} onClick={() => void save()}>
          {saving ? "Saqlanmoqda…" : saved ? "Saqlandi ✓" : "Saqlash va ishga tushirish"}
        </button>
        <p className="metric-note">
          Saqlagach do‘kon kompyuteri 20 soniya ichida yangi sozlamani oladi.
        </p>
      </div>
    </Card>
  </>;
}
