import { useCallback, useEffect, useState } from "react";
import { api, formatDateShort, formatTimeUz } from "./api";
import { Card, CopyField, EmptyState, ErrorStrip, PageHeader, Pill, Skeleton, TabPanel, Tabs, useConfirm, useToast } from "./components";
import { GeometryEditor } from "./GeometryEditor";
import { InstallerCamera } from "./InstallerCamera";
import { t } from "./i18n";
import { Icon } from "./icons";

/* Usta ishining ikki ekrani: biriktirilgan obyektlar ro'yxati va
 * bitta obyektning ishga tushirish sahifasi.
 *
 * Eski panelda obyekt MODAL oynada ochilardi: telefonda u ekranning
 * hammasini egallardi, havola qilib bo'lmasdi va «orqaga» tugmasi
 * panelni butunlay tark etardi.  Endi bu manzil:
 * `/installer/jobs/<site_id>/<tab>`.
 */

export type Assignment = {
  site_id: string;
  site_name?: string;
  address?: string;
  contact_phone?: string;
  status: string;
  notes?: string;
  connection?: string;
  cameras_active?: number;
  cameras_expected?: number;
  updated_at?: string;
};

type Step = { key: string; label: string; done: boolean };
type Onboarding = {
  site_id: string;
  site: { name: string; address?: string; connection?: string };
  completed: number;
  total: number;
  percent: number;
  steps: Step[];
  pairing?: { code: string; expires_at?: string } | null;
  install_command?: string | null;
};

/** Ish holati — pill rangi bilan.  Holat nomi serverdan KOD bo'lib
 *  keladi (`assigned`/`in_progress`/`ready`/`completed`/`cancelled`);
 *  eski panel uni xom holda ko'rsatardi va usta «assigned» degan
 *  inglizcha so'zni o'qirdi. */
const STATUS_TONE: Record<string, string> = {
  assigned: "stale",
  in_progress: "grace",
  ready: "grace",
  completed: "online",
  cancelled: "offline",
};

function StatusPill({ status }: { status: string }) {
  const key = `panel.installer.status.${status}`;
  const label = t(key);
  return <Pill state={STATUS_TONE[status]}>{label === key ? status : label}</Pill>;
}

/* Usta o'zi qo'yadigan holatlar.  `cancelled` bu ro'yxatda YO'Q: server
   ham uni o'rnatuvchidan qabul qilmaydi (`installer_update_assignment`)
   — ishni bekor qilish admin qarori. */
const NEXT_STATUS = [
  { id: "in_progress", key: "panel.installer.status.set_in_progress" },
  { id: "ready", key: "panel.installer.status.set_ready" },
  { id: "completed", key: "panel.installer.status.set_completed" },
];

export function InstallerJobs({ jobs, error, onRetry, onOpen }: {
  jobs: Assignment[] | null;
  error: string;
  onRetry: () => void;
  onOpen: (siteId: string) => void;
}) {
  return <>
    <PageHeader title={t("panel.installer.jobs.title")} subtitle={t("panel.installer.jobs.subtitle")} actions={
      <button className="btn" onClick={onRetry}><Icon name="pulse"/>{t("panel.common.refresh")}</button>
    }/>
    {error ? <ErrorStrip detail={error} onRetry={onRetry}/> : null}
    {jobs === null
      ? <Card><div className="card-body"><Skeleton height={90}/></div></Card>
      : jobs.length
        /* `split-grid` — telefonda BITTA ustun (760 px dan pastda).
           `metric-grid` bu yerda yaramaydi: u telefonda ham ikki
           ustunda qoladi va obyekt nomi bilan manzil 180 px ga
           siqilardi. */
        ? <div className="split-grid">{jobs.map(job => <Card key={job.site_id}>
          <div className="card-body">
            <div className="shape-summary"><StatusPill status={job.status}/></div>
            <h2>{job.site_name || job.site_id}</h2>
            <p className="metric-note">{job.address || t("panel.installer.jobs.no_address")}</p>
            <p className="metric-note">
              {t("panel.installer.jobs.connection")}: <b>{job.connection || t("panel.common.unknown")}</b>
              {" · "}
              {t("panel.installer.jobs.cameras", { active: job.cameras_active ?? 0, expected: job.cameras_expected || "?" })}
            </p>
            <button className="btn btn-primary btn-wide" onClick={() => onOpen(job.site_id)}>{t("panel.installer.jobs.open")}</button>
          </div>
        </Card>)}</div>
        : <Card><div className="card-body">
          <EmptyState icon="store" title={t("panel.installer.jobs.empty_title")} detail={t("panel.installer.jobs.empty_detail")}/>
        </div></Card>}
  </>;
}

export const SITE_TABS = ["steps", "cameras", "zones"] as const;

