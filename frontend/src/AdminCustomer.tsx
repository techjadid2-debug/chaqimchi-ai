import { useCallback, useEffect, useMemo, useState } from "react";
import { api, formatDateShort, formatMoney, mediaObjectUrl, relativeMinutes, toJpeg } from "./api";
import { Card, ConfirmRequest, CopyField, EmptyState, Modal, MonthPicker, PageHeader, Pill, Skeleton, useConfirm, useToast } from "./components";
import { GeometryEditor } from "./GeometryEditor";
import { Icon } from "./icons";

/* Mijoz tafsiloti — admin support vositalari.
 *
 * Eski `admin.html` ning `renderCustomerDetail` i (2 310 qatorli faylning
 * yuragi) shu yerga ko'chdi.  Har vosita jonli do'konda yeyilgan xatodan
 * paydo bo'lgan; sababi tugma yonidagi izohda.  Bu sahifa bo'lmasa
 * do'konni masofadan tuzatib bo'lmaydi — F4 ning birinchi sharti.
 *
 * Matn hozircha o'zbekcha: admin panelini faqat biz ochamiz, tarjima
 * eng oxirgi navbatda (rebrend rejasi). */

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

const CONN_LABEL: Record<string, string> = { online: "Aloqada", stale: "Aloqa eskirgan", not_paired: "Ulanmagan", offline: "Oflayn" };
const CONN_STATE: Record<string, string> = { online: "active", stale: "grace", not_paired: "pending", offline: "failed" };
const LICENSE_LABEL: Record<string, string> = { active: "Faol", grace: "Qo‘shimcha muddat", expired: "Muddati tugagan", suspended: "To‘xtatilgan", trial: "Sinov" };
const PROBE_LABEL: Record<string, string> = { online: "Ishlayapti", offline: "Javob bermayapti", pending: "Tekshirilmoqda" };
const CONFIG_LABEL: Record<string, string> = { applied: "Sozlama qo‘llangan", pending: "Sozlama kutilmoqda", error: "Sozlama xatosi", unknown: "Sozlama holati noma’lum" };
const PLAN_LABEL: Record<string, string> = { boshlangich: "Boshlang‘ich", biznes: "Biznes", lite: "Lite (eski)" };
const ROLE_LABEL: Record<string, string> = { entrance: "Kirish", checkout: "Kassa", sales: "Zal", storage: "Ombor" };
const CAMERA_SLOTS = ["camera-01", "camera-02", "camera-03", "camera-04"];

/** Heartbeat'dagi raqamlarni odam o'qiydigan qatorlarga aylantiradi.
 *  Bu raqamlar bazada yotardi va do'kondagi nosozlikni faqat SSH bilan
 *  ko'rish mumkin edi — «hodisa bor, klip yo'q» va «2 730 ta yozuv
 *  tashlangan» holatlari shu sabab uzoq sezilmadi. */
function healthLines(health?: DeviceHealth): { text: string; bad?: boolean }[] {
  if (!health) return [];
  const out: { text: string; bad?: boolean }[] = [];
  const n = (value: unknown) => Number(value) || 0;
  if (n(health.outbox_poisoned)) out.push({ text: `${n(health.outbox_poisoned)} ta hodisa tashlangan${(health.outbox_poisoned_reasons || []).length ? ` — ${health.outbox_poisoned_reasons!.join(", ")}` : ""}`, bad: true });
  if (n(health.outbox_pending)) out.push({ text: `${n(health.outbox_pending)} ta navbatda` });
  if (n(health.plan_filtered)) out.push({ text: `${n(health.plan_filtered)} ta hodisa tarif filtrida tashlangan` });
  const clips = health.clips || {};
  if (Object.keys(clips).length) out.push({ text: `klip: ${n(clips.written)} yozildi${n(clips.no_segments) ? `, ${n(clips.no_segments)} tasida buferda segment yo‘q` : ""}${n(clips.cut_failed) ? `, ${n(clips.cut_failed)} tasi kesilmadi` : ""}${n(clips.unavailable) ? `, ${n(clips.unavailable)} tasida yozuv manzili yo‘q` : ""}`, bad: n(clips.missing) > 0 && !n(clips.written) });
  if (n(health.chain_restarts)) out.push({ text: `zanjir ${n(health.chain_restarts)} marta qayta ishga tushgan` });
  const crops = health.face_crops || {};
  if (n(crops.too_small)) out.push({ text: `yuz kadri: ${n(crops.too_small)} tasi juda mayda (kamera uzoq yoki oqim past sifatli)`, bad: true });
  else if (n(crops.written)) out.push({ text: `yuz kadri: ${n(crops.written)} ta yaroqli` });
  if (n(crops.suppressed)) out.push({ text: `${n(crops.suppressed)} tasi soatlik chegara bilan to‘xtatilgan` });
  const demo = health.demography || {};
  if (demo.off_reason) out.push({ text: `mijoz portreti o‘chiq: ${demo.off_reason}`, bad: true });
  else if (n(demo.attempts)) out.push({ text: `mijoz portreti: ${n(demo.attempts)} urinishdan ${n(demo.found)} tasida yuz topildi` });
  const stale = health.stale_chains || {};
  if (n(stale.running) > 1 || n(stale.after_update) > 0) out.push({ text: `${n(stale.running) > 1 ? `${n(stale.running)} ta zanjir bir vaqtda ishlayapti` : `yangilanishdan keyin ${n(stale.after_update)} ta eski zanjir qoldi`} — «Eski jarayonlarni tozalash» tugmasini bosing`, bad: true });
  (health.cameras || []).forEach(camera => {
    const ok = camera.connected && !camera.offline;
    out.push({ text: `${camera.camera_id}: ${ok ? "ishlayapti" : "javob bermayapti"}${camera.codec ? ` · ${camera.codec}` : ""}${n(camera.reconnects) > 5 ? ` · ${n(camera.reconnects)} marta uzilgan` : ""}`, bad: !ok });
  });
  return out;
}

