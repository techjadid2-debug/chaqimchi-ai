import { eventLabel, t } from "./i18n";
import { useEffect, useState } from "react";
import { api, formatDateShort, formatDateUz, formatMoney, formatNumber, formatTimeUz, hasFeature, mediaObjectUrl, relativeMinutes, telegramBotUrl } from "./api";
import { Avatar, Card, EmptyState, PageHeader, Pill, PlanLock, StatCard } from "./components";
import { Donut, LineChart, type Point } from "./charts";
import { Demography } from "./Demography";
import { toneOf } from "./EventTimeline";
import { HeatmapThumb } from "./Heatmap";
import { Icon } from "./icons";
import { PeriodBar, dayLabel, eventSegments, eventTotal, nightCount, periodDays, periodLabel, readPeriod, savePeriod, useOverview, type Period } from "./overview";
import type { Dashboard, Site } from "./types";

/* «Bosh sahifa» — do'kon egasining yagona ekrani (dizayn-3 «Overview»).
 *
 * Tartib ataylab: tepada davr tanlagich va beshta raqam, ostida jonli
 * kadrlar, keyin mijozlar tahlili va issiqlik xaritasi, hodisalar
 * taqsimoti va zonalar; o'ngda AI hodisalari, xodim, tarif, qurilma va
 * Telegram.  Egasi panelni kuniga bir necha marta telefondan ochadi va
 * unga "hammasi joyidami?" degan savolga javob kerak — bo'limlar
 * bo'ylab yurish emas.
 *
 * «Bugun» bitta so'rovdan (`/api/v1/owner/dashboard`) keladi; 7 va 30
 * kun uchun `/owner/overview` qo'shiladi.  Server bermaydigan
 * ko'rsatkich UMUMAN chizilmaydi: yolg'on nol yoki bo'sh grafik
 * "tizim ishlamayapti" degan taassurot qoldiradi. */

type AttendanceRow = {
  employee_id: string;
  employee_name: string;
  external_id?: string | null;
  first_seen?: string | null;
  status: string;
};

/* Matnning o'zi emas, KALITI: modul yuklanganda til hali tanlanmagan
   (`initLang()` keyinroq chaqiriladi), ya'ni bu yerda `t()` chaqirilsa
   yorliq doim o'zbekcha qolardi.  Tarjima chizish paytida. */
const ATTENDANCE_LABEL: Record<string, { key: string; tone: string }> = {
  present: { key: "panel.home.attendance.present", tone: "online" },
  late: { key: "panel.home.attendance.late", tone: "stale" },
  absent: { key: "panel.home.attendance.absent", tone: "offline" },
  early_leave: { key: "panel.home.attendance.early_leave", tone: "stale" },
  unscheduled: { key: "panel.home.attendance.unscheduled", tone: "" },
};

/* Hodisa belgisi — rang turga qarab (`EventTimeline.toneOf` bilan bir
   ma'no), belgi rangga qarab: qizil — xavfsizlik, sariq — savdo zali,
   ko'k — o'tish, yashil — tiklanish, kulrang — noma'lum. */
const ICON_BY_TONE: Record<string, string> = { red: "shield", yellow: "clock", blue: "users", green: "camera", grey: "pulse" };

const HOME_PERIODS: Period[] = ["today", "7", "30"];

/* Hodisa rasmchasi — namunadagi ro'yxatdagi kichik kadr.
 *
 * Faqat `has_snapshot` bo'lgan hodisa uchun so'raladi: har qatorga
 * so'rov yuborilsa kirish-chiqishlar 404 bilan jurnalni to'ldirardi.
 * Blob URL kesh — dashboard 15 soniyada yangilanadi, rasm esa bitta
 * hodisa uchun bir marta yuklanadi. */
const THUMBS = new Map<string, Promise<string>>();
function EventThumb({ id, siteId, tone }: { id: string; siteId: string; tone: string }) {
  const [src, setSrc] = useState("");
  useEffect(() => {
    let alive = true;
    const key = `${siteId}:${id}`;
    if (!THUMBS.has(key)) {
      THUMBS.set(key, mediaObjectUrl(`/api/v1/owner/events/${encodeURIComponent(id)}/snapshot`, "owner", siteId).catch(() => ""));
    }
    void THUMBS.get(key)?.then(url => { if (alive) setSrc(url); });
    return () => { alive = false; };
  }, [id, siteId]);
  return src
    ? <img className="event-thumb" src={src} alt=""/>
    : <span className={`event-icon tone-${tone}`}><Icon name={ICON_BY_TONE[tone] || "pulse"} size={16}/></span>;
}

