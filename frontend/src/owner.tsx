import { StrictMode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { api, clearToken, formatMoney, formatNumber, login, relativeMinutes, saveToken, tokenFor } from "./api";
import { AppShell, Card, EmptyState, LoginScreen, MetricCard, PageHeader, Pill, Skeleton, StatusDot, type NavItem } from "./components";
import { Icon, Logo } from "./icons";
import "./styles.css";

type Site = { id: string; name: string; address?: string; connection?: string; cameras_active?: number; cameras_expected?: number; role?: string };
type CameraState = { camera_id: string; state: string; reason?: string; reported_at?: string };
type Camera = { camera_id: string; label?: string; enabled?: boolean };
type EventItem = { id?: string; event_type: string; label?: string; camera_id?: string; created_at?: string; occurred_at?: string };
type TrendPoint = { date?: string; day?: string; entries?: number; entered?: number; count?: number };
type Dashboard = {
  site: { id: string; name: string; address?: string; connection: string; minutes_since_seen?: number | null; cameras_active?: number; cameras_expected?: number; plan?: { name?: string } };
  today: Record<string, unknown>;
  cameras: Camera[];
  camera_states: CameraState[];
  events: EventItem[];
  trend: TrendPoint[];
  subscription?: { status?: string; days_left?: number; monthly_price_uzs?: number; subscription_until?: string };
  updated_at: string;
  revision?: string;
};
type Employee = { id: string; name?: string; external_id?: string; active?: boolean; enrollment_status?: string; photos?: {id:string}[] };
type Invoice = { id:string; months:number; amount_uzs:number; state:string; created_at?:string; paid_at?:string; pay_url?:string; payme_url?:string; click_url?:string };
type TelegramMember = { id:string; telegram_id:string; role:string; display_name?:string; digest_muted?:boolean; created_at?:string };

const NAV: NavItem[] = [
  { id: "home", label: "Bosh sahifa", icon: "home" },
  { id: "cameras", label: "Kameralar", icon: "camera" },
  { id: "traffic", label: "Mijozlar oqimi", icon: "chart" },
  { id: "employees", label: "Xodimlar", icon: "users" },
  { id: "heatmap", label: "Issiqlik xaritasi", icon: "heat" },
  { id: "branches", label: "Filiallar", icon: "branch" },
  { id: "alerts", label: "Ogohlantirishlar", icon: "bell" },
  { id: "reports", label: "Hisobotlar", icon: "report" },
  { id: "billing", label: "Tarif va to‘lov", icon: "card" },
  { id: "telegram", label: "Telegram", icon: "bell" },
  { id: "settings", label: "Sozlamalar", icon: "settings" },
];

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
    if (!authenticated || !siteId) return;
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
      } catch { if (!src) setError(true); }
      if (!stopped && live) timer = window.setTimeout(load, 2500);
    };
    void load();
    return () => { stopped = true; window.clearTimeout(timer); if (current) URL.revokeObjectURL(current); };
  }, [camera.camera_id, live, overlay, siteId]);
  return <div className="camera-frame">{src ? <img src={src} alt={`${camera.label || camera.camera_id} kamerasi`} /> : <div className="camera-empty"><Icon name="camera" size={28}/><span>{error ? "Kadr hozircha kelmadi" : "Kadr yuklanmoqda…"}</span></div>}{overlay && src ? <span className="camera-overlay-badge">AI tahlil</span> : null}</div>;
}

