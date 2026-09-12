import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { Card, EmptyState, ErrorStrip, PageHeader, Pill, Skeleton, useConfirm, useToast } from "./components";
import { Icon } from "./icons";
import { t } from "./i18n";

/* Sozlamalar — tizim tayyorligi, Telegram ogohlantirishi, yangilanish
 * tarqatish, onlayn to'lov.  Eski admindagi `renderSettings`. */

type ReadinessItem = { key: string; label: string; ok: boolean; required: boolean; reasons?: string[] };
type Alerts = { enabled?: boolean; interval_sec?: number; last_run?: { ran_at?: string } | null };
type Providers = { payme?: boolean; click?: boolean; public_url?: string };

export function AdminSettings() {
  const [readiness, setReadiness] = useState<{ items?: ReadinessItem[] } | null>(null);
  const [alerts, setAlerts] = useState<Alerts | null>(null);
  const [providers, setProviders] = useState<Providers | null>(null);
  const [paused, setPaused] = useState<boolean | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [confirm, confirmDialog] = useConfirm();
  const [toast, toastNode] = useToast();

  const load = useCallback(() => {
    // Xatoda BO'SH ro'yxat, `null` emas: `null` — «hali yuklanmoqda»,
    // ya'ni skelet abadiy qolib ketardi (ega panelidagi naqsh,
    // `EventEvidence.tsx`).
    api<{ items?: ReadinessItem[] }>("/api/v1/admin/readiness", "admin").then(data => { setReadiness(data); setError(""); }).catch(reason => { setReadiness({ items: [] }); setError(reason instanceof Error ? reason.message : t("panel.admin.settings.readiness_failed")); });
    api<Alerts>("/api/v1/admin/alerts", "admin").then(setAlerts).catch(() => setAlerts({}));
    api<Providers>("/api/v1/admin/payments/providers", "admin").then(setProviders).catch(() => setProviders({}));
    api<{ paused: boolean }>("/api/v1/admin/updates-paused", "admin").then(data => setPaused(Boolean(data.paused))).catch(() => setPaused(null));
  }, []);
  useEffect(load, [load]);

  const testAlert = async () => {
    setBusy("alert");
    try { await api("/api/v1/admin/alerts/test", "admin", { method: "POST" }); toast(t("panel.admin.settings.test_sent")); }
    catch (reason) { toast(reason instanceof Error ? reason.message : t("panel.admin.settings.send_failed"), false); }
    finally { setBusy(""); }
  };

  // Buzuq reliz chiqib ketsa — bitta tugma bilan hammasini to'xtatish.
  // Har do'konni alohida sozlashga ulgurib bo'lmaydi: qurilmalar har
  // 15 daqiqada so'raydi.
  const toggleUpdates = async () => {
    const next = !paused;
    const ok = await confirm({
      title: t(next ? "panel.admin.settings.pause_title" : "panel.admin.settings.resume_title"),
      text: t(next ? "panel.admin.settings.pause_text" : "panel.admin.settings.resume_text"),
      confirmLabel: t(next ? "panel.admin.settings.pause_confirm" : "panel.admin.settings.resume_confirm"), danger: next,
    });
    if (!ok) return;
    setBusy("updates");
    try { const data = await api<{ paused: boolean }>("/api/v1/admin/updates-paused", "admin", { method: "PUT", body: JSON.stringify({ paused: next }) }); setPaused(Boolean(data.paused)); toast(t(next ? "panel.admin.settings.paused_toast" : "panel.admin.settings.resumed_toast")); }
    catch (reason) { toast(reason instanceof Error ? reason.message : t("panel.admin.settings.toggle_failed"), false); }
    finally { setBusy(""); }
  };

  const items = readiness?.items || [];
  const missing = items.filter(item => !item.ok);

  return <>
    <PageHeader title={t("panel.nav.settings")} subtitle={t("panel.admin.settings.subtitle")} />
    {error ? <ErrorStrip detail={error} onRetry={() => { setReadiness(null); load(); }} /> : null}

    <Card>
      <div className="card-head"><div><h2>{t("panel.admin.settings.readiness_title")}</h2><p>{readiness ? t("panel.admin.settings.readiness_count", { done: items.length - missing.length, total: items.length }) : t("panel.admin.settings.readiness_subtitle")}</p></div></div>
      {readiness ? <div className="health-list">{items.map(item => <div className="health-row" key={item.key}><div className="health-name"><span className={`status-dot status-${item.ok ? "online" : item.required ? "offline" : "stale"}`} /><div><b>{item.label}</b><small>{item.reasons?.join(" · ") || t(item.required ? "panel.admin.settings.required_check" : "panel.admin.settings.optional_check")}</small></div></div><Pill state={item.ok ? "active" : item.required ? "failed" : "pending"}>{t(item.ok ? "panel.admin.settings.ready" : item.required ? "panel.admin.settings.not_ready" : "panel.admin.settings.optional")}</Pill></div>)}</div> : <div className="card-body"><Skeleton height={190} /></div>}
    </Card>

    <div className="split-grid section-gap">
      <Card>
        <div className="card-head"><div><h2>{t("panel.admin.settings.alerts_title")}</h2><p>{t("panel.admin.settings.alerts_subtitle")}</p></div></div>
        <div className="card-body">
          {alerts === null ? <Skeleton height={60} /> : alerts.enabled
            ? <><div className="note ok"><b>{t("panel.admin.settings.on")}</b>{t("panel.admin.settings.alerts_interval", { minutes: Math.round(Number(alerts.interval_sec || 0) / 60) })}{alerts.last_run?.ran_at ? t("panel.admin.settings.alerts_last", { time: String(alerts.last_run.ran_at).slice(11, 16) }) : ""}</div><button className="btn" disabled={busy === "alert"} onClick={() => void testAlert()}>{t("panel.admin.settings.test_send")}</button></>
            : <div className="note warn"><b>{t("panel.admin.settings.off")}</b>{t("panel.admin.settings.alerts_off_detail")}</div>}
        </div>
      </Card>

      <Card className={paused ? "card-danger" : ""}>
        <div className="card-head"><div><h2>{t("panel.admin.settings.updates_title")}</h2><p>{t("panel.admin.settings.updates_subtitle")}</p></div></div>
        <div className="card-body">
          {paused === null ? <Skeleton height={60} /> : paused
            ? <div className="note err"><b>{t("panel.admin.settings.updates_paused")}</b>{t("panel.admin.settings.updates_paused_detail")}</div>
            : <div className="note ok"><b>{t("panel.admin.settings.on")}</b>{t("panel.admin.settings.updates_on_detail")}</div>}
          <p className="metric-note">{t("panel.admin.settings.updates_note")}</p>
          {paused === null ? null : <button className={`btn ${paused ? "btn-primary" : "btn-danger"}`} disabled={busy === "updates"} onClick={() => void toggleUpdates()}>{t(paused ? "panel.admin.settings.updates_resume" : "panel.admin.settings.updates_stop")}</button>}
        </div>
      </Card>
    </div>

    <Card className="section-gap">
      <div className="card-head"><div><h2>{t("panel.admin.settings.providers_title")}</h2><p>{t("panel.admin.settings.providers_subtitle")}</p></div></div>
      {providers === null ? <div className="card-body"><Skeleton height={80} /></div> : <div className="simple-list">
        <div className="simple-row"><span>Payme</span><Pill state={providers.payme ? "active" : "pending"}>{t(providers.payme ? "panel.admin.settings.connected" : "panel.admin.settings.not_connected")}</Pill></div>
        <div className="simple-row"><span>Click</span><Pill state={providers.click ? "active" : "pending"}>{t(providers.click ? "panel.admin.settings.connected" : "panel.admin.settings.not_connected")}</Pill></div>
        <div className="simple-row"><span>{t("panel.admin.settings.public_domain")}</span>{providers.public_url ? <b className="mono">{providers.public_url}</b> : <Pill state="pending">{t("panel.admin.settings.no_domain")}</Pill>}</div>
      </div>}
    </Card>
    {!items.length && readiness ? <EmptyState icon="settings" title={t("panel.admin.settings.empty_title")} detail={t("panel.admin.settings.empty_detail")} /> : null}
    {confirmDialog}
    {toastNode}
  </>;
}
