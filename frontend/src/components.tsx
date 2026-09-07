import { useEffect, useRef, useState, type InputHTMLAttributes, type ReactNode } from "react";
import { copyText } from "./api";
import { Icon, Logo } from "./icons";
import { Sparkline, Delta } from "./charts";
import { applyTheme, nextTheme, readTheme, saveTheme, themeLabel, THEME_ICON, type Theme } from "./theme";
import { getLang, LANG_SHORT, LANGS, setLang, t, type Lang } from "./i18n";

/** Qo'llab-quvvatlash raqami.
 *
 * Sayt sahifalarida ham shu raqam turadi (`cloud/static/*.html`) va
 * `tests/test_panel_v2.py` ikkalasi bir xilligini tekshiradi: mijozga
 * ikki xil raqam ko'rsatilishi eng bilinmaydigan xatolardan biri. */
export const SUPPORT_PHONE = "+998932225070";
export const SUPPORT_PHONE_LABEL = "+998 93 222 50 70";

export type NavItem = { id: string; label: string; icon: string };

/** Tema tugmasi: yorug' → qorong'i → tizim.
 *
 * Nega uchinchi holat ko'rinadi: "tizim bo'yicha" ni yashirsak, odam
 * bir marta qo'lda tanlagach tizimga qaytolmaydi va kechqurun
 * kompyuter qorong'iga o'tganda panel yorug' bo'lib qolaveradi. */
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(() => readTheme());

  /* Tizim rejimi tanlangan bo'lsa, foydalanuvchi OS sozlamasini
     o'zgartirganda sahifa QAYTA YUKLANMASDAN moslashsin. */
  useEffect(() => {
    if (theme !== "system") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const sync = () => applyTheme("system");
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, [theme]);

  function toggle() {
    const next = nextTheme(theme);
    setTheme(next);
    saveTheme(next);
    applyTheme(next);
  }

  return <button
    className="btn btn-icon"
    onClick={toggle}
    title={themeLabel(theme)}
    aria-label={t("panel.theme.switch", { mode: themeLabel(theme) })}
  ><Icon name={THEME_ICON[theme]}/></button>;
}

/** Til tanlagich — namunadagidek UZ · RU · EN.
 *
 * Tanlangach sahifa qayta yuklanadi (`i18n/index.ts` dagi izohga
 * qarang): serverdan keladigan matn ham yangi tilda bo'lishi kerak,
 * aks holda ekranda ikki til aralashardi. */
export function LangSwitch() {
  const active = getLang();
  return <div className="lang-switch" role="group" aria-label={t("panel.lang.choose")}>
    {LANGS.map((lang: Lang) => <button
      key={lang}
      className={lang === active ? "active" : ""}
      onClick={() => setLang(lang)}
      aria-current={lang === active}
    >{LANG_SHORT[lang]}</button>)}
  </div>;
}

export function StatusDot({ state }: { state: string }) {
  return <span className={`status-dot status-${state}`} aria-label={state} />;
}

export function Pill({ state, children }: { state?: string; children: ReactNode }) {
  return <span className={`pill ${state ? `pill-${state}` : ""}`}>{children}</span>;
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`card ${className}`}>{children}</section>;
}

export function MetricCard({ label, value, note, icon, tone = "blue" }: { label: string; value: ReactNode; note?: ReactNode; icon: string; tone?: string }) {
  return <Card className="metric-card">
    <div className={`metric-icon tone-${tone}`}><Icon name={icon} /></div>
    <div className="metric-label">{label}</div>
    <div className="metric-value">{value}</div>
    {note ? <div className="metric-note">{note}</div> : null}
  </Card>;
}

/** Ko'rsatkich kartasi: raqam + ixtiyoriy o'zgarish + ixtiyoriy
 *  tendensiya chizig'i.
 *
 *  `series` va `deltaPercent` — IXTIYORIY.  Server hali bermaydigan
 *  ko'rsatkich uchun karta ularsiz chiziladi: bo'sh sparkline yoki
 *  "0%" degan yolg'on o'sish ko'rsatgandan ko'ra hech narsa
 *  ko'rsatmagan yaxshi. */
