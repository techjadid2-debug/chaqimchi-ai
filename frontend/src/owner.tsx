import { StrictMode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { api, clearToken, logout as serverLogout, downloadBlobUrl, downloadCsv, formatDateShort, formatDateUz, formatMoney, formatNumber, formatTimeUz, login, loginWithLinkKey, loginWithTelegram, mediaObjectUrl, relativeMinutes, takeConnectToken, telegramBotUrl, toJpeg, tokenFor } from "./api";
import { Demography } from "./Demography";
import { Numbers } from "./Numbers";
import { AppShell, Card, CopyButton, EmptyState, Avatar, ErrorStrip, LangSwitch, LoginScreen, PageHeader, Pill, Skeleton, StatCard, TabPanel, Tabs, ThemeToggle, useConfirm, useToast, type NavItem } from "./components";
import { LineChart, type Point } from "./charts";
import { Connect } from "./Connect";
import { GeometryEditor } from "./GeometryEditor";
import { HeatmapPage } from "./Heatmap";
import { CamerasBlock } from "./Cameras";
import { CAMERA_TABS, CameraDetail } from "./CameraDetail";
import { OwnerHome } from "./OwnerHome";
import { Analytics } from "./Analytics";
import { SetupCameras } from "./SetupCameras";
import { VisionAgent } from "./VisionAgent";
import { EventEvidence } from "./EventEvidence";
import { usePanelRoute } from "./router";
import type { Dashboard, Employee, Invoice, Site, TelegramMember, TrendPoint } from "./types";
import { Icon, Logo } from "./icons";
import { initLang, t } from "./i18n";
import { applyTheme, readTheme } from "./theme";
import "./styles.css";

/* Yorliq matn emas, katalog KALITI (`SetupCameras.tsx: ROLE_CHOICES`
   bilan bir xil sabab): modul yuklanganda til hali tanlanmagan —
   `initLang()` shu faylning oxirida chaqiriladi, ya'ni bu yerda `t()`
   ishlatilsa menyu doim o'zbekcha qolardi.  Matn `OwnerApp` ichida,
   chizish paytida ochiladi. */
const NAV_ITEMS: Array<{ id: string; key: string; icon: string }> = [
  { id: "home", key: "panel.nav.home", icon: "home" },
  { id: "cameras", key: "panel.nav.cameras", icon: "camera" },
  { id: "alerts", key: "panel.nav.alerts", icon: "shield" },
  { id: "employees", key: "panel.nav.employees", icon: "users" },
  { id: "customers", key: "panel.nav.customers", icon: "entry" },
  { id: "analytics", key: "panel.nav.analytics", icon: "chart" },
  { id: "reports", key: "panel.nav.reports", icon: "report" },
  { id: "settings", key: "panel.nav.settings", icon: "settings" },
];

/* Bo'lim ichidagi tablar.  Birinchisi — standart.
 *
 * Menyu 14 bo'limdan 8 taga qisqardi (dizayn-3, 2026-09-10): ega
 * kuniga bir necha marta telefondan ochadi va 14 qatorli menyuda
 * "Chiziq va zonalar" bilan "Kamerani ulash" qayerdaligini har safar
 * qidirardi.  Sahifalarning O'ZI o'zgarmadi — faqat manzili. */
const TABS: Record<string, string[]> = {
  cameras: ["live", "setup", "zones"],
  alerts: ["evidence", "agent"],
  customers: ["flow", "demography", "heatmap"],
  settings: ["store", "telegram", "billing", "branches"],
};

/* Eski bo'lim nomi → yangi bo'lim va tab.  Telegram xabarlaridagi
   havolalar, xatcho'plar va koddagi `onNavigate("billing")` chaqiruvlari
   shu xarita orqali o'z joyiga boradi (`router.ts`). */
const LEGACY_ROUTES = {
  setup: ["cameras", "setup"],
  zones: ["cameras", "zones"],
  agent: ["alerts", "agent"],
  traffic: ["customers", "flow"],
  heatmap: ["customers", "heatmap"],
  telegram: ["settings", "telegram"],
  billing: ["settings", "billing"],
  branches: ["settings", "branches"],
} as const;

const ROUTE_IDS = NAV_ITEMS.map(item => item.id);
const MOBILE_NAV = ["home", "cameras", "alerts", "customers"];

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
      setError(reason instanceof Error ? reason.message : t("panel.owner.dashboard_load_failed"));
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

/** 14 kunlik dinamika — bosh sahifadagi bilan bitta `LineChart`.
 *  Ilgari bu yerda alohida SVG bor edi: ikkinchi nusxa, qattiq rang
 *  (`#4285f4`) va tooltip'siz. */
function TrendChart({ points }: { points: TrendPoint[] }) {
  const normalized: Point[] = (points || []).slice(-14).map(point => ({ label: String(point.date || point.day || "").slice(5), value: Number(point.entries ?? point.entered ?? point.count ?? 0) }));
  if (normalized.length < 2 || !normalized.some(point => point.value > 0)) return <EmptyState icon="chart" title={t("panel.traffic.trend_empty_title")} detail={t("panel.traffic.trend_empty_detail")} />;
  return <LineChart series={[{ name: t("panel.home.flow.series"), points: normalized }]}/>;
}

type Notification = { event_id: string; event_type: string; label?: string; camera_id?: string; occurred_at?: string; severity?: string; unread?: boolean };

/** Qo'ng'iroq — o'qilmagan ogohlantirishlar.
 *
 * Ilgari bu tugmadagi son `data.events.length` edi: panel olgan oxirgi
 * 12 ta hodisa soni.  U hech qachon kamaymasdi va gavjum do'konda
 * abadiy "9+" bo'lib turardi, ya'ni egaga hech narsa aytmasdi.
 *
 * Endi son SERVERDAN keladi va "o'qildi" belgisi ham serverda
 * (`/owner/notifications`): ega telefonda ko'rgan xabar kompyuterda
 * ham o'qilgan bo'lib turishi kerak.
 */
function NotificationBell({ siteId, onOpenEvent }: { siteId: string; onOpenEvent: () => void }) {
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [items, setItems] = useState<Notification[] | null>(null);
  const [error, setError] = useState("");
  const box = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    try {
      const data = await api<{ unread: number; events: Notification[] }>("/api/v1/owner/notifications?limit=20", "owner", { siteId });
      setUnread(data.unread || 0);
      setItems(data.events || []);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("panel.owner.notif_load_failed"));
    }
  }, [siteId]);

  /* Qo'ng'iroq dashboard'dan ALOHIDA so'raladi: dashboard og'ir
     (salomatlik, hisobot, obuna), qo'ng'iroq esa tez-tez yangilanishi
     kerak.  60 soniya — yangi hodisa Telegramga ham shu atrofda
     boradi, ya'ni panel undan orqada qolmaydi. */
  useEffect(() => {
    if (!siteId) return;
    void load();
    const timer = window.setInterval(() => { void load(); }, 60000);
    return () => window.clearInterval(timer);
  }, [load, siteId]);

  // Tashqariga bosish va Escape — `ActionMenu` dagi bilan bir xil naqsh.
  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => { if (!box.current?.contains(event.target as Node)) setOpen(false); };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", escape); };
  }, [open]);

  /* Fokus panelga KIRADI va yopilganda qo'ng'iroqqa QAYTADI.
     `Modal` dagi `useFocusTrap` bu yerda ATAYLAB ishlatilmaydi: bu
     modal emas, ochiladigan menyu — Tab bilan undan chiqib ketish
     TO'G'RI xatti-harakat.  Yetishmagani faqat ikkita: ochilganda
     klaviatura paneldan boshlanishi va yopilganda fokus yo'qolmasligi
     (Escape'dan keyin odam sahifa boshiga tashlanardi). */
  useEffect(() => {
    if (!open) return;
    const bell = box.current?.querySelector<HTMLElement>("button.topbar-bell");
    const first = box.current?.querySelector<HTMLElement>(".notif-panel button, .notif-panel a");
    first?.focus();
    return () => { if (bell?.isConnected) bell.focus(); };
  }, [open]);

  const markRead = async () => {
    /* Son DARHOL nolga tushadi, server javobini kutmasdan: tugma
       bosilganda hech narsa o'zgarmasa foydalanuvchi uni yana bosadi.
       So'rov yiqilsa keyingi `load()` haqiqatni qaytaradi. */
    setUnread(0);
    setItems(current => current?.map(item => ({ ...item, unread: false })) || null);
    try {
      await api("/api/v1/owner/notifications/read", "owner", { method: "POST", siteId });
    } catch {
      void load();
    }
  };

  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next) void load();
  };

  return <div className="notif-wrap" ref={box}>
    <button className="btn btn-icon topbar-bell" aria-expanded={open} onClick={toggle} aria-label={unread ? t("panel.owner.notif_aria_unread", { count: unread }) : t("panel.owner.notifications")}>
      <Icon name="bell"/>
      {unread ? <i className="bell-badge">{unread > 9 ? "9+" : unread}</i> : null}
    </button>
    {open ? <div className="notif-panel" role="dialog" aria-label={t("panel.owner.notifications")}>
      <div className="notif-head">
        <b>{unread ? t("panel.owner.notif_unread_count", { count: formatNumber(unread) }) : t("panel.owner.notif_none")}</b>
        {unread ? <button className="btn btn-small" onClick={() => void markRead()}>{t("panel.owner.notif_mark_read")}</button> : null}
      </div>
      {error ? <p className="notif-empty">{error}</p> : null}
      {items === null ? <div className="notif-empty"><Skeleton height={60}/></div>
        : items.length ? <ul className="notif-list">
            {items.map(item => <li key={item.event_id} className={item.unread ? "is-unread" : ""}>
              {/* Nuqta faqat RANG bilan gapirardi: rang ko'rmaydigan
                  odam uchun muhim va oddiy xabar bir xil ko'rinardi.
                  Matn ko'rinmas, lekin skrinrider o'qiydi. */}
              <span className={`notif-dot sev-${item.severity || "info"}`} aria-label={t(`panel.owner.severity_${item.severity || "info"}`)} role="img"/>
              <div>
                <b>{item.label || item.event_type}</b>
                <small>{item.camera_id || t("panel.home.events.system")} · {formatTimeUz(item.occurred_at)}</small>
              </div>
            </li>)}
          </ul>
        /* Bo'sh holat AYBLAMAYDI: ogohlantirish yo'qligi yaxshi
           xabar, "hech narsa topilmadi" esa buzuqday ko'rinadi. */
        : <p className="notif-empty">{t("panel.owner.notif_empty")}</p>}
      <button className="btn btn-wide" onClick={() => { setOpen(false); onOpenEvent(); }}>{t("panel.owner.notif_view_all")}</button>
    </div> : null}
  </div>;
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
        setError(reason instanceof Error ? reason.message : t("panel.employees.load_failed"));
      }
    }
  },[siteId]);
  useEffect(() => { void load(); }, [load]);
  const create = async (event:React.FormEvent<HTMLFormElement>) => { event.preventDefault();const form=event.currentTarget;const data=new FormData(form);setBusy(true);setError("");try{await api("/api/v1/owner/employees","owner",{method:"POST",siteId,body:JSON.stringify({name:String(data.get("name")||""),external_id:String(data.get("external_id")||"")||null,consent:data.get("consent")==="on",consent_note:t("panel.employees.consent_note")})});form.reset();setAdding(false);await load();}catch(reason){setError(reason instanceof Error?reason.message:t("panel.employees.create_failed"));}finally{setBusy(false);}};
  const uploadFace = async (employee:Employee, file?:File) => {
    if (!file) return;
    setUploading(employee.id); setError("");
    try {
      /* PNG o'z holicha ketadi (shaffoflik yo'qolmasin), qolgani —
         HEIC ham, katta JPEG ham — brauzerda JPEG ga aylantiriladi.
         Usiz iPhone'dan yuklab bo'lmasdi: server HEIC'ni 415 bilan
         rad etadi. */
      const payload = file.type === "image/png" ? file : await toJpeg(file);
      const type = file.type === "image/png" ? "image/png" : "image/jpeg";
      await api(`/api/v1/owner/faces/employees/${encodeURIComponent(employee.id)}/photos`,"owner",{method:"POST",siteId,headers:{"Content-Type":type},body:payload});
      await load();
    } catch(reason) { setError(reason instanceof Error?reason.message:t("panel.employees.photo_failed")); }
    finally { setUploading(""); }
  };
  return <><PageHeader title={t("panel.nav.employees")} subtitle={t("panel.employees.subtitle")} actions={<button className="btn btn-primary" onClick={()=>setAdding(value=>!value)}><Icon name="users"/><span>{adding?t("panel.common.cancel"):t("panel.employees.add")}</span></button>}/>{adding?<Card className="employee-form"><form className="card-body" onSubmit={create}><div className="form-grid"><label>{t("panel.employees.full_name")}<input className="input" name="name" minLength={2} required/></label><label>{t("panel.employees.external_id_optional")}<input className="input" name="external_id"/></label></div><label className="consent-row"><input type="checkbox" name="consent" required/><span>{t("panel.employees.consent_text")}</span></label><button className="btn btn-primary" disabled={busy}>{busy?t("panel.common.saving"):t("panel.employees.save")}</button></form></Card>:null}{error?<div className="alert-strip"><Icon name="bell"/><div><strong>{t("panel.employees.error_prefix")}</strong> {error}</div></div>:null}<Card><div className="card-head"><div><h2>{t("panel.employees.list_title")}</h2><p>{t("panel.employees.list_subtitle")}</p></div></div>{items === null ? <div className="card-body"><Skeleton height={180}/></div> : items.length ? <div className="table-wrap"><table><thead><tr><th>{t("panel.employees.col_employee")}</th><th>{t("panel.employees.col_external_id")}</th><th>{t("panel.employees.col_face_id")}</th><th>{t("panel.employees.col_status")}</th><th>{t("panel.employees.col_action")}</th></tr></thead><tbody>{items.map(item => <tr key={item.id}><td><div className="table-title">{item.name || t("panel.employees.unnamed")}</div></td><td>{item.external_id || "—"}</td><td>{item.enrollment_status==="enrolled"?t("panel.employees.templates_count",{count:item.photos?.length || 1}):t("panel.employees.not_enrolled")}</td><td><Pill state={item.active === false ? "offline" : "active"}>{item.active === false ? t("panel.employees.inactive") : t("panel.employees.active")}</Pill></td><td><label className={`btn upload-btn ${uploading===item.id?"disabled":""}`}>{uploading===item.id?t("panel.common.loading"):t("panel.employees.upload_photo")}<input type="file" accept="image/*" capture="user" disabled={Boolean(uploading)} onChange={event=>{void uploadFace(item,event.target.files?.[0]);event.currentTarget.value="";}}/></label></td></tr>)}</tbody></table></div> : <EmptyState icon="users" title={t("panel.employees.empty_title")} detail={t("panel.employees.empty_detail")}/>}</Card></>;
}

