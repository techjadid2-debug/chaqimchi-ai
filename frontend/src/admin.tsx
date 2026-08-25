import { StrictMode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { api, clearToken, formatDateUz, formatMoney, formatNumber, login, tokenFor } from "./api";
import { ActionMenu, AppShell, Avatar, Card, EmptyState, LoginScreen, MetricCard, PageHeader, Pill, SearchPalette, Skeleton, type NavItem } from "./components";
import { AdminHome } from "./AdminHome";
import { EventEvidence } from "./EventEvidence";
import { usePanelRoute } from "./router";
import { Icon, Logo } from "./icons";
import "./styles.css";

type Site = { id:string; name:string; address?:string; contact_phone?:string; plan?:string; license_status?:string; connection?:string; devices?:number; cameras_active?:number; cameras_expected?:number; days_left?:number; monthly_price_uzs?:number; last_seen?:string };
type DeviceMetric = { device_id:string; site_id:string; site_name?:string; label?:string; received_at?:string; cpu_percent?:number|null; ram_percent?:number|null; disk_percent?:number|null; fps?:number|null; inference_latency_ms?:number|null; uptime_sec?:number|null; npu_percent?:number|null; temperature_c?:number|null };
type CreatedCustomer = {site_id:string;name:string;pairing_code:string;pairing_expires_at?:string;username:string;password:string};
type AdminInvoice = {id:string;site_name?:string;site_id:string;months:number;amount_uzs:number;state:string;provider?:string;created_at?:string;paid_at?:string};
type Feature = {code:string;name:string;category:string;monthly_usd_cents:number;cost_usd_cents:number;active?:boolean};
type Account = {id:string;username:string;full_name?:string;role:string;status:string;company?:string;site_id?:string};
type ReadinessItem = {key:string;label:string;ok:boolean;required:boolean;reasons?:string[]};
type AdminDashboard = {
  range:string;
  stats:{ total_sites:number; active:number; total_devices:number; monthly_revenue_uzs:number; offline:number; not_paired:number; expiring_soon:number; by_connection?:Record<string,number> };
  sites:Site[];
  telemetry:DeviceMetric[];
  /** Serverning O'ZI.  O'lchanmagan ko'rsatkich kalit sifatida ham
   *  kelmaydi — shuning uchun hammasi ixtiyoriy. */
  server?:{ cpu_percent?:number; ram_percent?:number; disk_percent?:number; free_disk_gb?:number; load_1m?:number; cores?:number; temperature_c?:number };
  invoices?:{total?:number; pending?:number; paid?:number};
  readiness?:Record<string,unknown>;
  updated_at:string;
};

const NAV:NavItem[] = [
  {id:"overview",label:"Umumiy holat",icon:"home"},
  {id:"customers",label:"Mijozlar",icon:"users"},
  {id:"branches",label:"Filiallar",icon:"branch"},
  {id:"cameras",label:"Kameralar",icon:"camera"},
  {id:"devices",label:"Qurilmalar",icon:"server"},
  {id:"plans",label:"Tariflar",icon:"card"},
  {id:"payments",label:"To‘lovlar",icon:"invoice"},
  {id:"finance",label:"Moliya",icon:"chart"},
  {id:"events",label:"AI hodisalar",icon:"pulse"},
  {id:"agent",label:"Vision Agent",icon:"pulse"},
  {id:"monitoring",label:"Monitoring",icon:"chart"},
  {id:"roles",label:"Rollar",icon:"shield"},
  {id:"settings",label:"Sozlamalar",icon:"settings"},
];

const ROUTE_IDS = NAV.map(item=>item.id);
const MOBILE_NAV = ["overview","customers","payments","monitoring"];

function useAdminDashboard(authenticated:boolean, range:string) {
  const [data,setData] = useState<AdminDashboard|null>(null); const [loading,setLoading] = useState(true); const [error,setError] = useState(""); const failures=useRef(0);
  const refresh = useCallback(async()=>{ if(!authenticated)return;try{const next=await api<AdminDashboard>(`/api/v1/admin/dashboard?range=${range}`,"admin");setData(next);setError("");failures.current=0;}catch(reason){failures.current+=1;setError(reason instanceof Error?reason.message:"Ma’lumot olinmadi");}finally{setLoading(false);}},[authenticated,range]);
  useEffect(()=>{let timer=0,stopped=false;const tick=async()=>{await refresh();if(!stopped)timer=window.setTimeout(tick,document.hidden?60_000:failures.current?30_000:15_000);};void tick();return()=>{stopped=true;window.clearTimeout(timer);};},[refresh]);
  return {data,loading,error,refresh};
}

export function Percent({value}:{value:number|null|undefined}) { const safe=typeof value==="number"?Math.max(0,Math.min(value,100)):0;return <><div className="telemetry-head"><span>{typeof value==="number"?`${value.toFixed(1)}%`:"Yig‘ilmoqda"}</span></div><div className="progress"><span style={{width:`${safe}%`}}/></div></>; }

/** CSV eksport — brauzerda, serverga so'rovsiz.  Ro'yxat allaqachon
 *  yuklangan, `﻿` esa Excel'ni UTF-8 ga majbur qiladi (usiz
 *  o'zbekcha harflar buziladi). */
function exportSites(sites:Site[]) {
  const header = ["nomi","manzil","aloqa","kameralar_faol","kameralar_jami","tarif","kun_qoldi","oylik_narx"];
  const rows = sites.map(site=>[site.name,site.address||"",site.connection||"",site.cameras_active??"",site.cameras_expected??"",site.plan||"",site.days_left??"",site.monthly_price_uzs??""]);
  const csv = [header, ...rows].map(row=>row.map(cell=>`"${String(cell).replace(/"/g,'""')}"`).join(",")).join("\n");
  const url = URL.createObjectURL(new Blob([`﻿${csv}`],{type:"text/csv;charset=utf-8"}));
  const link = document.createElement("a"); link.href = url; link.download = "chaqimchi-mijozlar.csv"; link.click(); URL.revokeObjectURL(url);
}

const CONNECTION_LABEL:Record<string,string> = { online:"Aloqada", stale:"Eskirgan", not_paired:"Ulanmagan", offline:"Oflayn" };

function SiteTable({sites,onCreate,onOpen,searchable=false}:{sites:Site[];onCreate?:()=>void;onOpen?:(site:Site)=>void;searchable?:boolean}) {
  const [query,setQuery] = useState("");
  const [status,setStatus] = useState("");
  const [plan,setPlan] = useState("");

  const plans = useMemo(()=>[...new Set(sites.map(site=>site.plan).filter(Boolean))] as string[],[sites]);
  const shown = useMemo(()=>{
    const needle = query.trim().toLowerCase();
    return sites.filter(site=>{
      if (needle && !(`${site.name} ${site.address||""} ${site.id}`.toLowerCase().includes(needle))) return false;
      if (status && (site.connection||"") !== status) return false;
      if (plan && (site.plan||"") !== plan) return false;
      return true;
    });
  },[sites,query,status,plan]);

  return <Card>
    <div className="card-head">
      <div><h2>Mijoz tizimlari</h2><p>Aloqa, tarif va kamera holati</p></div>
      <div className="page-actions">
        {searchable ? <button className="btn" onClick={()=>exportSites(shown)}><Icon name="download"/>Eksport</button> : null}
        {onCreate?<button className="btn btn-primary" onClick={onCreate}><Icon name="branch"/>Yangi mijoz</button>:null}
      </div>
    </div>
    {searchable ? <div className="table-filters">
      <label className="table-search"><Icon name="search" size={16}/><input value={query} placeholder="Mijoz yoki filial bo‘yicha qidirish…" onChange={event=>setQuery(event.target.value)}/></label>
      <select className="select" value={status} onChange={event=>setStatus(event.target.value)} aria-label="Holat">
        <option value="">Holat: barchasi</option>
        {Object.entries(CONNECTION_LABEL).map(([key,label])=><option key={key} value={key}>{label}</option>)}
      </select>
      <select className="select" value={plan} onChange={event=>setPlan(event.target.value)} aria-label="Tarif">
        <option value="">Tarif: barchasi</option>
        {plans.map(item=><option key={item} value={item}>{item}</option>)}
      </select>
    </div> : null}
    {shown.length?<div className="table-wrap"><table>
      <thead><tr><th>Mijoz / filial</th><th>Aloqa</th><th>Kameralar</th><th>Tarif</th><th>To‘lov muddati</th>{onOpen?<th aria-label="Amallar"/>:null}</tr></thead>
      <tbody>{shown.map(site=><tr key={site.id}>
        <td><div className="table-name"><Avatar name={site.name}/><div><div className="table-title">{site.name}</div><div className="table-sub">{site.address||site.contact_phone||site.id}</div></div></div></td>
        <td><Pill state={site.connection}>{CONNECTION_LABEL[site.connection||""]||"Oflayn"}</Pill></td>
        <td>{formatNumber(site.cameras_active)} / {formatNumber(site.cameras_expected)}
          {site.cameras_expected ? <small className="table-sub">{Math.round(((site.cameras_active||0)*100)/site.cameras_expected)}%</small> : null}</td>
        <td>{site.plan||"—"}</td>
        <td>{site.days_left==null?"—":<Pill state={site.days_left<=7?"failed":"active"}>{site.days_left} kun</Pill>}</td>
        {onOpen?<td><ActionMenu items={[{label:"Kirish ma’lumoti yaratish",onSelect:()=>onOpen(site)}]}/></td>:null}
      </tr>)}</tbody>
    </table></div>:<EmptyState icon="branch" title={sites.length?"Filtrga mos mijoz yo‘q":"Mijozlar yo‘q"} detail={sites.length?"Qidiruv yoki filtrlarni bo‘shatib ko‘ring.":"Yangi mijoz qo‘shilgach uning tizim holati shu yerda ko‘rinadi."}/>}
  </Card>;
}

function Telemetry({items}:{items:DeviceMetric[]}) { return <Card><div className="card-head"><div><h2>Qurilma telemetriyasi</h2><p>Haqiqiy heartbeat ma’lumotlari; mavjud bo‘lmagan ko‘rsatkich yashirilmaydi</p></div><Pill>{items.length} qurilma</Pill></div>{items.length?<div className="telemetry-grid">{items.map(item=><article className="telemetry" key={`${item.site_id}-${item.device_id}`}><div className="health-name" style={{marginBottom:15}}><div className="metric-icon tone-blue" style={{position:"static"}}><Icon name="server" size={18}/></div><div><b>{item.label||item.device_id}</b><small>{item.site_name||item.site_id}</small></div></div><div className="simple-row"><span>CPU</span><b>{item.cpu_percent==null?"—":`${item.cpu_percent.toFixed(1)}%`}</b></div><Percent value={item.cpu_percent}/><div className="simple-row"><span>RAM</span><b>{item.ram_percent==null?"—":`${item.ram_percent.toFixed(1)}%`}</b></div><Percent value={item.ram_percent}/><div className="simple-row"><span>Disk</span><b>{item.disk_percent==null?"—":`${item.disk_percent.toFixed(1)}%`}</b></div><Percent value={item.disk_percent}/><div className="simple-row"><span>FPS</span><b>{item.fps==null?"—":item.fps.toFixed(1)}</b></div><div className="simple-row"><span>Inference</span><b>{item.inference_latency_ms==null?"—":`${item.inference_latency_ms.toFixed(0)} ms`}</b></div>{item.npu_percent==null?null:<div className="simple-row"><span>NPU</span><b>{item.npu_percent.toFixed(1)}%</b></div>}{item.temperature_c==null?null:<div className="simple-row"><span>Harorat</span><b className={item.temperature_c>=85?"is-hot":undefined}>{item.temperature_c.toFixed(0)}°C</b></div>}</article>)}</div>:<EmptyState icon="server" title="Telemetriya yig‘ilmoqda" detail="Yangi agent heartbeat yuborgach CPU, RAM, disk, FPS va inference kechikishi ko‘rinadi."/>}</Card>; }
function CustomersPage({sites,onRefresh}:{sites:Site[];onRefresh:()=>Promise<void>}) {
  const[adding,setAdding]=useState(false);const[busy,setBusy]=useState(false);const[error,setError]=useState("");const[created,setCreated]=useState<CreatedCustomer|null>(null);
  const submit=async(event:React.FormEvent<HTMLFormElement>)=>{event.preventDefault();const form=event.currentTarget;const values=new FormData(form);setBusy(true);setError("");setCreated(null);try{const site=await api<{site_id:string;name:string;pairing_code:string;pairing_expires_at?:string}>("/api/v1/admin/sites","admin",{method:"POST",body:JSON.stringify({name:String(values.get("name")||""),plan:String(values.get("plan")||"biznes"),subscription_months:Number(values.get("months")||1),contact_phone:String(values.get("phone")||"")||null,address:String(values.get("address")||"")||null})});const loginData=await api<{username:string;password:string}>(`/api/v1/admin/sites/${encodeURIComponent(site.site_id)}/login`,"admin",{method:"POST"});setCreated({...site,...loginData});form.reset();setAdding(false);await onRefresh();}catch(reason){setError(reason instanceof Error?reason.message:"Mijoz yaratilmadi");}finally{setBusy(false);}};
  const copyCredentials=()=>{if(!created)return;const text=`Chaqimchi AI\nPanel: ${window.location.origin}/owner\nLogin: ${created.username}\nParol: ${created.password}\nQurilma kodi: ${created.pairing_code}`;void navigator.clipboard?.writeText(text);};
  return <><PageHeader title="Mijozlar" subtitle="Yangi do‘kon, bir martalik kirish ma’lumoti va qurilma ulash kodi." actions={<button className="btn btn-primary" onClick={()=>setAdding(value=>!value)}><Icon name="users"/>{adding?"Bekor qilish":"Yangi mijoz"}</button>}/>{adding?<Card className="employee-form"><form className="card-body" onSubmit={submit}><div className="form-grid"><label>Do‘kon yoki kompaniya nomi<input className="input" name="name" minLength={2} required/></label><label>Tarif<select className="select" name="plan" defaultValue="biznes"><option value="boshlangich">Boshlang‘ich</option><option value="biznes">Biznes</option></select></label><label>Telefon<input className="input" name="phone" inputMode="tel" placeholder="+998…"/></label><label>Manzil<input className="input" name="address"/></label><label>Obuna muddati<select className="select" name="months" defaultValue="1"><option value="1">1 oy</option><option value="3">3 oy</option><option value="6">6 oy</option><option value="12">12 oy</option></select></label></div><button className="btn btn-primary" disabled={busy}>{busy?"Yaratilmoqda…":"Mijoz va login yaratish"}</button></form></Card>:null}{error?<div className="alert-strip"><Icon name="bell"/><div><strong>Amal bajarilmadi:</strong> {error}</div></div>:null}{created?<Card className="credential-card"><div className="card-head"><div><h2>Kirish ma’lumoti tayyor</h2><p>Parol faqat shu safar ko‘rinadi — xavfsiz tarzda mijozga yuboring</p></div><Pill state="active">Yaratildi</Pill></div><div className="credential-grid"><div><span>Panel</span><b>{window.location.origin}/owner</b></div><div><span>Login</span><b>{created.username}</b></div><div><span>Bir martalik parol</span><b>{created.password}</b></div><div><span>Qurilma ulash kodi</span><b>{created.pairing_code}</b></div></div><div className="card-body"><button className="btn btn-primary" onClick={copyCredentials}>Hammasini nusxalash</button></div></Card>:null}<div className="section-gap"><SiteTable sites={sites} onCreate={()=>setAdding(true)} searchable/></div></>;
}

function PaymentsPage() {
  const[items,setItems]=useState<AdminInvoice[]|null>(null);const[error,setError]=useState("");const[busy,setBusy]=useState("");
  const load=useCallback(()=>api<AdminInvoice[]>("/api/v1/admin/invoices","admin").then(data=>{setItems(data);setError("");}).catch(reason=>setError(reason instanceof Error?reason.message:"To‘lovlar olinmadi")),[]);
  useEffect(()=>{void load();},[load]);
  const approve=async(invoice:AdminInvoice)=>{if(!window.confirm(`#${invoice.id} hisobini qo‘lda to‘langan deb tasdiqlaysizmi? Obuna uzayadi.`))return;setBusy(invoice.id);setError("");try{await api(`/api/v1/admin/invoices/${encodeURIComponent(invoice.id)}/paid`,"admin",{method:"POST",body:JSON.stringify({provider:"manual",reference:null})});await load();}catch(reason){setError(reason instanceof Error?reason.message:"To‘lov tasdiqlanmadi");}finally{setBusy("");}};
  return <><PageHeader title="To‘lovlar" subtitle="Hisob-faktura va operator tasdig‘idagi real obuna jarayoni."/>{error?<div className="alert-strip"><Icon name="bell"/><div><strong>To‘lov bilan muammo:</strong> {error}</div></div>:null}<Card><div className="card-head"><div><h2>Hisob-fakturalar</h2><p>Tasdiqlash obuna muddatini avtomatik uzaytiradi</p></div></div>{items===null?<div className="card-body"><Skeleton height={180}/></div>:items.length?<div className="table-wrap"><table><thead><tr><th>Mijoz</th><th>Hisob</th><th>Muddat</th><th>Summa</th><th>Holat</th><th>Amal</th></tr></thead><tbody>{items.map(invoice=><tr key={invoice.id}><td><div className="table-title">{invoice.site_name||invoice.site_id}</div></td><td>#{invoice.id}</td><td>{invoice.months} oy</td><td>{formatMoney(invoice.amount_uzs,{short:false})}</td><td><Pill state={invoice.state}>{invoice.state==="paid"?"To‘langan":invoice.state==="pending"?"Kutilmoqda":"Bekor"}</Pill></td><td>{invoice.state==="pending"?<button className="btn btn-primary" disabled={busy===invoice.id} onClick={()=>void approve(invoice)}>{busy===invoice.id?"Tasdiqlanmoqda…":"To‘lovni tasdiqlash"}</button>:invoice.provider||"—"}</td></tr>)}</tbody></table></div>:<EmptyState icon="invoice" title="Hisob-faktura yo‘q" detail="Mijoz hisob yaratgach u shu ro‘yxatda ko‘rinadi."/>}</Card></>;
}

function PlansPage() {
  const[data,setData]=useState<{price_book?:{label?:string;usd_rate_uzs?:number;base_fee_usd_cents?:number};features:Feature[]}|null>(null);const[error,setError]=useState("");
  useEffect(()=>{api<{price_book?:{label?:string;usd_rate_uzs?:number;base_fee_usd_cents?:number};features:Feature[]}>("/api/v1/admin/features","admin").then(setData).catch(reason=>setError(reason instanceof Error?reason.message:"Katalog olinmadi"));},[]);
  return <><PageHeader title="Tariflar" subtitle="Versiyalangan narx katalogi; qo‘lda yozilgan soxta qiymat ko‘rsatilmaydi."/>{error?<div className="alert-strip"><Icon name="bell"/>{error}</div>:null}{data?<><div className="metric-grid"><MetricCard label="Faol katalog" value={data.price_book?.label||"—"} note="Serverdagi nashr" icon="card"/><MetricCard label="AI funksiyalar" value={formatNumber(data.features.length)} note="Katalogdagi imkoniyatlar" icon="pulse"/><MetricCard label="USD kursi" value={formatMoney(data.price_book?.usd_rate_uzs)} note="Hisoblash manbasi" icon="chart"/><MetricCard label="Platforma bazasi" value={data.price_book?.base_fee_usd_cents==null?"—":`$${(data.price_book.base_fee_usd_cents/100).toFixed(0)}`} note="Oylik bazaviy haq" icon="server"/></div><Card><div className="card-head"><div><h2>Funksiyalar katalogi</h2><p>Bir kamera uchun oylik qiymat</p></div></div><div className="table-wrap"><table><thead><tr><th>Funksiya</th><th>Tur</th><th>Mijoz narxi</th><th>Ichki qiymat</th></tr></thead><tbody>{data.features.map(feature=><tr key={feature.code}><td><div className="table-title">{feature.name}</div><div className="table-sub">{feature.code}</div></td><td>{feature.category}</td><td>${(feature.monthly_usd_cents/100).toFixed(2)}</td><td>${(feature.cost_usd_cents/100).toFixed(2)}</td></tr>)}</tbody></table></div></Card></>:<Card><div className="card-body"><Skeleton height={190}/></div></Card>}</>;
}

/* Moliya: platforma va HAR MIJOZ nechchiga tushayapti.  Gemini xarajati
   haqiqiy token sarfidan (usageMetadata), infra env'dagi summalardan —
   sahifada qo'lda yozilgan raqam yo'q. */
type FinanceSite = {site_id:string;name?:string;plan?:string;billable:boolean;revenue_uzs:number;gemini_jobs:number;gemini_untracked_jobs:number;gemini_input_tokens:number;gemini_output_tokens:number;gemini_cost_uzs:number;shared_cost_uzs:number;total_cost_uzs:number;margin_uzs:number};
type Finance = {
  month:string; usd_rate_uzs:number;
  fixed:{server_monthly_usd:number;server_monthly_uzs:number;server_configured:boolean;domain_yearly_uzs:number;domain_monthly_uzs:number;total_monthly_uzs:number;split_between:number;share_per_site_uzs:number};
  gemini:{jobs:number;untracked_jobs:number;input_tokens:number;output_tokens:number;cost_uzs:number;input_usd_per_m:number;output_usd_per_m:number;model?:string|null};
  sites:FinanceSite[];
  totals:{revenue_uzs:number;cost_uzs:number;margin_uzs:number};
};

function financeMonths():string[] {
  const now=new Date();
  return Array.from({length:6},(_,back)=>{const d=new Date(now.getFullYear(),now.getMonth()-back,1);return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}`;});
}

function FinancePage() {
  const [month,setMonth]=useState("");
  const [data,setData]=useState<Finance|null>(null);
  const [error,setError]=useState("");
  useEffect(()=>{let stopped=false;setData(null);api<Finance>(`/api/v1/admin/finance${month?`?month=${month}`:""}`,"admin").then(next=>{if(!stopped){setData(next);setError("");}}).catch(reason=>{if(!stopped)setError(reason instanceof Error?reason.message:"Moliya olinmadi");});return()=>{stopped=true;};},[month]);
  const t=(n:number)=>Number(n||0).toLocaleString("ru-RU");
  if(error) return <><PageHeader title="Moliya" subtitle="Xarajat va daromad hisobi."/><Card><EmptyState icon="bell" title="Ma’lumot olinmadi" detail={error}/></Card></>;
  if(!data) return <><PageHeader title="Moliya" subtitle="Xarajat va daromad hisobi."/><Card><div className="card-body"><Skeleton height={190}/></div></Card></>;
  const {fixed,gemini,totals}=data;
  return <>
    <PageHeader title="Moliya" subtitle={`${data.month} · kurs 1 $ = ${formatMoney(data.usd_rate_uzs)}`} actions={<select className="select" value={month||data.month} onChange={event=>setMonth(event.target.value)} aria-label="Oy">{financeMonths().map(m=><option key={m} value={m}>{m}</option>)}</select>}/>
    {!fixed.server_configured?<div className="alert-strip alert-warning"><Icon name="bell"/><div><strong>Server narxi kiritilmagan.</strong> Contabo oylik summasini serverdagi .env.production ga CHAQIMCHI_COST_SERVER_MONTHLY_USD qilib yozing.</div></div>:null}
    <div className="metric-grid">
      <MetricCard label="Oylik xarajat (jami)" value={formatMoney(totals.cost_uzs)} note="infra + Gemini" icon="invoice" tone="red"/>
      <MetricCard label="Oylik daromad" value={formatMoney(totals.revenue_uzs)} note="faol mijoz tariflari" icon="card" tone="green"/>
      <MetricCard label="Marja" value={formatMoney(totals.margin_uzs)} note="daromad − xarajat" icon="chart" tone={totals.margin_uzs>=0?"green":"red"}/>
      <MetricCard label={`Gemini (${data.month})`} value={formatMoney(gemini.cost_uzs)} note={`${gemini.jobs} ta savol`} icon="pulse" tone="blue"/>
    </div>
    <div className="dashboard-grid section-gap">
      <Card><div className="card-head"><div><h2>Doimiy xarajatlar</h2><p>Ulangan do‘konlar orasida teng bo‘linadi</p></div></div><div className="card-body">
        <div className="simple-row"><span>Server (Contabo)</span><b>{fixed.server_configured?`$${fixed.server_monthly_usd} ≈ ${formatMoney(fixed.server_monthly_uzs)}`:"kiritilmagan"}</b></div>
        <div className="simple-row"><span>Domen</span><b>{formatMoney(fixed.domain_yearly_uzs)}/yil ≈ {formatMoney(fixed.domain_monthly_uzs)}/oy</b></div>
        <div className="simple-row"><span>Jami oyiga</span><b>{formatMoney(fixed.total_monthly_uzs)}</b></div>
        <div className="simple-row"><span>Bo‘linish</span><b>{fixed.split_between} do‘kon · {formatMoney(fixed.share_per_site_uzs)} dan</b></div>
      </div></Card>
      <Card><div className="card-head"><div><h2>Gemini (AI yordamchi)</h2><p>Token sarfi Google javobidan — taxmin emas</p></div></div><div className="card-body">
        <div className="simple-row"><span>Model</span><b>{gemini.model||"sozlanmagan"}</b></div>
        <div className="simple-row"><span>Savollar</span><b>{gemini.jobs} ta{gemini.untracked_jobs?` (${gemini.untracked_jobs} kuzatilmagan)`:""}</b></div>
        <div className="simple-row"><span>Tokenlar</span><b>{t(gemini.input_tokens)} kirish · {t(gemini.output_tokens)} chiqish</b></div>
        <div className="simple-row"><span>Tarif</span><b>${gemini.input_usd_per_m}/1M · ${gemini.output_usd_per_m}/1M</b></div>
      </div></Card>
    </div>
    <Card className="section-gap"><div className="card-head"><div><h2>Har mijoz nechchiga tushyapti</h2><p>Infra ulushi + o‘z Gemini sarfi; marja = tarif − xarajat</p></div></div>
      {data.sites.length?<div className="table-wrap"><table>
        <thead><tr><th>Mijoz</th><th>Tarif (daromad)</th><th>Gemini</th><th>Tokenlar</th><th>Gemini xarajat</th><th>Infra ulushi</th><th>Jami xarajat</th><th>Marja</th></tr></thead>
        <tbody>{data.sites.map(s=><tr key={s.site_id}>
          <td><div className="table-title">{s.name||s.site_id}</div><div className="table-sub">{s.plan||"—"}{s.billable?"":" · qurilma ulanmagan"}</div></td>
          <td>{s.billable?formatMoney(s.revenue_uzs):"—"}</td>
          <td>{s.gemini_jobs}{s.gemini_untracked_jobs?<small className="table-sub"> ({s.gemini_untracked_jobs})</small>:null}</td>
          <td><small>{t(s.gemini_input_tokens)} / {t(s.gemini_output_tokens)}</small></td>
          <td>{formatMoney(s.gemini_cost_uzs)}</td>
          <td>{s.billable?formatMoney(s.shared_cost_uzs):"—"}</td>
          <td><b>{formatMoney(s.total_cost_uzs)}</b></td>
          <td><Pill state={s.margin_uzs>=0?"active":"failed"}>{formatMoney(s.margin_uzs)}</Pill></td>
        </tr>)}</tbody>
      </table></div>:<EmptyState icon="branch" title="Mijoz yo‘q" detail="Mijoz qo‘shilgach xarajat taqsimoti shu yerda ko‘rinadi."/>}
    </Card>
  </>;
}

function RolesPage() {
  const[accounts,setAccounts]=useState<Account[]|null>(null);const[error,setError]=useState("");
  useEffect(()=>{api<{accounts:Account[]}>("/api/v1/admin/accounts","admin").then(data=>setAccounts(data.accounts)).catch(reason=>setError(reason instanceof Error?reason.message:"Akkauntlar olinmadi"));},[]);
  return <><PageHeader title="Rollar" subtitle="Admin, o‘rnatuvchi va mijoz akkauntlarining haqiqiy ruxsat holati."/>{error?<div className="alert-strip"><Icon name="bell"/>{error}</div>:null}<Card>{accounts===null?<div className="card-body"><Skeleton height={180}/></div>:accounts.length?<div className="table-wrap"><table><thead><tr><th>Foydalanuvchi</th><th>Login</th><th>Rol</th><th>Holat</th><th>Filial</th></tr></thead><tbody>{accounts.map(account=><tr key={account.id}><td><div className="table-title">{account.full_name||account.company||"—"}</div></td><td>{account.username}</td><td>{account.role}</td><td><Pill state={account.status}>{account.status}</Pill></td><td>{account.site_id||"Platforma"}</td></tr>)}</tbody></table></div>:<EmptyState icon="shield" title="Akkaunt yo‘q" detail="Akkaunt yaratilgach rol va holati shu yerda ko‘rinadi."/>}</Card></>;
}

function SettingsPage() {
  const[data,setData]=useState<{items?:ReadinessItem[]}|null>(null);const[error,setError]=useState("");
  useEffect(()=>{api<{items?:ReadinessItem[]}>("/api/v1/admin/readiness","admin").then(setData).catch(reason=>setError(reason instanceof Error?reason.message:"Readiness olinmadi"));},[]);
  const items=data?.items||[];
  return <><PageHeader title="Sozlamalar" subtitle="Ishlab chiqarish integratsiyalari va xavfsizlik tayyorligi."/>{error?<div className="alert-strip"><Icon name="bell"/>{error}</div>:null}<Card><div className="card-head"><div><h2>Production readiness</h2><p>Yashirilmagan real muhit tekshiruvlari</p></div></div>{data?<div className="health-list">{items.map(item=><div className="health-row" key={item.key}><div className="health-name"><span className={`status-dot status-${item.ok?"online":item.required?"offline":"stale"}`}/><div><b>{item.label}</b><small>{item.reasons?.join(" · ")|| (item.required?"Majburiy tekshiruv":"Ixtiyoriy tekshiruv")}</small></div></div><Pill state={item.ok?"active":item.required?"failed":"pending"}>{item.ok?"Tayyor":item.required?"Tayyor emas":"Ixtiyoriy"}</Pill></div>)}</div>:<div className="card-body"><Skeleton height={190}/></div>}</Card></>;
}

function VisionAgentPage({sites}:{sites:Site[]}) {
  const [siteId,setSiteId]=useState(""); const [question,setQuestion]=useState(""); const [settings,setSettings]=useState<{consented:boolean;provider_configured:boolean}|null>(null); const [settingsError,setSettingsError]=useState(""); const [result,setResult]=useState<{status:string;result?:{answer?:string;sources?:Array<{event_id:string;label?:string;occurred_at?:string}>};error?:string}|null>(null); const timer=useRef(0);
  useEffect(()=>{setSiteId(current=>current||sites[0]?.id||"");},[sites]);
  /* Sozlama xatosi ham KO'RSATILADI — avval `.catch(()=>setSettings(null))`
     jim yutar va admin sababsiz o'chirilgan tugma qarshisida qolardi. */
  useEffect(()=>{if(!siteId)return;setSettings(null);setSettingsError("");api<{consented:boolean;provider_configured:boolean}>(`/api/v1/admin/sites/${encodeURIComponent(siteId)}/agent/settings`,"admin").then(next=>{setSettings(next);setSettingsError("");}).catch(reason=>{setSettings(null);setSettingsError(reason instanceof Error?reason.message:"Sozlama olinmadi");});},[siteId]);
  useEffect(()=>()=>window.clearTimeout(timer.current),[]);
  const poll=useCallback(async(id:string,ticks=0,fails=0)=>{try{const job=await api<{status:string;result?:{answer?:string;sources?:Array<{event_id:string;label?:string;occurred_at?:string}>};error?:string}>(`/api/v1/admin/sites/${encodeURIComponent(siteId)}/agent/jobs/${encodeURIComponent(id)}`,"admin");if(job.status==="queued"||job.status==="running"){if(ticks>=130){setResult({status:"failed",error:"Javob cho‘zilib ketdi — worker holatini tekshiring."});return;}setResult(job);timer.current=window.setTimeout(()=>void poll(id,ticks+1,0),1800);return;}setResult(job);}catch(reason){if(fails>=4){setResult({status:"failed",error:reason instanceof Error?reason.message:"Javob olinmadi"});return;}timer.current=window.setTimeout(()=>void poll(id,ticks+1,fails+1),3000);}},[siteId]);
  const ask=async()=>{if(!question.trim()||!siteId)return;setResult({status:"queued"});try{const job=await api<{job_id:string}>(`/api/v1/admin/sites/${encodeURIComponent(siteId)}/agent/queries`,"admin",{method:"POST",body:JSON.stringify({message:question.trim()})});void poll(job.job_id);}catch(reason){setResult({status:"failed",error:reason instanceof Error?reason.message:"Savol yuborilmadi"});}};
  return <><PageHeader title="Vision Agent" subtitle="Tanlangan filialning eventlari bo‘yicha dalilli Uzbek javob."/><Card><div className="card-body agent-composer"><select className="select" value={siteId} onChange={event=>setSiteId(event.target.value)} aria-label="Filial">{sites.map(site=><option key={site.id} value={site.id}>{site.name}</option>)}</select>{settingsError?<div className="alert-strip"><Icon name="bell"/>Sozlama olinmadi: {settingsError}</div>:null}{settings&&!settings.provider_configured?<div className="alert-strip alert-warning"><Icon name="bell"/>Gemini provideri sozlanmagan (CHAQIMCHI_GEMINI_API_KEY / CHAQIMCHI_GEMINI_VISION_MODEL) — savollar ishlamaydi.</div>:null}{settings&&!settings.consented?<div className="alert-strip alert-info"><Icon name="shield"/>Bu filial egasi hali Agent roziligini bermagan.</div>:null}<textarea className="input" rows={4} value={question} onChange={event=>setQuestion(event.target.value)} placeholder="Masalan: kecha kassa yonida navbat bo‘ldimi?"/><button className="btn btn-primary" disabled={!settings?.consented||!settings?.provider_configured||result?.status==="queued"||result?.status==="running"} onClick={()=>void ask()}>{result?.status==="queued"||result?.status==="running"?"Tekshirilmoqda…":"Savol berish"}</button></div></Card>{result?.status==="completed"?<Card className="section-gap"><div className="card-body"><p className="agent-answer">{result.result?.answer}</p>{result.result?.sources?.map(source=><div className="simple-row" key={source.event_id}><b>{source.label||"Hodisa"}</b><span>{source.occurred_at||"—"}</span></div>)}</div></Card>:null}{result?.status==="failed"?<Card className="section-gap"><EmptyState icon="bell" title="Agent xatosi" detail={result.error||"Qayta urinib ko‘ring."}/></Card>:null}</>;
}

function GenericAdmin({id,data,onRefresh}:{id:string;data:AdminDashboard;onRefresh:()=>Promise<void>}) {
  if(id==="customers") return <CustomersPage sites={data.sites} onRefresh={onRefresh}/>;
  if(id==="branches") return <><PageHeader title="Filiallar" subtitle="Obuna va tizim holatini bitta ro‘yxatdan boshqaring."/><SiteTable sites={data.sites} searchable/></>;
  if(id==="devices"||id==="monitoring") return <><PageHeader title={id==="devices"?"Qurilmalar":"Monitoring"} subtitle="Sotqin agentlari va haqiqiy resurs ko‘rsatkichlari."/><Telemetry items={data.telemetry}/></>;
  if(id==="cameras") return <><PageHeader title="Kameralar" subtitle="Filiallar bo‘yicha ishlayotgan va e’tibor talab qiladigan kameralar."/><div className="metric-grid">{data.sites.map(site=><MetricCard key={site.id} label={site.name} value={`${formatNumber(site.cameras_active)} / ${formatNumber(site.cameras_expected)}`} note={site.connection||"—"} icon="camera" tone={(site.cameras_active||0)>=(site.cameras_expected||1)?"green":"red"}/>)}</div></>;
  if(id==="plans") return <PlansPage/>;
  if(id==="payments") return <PaymentsPage/>;
  if(id==="finance") return <FinancePage/>;
  if(id==="events") return <EventEvidence kind="admin" sites={data.sites}/>;
  if(id==="agent") return <VisionAgentPage sites={data.sites}/>;
  if(id==="roles") return <RolesPage/>;
  if(id==="settings") return <SettingsPage/>;
  return <><PageHeader title="Bo‘lim" subtitle="Operatsion boshqaruv."/><Card><EmptyState icon="settings" title="Ma’lumot yo‘q" detail="Haqiqiy ma’lumot kelgach shu yerda ko‘rinadi."/></Card></>;
}

function AdminApp() {
  const [authenticated,setAuthenticated] = useState(()=>Boolean(tokenFor("admin")));
  const [active,navigateTo] = usePanelRoute("/admin", ROUTE_IDS, "overview");
  const [range,setRange] = useState("7d");
  const [busy,setBusy] = useState(false);
  const [loginError,setLoginError] = useState("");
  const [drawer,setDrawer] = useState(false);
  const {data,loading,error,refresh} = useAdminDashboard(authenticated,range);

  const submit = async(username:string,password:string)=>{setBusy(true);setLoginError("");try{await login(username,password,"admin");setAuthenticated(true);}catch(reason){setLoginError(reason instanceof Error?reason.message:"Kirish amalga oshmadi");}finally{setBusy(false);}};
  const logout = ()=>{clearToken("admin");setAuthenticated(false);};
  const navigate = (id:string)=>{if(id==="more")setDrawer(true);else{navigateTo(id);setDrawer(false);window.scrollTo({top:0,behavior:"smooth"});}};

  const offline = data?.stats.offline || 0;
  const notPaired = data?.stats.not_paired || 0;
  const attention = offline + notPaired;

  /* ⌘K uchun ro'yxat: bo'limlar + mijozlar.  Mijozni tanlash uni
     filtrlash uchun emas, mijozlar sahifasiga olib boradi — u yerda
     qidiruv maydoni bor. */
  const searchEntries = useMemo(()=>[
    ...NAV.map(item=>({ id:`nav-${item.id}`, label:item.label, hint:"Bo‘lim", onSelect:()=>navigate(item.id) })),
    ...(data?.sites || []).map(site=>({ id:`site-${site.id}`, label:site.name, hint:site.address||"Mijoz", onSelect:()=>navigate("customers") })),
  ],[data?.sites]);

  if(!authenticated) return <LoginScreen kind="admin" onSubmit={submit} busy={busy} error={loginError}/>;
  if(loading&&!data) return <div className="login-page"><section className="login-visual"><Logo/><div><span className="eyebrow">ADMIN PANEL</span><h1>Platforma holati olinmoqda.</h1></div></section><section className="login-panel"><div style={{width:"min(390px,100%)"}}><Skeleton height={60}/><div style={{height:14}}/><Skeleton height={180}/></div></section></div>;
  /* Server javob bermasa — sabab va qayta urinish.  Avval bu holat ham
     "olinmoqda" skeletida abadiy qolardi. */
  if(!data) return <div className="login-page"><section className="login-visual"><Logo/><div><span className="eyebrow">ADMIN PANEL</span><h1>Ma’lumot ochilmadi</h1></div></section><section className="login-panel"><div style={{width:"min(390px,100%)"}}><p className="metric-note">{error||"Server bilan aloqa bo‘lmadi."}</p><div className="page-actions" style={{marginTop:14}}><button className="btn btn-primary" onClick={()=>void refresh()}>Qayta urinish</button><button className="btn" onClick={logout}>Chiqish</button></div></div></section></div>;

  const today = formatDateUz();
  return <AppShell
    nav={NAV}
    mobileNav={MOBILE_NAV}
    active={active}
    onNavigate={navigate}
    title="Platforma boshqaruvi"
    subtitle={`Yangilandi: ${new Date(data.updated_at).toLocaleTimeString("uz-UZ",{hour:"2-digit",minute:"2-digit"})}`}
    onLogout={logout}
    sidebarFooter={<div className="sidebar-user"><Icon name="shield"/><div><b>Chaqimchi Cloud</b><small>Admin panel</small></div></div>}
    headerActions={<>
      <SearchPalette entries={searchEntries} placeholder="Mijoz yoki bo‘lim…"/>
      <span className={`status-chip ${attention ? "is-warn" : "is-ok"}`}><i/>{attention ? `${attention} ta e’tibor talab` : "Tizim barqaror"}</span>
      <span className="topbar-date"><Icon name="calendar" size={16}/>{today}</span>
      <select className="select" value={range} onChange={event=>setRange(event.target.value)} aria-label="Davr"><option value="7d">7 kun</option><option value="30d">30 kun</option></select>
      <button className="btn btn-icon" onClick={()=>void refresh()} aria-label="Yangilash"><Icon name="pulse"/></button>
    </>}>
    {error?<div className="alert-strip"><Icon name="bell"/><div><strong>Yangilashda muammo:</strong> {error}. Oxirgi ma’lumot ko‘rsatilmoqda.</div></div>:null}
    {active==="overview"
      ? <><PageHeader title="Platforma boshqaruvi" subtitle={today} actions={<button className="btn btn-primary" onClick={()=>navigate("customers")}><Icon name="users"/>Mijoz qo‘shish</button>}/><AdminHome data={data} onNavigate={navigate}/></>
      : <GenericAdmin id={active} data={data} onRefresh={refresh}/>}
    {drawer?<div className="drawer-backdrop" onClick={()=>setDrawer(false)}><aside className="drawer" onClick={event=>event.stopPropagation()}><div className="drawer-head"><Logo/><button className="btn btn-icon" onClick={()=>setDrawer(false)}><Icon name="close"/></button></div><nav>{NAV.map(item=><button key={item.id} className={active===item.id?"active":""} onClick={()=>navigate(item.id)}><Icon name={item.icon}/>{item.label}</button>)}</nav></aside></div>:null}
  </AppShell>;
}

createRoot(document.getElementById("root")!).render(<StrictMode><AdminApp/></StrictMode>);