export function StatCard({ label, value, note, icon, tone = "blue", series, deltaPercent, deltaNote, goodWhenDown }: {
  label: string;
  value: ReactNode;
  note?: ReactNode;
  icon: string;
  tone?: string;
  series?: number[];
  deltaPercent?: number | null;
  deltaNote?: string;
  goodWhenDown?: boolean;
}) {
  return <Card className="metric-card stat-card">
    <div className="stat-head">
      <div className={`metric-icon tone-${tone}`}><Icon name={icon} /></div>
      <div className="metric-label">{label}</div>
    </div>
    <div className="metric-value">{value}</div>
    <Delta percent={deltaPercent} note={deltaNote} goodWhenDown={goodWhenDown} />
    {note ? <div className="metric-note">{note}</div> : null}
    {series && series.length > 1 ? <Sparkline points={series} tone={tone === "red" ? "red" : tone === "green" ? "green" : "blue"} /> : null}
  </Card>;
}

export function EmptyState({ icon = "report", title, detail }: { icon?: string; title: string; detail: string }) {
  return <div className="empty-state"><span><Icon name={icon} size={26} /></span><b>{title}</b><p>{detail}</p></div>;
}

/** Tarifda yopiq bo'lim.
 *
 * Bo'lim YO'QOLMAYDI — mijoz nimani ololishini ko'rsin.  Yo'q bo'lib
 * qolgan karta «buzilibdi» degan taassurot beradi, qulf esa
 * «ko'tarish mumkin» degani.
 */
export function PlanLock({ title, detail, onUpgrade }: { title: string; detail: string; onUpgrade: () => void }) {
  return <>
    <EmptyState icon="card" title={title} detail={detail} />
    <div className="card-body"><button className="btn btn-wide" onClick={onUpgrade}>Tarifni ko‘rish</button></div>
  </>;
}

export function Skeleton({ height = 80 }: { height?: number }) {
  return <div className="skeleton" style={{ height }} aria-label="Yuklanmoqda" />;
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle: string; actions?: ReactNode }) {
  return <header className="page-header"><div><h1>{title}</h1><p>{subtitle}</p></div>{actions ? <div className="page-actions">{actions}</div> : null}</header>;
}

/** Ism bosh harflaridan doira.  Haqiqiy suratlar yo'q — jadvalda
 *  qatorlarni ko'z bilan ajratish uchun shu yetadi. */
export function Avatar({ name, tone }: { name: string; tone?: number }) {
  const initials = name.trim().split(/\s+/).slice(0, 2).map(part => part[0] || "").join("").toUpperCase() || "?";
  const index = tone ?? Array.from(name).reduce((sum, char) => sum + char.charCodeAt(0), 0);
  return <span className={`avatar avatar-${index % 5}`} aria-hidden="true">{initials}</span>;
}

/** Jadval qatoridagi "…" menyusi. */
export function ActionMenu({ items }: { items: { label: string; onSelect: () => void; danger?: boolean }[] }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => { if (!box.current?.contains(event.target as Node)) setOpen(false); };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", escape); };
  }, [open]);
  if (!items.length) return null;
  return <div className="action-menu" ref={box}>
    <button className="btn btn-icon" aria-label="Amallar" aria-expanded={open} onClick={() => setOpen(value => !value)}><Icon name="more" /></button>
    {open ? <div className="action-list" role="menu">
      {items.map(item => <button key={item.label} role="menuitem" className={item.danger ? "danger" : ""} onClick={() => { setOpen(false); item.onSelect(); }}>{item.label}</button>)}
    </div> : null}
  </div>;
}

/** Nusxalash tugmasi — natijani KO'RSATADI.
 *
 * Javobsiz tugma buzuq tugmadan farq qilmaydi: foydalanuvchi uni yana
 * bosadi va baribir ishonchi bo'lmaydi.  Nusxalash imkonsiz muhitda
 * halol aytiladi ("qo'lda nusxalang") — jimgina yutilmaydi.
 */
export function CopyButton({ value, label = "Nusxalash" }: { value: string; label?: string }) {
  const [state, setState] = useState<"" | "ok" | "fail">("");
  useEffect(() => {
    if (!state) return;
    const timer = window.setTimeout(() => setState(""), 2200);
    return () => window.clearTimeout(timer);
  }, [state]);
  return <button
    className={`btn${state === "ok" ? " btn-copied" : ""}`}
    onClick={() => { void copyText(value).then(ok => setState(ok ? "ok" : "fail")); }}
  >{state === "ok" ? "Nusxalandi ✓" : state === "fail" ? "Qo‘lda nusxalang" : label}</button>;
}