function CamerasBlock({ dashboard, siteId, expanded = false }: { dashboard: Dashboard; siteId: string; expanded?: boolean }) {
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
    <div className="card-head"><div><h2>Kameralar</h2><p>Do‘kon holati va so‘nggi haqiqiy kadrlar</p></div><div className="page-actions"><button className="btn" onClick={toggleOverlay}><Icon name="eye"/>{overlay ? "AI ramkani yopish" : "AI ramkani ko‘rsatish"}</button><button className={`btn ${live ? "btn-primary" : ""}`} onClick={toggleLive}><Icon name="pulse"/>{live ? "Jonli" : "Jonli ko‘rish"}</button></div></div>
    {cameras.length ? <div className="live-grid">{cameras.map(camera => { const state = stateMap.get(camera.camera_id); return <article className="camera-tile" key={camera.camera_id}><CameraImage camera={camera} siteId={siteId} overlay={overlay} live={live}/><div className="camera-meta"><div className="camera-name"><StatusDot state={state?.state || "unknown"}/><span>{camera.label || camera.camera_id}</span></div><small>{state?.reason || "Holat olinmoqda"}</small></div></article>; })}</div> : <EmptyState icon="camera" title="Kamera ulanmagan" detail="Kamera o‘rnatuvchi tomonidan qo‘shilgach haqiqiy kadrlar shu yerda ko‘rinadi." />}
  </Card>;
}

function Overview({ dashboard, siteId, onNavigate }: { dashboard: Dashboard; siteId: string; onNavigate: (id: string) => void }) {
  const entries = value(dashboard.today, "traffic.entered", "entered", "entries", "visitors", "person_count");
  const exits = value(dashboard.today, "traffic.exited", "exited", "exits");
  const peak = textValue(dashboard.today,"traffic.busiest_hour");
  const queues = value(dashboard.today, "queue.alerts", "queue_events", "queue_alerts", "queue_threshold_exceeded");
  const connection = dashboard.site.connection;
  return <>
    <PageHeader title={`Salom, ${dashboard.site.name}`} subtitle="Bugungi biznes holati — eng muhim raqamlar bitta sahifada." actions={<button className="btn" onClick={() => onNavigate("reports")}><Icon name="report"/><span>Hisobot</span></button>} />
    {connection !== "online" ? <div className={`alert-strip ${connection === "stale" ? "alert-info" : "alert-warning"}`}><Icon name="bell"/><div><strong>Aloqa {connection === "stale" ? "yangilanmoqda" : "uzilgan"}.</strong> Oxirgi aloqa: {relativeMinutes(dashboard.site.minutes_since_seen)}. Yangi ma’lumot kelguncha oxirgi tasdiqlangan raqamlar ko‘rsatiladi.</div></div> : null}
    <div className="metric-grid">
      <MetricCard label="Bugun kirgan mijozlar" value={formatNumber(entries)} note={entries == null ? "Yig‘ilmoqda" : exits != null ? `${formatNumber(exits)} ta chiqish` : "Bugungi hisob"} icon="users" tone="blue"/>
      <MetricCard label="Eng gavjum vaqt" value={String(peak)} note="Bugungi oqim bo‘yicha" icon="chart" tone="yellow"/>
      <MetricCard label="Kameralar ishlayapti" value={`${formatNumber(dashboard.site.cameras_active)} / ${formatNumber(dashboard.site.cameras_expected)}`} note={connection === "online" ? "Joriy holat" : "Oxirgi ma’lumot"} icon="camera" tone={connection === "online" ? "green" : "red"}/>
      <MetricCard label="Navbat signallari" value={formatNumber(queues)} note={queues === 0 ? "Muammo qayd etilmadi" : "Bugungi holatlar"} icon="bell" tone={queues ? "red" : "green"}/>
    </div>
    <div className="dashboard-grid">
      <div className="stack">
        <Card className="traffic-card"><div className="card-head"><div><h2>Mijozlar oqimi</h2><p>Oxirgi 14 kun</p></div><button className="btn" onClick={() => onNavigate("traffic")}>Batafsil</button></div><TrendChart points={dashboard.trend}/></Card>
        <CamerasBlock dashboard={dashboard} siteId={siteId}/>
      </div>
      <div className="stack">
        <Card><div className="card-head"><div><h2>Filial holati</h2><p>Qurilma va kameralar</p></div><Pill state={connection}>{connection === "online" ? "Ishlayapti" : connection === "stale" ? "Aloqa eskirgan" : "Oflayn"}</Pill></div><div className="health-list">{dashboard.camera_states.slice(0,6).map(item => <div className="health-row" key={item.camera_id}><div className="health-name"><StatusDot state={item.state}/><div><b>{dashboard.cameras.find(camera => camera.camera_id === item.camera_id)?.label || item.camera_id}</b><small>{item.reason}</small></div></div><span className="list-value">{item.state === "online" ? "Faol" : "Tekshirish kerak"}</span></div>)}</div></Card>
        <Card><div className="card-head"><div><h2>So‘nggi hodisalar</h2><p>AI va tizim xabarlari</p></div><button className="btn btn-icon" aria-label="Ogohlantirishlarni ko‘rish" onClick={() => onNavigate("alerts")}><Icon name="bell"/></button></div>{dashboard.events.length ? <div className="event-list">{dashboard.events.slice(0,6).map((item,index) => <div className="event-row" key={item.id || index}><div className="event-name"><div className="metric-icon tone-blue" style={{position:"static",width:34,height:34}}><Icon name="pulse" size={17}/></div><div><b>{item.label || item.event_type}</b><small>{item.camera_id || "Tizim"}</small></div></div><span className="list-value">{String(item.occurred_at || item.created_at || "").slice(11,16) || "—"}</span></div>)}</div> : <EmptyState icon="shield" title="Yangi hodisa yo‘q" detail="Bu yaxshi belgi. Tizim yangi muhim holatni shu yerda ko‘rsatadi." />}</Card>
        <Card><div className="card-head"><div><h2>Tarif</h2><p>{dashboard.subscription?.status === "active" ? "Obuna faol" : "Holatni tekshiring"}</p></div><Pill state={dashboard.subscription?.status}>{dashboard.site.plan?.name || "Tarif"}</Pill></div><div className="card-body"><div className="simple-row"><span>Keyingi to‘lov</span><b>{formatMoney(dashboard.subscription?.monthly_price_uzs)}</b></div><button className="btn btn-wide" onClick={() => onNavigate("billing")}>Tarif va hisoblar</button></div></Card>
      </div>
    </div>
  </>;
}