function BillingPage({dashboard,siteId}:{dashboard:Dashboard;siteId:string}) {
  const [invoices,setInvoices]=useState<Invoice[]|null>(null);const[months,setMonths]=useState(1);const[busy,setBusy]=useState(false);const[error,setError]=useState("");
  // Xatoda ro'yxat BO'SH: `null` skelet degani va u abadiy qolardi.
  const load=useCallback(()=>api<Invoice[]>("/api/v1/owner/invoices","owner",{siteId}).then(data=>{setInvoices(data);setError("");}).catch(reason=>{setInvoices([]);setError(reason instanceof Error?reason.message:t("panel.billing.load_failed"));}),[siteId]);
  useEffect(()=>{void load();},[load]);
  const create=async()=>{setBusy(true);setError("");try{const invoice=await api<Invoice>("/api/v1/owner/invoices","owner",{method:"POST",siteId,body:JSON.stringify({months})});setInvoices(current=>[invoice,...(current||[])]);}catch(reason){setError(reason instanceof Error?reason.message:t("panel.billing.create_failed"));}finally{setBusy(false);}};
  return <><PageHeader title={t("panel.nav.billing")} subtitle={t("panel.billing.subtitle")}/><div className="dashboard-grid"><Card><div className="card-head"><div><h2>{dashboard.site.plan?.name || t("panel.billing.current_plan")}</h2><p>{t("panel.billing.plan_note")}</p></div><Pill state={dashboard.subscription?.status}>{dashboard.subscription?.status || "—"}</Pill></div><div className="card-body"><div className="metric-value">{formatMoney(dashboard.subscription?.monthly_price_uzs)}</div><p className="metric-note">{t("panel.billing.per_month")} · {dashboard.subscription?.days_left==null?t("panel.billing.term_unknown"):t("panel.billing.days_left",{count:dashboard.subscription.days_left})}</p><div className="invoice-create"><select className="select" value={months} onChange={event=>setMonths(Number(event.target.value))} aria-label={t("panel.billing.term_aria")}>{[1,3,6,12].map(count=><option value={count} key={count}>{t("panel.shell.months_count",{count})}</option>)}</select><button className="btn btn-primary" disabled={busy} onClick={()=>void create()}>{busy?t("panel.billing.creating"):t("panel.billing.create_invoice")}</button></div></div></Card><Card><div className="card-head"><div><h2>{t("panel.billing.how_title")}</h2><p>{t("panel.billing.how_subtitle")}</p></div></div><div className="card-body"><p className="metric-note">{t("panel.billing.how_note")}</p></div></Card></div>{error?<ErrorStrip className="section-gap" title={t("panel.billing.error_prefix")} detail={error} onRetry={()=>{setInvoices(null);void load();}}/>:null}<Card className="section-gap"><div className="card-head"><div><h2>{t("panel.billing.invoices_title")}</h2><p>{t("panel.billing.invoices_subtitle")}</p></div></div>{invoices===null?<div className="card-body"><Skeleton height={140}/></div>:invoices.length?<div className="table-wrap"><table><thead><tr><th>{t("panel.billing.col_number")}</th><th>{t("panel.billing.col_term")}</th><th>{t("panel.billing.col_amount")}</th><th>{t("panel.billing.col_state")}</th><th>{t("panel.billing.col_date")}</th><th>{t("panel.billing.col_action")}</th></tr></thead><tbody>{invoices.map(invoice=><tr key={invoice.id}><td><div className="table-title">#{invoice.id}</div></td><td>{t("panel.shell.months_count",{count:invoice.months})}</td><td>{formatMoney(invoice.amount_uzs,{short:false})}</td><td><Pill state={invoice.state}>{invoice.state==="paid"?t("panel.billing.state_paid"):invoice.state==="pending"?t("panel.billing.state_pending"):t("panel.billing.state_cancelled")}</Pill></td><td>{formatDateShort(invoice.created_at)}</td><td>{invoice.state==="pending"&&invoice.pay_url?<a className="btn" href={invoice.pay_url} target="_blank" rel="noreferrer">{t("panel.common.open")}</a>:"—"}</td></tr>)}</tbody></table></div>:<EmptyState icon="invoice" title={t("panel.billing.empty_title")} detail={t("panel.billing.empty_detail")}/>}</Card></>;
}

function TelegramPage({siteId}:{siteId:string}) {
  const [members,setMembers]=useState<TelegramMember[]|null>(null);const[role,setRole]=useState<"owner"|"manager">("manager");const[name,setName]=useState("");const[invite,setInvite]=useState<{url:string;expires_minutes:number}|null>(null);const[busy,setBusy]=useState(false);const[error,setError]=useState("");const[confirm,confirmDialog]=useConfirm();
  const load=useCallback(()=>api<{members:TelegramMember[]}>("/api/v1/owner/members","owner",{siteId}).then(data=>{setMembers(data.members||[]);setError("");}).catch(reason=>{setMembers([]);setError(reason instanceof Error?reason.message:t("panel.telegram.members_load_failed"));}),[siteId]);
  useEffect(()=>{void load();},[load]);
  const createInvite=async()=>{setBusy(true);setError("");try{const result=await api<{url:string;expires_minutes:number}>("/api/v1/owner/telegram-invite","owner",{method:"POST",siteId,body:JSON.stringify({role,display_name:name.trim()||null})});setInvite(result);}catch(reason){setError(reason instanceof Error?reason.message:t("panel.telegram.invite_failed"));}finally{setBusy(false);}};
  /* Brauzerning o'z tasdiq oynasi emas, admin paneldagi bilan bir xil
     `ConfirmDialog`: brauzer oynasi panel tiliga bo'ysunmaydi va
     Telegram WebView'ida umuman ko'rinmasligi mumkin — tugma bosilib,
     hech narsa bo'lmasdi. */
  const remove=async(member:TelegramMember)=>{if(!(await confirm({title:t("panel.telegram.remove_title"),text:t("panel.telegram.remove_text",{name:member.display_name||member.telegram_id}),confirmLabel:t("panel.common.delete"),danger:true})))return;setError("");try{await api(`/api/v1/owner/members/${encodeURIComponent(member.id)}`,"owner",{method:"DELETE",siteId});await load();}catch(reason){setError(reason instanceof Error?reason.message:t("panel.telegram.remove_failed"));}};
  return <><PageHeader title={t("panel.nav.telegram")} subtitle={t("panel.telegram.subtitle")}/><div className="dashboard-grid"><Card><div className="card-head"><div><h2>{t("panel.telegram.invite_title")}</h2><p>{t("panel.telegram.invite_subtitle")}</p></div></div><div className="card-body"><div className="form-grid"><label>{t("panel.telegram.for_whom")}<select className="select" value={role} onChange={event=>setRole(event.target.value as "owner"|"manager")}><option value="manager">{t("panel.telegram.role_manager")}</option><option value="owner">{t("panel.telegram.role_owner_option")}</option></select></label><label>{t("panel.telegram.name_optional")}<input className="input" value={name} onChange={event=>setName(event.target.value)} maxLength={120}/></label></div><button className="btn btn-primary" disabled={busy} onClick={()=>void createInvite()}>{busy?t("panel.telegram.creating"):t("panel.telegram.create_invite")}</button>{invite?<div className="invite-result"><b>{t("panel.telegram.invite_ready",{count:invite.expires_minutes})}</b><a href={invite.url} target="_blank" rel="noreferrer">{invite.url}</a><div className="page-actions"><CopyButton value={invite.url}/><a className="btn btn-primary" href={invite.url} target="_blank" rel="noreferrer">{t("panel.telegram.open_in_telegram")}</a></div></div>:null}</div></Card><Card><div className="card-head"><div><h2>{t("panel.telegram.what_title")}</h2><p>{t("panel.telegram.what_subtitle")}</p></div></div><div className="card-body"><p className="metric-note">{t("panel.telegram.what_note")}</p></div></Card></div>{error?<ErrorStrip title={t("panel.telegram.error_prefix")} detail={error} onRetry={()=>{setMembers(null);void load();}}/>:null}<Card className="section-gap"><div className="card-head"><div><h2>{t("panel.telegram.members_title")}</h2><p>{t("panel.telegram.members_subtitle")}</p></div></div>{members===null?<div className="card-body"><Skeleton height={130}/></div>:members.length?<div className="table-wrap"><table><thead><tr><th>{t("panel.telegram.col_user")}</th><th>{t("panel.telegram.col_role")}</th><th>{t("panel.telegram.col_digest")}</th><th>{t("panel.telegram.col_action")}</th></tr></thead><tbody>{members.map(member=><tr key={member.id}><td><div className="table-title">{member.display_name||t("panel.telegram.member_fallback",{id:member.telegram_id})}</div></td><td>{member.role==="owner"?t("panel.telegram.role_owner"):member.role==="manager"?t("panel.telegram.role_manager"):t("panel.telegram.role_service_admin")}</td><td>{member.digest_muted?t("panel.telegram.digest_off"):t("panel.telegram.digest_on")}</td><td><button className="btn btn-danger" onClick={()=>void remove(member)}>{t("panel.common.delete")}</button></td></tr>)}</tbody></table></div>:<EmptyState icon="bell" title={t("panel.telegram.empty_title")} detail={t("panel.telegram.empty_detail")}/>}</Card>{confirmDialog}</>;
}

function downloadTrafficCsv(dashboard:Dashboard) {
  const rows = dashboard.trend.map(point=>[point.date||point.day||"",point.entries??point.entered??point.count??0]);
  const csv = [[t("panel.download.csv_col_date"),t("panel.download.csv_col_entered")].join(","),...rows.map(row=>row.join(","))].join("\n");
  downloadCsv(csv, t("panel.download.traffic_csv_filename",{site:dashboard.site.id}));
}

/* Kunning to'liq hisobotini serverdan Excelda ochiladigan CSV qilib oladi.
 * `downloadTrafficCsv` klientda faqat 14 kunlik oqimni beradi; bu esa
 * bitta kunning YAKUNI \u2014 kirdi/chiqdi, eshik, konversiya, mijoz portreti
 * va xavfsizlik.  Raqamlar serverda hisoblangani uchun panel bilan bir
 * xil bo'ladi (docs/RAQOBAT_RETAILSOLUTION.md).  `<a download>` Bearer
 * yubora olmaydi, shu sabab autentifikatsiyalangan `mediaObjectUrl`. */
async function downloadDailyReportCsv(siteId:string) {
  const today = new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Tashkent" });
  const url = await mediaObjectUrl("/api/v1/owner/report.csv", "owner", siteId);
  downloadBlobUrl(url, t("panel.download.daily_filename",{date:today}));
}

/* Oxirgi 30 kunning davriy hisoboti — raqobatchining oylik branch-summary
 * Exceliga to'g'ri keladi (kuniga bitta qator + jami).  Sana hisobi
 * Toshkent kunida: `en-CA` YYYY-MM-DD beradi, `limits.py: formatTimeUz`
 * bilan bir xil sabab (Intl'siz UTC+5). */
async function downloadPeriodReportCsv(siteId:string) {
  const tz = { timeZone: "Asia/Tashkent" } as const;
  const end = new Date().toLocaleDateString("en-CA", tz);
  const startDate = new Date(); startDate.setDate(startDate.getDate() - 29);
  const start = startDate.toLocaleDateString("en-CA", tz);
  const url = await mediaObjectUrl(`/api/v1/owner/report.csv?start=${start}&end=${end}`, "owner", siteId);
  downloadBlobUrl(url, t("panel.download.period_filename",{start,end}));
}

type Navigate = (id: string, param?: string, sub?: string) => void;

/** Kamera ID naqshi — server bilan bir xil (`cloud/main.py`: `^camera-\\d{2}$`).
 *  `cameras` bo'limida ikkinchi segment tab NOMI ham, kamera ID ham
 *  bo'lishi mumkin; shundan ajratiladi. */
const CAMERA_ID = /^camera-\d{2}$/;

/** Bo'lim tablari — faol tab manzildan (`param`), bosilsa manzil o'zgaradi. */
function SectionTabs({ section, tab, onNavigate, hidden = [] }: { section: string; tab: string; onNavigate: Navigate; hidden?: string[] }) {
  /* `TABS` ro'yxatining O'ZI o'zgarmaydi — tab shu yerda chiqarib
     tashlanadi.  Sabab: manzil xaritasi (`LEGACY_ROUTES`) va testlar
     o'sha literalga bog'langan, ya'ni ro'yxatni tahrirlash eski
     havolalarni uzardi. */
  const ids = (TABS[section] || []).filter(id => !hidden.includes(id));
  if (ids.length < 2) return null;
  return <Tabs items={ids.map(id => ({ id, label: t(`panel.tabs.${id}`) }))} active={tab} onSelect={id => onNavigate(section, id)} panelId="section-panel" />;
}

function BranchesPage({ sites }: { sites: Site[] }) {
  // Bitta do'kon — bo'sh to'r emas, nima uchun bo'shligi va keyingi qadam.
  if (sites.length < 2) return <><PageHeader title={t("panel.nav.branches")} subtitle={t("panel.owner.branches_subtitle")}/><Card><EmptyState icon="store" title={t("panel.branches.single_title")} detail={t("panel.branches.single_detail")}/></Card></>;
  return <><PageHeader title={t("panel.nav.branches")} subtitle={t("panel.owner.branches_subtitle")}/><div className="metric-grid">{sites.map(site => <StatCard key={site.id} label={site.name} value={`${formatNumber(site.cameras_active)} / ${formatNumber(site.cameras_expected)}`} note={site.address || (site.connection === "online" ? t("panel.owner.branch_online") : t("panel.owner.branch_check"))} icon="branch" tone={site.connection === "online" ? "green" : "red"}/>)}</div></>;
}

function ReportsPage({ dashboard, siteId, onNavigate }: { dashboard: Dashboard; siteId: string; onNavigate: Navigate }) {
  /* Yuklash yiqilsa ega buni KO'RSIN: ilgari rad etilgan va'da hech
     qayerda ushlanmas, tugma shunchaki «bosilmas» edi. */
  const [toast, toastNode] = useToast();
  const [busy, setBusy] = useState("");
  const download = async (kind: "daily" | "period") => {
    if (busy) return;
    setBusy(kind);
    try { await (kind === "daily" ? downloadDailyReportCsv(siteId) : downloadPeriodReportCsv(siteId)); }
    catch (reason) { toast(reason instanceof Error ? reason.message : t("panel.download.failed"), false); }
    finally { setBusy(""); }
  };
  /* Uchinchi tugma toastsiz qolgan edi: u ma'lumotni KLIENTDA yasaydi,
     ya'ni tarmoq xatosi bo'lmaydi — lekin `trend` bo'sh bo'lsa faqat
     sarlavhali fayl tushadi va ega nima bo'lganini bilmaydi. */
  const downloadTrend = () => {
    if (!dashboard.trend.length) { toast(t("panel.download.empty"), false); return; }
    try { downloadTrafficCsv(dashboard); }
    catch (reason) { toast(reason instanceof Error ? reason.message : t("panel.download.failed"), false); }
  };
  return <>{toastNode}<PageHeader title={t("panel.nav.reports")} subtitle={t("panel.owner.reports_subtitle")} actions={<><button className="btn btn-primary" disabled={Boolean(busy)} onClick={()=>void download("daily")}><Icon name="download"/>{t("panel.download.daily_csv")}</button><button className="btn" disabled={Boolean(busy)} onClick={()=>void download("period")}><Icon name="download"/>{t("panel.download.period_csv")}</button><button className="btn" onClick={downloadTrend}><Icon name="report"/>{t("panel.download.traffic_csv")}</button></>}/><div className="metric-grid"><StatCard label={t("panel.owner.metric_visits_today")} value={formatNumber(value(dashboard.today,"traffic.entered","entered","entries","visitors"))} icon="users"/><StatCard label={t("panel.owner.metric_queue")} value={formatNumber(value(dashboard.today,"queue.alerts","queue_events","queue_alerts"))} icon="bell" tone="yellow"/><StatCard label={t("panel.home.stat.cameras")} value={formatNumber(dashboard.site.cameras_active)} icon="camera" tone="green"/><StatCard label={t("panel.nav.alerts")} value={formatNumber(dashboard.events.length)} icon="shield" tone="blue"/></div><Numbers dashboard={dashboard} siteId={siteId}/><Card><div className="card-head"><div><h2>{t("panel.owner.trend_title")}</h2><p>{t("panel.owner.trend_note")}</p></div></div><TrendChart points={dashboard.trend}/></Card><Demography dashboard={dashboard} siteId={siteId} onNavigate={onNavigate}/></>;
}

/** Bo'lim sahifasi: tab qatori + tanlangan sahifa.
 *
 *  Har ichki sahifa o'z `PageHeader`ini chizadi (ular ilgari alohida
 *  bo'lim edi) — tab qatori undan TEPADA turadi, sahifaning o'zi
 *  o'zgarmaydi. */
function SectionPage({ id, tab, dashboard, sites, siteId, onNavigate, onRefresh, focusEventId = "", cameraId = "", cameraTab = "" }: { id:string; tab:string; dashboard:Dashboard; sites:Site[]; siteId:string; onNavigate:Navigate; onRefresh:()=>void; focusEventId?:string; cameraId?:string; cameraTab?:string }) {
  /* AI yordamchi Gemini kaliti qo'yilmagan do'konda YASHIRINADI.
     Bungacha tab ochilar, har savol xato bilan tugar va ega
     «buzuq» deb o'ylardi — jonli bazada `vision_observations` = 0.
     Qaror serverda (`capabilities.agent`), panelda ikkinchi shart
     yozilmaydi. */
  const agentReady = dashboard.capabilities?.agent?.ready !== false;
  const tabs = <SectionTabs section={id} tab={tab} onNavigate={onNavigate} hidden={agentReady ? [] : ["agent"]}/>;
  /* Tab tarkibi `role="tabpanel"` ichida: skrinrider tugmani «tab» deb
     o'qib, bosilgandan keyin qayerga borganini aytmasdi.  `Panel`
     yordamchisi shu faylda — `tab` har branchda bir xil. */
  const Panel = ({ children }: { children: React.ReactNode }) => <TabPanel id="section-panel" activeTab={tab}>{children}</TabPanel>;
  /* Alohida kamera sahifasi — bo'lim tablarisiz, o'z tablari bilan. */
  if (id === "cameras" && cameraId) return <CameraDetail dashboard={dashboard} siteId={siteId} cameraId={cameraId} tab={cameraTab || "live"} onNavigate={onNavigate}/>;
  if (id === "cameras") return <>{tabs}<Panel>{
    tab === "setup" ? <SetupCameras siteId={siteId} onDone={() => { onRefresh(); onNavigate("cameras", "zones"); }}/>
    : tab === "zones" ? <GeometryEditor siteId={siteId} cameras={dashboard.cameras}/>
    : <><PageHeader title={t("panel.nav.cameras")} subtitle={t("panel.cameras.page_subtitle")}/><CamerasBlock dashboard={dashboard} siteId={siteId} expanded onOpenCamera={id => onNavigate("cameras", id)}/></>}</Panel></>;
  if (id === "alerts") return <>{tabs}<Panel>{
    /* Manzilga TO'G'RIDAN-TO'G'RI kirilsa (eski havola, xatcho'p)
       bo'sh holat ko'rsatiladi — tab yashiringani sahifani ochib
       bo'lmaydi degani emas, sababini aytish kerak. */
    tab === "agent" ? (agentReady
      ? <VisionAgent siteId={siteId} onNavigate={onNavigate}/>
      : <><PageHeader title={t("panel.tabs.agent")} subtitle={t("panel.agent.subtitle")}/><Card><EmptyState icon="pulse" title={t("panel.agent.off_title")} detail={dashboard.capabilities?.agent?.reason || t("panel.agent.off_detail")}/></Card></>)
    : <EventEvidence kind="owner" siteId={siteId} focusEventId={focusEventId} dashboard={dashboard} onNavigate={onNavigate}/>}</Panel></>;
  if (id === "customers") return <>{tabs}<Panel>{
    tab === "heatmap" ? <HeatmapPage dashboard={dashboard} siteId={siteId} onNavigate={onNavigate}/>
    : tab === "demography" ? <><PageHeader title={t("panel.tabs.demography")} subtitle={t("panel.customers.demography_subtitle")}/><Demography dashboard={dashboard} siteId={siteId} onNavigate={onNavigate}/></>
    : <TrafficPage dashboard={dashboard}/>}</Panel></>;
  if (id === "settings") return <>{tabs}<Panel>{
    tab === "telegram" ? <TelegramPage siteId={siteId}/>
    : tab === "billing" ? <BillingPage dashboard={dashboard} siteId={siteId}/>
    : tab === "branches" ? <BranchesPage sites={sites}/>
    : <SettingsPage dashboard={dashboard} sites={sites} siteId={siteId} onNavigate={onNavigate} onRefresh={onRefresh}/>}</Panel></>;
  if (id === "analytics") return <Analytics dashboard={dashboard} siteId={siteId} onNavigate={onNavigate}/>;
  if (id === "reports") return <ReportsPage dashboard={dashboard} siteId={siteId} onNavigate={onNavigate}/>;
  return <><PageHeader title={t("panel.owner.section_title")} subtitle={t("panel.owner.section_subtitle")}/><Card><EmptyState icon="settings" title={t("panel.owner.section_empty_title")} detail={t("panel.owner.section_empty_detail")}/></Card></>;
}

/** Oqim sahifasi: bugungi soatlik egri va 14 kunlik dinamika. */
function TrafficPage({ dashboard }: { dashboard: Dashboard }) {
  const traffic = ((dashboard.today as Record<string, unknown>).traffic || {}) as Record<string, unknown>;
  const hourly = Array.isArray(traffic.hourly) ? (traffic.hourly as { hour:number; entered:number; exited:number }[]) : [];
  const hourPoints: Point[] = hourly.map(item => ({ label: `${String(item.hour).padStart(2,"0")}:00`, value: Number(item.entered) || 0 }));
  const exitPoints: Point[] = hourly.map(item => ({ label: `${String(item.hour).padStart(2,"0")}:00`, value: Number(item.exited) || 0 }));
  return <>
    <PageHeader title={t("panel.nav.customers")} subtitle={t("panel.customers.subtitle")}/>
    <Card>
      <div className="card-head"><div><h2>{t("panel.home.flow.subtitle")}</h2><p>{t("panel.traffic.hourly_subtitle")}</p></div></div>
      {hourPoints.some(point => point.value > 0)
        ? <LineChart series={[{ name: t("panel.numbers.entered"), points: hourPoints }, { name: t("panel.numbers.exited"), points: exitPoints }]}/>
        : <EmptyState icon="chart" title={t("panel.home.flow.empty_title")} detail={t("panel.home.flow.empty_detail")}/>}
    </Card>
    <Card className="section-gap">
      <div className="card-head"><div><h2>{t("panel.traffic.last_14_days")}</h2><p>{t("panel.traffic.daily_dynamics")}</p></div></div>
      <TrendChart points={dashboard.trend}/>
    </Card>
  </>;
}

/** Telegramga qaysi hodisalar borsin.
 *
 * Ilgari bu kodda qotirilgan edi (faqat `critical`) va hech qayerda
 * aytilmasdi.  2026-08-26 da sinov do'konida 449 hodisadan 9 tasi botga
 * bordi — ega "bot buzilgan" deb o'yladi, chunki qolgan 440 tasi jimgina
 * panelda qolgani hech qanday joyda yozilmagan edi. */
/* `label`/`note` — katalog kalitlari, `NAV_ITEMS` dagi bilan bir xil
   sabab: modul yuklanganda til hali tanlanmagan. */
const TELEGRAM_LEVELS = [
  { id: "critical", label: "panel.telegram.level_critical", note: "panel.telegram.level_critical_note" },
  { id: "warning", label: "panel.telegram.level_warning", note: "panel.telegram.level_warning_note" },
  { id: "all", label: "panel.common.all", note: "panel.telegram.level_all_note" },
] as const;

function TelegramLevelPicker({ siteId }: { siteId: string }) {
  const [config, setConfig] = useState<Record<string, unknown> | null>(null);
  const [saving, setSaving] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let stopped = false;
    api<{ config: Record<string, unknown> }>("/api/v1/owner/config", "owner", { siteId })
      .then(answer => { if (!stopped) setConfig(answer.config); })
      .catch(() => { if (!stopped) setError(t("panel.telegram.level_load_failed")); });
    return () => { stopped = true; };
  }, [siteId]);

  const choose = async (level: string) => {
    if (!config || saving) return;
    setSaving(level); setError("");
    try {
      /* `...config` SHART: validator TO'LIQ hujjatni kutadi — faqat bitta
         maydon yuborilsa ish vaqti, zona va davomat sozlamalari standart
         qiymatga qaytardi (GeometryEditor'dagi bilan bir xil tuzoq). */
      await api("/api/v1/owner/config", "owner", {
        method: "PUT", siteId,
        body: JSON.stringify({ ...config, telegram_min_severity: level }),
      });
      setConfig({ ...config, telegram_min_severity: level });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("panel.telegram.level_save_failed"));
    } finally { setSaving(""); }
  };

  const current = String(config?.telegram_min_severity || "critical");
  return <div className="simple-list">
    {TELEGRAM_LEVELS.map(level => <button
      key={level.id}
      className={`simple-row level-row${current === level.id ? " is-active" : ""}`}
      disabled={!config || Boolean(saving)}
      onClick={() => void choose(level.id)}
    >
      <div><b>{t(level.label)}</b><div className="table-sub">{t(level.note)}</div></div>
      {current === level.id ? <Pill state="active">{t("panel.telegram.level_selected")}</Pill> : null}
    </button>)}
    {error ? <p className="media-error">{error}</p> : null}
  </div>;
}