export function InstallerSite({ siteId, tab, status, onSelectTab, onBack, onStatusChanged }: {
  siteId: string;
  tab: string;
  /* Ish holati obyekt javobida YO'Q — u biriktiruv yozuvida
     (`/installer/assignments`).  Shuning uchun yuqoridan beriladi:
     usta o'zi qaysi holatni qo'yganini KO'RIB turishi kerak, aks holda
     «Yakunlandi» ni ikki marta bosib, natijani hech qachon bilmasdi. */
  status: string;
  onSelectTab: (tab: string) => void;
  onBack: () => void;
  onStatusChanged: () => void;
}) {
  const [data, setData] = useState<Onboarding | null>(null);
  const [error, setError] = useState("");
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirm, confirmDialog] = useConfirm();
  const [toast, toastNode] = useToast();

  const load = useCallback(async () => {
    setError("");
    try {
      setData(await api<Onboarding>(`/api/v1/installer/sites/${encodeURIComponent(siteId)}/onboarding`, "installer"));
      setFailed(false);
    } catch (reason) {
      /* Alohida bayroq: `data` ni `null` qoldirsak sahifa abadiy
         skeletda qolardi, `{}` qilib qo'ysak esa bo'sh bosqichlar
         ro'yxati «hammasi bajarilgan» bo'lib ko'rinardi. */
      setFailed(true);
      setError(reason instanceof Error ? reason.message : t("panel.installer.site.load_failed"));
    }
  }, [siteId]);

  useEffect(() => { void load(); }, [load]);

  const newPairing = async () => {
    const ok = await confirm({
      title: t("panel.installer.pairing.confirm_title"),
      text: t("panel.installer.pairing.confirm_text"),
      confirmLabel: t("panel.installer.pairing.new"),
    });
    if (!ok) return;
    setBusy(true);
    try {
      const result = await api<{ onboarding: Onboarding }>(`/api/v1/installer/sites/${encodeURIComponent(siteId)}/pairing`, "installer", { method: "POST" });
      setData(result.onboarding);
      toast(t("panel.installer.pairing.created"));
    } catch (reason) {
      toast(reason instanceof Error ? reason.message : t("panel.installer.pairing.failed"), false);
    } finally {
      setBusy(false);
    }
  };

  const setStatus = async (status: string) => {
    /* «Yakunlandi» — tasdiq bilan: shundan keyin obyekt admin
       tekshiruviga o'tadi va usta ro'yxatidan yo'qoladi. */
    if (status === "completed") {
      const ok = await confirm({
        title: t("panel.installer.status.confirm_title"),
        text: t("panel.installer.status.confirm_text"),
        confirmLabel: t("panel.installer.status.set_completed"),
      });
      if (!ok) return;
    }
    setBusy(true);
    try {
      await api(`/api/v1/installer/sites/${encodeURIComponent(siteId)}/status`, "installer", {
        method: "PUT",
        body: JSON.stringify({ status }),
      });
      toast(t("panel.installer.status.saved"));
      onStatusChanged();
    } catch (reason) {
      toast(reason instanceof Error ? reason.message : t("panel.installer.status.failed"), false);
    } finally {
      setBusy(false);
    }
  };

  const back = <button className="btn" onClick={onBack}>{t("panel.common.back")}</button>;

  if (failed && !data) {
    return <>
      <PageHeader title={siteId} subtitle={t("panel.installer.site.load_failed")} actions={back}/>
      <ErrorStrip detail={error} onRetry={() => void load()}/>
    </>;
  }
  if (!data) {
    return <>
      <PageHeader title={siteId} subtitle={t("panel.common.loading")} actions={back}/>
      <Card><div className="card-body"><Skeleton height={120}/></div></Card>
    </>;
  }

  return <>
    <PageHeader title={data.site.name || siteId} subtitle={data.site.address || t("panel.installer.jobs.no_address")} actions={back}/>
    {error ? <ErrorStrip detail={error} onRetry={() => void load()}/> : null}
    <Tabs
      items={SITE_TABS.map(id => ({ id, label: t(id === "zones" ? "panel.tabs.zones" : `panel.installer.tabs.${id}`) }))}
      active={tab}
      onSelect={onSelectTab}
      panelId="installer-site-panel"
    />
    <TabPanel id="installer-site-panel" activeTab={tab}>
      {tab === "cameras" ? <InstallerCamera siteId={siteId} onChanged={() => void load()}/>
        : tab === "zones" ? <SiteZones siteId={siteId} onSaved={() => void load()}/>
        : <SiteSteps data={data} status={status} busy={busy} onNewPairing={() => void newPairing()} onStatus={next => void setStatus(next)}/>}
    </TabPanel>
    {confirmDialog}
    {toastNode}
  </>;
}

/** Chiziq va zona — muharrir kameralar ro'yxatini o'zi so'raydi.
 *
 * Nega alohida komponent: muharrir `cameras` propini TALAB qiladi
 * (kamera tanlagichi uchun), ro'yxat esa alohida endpointda.  Bu
 * so'rov `InstallerCamera` dagi bilan bir xil, lekin tab ochilmaguncha
 * yuborilmaydi. */
