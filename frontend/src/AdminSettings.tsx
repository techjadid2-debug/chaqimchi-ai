import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { Card, EmptyState, ErrorStrip, PageHeader, Pill, Skeleton, useConfirm, useToast } from "./components";
import { Icon } from "./icons";

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
    api<{ items?: ReadinessItem[] }>("/api/v1/admin/readiness", "admin").then(data => { setReadiness(data); setError(""); }).catch(reason => { setReadiness({ items: [] }); setError(reason instanceof Error ? reason.message : "Readiness olinmadi"); });
    api<Alerts>("/api/v1/admin/alerts", "admin").then(setAlerts).catch(() => setAlerts({}));
    api<Providers>("/api/v1/admin/payments/providers", "admin").then(setProviders).catch(() => setProviders({}));
    api<{ paused: boolean }>("/api/v1/admin/updates-paused", "admin").then(data => setPaused(Boolean(data.paused))).catch(() => setPaused(null));
  }, []);
  useEffect(load, [load]);

  const testAlert = async () => {
    setBusy("alert");
    try { await api("/api/v1/admin/alerts/test", "admin", { method: "POST" }); toast("Sinov xabari yuborildi — Telegramni tekshiring"); }
    catch (reason) { toast(reason instanceof Error ? reason.message : "Yuborilmadi", false); }
    finally { setBusy(""); }
  };

  // Buzuq reliz chiqib ketsa — bitta tugma bilan hammasini to'xtatish.
  // Har do'konni alohida sozlashga ulgurib bo'lmaydi: qurilmalar har
  // 15 daqiqada so'raydi.
  const toggleUpdates = async () => {
    const next = !paused;
    const ok = await confirm({
      title: next ? "Yangilanishni to‘xtatish" : "Yangilanishni qayta yoqish",
      text: next ? "Hech bir do‘kon yangi versiyani olmaydi. Buzuq reliz tarqalayotganda shu kerak." : "Do‘konlar yangi versiyani 15 daqiqa ichida oladi.",
      confirmLabel: next ? "To‘xtatish" : "Yoqish", danger: next,
    });
    if (!ok) return;
    setBusy("updates");
    try { const data = await api<{ paused: boolean }>("/api/v1/admin/updates-paused", "admin", { method: "PUT", body: JSON.stringify({ paused: next }) }); setPaused(Boolean(data.paused)); toast(next ? "Yangilanish to‘xtatildi" : "Yangilanish yoqildi"); }
    catch (reason) { toast(reason instanceof Error ? reason.message : "O‘zgartirilmadi", false); }
    finally { setBusy(""); }
  };

  const items = readiness?.items || [];
  const missing = items.filter(item => !item.ok);

  return <>
    <PageHeader title="Sozlamalar" subtitle="Ishlab chiqarish integratsiyalari, ogohlantirish va yangilanish tarqatish." />
    {error ? <ErrorStrip detail={error} onRetry={() => { setReadiness(null); load(); }} /> : null}

    <Card>
      <div className="card-head"><div><h2>Tizim tayyorligi</h2><p>{readiness ? `${items.length - missing.length}/${items.length} tayyor` : "Yashirilmagan real muhit tekshiruvlari"}</p></div></div>
      {readiness ? <div className="health-list">{items.map(item => <div className="health-row" key={item.key}><div className="health-name"><span className={`status-dot status-${item.ok ? "online" : item.required ? "offline" : "stale"}`} /><div><b>{item.label}</b><small>{item.reasons?.join(" · ") || (item.required ? "Majburiy tekshiruv" : "Ixtiyoriy tekshiruv")}</small></div></div><Pill state={item.ok ? "active" : item.required ? "failed" : "pending"}>{item.ok ? "Tayyor" : item.required ? "Tayyor emas" : "Ixtiyoriy"}</Pill></div>)}</div> : <div className="card-body"><Skeleton height={190} /></div>}
    </Card>

    <div className="split-grid section-gap">
      <Card>
        <div className="card-head"><div><h2>Telegram ogohlantirishi</h2><p>Do‘kon ishlamay qolsa bizga xabar</p></div></div>
        <div className="card-body">
          {alerts === null ? <Skeleton height={60} /> : alerts.enabled
            ? <><div className="note ok"><b>Yoqilgan</b>Har {Math.round(Number(alerts.interval_sec || 0) / 60)} daqiqada tekshiriladi{alerts.last_run?.ran_at ? ` · oxirgi tekshiruv ${String(alerts.last_run.ran_at).slice(11, 16)} (UTC)` : ""}</div><button className="btn" disabled={busy === "alert"} onClick={() => void testAlert()}>Sinov xabarini yuborish</button></>
            : <div className="note warn"><b>O‘chiq</b>Do‘kon ishlamay qolsa sizga xabar kelmaydi. Serverda Telegram sozlamalarini yoqing.</div>}
        </div>
      </Card>

      <Card className={paused ? "card-danger" : ""}>
        <div className="card-head"><div><h2>Dasturni yangilash</h2><p>Windows relizlarini tarqatish</p></div></div>
        <div className="card-body">
          {paused === null ? <Skeleton height={60} /> : paused
            ? <div className="note err"><b>To‘xtatilgan</b>Hech bir do‘kon yangi versiyani olmayapti.</div>
            : <div className="note ok"><b>Yoqilgan</b>Yangi versiya nashr qilinsa do‘konlar 15 daqiqada oladi.</div>}
          <p className="metric-note">Buzuq versiya chiqib ketsa shu tugma hammasini bir zumda to‘xtatadi — har do‘konni alohida sozlash shart emas.</p>
          {paused === null ? null : <button className={`btn ${paused ? "btn-primary" : "btn-danger"}`} disabled={busy === "updates"} onClick={() => void toggleUpdates()}>{paused ? "Yangilanishni qayta yoqish" : "Barcha yangilanishni to‘xtatish"}</button>}
        </div>
      </Card>
    </div>

    <Card className="section-gap">
      <div className="card-head"><div><h2>Onlayn to‘lov</h2><p>Qaysi provayder sozlangan</p></div></div>
      {providers === null ? <div className="card-body"><Skeleton height={80} /></div> : <div className="simple-list">
        <div className="simple-row"><span>Payme</span><Pill state={providers.payme ? "active" : "pending"}>{providers.payme ? "Ulangan" : "Ulanmagan"}</Pill></div>
        <div className="simple-row"><span>Click</span><Pill state={providers.click ? "active" : "pending"}>{providers.click ? "Ulangan" : "Ulanmagan"}</Pill></div>
        <div className="simple-row"><span>Rasmiy domen</span>{providers.public_url ? <b className="mono">{providers.public_url}</b> : <Pill state="pending">Sozlanmagan — havola faqat ichki tarmoqda ochiladi</Pill>}</div>
      </div>}
    </Card>
    {!items.length && readiness ? <EmptyState icon="settings" title="Tekshiruv yo‘q" detail="Server readiness ro‘yxatini bermadi." /> : null}
    {confirmDialog}
    {toastNode}
  </>;
}
