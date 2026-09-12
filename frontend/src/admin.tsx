import { StrictMode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { api, logout as serverLogout, copyText, downloadCsv, formatDateShort, formatDateUz, formatMoney, formatNumber, login, tokenFor } from "./api";
import { t } from "./i18n";
import { ActionMenu, AppShell, Avatar, Card, CopyField, EmptyState, ErrorStrip, LoginScreen, StatCard, Modal, PageHeader, Pill, SearchPalette, Skeleton, useConfirm, useToast, type NavItem } from "./components";
import { AdminHome } from "./AdminHome";
import { AdminCustomer } from "./AdminCustomer";
import { AdminTeam } from "./AdminTeam";
import { AdminSettings } from "./AdminSettings";
import type { Lead } from "./types";
import { EventEvidence } from "./EventEvidence";
import { usePanelRoute } from "./router";
import { Icon, Logo } from "./icons";
import { initLang } from "./i18n";
import { applyTheme, readTheme } from "./theme";
import "./styles.css";

type Site = { id:string; name:string; address?:string; contact_phone?:string; plan?:string; license_status?:string; connection?:string; devices?:number; cameras_active?:number; cameras_expected?:number; days_left?:number; monthly_price_uzs?:number; last_seen?:string };
type DeviceMetric = { device_id:string; site_id:string; site_name?:string; label?:string; received_at?:string; cpu_percent?:number|null; ram_percent?:number|null; disk_percent?:number|null; fps?:number|null; inference_latency_ms?:number|null; uptime_sec?:number|null; npu_percent?:number|null; temperature_c?:number|null };
type CreatedCustomer = {site_id:string;name:string;pairing_code:string;pairing_expires_at?:string;username:string;password:string};
type AdminInvoice = {id:string;site_name?:string;site_id:string;months:number;amount_uzs:number;state:string;provider?:string;created_at?:string;paid_at?:string;payme_url?:string;click_url?:string};
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

/* Bo'limlar ro'yxati.  Tarjimali yorliq matn emas, katalog KALITI —
   `owner.tsx: NAV_ITEMS` bilan bir xil sabab: modul yuklanganda til
   hali tanlanmagan (`initLang()` fayl oxirida chaqiriladi), ya'ni bu
   yerda `t()` ishlatilsa yorliq doim o'zbekcha qolardi.  `leads` aynan
   shunday qotib qolgan edi.  Matn `AdminApp` ichida, chizish paytida
   ochiladi. */
const NAV_ITEMS:Array<{id:string;key:string;icon:string}> = [
  {id:"overview",key:"panel.admin.nav.overview",icon:"home"},
  {id:"customers",key:"panel.admin.nav.customers",icon:"users"},
  {id:"leads",key:"panel.nav.leads",icon:"invoice"},
  {id:"branches",key:"panel.nav.branches",icon:"branch"},
  {id:"cameras",key:"panel.nav.cameras",icon:"camera"},
  {id:"plans",key:"panel.admin.nav.plans",icon:"card"},
  {id:"payments",key:"panel.admin.nav.payments",icon:"invoice"},
  {id:"finance",key:"panel.admin.nav.finance",icon:"chart"},
  {id:"events",key:"panel.admin.nav.events",icon:"pulse"},
  {id:"agent",key:"panel.admin.nav.agent",icon:"pulse"},
  {id:"monitoring",key:"panel.admin.nav.monitoring",icon:"chart"},
  {id:"team",key:"panel.admin.nav.team",icon:"shield"},
  {id:"settings",key:"panel.nav.settings",icon:"settings"},
];

const ROUTE_IDS = NAV_ITEMS.map(item=>item.id);

/* Eski bo'lim nomi → yangi bo'lim.  «Qurilmalar» va «Monitoring» AYNAN
   bir sahifani chizardi (`<Telemetry/>`) va menyuda ikki qator
   egallardi — admin qaysi biriga bosishini har safar o'ylardi.
   Manzil yo'naltiriladi, ya'ni eski xatcho'q ishlaydi. */
const LEGACY_ROUTES = { devices: ["monitoring", ""] } as const;
const MOBILE_NAV = ["overview","customers","payments","monitoring"];

function useAdminDashboard(authenticated:boolean, range:string) {
  const [data,setData] = useState<AdminDashboard|null>(null); const [loading,setLoading] = useState(true); const [error,setError] = useState(""); const failures=useRef(0);
  const refresh = useCallback(async()=>{ if(!authenticated)return;try{const next=await api<AdminDashboard>(`/api/v1/admin/dashboard?range=${range}`,"admin");setData(next);setError("");failures.current=0;}catch(reason){failures.current+=1;setError(reason instanceof Error?reason.message:t("panel.admin.load_failed"));}finally{setLoading(false);}},[authenticated,range]);
  useEffect(()=>{let timer=0,stopped=false;const tick=async()=>{await refresh();if(!stopped)timer=window.setTimeout(tick,document.hidden?60_000:failures.current?30_000:15_000);};void tick();return()=>{stopped=true;window.clearTimeout(timer);};},[refresh]);
  return {data,loading,error,refresh};
}

export function Percent({value}:{value:number|null|undefined}) { const safe=typeof value==="number"?Math.max(0,Math.min(value,100)):0;return <><div className="telemetry-head"><span>{typeof value==="number"?`${value.toFixed(1)}%`:t("panel.admin.collecting")}</span></div><div className="progress"><span style={{width:`${safe}%`}}/></div></>; }

/** CSV eksport — brauzerda, serverga so'rovsiz.  Ro'yxat allaqachon
 *  yuklangan, `﻿` esa Excel'ni UTF-8 ga majbur qiladi (usiz
 *  o'zbekcha harflar buziladi). */
function exportSites(sites:Site[]) {
  const header = ["col_name","col_address","col_connection","col_cameras_active","col_cameras_total","col_plan","col_days_left","col_monthly_price"].map(name=>t(`panel.admin.export.${name}`));
  const rows = sites.map(site=>[site.name,site.address||"",site.connection||"",site.cameras_active??"",site.cameras_expected??"",site.plan||"",site.days_left??"",site.monthly_price_uzs??""]);
  const csv = [header, ...rows].map(row=>row.map(cell=>`"${String(cell).replace(/"/g,'""')}"`).join(",")).join("\n");
  downloadCsv(csv, `${t("panel.admin.export.filename")}.csv`);
}

/* Yorliq matn emas, katalog KALITI — `NAV_ITEMS` bilan bir xil sabab.
   Ro'yxat menyuda ham, jadvalda ham, filtrda ham ishlatiladi. */
const CONNECTION_KEY:Record<string,string> = { online:"panel.admin.conn.online", stale:"panel.admin.conn.stale", not_paired:"panel.admin.conn.not_paired", offline:"panel.admin.conn.offline" };

function SiteTable({sites,onCreate,onOpen,searchable=false}:{sites:Site[];onCreate?:()=>void;onOpen?:(site:Site)=>void;searchable?:boolean}) {
  /* Javobsiz tugma buzuq tugmadan farq qilmaydi: bo'sh ro'yxatni
     eksport qilsa faqat sarlavhali fayl tushardi. */
  const[toast,toastNode]=useToast();
  /* `onOpen` — mijoz tafsilot sahifasi (`/admin/customers/<id>`): qurilma,
     kamera, diagnostika, funksiya biriktirish, login, hisob.  Eski
     admindagi «Mijozlar → karta» yo'li. */
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
    {toastNode}
    <div className="card-head">
      <div><h2>{t("panel.admin.sites.title")}</h2><p>{t("panel.admin.sites.subtitle")}</p></div>
      <div className="page-actions">
        {searchable ? <button className="btn" onClick={()=>{if(!shown.length){toast(t("panel.admin.sites.export_empty"),false);return;}exportSites(shown);toast(t("panel.admin.sites.exported",{count:shown.length}));}}><Icon name="download"/>{t("panel.admin.sites.export")}</button> : null}
        {onCreate?<button className="btn btn-primary" onClick={onCreate}><Icon name="branch"/>{t("panel.admin.customers.new")}</button>:null}
      </div>
    </div>
    {searchable ? <div className="table-filters">
      <label className="table-search"><Icon name="search" size={16}/><input value={query} placeholder={t("panel.admin.sites.search")} onChange={event=>setQuery(event.target.value)}/></label>
      <select className="select" value={status} onChange={event=>setStatus(event.target.value)} aria-label={t("panel.admin.col_status")}>
        <option value="">{t("panel.admin.sites.status_all")}</option>
        {Object.entries(CONNECTION_KEY).map(([code,key])=><option key={code} value={code}>{t(key)}</option>)}
      </select>
      <select className="select" value={plan} onChange={event=>setPlan(event.target.value)} aria-label={t("panel.admin.col_plan")}>
        <option value="">{t("panel.admin.sites.plan_all")}</option>
        {plans.map(item=><option key={item} value={item}>{item}</option>)}
      </select>
    </div> : null}
    {shown.length?<div className="table-wrap"><table>
      <thead><tr><th>{t("panel.admin.sites.col_site")}</th><th>{t("panel.admin.sites.col_connection")}</th><th>{t("panel.admin.sites.col_cameras")}</th><th>{t("panel.admin.col_plan")}</th><th>{t("panel.admin.sites.col_due")}</th>{onOpen?<th aria-label={t("panel.shell.actions")}/>:null}</tr></thead>
      <tbody>{shown.map(site=><tr key={site.id} className={onOpen?"row-link":""}>
        <td><div className="table-name"><Avatar name={site.name}/><div><div className="table-title">{onOpen?<button className="link-button" onClick={()=>onOpen(site)}>{site.name}</button>:site.name}</div><div className="table-sub">{site.address||site.contact_phone||site.id}</div></div></div></td>
        <td><Pill state={site.connection}>{t(CONNECTION_KEY[site.connection||""]||"panel.admin.conn.offline")}</Pill></td>
        <td>{formatNumber(site.cameras_active)} / {formatNumber(site.cameras_expected)}
          {site.cameras_expected ? <small className="table-sub">{Math.round(((site.cameras_active||0)*100)/site.cameras_expected)}%</small> : null}</td>
        <td>{site.plan||"—"}</td>
        <td>{site.days_left==null?"—":<Pill state={site.days_left<=7?"failed":"active"}>{t("panel.common.days_count",{count:site.days_left})}</Pill>}</td>
        {onOpen?<td><ActionMenu items={[{label:t("panel.common.open"),onSelect:()=>onOpen(site)}]}/></td>:null}
      </tr>)}</tbody>
    </table></div>:<EmptyState icon="branch" title={t(sites.length?"panel.admin.sites.empty_filtered_title":"panel.admin.sites.empty_title")} detail={t(sites.length?"panel.admin.sites.empty_filtered_detail":"panel.admin.sites.empty_detail")}/>}
  </Card>;
}

function Telemetry({items}:{items:DeviceMetric[]}) { return <Card><div className="card-head"><div><h2>{t("panel.admin.telemetry.title")}</h2><p>{t("panel.admin.telemetry.subtitle")}</p></div><Pill>{t("panel.admin.telemetry.count",{count:items.length})}</Pill></div>{items.length?<div className="telemetry-grid">{items.map(item=><article className="telemetry" key={`${item.site_id}-${item.device_id}`}><div className="health-name" style={{marginBottom:15}}><div className="metric-icon tone-blue" style={{position:"static"}}><Icon name="server" size={18}/></div><div><b>{item.label||item.device_id}</b><small>{item.site_name||item.site_id}</small></div></div><div className="simple-row"><span>CPU</span><b>{item.cpu_percent==null?"—":`${item.cpu_percent.toFixed(1)}%`}</b></div><Percent value={item.cpu_percent}/><div className="simple-row"><span>RAM</span><b>{item.ram_percent==null?"—":`${item.ram_percent.toFixed(1)}%`}</b></div><Percent value={item.ram_percent}/><div className="simple-row"><span>{t("panel.admin.telemetry.disk")}</span><b>{item.disk_percent==null?"—":`${item.disk_percent.toFixed(1)}%`}</b></div><Percent value={item.disk_percent}/><div className="simple-row"><span>FPS</span><b>{item.fps==null?"—":item.fps.toFixed(1)}</b></div><div className="simple-row"><span>Inference</span><b>{item.inference_latency_ms==null?"—":`${item.inference_latency_ms.toFixed(0)} ms`}</b></div>{item.npu_percent==null?null:<div className="simple-row"><span>NPU</span><b>{item.npu_percent.toFixed(1)}%</b></div>}{item.temperature_c==null?null:<div className="simple-row"><span>{t("panel.admin.telemetry.temperature")}</span><b className={item.temperature_c>=85?"is-hot":undefined}>{item.temperature_c.toFixed(0)}°C</b></div>}</article>)}</div>:<EmptyState icon="server" title={t("panel.admin.telemetry.empty_title")} detail={t("panel.admin.telemetry.empty_detail")}/>}</Card>; }
function CustomersPage({sites,onRefresh,selected,onSelect}:{sites:Site[];onRefresh:()=>Promise<void>;selected:string;onSelect:(id:string)=>void}) {
  if (selected) return <AdminCustomer siteId={selected} onBack={()=>onSelect("")} onChanged={onRefresh}/>;
  return <CustomersList sites={sites} onRefresh={onRefresh} onSelect={onSelect}/>;
}

function CustomersList({sites,onRefresh,onSelect}:{sites:Site[];onRefresh:()=>Promise<void>;onSelect:(id:string)=>void}) {
  const[adding,setAdding]=useState(false);const[busy,setBusy]=useState(false);const[error,setError]=useState("");const[created,setCreated]=useState<CreatedCustomer|null>(null);
  const submit=async(event:React.FormEvent<HTMLFormElement>)=>{event.preventDefault();const form=event.currentTarget;const values=new FormData(form);setBusy(true);setError("");setCreated(null);try{const site=await api<{site_id:string;name:string;pairing_code:string;pairing_expires_at?:string}>("/api/v1/admin/sites","admin",{method:"POST",body:JSON.stringify({name:String(values.get("name")||""),plan:String(values.get("plan")||"biznes"),subscription_months:Number(values.get("months")||1),contact_phone:String(values.get("phone")||"")||null,address:String(values.get("address")||"")||null})});const loginData=await api<{username:string;password:string}>(`/api/v1/admin/sites/${encodeURIComponent(site.site_id)}/login`,"admin",{method:"POST"});setCreated({...site,...loginData});form.reset();setAdding(false);await onRefresh();}catch(reason){setError(reason instanceof Error?reason.message:t("panel.admin.customers.create_failed"));}finally{setBusy(false);}};
  const [copied,setCopied]=useState("");
  const copyCredentials=()=>{if(!created)return;const text=t("panel.admin.customers.credentials_text",{url:`${window.location.origin}/owner`,username:created.username,password:created.password,code:created.pairing_code});void copyText(text).then(ok=>setCopied(t(ok?"panel.admin.customers.copied":"panel.shell.copy_manually")));};
  return <><PageHeader title={t("panel.admin.nav.customers")} subtitle={t("panel.admin.customers.subtitle")} actions={<button className="btn btn-primary" onClick={()=>setAdding(value=>!value)}><Icon name="users"/>{t(adding?"panel.common.cancel":"panel.admin.customers.new")}</button>}/>{adding?<Card className="employee-form"><form className="card-body" onSubmit={submit}><div className="form-grid"><label>{t("panel.admin.customers.name")}<input className="input" name="name" minLength={2} required/></label><label>{t("panel.admin.col_plan")}<select className="select" name="plan" defaultValue="biznes"><option value="boshlangich">{t("panel.admin.plan.boshlangich")}</option><option value="biznes">{t("panel.admin.plan.biznes")}</option></select></label><label>{t("panel.admin.customers.phone")}<input className="input" name="phone" inputMode="tel" placeholder="+998…"/></label><label>{t("panel.admin.customers.address")}<input className="input" name="address"/></label><label>{t("panel.admin.customers.term")}<select className="select" name="months" defaultValue="1">{[1,3,6,12].map(months=><option key={months} value={months}>{t("panel.shell.months_count",{count:months})}</option>)}</select></label></div><button className="btn btn-primary" disabled={busy}>{t(busy?"panel.admin.customers.creating":"panel.admin.customers.create")}</button></form></Card>:null}{error?<div className="alert-strip"><Icon name="bell"/><div><strong>{t("panel.admin.action_failed_prefix")}</strong> {error}</div></div>:null}{created?<Card className="credential-card"><div className="card-head"><div><h2>{t("panel.admin.customers.creds_title")}</h2><p>{t("panel.admin.customers.creds_subtitle")}</p></div><Pill state="active">{t("panel.admin.customers.created")}</Pill></div><div className="credential-grid"><div><span>{t("panel.admin.customers.panel")}</span><b>{window.location.origin}/owner</b></div><div><span>{t("panel.login.username")}</span><b>{created.username}</b></div><div><span>{t("panel.admin.customers.one_time_password")}</span><b>{created.password}</b></div><div><span>{t("panel.admin.customers.pairing_code")}</span><b>{created.pairing_code}</b></div></div><div className="card-body"><button className="btn btn-primary" onClick={copyCredentials}>{copied||t("panel.admin.customers.copy_all")}</button></div></Card>:null}<div className="section-gap"><SiteTable sites={sites} onCreate={()=>setAdding(true)} onOpen={site=>onSelect(site.id)} searchable/></div></>;
}

/* To'lovni qayd etish — modal ichida, to'lov USULI bilan (naqd/bank).
   Ilgari `window.confirm` edi: usul so'ralmasdi va Telegram WebView'da
   brauzer oynasi ishonchsiz. */
function PaidModal({invoice,onClose,onDone}:{invoice:AdminInvoice;onClose:()=>void;onDone:()=>void}) {
  const[provider,setProvider]=useState("naqd");const[busy,setBusy]=useState(false);const[error,setError]=useState("");
  const submit=async()=>{setBusy(true);setError("");try{await api(`/api/v1/admin/invoices/${encodeURIComponent(invoice.id)}/paid`,"admin",{method:"POST",body:JSON.stringify({provider})});onDone();}catch(reason){setError(reason instanceof Error?reason.message:t("panel.admin.payments.confirm_failed"));setBusy(false);}};
  return <Modal title={t("panel.admin.payments.record_title")} onClose={onClose} footer={<><button className="btn" onClick={onClose}>{t("panel.common.cancel")}</button><button className="btn btn-primary" disabled={busy} onClick={()=>void submit()}>{t("panel.admin.payments.mark_paid")}</button></>}>
    <p className="modal-text">{t("panel.admin.payments.record_text",{site:invoice.site_name||invoice.site_id,amount:formatMoney(invoice.amount_uzs,{short:false}),months:invoice.months})}</p>
    <label className="choice"><input type="radio" name="provider" checked={provider==="naqd"} onChange={()=>setProvider("naqd")}/><span><b>{t("panel.admin.payments.cash")}</b><small>{t("panel.admin.payments.cash_hint")}</small></span></label>
    <label className="choice"><input type="radio" name="provider" checked={provider==="bank"} onChange={()=>setProvider("bank")}/><span><b>{t("panel.admin.payments.bank")}</b><small>{t("panel.admin.payments.bank_hint")}</small></span></label>
    {error?<div className="form-error">{error}</div>:null}
  </Modal>;
}

function PaymentsPage() {
  const[items,setItems]=useState<AdminInvoice[]|null>(null);const[error,setError]=useState("");const[paying,setPaying]=useState<AdminInvoice|null>(null);const[shown,setShown]=useState<AdminInvoice|null>(null);const[publicUrl,setPublicUrl]=useState("");
  const[confirm,confirmDialog]=useConfirm();const[toast,toastNode]=useToast();
  /* Xatoda ro'yxat BO'SH bo'ladi, `null` emas: `null` — «hali
     yuklanmoqda», ya'ni skelet.  Ilgari xato chizig'i bilan yonma-yon
     skelet ABADIY turib qolardi va qayta urinish tugmasi yo'q edi —
     ega panelida bu 2026-09-11 da tuzatilgan, adminga ko'chmagan. */
  const load=useCallback(()=>api<AdminInvoice[]>("/api/v1/admin/invoices","admin").then(data=>{setItems(data);setError("");}).catch(reason=>{setItems([]);setError(reason instanceof Error?reason.message:t("panel.admin.payments.load_failed"));}),[]);
  useEffect(()=>{void load();api<{public_url?:string}>("/api/v1/admin/payments/providers","admin").then(data=>setPublicUrl(data.public_url||"")).catch(()=>{});},[load]);
  const cancel=async(invoice:AdminInvoice)=>{
    if(!(await confirm({title:t("panel.admin.payments.cancel_title"),text:t("panel.admin.payments.cancel_text",{site:invoice.site_name||invoice.site_id,amount:formatMoney(invoice.amount_uzs,{short:false})}),confirmLabel:t("panel.common.cancel"),danger:true})))return;
    try{await api(`/api/v1/admin/invoices/${encodeURIComponent(invoice.id)}/cancel`,"admin",{method:"POST"});toast(t("panel.admin.payments.cancelled"));await load();}catch(reason){toast(reason instanceof Error?reason.message:t("panel.admin.payments.cancel_failed"),false);}
  };
  const payLink=(invoice:AdminInvoice)=>`${(publicUrl||window.location.origin).replace(/\/$/,"")}/pay/${invoice.id}`;
  return <><PageHeader title={t("panel.admin.nav.payments")} subtitle={t("panel.admin.payments.subtitle")}/>{error?<ErrorStrip title={t("panel.admin.payments.error_prefix")} detail={error} onRetry={()=>{setItems(null);void load();}}/>:null}<Card><div className="card-head"><div><h2>{t("panel.billing.invoices_title")}</h2><p>{t("panel.admin.payments.invoices_subtitle")}</p></div></div>{items===null?<div className="card-body"><Skeleton height={180}/></div>:items.length?<div className="table-wrap"><table><thead><tr><th>{t("panel.admin.col_customer")}</th><th>{t("panel.admin.payments.col_invoice")}</th><th>{t("panel.billing.col_term")}</th><th>{t("panel.billing.col_amount")}</th><th>{t("panel.billing.col_state")}</th><th>{t("panel.billing.col_action")}</th></tr></thead><tbody>{items.map(invoice=><tr key={invoice.id}><td><div className="table-title">{invoice.site_name||invoice.site_id}</div></td><td><button className="link-button mono" onClick={()=>setShown(invoice)}>#{invoice.id.slice(0,8)}</button></td><td>{t("panel.shell.months_count",{count:invoice.months})}</td><td>{formatMoney(invoice.amount_uzs,{short:false})}</td><td><Pill state={invoice.state}>{t(invoice.state==="paid"?"panel.billing.state_paid":invoice.state==="pending"?"panel.billing.state_pending":"panel.admin.payments.state_cancelled")}</Pill></td><td>{invoice.state==="pending"?<div className="page-actions"><button className="btn btn-primary btn-small" onClick={()=>setPaying(invoice)}>{t("panel.admin.payments.confirm")}</button><button className="btn btn-small btn-danger" onClick={()=>void cancel(invoice)}>{t("panel.admin.payments.cancel_short")}</button></div>:invoice.provider||"—"}</td></tr>)}</tbody></table></div>:<EmptyState icon="invoice" title={t("panel.billing.empty_title")} detail={t("panel.admin.payments.empty_detail")}/>}</Card>
    {paying?<PaidModal invoice={paying} onClose={()=>setPaying(null)} onDone={()=>{setPaying(null);toast(t("panel.admin.payments.recorded"));void load();}}/>:null}
    {shown?<Modal title={t("panel.admin.payments.invoice_title",{name:shown.site_name||t("panel.admin.col_customer")})} onClose={()=>setShown(null)}>
      <div className="simple-list"><div className="simple-row"><span>{t("panel.billing.col_amount")}</span><b>{formatMoney(shown.amount_uzs,{short:false})}</b></div><div className="simple-row"><span>{t("panel.billing.col_term")}</span><b>{t("panel.shell.months_count",{count:shown.months})}</b></div><div className="simple-row"><span>{t("panel.billing.col_state")}</span><Pill state={shown.state}>{t(shown.state==="paid"?"panel.billing.state_paid":shown.state==="pending"?"panel.billing.state_pending":"panel.admin.payments.state_cancelled")}</Pill></div></div>
      <p className="modal-text">{t("panel.admin.payments.link_text")}</p><CopyField value={payLink(shown)}/>
      <div className="page-actions wrap">{shown.payme_url?<a className="btn" href={shown.payme_url} target="_blank" rel="noopener noreferrer">Payme</a>:null}{shown.click_url?<a className="btn" href={shown.click_url} target="_blank" rel="noopener noreferrer">Click</a>:null}</div>
      {publicUrl?null:<p className="metric-note">{t("panel.admin.payments.no_domain")}</p>}
    </Modal>:null}
    {confirmDialog}{toastNode}</>;
}

function PlansPage() {
  const[data,setData]=useState<{price_book?:{label?:string;usd_rate_uzs?:number;base_fee_usd_cents?:number};features:Feature[]}|null>(null);const[error,setError]=useState("");
  const load=useCallback(()=>{api<{price_book?:{label?:string;usd_rate_uzs?:number;base_fee_usd_cents?:number};features:Feature[]}>("/api/v1/admin/features","admin").then(data=>{setData(data);setError("");})
    // Bo'sh katalog — «yuklanmadi» dan FARQLI holat: skelet to'xtaydi.
    .catch(reason=>{setData({features:[]});setError(reason instanceof Error?reason.message:t("panel.admin.plans.load_failed"));});},[]);
  useEffect(()=>{void load();},[load]);
  return <><PageHeader title={t("panel.admin.nav.plans")} subtitle={t("panel.admin.plans.subtitle")}/>{error?<ErrorStrip detail={error} onRetry={()=>{setData(null);void load();}}/>:null}{data?<><div className="metric-grid"><StatCard label={t("panel.admin.plans.book")} value={data.price_book?.label||"—"} note={t("panel.admin.plans.book_note")} icon="card"/><StatCard label={t("panel.admin.plans.features")} value={formatNumber(data.features.length)} note={t("panel.admin.plans.features_note")} icon="pulse"/><StatCard label={t("panel.admin.plans.usd_rate")} value={formatMoney(data.price_book?.usd_rate_uzs)} note={t("panel.admin.plans.usd_rate_note")} icon="chart"/><StatCard label={t("panel.admin.plans.base_fee")} value={data.price_book?.base_fee_usd_cents==null?"—":`$${(data.price_book.base_fee_usd_cents/100).toFixed(0)}`} note={t("panel.admin.plans.base_fee_note")} icon="server"/></div><Card><div className="card-head"><div><h2>{t("panel.admin.plans.table_title")}</h2><p>{t("panel.admin.plans.table_subtitle")}</p></div></div><div className="table-wrap"><table><thead><tr><th>{t("panel.admin.plans.col_feature")}</th><th>{t("panel.admin.plans.col_kind")}</th><th>{t("panel.admin.plans.col_price")}</th><th>{t("panel.admin.plans.col_cost")}</th></tr></thead><tbody>{data.features.map(feature=><tr key={feature.code}><td><div className="table-title">{feature.name}</div><div className="table-sub">{feature.code}</div></td><td>{feature.category}</td><td>${(feature.monthly_usd_cents/100).toFixed(2)}</td><td>${(feature.cost_usd_cents/100).toFixed(2)}</td></tr>)}</tbody></table></div></Card></>:<Card><div className="card-body"><Skeleton height={190}/></div></Card>}</>;
}

/* Moliya: platforma va HAR MIJOZ nechchiga tushayapti.  Gemini xarajati
   haqiqiy token sarfidan (usageMetadata), infra env'dagi summalardan —
   sahifada qo'lda yozilgan raqam yo'q. */
type FinanceSite = {site_id:string;name?:string;plan?:string;billable:boolean;license_status?:string;revenue_uzs:number;gemini_jobs:number;gemini_untracked_jobs:number;gemini_input_tokens:number;gemini_output_tokens:number;gemini_cost_uzs:number;shared_cost_uzs:number;energy_measured:boolean;energy_watts:number;energy_uptime_hours:number;energy_kwh:number;energy_cost_uzs:number;customer_total_uzs:number;total_cost_uzs:number;margin_uzs:number;margin_percent:number|null};
type Finance = {
  month:string; usd_rate_uzs:number;
  fixed:{server_monthly_usd:number;server_monthly_uzs:number;server_configured:boolean;domain_yearly_uzs:number;domain_monthly_uzs:number;total_monthly_uzs:number;split_between:number;share_per_site_uzs:number;kwh_uzs:number;watts_windows:number;watts_box:number};
  gemini:{jobs:number;untracked_jobs:number;input_tokens:number;output_tokens:number;cost_uzs:number;input_usd_per_m:number;output_usd_per_m:number;model?:string|null};
  sites:FinanceSite[];
  energy:{cost_uzs:number;kwh_uzs:number;paid_by:string};
  totals:{revenue_uzs:number;cost_uzs:number;gemini_cost_uzs:number;energy_cost_uzs:number;fixed_cost_uzs:number;margin_uzs:number;margin_percent:number|null;sites_billable:number;sites_paying:number;customer_total_uzs:number};
};

function financeMonths():string[] {
  const now=new Date();
  return Array.from({length:6},(_,back)=>{const d=new Date(now.getFullYear(),now.getMonth()-back,1);return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}`;});
}

function FinancePage() {
  const [month,setMonth]=useState("");
  const [data,setData]=useState<Finance|null>(null);
  const [error,setError]=useState("");
  useEffect(()=>{let stopped=false;setData(null);api<Finance>(`/api/v1/admin/finance${month?`?month=${month}`:""}`,"admin").then(next=>{if(!stopped){setData(next);setError("");}}).catch(reason=>{if(!stopped)setError(reason instanceof Error?reason.message:t("panel.admin.finance.load_failed"));});return()=>{stopped=true;};},[month]);
  // `t` EMAS: i18n `t()` ni soyalab qo'yardi va shu funksiyada
  // keyinchalik tarjima chaqirilsa jimgina son formatlagichga
  // tushib ketardi.
  const fmt=(n:number)=>Number(n||0).toLocaleString("ru-RU");
  if(error) return <><PageHeader title={t("panel.admin.nav.finance")} subtitle={t("panel.admin.finance.subtitle")}/><Card><EmptyState icon="bell" title={t("panel.admin.load_failed")} detail={error}/></Card></>;
  if(!data) return <><PageHeader title={t("panel.admin.nav.finance")} subtitle={t("panel.admin.finance.subtitle")}/><Card><div className="card-body"><Skeleton height={190}/></div></Card></>;
  const {fixed,gemini,totals}=data;
  return <>
    <PageHeader title={t("panel.admin.nav.finance")} subtitle={t("panel.admin.finance.rate",{month:data.month,rate:formatMoney(data.usd_rate_uzs)})} actions={<select className="select" value={month||data.month} onChange={event=>setMonth(event.target.value)} aria-label={t("panel.common.month")}>{financeMonths().map(m=><option key={m} value={m}>{m}</option>)}</select>}/>
    {!fixed.server_configured?<div className="alert-strip alert-warning"><Icon name="bell"/><div><strong>{t("panel.admin.finance.no_server_price")}</strong> {t("panel.admin.finance.no_server_price_detail")}</div></div>:null}
    <div className="metric-grid">
      <StatCard label={t("panel.admin.finance.revenue")} value={formatMoney(totals.revenue_uzs)} note={t("panel.admin.finance.revenue_note",{count:totals.sites_paying})} icon="card" tone="green"/>
      <StatCard label={t("panel.admin.finance.cost")} value={formatMoney(totals.cost_uzs)} note={t("panel.admin.finance.cost_note")} icon="invoice" tone="red"/>
      <StatCard label={t("panel.admin.finance.margin")} value={formatMoney(totals.margin_uzs)} note={totals.margin_percent===null?t("panel.admin.finance.margin_note"):t("panel.admin.finance.margin_note_percent",{percent:totals.margin_percent})} icon="chart" tone={totals.margin_uzs>=0?"green":"red"}/>
      <StatCard label={t("panel.admin.finance.customer_total")} value={formatMoney(totals.customer_total_uzs)} note={t("panel.admin.finance.customer_total_note")} icon="pulse" tone="blue"/>
    </div>
    <div className="dashboard-grid section-gap">
      <Card><div className="card-head"><div><h2>{t("panel.admin.finance.fixed_title")}</h2><p>{t("panel.admin.finance.fixed_subtitle")}</p></div></div><div className="card-body">
        <div className="simple-row"><span>{t("panel.admin.finance.server")}</span><b>{fixed.server_configured?`$${fixed.server_monthly_usd} ≈ ${formatMoney(fixed.server_monthly_uzs)}`:t("panel.admin.finance.server_missing")}</b></div>
        <div className="simple-row"><span>{t("panel.admin.finance.domain")}</span><b>{t("panel.admin.finance.domain_value",{yearly:formatMoney(fixed.domain_yearly_uzs),monthly:formatMoney(fixed.domain_monthly_uzs)})}</b></div>
        <div className="simple-row"><span>{t("panel.admin.finance.total_monthly")}</span><b>{formatMoney(fixed.total_monthly_uzs)}</b></div>
        <div className="simple-row"><span>{t("panel.admin.finance.split")}</span><b>{t("panel.admin.finance.split_value",{count:fixed.split_between,amount:formatMoney(fixed.share_per_site_uzs)})}</b></div>
        <div className="simple-row"><span>{t("panel.admin.finance.energy")}</span><b>{formatMoney(totals.energy_cost_uzs)}</b></div>
        <div className="simple-row"><span>{t("panel.admin.finance.kwh")}</span><b>{t("panel.admin.finance.kwh_value",{amount:formatMoney(fixed.kwh_uzs)})}</b></div>
        <div className="simple-row"><span>{t("panel.admin.finance.power")}</span><b>{t("panel.admin.finance.power_value",{windows:fixed.watts_windows,box:fixed.watts_box})}</b></div>
      </div></Card>
      <Card><div className="card-head"><div><h2>{t("panel.admin.finance.gemini_title")}</h2><p>{t("panel.admin.finance.gemini_subtitle")}</p></div></div><div className="card-body">
        <div className="simple-row"><span>{t("panel.admin.finance.model")}</span><b>{gemini.model||t("panel.admin.finance.model_missing")}</b></div>
        <div className="simple-row"><span>{t("panel.admin.finance.questions")}</span><b>{t("panel.admin.finance.questions_value",{count:gemini.jobs})}{gemini.untracked_jobs?t("panel.admin.finance.untracked",{count:gemini.untracked_jobs}):""}</b></div>
        <div className="simple-row"><span>{t("panel.admin.finance.tokens")}</span><b>{t("panel.admin.finance.tokens_value",{input:fmt(gemini.input_tokens),output:fmt(gemini.output_tokens)})}</b></div>
        <div className="simple-row"><span>{t("panel.admin.finance.price")}</span><b>${gemini.input_usd_per_m}/1M · ${gemini.output_usd_per_m}/1M</b></div>
      </div></Card>
    </div>
    <Card className="section-gap"><div className="card-head"><div><h2>{t("panel.admin.finance.per_site_title")}</h2><p>{t("panel.admin.finance.per_site_subtitle")}</p></div></div>
      {data.sites.length?<div className="table-wrap"><table>
        <thead><tr><th>{t("panel.admin.col_customer")}</th><th>{t("panel.admin.finance.col_revenue")}</th><th>{t("panel.admin.finance.col_gemini")}</th><th>{t("panel.admin.finance.col_tokens")}</th><th>{t("panel.admin.finance.col_gemini_cost")}</th><th>{t("panel.admin.finance.col_infra")}</th><th>{t("panel.admin.finance.col_cost")}</th><th>{t("panel.admin.finance.col_margin")}</th><th>{t("panel.admin.finance.col_energy")}</th></tr></thead>
        <tbody>{data.sites.map(s=><tr key={s.site_id}>
          <td><div className="table-title">{s.name||s.site_id}</div><div className="table-sub">{s.plan||"—"}{s.billable?"":t("panel.admin.finance.not_billable")}</div></td>
          <td>{s.billable?formatMoney(s.revenue_uzs):"—"}</td>
          <td>{s.gemini_jobs}{s.gemini_untracked_jobs?<small className="table-sub"> ({s.gemini_untracked_jobs})</small>:null}</td>
          <td><small>{fmt(s.gemini_input_tokens)} / {fmt(s.gemini_output_tokens)}</small></td>
          <td>{formatMoney(s.gemini_cost_uzs)}</td>
          <td>{s.billable?formatMoney(s.shared_cost_uzs):"—"}</td>
          <td><b>{formatMoney(s.total_cost_uzs)}</b></td>
          <td><Pill state={s.margin_uzs>=0?"active":"failed"}>{formatMoney(s.margin_uzs)}</Pill>{s.margin_percent===null?null:<div className="table-sub">{s.margin_percent}%</div>}</td>
          <td className="table-sub">{s.energy_measured?<>{formatMoney(s.energy_cost_uzs)}<div className="table-sub">{t("panel.admin.finance.energy_value",{hours:s.energy_uptime_hours,watts:s.energy_watts})}</div></>:<>—<div className="table-sub">{t("panel.admin.finance.no_measure")}</div></>}</td>
        </tr>)}</tbody>
      </table></div>:<EmptyState icon="branch" title={t("panel.admin.finance.empty_title")} detail={t("panel.admin.finance.empty_detail")}/>}
    </Card>
  </>;
}

/** Saytdan kelgan arizalar.
 *
 * Eski paneldagi «Arizalar» bo'limi v2 ga ko'chirilmay qolgan edi —
 * ya'ni eski panel o'chirilsa sotuv quvuri KO'RINMAY qolardi.
 * (2026-09-07 da rebrending paytida topildi.) */
function LeadsPage() {
  const[leads,setLeads]=useState<Lead[]|null>(null);const[error,setError]=useState("");const[busy,setBusy]=useState("");
  const load=useCallback(()=>{api<Lead[]>("/api/v1/admin/leads","admin").then(data=>{setLeads(data);setError("");}).catch(reason=>{setLeads([]);setError(reason instanceof Error?reason.message:t("panel.lead.load_failed"));});},[]);
  useEffect(load,[load]);

  async function act(lead:Lead,path:string,body:unknown){
    setBusy(lead.id);setError("");
    try{await api(path,"admin",{method:"POST",body:JSON.stringify(body)});load();}
    catch(reason){setError(reason instanceof Error?reason.message:t("panel.lead.load_failed"));}
    finally{setBusy("");}
  }
  const status=(lead:Lead,to:string)=>act(lead,`/api/v1/admin/leads/${lead.id}/status`,{status:to});
  const convert=(lead:Lead)=>act(lead,`/api/v1/admin/leads/${lead.id}/convert`,{subscription_months:1});

  return <><PageHeader title={t("panel.lead.title")} subtitle={t("panel.lead.subtitle")}/>
    {error?<ErrorStrip detail={error} onRetry={()=>{setLeads(null);void load();}}/>:null}
    <Card>{leads===null?<div className="card-body"><Skeleton height={200}/></div>:leads.length?<div className="simple-list">{leads.map(lead=>{
      const open=lead.status!=="closed"&&!lead.site_id;
      return <div className="simple-row" key={lead.id}>
        <div>
          <b>{lead.full_name||lead.phone}</b>
          <div className="table-sub"><a href={`tel:${lead.phone}`}>{lead.phone}</a>
            {" · "}{lead.company||t("panel.lead.no_company")}
            {" · "}{lead.city||t("panel.lead.no_city")}
            {" · "}{t("panel.lead.cameras",{count:lead.cameras})}
            {lead.created_at?` · ${formatDateShort(lead.created_at)}`:""}</div>
        </div>
        <div className="page-actions">
          <Pill state={lead.status==="new"?"pending":lead.status==="closed"?"expired":"active"}>{t(`panel.lead.status.${lead.status}`)}</Pill>
          {lead.status==="new"?<button className="btn" disabled={busy===lead.id} onClick={()=>void status(lead,"contacted")}>{t("panel.lead.action.contacted")}</button>:null}
          {["new","contacted"].includes(lead.status)?<button className="btn" disabled={busy===lead.id} onClick={()=>void status(lead,"qualified")}>{t("panel.lead.action.qualified")}</button>:null}
          {open?<button className="btn btn-primary" disabled={busy===lead.id} onClick={()=>void convert(lead)}>{t("panel.lead.action.convert")}</button>:null}
          {open?<button className="btn btn-danger" disabled={busy===lead.id} onClick={()=>void status(lead,"closed")}>{t("panel.lead.action.close")}</button>:null}
        </div>
      </div>;
    })}</div>:<EmptyState icon="invoice" title={t("panel.lead.empty.title")} detail={t("panel.lead.empty.detail")}/>}</Card>
  </>;
}

function VisionAgentPage({sites}:{sites:Site[]}) {
  const [siteId,setSiteId]=useState(""); const [question,setQuestion]=useState(""); const [settings,setSettings]=useState<{consented:boolean;provider_configured:boolean}|null>(null); const [settingsError,setSettingsError]=useState(""); const [result,setResult]=useState<{status:string;result?:{answer?:string;sources?:Array<{event_id:string;label?:string;occurred_at?:string}>};error?:string}|null>(null); const timer=useRef(0);
  useEffect(()=>{setSiteId(current=>current||sites[0]?.id||"");},[sites]);
  /* Sozlama xatosi ham KO'RSATILADI — avval `.catch(()=>setSettings(null))`
     jim yutar va admin sababsiz o'chirilgan tugma qarshisida qolardi. */
  useEffect(()=>{if(!siteId)return;setSettings(null);setSettingsError("");api<{consented:boolean;provider_configured:boolean}>(`/api/v1/admin/sites/${encodeURIComponent(siteId)}/agent/settings`,"admin").then(next=>{setSettings(next);setSettingsError("");}).catch(reason=>{setSettings(null);setSettingsError(reason instanceof Error?reason.message:t("panel.agent.settings_failed"));});},[siteId]);
  useEffect(()=>()=>window.clearTimeout(timer.current),[]);
  const poll=useCallback(async(id:string,ticks=0,fails=0)=>{try{const job=await api<{status:string;result?:{answer?:string;sources?:Array<{event_id:string;label?:string;occurred_at?:string}>};error?:string}>(`/api/v1/admin/sites/${encodeURIComponent(siteId)}/agent/jobs/${encodeURIComponent(id)}`,"admin");if(job.status==="queued"||job.status==="running"){if(ticks>=130){setResult({status:"failed",error:t("panel.admin.agent.timeout")});return;}setResult(job);timer.current=window.setTimeout(()=>void poll(id,ticks+1,0),1800);return;}setResult(job);}catch(reason){if(fails>=4){setResult({status:"failed",error:reason instanceof Error?reason.message:t("panel.agent.answer_failed")});return;}timer.current=window.setTimeout(()=>void poll(id,ticks+1,fails+1),3000);}},[siteId]);
  const ask=async()=>{if(!question.trim()||!siteId)return;setResult({status:"queued"});try{const job=await api<{job_id:string}>(`/api/v1/admin/sites/${encodeURIComponent(siteId)}/agent/queries`,"admin",{method:"POST",body:JSON.stringify({message:question.trim()})});void poll(job.job_id);}catch(reason){setResult({status:"failed",error:reason instanceof Error?reason.message:t("panel.agent.send_failed")});}};
  return <><PageHeader title={t("panel.admin.nav.agent")} subtitle={t("panel.admin.agent.subtitle")}/><Card><div className="card-body agent-composer"><select className="select" value={siteId} onChange={event=>setSiteId(event.target.value)} aria-label={t("panel.admin.branch")}>{sites.map(site=><option key={site.id} value={site.id}>{site.name}</option>)}</select>{settingsError?<div className="alert-strip"><Icon name="bell"/>{t("panel.admin.agent.settings_failed_prefix",{reason:settingsError})}</div>:null}{settings&&!settings.provider_configured?<div className="alert-strip alert-warning"><Icon name="bell"/>{t("panel.admin.agent.no_provider")}</div>:null}{settings&&!settings.consented?<div className="alert-strip alert-info"><Icon name="shield"/>{t("panel.admin.agent.no_consent")}</div>:null}<textarea className="input" rows={4} value={question} onChange={event=>setQuestion(event.target.value)} placeholder={t("panel.admin.agent.example")}/><button className="btn btn-primary" disabled={!settings?.consented||!settings?.provider_configured||result?.status==="queued"||result?.status==="running"} onClick={()=>void ask()}>{t(result?.status==="queued"||result?.status==="running"?"panel.admin.agent.checking":"panel.agent.ask")}</button></div></Card>{result?.status==="completed"?<Card className="section-gap"><div className="card-body"><p className="agent-answer">{result.result?.answer}</p>{result.result?.sources?.map(source=><div className="simple-row" key={source.event_id}><b>{source.label||t("panel.agent.source_event")}</b><span>{source.occurred_at||"—"}</span></div>)}</div></Card>:null}{result?.status==="failed"?<Card className="section-gap"><EmptyState icon="bell" title={t("panel.admin.agent.error_title")} detail={result.error||t("panel.admin.agent.retry_detail")}/></Card>:null}</>;
}

function GenericAdmin({id,param,data,onRefresh,onSelect}:{id:string;param:string;data:AdminDashboard;onRefresh:()=>Promise<void>;onSelect:(site:string)=>void}) {
  if(id==="customers") return <CustomersPage sites={data.sites} onRefresh={onRefresh} selected={param} onSelect={onSelect}/>;
  if(id==="branches") return <><PageHeader title={t("panel.nav.branches")} subtitle={t("panel.admin.branches.subtitle")}/><SiteTable sites={data.sites} searchable/></>;
  if(id==="monitoring") return <><PageHeader title={t("panel.admin.nav.monitoring")} subtitle={t("panel.admin.monitoring.subtitle")}/><Telemetry items={data.telemetry}/></>;
  if(id==="cameras") return <><PageHeader title={t("panel.nav.cameras")} subtitle={t("panel.admin.cameras.subtitle")}/><div className="metric-grid">{data.sites.map(site=><StatCard key={site.id} label={site.name} value={`${formatNumber(site.cameras_active)} / ${formatNumber(site.cameras_expected)}`} note={site.connection||"—"} icon="camera" tone={(site.cameras_active||0)>=(site.cameras_expected||1)?"green":"red"}/>)}</div></>;
  if(id==="plans") return <PlansPage/>;
  if(id==="payments") return <PaymentsPage/>;
  if(id==="finance") return <FinancePage/>;
  if(id==="events") return <EventEvidence kind="admin" sites={data.sites}/>;
  if(id==="agent") return <VisionAgentPage sites={data.sites}/>;
  if(id==="leads") return <LeadsPage/>;
  if(id==="team") return <AdminTeam sites={data.sites}/>;
  if(id==="settings") return <AdminSettings/>;
  return <><PageHeader title={t("panel.admin.section.title")} subtitle={t("panel.admin.section.subtitle")}/><Card><EmptyState icon="settings" title={t("panel.admin.section.empty_title")} detail={t("panel.admin.section.empty_detail")}/></Card></>;
}

function AdminApp() {
  const [authenticated,setAuthenticated] = useState(()=>Boolean(tokenFor("admin")));
  const [active,navigateTo,param] = usePanelRoute("/admin", ROUTE_IDS, "overview", LEGACY_ROUTES);
  const [range,setRange] = useState("7d");
  const [busy,setBusy] = useState(false);
  const [loginError,setLoginError] = useState("");
  const [drawer,setDrawer] = useState(false);
  const {data,loading,error,refresh} = useAdminDashboard(authenticated,range);

  const submit = async(username:string,password:string)=>{setBusy(true);setLoginError("");try{await login(username,password,"admin");setAuthenticated(true);}catch(reason){setLoginError(reason instanceof Error?reason.message:t("panel.admin.login_failed"));}finally{setBusy(false);}};
  const logout = ()=>{void serverLogout("admin");setAuthenticated(false);};
  const navigate = (id:string,item="")=>{if(id==="more")setDrawer(true);else{navigateTo(id,item);setDrawer(false);window.scrollTo({top:0,behavior:"smooth"});}};

  const offline = data?.stats.offline || 0;
  const notPaired = data?.stats.not_paired || 0;
  const attention = offline + notPaired;

  /* Menyu yorliqlari shu yerda ochiladi (`NAV_ITEMS` izohiga qarang). */
  const NAV:NavItem[] = useMemo(()=>NAV_ITEMS.map(({id,key,icon})=>({ id, icon, label: t(key) })),[]);

  /* ⌘K uchun ro'yxat: bo'limlar + mijozlar.  Mijozni tanlash uni
     filtrlash uchun emas, mijozlar sahifasiga olib boradi — u yerda
     qidiruv maydoni bor. */
  const searchEntries = useMemo(()=>[
    ...NAV.map(item=>({ id:`nav-${item.id}`, label:item.label, hint:t("panel.admin.hint_section"), onSelect:()=>navigate(item.id) })),
    ...(data?.sites || []).map(site=>({ id:`site-${site.id}`, label:site.name, hint:site.address||t("panel.admin.col_customer"), onSelect:()=>navigate("customers", site.id) })),
  ],[NAV,data?.sites]);

  if(!authenticated) return <LoginScreen kind="admin" onSubmit={submit} busy={busy} error={loginError}/>;
  if(loading&&!data) return <div className="login-page"><section className="login-visual"><Logo/><div><span className="eyebrow">{t("panel.login.eyebrow_admin")}</span><h1>{t("panel.admin.boot_loading")}</h1></div></section><section className="login-panel"><div style={{width:"min(390px,100%)"}}><Skeleton height={60}/><div style={{height:14}}/><Skeleton height={180}/></div></section></div>;
  /* Server javob bermasa — sabab va qayta urinish.  Avval bu holat ham
     "olinmoqda" skeletida abadiy qolardi. */
  if(!data) return <div className="login-page"><section className="login-visual"><Logo/><div><span className="eyebrow">{t("panel.login.eyebrow_admin")}</span><h1>{t("panel.admin.boot_failed")}</h1></div></section><section className="login-panel"><div style={{width:"min(390px,100%)"}}><p className="metric-note">{error||t("panel.admin.server_unreachable")}</p><div className="page-actions" style={{marginTop:14}}><button className="btn btn-primary" onClick={()=>void refresh()}>{t("panel.common.retry")}</button><button className="btn" onClick={logout}>{t("panel.common.logout")}</button></div></div></section></div>;

  const today = formatDateUz();
  return <AppShell
    nav={NAV}
    mobileNav={MOBILE_NAV}
    active={active}
    onNavigate={navigate}
    title={t("panel.admin.title")}
    subtitle={t("panel.admin.updated",{time:new Date(data.updated_at).toLocaleTimeString("uz-UZ",{hour:"2-digit",minute:"2-digit"})})}
    onLogout={logout}
    sidebarFooter={<div className="sidebar-user"><Icon name="shield"/><div><b>ENES Cloud</b><small>{t("panel.admin.sidebar_role")}</small></div></div>}
    headerActions={<>
      <SearchPalette entries={searchEntries} placeholder={t("panel.admin.search_placeholder")}/>
      <span className={`status-chip ${attention ? "is-warn" : "is-ok"}`}><i/>{attention ? t("panel.admin.attention_count",{count:attention}) : t("panel.admin.system_stable")}</span>
      <span className="topbar-date"><Icon name="calendar" size={16}/>{today}</span>
      <select className="select" value={range} onChange={event=>setRange(event.target.value)} aria-label={t("panel.admin.range_aria")}><option value="7d">{t("panel.common.days_count",{count:7})}</option><option value="30d">{t("panel.common.days_count",{count:30})}</option></select>
      <button className="btn btn-icon" onClick={()=>void refresh()} aria-label={t("panel.common.refresh")}><Icon name="pulse"/></button>
    </>}>
    {error?<div className="alert-strip"><Icon name="bell"/><div><strong>{t("panel.admin.refresh_error")}</strong> {error}. {t("panel.admin.showing_last")}</div></div>:null}
    {active==="overview"
      ? <><PageHeader title={t("panel.admin.title")} subtitle={today} actions={<button className="btn btn-primary" onClick={()=>navigate("customers")}><Icon name="users"/>{t("panel.admin.customers.add")}</button>}/><AdminHome data={data} onNavigate={navigate}/></>
      : <GenericAdmin id={active} param={param} data={data} onRefresh={refresh} onSelect={site=>navigate("customers", site)}/>}
    {drawer?<div className="drawer-backdrop" onClick={()=>setDrawer(false)}><aside className="drawer" onClick={event=>event.stopPropagation()}><div className="drawer-head"><Logo/><button className="btn btn-icon" aria-label={t("panel.common.close")} onClick={()=>setDrawer(false)}><Icon name="close"/></button></div><nav>{NAV.map(item=><button key={item.id} className={active===item.id?"active":""} onClick={()=>navigate(item.id)}><Icon name={item.icon}/>{item.label}</button>)}</nav></aside></div>:null}
  </AppShell>;
}

/* Tema `owner.html`/`admin.html` dagi boot skriptida allaqachon
 * qo'yilgan (chizishdan oldin).  Bu yerda yana bir marta chaqiriladi:
 * skript faqat ATRIBUTNI qo'yadi, `theme-color` metasi esa tizim
 * rejimida ham to'g'ri bo'lishi kerak — uni JS hisoblab beradi. */
/* Til birinchi chizishdan oldin: `document.documentElement.lang`
 * ham shu yerda qo'yiladi — brauzerning imlo tekshiruvi va
 * ekran o'quvchisi to'g'ri tilni bilishi uchun. */
initLang();
applyTheme(readTheme());

createRoot(document.getElementById("root")!).render(<StrictMode><AdminApp/></StrictMode>);
