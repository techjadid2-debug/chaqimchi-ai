import { useEffect, useMemo, useState } from "react";
import { api, formatMoney, formatNumber } from "./api";
import { Avatar, Card, EmptyState, Pill, StatCard, StatusDot } from "./components";
import { Bars, Donut, LineChart, type Point, type Segment } from "./charts";
import { Icon } from "./icons";

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

/* Akkaunt holati o'zbekchada.  Server inglizcha kalit qaytaradi va u
   panelga to'g'ridan-to'g'ri chiqib qolgan edi ("pending"). */
const ACCOUNT_STATUS: Record<string, string> = {
  active: "Faol",
  pending: "Tasdiq kutmoqda",
  suspended: "To‘xtatilgan",
  blocked: "Bloklangan",
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
    label: state === "online" ? "Onlayn" : state === "stale" ? "Aloqa eskirgan" : state === "not_paired" ? "Ulanmagan" : "Oflayn",
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
      <div><strong>{problems} ta tizim e’tibor talab qiladi.</strong> {stats.offline || 0} ta oflayn, {stats.not_paired || 0} ta hali qurilmaga ulanmagan.</div>
    </div> : null}

    <div className="metric-grid metric-grid-6">
      <StatCard label="Faol mijozlar" value={formatNumber(stats.active)} note={`${formatNumber(stats.total_sites)} ta jami`} icon="users" tone="blue" />
      <StatCard label="Filiallar" value={formatNumber(stats.total_sites)} note="Ro‘yxatdagi savdo nuqtalari" icon="branch" tone="blue" />
      <StatCard label="Onlayn kameralar" value={`${formatNumber(cameras.active)} / ${formatNumber(cameras.expected)}`} note="Barcha filiallar bo‘yicha" icon="camera" tone={cameras.active >= cameras.expected ? "green" : "yellow"} />
      <StatCard label="Edge qurilmalar" value={formatNumber(stats.total_devices)} note={`${formatNumber(stats.offline)} ta oflayn`} icon="server" tone={stats.offline ? "red" : "green"} />
      <StatCard label="Oylik tushum" value={formatMoney(stats.monthly_revenue_uzs)} note="Faol va grace obunalar" icon="invoice" tone="green" />
      <StatCard label="AI hodisalari" value={formatNumber(eventsToday)} note="Bugun qayd etilgan" icon="pulse" tone="blue" />
    </div>

    <div className="home-grid">
      <div className="stack">
        <Card>
          <div className="card-head">
            <div><h2>Platforma faolligi</h2><p>AI hodisalari, oxirgi {EVENT_WINDOW_DAYS} kun</p></div>
            <button className="btn" onClick={() => onNavigate("events")}>Hodisalar</button>
          </div>
          {events === null
            ? <div className="card-body"><div className="skeleton" style={{ height: 190 }} /></div>
            : eventDays.some(point => point.value > 0)
              ? <>
                  <LineChart series={[{ name: "Hodisalar", points: eventDays }]} />
                  {events.length >= EVENT_LIMIT ? <p className="metric-note">Grafik oxirgi {EVENT_LIMIT} ta hodisa bo‘yicha tuzilgan.</p> : null}
                </>
              : <EmptyState icon="pulse" title="Hodisa qayd etilmadi" detail="Qurilmalar AI hodisa yuborgach kunlik dinamika shu yerda ko‘rinadi." />}
        </Card>

        <div className="split-grid">
          <Card>
            <div className="card-head"><div><h2>Tizimlar holati</h2><p>Aloqa bo‘yicha taqsimot</p></div></div>
            {connectionSegments.some(segment => segment.value > 0)
              ? <Donut segments={connectionSegments} centerValue={formatNumber(stats.total_sites)} centerLabel="tizim" />
              : <EmptyState icon="server" title="Ma’lumot yo‘q" detail="Mijoz tizimlari ulangach taqsimot shu yerda ko‘rinadi." />}
          </Card>

          <Card>
            <div className="card-head"><div><h2>Resurslar</h2><p>Qurilmalar bo‘yicha o‘rtacha</p></div></div>
            <div className="mini-metrics">
              <div><span>CPU</span><b>{cpu == null ? "—" : `${cpu.toFixed(0)}%`}</b></div>
              <div><span>NPU</span><b>{npu == null ? "—" : `${npu.toFixed(0)}%`}</b></div>
              <div><span>Kechikish</span><b>{latency == null ? "—" : `${latency.toFixed(0)} ms`}</b></div>
              <div><span>Ishlash muddati</span><b>{uptime == null ? "—" : `${Math.floor(uptime / 86400)} kun`}</b></div>
            </div>
            <p className="metric-note">Qiymatlar oxirgi heartbeat’lardan olingan. Tarixiy egri chiziq uchun server hali seriya bermaydi.</p>
          </Card>
        </div>

        <Card>
          <div className="card-head">
            <div><h2>To‘lovlar</h2><p>Joriy oy, tasdiqlangan tushum (ming so‘m)</p></div>
            <button className="btn" onClick={() => onNavigate("payments")}>Hisob-fakturalar</button>
          </div>
          {invoices === null
            ? <div className="card-body"><div className="skeleton" style={{ height: 120 }} /></div>
            : <>
                {paymentBars.length ? <Bars items={paymentBars} /> : <EmptyState icon="invoice" title="Bu oyda to‘lov yo‘q" detail="Operator hisobni tasdiqlagach kunlik tushum shu yerda ko‘rinadi." />}
                <div className="summary-strip">
                  <div><span>Kutilayotgan</span><b>{formatMoney(pendingSum)}</b></div>
                  <div><span>Undirilgan</span><b>{formatMoney(paidSum)}</b></div>
                  <div><span>Hisoblar</span><b>{formatNumber(paid.length + pending.length)}</b></div>
                  <div><span>Muvaffaqiyat</span><b>{successRate == null ? "—" : `${successRate}%`}</b></div>
                </div>
              </>}
        </Card>
      </div>

      <div className="stack">
        <Card>
          <div className="card-head"><div><h2>Muhim hodisalar</h2><p>So‘nggi qayd etilganlar</p></div><button className="btn btn-icon" aria-label="Barchasi" onClick={() => onNavigate("events")}><Icon name="pulse" /></button></div>
          {events === null
            ? <div className="card-body"><div className="skeleton" style={{ height: 150 }} /></div>
            : events.length
              ? <div className="event-list">
                  {events.slice(0, 6).map((item, index) => <div className="event-row" key={item.event_id || item.id || index}>
                    <div className="event-name">
                      <StatusDot state={item.event_type?.startsWith("camera") || item.event_type?.includes("offline") ? "offline" : "online"} />
                      <div><b>{item.label || item.event_type}</b><small>{item.site_name || "—"} · {item.camera_id || "Tizim"}</small></div>
                    </div>
                    <span className="list-value">{item.occurred_at ? new Date(item.occurred_at).toLocaleTimeString("uz-UZ", { hour: "2-digit", minute: "2-digit" }) : "—"}</span>
                  </div>)}
                </div>
              : <EmptyState icon="pulse" title="Hodisa yo‘q" detail="Qurilmalar hodisa yuborgach ular shu yerda ko‘rinadi." />}
        </Card>

        <Card>
          <div className="card-head"><div><h2>Operatsion eslatma</h2><p>Navbatdagi ishlar</p></div></div>
          <div className="simple-list">
            <div className="simple-row"><span>Ulanmagan qurilmalar</span><b>{stats.not_paired || 0}</b></div>
            <div className="simple-row"><span>Oflayn mijozlar</span><b>{stats.offline || 0}</b></div>
            <div className="simple-row"><span>Muddati yaqin</span><b>{stats.expiring_soon || 0}</b></div>
          </div>
        </Card>

        {team.length ? <Card>
          <div className="card-head"><div><h2>Jamoa</h2><p>Platforma akkauntlari</p></div><button className="btn btn-icon" aria-label="Rollar" onClick={() => onNavigate("roles")}><Icon name="shield" /></button></div>
          <div className="team-row">
            {team.map(account => <div className="team-member" key={account.id}>
              <Avatar name={account.full_name || account.username} />
              <b>{(account.full_name || account.username).split(" ")[0]}</b>
              <small>{account.role === "admin" ? "Admin" : account.role === "installer" ? "O‘rnatuvchi" : account.role}</small>
              <Pill state={account.status}>{ACCOUNT_STATUS[account.status] || account.status}</Pill>
            </div>)}
          </div>
        </Card> : null}
      </div>
    </div>
  </>;
}