export type SearchEntry = { id: string; label: string; hint?: string; onSelect: () => void };

/** ⌘K qidiruv — bo'limlar va mijozlar bo'yicha, brauzer ichida.
 *  Serverga so'rov yubormaydi: ro'yxat allaqachon yuklangan. */
export function SearchPalette({ entries, placeholder = "Qidirish…" }: { entries: SearchEntry[]; placeholder?: string }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); setOpen(true); }
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const needle = query.trim().toLowerCase();
  const found = needle ? entries.filter(entry => entry.label.toLowerCase().includes(needle) || (entry.hint || "").toLowerCase().includes(needle)).slice(0, 8) : entries.slice(0, 8);
  return <>
    <button className="search-trigger" onClick={() => setOpen(true)}>
      <Icon name="search" size={16} /><span>{placeholder}</span><kbd>⌘K</kbd>
    </button>
    {open ? <div className="palette-backdrop" onClick={() => setOpen(false)}>
      <div className="palette" onClick={event => event.stopPropagation()}>
        <div className="palette-input">
          <Icon name="search" size={18} />
          <input autoFocus value={query} placeholder={placeholder} onChange={event => setQuery(event.target.value)} />
        </div>
        {found.length ? <ul>
          {found.map(entry => <li key={entry.id}>
            <button onClick={() => { setOpen(false); setQuery(""); entry.onSelect(); }}>
              <span>{entry.label}</span>{entry.hint ? <em>{entry.hint}</em> : null}
            </button>
          </li>)}
        </ul> : <p className="palette-empty">Hech narsa topilmadi</p>}
      </div>
    </div> : null}
  </>;
}

export function AppShell({ nav, active, onNavigate, title, subtitle, headerActions, children, onLogout, mobileNav, sidebarFooter }: {
  nav: NavItem[];
  active: string;
  onNavigate: (id: string) => void;
  title: string;
  subtitle: string;
  headerActions?: ReactNode;
  children: ReactNode;
  onLogout: () => void;
  /* Telefon pastidagi menyuda ko'rinadigan bo'limlar.  Ilgari bu
     ro'yxat komponent ichida qotirilgan edi: menyuga yangi bo'lim
     qo'shilsa, u mobil menyuda jimgina yo'q bo'lib qolardi. */
  mobileNav: string[];
  sidebarFooter?: ReactNode;
}) {
  const mobile = nav.filter(item => mobileNav.includes(item.id));
  return <div className="app-shell">
    <aside className="sidebar">
      <div className="sidebar-logo"><Logo /></div>
      <nav aria-label="Asosiy menyu">{nav.map(item => <button key={item.id} className={active === item.id ? "active" : ""} onClick={() => onNavigate(item.id)}><Icon name={item.icon}/><span>{item.label}</span></button>)}</nav>
      <div className="sidebar-foot">
        {sidebarFooter}
        {/* Aloqa panel ICHIDA bo'lsin.  Ilgari u faqat kirish ekranida
            edi: panel to'rt joyda "bizga yozing" deydi-yu, kirgandan
            keyin qayerga yozishni ko'rsatmasdi. */}
        <a className="sidebar-support" href={`tel:${SUPPORT_PHONE}`}>
          <Icon name="bell"/><span>{t("panel.support")}<b>{SUPPORT_PHONE_LABEL}</b></span>
        </a>
        <button className="sidebar-logout" onClick={onLogout}><Icon name="logout"/><span>Chiqish</span></button>
      </div>
    </aside>
    <main className="main-shell">
      <div className="topbar"><div className="topbar-title"><strong>{title}</strong><span>{subtitle}</span></div><div className="topbar-actions">{headerActions}<LangSwitch/><ThemeToggle/></div></div>
      <div className="content">{children}</div>
    </main>
    <nav className="bottom-nav" aria-label="Mobil menyu">{mobile.map(item => <button key={item.id} className={active === item.id ? "active" : ""} onClick={() => onNavigate(item.id)}><Icon name={item.icon}/><span>{item.label}</span></button>)}<button onClick={() => onNavigate("more")}><Icon name="more"/><span>Yana</span></button></nav>
  </div>;
}

