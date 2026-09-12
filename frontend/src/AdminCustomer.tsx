import { useCallback, useEffect, useMemo, useState } from "react";
import { api, formatDateShort, formatMoney, mediaObjectUrl, relativeMinutes, toJpeg } from "./api";
import { Card, ConfirmRequest, CopyField, EmptyState, Modal, MonthPicker, PageHeader, Pill, Skeleton, useConfirm, useToast } from "./components";
import { GeometryEditor } from "./GeometryEditor";
import { Icon } from "./icons";
import { t } from "./i18n";

/* Mijoz tafsiloti — admin support vositalari.
 *
 * Eski `admin.html` ning `renderCustomerDetail` i (2 310 qatorli faylning
 * yuragi) shu yerga ko'chdi.  Har vosita jonli do'konda yeyilgan xatodan
 * paydo bo'lgan; sababi tugma yonidagi izohda.  Bu sahifa bo'lmasa
 * do'konni masofadan tuzatib bo'lmaydi — F4 ning birinchi sharti. */

type DeviceHealth = {
  outbox_poisoned?: number; outbox_poisoned_reasons?: string[]; outbox_pending?: number;
  clips?: { written?: number; unavailable?: number; missing?: number; no_segments?: number; cut_failed?: number };
  chain_restarts?: number;
  face_crops?: { written?: number; too_small?: number; suppressed?: number };
  demography?: { off_reason?: string; attempts?: number; found?: number };
  stale_chains?: { running?: number; after_update?: number };
  cameras?: { camera_id: string; connected?: boolean; offline?: boolean; codec?: string; reconnects?: number }[];
  plan_filtered?: number; suppressed?: number;
};
type Device = { id?: string; device_id?: string; hardware_model?: string; product_name?: string; app_version?: string; config_status?: string; connection?: string; minutes_since_seen?: number | null; health?: DeviceHealth; health_at?: string };
type Problem = { camera_id?: string; kind?: string; name?: string; problem: string; measure?: string; role?: string };
export type SiteDetail = {
  id: string; name: string; status?: string; license_status?: string; connection?: string; minutes_since_seen?: number | null;
  cameras_active?: number; cameras_expected?: number; cameras_ok?: boolean; contact_phone?: string; address?: string;
  plan?: string; subscription_until?: string; days_left?: number;
  limits?: { monthly_price_uzs?: number; monthly_price_usd?: number; max_cameras?: number; retention_days?: number };
  devices?: Device[]; geometry_problems?: Problem[]; role_problems?: Problem[]; feature_problems?: Problem[];
  active_pairing_codes?: { code: string; expires_at: string }[]; last_seen?: string; rate_limited?: Record<string, number>;
};
type InventoryCamera = { camera_id: string; label?: string; enabled?: boolean; probe_status?: string; probe_error?: string; codec?: string; width?: number; height?: number; fps?: number; origin?: string; role?: string };
type Onboarding = { steps: { key?: string; label: string; done: boolean }[]; completed: number; total: number };
type Account = { id: string; username: string; full_name?: string; role: string; status: string; site_id?: string };
type Platform = { dl?: string; app?: string; api?: string; apex?: string };

/* Yorliq matn emas, katalog KALITI — modul yuklanganda til hali
   tanlanmagan (`admin.tsx: NAV_ITEMS` izohiga qarang).  `t()` faqat
   chizish paytida chaqiriladi. */
const CONN_KEY: Record<string, string> = { online: "panel.admin.conn.online", stale: "panel.admin.conn.stale_long", not_paired: "panel.admin.conn.not_paired", offline: "panel.admin.conn.offline" };
const CONN_STATE: Record<string, string> = { online: "active", stale: "grace", not_paired: "pending", offline: "failed" };
const LICENSE_KEY: Record<string, string> = { active: "panel.admin.license.active", grace: "panel.admin.license.grace", expired: "panel.admin.license.expired", suspended: "panel.admin.license.suspended", trial: "panel.admin.license.trial" };
const PROBE_KEY: Record<string, string> = { online: "panel.admin.probe.online", offline: "panel.admin.probe.offline", pending: "panel.admin.probe.pending" };
const CONFIG_KEY: Record<string, string> = { applied: "panel.admin.config.applied", pending: "panel.admin.config.pending", error: "panel.admin.config.error", unknown: "panel.admin.config.unknown" };
const PLAN_KEY: Record<string, string> = { boshlangich: "panel.admin.plan.boshlangich", biznes: "panel.admin.plan.biznes", lite: "panel.admin.plan.lite" };
const ROLE_KEY: Record<string, string> = { entrance: "panel.admin.camera_role.entrance", checkout: "panel.admin.camera_role.checkout", sales: "panel.admin.camera_role.sales", storage: "panel.admin.camera_role.storage" };
const CAMERA_SLOTS = ["camera-01", "camera-02", "camera-03", "camera-04"];

/** Heartbeat'dagi raqamlarni odam o'qiydigan qatorlarga aylantiradi.
 *  Bu raqamlar bazada yotardi va do'kondagi nosozlikni faqat SSH bilan
 *  ko'rish mumkin edi — «hodisa bor, klip yo'q» va «2 730 ta yozuv
 *  tashlangan» holatlari shu sabab uzoq sezilmadi. */
function healthLines(health?: DeviceHealth): { text: string; bad?: boolean }[] {
  if (!health) return [];
  const out: { text: string; bad?: boolean }[] = [];
  const n = (value: unknown) => Number(value) || 0;
  if (n(health.outbox_poisoned)) out.push({ text: `${t("panel.admin.health.poisoned", { count: n(health.outbox_poisoned) })}${(health.outbox_poisoned_reasons || []).length ? t("panel.admin.health.poisoned_reasons", { reasons: health.outbox_poisoned_reasons!.join(", ") }) : ""}`, bad: true });
  if (n(health.outbox_pending)) out.push({ text: t("panel.admin.health.pending", { count: n(health.outbox_pending) }) });
  if (n(health.plan_filtered)) out.push({ text: t("panel.admin.health.plan_filtered", { count: n(health.plan_filtered) }) });
  const clips = health.clips || {};
  if (Object.keys(clips).length) out.push({ text: `${t("panel.admin.health.clips", { written: n(clips.written) })}${n(clips.no_segments) ? t("panel.admin.health.clips_no_segments", { count: n(clips.no_segments) }) : ""}${n(clips.cut_failed) ? t("panel.admin.health.clips_cut_failed", { count: n(clips.cut_failed) }) : ""}${n(clips.unavailable) ? t("panel.admin.health.clips_unavailable", { count: n(clips.unavailable) }) : ""}`, bad: n(clips.missing) > 0 && !n(clips.written) });
  if (n(health.chain_restarts)) out.push({ text: t("panel.admin.health.chain_restarts", { count: n(health.chain_restarts) }) });
  const crops = health.face_crops || {};
  if (n(crops.too_small)) out.push({ text: t("panel.admin.health.face_too_small", { count: n(crops.too_small) }), bad: true });
  else if (n(crops.written)) out.push({ text: t("panel.admin.health.face_written", { count: n(crops.written) }) });
  if (n(crops.suppressed)) out.push({ text: t("panel.admin.health.face_suppressed", { count: n(crops.suppressed) }) });
  const demo = health.demography || {};
  if (demo.off_reason) out.push({ text: t("panel.admin.health.demography_off", { reason: demo.off_reason }), bad: true });
  else if (n(demo.attempts)) out.push({ text: t("panel.admin.health.demography", { attempts: n(demo.attempts), found: n(demo.found) }) });
  const stale = health.stale_chains || {};
  if (n(stale.running) > 1 || n(stale.after_update) > 0) out.push({ text: `${n(stale.running) > 1 ? t("panel.admin.health.stale_running", { count: n(stale.running) }) : t("panel.admin.health.stale_after_update", { count: n(stale.after_update) })}${t("panel.admin.health.stale_hint")}`, bad: true });
  (health.cameras || []).forEach(camera => {
    const ok = camera.connected && !camera.offline;
    out.push({ text: `${camera.camera_id}: ${t(ok ? "panel.admin.health.camera_ok" : "panel.admin.health.camera_down")}${camera.codec ? ` · ${camera.codec}` : ""}${n(camera.reconnects) > 5 ? t("panel.admin.health.camera_reconnects", { count: n(camera.reconnects) }) : ""}`, bad: !ok });
  });
  return out;
}