/** Sozlamalar: hozircha faqat HAQIQATAN mavjud bo'lgan ma'lumot.
 *  Ilgari bu sahifa bo'sh "ish olib borilmoqda" yozuvi edi. */
/** Ish vaqti — tungi nazoratning kaliti.
 *
 *  Qurilma `open_from/open_to` ni allaqachon tushunadi (`enes/settings.py`),
 *  lekin 2026-09-10 gacha uni faqat o'rnatuvchining sozlash ustasi
 *  yozardi — ega panelida maydon YO'Q edi.  Ya'ni o'rnatuvchi
 *  o'tkazib yuborsa tungi nazorat jimgina o'chiq turardi. */
function StoreHoursCard({ siteId, onSaved }: { siteId: string; onSaved: () => void }) {
  const [config, setConfig] = useState<Record<string, unknown> | null>(null);
  const [from, setFrom] = useState(""); const [to, setTo] = useState("");
  const [busy, setBusy] = useState(false); const [error, setError] = useState(""); const [saved, setSaved] = useState(false);
  useEffect(() => {
    let stopped = false;
    api<{ config: Record<string, unknown> }>("/api/v1/owner/config", "owner", { siteId })
      .then(answer => { if (stopped) return; setConfig(answer.config); setFrom(String(answer.config.open_from || "")); setTo(String(answer.config.open_to || "")); })
      .catch(() => { if (!stopped) setError(t("panel.telegram.level_load_failed")); });
    return () => { stopped = true; };
  }, [siteId]);
  const enabled = Boolean(config?.open_from && config?.open_to);
  const save = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!config || busy) return;
    if (Boolean(from) !== Boolean(to)) { setError(t("panel.settings.hours.both_required")); return; }
    setBusy(true); setError(""); setSaved(false);
    try {
      /* `...config` SHART — `TelegramLevelPicker` dagi bilan bir xil tuzoq:
         validator to'liq hujjatni kutadi. */
      const next = { ...config, open_from: from || null, open_to: to || null };
      await api("/api/v1/owner/config", "owner", { method: "PUT", siteId, body: JSON.stringify(next) });
      setConfig(next); setSaved(true); onSaved();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("panel.settings.hours.save_failed"));
    } finally { setBusy(false); }
  };
  return <Card>
    <div className="card-head">
      <div><h2>{t("panel.settings.hours.title")}</h2><p>{t("panel.settings.hours.subtitle")}</p></div>
      {/* Sozlama hali kelmagan (yoki kelmadi) — «ish vaqti kiritilmagan»
          deb aytish yolg'on bo'lardi. */}
      {config === null ? <Skeleton height={26}/> : <Pill state={enabled ? "active" : "pending"}>{t(enabled ? "panel.settings.hours.night_on" : "panel.settings.hours.night_off")}</Pill>}
    </div>
    <form className="card-body" onSubmit={save}>
      <div className="form-grid">
        <label>{t("panel.settings.hours.from")}<input className="input" type="time" value={from} disabled={!config} onChange={event => { setFrom(event.target.value); setSaved(false); }}/></label>
        <label>{t("panel.settings.hours.to")}<input className="input" type="time" value={to} disabled={!config} onChange={event => { setTo(event.target.value); setSaved(false); }}/></label>
      </div>
      <p className="metric-note">{t("panel.settings.hours.note")}</p>
      <div className="page-actions wrap">
        <button className="btn btn-primary" disabled={!config || busy}>{busy ? t("panel.common.saving") : t("panel.settings.hours.save")}</button>
        {saved ? <span className="metric-note">{t("panel.settings.hours.saved")}</span> : null}
      </div>
      {error ? <p className="media-error">{error}</p> : null}
    </form>
  </Card>;
}