function Banner({ detail }: { detail: SiteDetail }) {
  if (detail.connection === "not_paired") return <div className="status-banner warn"><b>Do‘kon kompyuteri hali ulanmagan</b><span>«Yangi ulanish havolasi» tugmasidan foydalaning.</span></div>;
  if (detail.connection === "offline" || detail.connection === "stale") return <div className="status-banner err"><b>Qurilma {relativeMinutes(detail.minutes_since_seen)} jim</b><span>Do‘kondagi kompyuter va internetni tekshiring.</span></div>;
  if (detail.cameras_expected && !detail.cameras_ok) return <div className="status-banner warn"><b>{detail.cameras_expected} kameradan {detail.cameras_active || 0} tasi ishlayapti</b><span>Kamera ro‘yxatini tekshiring.</span></div>;
  return <div className="status-banner ok"><b>Hammasi joyida</b><span>Qurilma aloqada, kameralar ishlayapti.</span></div>;
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
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Mijoz ochilmadi"); }
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
    } catch (reason) { toast(reason instanceof Error ? reason.message : "Amal bajarilmadi", false); }
    finally { setBusy(""); }
  };

  const open = (kind: ModalKind, payload: unknown = null) => { setModalPayload(payload); setModal(kind); };
  const close = () => { setModal(null); setModalPayload(null); };

  if (error) return <><PageHeader title="Mijoz" subtitle={siteId} actions={<button className="btn" onClick={onBack}>← Mijozlar</button>} /><Card><EmptyState icon="bell" title="Mijoz ochilmadi" detail={error} /></Card></>;
  if (!detail) return <><PageHeader title="Mijoz" subtitle="Yuklanmoqda…" actions={<button className="btn" onClick={onBack}>← Mijozlar</button>} /><Card><div className="card-body"><Skeleton height={220} /></div></Card></>;

  const suspended = detail.status === "suspended";
  const portalLogin = accounts.find(account => account.role === "customer" && account.site_id === detail.id && account.status !== "disabled");
  const limits = detail.limits || {};
  const cameraOptions = inventory.map(camera => ({ camera_id: camera.camera_id, label: camera.label }));

  // ── Amallar ──────────────────────────────────────────────────────────
  const cleanChains = () => run("clean", async () => {
    const answer = await api<{ job?: { reused?: boolean } }>(`/api/v1/admin/sites/${id}/jobs/clean-chains`, "admin", { method: "POST" });
    return answer.job?.reused ? "Tozalash allaqachon boshlangan — natijani kuting" : "Tozalash yuborildi — natija bir necha soniyada ko‘rinadi";
  }, false);
  const benchmark = async () => {
    // O'lchov protsessorni to'liq yuklaydi va tahlil sekinlashadi —
    // shuning uchun tasdiq bilan.  Natija «Diagnostika» da ko'rinadi.
    if (!(await confirm({ title: "Sig‘imni o‘lchash", text: "O‘lchov bir necha daqiqa davom etadi va shu vaqtda tahlil sekinlashadi. Natija «Diagnostika» bo‘limida ko‘rinadi.", confirmLabel: "O‘lchash" }))) return;
    await run("benchmark", async () => {
      const answer = await api<{ job?: { reused?: boolean } }>(`/api/v1/admin/sites/${id}/jobs/benchmark`, "admin", { method: "POST" });
      return answer.job?.reused ? "O‘lchov allaqachon ketyapti — natijani kuting" : "O‘lchov boshlandi. Bir necha daqiqadan keyin «Diagnostika» tugmasini bosing.";
    }, false);
  };
  const setStatus = async (to: "active" | "suspended") => {
    const ok = to === "suspended"
      ? await confirm({ title: "Obunani to‘xtatish", text: `«${detail.name}» do‘konida tahlil darhol to‘xtaydi va mijoz paneliga kira olmaydi.`, confirmLabel: "To‘xtatish", danger: true, typed: detail.name })
      : await confirm({ title: "Qayta yoqish", text: `«${detail.name}» obunasi qayta yoqilsinmi?`, confirmLabel: "Yoqish" });
    if (!ok) return;
    await run("status", async () => { await api(`/api/v1/admin/sites/${id}/status`, "admin", { method: "POST", body: JSON.stringify({ status: to }) }); return to === "suspended" ? "Obuna to‘xtatildi" : "Obuna qayta yoqildi"; });
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
    <PageHeader title={detail.name} subtitle={`${detail.contact_phone || "telefon kiritilmagan"} · ${detail.address || "manzil kiritilmagan"}`} actions={<>
      <Pill state={detail.license_status === "active" ? "active" : "failed"}>{LICENSE_LABEL[detail.license_status || ""] || detail.license_status || "—"}</Pill>
      <Pill state={CONN_STATE[detail.connection || ""]}>{CONN_LABEL[detail.connection || ""] || "Oflayn"}</Pill>
      <button className="btn" onClick={onBack}>← Mijozlar</button>
    </>} />
    <Banner detail={detail} />

    {/* ── Qurilma va kamera ─────────────────────────────────────── */}
    <Card className="section-gap">
      <div className="card-head"><div><h2>Qurilma va kamera</h2><p>{inventory.length} ta kamera · {(detail.devices || []).length} ta qurilma</p></div></div>
      {inventory.length ? <div className="table-wrap"><table>
        <thead><tr><th>Kamera</th><th>Rol</th><th>Tekshiruv</th><th>Video sifati</th><th>Holat</th></tr></thead>
        <tbody>{inventory.map(camera => <tr key={camera.camera_id}>
          <td><div className="table-title">{camera.label || camera.camera_id}</div><div className="table-sub">{camera.camera_id}{camera.origin === "device" ? " · qurilmadan (manzilsiz)" : ""}</div></td>
          <td>{ROLE_LABEL[camera.role || ""] || "—"}</td>
          <td><Pill state={camera.probe_status === "online" ? "active" : camera.probe_status === "offline" ? "failed" : "pending"}>{PROBE_LABEL[camera.probe_status || ""] || "Tekshirilmagan"}</Pill>{camera.probe_error ? <div className="table-sub">{camera.probe_error}</div> : null}</td>
          <td>{[camera.codec, camera.width && camera.height ? `${camera.width}×${camera.height}` : "", camera.fps ? `${camera.fps} FPS` : ""].filter(Boolean).join(" · ") || "—"}</td>
          <td>{camera.enabled === false ? "O‘chirilgan" : "Yoqilgan"}</td>
        </tr>)}</tbody>
      </table></div> : <div className="card-body"><p className="metric-note">Kamera kiritilmagan. RTSP manzillarini kiritmaguningizcha video tahlil boshlanmaydi.</p></div>}

      <div className="card-body">
        {(detail.devices || []).length ? (detail.devices || []).map((device, index) => {
          const lines = healthLines(device.health);
          return <div className="device-row" key={device.id || device.device_id || index}>
            <div><b>Qurilma {index + 1}</b><small>{device.hardware_model || device.product_name || "Windows kompyuter"} · dastur {device.app_version || "noma’lum"} · {CONFIG_LABEL[device.config_status || ""] || CONFIG_LABEL.unknown}</small>
              {lines.length ? <ul className="health-lines">{lines.map((line, i) => <li key={i} className={line.bad ? "is-bad" : ""}>{line.text}</li>)}</ul> : null}</div>
            <Pill state={CONN_STATE[device.connection || ""]}>{CONN_LABEL[device.connection || ""] || device.connection || "—"}</Pill>
            <span className="table-sub">{relativeMinutes(device.minutes_since_seen)}</span>
          </div>;
        }) : <p className="metric-note">Do‘kon kompyuteri hali ulanmagan.</p>}

        {(detail.feature_problems || []).length ? <div className="note warn"><b>Mijoz hodisa olmayapti</b>{(detail.feature_problems || []).map((p, i) => <div key={i}>{p.name} — {p.problem}{p.measure ? <small> ({p.measure})</small> : null}</div>)}</div> : null}
        {(detail.geometry_problems || []).length ? <div className="note warn"><b>{(detail.geometry_problems || []).length} ta chizma hech qachon ishlamaydi</b>{(detail.geometry_problems || []).map((p, i) => <div key={i}>{p.camera_id} · {p.kind === "line" ? "chiziq" : "zona"} «{p.name}» — {p.problem}</div>)}</div> : null}
        {(detail.role_problems || []).length ? <div className="note warn"><b>Rol berilgan, chizma yo‘q</b>{(detail.role_problems || []).map((p, i) => <div key={i}>{p.camera_id} · {ROLE_LABEL[p.role || ""] || p.role || ""} — {p.problem}</div>)}</div> : null}
        {!problems.length && (detail.devices || []).length ? <p className="metric-note">Chizma, rol va funksiya tekshiruvlari toza.</p> : null}

        <div className="page-actions wrap">
          <button className="btn btn-primary" onClick={() => open("camera")}><Icon name="camera" />Kamera qo‘shish</button>
          <button className="btn" onClick={() => open("expected")}>Kamera soni</button>
          <button className="btn" disabled={busy === "pairing"} onClick={() => void newPairing()}>Yangi ulanish havolasi</button>
          <button className="btn" onClick={() => open("policy")}>Yangilanish siyosati</button>
          <button className="btn" disabled={!inventory.length} onClick={() => open("geometry")}><Icon name="shapes" />Chiziq va zona</button>
          <button className="btn" onClick={() => open("diagnostics")}>Diagnostika</button>
          {(detail.devices || []).length ? <>
            <button className="btn" disabled={busy === "clean"} onClick={() => void cleanChains()}>Eski jarayonlarni tozalash</button>
            <button className="btn" disabled={busy === "benchmark"} onClick={() => void benchmark()}>Sig‘imni o‘lchash</button>
          </> : null}
        </div>
      </div>
    </Card>

    {/* ── Kirish va a'zolar ─────────────────────────────────────── */}
    <Card className="section-gap">
      <div className="card-head"><div><h2>Kirish va a’zolar</h2><p>{onboarding ? `${onboarding.completed}/${onboarding.total} bosqich bajarilgan` : "Bosqichlar ma’lumoti kelmadi"}</p></div></div>
      <div className="card-body">
        {onboarding ? <div className="simple-list">
          {onboarding.steps.filter(step => !step.done).map(step => <div className="simple-row" key={step.key || step.label}><span>{step.label}</span><Pill state="pending">Kutilmoqda</Pill></div>)}
          {onboarding.steps.every(step => step.done) ? <div className="note ok"><b>Ulanish tugallangan</b>Hamma bosqich bajarilgan.</div> : null}
          {onboarding.steps.some(step => step.done) ? <details className="quiet"><summary>{onboarding.steps.filter(step => step.done).length} ta bajarilgan bosqich</summary>{onboarding.steps.filter(step => step.done).map(step => <div className="simple-row" key={step.key || step.label}><span>{step.label}</span><Pill state="active">Bajarildi</Pill></div>)}</details> : null}
        </div> : null}
        <div className="simple-row"><div><b>Panel logini</b><div className="table-sub">{portalLogin ? `${portalLogin.username} — mijoz shu login bilan kiradi` : "yaratilmagan — mijoz panelga kira olmaydi"}</div></div><Pill state={portalLogin ? "active" : "pending"}>{portalLogin ? "Bor" : "Yo‘q"}</Pill></div>
        <div className="page-actions wrap">
          {portalLogin
            ? <button className="btn" onClick={() => open("password", portalLogin)}>Parolni yangilash</button>
            : <button className="btn btn-primary" disabled={busy === "login"} onClick={() => void createLogin()}>Login va parol yaratish</button>}
          <button className="btn" onClick={() => open("owner")}>Telegram egasini qo‘shish</button>
          <button className="btn" onClick={() => open("link")}>Kirish havolasi yaratish</button>
        </div>
      </div>
    </Card>

    {/* ── Tarif va to'lov ───────────────────────────────────────── */}
    <Card className="section-gap">
      <div className="card-head"><div><h2>Tarif va to‘lov</h2><p>Tasdiqlangan hisob obunani avtomatik uzaytiradi</p></div></div>
      <div className="card-body">
        <div className="simple-list">
          <div className="simple-row"><span>Tarif</span><b>{PLAN_LABEL[detail.plan || ""] || detail.plan || "—"} — {formatMoney(limits.monthly_price_uzs, { short: false })}/oy{limits.monthly_price_usd ? ` ($${limits.monthly_price_usd})` : ""}</b></div>
          <div className="simple-row"><span>Obuna tugaydi</span><b>{formatDateShort(detail.subscription_until)}{detail.days_left != null ? ` (${detail.days_left} kun qoldi)` : ""}</b></div>
          <div className="simple-row"><span>Cheklovlar</span><b>{limits.max_cameras ?? "—"} kamera · {limits.retention_days ?? "—"} kun arxiv</b></div>
        </div>
        <div className="page-actions wrap">
          <button className="btn btn-primary" onClick={() => open("features")}>AI imkoniyatlar</button>
          <button className="btn" onClick={() => open("invoice")}>Hisob ochish</button>
          <button className="btn" onClick={() => open("extend")}>To‘lovsiz uzaytirish</button>
          <button className="btn" onClick={() => open("plan")}>Tarifni almashtirish</button>
        </div>
      </div>
    </Card>

    <FacesCard siteId={siteId} toast={toast} confirm={confirm} />

    <Card className="section-gap card-danger">
      <div className="card-head"><div><h2>Xavfli amallar</h2><p>Obunani to‘xtatsangiz do‘konda tahlil darhol to‘xtaydi.</p></div></div>
      <div className="card-body"><button className={`btn ${suspended ? "btn-primary" : "btn-danger"}`} disabled={busy === "status"} onClick={() => void setStatus(suspended ? "active" : "suspended")}>{suspended ? "Qayta yoqish" : "Obunani to‘xtatish"}</button></div>
    </Card>

    <details className="card quiet section-gap">
      <summary><b>Texnik ma’lumot</b></summary>
      <div className="card-body simple-list">
        <div className="simple-row"><span>Ichki raqam</span><CopyField value={detail.id} /></div>
        <div className="simple-row"><span>Ulanish kodi</span><b>{(detail.active_pairing_codes || []).length ? (detail.active_pairing_codes || []).map(code => <div key={code.code} className="mono">{code.code} <small>({String(code.expires_at).slice(0, 16)} gacha)</small></div>) : "Faol kod yo‘q"}</b></div>
        <div className="simple-row"><span>Oxirgi aloqa</span><b>{detail.last_seen || "hech qachon"} (UTC)</b></div>
        {detail.rate_limited && Object.keys(detail.rate_limited).length ? <div className="simple-row"><span>Chegara rad etgan so‘rovlar</span><b>{Object.entries(detail.rate_limited).map(([key, count]) => `${key}: ${count}`).join(" · ")}</b></div> : null}
      </div>
    </details>

    {/* ── Modallar ──────────────────────────────────────────────── */}
    {modal === "camera" ? <CameraModal siteId={siteId} taken={inventory} onClose={close} onDone={message => { close(); void run("camera", async () => message); }} /> : null}
    {modal === "expected" ? <ExpectedModal siteId={siteId} current={detail.cameras_expected || 0} onClose={close} onDone={() => { close(); void run("expected", async () => "Kamera soni saqlandi"); }} /> : null}
    {modal === "pairing" ? <PairingModal name={detail.name} result={modalPayload as { pairing_code: string; pairing_expires_at?: string }} platform={platform} onClose={close} /> : null}
    {modal === "policy" ? <PolicyModal siteId={siteId} onClose={close} onDone={message => { close(); toast(message); }} /> : null}
    {modal === "diagnostics" ? <DiagnosticsModal siteId={siteId} onClose={close} /> : null}
    {modal === "geometry" ? <Modal title="Chiziq va zona" wide onClose={close}><GeometryEditor kind="admin" siteId={siteId} cameras={cameraOptions} onSaved={() => { toast("Chizma saqlandi — qurilma 20 soniyada oladi"); void load(); }} /></Modal> : null}
    {modal === "login" ? <LoginModal name={detail.name} phone={detail.contact_phone} login={modalPayload as { username: string; password: string }} platform={platform} onClose={close} /> : null}
    {modal === "password" ? <PasswordModal account={modalPayload as Account} onClose={close} onDone={() => { close(); toast("Parol yangilandi"); }} /> : null}
    {modal === "owner" ? <TelegramModal title="Telegram egasini qo‘shish" hint="Ega hisobotlarni va ogohlantirishlarni Telegramda oladi." submitLabel="Qo‘shish" onClose={close} onSubmit={async telegramId => { await api(`/api/v1/admin/sites/${id}/members`, "admin", { method: "POST", body: JSON.stringify({ telegram_id: telegramId, role: "owner" }) }); close(); toast("Telegram egasi qo‘shildi"); }} /> : null}
    {modal === "link" ? <TelegramModal title="Kirish havolasi yaratish" hint="Mijoz kod termasdan o‘z paneliga kiradi. Yangi havola eskisini bekor qiladi." submitLabel="Yaratish" onClose={close} onSubmit={async telegramId => { const link = await api<{ url: string; expires_days: number }>(`/api/v1/admin/sites/${id}/members/${encodeURIComponent(telegramId)}/login-link`, "admin", { method: "POST" }); open("pairing", { link }); }} /> : null}
    {modal === "pairing" && (modalPayload as { link?: { url: string; expires_days: number } })?.link ? null : null}
    {modal === "features" ? <FeaturesModal siteId={siteId} name={detail.name} onClose={close} onDone={message => { close(); void run("features", async () => message); }} /> : null}
    {modal === "invoice" ? <InvoiceModal siteId={siteId} name={detail.name} perMonth={limits.monthly_price_uzs || 0} platform={platform} onClose={close} onDone={() => void onChanged()} /> : null}
    {modal === "extend" ? <ExtendModal siteId={siteId} name={detail.name} until={detail.subscription_until} onClose={close} onDone={message => { close(); void run("extend", async () => message); }} /> : null}
    {modal === "plan" ? <PlanModal siteId={siteId} current={detail.plan || ""} onClose={close} onDone={() => { close(); void run("plan", async () => "Tarif almashtirildi — qurilma 20 soniyada yangi sozlamani oladi"); }} /> : null}
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
    if (!label.trim()) { setError("Kamera nomini kiriting"); return; }
    if (!/^rtsps?:\/\//.test(rtsp.trim())) { setError("Manzil rtsp:// yoki rtsps:// bilan boshlanishi kerak"); return; }
    setBusy(true); setError("");
    try {
      await api(`/api/v1/admin/sites/${encodeURIComponent(siteId)}/camera-inventory/${encodeURIComponent(slot)}`, "admin", { method: "PUT", body: JSON.stringify({ label: label.trim(), rtsp_url: rtsp.trim(), enabled: true, role }) });
      onDone("Kamera saqlandi. Dastur 15 daqiqa ichida tekshiradi.");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Saqlanmadi"); setBusy(false); }
  };
  return <Modal title="Kamera qo‘shish" onClose={onClose} footer={<><button className="btn" onClick={onClose}>Bekor qilish</button><button className="btn btn-primary" disabled={busy} onClick={() => void submit()}>{busy ? "Saqlanmoqda…" : "Saqlash"}</button></>}>
    <label className="field-label">Kamera o‘rni<select className="select" value={slot} onChange={event => setSlot(event.target.value)}>{CAMERA_SLOTS.map((item, index) => <option key={item} value={item}>{index + 1}-kamera{used.has(item) ? ` — band: ${used.get(item)} (almashtiriladi)` : " — bo‘sh"}</option>)}</select></label>
    <label className="field-label">Kamera nomi<input className="input" list="adminCameraNames" placeholder="Kirish" value={label} onChange={event => setLabel(event.target.value)} /><datalist id="adminCameraNames"><option value="Kirish" /><option value="Kassa" /><option value="Zal" /><option value="Ombor" /><option value="Orqa eshik" /></datalist></label>
    <label className="field-label">Rol<select className="select" value={role} onChange={event => setRole(event.target.value)}><option value="">Rol tanlanmagan</option>{Object.entries(ROLE_LABEL).map(([code, name]) => <option key={code} value={code}>{name}</option>)}</select></label>
    <label className="field-label">NVR video manzili (RTSP)<input className="input" placeholder="rtsp://login:parol@192.168.1.10:554/stream/sub" value={rtsp} onChange={event => setRtsp(event.target.value)} /><small>Substream (H.264, 720p) manzilini kiriting — kompyuter kam quvvat sarflaydi. Login va parol shifrlangan holda saqlanadi.</small></label>
    {error ? <div className="form-error" role="alert">{error}</div> : null}
  </Modal>;
}

function ExpectedModal({ siteId, current, onClose, onDone }: { siteId: string; current: number; onClose: () => void; onDone: () => void }) {
  const [count, setCount] = useState(current); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const submit = async () => { setBusy(true); try { await api(`/api/v1/admin/sites/${encodeURIComponent(siteId)}/cameras`, "admin", { method: "POST", body: JSON.stringify({ expected: count }) }); onDone(); } catch (reason) { setError(reason instanceof Error ? reason.message : "Saqlanmadi"); setBusy(false); } };
  return <Modal title="Kamera soni" onClose={onClose} footer={<><button className="btn" onClick={onClose}>Bekor qilish</button><button className="btn btn-primary" disabled={busy} onClick={() => void submit()}>Saqlash</button></>}>
    <p className="modal-text">Do‘konda nechta kamera ishlashi kerak. Shu songa qarab «kamera tushib qoldi» ogohlantirishi beriladi.</p>
    <label className="field-label">Kutilayotgan kamera soni<select className="select" value={count} onChange={event => setCount(Number(event.target.value))}>{[0, 1, 2, 3, 4].map(n => <option key={n} value={n}>{n} ta</option>)}</select></label>
    {error ? <div className="form-error">{error}</div> : null}
  </Modal>;
}

function PairingModal({ name, result, platform, onClose }: { name: string; result: { pairing_code?: string; pairing_expires_at?: string; link?: { url: string; expires_days: number } }; platform: Platform; onClose: () => void }) {
  // Kirish havolasi ham shu oynada: ikkalasi «mijozga yuboriladigan havola».
  if (result.link) {
    return <Modal title="Kirish havolasi tayyor" onClose={onClose}>
      <CopyField value={result.link.url} />
      <p className="metric-note">{result.link.expires_days} kun amal qiladi. Mijozga Telegram orqali yuboring.</p>
      <a className="btn" href={`https://t.me/share/url?url=${encodeURIComponent(result.link.url)}`} target="_blank" rel="noopener noreferrer"><Icon name="telegram" />Telegramga yuborish</a>
    </Modal>;
  }
  // Windows uchun asosiy yo'l: kod havolaga qo'shiladi, mijoz 6 ta
  // belgini qo'lda ko'chirmaydi.
  const base = (platform.dl || window.location.origin).replace(/\/$/, "");
  const link = `${base}/api/v1/public/download-installer?code=${encodeURIComponent(result.pairing_code || "")}`;
  return <Modal title={`${name} — o‘rnatish havolasi`} onClose={onClose}>
    <p className="modal-text"><b>Mijozga shu havolani yuboring</b> (Telegram yoki SMS):</p>
    <CopyField value={link} />
    <p className="metric-note">Havolani bosadi, dastur yuklanadi va o‘rnatilgach o‘zi ulanadi — hech qanday kod yozmaydi.</p>
    <details className="quiet"><summary>Kodni qo‘lda kiritish kerak bo‘lsa</summary><div className="code-box">{result.pairing_code}</div><p className="metric-note">Bir martalik, {String(result.pairing_expires_at || "").slice(0, 16)} (UTC) gacha amal qiladi.</p></details>
  </Modal>;
}

function PolicyModal({ siteId, onClose, onDone }: { siteId: string; onClose: () => void; onDone: (message: string) => void }) {
  const [info, setInfo] = useState<{ releases: { version: string; signed?: boolean; size_mb?: number }[]; latest?: string | null } | null>(null);
  const [choice, setChoice] = useState<"auto" | "hold" | "pin">("auto"); const [version, setVersion] = useState(""); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  useEffect(() => { api<{ releases: { version: string; signed?: boolean }[]; latest?: string | null }>("/api/v1/admin/windows-releases", "admin").then(data => { setInfo(data); setVersion(data.latest || data.releases[0]?.version || ""); }).catch(reason => setError(reason instanceof Error ? reason.message : "Relizlar olinmadi")); }, []);
  const submit = async () => {
    setBusy(true); setError("");
    try {
      await api(`/api/v1/admin/sites/${encodeURIComponent(siteId)}/update-policy`, "admin", { method: "PUT", body: JSON.stringify(choice === "pin" ? { channel: "pin", version } : { channel: choice }) });
      // Va'da o'rnatuvchidagi jadval bilan bir xil (15 daqiqa) —
      // `tests/test_windows_installer.py` buni qulflaydi.
      onDone(choice === "hold" ? "Yangilanish to‘xtatildi" : "Saqlandi. Do‘kon kompyuteri 15 daqiqa ichida qo‘llaydi.");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Saqlanmadi"); setBusy(false); }
  };
  return <Modal title="Yangilanish siyosati" onClose={onClose} footer={<><button className="btn" onClick={onClose}>Bekor qilish</button><button className="btn btn-primary" disabled={busy || !info?.releases.length} onClick={() => void submit()}>Saqlash</button></>}>
    {info ? <>
      <p className="modal-text">Eng yangi dastur: <b>{info.latest || "—"}</b>{info.releases.length ? "" : " · nashr qilingan reliz yo‘q"}</p>
      {([["auto", "Avtomatik yangilansin", "Eng yangi versiya o‘zi o‘rnatiladi"], ["hold", "Shu versiyada qolsin", "Yangi versiya chiqsa ham o‘rnatilmaydi"], ["pin", "Aniq versiya", "Faqat siz tanlagan versiyada ishlaydi"]] as const).map(([code, title, hint]) => <label key={code} className="choice"><input type="radio" name="policy" checked={choice === code} onChange={() => setChoice(code)} /><span><b>{title}</b><small>{hint}</small></span></label>)}
      {choice === "pin" ? <label className="field-label">Versiya<select className="select" value={version} onChange={event => setVersion(event.target.value)}>{info.releases.map(release => <option key={release.version} value={release.version}>{release.version}{release.signed ? "" : " (imzolanmagan)"}</option>)}</select></label> : null}
    </> : <Skeleton height={120} />}
    {error ? <div className="form-error">{error}</div> : null}
  </Modal>;
}

function BenchmarkBlock({ job }: { job: { status?: string; error?: string; updated_at?: string; result?: Record<string, unknown> } | null }) {
  if (!job) return null;
  if (job.status !== "done") return <div className="note warn"><b>Sig‘im o‘lchovi: {job.status}</b>{job.error || "hali tugamagan"}</div>;
  const result = (job.result || {}) as { device?: string; frame_size?: number[]; native_size?: number[]; detector?: { throughput_fps?: number; p95_ms?: number }; verdict?: { supported_cameras?: number; cameras?: number; ok?: boolean } };
  const native = (result.native_size || []).filter(Boolean).join("×");
  return <div className="note ok"><b>Sig‘im o‘lchovi — {job.updated_at || ""}</b>
    <div>Qurilma: {result.device || "—"} · tahlil {(result.frame_size || []).join("×") || "—"}{native ? <> · <b>kamera beryapti {native}</b></> : null}</div>
    <div>Detektor: {Number(result.detector?.throughput_fps || 0).toFixed(1)} inferens/s, p95 {Number(result.detector?.p95_ms || 0).toFixed(0)} ms</div>
    <div>Xulosa: <b>{Number(result.verdict?.supported_cameras || 0)} kamera ko‘taradi</b> (so‘ralgan {Number(result.verdict?.cameras || 0)}){result.verdict?.ok === false ? " — zaxira yetarli emas" : ""}</div>
  </div>;
}

function DiagnosticsModal({ siteId, onClose }: { siteId: string; onClose: () => void }) {
  const [data, setData] = useState<{ diagnostics: { device_id?: string; created_at?: string; payload?: unknown } | null; benchmark: { status?: string; error?: string; updated_at?: string; result?: Record<string, unknown> } | null } | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { api<{ diagnostics: { device_id?: string; created_at?: string; payload?: unknown } | null; benchmark: { status?: string } | null }>(`/api/v1/admin/sites/${encodeURIComponent(siteId)}/diagnostics`, "admin").then(setData).catch(reason => setError(reason instanceof Error ? reason.message : "Diagnostika olinmadi")); }, [siteId]);
  return <Modal title="Diagnostika paketi" wide onClose={onClose}>
    {error ? <div className="form-error">{error}</div> : !data ? <Skeleton height={160} /> : <>
      <BenchmarkBlock job={data.benchmark} />
      {data.diagnostics ? <>
        <div className="simple-list"><div className="simple-row"><span>Qurilma</span><b>{data.diagnostics.device_id || "—"}</b></div><div className="simple-row"><span>Kelgan vaqti</span><b>{data.diagnostics.created_at || "—"}</b></div></div>
        <pre className="diag-json">{JSON.stringify(data.diagnostics.payload || {}, null, 2)}</pre>
      </> : <p className="metric-note">Bu do‘kondan hali diagnostika paketi kelmagan. U 0.6.22 dan boshlab sutkada bir marta o‘zi keladi — qurilma yangilanganini tekshiring.</p>}
    </>}
  </Modal>;
}

function LoginModal({ name, phone, login, platform, onClose }: { name: string; phone?: string; login: { username: string; password: string }; platform: Platform; onClose: () => void }) {
  const url = `${(platform.app || window.location.origin).replace(/\/$/, "")}/owner`;
  const message = `ENES Monitoring paneli: ${url}\nLogin: ${login.username}\nParol: ${login.password}\n\nKirgach "Telegramimni ulash" tugmasini bosing — hisobotlar Telegramga keladi.`;
  return <Modal title={`${name} — kirish ma’lumotlari`} onClose={onClose}>
    <div className="note warn"><b>Parol shu oynadan keyin ko‘rinmaydi.</b> Hozir mijozga yuboring.</div>
    <div className="simple-list"><div className="simple-row"><span>Login</span><b className="mono">{login.username}</b></div><div className="simple-row"><span>Parol</span><b className="mono">{login.password}</b></div><div className="simple-row"><span>Manzil</span><b className="mono">{url}</b></div></div>
    <CopyField value={message} label="Tayyor xabarni nusxalash" />
    {phone ? <p className="metric-note">Mijoz raqami: <a href={`tel:${phone}`}>{phone}</a></p> : null}
    <p className="metric-note">Parol telefonda aytib berish uchun tanlangan — ikkita so‘z va to‘rt raqam.</p>
  </Modal>;
}

export function PasswordModal({ account, onClose, onDone }: { account: Account; onClose: () => void; onDone: () => void }) {
  const [password, setPassword] = useState(""); const [show, setShow] = useState(false); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (password.length < 10) { setError("Parol kamida 10 belgi bo‘lishi kerak"); return; }
    setBusy(true); setError("");
    try { await api(`/api/v1/admin/accounts/${encodeURIComponent(account.id)}/password`, "admin", { method: "POST", body: JSON.stringify({ new_password: password }) }); onDone(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Saqlanmadi"); setBusy(false); }
  };
  return <Modal title="Yangi vaqtinchalik parol" onClose={onClose} footer={<><button className="btn" onClick={onClose}>Bekor qilish</button><button className="btn btn-primary" disabled={busy} onClick={() => void submit()}>Saqlash</button></>}>
    <p className="modal-text">{account.full_name || account.username} uchun. Saqlangach eski sessiyalar bekor qilinadi.</p>
    <label className="field-label">Parol (kamida 10 belgi)<input className="input" type={show ? "text" : "password"} autoComplete="new-password" value={password} onChange={event => setPassword(event.target.value)} /></label>
    <div className="page-actions wrap">
      <button className="btn" type="button" onClick={() => { setPassword(generatePassword(account.role === "customer")); setShow(true); }}>Tasodifiy parol yaratish</button>
      <button className="btn" type="button" onClick={() => setShow(value => !value)}>{show ? "Yashirish" : "Ko‘rsatish"}</button>
      {password ? <CopyField value={password} /> : null}
    </div>
    {error ? <div className="form-error">{error}</div> : null}
  </Modal>;
}

function TelegramModal({ title, hint, submitLabel, onClose, onSubmit }: { title: string; hint: string; submitLabel: string; onClose: () => void; onSubmit: (telegramId: string) => Promise<void> }) {
  const [value, setValue] = useState(""); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (!/^[-0-9]{3,32}$/.test(value.trim())) { setError("Telegram ID faqat raqamlardan iborat bo‘ladi"); return; }
    setBusy(true); setError("");
    try { await onSubmit(value.trim()); } catch (reason) { setError(reason instanceof Error ? reason.message : "Bajarilmadi"); setBusy(false); }
  };
  return <Modal title={title} onClose={onClose} footer={<><button className="btn" onClick={onClose}>Bekor qilish</button><button className="btn btn-primary" disabled={busy} onClick={() => void submit()}>{submitLabel}</button></>}>
    <p className="modal-text">{hint}</p>
    <label className="field-label">Mijozning Telegram ID raqami<input className="input" inputMode="numeric" placeholder="123456789" value={value} onChange={event => setValue(event.target.value)} /><small>Mijoz botga /start yozsa bot unga o‘z ID raqamini aytadi.</small></label>
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
    }).catch(reason => setError(reason instanceof Error ? reason.message : "Katalog olinmadi"));
  }, [id]);
  const selections = (): Selection[] => Object.entries(selected).map(([feature_code, camera_count]) => ({ feature_code, camera_count }));
  // Narx har belgilaganda darrov yangilanadi — tasdiqlashdan oldin
  // "qancha bo'ladi?" degan savol qolmaydi.
  useEffect(() => {
    if (!summary) return;
    const items = selections();
    if (!items.length) { setQuote({ text: "Hech narsa tanlanmagan.", tone: "warn" }); return; }
    const timer = window.setTimeout(() => {
      api<{ monthly_usd_cents: number; monthly_uzs: number }>(`/api/v1/admin/sites/${id}/features/quote`, "admin", { method: "POST", body: JSON.stringify({ selections: items }) })
        .then(q => setQuote({ text: `Yangi oylik: $${(q.monthly_usd_cents / 100).toFixed(0)} ≈ ${formatMoney(q.monthly_uzs, { short: false })} (hozir: $${((summary.active_quote?.monthly_usd_cents || 0) / 100).toFixed(0)})`, tone: "ok" }))
        .catch(reason => setQuote({ text: reason instanceof Error ? reason.message : "Narx hisoblanmadi", tone: "err" }));
    }, 250);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, summary, id]);
  const toggle = (code: string, on: boolean) => setSelected(current => { const next = { ...current }; if (on) next[code] = next[code] || 1; else delete next[code]; return next; });
  const save = async () => { setBusy("draft"); try { await api(`/api/v1/admin/sites/${id}/features/draft`, "admin", { method: "PUT", body: JSON.stringify({ selections: selections() }) }); onDone("Qoralama saqlandi — tasdiqlashni kutmoqda"); } catch (reason) { setError(reason instanceof Error ? reason.message : "Saqlanmadi"); setBusy(""); } };
  const approve = async () => { setBusy("approve"); try { await api(`/api/v1/admin/sites/${id}/features/draft`, "admin", { method: "PUT", body: JSON.stringify({ selections: selections() }) }); const result = await api<{ active_quote: { monthly_usd_cents: number } }>(`/api/v1/admin/sites/${id}/features/approve`, "admin", { method: "POST" }); onDone(`Yoqildi. Yangi oylik: $${(result.active_quote.monthly_usd_cents / 100).toFixed(0)}`); } catch (reason) { setError(reason instanceof Error ? reason.message : "Tasdiqlanmadi"); setBusy(""); } };
  return <Modal title={`${name} — AI imkoniyatlar`} wide onClose={onClose} footer={<><button className="btn" disabled={!!busy || !Object.keys(selected).length} onClick={() => void save()}>Qoralama sifatida saqlash</button><button className="btn btn-primary" disabled={!!busy || !Object.keys(selected).length} onClick={() => void approve()}>{busy === "approve" ? "Yoqilmoqda…" : "Tasdiqlash va yoqish"}</button></>}>
    {error ? <div className="form-error">{error}</div> : null}
    {!summary ? <Skeleton height={160} /> : <>
      <p className="modal-text">Har do‘kon uchun $20 baza + tanlangan imkoniyat × kamera soni.</p>
      {templates.length ? <label className="field-label">Tayyor to‘plam<select className="select" defaultValue="" onChange={event => { const template = templates.find(item => item.code === event.target.value); if (template) setSelected(Object.fromEntries(template.feature_codes.map(code => [code, selected[code] || 1]))); }}><option value="">Qo‘lda tanlash</option>{templates.map(template => <option key={template.code} value={template.code}>{template.name}</option>)}</select></label> : null}
      {features.length ? features.map(feature => <label key={feature.code} className="choice">
        <input type="checkbox" checked={feature.code in selected} onChange={event => toggle(feature.code, event.target.checked)} />
        <span><b>{feature.name}</b><small>{feature.queue_kind === "realtime" ? "Tezkor xabar" : "Kunlik tahlil"} · ${(feature.monthly_usd_cents / 100).toFixed(0)} har kamera uchun</small></span>
        <input className="input input-narrow" type="number" min={1} max={8} aria-label={`${feature.name} uchun kamera soni`} value={selected[feature.code] || 1} disabled={!(feature.code in selected)} onChange={event => setSelected(current => ({ ...current, [feature.code]: Math.max(1, Math.min(8, Number(event.target.value) || 1)) }))} />
      </label>) : <p className="metric-note">Katalog bo‘sh.</p>}
      <div className={`note ${quote.tone}`}>{quote.text || `Hozirgi oylik: $${((summary.active_quote?.monthly_usd_cents || 0) / 100).toFixed(0)}`}</div>
    </>}
  </Modal>;
}

