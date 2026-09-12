import { useEffect, useMemo, useState } from "react";
import { api, formatMoney, formatNumber, formatTimeUz } from "./api";
import { Avatar, Card, EmptyState, Pill, StatCard, StatusDot } from "./components";
import { Percent } from "./admin";
import { Bars, Donut, LineChart, type Point, type Segment } from "./charts";
import { Icon } from "./icons";
import { t } from "./i18n";

/* "Platforma boshqaruvi" — admin bosh ekrani.
 *
 * Namunada har kartada kichik tendensiya chizig'i va oylik o'zgarish
 * bor.  Server hozircha VAQT SERIYASINI bermaydi (`/admin/dashboard`
 * faqat joriy hisoblagichlarni qaytaradi), shuning uchun bu kartalar
 * sparkline'siz chiziladi — o'ylab topilgan grafik ko'rsatishdan
 * ko'ra yo'qligi halolroq.  Kerakli maydonlar "backend keyin"
 * ro'yxatida.
 *
 * Hodisalar bo'yicha grafik esa HAQIQIY: u `/admin/events` dan
 * kelgan yozuvlarni kunlarga guruhlaydi. */

type AdminEvent = { event_id?: string; id?: string; event_type: string; label?: string; site_name?: string; camera_id?: string; occurred_at?: string };
type AdminInvoice = { id: string; site_name?: string; site_id: string; months: number; amount_uzs: number; state: string; provider?: string; created_at?: string; paid_at?: string };
type Account = { id: string; username: string; full_name?: string; role: string; status: string; company?: string; site_id?: string };

/* Akkaunt holati a'zoning tilida.  Server inglizcha KOD qaytaradi va u
   panelga to'g'ridan-to'g'ri chiqib qolgan edi ("pending").  Yorliq
   matn emas, katalog kaliti: modul yuklanganda til hali tanlanmagan
   (`admin.tsx: NAV_ITEMS` izohiga qarang). */
const ACCOUNT_STATUS_KEY: Record<string, string> = {
  active: "panel.admin.account_status.active",
  pending: "panel.admin.account_status.pending",
  suspended: "panel.admin.account_status.suspended",
  blocked: "panel.admin.account_status.blocked",
};

const EVENT_WINDOW_DAYS = 7;
//: Bitta so'rovda olinadigan hodisa chegarasi.  Undan ko'p bo'lsa
//: grafik "oxirgi N hodisa" bo'ladi — buni foydalanuvchiga aytamiz.
const EVENT_LIMIT = 500;

function dayKey(value?: string) {
  return value ? String(value).slice(0, 10) : "";
}

function lastDays(count: number) {
  const days: string[] = [];
  const now = new Date();
  for (let index = count - 1; index >= 0; index -= 1) {
    const day = new Date(now);
    day.setDate(now.getDate() - index);
    days.push(day.toISOString().slice(0, 10));
  }
  return days;
}

function average(values: (number | null | undefined)[]) {
  const known = values.filter((value): value is number => typeof value === "number");
  return known.length ? known.reduce((sum, value) => sum + value, 0) / known.length : null;
}

