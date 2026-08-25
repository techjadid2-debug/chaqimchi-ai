import { StrictMode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { api, clearToken, formatDateShort, formatDateUz, formatMoney, formatNumber, hasFeature, login, loginWithLinkKey, loginWithTelegram, mediaObjectUrl, relativeMinutes, takeConnectToken, telegramBotUrl, tokenFor } from "./api";
import { Demography } from "./Demography";
import { AppShell, Card, EmptyState, LoginScreen, MetricCard, PageHeader, Pill, PlanLock, Skeleton, StatusDot, type NavItem } from "./components";
import { LineChart, type Point } from "./charts";
import { Connect } from "./Connect";
import { GeometryEditor } from "./GeometryEditor";
import { OwnerHome } from "./OwnerHome";
import { SetupCameras } from "./SetupCameras";
import { VisionAgent } from "./VisionAgent";
import { EventEvidence } from "./EventEvidence";
import { usePanelRoute } from "./router";
import type { Camera, Dashboard, Employee, Invoice, Site, TelegramMember, TrendPoint } from "./types";
import { Icon, Logo } from "./icons";
import "./styles.css";

const NAV: NavItem[] = [
  { id: "home", label: "Bosh sahifa", icon: "home" },
  { id: "setup", label: "Kamerani ulash", icon: "search" },
  { id: "zones", label: "Chiziq va zonalar", icon: "shapes" },
  { id: "cameras", label: "Kameralar", icon: "camera" },
  { id: "traffic", label: "Mijozlar oqimi", icon: "chart" },
  { id: "employees", label: "Xodimlar", icon: "users" },
  { id: "heatmap", label: "Issiqlik xaritasi", icon: "heat" },
  { id: "branches", label: "Filiallar", icon: "branch" },
  { id: "reports", label: "Hisobotlar", icon: "report" },
  { id: "alerts", label: "Hodisalar", icon: "shield" },
  { id: "agent", label: "AI yordamchi", icon: "pulse" },
  { id: "billing", label: "Tarif va to‘lov", icon: "card" },
  { id: "telegram", label: "Telegram", icon: "telegram" },
  { id: "settings", label: "Sozlamalar", icon: "settings" },
];

/* "Hodisalar" endi menyuda ham bor: rasm/klip galereyasi faqat
   qo'ng'iroq belgisi orqali topiladigan yashirin sahifa bo'lib qolgan
   edi — mijoz uni umuman ko'rmasdi. */
const ROUTE_IDS = NAV.map(item => item.id);
const MOBILE_NAV = ["home", "cameras", "traffic", "employees"];

function value(report: Record<string, unknown>, ...keys: string[]) {
  for (const key of keys) {
    const found = key.split(".").reduce<unknown>((current, part) => current && typeof current === "object" ? (current as Record<string,unknown>)[part] : undefined, report);
    if (typeof found === "number") return found;
  }
  return null;
}

function textValue(report:Record<string,unknown>, key:string) {
  const found=key.split(".").reduce<unknown>((current,part)=>current&&typeof current==="object"?(current as Record<string,unknown>)[part]:undefined,report);
  if (found && typeof found === "object" && typeof (found as Record<string,unknown>).hour === "number") return `${String((found as Record<string,number>).hour).padStart(2,"0")}:00`;
  return typeof found==="string"?found:typeof found==="number"?`${String(found).padStart(2,"0")}:00`:"—";
}

function useAdaptiveDashboard(siteId: string, authenticated: boolean) {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const failures = useRef(0);

  const refresh = useCallback(async () => {
    // Sayt tanlanmagan (masalan, egaga hali filial biriktirilmagan) —
    // yuklanish tugagan hisoblanadi.  Avval bu yerda shunchaki `return`
    // edi va `loading` abadiy `true` qolib, ekranda cheksiz skelet
    // ko'rinardi.
    if (!authenticated || !siteId) { setLoading(false); return; }
    try {
      const next = await api<Dashboard>("/api/v1/owner/dashboard", "owner", { siteId });
      setData(next);
      setError("");
      failures.current = 0;
    } catch (reason) {
      failures.current += 1;
      setError(reason instanceof Error ? reason.message : "Ma’lumot olinmadi");
    } finally {
      setLoading(false);
    }
  }, [authenticated, siteId]);

  useEffect(() => {
    let timeout = 0;
    let stopped = false;
    const tick = async () => {
      await refresh();
      if (stopped) return;
      const delay = document.hidden ? 60_000 : failures.current > 1 ? 60_000 : failures.current ? 30_000 : 15_000;
      timeout = window.setTimeout(tick, delay);
    };
    void tick();
    const wake = () => { if (!document.hidden) void refresh(); };
    document.addEventListener("visibilitychange", wake);
    return () => { stopped = true; window.clearTimeout(timeout); document.removeEventListener("visibilitychange", wake); };
  }, [refresh]);
  return { data, error, loading, refresh };
}

function TrendChart({ points }: { points: TrendPoint[] }) {
  const normalized = (points || []).slice(-14).map(point => ({ label: String(point.date || point.day || "").slice(5), value: Number(point.entries ?? point.entered ?? point.count ?? 0) }));
  if (!normalized.length) return <EmptyState icon="chart" title="Oqim ma’lumoti hali yo‘q" detail="Kamera odam kirishini qayd qilgach bu yerda kunlar bo‘yicha grafik paydo bo‘ladi." />;
  const maximum = Math.max(...normalized.map(item => item.value), 1);
  const coords = normalized.map((item, index) => `${10 + (index * 580) / Math.max(1, normalized.length - 1)},${190 - (item.value / maximum) * 155}`).join(" ");
  return <div className="chart-wrap">
    <svg className="chart" viewBox="0 0 600 210" preserveAspectRatio="none" role="img" aria-label="Kunlik mijozlar oqimi grafigi">
      <defs><linearGradient id="areaBlue" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#4285f4" stopOpacity=".23"/><stop offset="1" stopColor="#4285f4" stopOpacity="0"/></linearGradient></defs>
      {[35,75,115,155,195].map(y => <line key={y} className="chart-grid" x1="0" y1={y} x2="600" y2={y}/>) }
      <polygon className="chart-area" points={`10,195 ${coords} 590,195`} />
      <polyline className="chart-line" points={coords}/>
    </svg>
    <div className="chart-labels">{normalized.map((item, index) => <span key={`${item.label}-${index}`}>{item.label || index + 1}</span>)}</div>
  </div>;
}

function CameraImage({ camera, siteId, overlay, live }: { camera: Camera; siteId: string; overlay: boolean; live: boolean }) {
  const [src, setSrc] = useState("");
  const [error, setError] = useState(false);
  const [stamp, setStamp] = useState("");
  useEffect(() => {
    let timer = 0;
    let stopped = false;
    let current = "";
    const load = async () => {
      const path = live ? `/api/v1/owner/cameras/${encodeURIComponent(camera.camera_id)}/live-frame?t=${Date.now()}` : `/api/v1/owner/cameras/${encodeURIComponent(camera.camera_id)}/preview?t=${Date.now()}`;
      try {
        const headers: Record<string,string> = { Authorization: `Bearer ${tokenFor("owner")}`, "X-Owner-Site-Id": siteId };
        const response = await fetch(path, { headers });
        if (!response.ok) throw new Error();
        const next = URL.createObjectURL(await response.blob());
        if (stopped) { URL.revokeObjectURL(next); return; }
        if (current) URL.revokeObjectURL(current);
        current = next; setSrc(next); setError(false);
        setStamp(new Date().toLocaleTimeString("uz-UZ", { hour: "2-digit", minute: "2-digit", second: "2-digit" }));
      } catch {
        // `current` — shu effektning O'Z holati.  Ilgari bu yerda
        // `src` tekshirilardi: u effekt yopilmasidan oldingi qiymatni
        // eslab qolgan edi, shuning uchun birinchi muvaffaqiyatli
        // kadrdan keyin ham "Kadr kelmadi" yozuvi chiqib ketardi.
        if (!current) setError(true);
      }
      if (!stopped && live) timer = window.setTimeout(load, 2500);
    };
    void load();
    return () => { stopped = true; window.clearTimeout(timer); if (current) URL.revokeObjectURL(current); };
  }, [camera.camera_id, live, overlay, siteId]);
  return <div className="camera-frame">
    {src ? <img src={src} alt={`${camera.label || camera.camera_id} kamerasi`} /> : <div className="camera-empty"><Icon name="camera" size={28}/><span>{error ? "Kadr hozircha kelmadi" : "Kadr yuklanmoqda…"}</span></div>}
    {overlay && src ? <span className="camera-overlay-badge">AI tahlil</span> : null}
    {stamp && src ? <span className="camera-stamp">{stamp}</span> : null}
  </div>;
}

function CamerasBlock({ dashboard, siteId, expanded = false, onOpenAll }: { dashboard: Dashboard; siteId: string; expanded?: boolean; onOpenAll?: () => void }) {
  const [overlay, setOverlay] = useState(false);
  const [live, setLive] = useState(false);
  const cameras = expanded ? dashboard.cameras : dashboard.cameras.slice(0, 4);
  const stateMap = useMemo(() => new Map(dashboard.camera_states.map(item => [item.camera_id, item])), [dashboard.camera_states]);
  const toggleLive = async () => {
    const next = !live;
    setLive(next);
    if (next) await Promise.all(cameras.map(camera => api(`/api/v1/owner/cameras/${encodeURIComponent(camera.camera_id)}/live`, "owner", { method: "POST", siteId, body: JSON.stringify({ overlay }) }).catch(() => null)));
  };
  const toggleOverlay = async () => {
    const next = !overlay; setOverlay(next);
    if (live) await Promise.all(cameras.map(camera => api(`/api/v1/owner/cameras/${encodeURIComponent(camera.camera_id)}/live`, "owner", { method: "POST", siteId, body: JSON.stringify({ overlay: next }) }).catch(() => null)));
  };
  return <Card>
    <div className="card-head">
      <div><h2>Jonli kameralar</h2><p>Do‘kon holati va so‘nggi haqiqiy kadrlar</p></div>
      <div className="page-actions">
        <button className="btn" onClick={toggleOverlay}><Icon name="eye"/>{overlay ? "AI ramkani yopish" : "AI ramkani ko‘rsatish"}</button>
        <button className={`btn ${live ? "btn-primary" : ""}`} onClick={toggleLive}><Icon name="pulse"/>{live ? "Jonli" : "Jonli ko‘rish"}</button>
        {!expanded && onOpenAll ? <button className="btn" onClick={onOpenAll}>Barchasini ochish</button> : null}
      </div>
    </div>
    {cameras.length ? <div className="live-grid">{cameras.map((camera, index) => {
      const state = stateMap.get(camera.camera_id)?.state || "unknown";
      // Uch holat uch xil so'z bilan: "eskirgan" va "oflayn" bir xil
      // qizil "Aloqa yo'q" bo'lib chiqsa, egasi tuzatib bo'ladigan
      // kechikishni butunlay uzilish deb o'ylaydi.
      const live_label = state === "online" ? "Jonli" : state === "stale" ? "Kechikmoqda" : "Aloqa yo‘q";
      return <article className="camera-tile" key={camera.camera_id}>
        <CameraImage camera={camera} siteId={siteId} overlay={overlay} live={live}/>
        {/* Sarlavha kadr USTIDA: namunadagidek, va shu bilan plitka
            balandligi kamera nomi uzunligiga bog'liq bo'lmay qoladi. */}
        <span className="camera-title">{index + 1}. {camera.label || camera.camera_id}</span>
        <span className={`camera-live is-${state}`}><i/>{live_label}</span>
        <div className="camera-meta">
          <div className="camera-name"><StatusDot state={state}/><span>{camera.label || camera.camera_id}</span></div>
          <small>{stateMap.get(camera.camera_id)?.reason || "Holat olinmoqda"}</small>
        </div>
      </article>;
    })}</div> : <EmptyState icon="camera" title="Kamera ulanmagan" detail="Kamera o‘rnatuvchi tomonidan qo‘shilgach haqiqiy kadrlar shu yerda ko‘rinadi." />}
  </Card>;
}

function EmployeesPage({ siteId }: { siteId: string }) {
  const [items, setItems] = useState<Employee[] | null>(null); const [error,setError] = useState(""); const [adding,setAdding] = useState(false); const [busy,setBusy] = useState(false); const [uploading,setUploading] = useState("");
  const load = useCallback(async () => {
    try {
      const data = await api<{employees:Employee[]}>("/api/v1/owner/faces", "owner", {siteId});
      setItems(data.employees || []); setError("");
    } catch {
      // Zaxira endpoint ham yiqilsa ro'yxat BO'SH holatga tushadi va
      // sabab ko'rinadi — avval bu istisno hech qayerda ushlanmay,
      // sahifa abadiy skeletda qolardi.
      try {
        const data = await api<{employees:Employee[]}>("/api/v1/owner/employees", "owner", {siteId});
        setItems(data.employees || []); setError("");
      } catch (reason) {
        setItems([]);
        setError(reason instanceof Error ? reason.message : "Xodimlar ro‘yxati olinmadi");
      }
    }
  },[siteId]);
  useEffect(() => { void load(); }, [load]);
  const create = async (event:React.FormEvent<HTMLFormElement>) => { event.preventDefault();const form=event.currentTarget;const data=new FormData(form);setBusy(true);setError("");try{await api("/api/v1/owner/employees","owner",{method:"POST",siteId,body:JSON.stringify({name:String(data.get("name")||""),external_id:String(data.get("external_id")||"")||null,consent:data.get("consent")==="on",consent_note:"Yozma rozilik biznes egasi tomonidan tasdiqlandi"})});form.reset();setAdding(false);await load();}catch(reason){setError(reason instanceof Error?reason.message:"Xodim qo‘shilmadi");}finally{setBusy(false);}};
  const uploadFace = async (employee:Employee, file?:File) => {
    if (!file) return;
    if (!["image/jpeg","image/png"].includes(file.type)) { setError("Face ID uchun JPEG yoki PNG rasm tanlang."); return; }
    setUploading(employee.id); setError("");
    try {
      await api(`/api/v1/owner/faces/employees/${encodeURIComponent(employee.id)}/photos`,"owner",{method:"POST",siteId,headers:{"Content-Type":file.type},body:file});
      await load();
    } catch(reason) { setError(reason instanceof Error?reason.message:"Rasm yuklanmadi"); }
    finally { setUploading(""); }
  };
  return <><PageHeader title="Xodimlar" subtitle="Xodim profili va Face ID yopiq pilot holati." actions={<button className="btn btn-primary" onClick={()=>setAdding(value=>!value)}><Icon name="users"/><span>{adding?"Bekor qilish":"Xodim qo‘shish"}</span></button>}/>{adding?<Card className="employee-form"><form className="card-body" onSubmit={create}><div className="form-grid"><label>Ism va familiya<input className="input" name="name" minLength={2} required/></label><label>Ichki ID (ixtiyoriy)<input className="input" name="external_id"/></label></div><label className="consent-row"><input type="checkbox" name="consent" required/><span>Xodimning biometrik ma’lumotlarni qayta ishlash bo‘yicha yozma roziligi olindi.</span></label><button className="btn btn-primary" disabled={busy}>{busy?"Saqlanmoqda…":"Xodimni saqlash"}</button></form></Card>:null}{error?<div className="alert-strip"><Icon name="bell"/><div><strong>Amal bajarilmadi:</strong> {error}</div></div>:null}<Card><div className="card-head"><div><h2>Xodimlar ro‘yxati</h2><p>Yuz rasmi faqat xodim roziligidan keyin yuklanadi va pilot yoqilgan tizimda ishlaydi</p></div></div>{items === null ? <div className="card-body"><Skeleton height={180}/></div> : items.length ? <div className="table-wrap"><table><thead><tr><th>Xodim</th><th>Ichki ID</th><th>Face ID</th><th>Holat</th><th>Amal</th></tr></thead><tbody>{items.map(item => <tr key={item.id}><td><div className="table-title">{item.name || "Nomsiz xodim"}</div></td><td>{item.external_id || "—"}</td><td>{item.enrollment_status==="enrolled"?`${item.photos?.length || 1} ta shablon`:"Sozlanmagan"}</td><td><Pill state={item.active === false ? "offline" : "active"}>{item.active === false ? "Nofaol" : "Faol"}</Pill></td><td><label className={`btn upload-btn ${uploading===item.id?"disabled":""}`}>{uploading===item.id?"Yuklanmoqda…":"Yuz rasmi"}<input type="file" accept="image/jpeg,image/png" capture="user" disabled={Boolean(uploading)} onChange={event=>{void uploadFace(item,event.target.files?.[0]);event.currentTarget.value="";}}/></label></td></tr>)}</tbody></table></div> : <EmptyState icon="users" title="Xodim qo‘shilmagan" detail="Yopiq pilot yoqilgan bo‘lsa, yozma rozilikdan keyin birinchi xodimni qo‘shing."/>}</Card></>;
}

function heatRgb(t:number) {
  const stops=[[37,99,235],[34,211,238],[34,197,94],[250,204,21],[220,38,38]];
  const x=Math.max(0,Math.min(1,t))*(stops.length-1);const i=Math.min(stops.length-2,Math.floor(x));const f=x-i;
  return stops[i].map((value,index)=>Math.round(value+(stops[i+1][index]-value)*f));
}

function HeatmapPage({ dashboard, siteId, onNavigate }: { dashboard: Dashboard; siteId: string; onNavigate: (id: string) => void }) {
  const [cameraId, setCameraId] = useState(() => dashboard.cameras[0]?.camera_id || "");
  const [days, setDays] = useState(7); const [points, setPoints] = useState<number | null>(null); const [error, setError] = useState("");
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    if (!cameraId) return; let stopped = false; let previewUrl = "";
    /* Preview ALOHIDA so'raladi va xatosi yutiladi: kamera kadri hali
       yuborilmagan bo'lsa (404) xarita baribir chiziladi — qoraroq fon
       ustida.  Avval `Promise.all` edi va preview 404 butun sahifani
       "Xarita olinmadi"ga tushirardi. */
    void (async () => {
      try {
        const heat = await api<{grid:number[][]; rows:number; cols:number; points?:number}>(`/api/v1/owner/heatmap?camera_id=${encodeURIComponent(cameraId)}&days=${days}`, "owner", { siteId });
        const url = await mediaObjectUrl(`/api/v1/owner/cameras/${encodeURIComponent(cameraId)}/preview`, "owner", siteId).catch(() => "");
        if (stopped) { if (url) URL.revokeObjectURL(url); return; }
        previewUrl = url;
        const target = canvas.current; const ctx = target?.getContext("2d"); if (!target || !ctx) return;
        const width = target.width, height = target.height; ctx.clearRect(0, 0, width, height);
        if (url) {
          const image = new Image(); image.src = url; await image.decode(); if (stopped) return;
          ctx.drawImage(image, 0, 0, width, height);
        } else {
          ctx.fillStyle = "#0f172a"; ctx.fillRect(0, 0, width, height);
          ctx.fillStyle = "#64748b"; ctx.font = "600 15px system-ui";
          ctx.fillText("Kamera kadri hali kelmagan — xarita mavhum fonda", 20, height - 20);
        }
        const peak = Math.max(1, ...heat.grid.flat()); ctx.save(); ctx.globalCompositeOperation = "screen";
        heat.grid.forEach((row, rowIndex) => row.forEach((value, colIndex) => { const strength = Number(value || 0) / peak; if (strength < .1) return; const x = (colIndex + .5) * width / heat.cols, y = (rowIndex + .5) * height / heat.rows, radius = Math.max(width / heat.cols * 2.8, 28) + strength * Math.max(width / heat.cols * 4, 64), rgb = heatRgb(strength); const glow = ctx.createRadialGradient(x, y, 0, x, y, radius); glow.addColorStop(0, `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${(.42 + strength * .34).toFixed(2)})`); glow.addColorStop(1, "rgba(0,0,0,0)"); ctx.fillStyle = glow; ctx.fillRect(x - radius, y - radius, radius * 2, radius * 2); }));
        ctx.restore(); setPoints(heat.points || 0); setError("");
      } catch (reason) {
        if (!stopped) setError(reason instanceof Error ? reason.message : "Xarita olinmadi");
      }
    })();
    return () => { stopped = true; if (previewUrl) URL.revokeObjectURL(previewUrl); };
  }, [cameraId, days, siteId]);
  return <><PageHeader title="Faol zonalar" subtitle="Tanlangan kameraning haqiqiy ko‘rinishidagi silliq anonim harakat oqimi." actions={<select className="select" value={cameraId} onChange={event => setCameraId(event.target.value)}>{dashboard.cameras.map(camera => <option value={camera.camera_id} key={camera.camera_id}>{camera.label || camera.camera_id}</option>)}</select>}/><Card><div className="card-head"><div><h2>Kamera ko‘rinishidagi faol zonalar</h2><p>{points == null ? "Ma’lumot yuklanmoqda…" : points ? `${formatNumber(points)} ta anonim harakat nuqtasi` : "Bu davr uchun harakat ma’lumoti yo‘q"}</p></div><div className="segmented">{[1,7,30].map(value => <button key={value} className={days === value ? "active" : ""} onClick={() => setDays(value)}>{value === 1 ? "Bugun" : `${value} kun`}</button>)}</div></div>{!hasFeature(dashboard,"xarita") ? <PlanLock title="Issiqlik xaritasi Biznes tarifida" detail="Mijozlarning qayerda ko‘p to‘xtashini aynan kamera burchagida ko‘rasiz." onUpgrade={() => onNavigate("billing")}/> : error ? <EmptyState icon="heat" title="Xarita hozir ochilmadi" detail={error}/> : cameraId ? <div className="heatmap-wrap"><canvas ref={canvas} width="960" height="540" aria-label="Kamera ko‘rinishidagi faol zonalar"/><div className="heat-legend"><span>past</span><i/><span>yuqori</span></div></div> : <EmptyState icon="camera" title="Kamera ulanmagan" detail="Kamera qo‘shilgach faol zonalar shu yerda ko‘rinadi."/>}</Card></>;
}

