import { useCallback, useEffect, useRef, useState } from "react";
import {
  pollScan,
  mediaObjectUrl,
  saveCameraFromScan,
  saveCameraManually,
  startScan,
  type CameraRole,
  type ScanJob,
  type ScanStream,
} from "./api";
import { Card, EmptyState, PageHeader, PasswordInput, Pill } from "./components";
import { t } from "./i18n";
import { Icon } from "./icons";

/* Kamerani bulutdan ulash.
 *
 * Qidiruvning o'zi do'kon kompyuterida bajariladi (tarmoq multicast,
 * xususiy IP), lekin egasi buni faqat shu sahifadan boshqaradi va
 * localhost sahifasini umuman ko'rmaydi.
 *
 * To'rt qadam ataylab: har biri bitta savolga javob beradi.
 *   1. Tarmoqda nima bor?
 *   2. Qaysi kamera va uning paroli nima?
 *   3. Tasvir chindan kelayaptimi?
 *   4. Nomlab saqlash.
 *
 * 3-qadam ayniqsa muhim: kadr — egasi uchun "ishladi" degan yagona
 * ishonchli isbot.  Usiz u sozlashni tugatib, keyin bo'sh hisobotga
 * qarab qolardi.
 */

const POLL_MS = 2000;
//: Shundan keyin "biroz cho'zilyapti" deyiladi — foydalanuvchi
//: spinnerni "qotib qoldi" deb o'ylamasin.
const SLOW_AFTER_MS = 60_000;

// Rol — nomdan alohida SAQLANADIGAN maydon (chaqimchi_ai/camera_roles.py).
// Tugma rolni tanlaydi va nomni to'ldiradi; rolsiz saqlash ham mumkin —
// majburiy tanlov 2026-08-22 da hamma kamerani jimgina "Kirish" qilib
// qo'ygan xatoning ildizi edi.
//
// Yorliq matn emas, katalog KALITI: modul yuklanganda til hali
// tanlanmagan bo'ladi (`initLang()` keyinroq chaqiriladi), shuning
// uchun `t()` faqat render paytida ishlatiladi.
const ROLE_CHOICES: Array<{ role: CameraRole; key: string }> = [
  { role: "entrance", key: "panel.setup.role.entrance" },
  { role: "checkout", key: "panel.setup.role.checkout" },
  { role: "sales", key: "panel.setup.role.sales" },
  { role: "storage", key: "panel.setup.role.storage" },
];

//: Qadam nomlari ham shu sababdan kalit.
const STEP_KEYS = [
  "panel.setup.step.search",
  "panel.setup.step.pick",
  "panel.setup.step.check",
  "panel.setup.step.save",
];

type Step = 1 | 2 | 3 | 4;

function streamsOf(job: ScanJob | null): ScanStream[] {
  if (!job?.result) return [];
  return job.result.streams || job.result.cameras || [];
}

/** Topshiriq tugaguncha kuzatadi. */
function useScanJob(siteId: string) {
  const [job, setJob] = useState<ScanJob | null>(null);
  const [error, setError] = useState("");
  const [slow, setSlow] = useState(false);
  const timer = useRef(0);
  const startedAt = useRef(0);

  const stop = useCallback(() => {
    window.clearTimeout(timer.current);
    timer.current = 0;
  }, []);

  const watch = useCallback(
    (jobId: string) => {
      const tick = async () => {
        try {
          const next = await pollScan(siteId, jobId);
          setJob(next);
          setSlow(Date.now() - startedAt.current > SLOW_AFTER_MS);
          if (next.status === "queued" || next.status === "running") {
            timer.current = window.setTimeout(tick, POLL_MS);
          }
        } catch (reason) {
          setError(reason instanceof Error ? reason.message : t("panel.setup.status_failed"));
        }
      };
      void tick();
    },
    [siteId],
  );

  const begin = useCallback(
    async (params: Record<string, unknown>) => {
      stop();
      setError("");
      setSlow(false);
      setJob(null);
      startedAt.current = Date.now();
      try {
        const started = await startScan(siteId, params);
        setJob(started);
        watch(started.job_id);
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : t("panel.setup.scan_start_failed"));
      }
    },
    [siteId, stop, watch],
  );

  useEffect(() => stop, [stop]);
  const running = job?.status === "queued" || job?.status === "running";
  return { job, error, slow, running, begin };
}