type InvoiceOut = { id: string; site_name?: string; months: number; amount_uzs: number; state: string; plan?: string; payme_url?: string; click_url?: string };

function InvoiceModal({ siteId, name, perMonth, platform, onClose, onDone }: { siteId: string; name: string; perMonth: number; platform: Platform; onClose: () => void; onDone: () => void }) {
  const [months, setMonths] = useState(1); const [invoice, setInvoice] = useState<InvoiceOut | null>(null); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const create = async () => { setBusy(true); setError(""); try { const result = await api<InvoiceOut>(`/api/v1/admin/sites/${encodeURIComponent(siteId)}/invoices`, "admin", { method: "POST", body: JSON.stringify({ months }) }); setInvoice(result); onDone(); } catch (reason) { setError(reason instanceof Error ? reason.message : "Hisob ochilmadi"); } finally { setBusy(false); } };
  if (invoice) {
    const link = `${(platform.apex || window.location.origin).replace(/\/$/, "")}/pay/${invoice.id}`;
    return <Modal title={`${name} — hisob-faktura`} onClose={onClose}>
      <div className="simple-list"><div className="simple-row"><span>Summa</span><b>{formatMoney(invoice.amount_uzs, { short: false })}</b></div><div className="simple-row"><span>Muddat</span><b>{invoice.months} oy · {PLAN_LABEL[invoice.plan || ""] || invoice.plan || ""}</b></div><div className="simple-row"><span>Holat</span><Pill state={invoice.state === "paid" ? "active" : "pending"}>{invoice.state === "paid" ? "To‘langan" : "Kutilmoqda"}</Pill></div></div>
      <p className="modal-text">Mijozga yuboriladigan havola:</p>
      <CopyField value={link} />
      <div className="page-actions wrap">{invoice.payme_url ? <a className="btn" href={invoice.payme_url} target="_blank" rel="noopener noreferrer">Payme</a> : null}{invoice.click_url ? <a className="btn" href={invoice.click_url} target="_blank" rel="noopener noreferrer">Click</a> : null}</div>
      <p className="metric-note">To‘lov tushgach obuna avtomatik uzayadi — qo‘lda tasdiqlash shart emas.</p>
    </Modal>;
  }
  return <Modal title="Hisob ochish" onClose={onClose} footer={<><button className="btn" onClick={onClose}>Bekor qilish</button><button className="btn btn-primary" disabled={busy} onClick={() => void create()}>Ochish</button></>}>
    <p className="modal-text">{name} uchun to‘lov hisobi.</p>
    <MonthPicker value={months} onChange={setMonths} />
    {perMonth ? <p className="metric-note">Taxminiy summa: {formatMoney(perMonth * months, { short: false })}</p> : null}
    {error ? <div className="form-error">{error}</div> : null}
  </Modal>;
}