function Banner({ detail }: { detail: SiteDetail }) {
  if (detail.connection === "not_paired") return <div className="status-banner warn"><b>{t("panel.admin.customer.banner_not_paired")}</b><span>{t("panel.admin.customer.banner_not_paired_hint")}</span></div>;
  if (detail.connection === "offline" || detail.connection === "stale") return <div className="status-banner err"><b>{t("panel.admin.customer.banner_silent", { since: relativeMinutes(detail.minutes_since_seen) })}</b><span>{t("panel.admin.customer.banner_silent_hint")}</span></div>;
  if (detail.cameras_expected && !detail.cameras_ok) return <div className="status-banner warn"><b>{t("panel.admin.customer.banner_cameras", { expected: detail.cameras_expected, active: detail.cameras_active || 0 })}</b><span>{t("panel.admin.customer.banner_cameras_hint")}</span></div>;
  return <div className="status-banner ok"><b>{t("panel.admin.customer.banner_ok")}</b><span>{t("panel.admin.customer.banner_ok_hint")}</span></div>;
}

/** Tasodifiy yoki TELEFONDA AYTIB BO'LADIGAN parol.  Do'kon egasiga parol
 *  telefonda aytiladi — SMS shlyuzi yo'q; «olma anor 4821» aytib
 *  bo'ladi, `k7Qm2xW9pL` — yo'q.  Server ham shu shaklda yaratadi. */
const PASSWORD_WORDS = ["olma", "anor", "uzum", "bodom", "shakar", "asal", "chinor", "lola", "qaymoq", "gilos", "nok", "shaftoli", "behi", "tut", "anjir"];
export function generatePassword(readable: boolean): string {
  const random = (limit: number) => crypto.getRandomValues(new Uint32Array(1))[0] % limit;
  if (readable) {
    const first = PASSWORD_WORDS[random(PASSWORD_WORDS.length)];
    let second = PASSWORD_WORDS[random(PASSWORD_WORDS.length)];
    while (second === first) second = PASSWORD_WORDS[random(PASSWORD_WORDS.length)];
    return `${first}${second}${1000 + random(9000)}`;
  }
  const alphabet = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  return Array.from(crypto.getRandomValues(new Uint32Array(14)), value => alphabet[value % alphabet.length]).join("");
}

type ModalKind = "camera" | "expected" | "pairing" | "policy" | "diagnostics" | "geometry" | "login" | "password" | "owner" | "link" | "features" | "invoice" | "extend" | "plan" | null;