function SiteZones({ siteId, onSaved }: { siteId: string; onSaved: () => void }) {
  const [cameras, setCameras] = useState<{ camera_id: string; label?: string }[] | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const result = await api<{ cameras: { camera_id: string; label?: string }[] }>(`/api/v1/installer/sites/${encodeURIComponent(siteId)}/cameras`, "installer");
      setCameras(result.cameras || []);
    } catch (reason) {
      // Xatoda BO'SH ro'yxat: `null` «hali yuklanmoqda» degani va
      // skelet abadiy qolib ketardi.
      setCameras([]);
      setError(reason instanceof Error ? reason.message : t("panel.installer.cameras.load_failed"));
    }
  }, [siteId]);

  useEffect(() => { void load(); }, [load]);

  if (cameras === null) return <Card><div className="card-body"><Skeleton height={200}/></div></Card>;
  return <>
    {error ? <ErrorStrip detail={error} onRetry={() => void load()}/> : null}
    <GeometryEditor siteId={siteId} cameras={cameras} kind="installer" onSaved={onSaved} embedded/>
  </>;
}

function SiteSteps({ data, status, busy, onNewPairing, onStatus }: {
  data: Onboarding;
  status: string;
  busy: boolean;
  onNewPairing: () => void;
  onStatus: (status: string) => void;
}) {
  return <>
    <Card>
      <div className="card-head">
        <div><h2>{t("panel.installer.steps.title")}</h2><p>{t("panel.installer.steps.progress", { done: data.completed, total: data.total })}</p></div>
      </div>
      <div className="card-body">
        <div className="progress"><span style={{ width: `${Math.max(2, data.percent)}%` }}/></div>
        <ol className="zone-list">
          {data.steps.map(step => {
            /* Bosqich nomi KALIT bo'yicha tarjima qilinadi; server
               o'zbekcha `label` ham yuboradi va u zaxira bo'lib qoladi
               — yangi bosqich qo'shilib tarjimasi unutilsa qadam
               YO'QOLMAYDI. */
            const key = `panel.installer.step.${step.key}`;
            const label = t(key);
            return <li className="device-row" key={step.key}>
              <div className="zone-name">
                <b>{label === key ? step.label : label}</b>
              </div>
              <Pill state={step.done ? "online" : undefined}>{step.done ? t("panel.common.done") : t("panel.installer.steps.pending")}</Pill>
            </li>;
          })}
        </ol>
      </div>
    </Card>

    <Card className="section-gap">
      <div className="card-head">
        <div><h2>{t("panel.installer.pairing.title")}</h2><p>{t("panel.installer.pairing.subtitle")}</p></div>
        <div className="page-actions">
          <button className="btn" disabled={busy} onClick={onNewPairing}>{t("panel.installer.pairing.new")}</button>
        </div>
      </div>
      <div className="card-body">
        {data.pairing
          ? <>
            <div className="code-box">{data.pairing.code}</div>
            {/* Sana VA soat: kod 48 soat yashaydi, ya'ni faqat sana
                «bugunmi yoki ertaga tugaydimi?» degan savolga javob
                bermaydi.  Ikkalasi ham do'kon vaqtida (`api.ts`). */}
            <p className="metric-note">{t("panel.installer.pairing.expires", { date: formatDateShort(data.pairing.expires_at), time: formatTimeUz(data.pairing.expires_at) })}</p>
            <CopyField value={data.pairing.code}/>
          </>
          : <div className="note warn">{t("panel.installer.pairing.none")}</div>}
        {/* Linux buyrug'i ALOHIDA va shunday NOMLANADI: sotuv fokusi
            Windows yo'lida va nomsiz buyruq ustani «shuni Windowsda
            ham yozish kerak» degan xayolga solardi. */}
        {data.install_command ? <>
          <p className="field-label section-gap">{t("panel.installer.command.title")}</p>
          <p className="mono">{data.install_command}</p>
          <CopyField value={data.install_command}/>
          <p className="metric-note">{t("panel.installer.command.subtitle")}</p>
        </> : null}
      </div>
    </Card>

    <Card className="section-gap">
      <div className="card-head">
        <div><h2>{t("panel.installer.status.title")}</h2><p>{t("panel.installer.status.subtitle")}</p></div>
        {status ? <StatusPill status={status}/> : null}
      </div>
      <div className="card-body">
        <div className="page-actions">
          {/* Joriy holat tugmasi o'chirilgan: uni qayta bosish hech
              narsani o'zgartirmaydi va usta «bosdim, javob yo'q» deb
              o'ylardi. */}
          {NEXT_STATUS.map(item => <button
            key={item.id}
            className={`btn${item.id === "completed" ? " btn-primary" : ""}`}
            disabled={busy || status === item.id}
            onClick={() => onStatus(item.id)}
          >{t(item.key)}</button>)}
        </div>
      </div>
    </Card>
  </>;
}