function Progress({ job, slow }: { job: ScanJob | null; slow: boolean }) {
  if (!job) return null;
  return (
    <div className="scan-progress">
      <div className="progress"><span style={{ width: `${Math.max(6, job.progress)}%` }} /></div>
      <p className="metric-note">
        {job.note || t("panel.setup.progress_default")}
        {slow ? ` ${t("panel.setup.progress_slow")}` : ""}
      </p>
    </div>
  );
}

function ScanFrame({ siteId, jobId }: { siteId: string; jobId: string }) {
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let current = "";
    let stopped = false;
    void mediaObjectUrl(`/api/v1/owner/scan/${encodeURIComponent(jobId)}/frame`, "owner", siteId)
      .then(next => {
        // Komponent yopilgach kelgan javob darhol bo'shatiladi — aks
        // holda blob URL brauzer xotirasida osilib qolardi.
        if (stopped) { URL.revokeObjectURL(next); return; }
        current = next; setUrl(next);
      })
      .catch(reason => { if (!stopped) setError(reason instanceof Error ? reason.message : t("panel.setup.frame_failed")); });
    return () => { stopped = true; if (current) URL.revokeObjectURL(current); };
  }, [jobId, siteId]);
  return url ? <img className="scan-frame" src={url} alt={t("panel.setup.frame_alt")} /> : <EmptyState icon="camera" title={t("panel.setup.frame_failed")} detail={error || t("panel.setup.frame_loading")} />;
}