function ExtendModal({ siteId, name, until, onClose, onDone }: { siteId: string; name: string; until?: string; onClose: () => void; onDone: (message: string) => void }) {
  const [months, setMonths] = useState(1); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const preview = useMemo(() => { const base = until ? new Date(until) : new Date(); const next = new Date(base.getTime()); next.setMonth(next.getMonth() + months); return next.toISOString().slice(0, 10); }, [until, months]);
  const submit = async () => { setBusy(true); try { const result = await api<{ subscription_until?: string; until?: string }>(`/api/v1/admin/sites/${encodeURIComponent(siteId)}/extend`, "admin", { method: "POST", body: JSON.stringify({ months }) }); onDone(`Obuna ${formatDateShort(result.subscription_until || result.until)} gacha uzaytirildi`); } catch (reason) { setError(reason instanceof Error ? reason.message : "Uzaytirilmadi"); setBusy(false); } };
  return <Modal title="To‘lovsiz uzaytirish" onClose={onClose} footer={<><button className="btn" onClick={onClose}>Bekor qilish</button><button className="btn btn-primary" disabled={busy} onClick={() => void submit()}>Uzaytirish</button></>}>
    <p className="modal-text">{name} obunasi hisob ochmasdan uzayadi.</p>
    <MonthPicker value={months} onChange={setMonths} max={36} />
    <p className="metric-note">Yangi tugash sanasi: {preview}</p>
    {error ? <div className="form-error">{error}</div> : null}
  </Modal>;
}