export function AdminHome({ data, onNavigate }: {
  data: {
    stats: { total_sites: number; active: number; total_devices: number; monthly_revenue_uzs: number; offline: number; not_paired: number; expiring_soon: number; by_connection?: Record<string, number> };
    sites: { id: string; name: string; cameras_active?: number; cameras_expected?: number }[];
    telemetry: { cpu_percent?: number | null; npu_percent?: number | null; inference_latency_ms?: number | null; uptime_sec?: number | null }[];
    server?: { cpu_percent?: number; ram_percent?: number; disk_percent?: number; free_disk_gb?: number; load_1m?: number; cores?: number; temperature_c?: number };
  };
  onNavigate: (id: string) => void;
}) {
  const [events, setEvents] = useState<AdminEvent[] | null>(null);
  const [invoices, setInvoices] = useState<AdminInvoice[] | null>(null);
  const [accounts, setAccounts] = useState<Account[] | null>(null);

  useEffect(() => {
    let stopped = false;
    api<{ events: AdminEvent[] }>(`/api/v1/admin/events?limit=${EVENT_LIMIT}`, "admin")
      .then(result => { if (!stopped) setEvents(result.events || []); })
      .catch(() => { if (!stopped) setEvents([]); });
    api<AdminInvoice[]>("/api/v1/admin/invoices", "admin")
      .then(result => { if (!stopped) setInvoices(result || []); })
      .catch(() => { if (!stopped) setInvoices([]); });
    api<{ accounts: Account[] }>("/api/v1/admin/accounts", "admin")
      .then(result => { if (!stopped) setAccounts(result.accounts || []); })
      .catch(() => { if (!stopped) setAccounts([]); });
    return () => { stopped = true; };
  }, []);

  const stats = data.stats;
  const server = data.server;
  const cameras = data.sites.reduce(
    (sum, site) => ({ active: sum.active + (site.cameras_active || 0), expected: sum.expected + (site.cameras_expected || 0) }),
    { active: 0, expected: 0 },
  );

  const eventDays = useMemo(() => {
    const days = lastDays(EVENT_WINDOW_DAYS);
    const counts = new Map(days.map(day => [day, 0]));
    (events || []).forEach(item => {
      const key = dayKey(item.occurred_at);
      if (counts.has(key)) counts.set(key, (counts.get(key) || 0) + 1);
    });
    return days.map<Point>(day => ({ label: day.slice(5), value: counts.get(day) || 0 }));
  }, [events]);

  const eventsToday = eventDays.length ? eventDays[eventDays.length - 1].value : 0;

  const connectionSegments: Segment[] = Object.entries(stats.by_connection || {}).map(([state, count]) => ({
    label: t(state === "online" ? "panel.admin.conn.online_plain" : state === "stale" ? "panel.admin.conn.stale_long" : state === "not_paired" ? "panel.admin.conn.not_paired" : "panel.admin.conn.offline"),
    value: Number(count) || 0,
    tone: state === "online" ? "green" : state === "stale" ? "yellow" : "red",
  }));

  const cpu = average(data.telemetry.map(item => item.cpu_percent));
  const npu = average(data.telemetry.map(item => item.npu_percent));
  const latency = average(data.telemetry.map(item => item.inference_latency_ms));
  const uptime = average(data.telemetry.map(item => item.uptime_sec));

  // To'lovlar: joriy oyning kunlari bo'yicha tasdiqlangan summalar.
  const paymentBars = useMemo(() => {
    if (!invoices) return [];
    const month = new Date().toISOString().slice(0, 7);
    const perDay = new Map<string, number>();
    invoices.filter(item => item.state === "paid" && dayKey(item.paid_at).startsWith(month)).forEach(item => {
      const key = dayKey(item.paid_at).slice(8);
      perDay.set(key, (perDay.get(key) || 0) + (item.amount_uzs || 0));
    });
    return [...perDay.entries()].sort(([a], [b]) => a.localeCompare(b)).map<Point>(([day, sum]) => ({ label: day, value: Math.round(sum / 1000) }));
  }, [invoices]);

  const paid = (invoices || []).filter(item => item.state === "paid");
  const pending = (invoices || []).filter(item => item.state === "pending");
  const paidSum = paid.reduce((sum, item) => sum + (item.amount_uzs || 0), 0);
  const pendingSum = pending.reduce((sum, item) => sum + (item.amount_uzs || 0), 0);
  const successRate = paid.length + pending.length ? Math.round((paid.length * 100) / (paid.length + pending.length)) : null;

  const team = (accounts || []).filter(account => account.role !== "customer").slice(0, 6);
  const problems = (stats.offline || 0) + (stats.not_paired || 0);

  return <>
    {problems ? <div className="alert-strip alert-info">
      <Icon name="bell" />
      <div><strong>{t("panel.admin.home.attention", { count: problems })}</strong> {t("panel.admin.home.attention_detail", { offline: stats.offline || 0, not_paired: stats.not_paired || 0 })}</div>
    </div> : null}

    <div className="metric-grid metric-grid-6">
      <StatCard label={t("panel.admin.home.stat_active")} value={formatNumber(stats.active)} note={t("panel.admin.home.stat_active_note", { count: formatNumber(stats.total_sites) })} icon="users" tone="blue" />
      <StatCard label={t("panel.nav.branches")} value={formatNumber(stats.total_sites)} note={t("panel.admin.home.stat_branches_note")} icon="branch" tone="blue" />
      <StatCard label={t("panel.admin.home.stat_cameras")} value={`${formatNumber(cameras.active)} / ${formatNumber(cameras.expected)}`} note={t("panel.admin.home.stat_cameras_note")} icon="camera" tone={cameras.active >= cameras.expected ? "green" : "yellow"} />
      <StatCard label={t("panel.admin.home.stat_devices")} value={formatNumber(stats.total_devices)} note={t("panel.admin.home.stat_devices_note", { count: formatNumber(stats.offline) })} icon="server" tone={stats.offline ? "red" : "green"} />
      <StatCard label={t("panel.admin.home.stat_revenue")} value={formatMoney(stats.monthly_revenue_uzs)} note={t("panel.admin.home.stat_revenue_note")} icon="invoice" tone="green" />
      <StatCard label={t("panel.admin.home.stat_events")} value={formatNumber(eventsToday)} note={t("panel.admin.home.stat_events_note")} icon="pulse" tone="blue" />
    </div>

    <div className="home-grid">
      <div className="stack">
        <Card>
          <div className="card-head">
            <div><h2>{t("panel.admin.home.activity_title")}</h2><p>{t("panel.admin.home.activity_subtitle", { days: EVENT_WINDOW_DAYS })}</p></div>
            <button className="btn" onClick={() => onNavigate("events")}>{t("panel.admin.home.events_button")}</button>
          </div>
          {events === null
            ? <div className="card-body"><div className="skeleton" style={{ height: 190 }} /></div>
            : eventDays.some(point => point.value > 0)
              ? <>
                  <LineChart series={[{ name: t("panel.admin.home.events_button"), points: eventDays }]} />
                  {events.length >= EVENT_LIMIT ? <p className="metric-note">{t("panel.admin.home.limit_note", { count: EVENT_LIMIT })}</p> : null}
                </>
              : <EmptyState icon="pulse" title={t("panel.admin.home.events_empty_title")} detail={t("panel.admin.home.events_empty_detail")} />}
        </Card>

        <div className="split-grid">
          <Card>
            <div className="card-head"><div><h2>{t("panel.admin.home.systems_title")}</h2><p>{t("panel.admin.home.systems_subtitle")}</p></div></div>
            {connectionSegments.some(segment => segment.value > 0)
              ? <Donut segments={connectionSegments} centerValue={formatNumber(stats.total_sites)} centerLabel={t("panel.admin.home.systems_center")} />
              : <EmptyState icon="server" title={t("panel.admin.section.empty_title")} detail={t("panel.admin.home.systems_empty_detail")} />}
          </Card>

          <Card>
            <div className="card-head"><div><h2>{t("panel.admin.home.resources_title")}</h2><p>{t("panel.admin.home.resources_subtitle")}</p></div></div>
            <div className="mini-metrics">
              <div><span>CPU</span><b>{cpu == null ? "—" : `${cpu.toFixed(0)}%`}</b></div>
              <div><span>NPU</span><b>{npu == null ? "—" : `${npu.toFixed(0)}%`}</b></div>
              <div><span>{t("panel.admin.home.latency")}</span><b>{latency == null ? "—" : `${latency.toFixed(0)} ms`}</b></div>
              <div><span>{t("panel.admin.home.uptime")}</span><b>{uptime == null ? "—" : t("panel.common.days_count", { count: Math.floor(uptime / 86400) })}</b></div>
            </div>
            <p className="metric-note">{t("panel.admin.home.resources_note")}</p>
          </Card>
        </div>

        <Card>
          <div className="card-head">
            <div><h2>{t("panel.admin.home.payments_title")}</h2><p>{t("panel.admin.home.payments_subtitle")}</p></div>
            <button className="btn" onClick={() => onNavigate("payments")}>{t("panel.admin.home.invoices_button")}</button>
          </div>
          {invoices === null
            ? <div className="card-body"><div className="skeleton" style={{ height: 120 }} /></div>
            : <>
                {paymentBars.length ? <Bars items={paymentBars} /> : <EmptyState icon="invoice" title={t("panel.admin.home.payments_empty_title")} detail={t("panel.admin.home.payments_empty_detail")} />}
                <div className="summary-strip">
                  <div><span>{t("panel.admin.home.pending")}</span><b>{formatMoney(pendingSum)}</b></div>
                  <div><span>{t("panel.admin.home.collected")}</span><b>{formatMoney(paidSum)}</b></div>
                  <div><span>{t("panel.admin.home.invoices")}</span><b>{formatNumber(paid.length + pending.length)}</b></div>
                  <div><span>{t("panel.admin.home.success")}</span><b>{successRate == null ? "—" : `${successRate}%`}</b></div>
                </div>
              </>}
        </Card>
      </div>

      <div className="stack">
        <Card>
          <div className="card-head"><div><h2>{t("panel.admin.home.top_events_title")}</h2><p>{t("panel.admin.home.top_events_subtitle")}</p></div><button className="btn btn-icon" aria-label={t("panel.admin.home.all_aria")} onClick={() => onNavigate("events")}><Icon name="pulse" /></button></div>
          {events === null
            ? <div className="card-body"><div className="skeleton" style={{ height: 150 }} /></div>
            : events.length
              ? <div className="event-list">
                  {events.slice(0, 6).map((item, index) => <div className="event-row" key={item.event_id || item.id || index}>
                    <div className="event-name">
                      <StatusDot state={item.event_type?.startsWith("camera") || item.event_type?.includes("offline") ? "offline" : "online"} />
                      <div><b>{item.label || item.event_type}</b><small>{item.site_name || "—"} · {item.camera_id || t("panel.admin.home.system")}</small></div>
                    </div>
                    <span className="list-value">{formatTimeUz(item.occurred_at)}</span>
                  </div>)}
                </div>
              : <EmptyState icon="pulse" title={t("panel.admin.home.event_empty_title")} detail={t("panel.admin.home.event_empty_detail")} />}
        </Card>

        <Card>
          <div className="card-head"><div><h2>{t("panel.admin.home.ops_title")}</h2><p>{t("panel.admin.home.ops_subtitle")}</p></div></div>
          <div className="simple-list">
            <div className="simple-row"><span>{t("panel.admin.home.not_paired")}</span><b>{stats.not_paired || 0}</b></div>
            <div className="simple-row"><span>{t("panel.admin.home.offline_sites")}</span><b>{stats.offline || 0}</b></div>
            <div className="simple-row"><span>{t("panel.admin.home.expiring")}</span><b>{stats.expiring_soon || 0}</b></div>
          </div>
        </Card>

        {/* Serverning O'ZI.  Mijoz qurilmalari yashil bo'lib turib,
            VPS xotirasi tugab qolishi mumkin — o'shanda panel
            sekinlashadi va hodisalar kechikadi.  Har qator FAQAT
            o'lchov bo'lsa chiziladi: "0%" yozish yolg'on bo'lardi. */}
        {server && Object.keys(server).length ? <Card>
          <div className="card-head"><div><h2>{t("panel.admin.home.server_title")}</h2><p>{t("panel.admin.home.server_subtitle")}</p></div></div>
          <div className="telemetry-grid">
            {typeof server.cpu_percent === "number" ? <div className="telemetry"><span>{t("panel.admin.home.cpu")}</span><Percent value={server.cpu_percent} /></div> : null}
            {typeof server.ram_percent === "number" ? <div className="telemetry"><span>{t("panel.admin.home.ram")}</span><Percent value={server.ram_percent} /></div> : null}
            {typeof server.disk_percent === "number" ? <div className="telemetry"><span>{t("panel.admin.telemetry.disk")}</span><Percent value={server.disk_percent} /></div> : null}
          </div>
          <div className="simple-list">
            {typeof server.load_1m === "number" ? <div className="simple-row"><span>{t("panel.admin.home.load")}</span><b>{server.load_1m.toFixed(2)}{server.cores ? ` / ${t("panel.admin.home.cores", { count: server.cores })}` : ""}</b></div> : null}
            {typeof server.free_disk_gb === "number" ? <div className="simple-row"><span>{t("panel.admin.home.free_space")}</span><b>{server.free_disk_gb.toFixed(1)} GB</b></div> : null}
            {typeof server.temperature_c === "number" ? <div className="simple-row"><span>{t("panel.admin.telemetry.temperature")}</span><b className={server.temperature_c >= 80 ? "is-hot" : undefined}>{server.temperature_c.toFixed(0)}°C</b></div> : null}
          </div>
        </Card> : null}

        {team.length ? <Card>
          <div className="card-head"><div><h2>{t("panel.admin.home.team_title")}</h2><p>{t("panel.admin.home.team_subtitle")}</p></div><button className="btn btn-icon" aria-label={t("panel.admin.home.roles_aria")} onClick={() => onNavigate("roles")}><Icon name="shield" /></button></div>
          <div className="team-row">
            {team.map(account => <div className="team-member" key={account.id}>
              <Avatar name={account.full_name || account.username} />
              <b>{(account.full_name || account.username).split(" ")[0]}</b>
              <small>{account.role === "admin" ? t("panel.admin.role.admin") : account.role === "installer" ? t("panel.admin.role.installer") : account.role}</small>
              <Pill state={account.status}>{ACCOUNT_STATUS_KEY[account.status] ? t(ACCOUNT_STATUS_KEY[account.status]) : account.status}</Pill>
            </div>)}
          </div>
        </Card> : null}
      </div>
    </div>
  </>;
}