export function AdminCustomer({ siteId, onBack, onChanged }: { siteId: string; onBack: () => void; onChanged: () => Promise<void> }) {
  const [detail, setDetail] = useState<SiteDetail | null>(null);
  const [inventory, setInventory] = useState<InventoryCamera[]>([]);
  const [onboarding, setOnboarding] = useState<Onboarding | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [platform, setPlatform] = useState<Platform>({});
  const [error, setError] = useState("");
  const [modal, setModal] = useState<ModalKind>(null);
  const [modalPayload, setModalPayload] = useState<unknown>(null);
  const [busy, setBusy] = useState("");
  const [confirm, confirmDialog] = useConfirm();
  const [toast, toastNode] = useToast();

  const id = encodeURIComponent(siteId);
  const load = useCallback(async () => {
    try {
      const [next, cameras, steps, users] = await Promise.all([
        api<SiteDetail>(`/api/v1/admin/sites/${id}`, "admin"),
        api<{ cameras: InventoryCamera[] }>(`/api/v1/admin/sites/${id}/camera-inventory`, "admin").catch(() => ({ cameras: [] })),
        api<Onboarding>(`/api/v1/admin/sites/${id}/onboarding`, "admin").catch(() => null),
        api<{ accounts: Account[] }>("/api/v1/admin/accounts", "admin").catch(() => ({ accounts: [] })),
      ]);
      setDetail(next); setInventory(cameras.cameras || []); setOnboarding(steps); setAccounts(users.accounts || []); setError("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : t("panel.admin.customer.open_failed")); }
  }, [id]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    // Yuklab olish va panel manzillari subdomenlarda — havola apex'dan
    // emas, o'sha bo'limdan qurilishi kerak.
    fetch("/api/v1/public/urls").then(r => r.ok ? r.json() : null).then(data => { if (data) setPlatform(data); }).catch(() => {});
  }, []);

  /** Amalni bajaradi, natijani aytadi, sahifani yangilaydi. */
  const run = async (key: string, action: () => Promise<string | void>, refresh = true) => {
    setBusy(key);
    try {
      const message = await action();
      if (message) toast(message);
      if (refresh) { await load(); await onChanged(); }
    } catch (reason) { toast(reason instanceof Error ? reason.message : t("panel.admin.action_failed"), false); }
    finally { setBusy(""); }
  };

  const open = (kind: ModalKind, payload: unknown = null) => { setModalPayload(payload); setModal(kind); };
  const close = () => { setModal(null); setModalPayload(null); };

  if (error) return <><PageHeader title={t("panel.admin.col_customer")} subtitle={siteId} actions={<button className="btn" onClick={onBack}>{t("panel.admin.customer.back")}</button>} /><Card><EmptyState icon="bell" title={t("panel.admin.customer.open_failed")} detail={error} /></Card></>;
  if (!detail) return <><PageHeader title={t("panel.admin.col_customer")} subtitle={t("panel.common.loading")} actions={<button className="btn" onClick={onBack}>{t("panel.admin.customer.back")}</button>} /><Card><div className="card-body"><Skeleton height={220} /></div></Card></>;

  const suspended = detail.status === "suspended";
  const portalLogin = accounts.find(account => account.role === "customer" && account.site_id === detail.id && account.status !== "disabled");
  const limits = detail.limits || {};
  const cameraOptions = inventory.map(camera => ({ camera_id: camera.camera_id, label: camera.label }));

  // ── Amallar ──────────────────────────────────────────────────────────
  const cleanChains = () => run("clean", async () => {
    const answer = await api<{ job?: { reused?: boolean } }>(`/api/v1/admin/sites/${id}/jobs/clean-chains`, "admin", { method: "POST" });
    return t(answer.job?.reused ? "panel.admin.customer.clean_reused" : "panel.admin.customer.clean_sent");
  }, false);
  const benchmark = async () => {
    // O'lchov protsessorni to'liq yuklaydi va tahlil sekinlashadi —
    // shuning uchun tasdiq bilan.  Natija «Diagnostika» da ko'rinadi.
    if (!(await confirm({ title: t("panel.admin.customer.benchmark"), text: t("panel.admin.customer.benchmark_confirm_text"), confirmLabel: t("panel.admin.customer.benchmark_confirm") }))) return;
    await run("benchmark", async () => {
      const answer = await api<{ job?: { reused?: boolean } }>(`/api/v1/admin/sites/${id}/jobs/benchmark`, "admin", { method: "POST" });
      return t(answer.job?.reused ? "panel.admin.customer.benchmark_reused" : "panel.admin.customer.benchmark_started");
    }, false);
  };
  const setStatus = async (to: "active" | "suspended") => {
    const ok = to === "suspended"
      ? await confirm({ title: t("panel.admin.customer.suspend"), text: t("panel.admin.customer.suspend_text", { name: detail.name }), confirmLabel: t("panel.admin.customer.suspend_confirm"), danger: true, typed: detail.name })
      : await confirm({ title: t("panel.admin.customer.resume"), text: t("panel.admin.customer.resume_text", { name: detail.name }), confirmLabel: t("panel.admin.customer.resume_confirm") });
    if (!ok) return;
    await run("status", async () => { await api(`/api/v1/admin/sites/${id}/status`, "admin", { method: "POST", body: JSON.stringify({ status: to }) }); return t(to === "suspended" ? "panel.admin.customer.suspended_toast" : "panel.admin.customer.resumed_toast"); });
  };
  const newPairing = () => run("pairing", async () => {
    const result = await api<{ pairing_code: string; pairing_expires_at?: string }>(`/api/v1/admin/sites/${id}/pairing`, "admin", { method: "POST" });
    open("pairing", result);
  });
  const createLogin = () => run("login", async () => {
    const login = await api<{ username: string; password: string }>(`/api/v1/admin/sites/${id}/login`, "admin", { method: "POST" });
    open("login", login);
  });

  const problems = [...(detail.feature_problems || []), ...(detail.geometry_problems || []), ...(detail.role_problems || [])];

  return <>
    <PageHeader title={detail.name} subtitle={`${detail.contact_phone || t("panel.admin.customer.no_phone")} · ${detail.address || t("panel.admin.customer.no_address")}`} actions={<>
      <Pill state={detail.license_status === "active" ? "active" : "failed"}>{LICENSE_KEY[detail.license_status || ""] ? t(LICENSE_KEY[detail.license_status || ""]) : detail.license_status || "—"}</Pill>
      <Pill state={CONN_STATE[detail.connection || ""]}>{t(CONN_KEY[detail.connection || ""] || "panel.admin.conn.offline")}</Pill>
      <button className="btn" onClick={onBack}>{t("panel.admin.customer.back")}</button>
    </>} />
    <Banner detail={detail} />

    {/* ── Qurilma va kamera ─────────────────────────────────────── */}
    <Card className="section-gap">
      <div className="card-head"><div><h2>{t("panel.admin.customer.device_title")}</h2><p>{t("panel.admin.customer.device_subtitle", { cameras: inventory.length, devices: (detail.devices || []).length })}</p></div></div>
      {inventory.length ? <div className="table-wrap"><table>
        <thead><tr><th>{t("panel.admin.customer.col_camera")}</th><th>{t("panel.admin.customer.col_role")}</th><th>{t("panel.admin.customer.col_probe")}</th><th>{t("panel.admin.customer.col_quality")}</th><th>{t("panel.admin.col_status")}</th></tr></thead>
        <tbody>{inventory.map(camera => <tr key={camera.camera_id}>
          <td><div className="table-title">{camera.label || camera.camera_id}</div><div className="table-sub">{camera.camera_id}{camera.origin === "device" ? t("panel.admin.customer.from_device") : ""}</div></td>
          <td>{ROLE_KEY[camera.role || ""] ? t(ROLE_KEY[camera.role || ""]) : "—"}</td>
          <td><Pill state={camera.probe_status === "online" ? "active" : camera.probe_status === "offline" ? "failed" : "pending"}>{t(PROBE_KEY[camera.probe_status || ""] || "panel.admin.probe.unknown")}</Pill>{camera.probe_error ? <div className="table-sub">{camera.probe_error}</div> : null}</td>
          <td>{[camera.codec, camera.width && camera.height ? `${camera.width}×${camera.height}` : "", camera.fps ? `${camera.fps} FPS` : ""].filter(Boolean).join(" · ") || "—"}</td>
          <td>{t(camera.enabled === false ? "panel.admin.customer.camera_disabled" : "panel.admin.customer.camera_enabled")}</td>
        </tr>)}</tbody>
      </table></div> : <div className="card-body"><p className="metric-note">{t("panel.admin.customer.no_cameras")}</p></div>}

      <div className="card-body">
        {(detail.devices || []).length ? (detail.devices || []).map((device, index) => {
          const lines = healthLines(device.health);
          return <div className="device-row" key={device.id || device.device_id || index}>
            <div><b>{t("panel.admin.customer.device_n", { index: index + 1 })}</b><small>{device.hardware_model || device.product_name || t("panel.admin.customer.windows_pc")} · {t("panel.admin.customer.app_version", { version: device.app_version || t("panel.common.unknown") })} · {t(CONFIG_KEY[device.config_status || ""] || CONFIG_KEY.unknown)}</small>
              {lines.length ? <ul className="health-lines">{lines.map((line, i) => <li key={i} className={line.bad ? "is-bad" : ""}>{line.text}</li>)}</ul> : null}</div>
            <Pill state={CONN_STATE[device.connection || ""]}>{CONN_KEY[device.connection || ""] ? t(CONN_KEY[device.connection || ""]) : device.connection || "—"}</Pill>
            <span className="table-sub">{relativeMinutes(device.minutes_since_seen)}</span>
          </div>;
        }) : <p className="metric-note">{t("panel.admin.customer.no_device")}</p>}

        {(detail.feature_problems || []).length ? <div className="note warn"><b>{t("panel.admin.customer.feature_problems")}</b>{(detail.feature_problems || []).map((p, i) => <div key={i}>{p.name} — {p.problem}{p.measure ? <small> ({p.measure})</small> : null}</div>)}</div> : null}
        {(detail.geometry_problems || []).length ? <div className="note warn"><b>{t("panel.admin.customer.geometry_problems", { count: (detail.geometry_problems || []).length })}</b>{(detail.geometry_problems || []).map((p, i) => <div key={i}>{p.camera_id} · {t(p.kind === "line" ? "panel.admin.customer.kind_line" : "panel.admin.customer.kind_zone")} «{p.name}» — {p.problem}</div>)}</div> : null}
        {(detail.role_problems || []).length ? <div className="note warn"><b>{t("panel.admin.customer.role_problems")}</b>{(detail.role_problems || []).map((p, i) => <div key={i}>{p.camera_id} · {ROLE_KEY[p.role || ""] ? t(ROLE_KEY[p.role || ""]) : p.role || ""} — {p.problem}</div>)}</div> : null}
        {!problems.length && (detail.devices || []).length ? <p className="metric-note">{t("panel.admin.customer.checks_clean")}</p> : null}

        <div className="page-actions wrap">
          <button className="btn btn-primary" onClick={() => open("camera")}><Icon name="camera" />{t("panel.admin.customer.add_camera")}</button>
          <button className="btn" onClick={() => open("expected")}>{t("panel.admin.customer.camera_count")}</button>
          <button className="btn" disabled={busy === "pairing"} onClick={() => void newPairing()}>{t("panel.admin.customer.new_pairing")}</button>
          <button className="btn" onClick={() => open("policy")}>{t("panel.admin.customer.update_policy")}</button>
          <button className="btn" disabled={!inventory.length} onClick={() => open("geometry")}><Icon name="shapes" />{t("panel.admin.customer.geometry")}</button>
          <button className="btn" onClick={() => open("diagnostics")}>{t("panel.admin.customer.diagnostics")}</button>
          {(detail.devices || []).length ? <>
            <button className="btn" disabled={busy === "clean"} onClick={() => void cleanChains()}>{t("panel.admin.customer.clean_chains")}</button>
            <button className="btn" disabled={busy === "benchmark"} onClick={() => void benchmark()}>{t("panel.admin.customer.benchmark")}</button>
          </> : null}
        </div>
      </div>
    </Card>

    {/* ── Kirish va a'zolar ─────────────────────────────────────── */}
    <Card className="section-gap">
      <div className="card-head"><div><h2>{t("panel.admin.customer.access_title")}</h2><p>{onboarding ? t("panel.admin.customer.onboarding_done", { done: onboarding.completed, total: onboarding.total }) : t("panel.admin.customer.onboarding_missing")}</p></div></div>
      <div className="card-body">
        {onboarding ? <div className="simple-list">
          {onboarding.steps.filter(step => !step.done).map(step => <div className="simple-row" key={step.key || step.label}><span>{step.label}</span><Pill state="pending">{t("panel.billing.state_pending")}</Pill></div>)}
          {onboarding.steps.every(step => step.done) ? <div className="note ok"><b>{t("panel.admin.customer.onboarding_complete")}</b>{t("panel.admin.customer.onboarding_complete_hint")}</div> : null}
          {onboarding.steps.some(step => step.done) ? <details className="quiet"><summary>{t("panel.admin.customer.onboarding_collapsed", { count: onboarding.steps.filter(step => step.done).length })}</summary>{onboarding.steps.filter(step => step.done).map(step => <div className="simple-row" key={step.key || step.label}><span>{step.label}</span><Pill state="active">{t("panel.admin.customer.step_done")}</Pill></div>)}</details> : null}
        </div> : null}
        <div className="simple-row"><div><b>{t("panel.admin.customer.portal_login")}</b><div className="table-sub">{portalLogin ? t("panel.admin.customer.portal_login_hint", { username: portalLogin.username }) : t("panel.admin.customer.portal_login_missing")}</div></div><Pill state={portalLogin ? "active" : "pending"}>{t(portalLogin ? "panel.admin.customer.has" : "panel.common.no")}</Pill></div>
        <div className="page-actions wrap">
          {portalLogin
            ? <button className="btn" onClick={() => open("password", portalLogin)}>{t("panel.admin.customer.reset_password")}</button>
            : <button className="btn btn-primary" disabled={busy === "login"} onClick={() => void createLogin()}>{t("panel.admin.customer.create_login")}</button>}
          <button className="btn" onClick={() => open("owner")}>{t("panel.admin.customer.add_owner")}</button>
          <button className="btn" onClick={() => open("link")}>{t("panel.admin.customer.make_link")}</button>
        </div>
      </div>
    </Card>

    {/* ── Tarif va to'lov ───────────────────────────────────────── */}
    <Card className="section-gap">
      <div className="card-head"><div><h2>{t("panel.admin.customer.billing_title")}</h2><p>{t("panel.admin.customer.billing_subtitle")}</p></div></div>
      <div className="card-body">
        <div className="simple-list">
          <div className="simple-row"><span>{t("panel.admin.col_plan")}</span><b>{t("panel.admin.customer.plan_value", { plan: PLAN_KEY[detail.plan || ""] ? t(PLAN_KEY[detail.plan || ""]) : detail.plan || "—", price: formatMoney(limits.monthly_price_uzs, { short: false }) })}{limits.monthly_price_usd ? ` ($${limits.monthly_price_usd})` : ""}</b></div>
          <div className="simple-row"><span>{t("panel.admin.customer.subscription_until")}</span><b>{formatDateShort(detail.subscription_until)}{detail.days_left != null ? t("panel.admin.customer.days_left_suffix", { count: detail.days_left }) : ""}</b></div>
          <div className="simple-row"><span>{t("panel.admin.customer.limits")}</span><b>{t("panel.admin.customer.limits_value", { cameras: limits.max_cameras ?? "—", days: limits.retention_days ?? "—" })}</b></div>
        </div>
        <div className="page-actions wrap">
          <button className="btn btn-primary" onClick={() => open("features")}>{t("panel.admin.customer.features")}</button>
          <button className="btn" onClick={() => open("invoice")}>{t("panel.admin.customer.open_invoice")}</button>
          <button className="btn" onClick={() => open("extend")}>{t("panel.admin.customer.extend")}</button>
          <button className="btn" onClick={() => open("plan")}>{t("panel.admin.customer.change_plan")}</button>
        </div>
      </div>
    </Card>

    <FacesCard siteId={siteId} toast={toast} confirm={confirm} />

    <Card className="section-gap card-danger">
      <div className="card-head"><div><h2>{t("panel.admin.customer.danger_title")}</h2><p>{t("panel.admin.customer.danger_subtitle")}</p></div></div>
      <div className="card-body"><button className={`btn ${suspended ? "btn-primary" : "btn-danger"}`} disabled={busy === "status"} onClick={() => void setStatus(suspended ? "active" : "suspended")}>{t(suspended ? "panel.admin.customer.resume" : "panel.admin.customer.suspend")}</button></div>
    </Card>

    <details className="card quiet section-gap">
      <summary><b>{t("panel.admin.customer.tech_title")}</b></summary>
      <div className="card-body simple-list">
        <div className="simple-row"><span>{t("panel.admin.customer.internal_id")}</span><CopyField value={detail.id} /></div>
        <div className="simple-row"><span>{t("panel.admin.customer.pairing_codes")}</span><b>{(detail.active_pairing_codes || []).length ? (detail.active_pairing_codes || []).map(code => <div key={code.code} className="mono">{code.code} <small>{t("panel.admin.customer.code_until", { time: String(code.expires_at).slice(0, 16) })}</small></div>) : t("panel.admin.customer.no_code")}</b></div>
        <div className="simple-row"><span>{t("panel.admin.customer.last_seen")}</span><b>{detail.last_seen || t("panel.admin.customer.never")} (UTC)</b></div>
        {detail.rate_limited && Object.keys(detail.rate_limited).length ? <div className="simple-row"><span>{t("panel.admin.customer.rate_limited")}</span><b>{Object.entries(detail.rate_limited).map(([key, count]) => `${key}: ${count}`).join(" · ")}</b></div> : null}
      </div>
    </details>

    {/* ── Modallar ──────────────────────────────────────────────── */}
    {modal === "camera" ? <CameraModal siteId={siteId} taken={inventory} onClose={close} onDone={message => { close(); void run("camera", async () => message); }} /> : null}
    {modal === "expected" ? <ExpectedModal siteId={siteId} current={detail.cameras_expected || 0} onClose={close} onDone={() => { close(); void run("expected", async () => t("panel.admin.customer.expected_saved")); }} /> : null}
    {modal === "pairing" ? <PairingModal name={detail.name} result={modalPayload as { pairing_code: string; pairing_expires_at?: string }} platform={platform} onClose={close} /> : null}
    {modal === "policy" ? <PolicyModal siteId={siteId} onClose={close} onDone={message => { close(); toast(message); }} /> : null}
    {modal === "diagnostics" ? <DiagnosticsModal siteId={siteId} onClose={close} /> : null}
    {modal === "geometry" ? <Modal title={t("panel.admin.customer.geometry")} wide onClose={close}><GeometryEditor kind="admin" siteId={siteId} cameras={cameraOptions} onSaved={() => { toast(t("panel.admin.customer.geometry_saved")); void load(); }} /></Modal> : null}
    {modal === "login" ? <LoginModal name={detail.name} phone={detail.contact_phone} login={modalPayload as { username: string; password: string }} platform={platform} onClose={close} /> : null}
    {modal === "password" ? <PasswordModal account={modalPayload as Account} onClose={close} onDone={() => { close(); toast(t("panel.admin.team.password_updated")); }} /> : null}
    {modal === "owner" ? <TelegramModal title={t("panel.admin.customer.add_owner")} hint={t("panel.admin.customer.owner_hint")} submitLabel={t("panel.common.add")} onClose={close} onSubmit={async telegramId => { await api(`/api/v1/admin/sites/${id}/members`, "admin", { method: "POST", body: JSON.stringify({ telegram_id: telegramId, role: "owner" }) }); close(); toast(t("panel.admin.customer.owner_added")); }} /> : null}
    {modal === "link" ? <TelegramModal title={t("panel.admin.customer.make_link")} hint={t("panel.admin.customer.link_hint")} submitLabel={t("panel.admin.invoice.submit")} onClose={close} onSubmit={async telegramId => { const link = await api<{ url: string; expires_days: number }>(`/api/v1/admin/sites/${id}/members/${encodeURIComponent(telegramId)}/login-link`, "admin", { method: "POST" }); open("pairing", { link }); }} /> : null}
    {modal === "pairing" && (modalPayload as { link?: { url: string; expires_days: number } })?.link ? null : null}
    {modal === "features" ? <FeaturesModal siteId={siteId} name={detail.name} onClose={close} onDone={message => { close(); void run("features", async () => message); }} /> : null}
    {modal === "invoice" ? <InvoiceModal siteId={siteId} name={detail.name} perMonth={limits.monthly_price_uzs || 0} platform={platform} onClose={close} onDone={() => void onChanged()} /> : null}
    {modal === "extend" ? <ExtendModal siteId={siteId} name={detail.name} until={detail.subscription_until} onClose={close} onDone={message => { close(); void run("extend", async () => message); }} /> : null}
    {modal === "plan" ? <PlanModal siteId={siteId} current={detail.plan || ""} onClose={close} onDone={() => { close(); void run("plan", async () => t("panel.admin.customer.plan_changed")); }} /> : null}
    {confirmDialog}
    {toastNode}
  </>;
}

// ── Modallar ────────────────────────────────────────────────────────────

function CameraModal({ siteId, taken, onClose, onDone }: { siteId: string; taken: InventoryCamera[]; onClose: () => void; onDone: (message: string) => void }) {
  const used = new Map(taken.map(camera => [camera.camera_id, camera.label || camera.camera_id]));
  const free = CAMERA_SLOTS.find(slot => !used.has(slot)) || CAMERA_SLOTS[0];
  const [slot, setSlot] = useState(free); const [label, setLabel] = useState(""); const [rtsp, setRtsp] = useState(""); const [role, setRole] = useState(""); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (!label.trim()) { setError(t("panel.admin.camera_modal.name_required")); return; }
    if (!/^rtsps?:\/\//.test(rtsp.trim())) { setError(t("panel.admin.camera_modal.bad_url")); return; }
    setBusy(true); setError("");
    try {
      await api(`/api/v1/admin/sites/${encodeURIComponent(siteId)}/camera-inventory/${encodeURIComponent(slot)}`, "admin", { method: "PUT", body: JSON.stringify({ label: label.trim(), rtsp_url: rtsp.trim(), enabled: true, role }) });
      onDone(t("panel.admin.camera_modal.saved"));
    } catch (reason) { setError(reason instanceof Error ? reason.message : t("panel.numbers.save_failed")); setBusy(false); }
  };
  /* Nom takliflari — rol yorliqlari bilan bir xil matn, ustiga «orqa eshik».
     Admin yozgan nom do'kon egasining panelida ham ko'rinadi. */
  const nameHints = [...Object.values(ROLE_KEY), "panel.admin.camera_modal.name_back_door"].map(key => t(key));
  return <Modal title={t("panel.admin.customer.add_camera")} onClose={onClose} footer={<><button className="btn" onClick={onClose}>{t("panel.common.cancel")}</button><button className="btn btn-primary" disabled={busy} onClick={() => void submit()}>{t(busy ? "panel.common.saving" : "panel.common.save")}</button></>}>
    <label className="field-label">{t("panel.admin.camera_modal.slot")}<select className="select" value={slot} onChange={event => setSlot(event.target.value)}>{CAMERA_SLOTS.map((item, index) => <option key={item} value={item}>{t("panel.admin.camera_modal.slot_n", { index: index + 1 })}{used.has(item) ? t("panel.admin.camera_modal.slot_taken", { label: used.get(item)! }) : t("panel.admin.camera_modal.slot_free")}</option>)}</select></label>
    <label className="field-label">{t("panel.admin.camera_modal.name")}<input className="input" list="adminCameraNames" placeholder={t("panel.admin.camera_role.entrance")} value={label} onChange={event => setLabel(event.target.value)} /><datalist id="adminCameraNames">{nameHints.map(hint => <option key={hint} value={hint} />)}</datalist></label>
    <label className="field-label">{t("panel.admin.customer.col_role")}<select className="select" value={role} onChange={event => setRole(event.target.value)}><option value="">{t("panel.setup.role.none")}</option>{Object.entries(ROLE_KEY).map(([code, key]) => <option key={code} value={code}>{t(key)}</option>)}</select></label>
    <label className="field-label">{t("panel.admin.camera_modal.rtsp")}<input className="input" placeholder="rtsp://login:parol@192.168.1.10:554/stream/sub" value={rtsp} onChange={event => setRtsp(event.target.value)} /><small>{t("panel.admin.camera_modal.rtsp_hint")}</small></label>
    {error ? <div className="form-error" role="alert">{error}</div> : null}
  </Modal>;
}

function ExpectedModal({ siteId, current, onClose, onDone }: { siteId: string; current: number; onClose: () => void; onDone: () => void }) {
  const [count, setCount] = useState(current); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const submit = async () => { setBusy(true); try { await api(`/api/v1/admin/sites/${encodeURIComponent(siteId)}/cameras`, "admin", { method: "POST", body: JSON.stringify({ expected: count }) }); onDone(); } catch (reason) { setError(reason instanceof Error ? reason.message : t("panel.numbers.save_failed")); setBusy(false); } };
  return <Modal title={t("panel.admin.customer.camera_count")} onClose={onClose} footer={<><button className="btn" onClick={onClose}>{t("panel.common.cancel")}</button><button className="btn btn-primary" disabled={busy} onClick={() => void submit()}>{t("panel.common.save")}</button></>}>
    <p className="modal-text">{t("panel.admin.expected.text")}</p>
    <label className="field-label">{t("panel.admin.expected.label")}<select className="select" value={count} onChange={event => setCount(Number(event.target.value))}>{[0, 1, 2, 3, 4].map(n => <option key={n} value={n}>{t("panel.admin.expected.count", { count: n })}</option>)}</select></label>
    {error ? <div className="form-error">{error}</div> : null}
  </Modal>;
}

function PairingModal({ name, result, platform, onClose }: { name: string; result: { pairing_code?: string; pairing_expires_at?: string; link?: { url: string; expires_days: number } }; platform: Platform; onClose: () => void }) {
  // Kirish havolasi ham shu oynada: ikkalasi «mijozga yuboriladigan havola».
  if (result.link) {
    return <Modal title={t("panel.admin.pairing.link_title")} onClose={onClose}>
      <CopyField value={result.link.url} />
      <p className="metric-note">{t("panel.admin.pairing.link_note", { days: result.link.expires_days })}</p>
      <a className="btn" href={`https://t.me/share/url?url=${encodeURIComponent(result.link.url)}`} target="_blank" rel="noopener noreferrer"><Icon name="telegram" />{t("panel.admin.pairing.send_telegram")}</a>
    </Modal>;
  }
  // Windows uchun asosiy yo'l: kod havolaga qo'shiladi, mijoz 6 ta
  // belgini qo'lda ko'chirmaydi.
  const base = (platform.dl || window.location.origin).replace(/\/$/, "");
  const link = `${base}/api/v1/public/download-installer?code=${encodeURIComponent(result.pairing_code || "")}`;
  return <Modal title={t("panel.admin.pairing.title", { name })} onClose={onClose}>
    <p className="modal-text"><b>{t("panel.admin.pairing.send_this")}</b>{t("panel.admin.pairing.send_this_hint")}</p>
    <CopyField value={link} />
    <p className="metric-note">{t("panel.admin.pairing.note")}</p>
    <details className="quiet"><summary>{t("panel.admin.pairing.manual")}</summary><div className="code-box">{result.pairing_code}</div><p className="metric-note">{t("panel.admin.pairing.manual_note", { time: String(result.pairing_expires_at || "").slice(0, 16) })}</p></details>
  </Modal>;
}

function PolicyModal({ siteId, onClose, onDone }: { siteId: string; onClose: () => void; onDone: (message: string) => void }) {
  const [info, setInfo] = useState<{ releases: { version: string; signed?: boolean; size_mb?: number }[]; latest?: string | null } | null>(null);
  const [choice, setChoice] = useState<"auto" | "hold" | "pin">("auto"); const [version, setVersion] = useState(""); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  /* Xatoda BO'SH ro'yxat, `null` emas: `null` skeletni abadiy
     ushlab turardi va oynada «Saqlash» tugmasi ham hech qachon
     ochilmasdi — admin nima bo'lganini bilmasdi. */
  useEffect(() => { api<{ releases: { version: string; signed?: boolean }[]; latest?: string | null }>("/api/v1/admin/windows-releases", "admin").then(data => { setInfo(data); setVersion(data.latest || data.releases[0]?.version || ""); }).catch(reason => { setInfo({ releases: [] }); setError(reason instanceof Error ? reason.message : t("panel.admin.policy.load_failed")); }); }, []);
  const submit = async () => {
    setBusy(true); setError("");
    try {
      await api(`/api/v1/admin/sites/${encodeURIComponent(siteId)}/update-policy`, "admin", { method: "PUT", body: JSON.stringify(choice === "pin" ? { channel: "pin", version } : { channel: choice }) });
      // Va'da o'rnatuvchidagi jadval bilan bir xil (15 daqiqa) —
      // `tests/test_windows_installer.py` buni qulflaydi.
      onDone(t(choice === "hold" ? "panel.admin.settings.paused_toast" : "panel.admin.policy.saved"));
    } catch (reason) { setError(reason instanceof Error ? reason.message : t("panel.numbers.save_failed")); setBusy(false); }
  };
  return <Modal title={t("panel.admin.customer.update_policy")} onClose={onClose} footer={<><button className="btn" onClick={onClose}>{t("panel.common.cancel")}</button><button className="btn btn-primary" disabled={busy || !info?.releases.length} onClick={() => void submit()}>{t("panel.common.save")}</button></>}>
    {info ? <>
      <p className="modal-text">{t("panel.admin.policy.latest")}<b>{info.latest || "—"}</b>{info.releases.length ? "" : t("panel.admin.policy.no_release")}</p>
      {(["auto", "hold", "pin"] as const).map(code => <label key={code} className="choice"><input type="radio" name="policy" checked={choice === code} onChange={() => setChoice(code)} /><span><b>{t(`panel.admin.policy.${code}`)}</b><small>{t(`panel.admin.policy.${code}_hint`)}</small></span></label>)}
      {choice === "pin" ? <label className="field-label">{t("panel.admin.policy.version")}<select className="select" value={version} onChange={event => setVersion(event.target.value)}>{info.releases.map(release => <option key={release.version} value={release.version}>{release.version}{release.signed ? "" : t("panel.admin.policy.unsigned")}</option>)}</select></label> : null}
    </> : <Skeleton height={120} />}
    {error ? <div className="form-error">{error}</div> : null}
  </Modal>;
}

function BenchmarkBlock({ job }: { job: { status?: string; error?: string; updated_at?: string; result?: Record<string, unknown> } | null }) {
  if (!job) return null;
  if (job.status !== "done") return <div className="note warn"><b>{t("panel.admin.diagnostics.benchmark_state", { status: job.status || "" })}</b>{job.error || t("panel.admin.diagnostics.benchmark_unfinished")}</div>;
  const result = (job.result || {}) as { device?: string; frame_size?: number[]; native_size?: number[]; detector?: { throughput_fps?: number; p95_ms?: number }; verdict?: { supported_cameras?: number; cameras?: number; ok?: boolean } };
  const native = (result.native_size || []).filter(Boolean).join("×");
  return <div className="note ok"><b>{t("panel.admin.diagnostics.benchmark_done", { time: job.updated_at || "" })}</b>
    <div>{t("panel.admin.diagnostics.device_frame", { device: result.device || "—", frame: (result.frame_size || []).join("×") || "—" })}{native ? <> · <b>{t("panel.admin.diagnostics.native_size", { size: native })}</b></> : null}</div>
    <div>{t("panel.admin.diagnostics.detector", { fps: Number(result.detector?.throughput_fps || 0).toFixed(1), p95: Number(result.detector?.p95_ms || 0).toFixed(0) })}</div>
    <div>{t("panel.admin.diagnostics.verdict_prefix")}<b>{t("panel.admin.diagnostics.verdict", { count: Number(result.verdict?.supported_cameras || 0) })}</b>{t("panel.admin.diagnostics.verdict_asked", { count: Number(result.verdict?.cameras || 0) })}{result.verdict?.ok === false ? t("panel.admin.diagnostics.verdict_short") : ""}</div>
  </div>;
}

function DiagnosticsModal({ siteId, onClose }: { siteId: string; onClose: () => void }) {
  const [data, setData] = useState<{ diagnostics: { device_id?: string; created_at?: string; payload?: unknown } | null; benchmark: { status?: string; error?: string; updated_at?: string; result?: Record<string, unknown> } | null } | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { api<{ diagnostics: { device_id?: string; created_at?: string; payload?: unknown } | null; benchmark: { status?: string } | null }>(`/api/v1/admin/sites/${encodeURIComponent(siteId)}/diagnostics`, "admin").then(setData).catch(reason => setError(reason instanceof Error ? reason.message : t("panel.admin.diagnostics.load_failed"))); }, [siteId]);
  return <Modal title={t("panel.admin.diagnostics.title")} wide onClose={onClose}>
    {error ? <div className="form-error">{error}</div> : !data ? <Skeleton height={160} /> : <>
      <BenchmarkBlock job={data.benchmark} />
      {data.diagnostics ? <>
        <div className="simple-list"><div className="simple-row"><span>{t("panel.admin.diagnostics.device")}</span><b>{data.diagnostics.device_id || "—"}</b></div><div className="simple-row"><span>{t("panel.admin.diagnostics.received_at")}</span><b>{data.diagnostics.created_at || "—"}</b></div></div>
        <pre className="diag-json">{JSON.stringify(data.diagnostics.payload || {}, null, 2)}</pre>
      </> : <p className="metric-note">{t("panel.admin.diagnostics.empty")}</p>}
    </>}
  </Modal>;
}