/** Parol maydoni — "ko'z" (ko'rsatish/yashirish) tugmasi bilan.
 *
 *  Telefon klaviaturasida xato terish oson, xatoni ko'rmasdan tuzatib
 *  bo'lmaydi.  Statik sahifalar uchun xuddi shu naqsh
 *  `chaqimchi_ai/local/static/pw-eye.js` da. */
/** Modal oyna — brauzerning `prompt`/`confirm` o'rniga.
 *
 * Eski admin qoidasi (2026-08-19): brauzer oynasida "auto" yoki "naqd"
 * deb YOZISH kerak edi — bitta harf xato, amal bajarilmasdi.  Modal
 * ichida esa tanlov tugma va ro'yxat bilan.  Escape va orqa fon yopadi;
 * fokus oyna ichida. */
export function Modal({ title, children, onClose, wide = false, footer }: { title: string; children: ReactNode; onClose: () => void; wide?: boolean; footer?: ReactNode }) {
  useEffect(() => {
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [onClose]);
  return <div className="modal-backdrop" onClick={onClose}>
    <div className={`modal${wide ? " modal-wide" : ""}`} role="dialog" aria-modal="true" aria-label={title} onClick={event => event.stopPropagation()}>
      <div className="modal-head"><h2>{title}</h2><button className="btn btn-icon" aria-label="Yopish" onClick={onClose}><Icon name="close" /></button></div>
      <div className="modal-body">{children}</div>
      {footer ? <div className="modal-foot">{footer}</div> : null}
    </div>
  </div>;
}

export type ConfirmRequest = {
  title: string;
  text: string;
  confirmLabel?: string;
  danger?: boolean;
  /** Xavfli amal: foydalanuvchi shu matnni TERIB tasdiqlaydi
   *  (obunani to'xtatish — do'kon nomi).  Tasodifiy bosishdan himoya. */
  typed?: string;
};

/** Tasdiqlash oynasi.  `window.confirm` ATAYLAB ishlatilmaydi: Telegram
 *  WebView'da u ishonchsiz, matnini esa uslublab bo'lmaydi. */
export function ConfirmDialog({ request, onResolve }: { request: ConfirmRequest; onResolve: (ok: boolean) => void }) {
  const [typed, setTyped] = useState("");
  const blocked = Boolean(request.typed) && typed.trim() !== request.typed;
  return <Modal title={request.title} onClose={() => onResolve(false)} footer={<>
    <button className="btn" onClick={() => onResolve(false)}>Bekor qilish</button>
    <button className={`btn ${request.danger ? "btn-danger" : "btn-primary"}`} disabled={blocked} onClick={() => onResolve(true)}>{request.confirmLabel || "Ha"}</button>
  </>}>
    <p className="modal-text">{request.text}</p>
    {request.typed ? <label className="field-label">Tasdiqlash uchun «{request.typed}» deb yozing<input className="input" value={typed} onChange={event => setTyped(event.target.value)} autoFocus /></label> : null}
  </Modal>;
}

/** `const [confirm, dialog] = useConfirm(); if (await confirm({...})) …` */
export function useConfirm(): [(request: ConfirmRequest) => Promise<boolean>, ReactNode] {
  const [pending, setPending] = useState<{ request: ConfirmRequest; resolve: (ok: boolean) => void } | null>(null);
  const ask = (request: ConfirmRequest) => new Promise<boolean>(resolve => setPending({ request, resolve }));
  const dialog = pending ? <ConfirmDialog request={pending.request} onResolve={ok => { pending.resolve(ok); setPending(null); }} /> : null;
  return [ask, dialog];
}

/** Qisqa xabar (toast) — amal natijasi.  Javobsiz tugma buzuq tugmadan
 *  farq qilmaydi. */
export function useToast(): [(message: string, ok?: boolean) => void, ReactNode] {
  const [toast, setToast] = useState<{ message: string; ok: boolean } | null>(null);
  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 3200);
    return () => window.clearTimeout(timer);
  }, [toast]);
  const show = (message: string, ok = true) => setToast({ message, ok });
  const node = toast ? <div className={`toast${toast.ok ? "" : " toast-error"}`} role="status">{toast.message}</div> : null;
  return [show, node];
}

