import { useEffect, useRef, useState, type ReactNode } from "react";
import { Icon, Logo } from "./icons";
import { Sparkline, Delta } from "./charts";

export type NavItem = { id: string; label: string; icon: string };

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
        <button className="sidebar-logout" onClick={onLogout}><Icon name="logout"/><span>Chiqish</span></button>
      </div>
    </aside>
    <main className="main-shell">
      <div className="topbar"><div className="topbar-title"><strong>{title}</strong><span>{subtitle}</span></div><div className="topbar-actions">{headerActions}</div></div>
      <div className="content">{children}</div>
    </main>
    <nav className="bottom-nav" aria-label="Mobil menyu">{mobile.map(item => <button key={item.id} className={active === item.id ? "active" : ""} onClick={() => onNavigate(item.id)}><Icon name={item.icon}/><span>{item.label}</span></button>)}<button onClick={() => onNavigate("more")}><Icon name="more"/><span>Yana</span></button></nav>
  </div>;
}

export function LoginScreen({ kind, onSubmit, busy, error, botUrl }: { kind: "owner" | "admin"; onSubmit: (username: string, password: string) => void; busy: boolean; error: string; botUrl?: string }) {
  return <main className="login-page">
    <section className="login-visual">
      <Logo />
      <div><span className="eyebrow">CHAQIMCHI CLOUD</span><h1>{kind === "owner" ? "Biznesingizni raqamlar orqali boshqaring." : "Tizim holatini bitta joydan boshqaring."}</h1><p>Kameralar, oqim, xavfsizlik va operatsion ko‘rsatkichlar — ortiqcha murakkabliksiz.</p></div>
      <div className="login-proof"><Icon name="shield"/><span>Ma’lumotlar himoyalangan ulanish orqali uzatiladi</span></div>
    </section>
    <section className="login-panel">
      <form onSubmit={(event) => { event.preventDefault(); const data = new FormData(event.currentTarget); onSubmit(String(data.get("username") || ""), String(data.get("password") || "")); }}>
        <div className="login-mobile-logo"><Logo /></div>
        <span className="eyebrow">{kind === "owner" ? "BIZNES PANELI" : "ADMIN PANEL"}</span>
        <h2>Xush kelibsiz</h2><p>Davom etish uchun login va parolingizni kiriting.</p>
        <label>Login<input name="username" autoComplete="username" required /></label>
        <label>Parol<input name="password" type="password" autoComplete="current-password" required /></label>
        {error ? <div className="form-error" role="alert">{error}</div> : null}
        <button className="btn btn-primary btn-wide" disabled={busy}>{busy ? "Tekshirilmoqda…" : "Kirish"}</button>
        {/* Parolsiz yo'l: bot bir martalik havola yuboradi.  Do'kon
            egasi uchun ko'pincha bu yagona qulay kirish usuli. */}
        {botUrl ? <p className="login-alt">Parolni eslay olmadingizmi? <a href={botUrl} target="_blank" rel="noreferrer">Telegram botdan kirish havolasini oling</a></p> : null}
      </form>
    </section>
  </main>;
}