function BillingPage({dashboard,siteId}:{dashboard:Dashboard;siteId:string}) {
  const [invoices,setInvoices]=useState<Invoice[]|null>(null);const[months,setMonths]=useState(1);const[busy,setBusy]=useState(false);const[error,setError]=useState("");
  const load=useCallback(()=>api<Invoice[]>("/api/v1/owner/invoices","owner",{siteId}).then(data=>{setInvoices(data);setError("");}).catch(reason=>setError(reason instanceof Error?reason.message:"Hisoblar olinmadi")),[siteId]);
  useEffect(()=>{void load();},[load]);
  const create=async()=>{setBusy(true);setError("");try{const invoice=await api<Invoice>("/api/v1/owner/invoices","owner",{method:"POST",siteId,body:JSON.stringify({months})});setInvoices(current=>[invoice,...(current||[])]);}catch(reason){setError(reason instanceof Error?reason.message:"Hisob yaratilmadi");}finally{setBusy(false);}};
  return <><PageHeader title="Tarif va to‘lov" subtitle="Amaldagi obuna va server hisoblagan haqiqiy hisob-fakturalar."/><div className="dashboard-grid"><Card><div className="card-head"><div><h2>{dashboard.site.plan?.name || "Amaldagi tarif"}</h2><p>To‘lov operator tasdig‘idan keyin obunaga qo‘shiladi</p></div><Pill state={dashboard.subscription?.status}>{dashboard.subscription?.status || "—"}</Pill></div><div className="card-body"><div className="metric-value">{formatMoney(dashboard.subscription?.monthly_price_uzs)}</div><p className="metric-note">oyiga · {dashboard.subscription?.days_left==null?"muddat olinmadi":`${dashboard.subscription.days_left} kun qoldi`}</p><div className="invoice-create"><select className="select" value={months} onChange={event=>setMonths(Number(event.target.value))} aria-label="Hisob muddati"><option value={1}>1 oy</option><option value={3}>3 oy</option><option value={6}>6 oy</option><option value={12}>12 oy</option></select><button className="btn btn-primary" disabled={busy} onClick={()=>void create()}>{busy?"Yaratilmoqda…":"Hisob-faktura yaratish"}</button></div></div></Card><Card><div className="card-head"><div><h2>To‘lov tartibi</h2><p>Provayder ulanmaguncha qo‘lda tasdiqlash</p></div></div><div className="card-body"><p className="metric-note">Hisobni yarating, rekvizitlar bo‘yicha to‘lang. Operator tushumni tasdiqlagandan keyin obuna avtomatik uzayadi.</p></div></Card></div>{error?<div className="alert-strip section-gap"><Icon name="bell"/><div><strong>Hisob bilan muammo:</strong> {error}</div></div>:null}<Card className="section-gap"><div className="card-head"><div><h2>Hisob-fakturalar</h2><p>Summalar tarif va muddat bo‘yicha serverda hisoblangan</p></div></div>{invoices===null?<div className="card-body"><Skeleton height={140}/></div>:invoices.length?<div className="table-wrap"><table><thead><tr><th>Raqam</th><th>Muddat</th><th>Summa</th><th>Holat</th><th>Sana</th><th>Amal</th></tr></thead><tbody>{invoices.map(invoice=><tr key={invoice.id}><td><div className="table-title">#{invoice.id}</div></td><td>{invoice.months} oy</td><td>{formatMoney(invoice.amount_uzs,{short:false})}</td><td><Pill state={invoice.state}>{invoice.state==="paid"?"To‘langan":invoice.state==="pending"?"Kutilmoqda":"Bekor qilingan"}</Pill></td><td>{formatDateShort(invoice.created_at)}</td><td>{invoice.state==="pending"&&invoice.pay_url?<a className="btn" href={invoice.pay_url} target="_blank" rel="noreferrer">Ochish</a>:"—"}</td></tr>)}</tbody></table></div>:<EmptyState icon="invoice" title="Hisob-faktura yo‘q" detail="Kerakli muddatni tanlab birinchi hisob-fakturani yarating."/>}</Card></>;
}

function TelegramPage({siteId}:{siteId:string}) {
  const [members,setMembers]=useState<TelegramMember[]|null>(null);const[role,setRole]=useState<"owner"|"manager">("manager");const[name,setName]=useState("");const[invite,setInvite]=useState<{url:string;expires_minutes:number}|null>(null);const[busy,setBusy]=useState(false);const[error,setError]=useState("");
  const load=useCallback(()=>api<{members:TelegramMember[]}>("/api/v1/owner/members","owner",{siteId}).then(data=>{setMembers(data.members||[]);setError("");}).catch(reason=>setError(reason instanceof Error?reason.message:"A’zolar olinmadi")),[siteId]);
  useEffect(()=>{void load();},[load]);
  const createInvite=async()=>{setBusy(true);setError("");try{const result=await api<{url:string;expires_minutes:number}>("/api/v1/owner/telegram-invite","owner",{method:"POST",siteId,body:JSON.stringify({role,display_name:name.trim()||null})});setInvite(result);}catch(reason){setError(reason instanceof Error?reason.message:"Taklif yaratilmadi");}finally{setBusy(false);}};
  const remove=async(member:TelegramMember)=>{if(!window.confirm(`${member.display_name||member.telegram_id} a’zoligini o‘chirasizmi?`))return;setError("");try{await api(`/api/v1/owner/members/${encodeURIComponent(member.id)}`,"owner",{method:"DELETE",siteId});await load();}catch(reason){setError(reason instanceof Error?reason.message:"A’zo o‘chirilmadi");}};
  return <><PageHeader title="Telegram" subtitle="Egalar va menejerlar uchun botga xavfsiz, bir martalik taklif."/><div className="dashboard-grid"><Card><div className="card-head"><div><h2>Taklif havolasi</h2><p>Havola 30 daqiqada eskiradi va bir marta ishlaydi</p></div></div><div className="card-body"><div className="form-grid"><label>Kim uchun<select className="select" value={role} onChange={event=>setRole(event.target.value as "owner"|"manager")}><option value="manager">Menejer</option><option value="owner">Biznes egasi</option></select></label><label>Ism (ixtiyoriy)<input className="input" value={name} onChange={event=>setName(event.target.value)} maxLength={120}/></label></div><button className="btn btn-primary" disabled={busy} onClick={()=>void createInvite()}>{busy?"Yaratilmoqda…":"Taklif yaratish"}</button>{invite?<div className="invite-result"><b>Taklif tayyor · {invite.expires_minutes} daqiqa</b><a href={invite.url} target="_blank" rel="noreferrer">{invite.url}</a><div className="page-actions"><button className="btn" onClick={()=>navigator.clipboard?.writeText(invite.url)}>Nusxalash</button><a className="btn btn-primary" href={invite.url} target="_blank" rel="noreferrer">Telegramda ochish</a></div></div>:null}</div></Card><Card><div className="card-head"><div><h2>Nima yuboriladi?</h2><p>Filial bo‘yicha ruxsatga bog‘liq</p></div></div><div className="card-body"><p className="metric-note">Muhim kamera va tizim ogohlantirishlari, kunlik biznes xulosasi hamda Mini App havolasi. Boshqa filial ma’lumoti berilmaydi.</p></div></Card></div>{error?<div className="alert-strip section-gap"><Icon name="bell"/><div><strong>Telegram bilan muammo:</strong> {error}</div></div>:null}<Card className="section-gap"><div className="card-head"><div><h2>Ulangan foydalanuvchilar</h2><p>Faol bot a’zolari</p></div></div>{members===null?<div className="card-body"><Skeleton height={130}/></div>:members.length?<div className="table-wrap"><table><thead><tr><th>Foydalanuvchi</th><th>Rol</th><th>Kunlik xulosa</th><th>Amal</th></tr></thead><tbody>{members.map(member=><tr key={member.id}><td><div className="table-title">{member.display_name||`Telegram ${member.telegram_id}`}</div></td><td>{member.role==="owner"?"Egasi":member.role==="manager"?"Menejer":"Servis admin"}</td><td>{member.digest_muted?"O‘chirilgan":"Yoqilgan"}</td><td><button className="btn btn-danger" onClick={()=>void remove(member)}>O‘chirish</button></td></tr>)}</tbody></table></div>:<EmptyState icon="bell" title="Telegram ulanmagan" detail="Taklif yarating va uni kerakli egasi yoki menejerga yuboring."/>}</Card></>;
}

function downloadTrafficCsv(dashboard:Dashboard) {
  const rows = dashboard.trend.map(point=>[point.date||point.day||"",point.entries??point.entered??point.count??0]);
  const csv = ["sana,kirgan_mijozlar",...rows.map(row=>row.join(","))].join("\n");
  const url=URL.createObjectURL(new Blob([`\uFEFF${csv}`],{type:"text/csv;charset=utf-8"}));
  const link=document.createElement("a");link.href=url;link.download=`chaqimchi-${dashboard.site.id}-14-kun.csv`;link.click();URL.revokeObjectURL(url);
}

function GenericPage({ id, dashboard, sites, siteId, onNavigate }: { id:string; dashboard:Dashboard; sites:Site[]; siteId:string; onNavigate:(id:string)=>void }) {
  if (id === "cameras") return <><PageHeader title="Kameralar" subtitle="Jonli kadr, ulanish holati va AI tahlil qatlami."/><CamerasBlock dashboard={dashboard} siteId={siteId} expanded/></>;
  if (id === "traffic") return <TrafficPage dashboard={dashboard}/>;
  if (id === "heatmap") return <HeatmapPage dashboard={dashboard} siteId={siteId} onNavigate={onNavigate}/>;
  if (id === "branches") return <><PageHeader title="Filiallar" subtitle="Barcha savdo nuqtalaringizning aloqa va kamera holati."/><div className="metric-grid">{sites.map(site => <MetricCard key={site.id} label={site.name} value={`${formatNumber(site.cameras_active)} / ${formatNumber(site.cameras_expected)}`} note={site.address || (site.connection === "online" ? "Aloqada" : "Aloqani tekshiring")} icon="branch" tone={site.connection === "online" ? "green" : "red"}/>)}</div></>;
  if (id === "alerts") return <EventEvidence kind="owner" siteId={siteId}/>;
  if (id === "reports") return <><PageHeader title="Hisobotlar" subtitle="Oqim, kamera va xavfsizlik bo‘yicha tushunarli yakun." actions={<button className="btn" onClick={()=>downloadTrafficCsv(dashboard)}><Icon name="report"/>CSV yuklash</button>}/><div className="metric-grid"><MetricCard label="Bugungi tashrif" value={formatNumber(value(dashboard.today,"traffic.entered","entered","entries","visitors"))} icon="users"/><MetricCard label="Navbat holatlari" value={formatNumber(value(dashboard.today,"queue.alerts","queue_events","queue_alerts"))} icon="bell" tone="yellow"/><MetricCard label="Faol kameralar" value={formatNumber(dashboard.site.cameras_active)} icon="camera" tone="green"/><MetricCard label="Hodisalar" value={formatNumber(dashboard.events.length)} icon="shield" tone="blue"/></div><Card><div className="card-head"><div><h2>14 kunlik ko‘rsatkich</h2><p>Grafik va yuklab olinadigan CSV bitta real ma’lumotdan tuzilgan</p></div></div><TrendChart points={dashboard.trend}/></Card><Demography dashboard={dashboard} siteId={siteId} onNavigate={onNavigate}/></>;
  if (id === "billing") return <BillingPage dashboard={dashboard} siteId={siteId}/>;
  if (id === "telegram") return <TelegramPage siteId={siteId}/>;
  if (id === "settings") return <SettingsPage dashboard={dashboard} sites={sites} siteId={siteId}/>;
  return <><PageHeader title="Bo‘lim" subtitle="Bu bo‘lim panel tarkibida."/><Card><EmptyState icon="settings" title="Soddalashtirilgan ish maydoni" detail="Kerakli ma’lumotlar yig‘ilgach mazmun avtomatik ko‘rinadi."/></Card></>;
}

/** Oqim sahifasi: bugungi soatlik egri va 14 kunlik dinamika. */
function TrafficPage({ dashboard }: { dashboard: Dashboard }) {
  const traffic = ((dashboard.today as Record<string, unknown>).traffic || {}) as Record<string, unknown>;
  const hourly = Array.isArray(traffic.hourly) ? (traffic.hourly as { hour:number; entered:number; exited:number }[]) : [];
  const hourPoints: Point[] = hourly.map(item => ({ label: `${String(item.hour).padStart(2,"0")}:00`, value: Number(item.entered) || 0 }));
  const exitPoints: Point[] = hourly.map(item => ({ label: `${String(item.hour).padStart(2,"0")}:00`, value: Number(item.exited) || 0 }));
  return <>
    <PageHeader title="Mijozlar oqimi" subtitle="Kunlar va vaqt bo‘yicha anonim tashriflar tahlili."/>
    <Card>
      <div className="card-head"><div><h2>Bugun, soat bo‘yicha</h2><p>Kirgan va chiqqanlar — shaxsni saqlamasdan</p></div></div>
      {hourPoints.some(point => point.value > 0)
        ? <LineChart series={[{ name: "Kirdi", points: hourPoints }, { name: "Chiqdi", points: exitPoints }]}/>
        : <EmptyState icon="chart" title="Bugun hali tashrif yo‘q" detail="Kamera birinchi kirishni qayd qilgach grafik shu yerda to‘ladi."/>}
    </Card>
    <Card className="section-gap">
      <div className="card-head"><div><h2>Oxirgi 14 kun</h2><p>Kunlik dinamika</p></div></div>
      <TrendChart points={dashboard.trend}/>
    </Card>
  </>;
}

/** Sozlamalar: hozircha faqat HAQIQATAN mavjud bo'lgan ma'lumot.
 *  Ilgari bu sahifa bo'sh "ish olib borilmoqda" yozuvi edi. */
function SettingsPage({ dashboard, sites, siteId }: { dashboard: Dashboard; sites: Site[]; siteId: string }) {
  const site = sites.find(item => item.id === siteId);
  return <>
    <PageHeader title="Sozlamalar" subtitle="Do‘kon ma’lumotlari va bildirishnoma kanallari."/>
    <div className="dashboard-grid">
      <Card>
        <div className="card-head"><div><h2>Do‘kon</h2><p>O‘rnatuvchi kiritgan ma’lumot</p></div></div>
        <div className="card-body">
          <div className="simple-row"><span>Nomi</span><b>{site?.name || dashboard.site.name}</b></div>
          <div className="simple-row"><span>Manzil</span><b>{site?.address || dashboard.site.address || "—"}</b></div>
          <div className="simple-row"><span>Tarif</span><b>{dashboard.site.plan?.name || "—"}</b></div>
          <div className="simple-row"><span>Kameralar</span><b>{formatNumber(dashboard.site.cameras_expected)} tagacha</b></div>
          <p className="metric-note">Bu maydonlarni o‘zgartirish uchun o‘rnatuvchi yoki qo‘llab-quvvatlash xizmatiga murojaat qiling.</p>
        </div>
      </Card>
      <Card>
        <div className="card-head"><div><h2>Bildirishnomalar</h2><p>Telegram orqali yuboriladi</p></div></div>
        <div className="card-body">
          <p className="metric-note">Muhim kamera va tizim holatlari hamda kunlik xulosa botga boradi. Kim olishini «Telegram» bo‘limida boshqarasiz.</p>
          <a className="btn btn-wide" href="/owner/telegram">Telegram a’zolari</a>
        </div>
      </Card>
    </div>
  </>;
}

function OwnerApp() {
  const [authenticated,setAuthenticated] = useState(() => Boolean(tokenFor("owner")));
  // Tokenni DARHOL manzildan olib tashlaymiz (bir marta, render'dan
  // oldin): u tarixda va `Referer` sarlavhasida qolib ketmasin.
  const [connectToken,setConnectToken] = useState(() => takeConnectToken());
  const [checkingLink,setCheckingLink] = useState(() => new URLSearchParams(window.location.search).has("key"));
  const [sites,setSites] = useState<Site[]>([]); const [siteId,setSiteId] = useState("");
  const [active,navigateTo] = usePanelRoute("/owner", ROUTE_IDS, "home");
  const [drawer,setDrawer] = useState(false);
  const [loginError,setLoginError] = useState(""); const [busy,setBusy] = useState(false);
  const {data,error,loading,refresh} = useAdaptiveDashboard(siteId,authenticated);

  useEffect(() => {
    if ("serviceWorker" in navigator) navigator.serviceWorker.register("/owner-sw.js").catch(() => undefined);
  }, []);

  /* Parolsiz kirishning ikki yo'li.  Ikkalasi ham bitta effektda:
     ular ketma-ket sinaladi va faqat ikkalasi ham ishlamaganda login
     formasi ko'rsatiladi.
       1) Botdagi bir martalik havola — `/owner?key=...`
       2) Telegram Mini App — `initData` */
  useEffect(() => {
    if (authenticated) { setCheckingLink(false); return; }
    let stopped = false;
    (async () => {
      try {
        if (await loginWithLinkKey()) { if (!stopped) setAuthenticated(true); return; }
        if (await loginWithTelegram()) { if (!stopped) setAuthenticated(true); return; }
      } catch (reason) {
        if (!stopped) setLoginError(reason instanceof Error ? reason.message : "Havola bo‘yicha kirish amalga oshmadi");
      } finally {
        if (!stopped) setCheckingLink(false);
      }
    })();
    return () => { stopped = true; };
  }, [authenticated]);

  const loadSites = useCallback(async () => {
    const result = await api<{sites:Site[]}>("/api/v1/owner/sites", "owner");
    setSites(result.sites || []); setSiteId(current => current || result.sites?.[0]?.id || "");
  }, []);
  useEffect(() => {
    if (!authenticated) return;
    loadSites().catch((reason: unknown) => {
      // `reason` — `unknown`: rad etilgan va'da Error bo'lmasligi ham
      // mumkin, avvalgi `reason.status` esa bunday holatda ishlov
      // beruvchining o'zini yiqitardi.
      const status = (reason as { status?: number } | null)?.status;
      if (status === 401) { clearToken("owner"); setAuthenticated(false); }
      else setLoginError(reason instanceof Error ? reason.message : "Filiallar olinmadi");
    });
  }, [authenticated,loadSites]);

  const submit = async (username:string,password:string) => { setBusy(true);setLoginError("");try { await login(username,password,"owner");setAuthenticated(true); } catch(reason) { setLoginError(reason instanceof Error ? reason.message : "Kirish amalga oshmadi"); } finally { setBusy(false); } };
  const logout = () => { clearToken("owner");setAuthenticated(false);setSites([]);setSiteId(""); };
  const navigate = (id:string) => { if (id === "more") setDrawer(true); else { navigateTo(id); setDrawer(false); window.scrollTo({top:0,behavior:"smooth"}); } };

  const splash = (title:string) => <div className="login-page"><section className="login-visual"><Logo/><div><span className="eyebrow">BIZNES PANELI</span><h1>{title}</h1></div></section><section className="login-panel"><div style={{width:"min(390px,100%)"}}><Skeleton height={54}/><div style={{height:14}}/><Skeleton height={150}/></div></section></div>;
  if (checkingLink) return splash("Havola tekshirilmoqda.");
  // Kompyuterni ulash oqimi login ekranidan OLDIN: dastur o'rnatilgach
  // brauzer aynan shu havolani ochadi va odam hali hisobga ega
  // bo'lmasligi mumkin.
  if (connectToken) {
    return <Connect
      token={connectToken}
      authenticated={authenticated}
      onConnected={() => { setConnectToken(""); setAuthenticated(true); navigateTo("setup"); }}
    />;
  }
  if (!authenticated) return <LoginScreen kind="owner" onSubmit={submit} busy={busy} error={loginError} botUrl={telegramBotUrl()}/>;
  if (loading && !data) return splash("Ko‘rsatkichlar tayyorlanmoqda.");
  /* Ma'lumot kelmadi — sabab va chiqish yo'li KO'RSATILADI.  Avval bu
     holat cheksiz skeletga tushardi: 0 ta filial ham, doimiy server
     xatosi ham xabarsiz "yuklanmoqda" bo'lib qolar edi. */
  if (!data) {
    return <div className="login-page">
      <section className="login-visual"><Logo/><div><span className="eyebrow">BIZNES PANELI</span>
        <h1>{sites.length === 0 && !loginError ? "Sizga hali do‘kon biriktirilmagan" : "Ma’lumot ochilmadi"}</h1></div></section>
      <section className="login-panel"><div style={{width:"min(390px,100%)"}}>
        <p className="metric-note">{sites.length === 0 && !loginError
          ? "Hisobingiz ishlayapti, lekin unga birorta do‘kon ulanmagan. O‘rnatuvchi yoki qo‘llab-quvvatlash xizmatiga murojaat qiling."
          : error || loginError || "Server bilan aloqa bo‘lmadi. Internetni tekshirib, qayta urinib ko‘ring."}</p>
        <div className="page-actions" style={{marginTop:14}}>
          <button className="btn btn-primary" onClick={() => { void loadSites(); void refresh(); }}>Qayta urinish</button>
          <button className="btn" onClick={logout}>Chiqish</button>
        </div>
      </div></section>
    </div>;
  }

  const selected = sites.find(site => site.id === siteId);
  const today = formatDateUz();
  const alertCount = data.events.length;
  return <AppShell
    nav={NAV}
    mobileNav={MOBILE_NAV}
    active={active}
    onNavigate={navigate}
    title={selected?.name || data.site.name}
    subtitle={`Yangilandi: ${new Date(data.updated_at).toLocaleTimeString("uz-UZ",{hour:"2-digit",minute:"2-digit"})}`}
    onLogout={logout}
    sidebarFooter={<div className="sidebar-user"><Icon name="store"/><div><b>{selected?.name || data.site.name}</b><small>{selected?.address || data.site.address || "Manzil kiritilmagan"}</small></div></div>}
    headerActions={<>
      {sites.length > 1 ? <select className="select" value={siteId} onChange={event => setSiteId(event.target.value)} aria-label="Filialni tanlash">{sites.map(site => <option value={site.id} key={site.id}>{site.name}</option>)}</select> : null}
      <span className="topbar-date"><Icon name="calendar" size={16}/>{today}</span>
      <button className="btn btn-icon topbar-bell" onClick={() => navigate("alerts")} aria-label={`Ogohlantirishlar: ${alertCount}`}><Icon name="bell"/>{alertCount ? <i className="bell-badge">{alertCount > 9 ? "9+" : alertCount}</i> : null}</button>
      <button className="btn btn-icon" onClick={() => refresh()} aria-label="Yangilash"><Icon name="pulse"/></button>
    </>}>
    {error ? <div className="alert-strip"><Icon name="bell"/><div><strong>Yangilashda muammo:</strong> {error}. Oxirgi olingan ma’lumot ko‘rsatilmoqda.</div></div> : null}
    {active === "home"
      ? <>
          <PageHeader title="Bugungi nazorat" subtitle={today} />
          <OwnerHome dashboard={data} sites={sites} siteId={siteId} onNavigate={navigate} cameras={<CamerasBlock dashboard={data} siteId={siteId} onOpenAll={() => navigate("cameras")}/>} />
        </>
      : active === "employees" ? <EmployeesPage siteId={siteId}/>
      : active === "setup" ? <SetupCameras siteId={siteId} onDone={() => { void refresh(); navigate("zones"); }}/>
      : active === "zones" ? <GeometryEditor siteId={siteId} cameras={data.cameras}/>
      : active === "agent" ? <VisionAgent siteId={siteId} onNavigate={navigate}/>
      : <GenericPage id={active} dashboard={data} sites={sites} siteId={siteId} onNavigate={navigate}/>}
    {drawer ? <div className="drawer-backdrop" onClick={() => setDrawer(false)}><aside className="drawer" onClick={event => event.stopPropagation()}><div className="drawer-head"><Logo/><button className="btn btn-icon" onClick={() => setDrawer(false)} aria-label="Yopish"><Icon name="close"/></button></div><nav>{NAV.map(item => <button key={item.id} className={active === item.id ? "active" : ""} onClick={() => navigate(item.id)}><Icon name={item.icon}/>{item.label}</button>)}<button onClick={logout}><Icon name="logout"/>Chiqish</button></nav></aside></div> : null}
  </AppShell>;
}

createRoot(document.getElementById("root")!).render(<StrictMode><OwnerApp/></StrictMode>);