function PlanModal({ siteId, current, onClose, onDone }: { siteId: string; current: string; onClose: () => void; onDone: () => void }) {
  const [plan, setPlan] = useState(current || "biznes"); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const submit = async () => { setBusy(true); try { await api(`/api/v1/admin/sites/${encodeURIComponent(siteId)}/plan`, "admin", { method: "POST", body: JSON.stringify({ plan }) }); onDone(); } catch (reason) { setError(reason instanceof Error ? reason.message : "Almashtirilmadi"); setBusy(false); } };
  return <Modal title="Tarifni almashtirish" onClose={onClose} footer={<><button className="btn" onClick={onClose}>Bekor qilish</button><button className="btn btn-primary" disabled={busy || plan === current} onClick={() => void submit()}>Almashtirish</button></>}>
    <p className="modal-text">Tarif — pul va funksiya to‘plami. O‘zgarish mijozga sezilarli; audit jurnaliga yoziladi.</p>
    <label className="field-label">Tarif<select className="select" value={plan} onChange={event => setPlan(event.target.value)}>{Object.entries(PLAN_LABEL).map(([code, label]) => <option key={code} value={code}>{label}</option>)}</select></label>
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
    api<{ service: { ok: boolean; reason?: string }; threshold?: number; employees: FaceEmployee[] }>(`/api/v1/admin/sites/${id}/faces`, "admin").then(next => { setData(next); setError(""); }).catch(reason => setError(reason instanceof Error ? reason.message : "Ma’lumot kelmadi"));
    api<{ events: FaceEvent[] }>(`/api/v1/admin/sites/${id}/faces/events?limit=30`, "admin").then(next => setEvents(next.events || [])).catch(() => setEvents([]));
  }, [id]);
  useEffect(() => { if (open) load(); }, [open, load]);
  const upload = async (employee: FaceEmployee, file?: File) => {
    if (!file) return;
    try { const payload = file.type === "image/png" ? file : await toJpeg(file); await api(`/api/v1/admin/sites/${id}/faces/employees/${encodeURIComponent(employee.id)}/photos`, "admin", { method: "POST", headers: { "Content-Type": file.type === "image/png" ? "image/png" : "image/jpeg" }, body: payload }); toast("Rasm qabul qilindi — yuz namunasi saqlandi"); load(); }
    catch (reason) { toast(reason instanceof Error ? reason.message : "Rasm yuklanmadi", false); }
  };
  const remove = async (faceId: string) => {
    if (!(await confirm({ title: "Rasmni o‘chirish", text: "Bu rasm va undan olingan yuz namunasi butunlay o‘chiriladi.", confirmLabel: "O‘chirish", danger: true }))) return;
    try { await api(`/api/v1/admin/sites/${id}/faces/photos/${encodeURIComponent(faceId)}`, "admin", { method: "DELETE" }); toast("O‘chirildi"); load(); } catch (reason) { toast(reason instanceof Error ? reason.message : "O‘chirilmadi", false); }
  };
  return <details className="card quiet section-gap" open={open} onToggle={event => setOpen((event.currentTarget as HTMLDetailsElement).open)}>
    <summary><b>Yuz tanish (yopiq pilot)</b></summary>
    <div className="card-body">
      {error ? <div className="form-error">{error}</div> : !data ? <Skeleton height={120} /> : <>
        {data.service.ok ? <div className="note ok"><b>Xizmat tayyor</b>Moslik chegarasi: {data.threshold}</div> : <div className="note warn"><b>Xizmat ishlamayapti</b>{data.service.reason}</div>}
        <p className="metric-note">Yopiq pilot: har xodimdan <b>yozma rozilik</b> olinadi, 1–3 aniq yuzli rasm yuklanadi. Rasm shifrlangan namunaga aylanadi, davomat kadrlari 48 soatdan keyin o‘chadi.</p>
        {data.employees.length ? data.employees.map(employee => <div className={`face-card${employee.active === false ? " off" : ""}`} key={employee.id}>
          <div><b>{employee.name || "Nomsiz"}</b><small>{employee.active === false ? "faol emas" : employee.enrollment_status === "enrolled" ? "ro‘yxatda" : "rasm kutilmoqda"} · rozilik: {formatDateShort(employee.consent_recorded_at)}</small></div>
          <div className="face-photos">{employee.photos.length ? employee.photos.map(photo => <span className="face-photo" key={photo.id}><AuthedImage path={`/api/v1/admin/sites/${id}/faces/photos/${encodeURIComponent(photo.id)}/image`} className="face-thumb" /><button className="btn btn-icon btn-danger" aria-label="Rasmni o‘chirish" onClick={() => void remove(photo.id)}><Icon name="close" size={14} /></button></span>) : <span className="metric-note">rasm yo‘q</span>}</div>
          <label className="btn upload-btn">Rasm yuklash<input type="file" accept="image/*" onChange={event => { void upload(employee, event.target.files?.[0]); event.currentTarget.value = ""; }} /></label>
        </div>) : <EmptyState icon="users" title="Hali xodim kiritilmagan" detail="Yozma rozilikdan keyin xodim qo‘shing va rasmini yuklang." />}
        <button className="btn btn-primary" onClick={() => setAdding(true)}>Xodim qo‘shish</button>
        {events.length ? <><h3 className="face-events-title">So‘nggi kadrlar</h3><div className="face-grid">{events.map(event => <figure key={event.event_id} className={`face-item${event.person_id ? "" : " face-unknown"}`}><AuthedImage path={`/api/v1/admin/sites/${id}/faces/events/${encodeURIComponent(event.event_id)}/image`} /><figcaption><b>{event.person_id ? event.person_name || "?" : "Notanish"}</b><small>{String(event.occurred_at || "").slice(11, 16)} · {formatDateShort(event.occurred_at)}</small></figcaption></figure>)}</div></> : <p className="metric-note">Davomat kamerasidan hali kadr kelmagan.</p>}
      </>}
    </div>
    {adding ? <EmployeeModal siteId={siteId} onClose={() => setAdding(false)} onDone={() => { setAdding(false); toast("Xodim qo‘shildi — endi rasmini yuklang"); load(); }} /> : null}
  </details>;
}