function LoginModal({ name, phone, login, platform, onClose }: { name: string; phone?: string; login: { username: string; password: string }; platform: Platform; onClose: () => void }) {
  const url = `${(platform.app || window.location.origin).replace(/\/$/, "")}/owner`;
  const message = t("panel.admin.login_modal.message", { url, username: login.username, password: login.password });
  return <Modal title={t("panel.admin.login_modal.title", { name })} onClose={onClose}>
    <div className="note warn"><b>{t("panel.admin.login_modal.warn")}</b> {t("panel.admin.login_modal.warn_hint")}</div>
    <div className="simple-list"><div className="simple-row"><span>{t("panel.login.username")}</span><b className="mono">{login.username}</b></div><div className="simple-row"><span>{t("panel.login.password")}</span><b className="mono">{login.password}</b></div><div className="simple-row"><span>{t("panel.admin.login_modal.url")}</span><b className="mono">{url}</b></div></div>
    <CopyField value={message} label={t("panel.admin.login_modal.copy")} />
    {phone ? <p className="metric-note">{t("panel.admin.login_modal.phone")}<a href={`tel:${phone}`}>{phone}</a></p> : null}
    <p className="metric-note">{t("panel.admin.login_modal.password_note")}</p>
  </Modal>;
}

export function PasswordModal({ account, onClose, onDone }: { account: Account; onClose: () => void; onDone: () => void }) {
  const [password, setPassword] = useState(""); const [show, setShow] = useState(false); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (password.length < 10) { setError(t("panel.admin.password.too_short")); return; }
    setBusy(true); setError("");
    try { await api(`/api/v1/admin/accounts/${encodeURIComponent(account.id)}/password`, "admin", { method: "POST", body: JSON.stringify({ new_password: password }) }); onDone(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : t("panel.numbers.save_failed")); setBusy(false); }
  };
  return <Modal title={t("panel.admin.password.title")} onClose={onClose} footer={<><button className="btn" onClick={onClose}>{t("panel.common.cancel")}</button><button className="btn btn-primary" disabled={busy} onClick={() => void submit()}>{t("panel.common.save")}</button></>}>
    <p className="modal-text">{t("panel.admin.password.text", { name: account.full_name || account.username })}</p>
    <label className="field-label">{t("panel.admin.password.label")}<input className="input" type={show ? "text" : "password"} autoComplete="new-password" value={password} onChange={event => setPassword(event.target.value)} /></label>
    <div className="page-actions wrap">
      <button className="btn" type="button" onClick={() => { setPassword(generatePassword(account.role === "customer")); setShow(true); }}>{t("panel.admin.password.generate")}</button>
      <button className="btn" type="button" onClick={() => setShow(value => !value)}>{t(show ? "panel.admin.password.hide" : "panel.admin.password.show")}</button>
      {password ? <CopyField value={password} /> : null}
    </div>
    {error ? <div className="form-error">{error}</div> : null}
  </Modal>;
}