/** Oy tanlagich: 1/3/6/12 chip + ixtiyoriy son.  Obuna, hisob va
 *  uzaytirish uchun bitta shakl. */
export function MonthPicker({ value, onChange, max = 60 }: { value: number; onChange: (months: number) => void; max?: number }) {
  return <div className="month-picker">
    <div className="chip-row">
      {[1, 3, 6, 12].map(months => <button key={months} type="button" className={`chip${value === months ? " active" : ""}`} onClick={() => onChange(months)}>{months} oy</button>)}
    </div>
    <label className="field-label">Yoki boshqa son<input className="input" type="number" min={1} max={max} value={value} onChange={event => onChange(Math.max(1, Math.min(max, Number(event.target.value) || 1)))} /></label>
  </div>;
}

/** Nusxalanadigan maydon: havola yoki kod + tugma. */
export function CopyField({ value, label = "Nusxalash" }: { value: string; label?: string }) {
  return <div className="copy-field"><input readOnly value={value} onFocus={event => event.currentTarget.select()} /><CopyButton value={value} label={label} /></div>;
}

export function PasswordInput({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  const [show, setShow] = useState(false);
  return <span className="pw-wrap">
    <input {...rest} className={className} type={show ? "text" : "password"} />
    <button
      type="button"
      className="pw-eye"
      tabIndex={-1}
      aria-label={show ? "Parolni yashirish" : "Parolni ko‘rsatish"}
      onClick={() => setShow(value => !value)}
    ><Icon name={show ? "eyeOff" : "eye"} size={18} /></button>
  </span>;
}

export function LoginScreen({ kind, onSubmit, busy, error, botUrl }: { kind: "owner" | "admin"; onSubmit: (username: string, password: string) => void; busy: boolean; error: string; botUrl?: string }) {
  return <main className="login-page">
    <section className="login-visual">
      <Logo />
      <div><span className="eyebrow">ENES CLOUD</span><h1>{kind === "owner" ? "Biznesingizni raqamlar orqali boshqaring." : "Tizim holatini bitta joydan boshqaring."}</h1><p>Kameralar, oqim, xavfsizlik va operatsion ko‘rsatkichlar — ortiqcha murakkabliksiz.</p></div>
      <div className="login-proof"><Icon name="shield"/><span>Ma’lumotlar himoyalangan ulanish orqali uzatiladi</span></div>
    </section>
    <section className="login-panel">
      {/* Tema tugmasi kirish ekranida ham kerak: paneldagisi faqat
          kirgandan keyin ko'rinadi, ya'ni kechasi login sahifasini
          ochgan odam yorug' ekranni almashtira olmasdi. */}
      <div className="login-tools"><LangSwitch/><ThemeToggle/></div>
      <form onSubmit={(event) => { event.preventDefault(); const data = new FormData(event.currentTarget); onSubmit(String(data.get("username") || ""), String(data.get("password") || "")); }}>
        <div className="login-mobile-logo"><Logo /></div>
        <span className="eyebrow">{kind === "owner" ? "BIZNES PANELI" : "ADMIN PANEL"}</span>
        <h2>Xush kelibsiz</h2><p>Davom etish uchun login va parolingizni kiriting.</p>
        <label>Login<input name="username" autoComplete="username" required /></label>
        <label>Parol<PasswordInput name="password" autoComplete="current-password" required /></label>
        {error ? <div className="form-error" role="alert">{error}</div> : null}
        <button className="btn btn-primary btn-wide" disabled={busy}>{busy ? "Tekshirilmoqda…" : "Kirish"}</button>
        {/* Parolsiz yo'l: bot bir martalik havola yuboradi.  Do'kon
            egasi uchun ko'pincha bu yagona qulay kirish usuli. */}
        {botUrl ? <p className="login-alt">Parolni eslay olmadingizmi? <a href={botUrl} target="_blank" rel="noreferrer">Telegram botdan kirish havolasini oling</a></p> : null}
      </form>
    </section>
  </main>;
}