function EmployeeModal({ siteId, onClose, onDone }: { siteId: string; onClose: () => void; onDone: () => void }) {
  const [name, setName] = useState(""); const [consent, setConsent] = useState(false); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (!name.trim()) { setError("Xodim ismini kiriting"); return; }
    if (!consent) { setError("Avval yozma rozilik oling va belgilang"); return; }
    setBusy(true); setError("");
    try { await api(`/api/v1/admin/sites/${encodeURIComponent(siteId)}/employees`, "admin", { method: "POST", body: JSON.stringify({ name: name.trim(), consent: true, consent_note: "Admin panel orqali qayd etildi" }) }); onDone(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Qo‘shilmadi"); setBusy(false); }
  };
  return <Modal title="Xodim qo‘shish" onClose={onClose} footer={<><button className="btn" onClick={onClose}>Bekor qilish</button><button className="btn btn-primary" disabled={busy} onClick={() => void submit()}>Qo‘shish</button></>}>
    <label className="field-label">Xodim ismi<input className="input" value={name} onChange={event => setName(event.target.value)} /></label>
    <label className="choice"><input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)} /><span><b>Yozma rozilik olindi</b><small>Rozilik qog‘ozisiz yuz namunasini saqlash mumkin emas</small></span></label>
    {error ? <div className="form-error">{error}</div> : null}
  </Modal>;
}
