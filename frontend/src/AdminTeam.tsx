import { useCallback, useEffect, useState } from "react";
import { api, formatDateShort } from "./api";
import { Card, EmptyState, ErrorStrip, PageHeader, Pill, Skeleton, useToast } from "./components";
import { Icon } from "./icons";
import { t } from "./i18n";
import { PasswordModal, generatePassword } from "./AdminCustomer";

/* Jamoa — loginlar va o'rnatuvchi biriktirishlari.
 * Eski admindagi `renderTeam` shu yerga ko'chdi. */

type Account = { id: string; username: string; full_name?: string; role: string; status: string; company?: string; site_id?: string; last_login_at?: string };
type Assignment = { id?: string; installer_name?: string; site_name?: string; status: string; notes?: string; updated_at?: string };
type Site = { id: string; name: string };

/* Yorliq matn emas, katalog KALITI — modul yuklanganda til hali
   tanlanmagan (`admin.tsx: NAV_ITEMS` izohiga qarang). */
const ROLE_KEY: Record<string, string> = { admin: "panel.admin.role.admin", installer: "panel.admin.role.installer", customer: "panel.admin.role.customer" };
const STATUS_KEY: Record<string, string> = { active: "panel.admin.account_status.active", pending: "panel.admin.account_status.pending", disabled: "panel.admin.account_status.blocked", suspended: "panel.admin.account_status.suspended" };
const STATUS_STATE: Record<string, string> = { active: "active", pending: "pending", disabled: "failed", suspended: "failed" };
const ASSIGN_KEY: Record<string, string> = { assigned: "panel.admin.assign.assigned", in_progress: "panel.admin.assign.in_progress", ready: "panel.admin.assign.ready", completed: "panel.admin.assign.completed", cancelled: "panel.admin.assign.cancelled" };

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
    api<{ accounts: Account[] }>("/api/v1/admin/accounts", "admin").then(data => { setAccounts(data.accounts || []); setError(""); }).catch(reason => { setAccounts([]); setError(reason instanceof Error ? reason.message : t("panel.admin.team.accounts_failed")); });
    api<{ assignments: Assignment[] }>("/api/v1/admin/installer-assignments", "admin").then(data => setAssignments(data.assignments || [])).catch(() => setAssignments([]));
  }, []);
  useEffect(load, [load]);

  const setStatus = async (account: Account, status: "active" | "disabled") => {
    try { await api(`/api/v1/admin/accounts/${encodeURIComponent(account.id)}`, "admin", { method: "PUT", body: JSON.stringify({ status }) }); toast(t("panel.admin.team.status_updated")); load(); }
    catch (reason) { toast(reason instanceof Error ? reason.message : t("panel.admin.team.update_failed"), false); }
  };

  const createAccount = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget; const data = new FormData(form);
    const body = {
      full_name: String(data.get("full_name") || "").trim(), username: String(data.get("username") || "").trim(),
      password: String(data.get("password") || ""), role: String(data.get("role") || "customer"),
      site_id: String(data.get("site_id") || "") || null, phone: String(data.get("phone") || "") || null,
    };
    try { await api("/api/v1/admin/accounts", "admin", { method: "POST", body: JSON.stringify(body) }); toast(t("panel.admin.team.created")); form.reset(); setShowAccount(false); load(); }
    catch (reason) { toast(reason instanceof Error ? reason.message : t("panel.admin.team.create_failed"), false); }
  };

  const createAssignment = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget; const data = new FormData(form);
    try { await api("/api/v1/admin/installer-assignments", "admin", { method: "POST", body: JSON.stringify({ installer_id: String(data.get("installer_id") || ""), site_id: String(data.get("site_id") || ""), notes: String(data.get("notes") || "") || null }) }); toast(t("panel.admin.team.assigned")); form.reset(); setShowAssign(false); load(); }
    catch (reason) { toast(reason instanceof Error ? reason.message : t("panel.admin.team.assign_failed"), false); }
  };

  const installers = (accounts || []).filter(account => account.role === "installer" && account.status === "active");

  return <>
    <PageHeader title={t("panel.admin.nav.team")} subtitle={t("panel.admin.team.subtitle")} actions={<button className="btn btn-primary" onClick={() => setShowAccount(value => !value)}><Icon name="users" />{t(showAccount ? "panel.common.cancel" : "panel.admin.team.new_login")}</button>} />
    {error ? <ErrorStrip detail={error} onRetry={() => { setAccounts(null); load(); }} /> : null}

    {showAccount ? <Card className="section-gap"><form className="card-body" onSubmit={createAccount}>
      <div className="form-grid">
        <label>{t("panel.admin.team.full_name")}<input className="input" name="full_name" minLength={2} required /></label>
        <label>{t("panel.login.username")}<input className="input" name="username" minLength={3} required autoComplete="off" /></label>
        <label>{t("panel.admin.team.temp_password")}<input className="input" name="password" minLength={10} required defaultValue={generatePassword(false)} autoComplete="new-password" /><small>{t("panel.admin.team.temp_password_hint")}</small></label>
        <label>{t("panel.admin.team.role")}<select className="select" name="role" defaultValue="customer">{["customer", "installer", "admin"].map(role => <option key={role} value={role}>{t(ROLE_KEY[role])}</option>)}</select></label>
        <label>{t("panel.admin.team.site_optional")}<select className="select" name="site_id" defaultValue=""><option value="">{t("panel.admin.team.choose")}</option>{sites.map(site => <option key={site.id} value={site.id}>{site.name}</option>)}</select></label>
        <label>{t("panel.admin.customers.phone")}<input className="input" name="phone" inputMode="tel" placeholder="+998…" /></label>
      </div>
      <button className="btn btn-primary">{t("panel.admin.team.create_button")}</button>
    </form></Card> : null}

    <Card className="section-gap">
      <div className="card-head"><div><h2>{t("panel.admin.team.logins_title")}</h2><p>{accounts ? t("panel.admin.team.logins_count", { count: accounts.length }) : ""}</p></div></div>
      {accounts === null ? <div className="card-body"><Skeleton height={160} /></div> : accounts.length ? <div className="table-wrap"><table>
        <thead><tr><th>{t("panel.admin.team.col_user")}</th><th>{t("panel.login.username")}</th><th>{t("panel.admin.team.role")}</th><th>{t("panel.admin.team.col_site")}</th><th>{t("panel.admin.team.col_last_login")}</th><th>{t("panel.admin.col_status")}</th><th aria-label={t("panel.shell.actions")} /></tr></thead>
        <tbody>{accounts.map(account => <tr key={account.id}>
          <td><div className="table-title">{account.full_name || account.company || "—"}</div></td>
          <td className="mono">{account.username}</td>
          <td>{ROLE_KEY[account.role] ? t(ROLE_KEY[account.role]) : account.role}</td>
          <td>{account.site_id ? siteName.get(account.site_id) || account.site_id : t("panel.admin.team.platform")}</td>
          <td>{account.last_login_at ? formatDateShort(account.last_login_at) : "—"}</td>
          <td><Pill state={STATUS_STATE[account.status]}>{STATUS_KEY[account.status] ? t(STATUS_KEY[account.status]) : account.status}</Pill></td>
          <td><div className="page-actions">
            {account.status !== "active" ? <button className="btn btn-small" onClick={() => void setStatus(account, "active")}>{t("panel.admin.team.activate")}</button> : null}
            {account.status !== "disabled" ? <button className="btn btn-small btn-danger" onClick={() => void setStatus(account, "disabled")}>{t("panel.admin.team.block")}</button> : null}
            <button className="btn btn-small" onClick={() => setPassword(account)}>{t("panel.login.password")}</button>
          </div></td>
        </tr>)}</tbody>
      </table></div> : <EmptyState icon="shield" title={t("panel.admin.team.empty_title")} detail={t("panel.admin.team.empty_detail")} />}
    </Card>

    <Card className="section-gap">
      <div className="card-head"><div><h2>{t("panel.admin.team.jobs_title")}</h2><p>{t("panel.admin.team.jobs_subtitle")}</p></div><div className="page-actions"><a className="btn" href="/installer-guide" target="_blank" rel="noopener noreferrer">{t("panel.admin.team.guide")}</a><button className="btn btn-primary" onClick={() => setShowAssign(value => !value)}>{t(showAssign ? "panel.common.cancel" : "panel.admin.team.assign_button")}</button></div></div>
      {showAssign ? <form className="card-body" onSubmit={createAssignment}>
        <div className="form-grid">
          <label>{t("panel.admin.team.installer")}<select className="select" name="installer_id" required defaultValue=""><option value="">{t("panel.admin.team.choose")}</option>{installers.map(account => <option key={account.id} value={account.id}>{account.full_name || account.username}</option>)}</select></label>
          <label>{t("panel.admin.team.shop")}<select className="select" name="site_id" required defaultValue=""><option value="">{t("panel.admin.team.choose")}</option>{sites.map(site => <option key={site.id} value={site.id}>{site.name}</option>)}</select></label>
          <label>{t("panel.admin.team.note")}<input className="input" name="notes" placeholder={t("panel.admin.team.note_placeholder")} /></label>
        </div>
        <button className="btn btn-primary" disabled={!installers.length}>{t("panel.admin.team.assign_submit")}</button>
        {!installers.length ? <p className="metric-note">{t("panel.admin.team.no_installers")}</p> : null}
      </form> : null}
      {assignments.length ? <div className="simple-list">{assignments.map((item, index) => <div className="simple-row" key={item.id || index}><div><b>{item.installer_name || "—"}</b><div className="table-sub">{item.site_name || "—"} · {item.notes || t("panel.admin.team.no_note")} · {formatDateShort(item.updated_at)}</div></div><Pill state={item.status === "completed" ? "active" : "pending"}>{ASSIGN_KEY[item.status] ? t(ASSIGN_KEY[item.status]) : item.status}</Pill></div>)}</div> : <EmptyState icon="branch" title={t("panel.admin.team.assign_empty_title")} detail={t("panel.admin.team.assign_empty_detail")} />}
    </Card>

    {password ? <PasswordModal account={password} onClose={() => setPassword(null)} onDone={() => { setPassword(null); toast(t("panel.admin.team.password_updated")); }} /> : null}
    {toastNode}
  </>;
}