function TelegramModal({ title, hint, submitLabel, onClose, onSubmit }: { title: string; hint: string; submitLabel: string; onClose: () => void; onSubmit: (telegramId: string) => Promise<void> }) {
  const [value, setValue] = useState(""); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (!/^[-0-9]{3,32}$/.test(value.trim())) { setError(t("panel.admin.telegram_modal.bad_id")); return; }
    setBusy(true); setError("");
    try { await onSubmit(value.trim()); } catch (reason) { setError(reason instanceof Error ? reason.message : t("panel.admin.telegram_modal.failed")); setBusy(false); }
  };
  return <Modal title={title} onClose={onClose} footer={<><button className="btn" onClick={onClose}>{t("panel.common.cancel")}</button><button className="btn btn-primary" disabled={busy} onClick={() => void submit()}>{submitLabel}</button></>}>
    <p className="modal-text">{hint}</p>
    <label className="field-label">{t("panel.admin.telegram_modal.label")}<input className="input" inputMode="numeric" placeholder="123456789" value={value} onChange={event => setValue(event.target.value)} /><small>{t("panel.admin.telegram_modal.hint")}</small></label>
    {error ? <div className="form-error">{error}</div> : null}
  </Modal>;
}

type Feature = { code: string; name: string; queue_kind?: string; monthly_usd_cents: number };
type Selection = { feature_code: string; camera_count: number };
type FeatureSummary = { drafts: Selection[]; assignments: (Selection & { status?: string })[]; active_quote?: { monthly_usd_cents: number; monthly_uzs: number } | null };

