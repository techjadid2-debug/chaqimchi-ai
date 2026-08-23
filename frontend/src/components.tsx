import type { ReactNode } from "react";
import { Icon, Logo } from "./icons";

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

export function EmptyState({ icon = "report", title, detail }: { icon?: string; title: string; detail: string }) {
  return <div className="empty-state"><span><Icon name={icon} size={26} /></span><b>{title}</b><p>{detail}</p></div>;
}

export function Skeleton({ height = 80 }: { height?: number }) {
  return <div className="skeleton" style={{ height }} aria-label="Yuklanmoqda" />;
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle: string; actions?: ReactNode }) {
  return <header className="page-header"><div><h1>{title}</h1><p>{subtitle}</p></div>{actions ? <div className="page-actions">{actions}</div> : null}</header>;
}

export function AppShell({ kind, nav, active, onNavigate, title, subtitle, headerActions, children, onLogout }: {
  kind: "owner" | "admin";
  nav: NavItem[];
  active: string;
  onNavigate: (id: string) => void;
  title: string;
  subtitle: string;
  headerActions?: ReactNode;
  children: ReactNode;
  onLogout: () => void;
}) {
  const mobileIds = kind === "owner" ? new Set(["home", "cameras", "alerts", "reports"]) : new Set(["overview", "customers", "monitoring", "settings"]);
  const mobile = nav.filter(item => mobileIds.has(item.id));
  return <div className="app-shell">
    <aside className="sidebar">
      <div className="sidebar-logo"><Logo /></div>
      <nav aria-label="Asosiy menyu">{nav.map(item => <button key={item.id} className={active === item.id ? "active" : ""} onClick={() => onNavigate(item.id)}><Icon name={item.icon}/><span>{item.label}</span></button>)}</nav>
      <button className="sidebar-logout" onClick={onLogout}><Icon name="logout"/><span>Chiqish</span></button>
    </aside>
    <main className="main-shell">
      <div className="topbar"><div><strong>{title}</strong><span>{subtitle}</span></div><div className="topbar-actions">{headerActions}</div></div>
      <div className="content">{children}</div>
    </main>
    <nav className="bottom-nav" aria-label="Mobil menyu">{mobile.map(item => <button key={item.id} className={active === item.id ? "active" : ""} onClick={() => onNavigate(item.id)}><Icon name={item.icon}/><span>{item.label}</span></button>)}<button onClick={() => onNavigate("more")}><Icon name="more"/><span>Yana</span></button></nav>
  </div>;
}

export function LoginScreen({ kind, onSubmit, busy, error }: { kind: "owner" | "admin"; onSubmit: (username: string, password: string) => void; busy: boolean; error: string }) {
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
      </form>
    </section>
  </main>;
}