function EmployeesPage({ siteId }: { siteId: string }) {
  const [items, setItems] = useState<Employee[] | null>(null); const [error,setError] = useState(""); const [adding,setAdding] = useState(false); const [busy,setBusy] = useState(false); const [uploading,setUploading] = useState("");
  const load = useCallback(async () => {
    try {
      const data = await api<{employees:Employee[]}>("/api/v1/owner/faces", "owner", {siteId});
      setItems(data.employees || []); setError("");
    } catch {
      const data = await api<{employees:Employee[]}>("/api/v1/owner/employees", "owner", {siteId});
      setItems(data.employees || []); setError("");
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

function HeatmapPage({dashboard,siteId}:{dashboard:Dashboard;siteId:string}) {
  const [cameraId,setCameraId]=useState(()=>dashboard.cameras[0]?.camera_id||"");const[days,setDays]=useState(7);const[data,setData]=useState<{grid:number[][];rows:number;cols:number;points?:number}|null>(null);const[error,setError]=useState("");const canvas=useRef<HTMLCanvasElement>(null);
  useEffect(()=>{if(!cameraId)return;let stopped=false;api<{grid:number[][];rows:number;cols:number;points?:number}>(`/api/v1/owner/heatmap?camera_id=${encodeURIComponent(cameraId)}&days=${days}`,"owner",{siteId}).then(heat=>{if(stopped)return;setData(heat);setError("");const target=canvas.current;const ctx=target?.getContext("2d");if(!target||!ctx)return;const width=target.width,height=target.height,padX=width*.055,padY=height*.10,planW=width-padX*2,planH=height-padY*2;ctx.fillStyle="#f8fafc";ctx.fillRect(0,0,width,height);ctx.strokeStyle="#64748b";ctx.lineWidth=3;ctx.strokeRect(padX,padY,planW,planH);ctx.strokeStyle="#cbd5e1";ctx.lineWidth=2;[[.11,.18,.22,.13],[.39,.18,.18,.13],[.66,.18,.20,.13],[.13,.55,.23,.13],[.43,.55,.19,.13],[.72,.55,.15,.13]].forEach(([x,y,w,h])=>ctx.strokeRect(padX+planW*x,padY+planH*y,planW*w,planH*h));ctx.strokeStyle="#94a3b8";ctx.beginPath();ctx.moveTo(padX+planW*.41,padY+planH);ctx.lineTo(padX+planW*.59,padY+planH);ctx.stroke();ctx.fillStyle="#64748b";ctx.font="600 16px system-ui";ctx.fillText("Kirish",padX+planW*.44,padY+planH+28);const peak=Math.max(1,...heat.grid.flat());ctx.save();ctx.globalCompositeOperation="multiply";heat.grid.forEach((row,rowIndex)=>row.forEach((value,colIndex)=>{const t=Number(value||0)/peak;if(t<.12)return;const x=padX+(colIndex+.5)*(planW/heat.cols),y=padY+(rowIndex+.5)*(planH/heat.rows),radius=Math.max(planW/heat.cols*3.2,28)+t*Math.max(planW/heat.cols*5.5,58),rgb=heatRgb(t),glow=ctx.createRadialGradient(x,y,0,x,y,radius);glow.addColorStop(0,`rgba(${rgb[0]},${rgb[1]},${rgb[2]},.78)`);glow.addColorStop(.42,`rgba(${rgb[0]},${rgb[1]},${rgb[2]},.42)`);glow.addColorStop(1,"rgba(0,0,0,0)");ctx.fillStyle=glow;ctx.fillRect(x-radius,y-radius,radius*2,radius*2);}));ctx.restore();}).catch(reason=>{if(!stopped)setError(reason instanceof Error?reason.message:"Xarita olinmadi");});return()=>{stopped=true;};},[cameraId,days,siteId]);
  return <><PageHeader title="Faol zonalar" subtitle="Do‘kon rejasida mijozlar ko‘p to‘plangan joylar. Kataklar emas, silliq anonim harakat oqimi." actions={<select className="select" value={cameraId} onChange={event=>setCameraId(event.target.value)}>{dashboard.cameras.map(camera=><option value={camera.camera_id} key={camera.camera_id}>{camera.label||camera.camera_id}</option>)}</select>}/><Card><div className="card-head"><div><h2>Do‘kon rejasi</h2><p>{data?.points?`${formatNumber(data.points)} ta anonim harakat nuqtasi`:"Qurilma har 10 daqiqada yangi nuqtalarni yuboradi"}</p></div><div className="segmented">{[1,7,30].map(value=><button key={value} className={days===value?"active":""} onClick={()=>setDays(value)}>{value===1?"Bugun":`${value} kun`}</button>)}</div></div>{error?<EmptyState icon="heat" title="Xarita hozir ochilmadi" detail={error}/>:cameraId?<div className="heatmap-wrap plan-heatmap"><canvas ref={canvas} width="960" height="540" aria-label="Do‘kon rejasidagi faol zonalar"/><div className="heat-legend"><span>past</span><i/><span>yuqori</span></div></div>:<EmptyState icon="camera" title="Kamera ulanmagan" detail="Kamera qo‘shilgach faol zonalar shu yerda ko‘rinadi."/>}</Card></>;
}

function BillingPage({dashboard,siteId}:{dashboard:Dashboard;siteId:string}) {
  const [invoices,setInvoices]=useState<Invoice[]|null>(null);const[months,setMonths]=useState(1);const[busy,setBusy]=useState(false);const[error,setError]=useState("");
  const load=useCallback(()=>api<Invoice[]>("/api/v1/owner/invoices","owner",{siteId}).then(data=>{setInvoices(data);setError("");}).catch(reason=>setError(reason instanceof Error?reason.message:"Hisoblar olinmadi")),[siteId]);
  useEffect(()=>{void load();},[load]);
  const create=async()=>{setBusy(true);setError("");try{const invoice=await api<Invoice>("/api/v1/owner/invoices","owner",{method:"POST",siteId,body:JSON.stringify({months})});setInvoices(current=>[invoice,...(current||[])]);}catch(reason){setError(reason instanceof Error?reason.message:"Hisob yaratilmadi");}finally{setBusy(false);}};
  return <><PageHeader title="Tarif va to‘lov" subtitle="Amaldagi obuna va server hisoblagan haqiqiy hisob-fakturalar."/><div className="dashboard-grid"><Card><div className="card-head"><div><h2>{dashboard.site.plan?.name || "Amaldagi tarif"}</h2><p>To‘lov operator tasdig‘idan keyin obunaga qo‘shiladi</p></div><Pill state={dashboard.subscription?.status}>{dashboard.subscription?.status || "—"}</Pill></div><div className="card-body"><div className="metric-value">{formatMoney(dashboard.subscription?.monthly_price_uzs)}</div><p className="metric-note">oyiga · {dashboard.subscription?.days_left==null?"muddat olinmadi":`${dashboard.subscription.days_left} kun qoldi`}</p><div className="invoice-create"><select className="select" value={months} onChange={event=>setMonths(Number(event.target.value))} aria-label="Hisob muddati"><option value={1}>1 oy</option><option value={3}>3 oy</option><option value={6}>6 oy</option><option value={12}>12 oy</option></select><button className="btn btn-primary" disabled={busy} onClick={()=>void create()}>{busy?"Yaratilmoqda…":"Hisob-faktura yaratish"}</button></div></div></Card><Card><div className="card-head"><div><h2>To‘lov tartibi</h2><p>Provayder ulanmaguncha qo‘lda tasdiqlash</p></div></div><div className="card-body"><p className="metric-note">Hisobni yarating, rekvizitlar bo‘yicha to‘lang. Operator tushumni tasdiqlagandan keyin obuna avtomatik uzayadi.</p></div></Card></div>{error?<div className="alert-strip section-gap"><Icon name="bell"/><div><strong>Hisob bilan muammo:</strong> {error}</div></div>:null}<Card className="section-gap"><div className="card-head"><div><h2>Hisob-fakturalar</h2><p>Summalar tarif va muddat bo‘yicha serverda hisoblangan</p></div></div>{invoices===null?<div className="card-body"><Skeleton height={140}/></div>:invoices.length?<div className="table-wrap"><table><thead><tr><th>Raqam</th><th>Muddat</th><th>Summa</th><th>Holat</th><th>Sana</th><th>Amal</th></tr></thead><tbody>{invoices.map(invoice=><tr key={invoice.id}><td><div className="table-title">#{invoice.id}</div></td><td>{invoice.months} oy</td><td>{formatMoney(invoice.amount_uzs)}</td><td><Pill state={invoice.state}>{invoice.state==="paid"?"To‘langan":invoice.state==="pending"?"Kutilmoqda":"Bekor qilingan"}</Pill></td><td>{invoice.created_at?new Date(invoice.created_at).toLocaleDateString("uz-UZ"):"—"}</td><td>{invoice.state==="pending"&&invoice.pay_url?<a className="btn" href={invoice.pay_url} target="_blank" rel="noreferrer">Ochish</a>:"—"}</td></tr>)}</tbody></table></div>:<EmptyState icon="invoice" title="Hisob-faktura yo‘q" detail="Kerakli muddatni tanlab birinchi hisob-fakturani yarating."/>}</Card></>;
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

function GenericPage({ id, dashboard, sites, siteId }: { id:string; dashboard:Dashboard; sites:Site[]; siteId:string }) {
  if (id === "cameras") return <><PageHeader title="Kameralar" subtitle="Jonli kadr, ulanish holati va AI tahlil qatlami."/><CamerasBlock dashboard={dashboard} siteId={siteId} expanded/></>;
  if (id === "traffic") return <><PageHeader title="Mijozlar oqimi" subtitle="Kunlar va vaqt bo‘yicha anonim tashriflar tahlili."/><Card><div className="card-head"><div><h2>Oqim dinamikasi</h2><p>Shaxsni saqlamasdan, faqat anonim sanash</p></div></div><TrendChart points={dashboard.trend}/></Card></>;
  if (id === "heatmap") return <HeatmapPage dashboard={dashboard} siteId={siteId}/>;
  if (id === "branches") return <><PageHeader title="Filiallar" subtitle="Barcha savdo nuqtalaringizning aloqa va kamera holati."/><div className="metric-grid">{sites.map(site => <MetricCard key={site.id} label={site.name} value={`${formatNumber(site.cameras_active)} / ${formatNumber(site.cameras_expected)}`} note={site.address || (site.connection === "online" ? "Aloqada" : "Aloqani tekshiring")} icon="branch" tone={site.connection === "online" ? "green" : "red"}/>)}</div></>;
  if (id === "alerts") return <><PageHeader title="Ogohlantirishlar" subtitle="Faqat e’tibor talab qiladigan AI va tizim holatlari."/><Card>{dashboard.events.length ? <div className="event-list">{dashboard.events.map((item,index) => <div className="event-row" key={item.id || index}><div className="event-name"><Icon name="bell"/><div><b>{item.label || item.event_type}</b><small>{item.camera_id || "Tizim"}</small></div></div><span>{item.occurred_at || item.created_at || "—"}</span></div>)}</div> : <EmptyState icon="shield" title="Ogohlantirish yo‘q" detail="Hozircha e’tibor talab qiladigan yangi holat qayd etilmadi."/>}</Card></>;
  if (id === "reports") return <><PageHeader title="Hisobotlar" subtitle="Oqim, kamera va xavfsizlik bo‘yicha tushunarli yakun." actions={<button className="btn" onClick={()=>downloadTrafficCsv(dashboard)}><Icon name="report"/>CSV yuklash</button>}/><div className="metric-grid"><MetricCard label="Bugungi tashrif" value={formatNumber(value(dashboard.today,"traffic.entered","entered","entries","visitors"))} icon="users"/><MetricCard label="Navbat holatlari" value={formatNumber(value(dashboard.today,"queue.alerts","queue_events","queue_alerts"))} icon="bell" tone="yellow"/><MetricCard label="Faol kameralar" value={formatNumber(dashboard.site.cameras_active)} icon="camera" tone="green"/><MetricCard label="Hodisalar" value={formatNumber(dashboard.events.length)} icon="shield" tone="blue"/></div><Card><div className="card-head"><div><h2>14 kunlik ko‘rsatkich</h2><p>Grafik va yuklab olinadigan CSV bitta real ma’lumotdan tuzilgan</p></div></div><TrendChart points={dashboard.trend}/></Card></>;
  if (id === "billing") return <BillingPage dashboard={dashboard} siteId={siteId}/>;
  if (id === "telegram") return <TelegramPage siteId={siteId}/>;
  const info:Record<string,[string,string,string]> = { settings:["Sozlamalar","Profil, bildirishnoma va xavfsizlik.","Tizim sozlamalari o‘rnatuvchi tomonidan boshqariladi; biznes egasi bildirishnoma vaqtini va panel ko‘rinishini belgilaydi."] };
  const item = info[id] || ["Bo‘lim","Bu bo‘lim V2 panel tarkibida.","Kerakli ma’lumotlar yig‘ilgach mazmun avtomatik ko‘rinadi."];
  return <><PageHeader title={item[0]} subtitle={item[1]}/><Card><EmptyState icon={id === "heatmap" ? "heat" : "settings"} title="Soddalashtirilgan ish maydoni" detail={item[2]}/></Card></>;
}

function OwnerApp() {
  const [authenticated,setAuthenticated] = useState(() => Boolean(tokenFor("owner")));
  const [sites,setSites] = useState<Site[]>([]); const [siteId,setSiteId] = useState("");
  const [active,setActive] = useState("home"); const [drawer,setDrawer] = useState(false);
  const [loginError,setLoginError] = useState(""); const [busy,setBusy] = useState(false);
  const {data,error,loading,refresh} = useAdaptiveDashboard(siteId,authenticated);

  useEffect(() => {
    if ("serviceWorker" in navigator) navigator.serviceWorker.register("/owner-sw.js").catch(() => undefined);
  }, []);

  const loadSites = useCallback(async () => {
    const result = await api<{sites:Site[]}>("/api/v1/owner/sites", "owner");
    setSites(result.sites || []); setSiteId(current => current || result.sites?.[0]?.id || "");
  }, []);
  useEffect(() => { if (authenticated) loadSites().catch(reason => { if (reason.status === 401) { clearToken("owner"); setAuthenticated(false); } else setLoginError(reason.message); }); }, [authenticated,loadSites]);
  useEffect(() => {
    const telegram = (window as Window & {Telegram?: {WebApp?: {initData?: string; ready?:()=>void; expand?:()=>void}}}).Telegram?.WebApp;
    if (authenticated || !telegram?.initData) return;
    telegram.ready?.(); telegram.expand?.();
    api<{access_token:string}>("/api/v1/owner/auth/telegram-webapp", "owner", {method:"POST",body:JSON.stringify({init_data:telegram.initData})}).then(result => { saveToken("owner",result.access_token);setAuthenticated(true); }).catch(reason => setLoginError(reason.message));
  }, [authenticated]);

  const submit = async (username:string,password:string) => { setBusy(true);setLoginError("");try { await login(username,password,"owner");setAuthenticated(true); } catch(reason) { setLoginError(reason instanceof Error ? reason.message : "Kirish amalga oshmadi"); } finally { setBusy(false); } };
  const logout = () => { clearToken("owner");setAuthenticated(false);setSites([]);setSiteId(""); };
  const navigate = (id:string) => { if (id === "more") setDrawer(true); else { setActive(id); setDrawer(false); window.scrollTo({top:0,behavior:"smooth"}); } };
  if (!authenticated) return <LoginScreen kind="owner" onSubmit={submit} busy={busy} error={loginError}/>;
  if (loading || !data) return <div className="login-page"><section className="login-visual"><Logo/><div><span className="eyebrow">BIZNES PANELI</span><h1>Ko‘rsatkichlar tayyorlanmoqda.</h1></div></section><section className="login-panel"><div style={{width:"min(390px,100%)"}}><Skeleton height={54}/><div style={{height:14}}/><Skeleton height={150}/></div></section></div>;
  const selected = sites.find(site => site.id === siteId);
  return <AppShell kind="owner" nav={NAV} active={active} onNavigate={navigate} title={selected?.name || data.site.name} subtitle={`Yangilandi: ${new Date(data.updated_at).toLocaleTimeString("uz-UZ",{hour:"2-digit",minute:"2-digit"})}`} onLogout={logout} headerActions={<><select className="select" value={siteId} onChange={event => setSiteId(event.target.value)} aria-label="Filialni tanlash">{sites.map(site => <option value={site.id} key={site.id}>{site.name}</option>)}</select><button className="btn btn-icon" onClick={() => refresh()} aria-label="Yangilash"><Icon name="pulse"/></button></>}>
    {error ? <div className="alert-strip"><Icon name="bell"/><div><strong>Yangilashda muammo:</strong> {error}. Oxirgi olingan ma’lumot ko‘rsatilmoqda.</div></div> : null}
    {active === "home" ? <Overview dashboard={data} siteId={siteId} onNavigate={navigate}/> : active === "employees" ? <EmployeesPage siteId={siteId}/> : <GenericPage id={active} dashboard={data} sites={sites} siteId={siteId}/>} 
    {drawer ? <div className="drawer-backdrop" onClick={() => setDrawer(false)}><aside className="drawer" onClick={event => event.stopPropagation()}><div className="drawer-head"><Logo/><button className="btn btn-icon" onClick={() => setDrawer(false)} aria-label="Yopish"><Icon name="close"/></button></div><nav>{NAV.map(item => <button key={item.id} className={active === item.id ? "active" : ""} onClick={() => navigate(item.id)}><Icon name={item.icon}/>{item.label}</button>)}<button onClick={logout}><Icon name="logout"/>Chiqish</button></nav></aside></div> : null}
  </AppShell>;
}

createRoot(document.getElementById("root")!).render(<StrictMode><OwnerApp/></StrictMode>);