/** AI imkoniyatlar — sotuv darvozasi.  Tasdiqlangach qurilma keyingi
 *  config revision'da faol funksiyalarni oladi. */
function FeaturesModal({ siteId, name, onClose, onDone }: { siteId: string; name: string; onClose: () => void; onDone: (message: string) => void }) {
  const id = encodeURIComponent(siteId);
  const [features, setFeatures] = useState<Feature[]>([]); const [templates, setTemplates] = useState<{ code: string; name: string; feature_codes: string[] }[]>([]);
  const [summary, setSummary] = useState<FeatureSummary | null>(null); const [selected, setSelected] = useState<Record<string, number>>({});
  const [quote, setQuote] = useState<{ text: string; tone: "ok" | "warn" | "err" }>({ text: "", tone: "ok" }); const [error, setError] = useState(""); const [busy, setBusy] = useState("");
  useEffect(() => {
    Promise.all([
      api<{ features: Feature[] }>("/api/v1/admin/features", "admin"),
      api<{ code: string; name: string; feature_codes: string[] }[]>("/api/v1/admin/business-templates", "admin").catch(() => []),
      api<FeatureSummary>(`/api/v1/admin/sites/${id}/features`, "admin"),
    ]).then(([catalog, list, current]) => {
      setFeatures(catalog.features || []); setTemplates(list || []); setSummary(current);
      const base = current.drafts.length ? current.drafts : current.assignments.filter(item => item.status === "active");
      setSelected(Object.fromEntries(base.map(item => [item.feature_code, item.camera_count])));
    }).catch(reason => setError(reason instanceof Error ? reason.message : t("panel.admin.plans.load_failed")));
  }, [id]);
  const selections = (): Selection[] => Object.entries(selected).map(([feature_code, camera_count]) => ({ feature_code, camera_count }));
  // Narx har belgilaganda darrov yangilanadi — tasdiqlashdan oldin
  // "qancha bo'ladi?" degan savol qolmaydi.
  useEffect(() => {
    if (!summary) return;
    const items = selections();
    if (!items.length) { setQuote({ text: t("panel.admin.features.nothing_selected"), tone: "warn" }); return; }
    const timer = window.setTimeout(() => {
      api<{ monthly_usd_cents: number; monthly_uzs: number }>(`/api/v1/admin/sites/${id}/features/quote`, "admin", { method: "POST", body: JSON.stringify({ selections: items }) })
        .then(q => setQuote({ text: t("panel.admin.features.quote", { next: (q.monthly_usd_cents / 100).toFixed(0), uzs: formatMoney(q.monthly_uzs, { short: false }), now: ((summary.active_quote?.monthly_usd_cents || 0) / 100).toFixed(0) }), tone: "ok" }))
        .catch(reason => setQuote({ text: reason instanceof Error ? reason.message : t("panel.admin.features.quote_failed"), tone: "err" }));
    }, 250);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, summary, id]);
  const toggle = (code: string, on: boolean) => setSelected(current => { const next = { ...current }; if (on) next[code] = next[code] || 1; else delete next[code]; return next; });
  const save = async () => { setBusy("draft"); try { await api(`/api/v1/admin/sites/${id}/features/draft`, "admin", { method: "PUT", body: JSON.stringify({ selections: selections() }) }); onDone(t("panel.admin.features.draft_saved")); } catch (reason) { setError(reason instanceof Error ? reason.message : t("panel.numbers.save_failed")); setBusy(""); } };
  const approve = async () => { setBusy("approve"); try { await api(`/api/v1/admin/sites/${id}/features/draft`, "admin", { method: "PUT", body: JSON.stringify({ selections: selections() }) }); const result = await api<{ active_quote: { monthly_usd_cents: number } }>(`/api/v1/admin/sites/${id}/features/approve`, "admin", { method: "POST" }); onDone(t("panel.admin.features.approved", { amount: (result.active_quote.monthly_usd_cents / 100).toFixed(0) })); } catch (reason) { setError(reason instanceof Error ? reason.message : t("panel.admin.features.approve_failed")); setBusy(""); } };
  return <Modal title={t("panel.admin.features.title", { name })} wide onClose={onClose} footer={<><button className="btn" disabled={!!busy || !Object.keys(selected).length} onClick={() => void save()}>{t("panel.admin.features.save_draft")}</button><button className="btn btn-primary" disabled={!!busy || !Object.keys(selected).length} onClick={() => void approve()}>{t(busy === "approve" ? "panel.admin.features.approving" : "panel.admin.features.approve")}</button></>}>
    {error ? <div className="form-error">{error}</div> : null}
    {!summary ? <Skeleton height={160} /> : <>
      <p className="modal-text">{t("panel.admin.features.formula")}</p>
      {templates.length ? <label className="field-label">{t("panel.admin.features.template")}<select className="select" defaultValue="" onChange={event => { const template = templates.find(item => item.code === event.target.value); if (template) setSelected(Object.fromEntries(template.feature_codes.map(code => [code, selected[code] || 1]))); }}><option value="">{t("panel.admin.features.template_manual")}</option>{templates.map(template => <option key={template.code} value={template.code}>{template.name}</option>)}</select></label> : null}
      {features.length ? features.map(feature => <label key={feature.code} className="choice">
        <input type="checkbox" checked={feature.code in selected} onChange={event => toggle(feature.code, event.target.checked)} />
        <span><b>{feature.name}</b><small>{t(feature.queue_kind === "realtime" ? "panel.admin.features.realtime" : "panel.admin.features.batch")} · {t("panel.admin.features.per_camera", { amount: (feature.monthly_usd_cents / 100).toFixed(0) })}</small></span>
        <input className="input input-narrow" type="number" min={1} max={8} aria-label={t("panel.admin.features.camera_count_aria", { name: feature.name })} value={selected[feature.code] || 1} disabled={!(feature.code in selected)} onChange={event => setSelected(current => ({ ...current, [feature.code]: Math.max(1, Math.min(8, Number(event.target.value) || 1)) }))} />
      </label>) : <p className="metric-note">{t("panel.admin.features.empty")}</p>}
      <div className={`note ${quote.tone}`}>{quote.text || t("panel.admin.features.current", { amount: ((summary.active_quote?.monthly_usd_cents || 0) / 100).toFixed(0) })}</div>
    </>}
  </Modal>;
}