/* Ogohlantirish (qizil/sariq) va oddiy qayd (kirish-chiqish, tizim)
   ikki ro'yxat: namunada «AI hodisalari» va «So'nggi hodisalar» alohida —
   ega avval xavotirli narsani ko'rsin, keyin oqimni. */
const ALERT_TONES = new Set(["red", "yellow"]);

/** Soniyalarni "06:42" ko'rinishiga o'tkazadi. */
function asDuration(seconds: number | null) {
  if (seconds == null || !Number.isFinite(seconds) || seconds <= 0) return null;
  const total = Math.round(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const rest = total % 60;
  return hours
    ? `${hours}:${String(minutes).padStart(2, "0")}`
    : `${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
}

function num(source: unknown, ...keys: string[]): number | null {
  for (const key of keys) {
    const found = key.split(".").reduce<unknown>(
      (current, part) => (current && typeof current === "object" ? (current as Record<string, unknown>)[part] : undefined),
      source,
    );
    if (typeof found === "number") return found;
  }
  return null;
}

/** Telegram a'zolari — karta "Ulangan" yoki "Ulash" holatini
 *  ko'rsatishi uchun. */
function useTelegramMembers(siteId: string) {
  const [count, setCount] = useState<number | null>(null);
  useEffect(() => {
    if (!siteId) return;
    let stopped = false;
    api<{ members: { id: string }[] }>("/api/v1/owner/members", "owner", { siteId })
      .then(data => { if (!stopped) setCount((data.members || []).length); })
      .catch(() => { if (!stopped) setCount(null); });
    return () => { stopped = true; };
  }, [siteId]);
  return count;
}

/** Xodimlar davomati — funksiya yopiq bo'lsa karta umuman chizilmaydi. */
function useAttendance(siteId: string) {
  const [rows, setRows] = useState<AttendanceRow[] | null>(null);
  const [available, setAvailable] = useState(true);
  useEffect(() => {
    if (!siteId) return;
    let stopped = false;
    api<{ rows: AttendanceRow[] }>("/api/v1/owner/attendance", "owner", { siteId })
      .then(data => { if (!stopped) setRows(data.rows || []); })
      // 402/403/404 — davomat funksiyasi shu tarifda yoqilmagan.  Bu
      // xato emas, shuning uchun ogohlantirish ko'rsatilmaydi.
      .catch(() => { if (!stopped) setAvailable(false); });
    return () => { stopped = true; };
  }, [siteId]);
  return { rows, available };
}

export function OwnerHome({ dashboard, sites, siteId, onNavigate, cameras }: {
  dashboard: Dashboard;
  sites: Site[];
  siteId: string;
  onNavigate: (id: string, param?: string) => void;
  cameras: React.ReactNode;
}) {
  const today = dashboard.today;
  const traffic = (today.traffic || {}) as Record<string, unknown>;
  const hourly = Array.isArray(traffic.hourly) ? (traffic.hourly as { hour: number; entered: number }[]) : [];
  const device = dashboard.device;
  const attendance = useAttendance(siteId);
  const members = useTelegramMembers(siteId);

  const [period, setPeriod] = useState<Period>(() => readPeriod());
  const { overview, error: overviewError } = useOverview(siteId, periodDays(period));
  const choose = (next: Period) => { setPeriod(next); savePeriod(next); };
  const isToday = period === "today";

  // Bugungi raqamlar dashboard'dan; davr uchun overview'dan.  Overview
  // hali kelmagan bo'lsa (yuklanmoqda) bugungi raqam turadi — bo'sh
  // karta emas, eski raqam; yangi so'rov tugagach almashadi.
  const entered = isToday || !overview ? num(traffic, "entered") : overview.totals.entered;
  const changePercent = isToday || !overview ? num(traffic, "change_percent") : overview.totals.change_percent;
  const changeNote = isToday ? t("panel.home.stat.vs_yesterday") : t("panel.period.vs_previous");
  const series = isToday || !overview ? hourly.map(item => Number(item.entered) || 0) : overview.daily.map(day => day.entered);

  const security = (today.security || {}) as Record<string, number>;
  const todayEvents: Record<string, number> = { ...security, queue_alerts: num(today, "queue.alerts") || 0 };
  const periodEvents = isToday || !overview ? todayEvents : overview.events;
  const alerts = eventTotal(periodEvents);
  const night = nightCount(periodEvents);

  // O'rtacha to'xtash — zonalar bo'yicha o'lchangan o'rtacha.
  const dwellZones = Array.isArray(today.dwell) ? (today.dwell as { count: number; average_sec: number }[]) : [];
  const dwellTotal = dwellZones.reduce((sum, zone) => sum + (zone.count || 0), 0);
  const dwellAverage = dwellTotal
    ? dwellZones.reduce((sum, zone) => sum + (zone.average_sec || 0) * (zone.count || 0), 0) / dwellTotal
    : null;

  const onDuty = attendance.rows?.filter(row => row.status === "present" || row.status === "late").length;
  const scheduled = attendance.rows?.filter(row => row.status !== "unscheduled").length;
  const onlineBranches = sites.filter(site => site.connection === "online").length;
  /* 4- va 5-karta o'rinbosarlari: xodim yoki navbat; filial / to'xtash /
     gavjum soat.  Karta soni DOIM 5 — 4 karta 5 ustunli to'rda bittasini
     yolg'iz qoldirardi, 3 karta esa namunadagi qatorni buzardi. */
  const queueAlerts = isToday || !overview
    ? num(today, "queue.alerts") || 0
    : Number(overview.events?.queue_alerts ?? overview.events?.queue_threshold_exceeded ?? 0);
  const busiestHour = (traffic.busiest_hour || null) as { hour: number; entered: number } | null;
  const busiestDay = overview?.totals.busiest_day || null;
  const busiest = isToday || !overview
    ? (busiestHour && busiestHour.entered ? { value: `${String(busiestHour.hour).padStart(2, "0")}:00`, count: busiestHour.entered, label: t("panel.home.stat.busiest_hour") } : null)
    : (busiestDay && busiestDay.entered ? { value: dayLabel(busiestDay.date), count: busiestDay.entered, label: t("panel.home.stat.busiest_day") } : null);

  const flowPoints: Point[] = isToday || !overview
    ? hourly.map(item => ({ label: `${String(item.hour).padStart(2, "0")}:00`, value: Number(item.entered) || 0 }))
    : overview.daily.map(day => ({ label: dayLabel(day.date), value: day.entered }));
  const connection = dashboard.site.connection;
  const botUrl = telegramBotUrl();
  const edgeConfig = dashboard.capabilities?.edge_config;
  const geometry = dashboard.capabilities?.geometry;
  const poisoned = dashboard.diagnostics?.payload?.outbox?.poisoned || 0;
  const heatOpen = hasFeature(dashboard, "xarita");
  const securityOpen = hasFeature(dashboard, "xavfsizlik");
  const firstCamera = dashboard.cameras[0]?.camera_id || "";
  const [heatState, setHeatState] = useState<"loading" | "ready" | "empty" | "error">("loading");
  const segments = eventSegments(periodEvents);
  const showStaff = Boolean(attendance.available && attendance.rows);
  const alertEvents = dashboard.events.filter(item => ALERT_TONES.has(toneOf(item.event_type)));
  const recentEvents = dashboard.events.filter(item => !ALERT_TONES.has(toneOf(item.event_type)));
  const eventRow = (item: Dashboard["events"][number], index: number) => {
    const tone = toneOf(item.event_type);
    const hasSnapshot = Boolean((item as { has_snapshot?: boolean }).has_snapshot);
    return <div className="event-row" key={item.id || index}>
      <div className="event-name">
        {item.id && hasSnapshot ? <EventThumb id={item.id} siteId={siteId} tone={tone}/> : <span className={`event-icon tone-${tone}`}><Icon name={ICON_BY_TONE[tone] || "pulse"} size={16}/></span>}
        <div><b>{eventLabel(item.event_type)}</b><small>{formatTimeUz(item.occurred_at || item.created_at)} · {item.camera_id || t("panel.home.events.system")}</small></div>
      </div>
      <button className="btn btn-icon" aria-label={t("panel.home.details")} onClick={() => onNavigate("alerts", item.id || "")}><Icon name="eye" size={16}/></button>
    </div>;
  };

  return <>
    <PageHeader title={t("panel.owner.home_title")} subtitle={formatDateUz()} actions={<PeriodBar value={period} options={HOME_PERIODS} onChange={choose}/>}/>
    {connection !== "online" ? <div className={`alert-strip ${connection === "stale" ? "alert-info" : "alert-warning"}`}>
      <Icon name="bell" />
      <div><strong>{t(connection === "stale" ? "panel.home.connection.stale_title" : "panel.home.connection.lost_title")}</strong> {t("panel.home.connection.detail", { since: relativeMinutes(dashboard.site.minutes_since_seen) })}</div>
    </div> : null}
    {/* ENG MUHIM eslatma: chiziqsiz hech narsa sanalmaydi.  Server buni
        biladi, endi egasi ham ko'radi — avval panel shunchaki 0
        ko'rsatib, "kutib turing" derdi va bu hech qachon o'zgarmasdi. */}
    {geometry && !geometry.lines_drawn ? <div className="alert-strip alert-warning">
      <Icon name="shapes" />
      <div><strong>{t("panel.home.lines.title")}</strong> {t("panel.home.lines.detail")}</div>
      <button className="btn btn-primary" onClick={() => onNavigate("cameras", "zones")}>{t("panel.home.lines.action")}</button>
    </div> : null}
    {dashboard.night_watch && !dashboard.night_watch.hours_set ? <div className="alert-strip alert-info">
      <Icon name="moon" />
      <div><strong>{t("panel.home.night.title")}</strong> {t("panel.home.night.detail")}</div>
      <button className="btn btn-primary" onClick={() => onNavigate("settings", "store")}>{t("panel.home.night.action")}</button>
    </div> : null}
    {edgeConfig && !edgeConfig.ready ? <div className="alert-strip alert-info"><Icon name="pulse"/><div><strong>{t("panel.home.config.pending_title")}</strong> {edgeConfig.reason || t("panel.home.config.pending_detail")}</div></div> : null}
    {poisoned ? <div className="alert-strip alert-info"><Icon name="bell"/><div><strong>{t("panel.home.outbox.title", { count: poisoned })}</strong> {t("panel.home.outbox.detail")}</div></div> : null}
    {overviewError ? <div className="alert-strip alert-info"><Icon name="bell"/><div>{overviewError}</div></div> : null}

    <div className="metric-grid metric-grid-5">
      <StatCard
        label={t("panel.home.stat.visitors_period")}
        value={formatNumber(entered)}
        note={periodLabel(period)}
        icon="entry"
        tone="blue"
        series={series}
        deltaPercent={changePercent}
        deltaNote={changeNote}
      />
      <StatCard
        label={t("panel.home.stat.cameras")}
        value={`${formatNumber(dashboard.site.cameras_active)} / ${formatNumber(dashboard.site.cameras_expected)}`}
        note={connection === "online" ? t("panel.home.status.online") : t("panel.home.stat.last_data")}
        icon="camera"
        tone={connection === "online" ? "green" : "red"}
      />
      <StatCard
        label={t("panel.home.stat.events")}
        value={formatNumber(alerts)}
        note={night ? t("panel.home.stat.events_night", { count: formatNumber(night) }) : alerts ? periodLabel(period) : t("panel.home.stat.alerts_none")}
        icon="shield"
        tone={night ? "red" : alerts ? "yellow" : "green"}
      />
      {showStaff ? <StatCard
        label={t("panel.home.stat.staff")}
        value={`${formatNumber(onDuty)} / ${formatNumber(scheduled)}`}
        note={t("panel.home.stat.staff_note")}
        icon="users"
        tone="green"
      /> : <StatCard
        label={t("panel.owner.metric_queue")}
        value={formatNumber(queueAlerts)}
        note={queueAlerts ? periodLabel(period) : t("panel.home.stat.queue_none")}
        icon="bell"
        tone={queueAlerts ? "yellow" : "green"}
      />}
      {sites.length > 1 ? <StatCard
        label={t("panel.home.stat.branches")}
        value={formatNumber(sites.length)}
        note={t("panel.home.stat.branches_note", { online: formatNumber(onlineBranches) })}
        icon="branch"
        tone={onlineBranches === sites.length ? "green" : "yellow"}
      /> : dwellAverage ? <StatCard
        label={t("panel.home.stat.dwell")}
        value={String(asDuration(dwellAverage))}
        note={t("panel.home.stat.dwell_note")}
        icon="clock"
        tone="yellow"
      /> : <StatCard
        label={busiest ? busiest.label : t("panel.home.stat.busiest_hour")}
        value={busiest ? busiest.value : "—"}
        note={busiest ? t("panel.home.stat.busiest_note", { count: formatNumber(busiest.count) }) : t("panel.home.stat.no_data_yet")}
        icon="clock"
        tone="blue"
      />}
    </div>

    <div className="home-grid">
      <div className="stack">
        {cameras}

        <div className="split-grid">
          <Card>
            <div className="card-head">
              <div><h2>{t("panel.home.analysis.title")}</h2><p>{isToday ? t("panel.home.flow.subtitle") : t("panel.home.analysis.daily_subtitle")}</p></div>
              <button className="btn" onClick={() => onNavigate("analytics")}>{t("panel.home.analysis.open")}</button>
            </div>
            {flowPoints.some(point => point.value > 0)
              ? <LineChart series={[{ name: t("panel.home.flow.series"), points: flowPoints }]} />
              : geometry && !geometry.lines_drawn
                ? <EmptyState icon="shapes" title={t("panel.home.flow.no_lines_title")} detail={t("panel.home.flow.no_lines_detail")} />
                : <EmptyState icon="chart" title={t("panel.home.flow.empty_title")} detail={t("panel.home.flow.empty_detail")} />}
          </Card>

          <Card>
            <div className="card-head">
              <div><h2>{t("panel.heat.title")}</h2><p>{t("panel.home.heat.subtitle")}</p></div>
              <button className="btn" onClick={() => onNavigate("customers", "heatmap")}>{t("panel.home.heat.open")}</button>
            </div>
            {!heatOpen
              ? <PlanLock title={t("panel.heat.lock_title")} detail={t("panel.heat.lock_detail")} onUpgrade={() => onNavigate("settings", "billing")}/>
              : firstCamera ? <div className={`heat-thumb-wrap${heatState === "empty" || heatState === "error" ? " is-empty" : ""}`}>
                  <HeatmapThumb siteId={siteId} cameraId={firstCamera} onState={setHeatState}/>
                  {heatState === "empty" || heatState === "error" ? <EmptyState icon="heat" title={t("panel.home.heat.empty_title")} detail={t("panel.home.heat.empty_detail")}/> : null}
                </div>
              : <EmptyState icon="camera" title={t("panel.home.heat.empty_title")} detail={t("panel.home.heat.empty_detail")}/>}
          </Card>
        </div>

        <div className="split-grid">
          <Card>
            <div className="card-head"><div><h2>{t("panel.home.mix.title")}</h2><p>{periodLabel(period)}</p></div></div>
            {!securityOpen
              ? <PlanLock title={t("panel.home.mix.lock_title")} detail={t("panel.home.mix.lock_detail")} onUpgrade={() => onNavigate("settings", "billing")}/>
              : segments.length
                ? <Donut segments={segments} centerValue={formatNumber(alerts)} centerLabel={t("panel.home.mix.center")}/>
                : <EmptyState icon="shield" title={t("panel.home.mix.empty_title")} detail={t("panel.home.mix.empty_detail")}/>}
          </Card>

          <Card>
            <div className="card-head">
              <div><h2>{t("panel.home.zones.title")}</h2><p>{t("panel.home.zones.subtitle")}</p></div>
            </div>
            {dwellZones.length ? <div className="zone-list">
              {dwellZones.slice(0, 5).map(zone => {
                const item = zone as unknown as { zone: string; count: number; average_sec: number };
                const peak = Math.max(...dwellZones.map(entry => entry.count || 0), 1);
                return <div className="zone-row" key={item.zone}>
                  <div className="zone-name"><b>{item.zone}</b><small>{t("panel.home.zones.average", { value: asDuration(item.average_sec) ?? "" })}</small></div>
                  <div className="zone-bar"><i style={{ width: `${Math.max(6, ((item.count || 0) / peak) * 100)}%` }} /></div>
                  <span className="list-value">{formatNumber(item.count)}</span>
                </div>;
              })}
            </div> : <EmptyState icon="heat" title={t("panel.home.zones.empty_title")} detail={t("panel.home.zones.empty_detail")} />}
          </Card>
        </div>

        {sites.length > 1 ? <Card>
          <div className="card-head"><div><h2>{t("panel.home.branches.title")}</h2><p>{t("panel.home.branches.subtitle")}</p></div><button className="btn" onClick={() => onNavigate("settings", "branches")}>{t("panel.common.all")}</button></div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>{t("panel.home.branches.col_branch")}</th><th>{t("panel.home.cameras")}</th><th>{t("panel.home.branches.col_connection")}</th></tr></thead>
              <tbody>
                {sites.map(site => <tr key={site.id}>
                  <td><div className="table-title">{site.name}{site.id === siteId ? <span className="chip-self">{t("panel.home.branches.you")}</span> : null}</div><small>{site.address || t("panel.home.branches.no_address")}</small></td>
                  <td>{formatNumber(site.cameras_active)} / {formatNumber(site.cameras_expected)}</td>
                  <td><Pill state={site.connection}>{t(site.connection === "online" ? "panel.home.status.online" : site.connection === "stale" ? "panel.home.status.stale" : "panel.home.status.offline")}</Pill></td>
                </tr>)}
              </tbody>
            </table>
          </div>
        </Card> : null}
      </div>

      <div className="stack">
        <Card>
          <div className="card-head"><div><h2>{t("panel.home.events.title")}</h2><p>{t("panel.home.events.subtitle")}</p></div><button className="btn btn-icon" aria-label={t("panel.home.events.view_all")} onClick={() => onNavigate("alerts")}><Icon name="bell" /></button></div>
          {/* Rasm yo'qligini YASHIRMAYMIZ.  2026-08-26 da do'kon uch soat
              rasmsiz ishladi va panel buni hech qanday tarzda aytmadi —
              hodisa bor, rasmi yo'q, sababi noma'lum edi. */}
          {dashboard.media_dropped ? <p className="metric-note media-error">
            {t("panel.home.events.media_dropped", { count: formatNumber(dashboard.media_dropped) })}
          </p> : null}
          {alertEvents.length ? <>
            <div className="event-list">{alertEvents.slice(0, 6).map(eventRow)}</div>
            <button className="btn btn-wide" onClick={() => onNavigate("alerts")}>{t("panel.home.events.view_all")}</button>
          </> : <EmptyState icon="shield" title={t("panel.home.events.empty_title")} detail={t("panel.home.events.empty_detail")} />}
        </Card>

        <Card>
          <div className="card-head"><div><h2>{t("panel.home.recent.title")}</h2><p>{t("panel.home.recent.subtitle")}</p></div></div>
          {recentEvents.length
            ? <div className="event-list">{recentEvents.slice(0, 5).map(eventRow)}</div>
            : <EmptyState icon="entry" title={t("panel.home.recent.empty_title")} detail={t("panel.home.recent.empty_detail")} />}
        </Card>

        <Demography dashboard={dashboard} siteId={siteId} onNavigate={onNavigate} />

        {attendance.available && attendance.rows?.length ? <Card>
          <div className="card-head"><div><h2>{t("panel.home.staff.title")}</h2><p>{t("panel.home.staff.subtitle")}</p></div><button className="btn btn-icon" aria-label={t("panel.home.staff.open")} onClick={() => onNavigate("employees")}><Icon name="users" /></button></div>
          <div className="staff-list">
            {attendance.rows.slice(0, 8).map(row => {
              const known = ATTENDANCE_LABEL[row.status];
              // Notanish holat YO'QOLMAYDI — xom kod ko'rinadi, bo'sh joy emas.
              const label = known ? { text: t(known.key), tone: known.tone } : { text: row.status, tone: "" };
              return <div className="staff-row" key={row.employee_id}>
                <Avatar name={row.employee_name} />
                <div className="staff-name"><b>{row.employee_name}</b><small>{row.external_id || "—"}</small></div>
                <Pill state={label.tone}>{label.text}</Pill>
                <span className="list-value">{(row.first_seen || "").slice(11, 16) || "—"}</span>
              </div>;
            })}
          </div>
        </Card> : null}

        <Card>
          <div className="card-head"><div><h2>{t("panel.home.plan.title")}</h2><p>{t(dashboard.subscription?.status === "active" ? "panel.home.plan.active" : "panel.home.plan.check")}</p></div><Pill state={dashboard.subscription?.status}>{dashboard.site.plan?.name || t("panel.home.plan.fallback")}</Pill></div>
          <div className="card-body">
            <div className="simple-row"><span>{t("panel.home.plan.monthly")}</span><b>{formatMoney(dashboard.subscription?.monthly_price_uzs)}</b></div>
            {dashboard.subscription?.subscription_until
              ? <div className="simple-row"><span>{t("panel.home.plan.until")}</span><b>{t("panel.home.plan.until_value", { date: formatDateShort(dashboard.subscription.subscription_until) })}</b></div>
              : null}
            <div className="simple-row"><span>{t("panel.home.cameras")}</span><b>{t("panel.home.plan.cameras_value", { count: formatNumber(dashboard.site.cameras_expected) })}</b></div>
            <button className="btn btn-wide" onClick={() => onNavigate("settings", "billing")}>{t("panel.home.plan.manage")}</button>
          </div>
        </Card>

        {/* Do'kon kompyuterining holati.
            Egasi uchun bitta savolga javob: "kompyuter yaxshi
            ishlayaptimi?".  Qizigan yoki diski to'lgan kompyuterni u
            O'ZI hal qila oladi (chang tozalash, joyini almashtirish) —
            biz aytmasak esa hech qachon bilmaydi.
            Har qator faqat o'lchov bo'lsa chiziladi. */}
        {device ? <Card>
          <div className="card-head">
            <div><h2>{t("panel.home.device.title")}</h2><p>{t("panel.home.device.subtitle")}</p></div>
            {device.hot ? <Pill state="offline">{t("panel.home.device.hot")}</Pill> : null}
          </div>
          <div className="card-body">
            {device.hot ? <div className="alert-strip">{t("panel.home.device.hot_detail")}</div> : null}
            {typeof device.cpu_percent === "number" ? <div className="simple-row"><span>{t("panel.home.device.cpu")}</span><b>{device.cpu_percent.toFixed(0)}%</b></div> : null}
            {typeof device.ram_percent === "number" ? <div className="simple-row"><span>{t("panel.home.device.ram")}</span><b>{device.ram_percent.toFixed(0)}%</b></div> : null}
            {typeof device.disk_percent === "number" ? <div className="simple-row"><span>{t("panel.home.device.disk")}</span><b>{device.disk_percent.toFixed(0)}%</b></div> : null}
            {typeof device.free_disk_gb === "number" ? <div className="simple-row"><span>{t("panel.home.device.free")}</span><b>{device.free_disk_gb.toFixed(1)} GB</b></div> : null}
            {typeof device.temperature_c === "number" ? <div className="simple-row"><span>{t("panel.home.device.temperature")}</span><b className={device.hot ? "is-hot" : undefined}>{device.temperature_c.toFixed(0)}°C</b></div> : null}
            {device.app_version ? <div className="simple-row"><span>{t("panel.home.device.version")}</span><b>v{device.app_version}</b></div> : null}
          </div>
        </Card> : null}

        <Card>
          <div className="card-head">
            <div><h2>{t("panel.home.telegram.title")}</h2><p>{t("panel.home.telegram.subtitle")}</p></div>
            {members == null ? <Icon name="telegram" /> : <Pill state={members ? "active" : "pending"}>{t(members ? "panel.home.telegram.connected" : "panel.home.telegram.not_connected")}</Pill>}
          </div>
          <div className="card-body">
            {members ? <div className="simple-row"><span>{t("panel.home.telegram.recipients")}</span><b>{t("panel.common.people_count", { count: formatNumber(members) })}</b></div> : null}
            <p className="metric-note">{t("panel.home.telegram.detail")}</p>
            <div className="page-actions">
              <button className="btn btn-wide" onClick={() => onNavigate("settings", "telegram")}>{t(members ? "panel.home.telegram.open_settings" : "panel.home.telegram.connect")}</button>
              {botUrl ? <a className="btn" href={botUrl} target="_blank" rel="noreferrer">{t("panel.home.telegram.open_bot")}</a> : null}
            </div>
          </div>
        </Card>
      </div>
    </div>
  </>;
}
