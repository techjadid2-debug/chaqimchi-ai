import { useCallback, useEffect, useState } from "react";
import { api, formatDateShort } from "./api";
import { Card, EmptyState, PageHeader, Pill, Skeleton, useToast } from "./components";
import { Icon } from "./icons";
import { PasswordModal, generatePassword } from "./AdminCustomer";

/* Jamoa — loginlar va o'rnatuvchi biriktirishlari.
 * Eski admindagi `renderTeam` shu yerga ko'chdi. */

type Account = { id: string; username: string; full_name?: string; role: string; status: string; company?: string; site_id?: string; last_login_at?: string };
type Assignment = { id?: string; installer_name?: string; site_name?: string; status: string; notes?: string; updated_at?: string };
type Site = { id: string; name: string };

const ROLE_LABEL: Record<string, string> = { admin: "Admin", installer: "O‘rnatuvchi", customer: "Mijoz" };
const STATUS_LABEL: Record<string, string> = { active: "Faol", pending: "Tasdiq kutmoqda", disabled: "Bloklangan", suspended: "To‘xtatilgan" };
const STATUS_STATE: Record<string, string> = { active: "active", pending: "pending", disabled: "failed", suspended: "failed" };
const ASSIGN_LABEL: Record<string, string> = { assigned: "Biriktirildi", in_progress: "Jarayonda", ready: "Tayyor", completed: "Tugallandi", cancelled: "Bekor qilindi" };