type InvoiceOut = { id: string; site_name?: string; months: number; amount_uzs: number; state: string; plan?: string; payme_url?: string; click_url?: string };

function InvoiceModal({ siteId, name, perMonth, platform, onClose, onDone }: { siteId: string; name: string; perMonth: number; platform: Platform; onClose: () => void; onDone: () => void }) {
  const [months, setMonths] = useState(1); const [invoice, setInvoice] = useState<InvoiceOut | null>(null); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const create = async () => { setBusy(true); setError(""); try { const result = await api<InvoiceOut>(`/api/v1/admin/sites/${encodeURIComponent(siteId)}/invoices`, "admin", { method: "POST", body: JSON.stringify({ months }) }); setInvoice(result); onDone(); } catch (reason) { setError(reason instanceof Error ? reason.message : t("panel.admin.invoice.create_failed")); } finally { setBusy(false); } };
  if (invoice) {
    const link = `${(platform.apex || window.location.origin).replace(/\/$/, "")}/pay/${invoice.id}`;
    return <Modal title={t("panel.admin.payments.invoice_title", { name })} onClose={onClose}>
      <div className="simple-list"><div className="simple-row"><span>{t("panel.billing.col_amount")}</span><b>{formatMoney(invoice.amount_uzs, { short: false })}</b></div><div className="simple-row"><span>{t("panel.billing.col_term")}</span><b>{t("panel.admin.invoice.term_value", { months: t("panel.shell.months_count", { count: invoice.months }), plan: PLAN_KEY[invoice.plan || ""] ? t(PLAN_KEY[invoice.plan || ""]) : invoice.plan || "" })}</b></div><div className="simple-row"><span>{t("panel.billing.col_state")}</span><Pill state={invoice.state === "paid" ? "active" : "pending"}>{t(invoice.state === "paid" ? "panel.billing.state_paid" : "panel.billing.state_pending")}</Pill></div></div>
      <p className="modal-text">{t("panel.admin.payments.link_text")}</p>
      <CopyField value={link} />
      <div className="page-actions wrap">{invoice.payme_url ? <a className="btn" href={invoice.payme_url} target="_blank" rel="noopener noreferrer">Payme</a> : null}{invoice.click_url ? <a className="btn" href={invoice.click_url} target="_blank" rel="noopener noreferrer">Click</a> : null}</div>
      <p className="metric-note">{t("panel.admin.invoice.auto_note")}</p>
    </Modal>;
  }
  return <Modal title={t("panel.admin.invoice.title")} onClose={onClose} footer={<><button className="btn" onClick={onClose}>{t("panel.common.cancel")}</button><button className="btn btn-primary" disabled={busy} onClick={() => void create()}>{t("panel.admin.invoice.submit")}</button></>}>
    <p className="modal-text">{t("panel.admin.invoice.text", { name })}</p>
    <MonthPicker value={months} onChange={setMonths} />
    {perMonth ? <p className="metric-note">{t("panel.admin.invoice.estimate", { amount: formatMoney(perMonth * months, { short: false }) })}</p> : null}
    {error ? <div className="form-error">{error}</div> : null}
  </Modal>;
}

function ExtendModal({ siteId, name, until, onClose, onDone }: { siteId: string; name: string; until?: string; onClose: () => void; onDone: (message: string) => void }) {
  const [months, setMonths] = useState(1); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const preview = useMemo(() => { const base = until ? new Date(until) : new Date(); const next = new Date(base.getTime()); next.setMonth(next.getMonth() + months); return next.toISOString().slice(0, 10); }, [until, months]);
  const submit = async () => { setBusy(true); try { const result = await api<{ subscription_until?: string; until?: string }>(`/api/v1/admin/sites/${encodeURIComponent(siteId)}/extend`, "admin", { method: "POST", body: JSON.stringify({ months }) }); onDone(t("panel.admin.extend.done", { date: formatDateShort(result.subscription_until || result.until) })); } catch (reason) { setError(reason instanceof Error ? reason.message : t("panel.admin.extend.failed")); setBusy(false); } };
  return <Modal title={t("panel.admin.customer.extend")} onClose={onClose} footer={<><button className="btn" onClick={onClose}>{t("panel.common.cancel")}</button><button className="btn btn-primary" disabled={busy} onClick={() => void submit()}>{t("panel.admin.extend.submit")}</button></>}>
    <p className="modal-text">{t("panel.admin.extend.text", { name })}</p>
    <MonthPicker value={months} onChange={setMonths} max={36} />
    <p className="metric-note">{t("panel.admin.extend.preview", { date: preview })}</p>
    {error ? <div className="form-error">{error}</div> : null}
  </Modal>;
}

function PlanModal({ siteId, current, onClose, onDone }: { siteId: string; current: string; onClose: () => void; onDone: () => void }) {
  const [plan, setPlan] = useState(current || "biznes"); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const submit = async () => { setBusy(true); try { await api(`/api/v1/admin/sites/${encodeURIComponent(siteId)}/plan`, "admin", { method: "POST", body: JSON.stringify({ plan }) }); onDone(); } catch (reason) { setError(reason instanceof Error ? reason.message : t("panel.admin.plan_modal.failed")); setBusy(false); } };
  return <Modal title={t("panel.admin.customer.change_plan")} onClose={onClose} footer={<><button className="btn" onClick={onClose}>{t("panel.common.cancel")}</button><button className="btn btn-primary" disabled={busy || plan === current} onClick={() => void submit()}>{t("panel.admin.plan_modal.submit")}</button></>}>
    <p className="modal-text">{t("panel.admin.plan_modal.text")}</p>
    <label className="field-label">{t("panel.admin.col_plan")}<select className="select" value={plan} onChange={event => setPlan(event.target.value)}>{Object.entries(PLAN_KEY).map(([code, key]) => <option key={code} value={code}>{t(key)}</option>)}</select></label>
    {error ? <div className="form-error">{error}</div> : null}
  </Modal>;
}