function SettingsPage({ dashboard, sites, siteId, onNavigate, onRefresh }: { dashboard: Dashboard; sites: Site[]; siteId: string; onNavigate: Navigate; onRefresh: () => void }) {
  const site = sites.find(item => item.id === siteId);
  return <>
    <PageHeader title={t("panel.nav.settings")} subtitle={t("panel.settings.subtitle")}/>
    <div className="dashboard-grid">
      <Card>
        <div className="card-head"><div><h2>{t("panel.settings.store_title")}</h2><p>{t("panel.settings.store_subtitle")}</p></div></div>
        <div className="card-body">
          <div className="simple-row"><span>{t("panel.settings.name")}</span><b>{site?.name || dashboard.site.name}</b></div>
          <div className="simple-row"><span>{t("panel.settings.address")}</span><b>{site?.address || dashboard.site.address || "—"}</b></div>
          <div className="simple-row"><span>{t("panel.settings.plan")}</span><b>{dashboard.site.plan?.name || "—"}</b></div>
          <div className="simple-row"><span>{t("panel.nav.cameras")}</span><b>{t("panel.settings.cameras_up_to", { count: formatNumber(dashboard.site.cameras_expected) })}</b></div>
          <p className="metric-note">{t("panel.settings.store_note")}</p>
        </div>
      </Card>
      <StoreHoursCard siteId={siteId} onSaved={onRefresh}/>
      <Card>
        <div className="card-head"><div><h2>{t("panel.owner.notifications")}</h2><p>{t("panel.settings.notifications_subtitle")}</p></div></div>
        <div className="card-body">
          <TelegramLevelPicker siteId={siteId}/>
          <p className="metric-note">{t("panel.settings.digest_note")}</p>
          {/* `<a href>` EMAS: to'liq sahifa qayta yuklanishi va hash
              rejimida (`router.ts`) 404 beradi.  SPA ichida qolamiz. */}
          <button className="btn btn-wide" onClick={() => onNavigate("settings", "telegram")}>{t("panel.settings.telegram_members")}</button>
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
  const [active,navigateTo,routeParam,subRoute] = usePanelRoute("/owner", ROUTE_IDS, "home", LEGACY_ROUTES);
  const [drawer,setDrawer] = useState(false);
  const [focusEvent,setFocusEvent] = useState("");
  const [loginError,setLoginError] = useState(""); const [busy,setBusy] = useState(false);
  const {data,error,loading,refresh} = useAdaptiveDashboard(siteId,authenticated);
  /* Menejer «Xodimlar» bo'limini KO'RMAYDI: server unga `/owner/faces`,
     `/owner/employees` va `/owner/attendance` ni bermaydi
     (`cloud/main.py: require_biometric_access`), ya'ni bo'lim ochilsa
     faqat bo'sh jadval va xato satri chiqardi.  Rol filialga bog'liq —
     bitta odam bir do'konda ega, boshqasida menejer bo'lishi mumkin. */
  const role = sites.find(site => site.id === siteId)?.role || "";
  /* «Xodimlar» ikki sababdan yashirinadi: menejerga ko'rsatilmaydi
     (biometrika) va davomat serverda yoqilmagan bo'lsa umuman yo'q —
     bungacha bo'lim menyuda turar, ochilsa har so'rov 403 berardi va
     ega buni «buzuq» deb o'qirdi. */
  const attendanceReady = data?.capabilities?.attendance?.ready !== false;
  const visibleNav = useMemo(
    () => NAV_ITEMS.filter(item => item.id !== "employees" || (role !== "manager" && attendanceReady)),
    [role, attendanceReady],
  );
  /* Menyu yorliqlari shu yerda ochiladi (`NAV_ITEMS` izohiga qarang).
     Til almashsa sahifa qayta yuklanadi (`i18n/index.ts`), shuning uchun
     `t()` ni qayta hisoblash shart emas — faqat rol o'zgarganda. */
  const nav: NavItem[] = useMemo(() => visibleNav.map(({ id, key, icon }) => ({ id, icon, label: t(key) })), [visibleNav]);
  const mobileNav = useMemo(
    () => MOBILE_NAV.filter(id => id !== "employees" || (role !== "manager" && attendanceReady)),
    [role, attendanceReady],
  );

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
        if (!stopped) setLoginError(reason instanceof Error ? reason.message : t("panel.owner.link_login_failed"));
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
      else setLoginError(reason instanceof Error ? reason.message : t("panel.owner.sites_load_failed"));
    });
  }, [authenticated,loadSites]);

  const submit = async (username:string,password:string) => { setBusy(true);setLoginError("");try { await login(username,password,"owner");setAuthenticated(true); } catch(reason) { setLoginError(reason instanceof Error ? reason.message : t("panel.owner.login_failed")); } finally { setBusy(false); } };
  const logout = () => { void serverLogout("owner");setAuthenticated(false);setSites([]);setSiteId(""); };
  /* Ikkinchi argument — ochilishi kerak bo'lgan aniq hodisa.
     "Dalilni ochish" tugmasi shuni uzatadi. */
  /* Ikkinchi argument — tab NOMI yoki (Hodisalar uchun) ochilishi kerak
     bo'lgan hodisa ID'si: "Dalilni ochish" tugmasi `("alerts", eventId)`
     uzatadi.  Tab nomlari ro'yxatda, hodisa ID'si — yo'q; shundan
     ajratiladi. */
  const navigate = (id:string, param?:string, sub?:string) => {
    if (id === "more") { setDrawer(true); return; }
    const isTab = Boolean(param) && (TABS[id] || []).includes(String(param));
    /* Uchinchi tur parametr — kamera sahifasi: `/owner/cameras/camera-01/alerts`. */
    const isCamera = id === "cameras" && CAMERA_ID.test(String(param || ""));
    setFocusEvent(!isTab && !isCamera && id === "alerts" ? param || "" : "");
    navigateTo(id, isTab || isCamera ? param : "", isCamera && sub && (CAMERA_TABS as readonly string[]).includes(sub) ? sub : "");
    setDrawer(false); window.scrollTo({top:0,behavior:"smooth"});
  };
  const cameraId = active === "cameras" && CAMERA_ID.test(routeParam) ? routeParam : "";
  /* Manzilda tab bo'lmasa — bo'limning birinchi tabi. */
  const tab = (TABS[active] || []).includes(routeParam) ? routeParam : (TABS[active] || [""])[0];

  const splash = (title:string) => <div className="login-page"><section className="login-visual"><Logo/><div><span className="eyebrow">{t("panel.login.eyebrow_owner")}</span><h1>{title}</h1></div></section><section className="login-panel"><div style={{width:"min(390px,100%)"}}><Skeleton height={54}/><div style={{height:14}}/><Skeleton height={150}/></div></section></div>;
  if (checkingLink) return splash(t("panel.owner.splash_checking_link"));
  // Kompyuterni ulash oqimi login ekranidan OLDIN: dastur o'rnatilgach
  // brauzer aynan shu havolani ochadi va odam hali hisobga ega
  // bo'lmasligi mumkin.
  if (connectToken) {
    return <Connect
      token={connectToken}
      authenticated={authenticated}
      onConnected={() => { setConnectToken(""); setAuthenticated(true); navigateTo("cameras", "setup"); }}
    />;
  }
  if (!authenticated) return <LoginScreen kind="owner" onSubmit={submit} busy={busy} error={loginError} botUrl={telegramBotUrl()}/>;
  if (loading && !data) return splash(t("panel.owner.splash_preparing"));
  /* Ma'lumot kelmadi — sabab va chiqish yo'li KO'RSATILADI.  Avval bu
     holat cheksiz skeletga tushardi: 0 ta filial ham, doimiy server
     xatosi ham xabarsiz "yuklanmoqda" bo'lib qolar edi. */
  if (!data) {
    return <div className="login-page">
      <section className="login-visual"><Logo/><div><span className="eyebrow">{t("panel.login.eyebrow_owner")}</span>
        <h1>{sites.length === 0 && !loginError ? t("panel.owner.no_site_title") : t("panel.owner.data_failed_title")}</h1></div></section>
      <section className="login-panel"><div style={{width:"min(390px,100%)"}}>
        <p className="metric-note">{sites.length === 0 && !loginError
          ? t("panel.owner.no_site_note")
          : error || loginError || t("panel.owner.server_unreachable")}</p>
        <div className="page-actions" style={{marginTop:14}}>
          <button className="btn btn-primary" onClick={() => { void loadSites(); void refresh(); }}>{t("panel.common.retry")}</button>
          <button className="btn" onClick={logout}>{t("panel.common.logout")}</button>
        </div>
      </div></section>
    </div>;
  }

  const selected = sites.find(site => site.id === siteId);
  const today = formatDateUz();
  return <AppShell
    nav={nav}
    mobileNav={mobileNav}
    active={active}
    onNavigate={navigate}
    title={nav.find(item => item.id === active)?.label || t("panel.owner.home_title")}
    subtitle={t("panel.owner.updated_at", { time: formatTimeUz(data.updated_at) })}
    onLogout={logout}
    headerActions={<>
      <span className="topbar-date"><Icon name="calendar" size={16}/>{today}</span>
      <NotificationBell siteId={siteId} onOpenEvent={() => navigate("alerts")}/>
      <button className="btn btn-icon" onClick={() => refresh()} aria-label={t("panel.common.refresh")}><Icon name="pulse"/></button>
      {/* Do'kon nomi BITTA joyda — namunadagi avatar chipi.  Ilgari u
          topbar sarlavhasi, tanlagich va yon panel kartasida uch marta
          turardi.  Bir nechta filial — chip o'rnida tanlagich. */}
      {sites.length > 1
        ? <select className="select topbar-store" value={siteId} onChange={event => setSiteId(event.target.value)} aria-label={t("panel.owner.select_branch")}>{sites.map(site => <option value={site.id} key={site.id}>{site.name}</option>)}</select>
        : <div className="topbar-user" title={selected?.address || data.site.address || ""}><Avatar name={selected?.name || data.site.name}/><div><b>{selected?.name || data.site.name}</b><small>{role === "manager" ? t("panel.telegram.role_manager") : t("panel.telegram.role_owner")}</small></div></div>}
    </>}>
    {error ? <div className="alert-strip"><Icon name="bell"/><div><strong>{t("panel.owner.refresh_error_title")}</strong> {error}. {t("panel.owner.refresh_error_note")}</div></div> : null}
    {active === "home"
      ? <OwnerHome dashboard={data} sites={sites} siteId={siteId} onNavigate={navigate} cameras={<CamerasBlock dashboard={data} siteId={siteId} onOpenAll={() => navigate("cameras")} onOpenCamera={id => navigate("cameras", id)}/>} />
      : active === "employees" ? <EmployeesPage siteId={siteId}/>
      : <SectionPage id={active} tab={tab} dashboard={data} sites={sites} siteId={siteId} onNavigate={navigate} onRefresh={() => void refresh()} focusEventId={focusEvent} cameraId={cameraId} cameraTab={subRoute}/>}
    {drawer ? <div className="drawer-backdrop" onClick={() => setDrawer(false)}><aside className="drawer" onClick={event => event.stopPropagation()}><div className="drawer-head"><Logo/><button className="btn btn-icon" onClick={() => setDrawer(false)} aria-label={t("panel.common.close")}><Icon name="close"/></button></div><nav>{nav.map(item => <button key={item.id} className={active === item.id ? "active" : ""} onClick={() => navigate(item.id)}><Icon name={item.icon}/>{item.label}</button>)}<button onClick={logout}><Icon name="logout"/>{t("panel.common.logout")}</button></nav><div className="drawer-tools"><LangSwitch/><ThemeToggle/></div></aside></div> : null}
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

createRoot(document.getElementById("root")!).render(<StrictMode><OwnerApp/></StrictMode>);