export function AdminTeam({ sites }: { sites: Site[] }) {
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [error, setError] = useState("");
  const [password, setPassword] = useState<Account | null>(null);
  const [showAccount, setShowAccount] = useState(false);
  const [showAssign, setShowAssign] = useState(false);
  const [toast, toastNode] = useToast();
  const siteName = new Map(sites.map(site => [site.id, site.name]));

  const load = useCallback(() => {
    api<{ accounts: Account[] }>("/api/v1/admin/accounts", "admin").then(data => { setAccounts(data.accounts || []); setError(""); }).catch(reason => setError(reason instanceof Error ? reason.message : "Akkauntlar olinmadi"));
    api<{ assignments: Assignment[] }>("/api/v1/admin/installer-assignments", "admin").then(data => setAssignments(data.assignments || [])).catch(() => setAssignments([]));
  }, []);
  useEffect(load, [load]);

  const setStatus = async (account: Account, status: "active" | "disabled") => {
    try { await api(`/api/v1/admin/accounts/${encodeURIComponent(account.id)}`, "admin", { method: "PUT", body: JSON.stringify({ status }) }); toast("Login holati yangilandi"); load(); }
    catch (reason) { toast(reason instanceof Error ? reason.message : "Yangilanmadi", false); }
  };

  const createAccount = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget; const data = new FormData(form);
    const body = {
      full_name: String(data.get("full_name") || "").trim(), username: String(data.get("username") || "").trim(),
      password: String(data.get("password") || ""), role: String(data.get("role") || "customer"),
      site_id: String(data.get("site_id") || "") || null, phone: String(data.get("phone") || "") || null,
    };
    try { await api("/api/v1/admin/accounts", "admin", { method: "POST", body: JSON.stringify(body) }); toast("Login yaratildi"); form.reset(); setShowAccount(false); load(); }
    catch (reason) { toast(reason instanceof Error ? reason.message : "Yaratilmadi", false); }
  };

  const createAssignment = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget; const data = new FormData(form);
    try { await api("/api/v1/admin/installer-assignments", "admin", { method: "POST", body: JSON.stringify({ installer_id: String(data.get("installer_id") || ""), site_id: String(data.get("site_id") || ""), notes: String(data.get("notes") || "") || null }) }); toast("Do‘kon o‘rnatuvchiga biriktirildi"); form.reset(); setShowAssign(false); load(); }
    catch (reason) { toast(reason instanceof Error ? reason.message : "Biriktirilmadi", false); }
  };

  const installers = (accounts || []).filter(account => account.role === "installer" && account.status === "active");

  return <>
    <PageHeader title="Jamoa" subtitle="Admin, o‘rnatuvchi va mijoz loginlari; o‘rnatuvchi ishlari." actions={<button className="btn btn-primary" onClick={() => setShowAccount(value => !value)}><Icon name="users" />{showAccount ? "Bekor qilish" : "Yangi login"}</button>} />
    {error ? <div className="alert-strip"><Icon name="bell" />{error}</div> : null}

    {showAccount ? <Card className="section-gap"><form className="card-body" onSubmit={createAccount}>
      <div className="form-grid">
        <label>Ism<input className="input" name="full_name" minLength={2} required /></label>
        <label>Login<input className="input" name="username" minLength={3} required autoComplete="off" /></label>
        <label>Vaqtinchalik parol<input className="input" name="password" minLength={10} required defaultValue={generatePassword(false)} autoComplete="new-password" /><small>Kamida 10 belgi</small></label>
        <label>Rol<select className="select" name="role" defaultValue="customer"><option value="customer">Mijoz</option><option value="installer">O‘rnatuvchi</option><option value="admin">Admin</option></select></label>
        <label>Obyekt (faqat mijoz uchun)<select className="select" name="site_id" defaultValue=""><option value="">Tanlang</option>{sites.map(site => <option key={site.id} value={site.id}>{site.name}</option>)}</select></label>
        <label>Telefon<input className="input" name="phone" inputMode="tel" placeholder="+998…" /></label>
      </div>
      <button className="btn btn-primary">Login yaratish</button>
    </form></Card> : null}

    <Card className="section-gap">
      <div className="card-head"><div><h2>Loginlar</h2><p>{accounts ? `${accounts.length} ta` : ""}</p></div></div>
      {accounts === null ? <div className="card-body"><Skeleton height={160} /></div> : accounts.length ? <div className="table-wrap"><table>
        <thead><tr><th>Foydalanuvchi</th><th>Login</th><th>Rol</th><th>Obyekt</th><th>Oxirgi kirish</th><th>Holat</th><th aria-label="Amallar" /></tr></thead>
        <tbody>{accounts.map(account => <tr key={account.id}>
          <td><div className="table-title">{account.full_name || account.company || "—"}</div></td>
          <td className="mono">{account.username}</td>
          <td>{ROLE_LABEL[account.role] || account.role}</td>
          <td>{account.site_id ? siteName.get(account.site_id) || account.site_id : "Platforma"}</td>
          <td>{account.last_login_at ? formatDateShort(account.last_login_at) : "—"}</td>
          <td><Pill state={STATUS_STATE[account.status]}>{STATUS_LABEL[account.status] || account.status}</Pill></td>
          <td><div className="page-actions">
            {account.status !== "active" ? <button className="btn btn-small" onClick={() => void setStatus(account, "active")}>Faollashtirish</button> : null}
            {account.status !== "disabled" ? <button className="btn btn-small btn-danger" onClick={() => void setStatus(account, "disabled")}>Bloklash</button> : null}
            <button className="btn btn-small" onClick={() => setPassword(account)}>Parol</button>
          </div></td>
        </tr>)}</tbody>
      </table></div> : <EmptyState icon="shield" title="Faqat siz" detail="Yordamchi yoki o‘rnatuvchi uchun login yarating." />}
    </Card>

    <Card className="section-gap">
      <div className="card-head"><div><h2>O‘rnatuvchi ishlari</h2><p>Kim qaysi do‘konni o‘rnatmoqda</p></div><div className="page-actions"><a className="btn" href="/installer-guide" target="_blank" rel="noopener noreferrer">Rasmli yo‘riqnoma</a><button className="btn btn-primary" onClick={() => setShowAssign(value => !value)}>{showAssign ? "Bekor qilish" : "Do‘kon biriktirish"}</button></div></div>
      {showAssign ? <form className="card-body" onSubmit={createAssignment}>
        <div className="form-grid">
          <label>O‘rnatuvchi<select className="select" name="installer_id" required defaultValue=""><option value="">Tanlang</option>{installers.map(account => <option key={account.id} value={account.id}>{account.full_name || account.username}</option>)}</select></label>
          <label>Do‘kon<select className="select" name="site_id" required defaultValue=""><option value="">Tanlang</option>{sites.map(site => <option key={site.id} value={site.id}>{site.name}</option>)}</select></label>
          <label>Izoh<input className="input" name="notes" placeholder="Muddat yoki aloqa ma’lumoti" /></label>
        </div>
        <button className="btn btn-primary" disabled={!installers.length}>Biriktirish</button>
        {!installers.length ? <p className="metric-note">Avval «O‘rnatuvchi» rolida faol login yarating.</p> : null}
      </form> : null}
      {assignments.length ? <div className="simple-list">{assignments.map((item, index) => <div className="simple-row" key={item.id || index}><div><b>{item.installer_name || "—"}</b><div className="table-sub">{item.site_name || "—"} · {item.notes || "izoh yo‘q"} · {formatDateShort(item.updated_at)}</div></div><Pill state={item.status === "completed" ? "active" : "pending"}>{ASSIGN_LABEL[item.status] || item.status}</Pill></div>)}</div> : <EmptyState icon="branch" title="Biriktirish yo‘q" detail="O‘rnatuvchiga do‘kon biriktirsangiz shu yerda ko‘rinadi." />}
    </Card>

    {password ? <PasswordModal account={password} onClose={() => setPassword(null)} onDone={() => { setPassword(null); toast("Parol yangilandi"); }} /> : null}
    {toastNode}
  </>;
}