// ── Yuz tanish (yopiq pilot) ────────────────────────────────────────────

type FaceEmployee = { id: string; name?: string; active?: boolean; enrollment_status?: string; consent_recorded_at?: string; photos: { id: string }[] };
type FaceEvent = { event_id: string; person_id?: string | null; person_name?: string; occurred_at?: string };

function AuthedImage({ path, className }: { path: string; className?: string }) {
  const [url, setUrl] = useState("");
  useEffect(() => { let active = true; let created = ""; mediaObjectUrl(path, "admin").then(next => { if (active) { created = next; setUrl(next); } else URL.revokeObjectURL(next); }).catch(() => {}); return () => { active = false; if (created) URL.revokeObjectURL(created); }; }, [path]);
  return url ? <img src={url} alt="" className={className} /> : <span className={`${className || ""} face-empty`} />;
}

/** Yuz tanish faqat OCHILGANDA yuklanadi — har mijoz sahifasida ortiqcha
 *  so'rov va rasm tortilmasin. */
function FacesCard({ siteId, toast, confirm }: { siteId: string; toast: (message: string, ok?: boolean) => void; confirm: (request: ConfirmRequest) => Promise<boolean> }) {
  const id = encodeURIComponent(siteId);
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<{ service: { ok: boolean; reason?: string }; threshold?: number; employees: FaceEmployee[] } | null>(null);
  const [events, setEvents] = useState<FaceEvent[]>([]); const [error, setError] = useState(""); const [adding, setAdding] = useState(false);
  const load = useCallback(() => {
    api<{ service: { ok: boolean; reason?: string }; threshold?: number; employees: FaceEmployee[] }>(`/api/v1/admin/sites/${id}/faces`, "admin").then(next => { setData(next); setError(""); }).catch(reason => setError(reason instanceof Error ? reason.message : t("panel.admin.faces.load_failed")));
    api<{ events: FaceEvent[] }>(`/api/v1/admin/sites/${id}/faces/events?limit=30`, "admin").then(next => setEvents(next.events || [])).catch(() => setEvents([]));
  }, [id]);
  useEffect(() => { if (open) load(); }, [open, load]);
  const upload = async (employee: FaceEmployee, file?: File) => {
    if (!file) return;
    try { const payload = file.type === "image/png" ? file : await toJpeg(file); await api(`/api/v1/admin/sites/${id}/faces/employees/${encodeURIComponent(employee.id)}/photos`, "admin", { method: "POST", headers: { "Content-Type": file.type === "image/png" ? "image/png" : "image/jpeg" }, body: payload }); toast(t("panel.admin.faces.photo_saved")); load(); }
    catch (reason) { toast(reason instanceof Error ? reason.message : t("panel.employees.photo_failed"), false); }
  };
  const remove = async (faceId: string) => {
    if (!(await confirm({ title: t("panel.admin.faces.delete_title"), text: t("panel.admin.faces.delete_text"), confirmLabel: t("panel.common.delete"), danger: true }))) return;
    try { await api(`/api/v1/admin/sites/${id}/faces/photos/${encodeURIComponent(faceId)}`, "admin", { method: "DELETE" }); toast(t("panel.admin.faces.deleted")); load(); } catch (reason) { toast(reason instanceof Error ? reason.message : t("panel.admin.faces.delete_failed"), false); }
  };
  return <details className="card quiet section-gap" open={open} onToggle={event => setOpen((event.currentTarget as HTMLDetailsElement).open)}>
    <summary><b>{t("panel.admin.faces.title")}</b></summary>
    <div className="card-body">
      {error ? <div className="form-error">{error}</div> : !data ? <Skeleton height={120} /> : <>
        {data.service.ok ? <div className="note ok"><b>{t("panel.admin.faces.service_ok")}</b>{t("panel.admin.faces.threshold", { value: String(data.threshold ?? "—") })}</div> : <div className="note warn"><b>{t("panel.admin.faces.service_down")}</b>{data.service.reason}</div>}
        <p className="metric-note">{t("panel.admin.faces.pilot_note_1")}<b>{t("panel.admin.faces.pilot_note_consent")}</b>{t("panel.admin.faces.pilot_note_2")}</p>
        {data.employees.length ? data.employees.map(employee => <div className={`face-card${employee.active === false ? " off" : ""}`} key={employee.id}>
          <div><b>{employee.name || t("panel.admin.faces.unnamed")}</b><small>{t(employee.active === false ? "panel.admin.faces.inactive" : employee.enrollment_status === "enrolled" ? "panel.admin.faces.enrolled" : "panel.admin.faces.awaiting_photo")} · {t("panel.admin.faces.consent_at", { date: formatDateShort(employee.consent_recorded_at) })}</small></div>
          <div className="face-photos">{employee.photos.length ? employee.photos.map(photo => <span className="face-photo" key={photo.id}><AuthedImage path={`/api/v1/admin/sites/${id}/faces/photos/${encodeURIComponent(photo.id)}/image`} className="face-thumb" /><button className="btn btn-icon btn-danger" aria-label={t("panel.admin.faces.delete_title")} onClick={() => void remove(photo.id)}><Icon name="close" size={14} /></button></span>) : <span className="metric-note">{t("panel.admin.faces.no_photo")}</span>}</div>
          <label className="btn upload-btn">{t("panel.admin.faces.upload")}<input type="file" accept="image/*" onChange={event => { void upload(employee, event.target.files?.[0]); event.currentTarget.value = ""; }} /></label>
        </div>) : <EmptyState icon="users" title={t("panel.admin.faces.empty_title")} detail={t("panel.admin.faces.empty_detail")} />}
        <button className="btn btn-primary" onClick={() => setAdding(true)}>{t("panel.employees.add")}</button>
        {events.length ? <><h3 className="face-events-title">{t("panel.admin.faces.recent")}</h3><div className="face-grid">{events.map(event => <figure key={event.event_id} className={`face-item${event.person_id ? "" : " face-unknown"}`}><AuthedImage path={`/api/v1/admin/sites/${id}/faces/events/${encodeURIComponent(event.event_id)}/image`} /><figcaption><b>{event.person_id ? event.person_name || "?" : t("panel.admin.faces.unknown_person")}</b><small>{String(event.occurred_at || "").slice(11, 16)} · {formatDateShort(event.occurred_at)}</small></figcaption></figure>)}</div></> : <p className="metric-note">{t("panel.admin.faces.no_frames")}</p>}
      </>}
    </div>
    {adding ? <EmployeeModal siteId={siteId} onClose={() => setAdding(false)} onDone={() => { setAdding(false); toast(t("panel.admin.faces.employee_added")); load(); }} /> : null}
  </details>;
}

function EmployeeModal({ siteId, onClose, onDone }: { siteId: string; onClose: () => void; onDone: () => void }) {
  const [name, setName] = useState(""); const [consent, setConsent] = useState(false); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (!name.trim()) { setError(t("panel.admin.employee.name_required")); return; }
    if (!consent) { setError(t("panel.admin.employee.consent_required")); return; }
    setBusy(true); setError("");
    // `consent_note` — audit yozuvi, ekran yorlig'i emas: u bazada qoladi
    // va keyin huquqiy savolga javob beradi.  Shuning uchun admin panel
    // qaysi tilda ochilgan bo'lsa ham AYNAN shu matn yoziladi — aks holda
    // bitta jurnalda uch xil tilda yozuv yig'ilardi.
    try { await api(`/api/v1/admin/sites/${encodeURIComponent(siteId)}/employees`, "admin", { method: "POST", body: JSON.stringify({ name: name.trim(), consent: true, consent_note: "Admin panel orqali qayd etildi" }) }); onDone(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : t("panel.admin.employee.add_failed")); setBusy(false); }
  };
  return <Modal title={t("panel.employees.add")} onClose={onClose} footer={<><button className="btn" onClick={onClose}>{t("panel.common.cancel")}</button><button className="btn btn-primary" disabled={busy} onClick={() => void submit()}>{t("panel.common.add")}</button></>}>
    <label className="field-label">{t("panel.admin.employee.name")}<input className="input" value={name} onChange={event => setName(event.target.value)} /></label>
    <label className="choice"><input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)} /><span><b>{t("panel.admin.employee.consent")}</b><small>{t("panel.admin.employee.consent_hint")}</small></span></label>
    {error ? <div className="form-error">{error}</div> : null}
  </Modal>;
}