export function SetupCameras({ siteId, onDone }: { siteId: string; onDone: () => void }) {
  const [step, setStep] = useState<Step>(1);
  const [picked, setPicked] = useState<ScanStream | null>(null);
  const [credentials, setCredentials] = useState({ username: "", password: "" });
  // Nom ham, rol ham bo'sh boshlanadi — jim standart yo'q.
  const [label, setLabel] = useState("");
  const [role, setRole] = useState<CameraRole | "">("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [manual, setManual] = useState(false);
  const scan = useScanJob(siteId);

  const found = streamsOf(scan.job);
  const done = scan.job?.status === "done";

  const back = (to: Step) => { setStep(to); setSaveError(""); };

  const save = async () => {
    if (!scan.job || !picked) return;
    setSaving(true);
    setSaveError("");
    try {
      await saveCameraFromScan(siteId, {
        job_id: scan.job.job_id,
        stream_ref: picked.stream_ref,
        label: label.trim() || t("panel.common.camera"),
        role,
      });
      onDone();
    } catch (reason) {
      setSaveError(reason instanceof Error ? reason.message : t("panel.setup.save_failed"));
    } finally {
      setSaving(false);
    }
  };

  const saveManual = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setSaving(true);
    setSaveError("");
    try {
      await saveCameraManually(siteId, String(data.get("camera_id") || "camera-01"), {
        label: String(data.get("label") || t("panel.common.camera")),
        rtsp_url: String(data.get("rtsp_url") || ""),
        role: String(data.get("role") || "") as CameraRole | "",
      });
      onDone();
    } catch (reason) {
      setSaveError(reason instanceof Error ? reason.message : t("panel.setup.save_failed"));
    } finally {
      setSaving(false);
    }
  };

  return <>
    <PageHeader
      title={t("panel.setup.title")}
      subtitle={t("panel.setup.subtitle")}
      actions={<button className="btn" onClick={() => setManual(value => !value)}>
        {manual ? t("panel.setup.back_to_scan") : t("panel.setup.manual_entry")}
      </button>}
    />

    {manual ? (
      <Card>
        <div className="card-head">
          <div><h2>{t("panel.setup.manual.title")}</h2><p>{t("panel.setup.manual.subtitle")}</p></div>
        </div>
        <form className="card-body" onSubmit={saveManual}>
          <div className="form-grid">
            <label>{t("panel.setup.field.slot")}
              <select className="select" name="camera_id" defaultValue="camera-01">
                {[1, 2, 3, 4].map(index => (
                  <option key={index} value={`camera-0${index}`}>{`camera-0${index}`}</option>
                ))}
              </select>
            </label>
            <label>{t("panel.setup.field.name")}
              {/* Bo'sh boshlanadi — "Kirish eshigi" jim standarti hamma
                  kamerani kirish qilib ko'rsatib qo'yardi. */}
              <input className="input" name="label" placeholder={t("panel.setup.name_placeholder")} required />
            </label>
            <label>{t("panel.setup.field.role")}
              <select className="select" name="role" defaultValue="">
                <option value="">{t("panel.setup.role.none")}</option>
                {ROLE_CHOICES.map(choice => (
                  <option key={choice.role} value={choice.role}>{t(choice.key)}</option>
                ))}
              </select>
            </label>
          </div>
          <label>{t("panel.setup.field.rtsp")}
            <input className="input" name="rtsp_url" required placeholder="rtsp://foydalanuvchi:parol@192.168.1.64:554/..." />
          </label>
          <p className="metric-note">
            {t("panel.setup.manual.note")}
          </p>
          {saveError ? <div className="form-error" role="alert">{saveError}</div> : null}
          <button className="btn btn-primary" disabled={saving}>{saving ? t("panel.common.saving") : t("panel.common.save")}</button>
        </form>
      </Card>
    ) : (
      <>
        <ol className="setup-steps">
          {STEP_KEYS.map((key, index) => (
            <li key={key} className={step === index + 1 ? "active" : step > index + 1 ? "done" : ""}>
              <b>{index + 1}</b>{t(key)}
            </li>
          ))}
        </ol>

        {step === 1 ? (
          <Card>
            <div className="card-head">
              <div><h2>{t("panel.setup.scan.title")}</h2><p>{t("panel.setup.scan.subtitle")}</p></div>
              <button
                className="btn btn-primary"
                disabled={scan.running}
                onClick={() => void scan.begin({ kind: "lan_scan" })}
              >
                <Icon name="search" />{scan.running ? t("panel.setup.scan.running") : t("panel.setup.scan.button")}
              </button>
            </div>
            <div className="card-body">
              {scan.error ? <div className="form-error" role="alert">{scan.error}</div> : null}
              {scan.running ? <Progress job={scan.job} slow={scan.slow} /> : null}
              {scan.job?.status === "failed" ? (
                <EmptyState icon="camera" title={t("panel.setup.scan.failed_title")} detail={scan.job.error || t("panel.setup.scan.failed_detail")} />
              ) : null}
              {done && !found.length ? (
                <EmptyState
                  icon="camera"
                  title={t("panel.setup.scan.empty_title")}
                  detail={t("panel.setup.scan.empty_detail")}
                />
              ) : null}
              {done && found.length ? (
                <div className="scan-list">
                  {found.map(item => (
                    <button
                      key={`${item.ip}-${item.stream_ref}`}
                      className="scan-row"
                      onClick={() => { setPicked(item); setStep(2); }}
                    >
                      <div className="scan-name">
                        <Icon name="camera" />
                        <div>
                          <b>{item.ip || item.name || t("panel.common.camera")}</b>
                          <small>{item.vendor_hint || t("panel.setup.vendor_unknown")}</small>
                        </div>
                      </div>
                      <div className="page-actions">
                        {item.has_onvif ? <Pill state="active">ONVIF</Pill> : null}
                        {item.has_rtsp ? <Pill>RTSP</Pill> : null}
                      </div>
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
          </Card>
        ) : null}

        {step === 2 ? (
          <Card>
            <div className="card-head">
              <div><h2>{picked?.ip || t("panel.common.camera")}</h2><p>{t("panel.setup.credentials.subtitle")}</p></div>
              <button className="btn" onClick={() => back(1)}>{t("panel.common.back")}</button>
            </div>
            <div className="card-body">
              <div className="form-grid">
                <label>{t("panel.setup.field.username")}
                  <input
                    className="input"
                    value={credentials.username}
                    autoComplete="off"
                    onChange={event => setCredentials(current => ({ ...current, username: event.target.value }))}
                  />
                </label>
                <label>{t("panel.setup.field.password")}
                  <PasswordInput
                    className="input"
                    value={credentials.password}
                    autoComplete="new-password"
                    onChange={event => setCredentials(current => ({ ...current, password: event.target.value }))}
                  />
                </label>
              </div>
              <p className="metric-note">
                {t("panel.setup.credentials.note")}
              </p>
              {scan.error ? <div className="form-error" role="alert">{scan.error}</div> : null}
              {scan.running ? <Progress job={scan.job} slow={scan.slow} /> : null}
              {done && streamsOf(scan.job).length && scan.job?.kind !== "lan_scan" ? (
                <div className="scan-list">
                  {streamsOf(scan.job).map(item => (
                    <button
                      key={item.stream_ref}
                      className="scan-row"
                      onClick={() => {
                        setPicked(item);
                        // Server taklifi 4-qadamda oldindan tanlangan
                        // bo'lib chiqadi — tasdiqlash odamda qoladi.
                        const suggested = (item.suggested_role || "") as CameraRole | "";
                        setRole(suggested);
                        const choice = ROLE_CHOICES.find(entry => entry.role === suggested);
                        setLabel(choice ? t(choice.key) : item.name || "");
                        // Manzil emas, INDEKS yuboriladi — parol
                        // brauzerga umuman tushmaydi.
                        void scan.begin({
                          kind: "probe",
                          from_job: scan.job?.job_id || "",
                          stream_ref: item.stream_ref,
                        });
                        setStep(3);
                      }}
                    >
                      <div className="scan-name">
                        <Icon name="camera" />
                        <div>
                          <b>{item.name || t("panel.setup.stream_n", { n: item.stream_ref + 1 })}</b>
                          <small>
                            {item.encoding || "—"}
                            {item.width ? ` · ${item.width}×${item.height}` : ""}
                          </small>
                        </div>
                      </div>
                      {item.works === false ? <Pill state="offline">{t("panel.setup.stream_failed")}</Pill> : <Pill state="active">{t("panel.setup.stream_ok")}</Pill>}
                    </button>
                  ))}
                </div>
              ) : null}
              {!scan.running ? (
                <button
                  className="btn btn-primary"
                  onClick={() =>
                    void scan.begin({
                      kind: picked?.has_onvif ? "onvif" : "channels",
                      host: picked?.ip || "",
                      username: credentials.username,
                      password: credentials.password,
                    })
                  }
                >
                  {t("panel.setup.find_streams")}
                </button>
              ) : null}
            </div>
          </Card>
        ) : null}

        {step === 3 ? (
          <Card>
            <div className="card-head">
              <div><h2>{t("panel.setup.check.title")}</h2><p>{t("panel.setup.check.subtitle")}</p></div>
              <button className="btn" onClick={() => back(2)}>{t("panel.common.back")}</button>
            </div>
            <div className="card-body">
              {scan.running ? <Progress job={scan.job} slow={scan.slow} /> : null}
              {scan.job?.has_frame ? (
                <>
                  <ScanFrame siteId={siteId} jobId={scan.job.job_id} />
                  <div className="page-actions">
                    <button className="btn btn-primary" onClick={() => setStep(4)}>{t("panel.setup.check.ok")}</button>
                    <button className="btn" onClick={() => back(2)}>{t("panel.setup.check.other_stream")}</button>
                  </div>
                </>
              ) : scan.job?.status === "failed" ? (
                <EmptyState icon="camera" title={t("panel.setup.check.failed_title")} detail={scan.job.error || t("panel.setup.check.failed_detail")} />
              ) : null}
            </div>
          </Card>
        ) : null}

        {step === 4 ? (
          <Card>
            <div className="card-head">
              <div><h2>{t("panel.setup.name.title")}</h2><p>{t("panel.setup.name.subtitle")}</p></div>
              <button className="btn" onClick={() => back(3)}>{t("panel.common.back")}</button>
            </div>
            <div className="card-body">
              <div className="page-actions preset-names">
                {ROLE_CHOICES.map(choice => (
                  <button
                    key={choice.role}
                    className={`btn ${role === choice.role ? "btn-primary" : ""}`}
                    onClick={() => {
                      setRole(choice.role);
                      setLabel(current => (current.trim() ? current : t(choice.key)));
                    }}
                  >
                    {t(choice.key)}
                  </button>
                ))}
                {/* Ochiq "rolsiz" varianti SHART: majburiy tanlov
                    2026-08-22 xatosining ildizi edi. */}
                <button className={`btn ${role === "" ? "btn-primary" : ""}`} onClick={() => setRole("")}>
                  {t("panel.setup.role.skip")}
                </button>
              </div>
              {picked?.suggestion_reasons?.length ? (
                <p className="metric-note">{picked.suggestion_reasons.join(" · ")}</p>
              ) : null}
              {role === "entrance" ? (
                <p className="metric-note">
                  {t("panel.setup.entrance_note")}
                </p>
              ) : null}
              <label>{t("panel.setup.field.name")}<input className="input" value={label} placeholder={t("panel.setup.name_placeholder")} onChange={event => setLabel(event.target.value)} /></label>
              {saveError ? <div className="form-error" role="alert">{saveError}</div> : null}
              <button className="btn btn-primary btn-wide" disabled={saving} onClick={() => void save()}>
                {saving ? t("panel.common.saving") : t("panel.setup.save_camera")}
              </button>
              <p className="metric-note">
                {t("panel.setup.applies_soon")}
              </p>
            </div>
          </Card>
        ) : null}
      </>
    )}
  </>;
}
