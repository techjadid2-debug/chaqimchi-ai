import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, formatNumber, hasFeature, mediaObjectUrl, tashkentToday } from "./api";
import { Card, EmptyState, PageHeader, PlanLock } from "./components";
import type { Dashboard } from "./types";

/* Issiqlik xaritasi.  `owner.tsx` dan alohida faylga chiqarildi: soat
 * rejimi (slayder, ijro, kesh) bilan u o'sha faylning eng zich qismiga
 * aylanardi.  Naqsh mavjud — `Demography.tsx`, `VisionAgent.tsx`.
 */

type DayAnswer = { grid: number[][]; rows: number; cols: number; points?: number };
type HourBucket = { hour: number; grid: number[][]; points: number; frames: number };
type HoursAnswer = { rows: number; cols: number; peak: number; points: number; hours: HourBucket[] };

function heatRgb(t: number) {
  const stops = [[37,99,235],[34,211,238],[34,197,94],[250,204,21],[220,38,38]];
  const x = Math.max(0, Math.min(1, t)) * (stops.length - 1);
  const i = Math.min(stops.length - 2, Math.floor(x)); const f = x - i;
  return stops[i].map((value, index) => Math.round(value + (stops[i + 1][index] - value) * f));
}

export function HeatmapPage({ dashboard, siteId, onNavigate }: { dashboard: Dashboard; siteId: string; onNavigate: (id: string) => void }) {
  const [cameraId, setCameraId] = useState(() => dashboard.cameras[0]?.camera_id || "");
  const [mode, setMode] = useState<"days" | "hour">("days");
  const [days, setDays] = useState(7);
  const [day] = useState(() => tashkentToday());
  const [hour, setHour] = useState(12);
  const [playing, setPlaying] = useState(false);
  const [dayAnswer, setDayAnswer] = useState<DayAnswer | null>(null);
  const [hoursAnswer, setHoursAnswer] = useState<HoursAnswer | null>(null);
  const [error, setError] = useState("");
  /* Bir kunning 24 soati keshda: slayderni surish so'rov YUBORMAYDI.
     Aks holda har qadam bitta HTTP bo'lardi va animatsiya tarmoqqa
     bog'lanib qolardi. */
  const cache = useRef<Map<string, HoursAnswer>>(new Map());
  const canvas = useRef<HTMLCanvasElement>(null);
  const preview = useRef<HTMLImageElement | null>(null);
  const [previewTick, setPreviewTick] = useState(0);

  /* Effekt A — kamera KADRI.  Faqat [cameraId, siteId] ga bog'liq:
     avval u ma'lumot so'rovi bilan bitta effektda edi va `days`
     o'zgarganda kadr ham qaytadan yuklanardi.  Soat rejimida bu 24
     barobar isrof bo'lardi.
     Xatosi ataylab yutiladi: kadr hali yuborilmagan bo'lsa (404)
     xarita baribir chiziladi — qoraroq fon ustida. */
  useEffect(() => {
    if (!cameraId) return;
    let stopped = false; let url = "";
    void (async () => {
      url = await mediaObjectUrl(`/api/v1/owner/cameras/${encodeURIComponent(cameraId)}/preview`, "owner", siteId).catch(() => "");
      if (stopped || !url) { if (url) URL.revokeObjectURL(url); return; }
      const image = new Image(); image.src = url;
      try { await image.decode(); } catch { return; }
      if (stopped) return;
      preview.current = image; setPreviewTick(value => value + 1);
    })();
    return () => { stopped = true; preview.current = null; if (url) URL.revokeObjectURL(url); };
  }, [cameraId, siteId]);

  // Effekt B — ma'lumot.
  useEffect(() => {
    if (!cameraId) return;
    let stopped = false;
    const key = `${cameraId}|${day}`;
    void (async () => {
      try {
        if (mode === "hour") {
          const cached = cache.current.get(key);
          if (cached) { if (!stopped) { setHoursAnswer(cached); setError(""); } return; }
          const answer = await api<HoursAnswer>(`/api/v1/owner/heatmap?camera_id=${encodeURIComponent(cameraId)}&date=${day}&by=hour`, "owner", { siteId });
          cache.current.set(key, answer);
          if (!stopped) { setHoursAnswer(answer); setError(""); }
        } else {
          const answer = await api<DayAnswer>(`/api/v1/owner/heatmap?camera_id=${encodeURIComponent(cameraId)}&days=${days}`, "owner", { siteId });
          if (!stopped) { setDayAnswer(answer); setError(""); }
        }
      } catch (reason) {
        if (!stopped) setError(reason instanceof Error ? reason.message : "Xarita olinmadi");
      }
    })();
    return () => { stopped = true; };
  }, [cameraId, day, days, mode, siteId]);

  const bucket = mode === "hour" ? hoursAnswer?.hours?.[hour] : null;
  const grid = mode === "hour" ? bucket?.grid : dayAnswer?.grid;
  const rows = (mode === "hour" ? hoursAnswer?.rows : dayAnswer?.rows) || 0;
  const cols = (mode === "hour" ? hoursAnswer?.cols : dayAnswer?.cols) || 0;
  /* Soat rejimida cho'qqi BUTUN KUNDAN olinadi.  Har soatni o'z
     cho'qqisiga nisbatan bo'yash ertalabki uch kishini kechqurungi uch
     yuz kishi bilan bir xil qizil qilardi: animatsiya ishlardi va
     yolg'on bo'lardi. */
  const peak = mode === "hour"
    ? Math.max(1, Number(hoursAnswer?.peak) || 0)
    : Math.max(1, ...(dayAnswer?.grid || [[0]]).flat());

  // Effekt C — chizish.
  useEffect(() => {
    const target = canvas.current; const ctx = target?.getContext("2d");
    if (!target || !ctx) return;
    const width = target.width, height = target.height;
    ctx.clearRect(0, 0, width, height);
    if (preview.current) {
      ctx.drawImage(preview.current, 0, 0, width, height);
    } else {
      ctx.fillStyle = "#0f172a"; ctx.fillRect(0, 0, width, height);
      ctx.fillStyle = "#64748b"; ctx.font = "600 15px system-ui";
      ctx.fillText("Kamera kadri hali kelmagan — xarita mavhum fonda", 20, height - 20);
    }
    // Bo'sh soat BO'SH qoladi: eski to'r ekranda qolib ketsa ega uni
    // "yangilanmayapti" deb o'qiydi.
    if (!grid || !rows || !cols) return;
    ctx.save(); ctx.globalCompositeOperation = "screen";
    grid.forEach((line, rowIndex) => line.forEach((value, colIndex) => {
      const strength = Number(value || 0) / peak;
      if (strength < .1) return;
      const x = (colIndex + .5) * width / cols, y = (rowIndex + .5) * height / rows;
      const radius = Math.max(width / cols * 2.8, 28) + strength * Math.max(width / cols * 4, 64);
      const rgb = heatRgb(strength);
      const glow = ctx.createRadialGradient(x, y, 0, x, y, radius);
      glow.addColorStop(0, `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${(.42 + strength * .34).toFixed(2)})`);
      glow.addColorStop(1, "rgba(0,0,0,0)");
      ctx.fillStyle = glow; ctx.fillRect(x - radius, y - radius, radius * 2, radius * 2);
    }));
    ctx.restore();
  }, [grid, rows, cols, peak, previewTick]);

  /* Ijro faqat ma'lumot BOR soatlar orasida aylanadi: tungi bo'sh
     soatlarni kutish 24 qadamning yarmini bekorga yeyardi. */
  const active = useMemo(() => (hoursAnswer?.hours || []).filter(item => item.points > 0).map(item => item.hour), [hoursAnswer]);
  useEffect(() => {
    if (!playing || mode !== "hour" || active.length < 2) return;
    const timer = window.setInterval(() => {
      // Fon yorlig'ida ijro davom etmasin — bekorga qayta chizish.
      if (document.hidden) return;
      setHour(current => {
        const next = active.find(value => value > current);
        return next == null ? active[0] : next;
      });
    }, 900);
    return () => window.clearInterval(timer);
  }, [playing, mode, active]);
  useEffect(() => { if (mode !== "hour") setPlaying(false); }, [mode]);

  const switchMode = useCallback((next: "days" | "hour") => {
    setMode(next); setError("");
    if (next === "hour") { setDayAnswer(null); } else { setHoursAnswer(null); setPlaying(false); }
  }, []);

  const points = mode === "hour" ? bucket?.points : dayAnswer?.points;
  const subtitle = mode === "hour"
    ? (hoursAnswer == null
        ? "Ma’lumot yuklanmoqda…"
        : points
          ? `${String(hour).padStart(2, "0")}:00 · ${formatNumber(points)} ta anonim harakat nuqtasi`
          : `${String(hour).padStart(2, "0")}:00 · bu soatda harakat qayd etilmagan`)
    : (dayAnswer == null ? "Ma’lumot yuklanmoqda…" : points ? `${formatNumber(points)} ta anonim harakat nuqtasi` : "Bu davr uchun harakat ma’lumoti yo‘q");

  return <>
    <PageHeader title="Faol zonalar" subtitle="Tanlangan kameraning haqiqiy ko‘rinishidagi silliq anonim harakat oqimi." actions={<select className="select" value={cameraId} onChange={event => setCameraId(event.target.value)}>{dashboard.cameras.map(camera => <option value={camera.camera_id} key={camera.camera_id}>{camera.label || camera.camera_id}</option>)}</select>}/>
    <Card>
      <div className="card-head">
        <div><h2>Kamera ko‘rinishidagi faol zonalar</h2><p>{subtitle}</p></div>
        <div className="page-actions">
          <div className="segmented">
            <button className={mode === "days" ? "active" : ""} onClick={() => switchMode("days")}>Kun bo‘yicha</button>
            <button className={mode === "hour" ? "active" : ""} onClick={() => switchMode("hour")}>Soat bo‘yicha</button>
          </div>
          {mode === "days" ? <div className="segmented">{[1,7,30].map(value => <button key={value} className={days === value ? "active" : ""} onClick={() => setDays(value)}>{value === 1 ? "Bugun" : `${value} kun`}</button>)}</div> : null}
        </div>
      </div>
      {!hasFeature(dashboard, "xarita")
        ? <PlanLock title="Issiqlik xaritasi Biznes tarifida" detail="Mijozlarning qayerda ko‘p to‘xtashini aynan kamera burchagida ko‘rasiz." onUpgrade={() => onNavigate("billing")}/>
        : error ? <EmptyState icon="heat" title="Xarita hozir ochilmadi" detail={error}/>
        : cameraId ? <>
          {mode === "hour" ? <div className="heat-scrub">
            <button className="btn" onClick={() => setHour(value => (value + 23) % 24)} aria-label="Oldingi soat">◀</button>
            <button className="btn" disabled={active.length < 2} onClick={() => setPlaying(value => !value)}>{playing ? "⏸ To‘xtatish" : "▶ Ijro"}</button>
            <button className="btn" onClick={() => setHour(value => (value + 1) % 24)} aria-label="Keyingi soat">▶</button>
            <input type="range" min={0} max={23} value={hour} onChange={event => { setPlaying(false); setHour(Number(event.target.value)); }} aria-label="Soat"/>
            <b>{String(hour).padStart(2, "0")}:00</b>
          </div> : null}
          <div className="heatmap-wrap">
            <canvas ref={canvas} width="960" height="540" aria-label="Kamera ko‘rinishidagi faol zonalar"/>
            <div className="heat-legend"><span>past</span><i/><span>yuqori</span></div>
          </div>
          {mode === "hour" ? <p className="media-note" style={{ padding: "0 20px 16px" }}>Ranglar butun kunning eng gavjum katagiga nisbatan — soatlarni bir-biri bilan solishtirsa bo‘ladi.</p> : null}
        </> : <EmptyState icon="camera" title="Kamera ulanmagan" detail="Kamera qo‘shilgach faol zonalar shu yerda ko‘rinadi."/>}
    </Card>
  </>;
}
