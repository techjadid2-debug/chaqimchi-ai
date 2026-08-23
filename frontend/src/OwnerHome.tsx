import { useEffect, useState } from "react";
import { api, formatDateShort, formatMoney, formatNumber, relativeMinutes, telegramBotUrl } from "./api";
import { Avatar, Card, EmptyState, Pill, StatCard, StatusDot } from "./components";
import { LineChart, type Point } from "./charts";
import { Icon } from "./icons";
import type { Dashboard, Site } from "./types";

/* "Bugungi nazorat" — do'kon egasining yagona ekrani.
 *
 * Namunadagi tartib ataylab: yuqorida bugungi beshta raqam, ostida
 * jonli kadrlar va AI hodisalari, keyin oqim/zonalar, pastda xodim,
 * filial, tarif va Telegram.  Egasi panelni kuniga bir necha marta
 * telefondan ochadi va unga "hammasi joyidami?" degan savolga javob
 * kerak — bo'limlar bo'ylab yurish emas.
 *
 * Ma'lumot bitta so'rovdan (`/api/v1/owner/dashboard`) keladi.  Server
 * bermaydigan ko'rsatkich UMUMAN chizilmaydi: yolg'on nol yoki bo'sh
 * grafik "tizim ishlamayapti" degan taassurot qoldiradi. */

type AttendanceRow = {
  employee_id: string;
  employee_name: string;
  external_id?: string | null;
  first_seen?: string | null;
  status: string;
};

const ATTENDANCE_LABEL: Record<string, { text: string; tone: string }> = {
  present: { text: "Ishda", tone: "online" },
  late: { text: "Kechikdi", tone: "stale" },
  absent: { text: "Kelmadi", tone: "offline" },
  early_leave: { text: "Erta ketdi", tone: "stale" },
  unscheduled: { text: "Rejada yo‘q", tone: "" },
};

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
  onNavigate: (id: string) => void;
  cameras: React.ReactNode;
}) {
  const today = dashboard.today as Record<string, unknown>;
  const traffic = (today.traffic || {}) as Record<string, unknown>;
  const hourly = Array.isArray(traffic.hourly) ? (traffic.hourly as { hour: number; entered: number }[]) : [];
  const attendance = useAttendance(siteId);
  const members = useTelegramMembers(siteId);

  const entered = num(traffic, "entered");
  const changePercent = num(traffic, "change_percent");
  const security = (today.security || {}) as Record<string, number>;
  const alerts = Object.values(security).reduce((sum, value) => sum + (Number(value) || 0), 0) + (num(today, "queue.alerts") || 0);

  // O'rtacha to'xtash — zonalar bo'yicha o'lchangan o'rtacha.
  const dwellZones = Array.isArray(today.dwell) ? (today.dwell as { count: number; average_sec: number }[]) : [];
  const dwellTotal = dwellZones.reduce((sum, zone) => sum + (zone.count || 0), 0);
  const dwellAverage = dwellTotal
    ? dwellZones.reduce((sum, zone) => sum + (zone.average_sec || 0) * (zone.count || 0), 0) / dwellTotal
    : null;

  const onDuty = attendance.rows?.filter(row => row.status === "present" || row.status === "late").length;
  const scheduled = attendance.rows?.filter(row => row.status !== "unscheduled").length;

  const flowPoints: Point[] = hourly.map(item => ({ label: `${String(item.hour).padStart(2, "0")}:00`, value: Number(item.entered) || 0 }));
  const connection = dashboard.site.connection;
  const botUrl = telegramBotUrl();

  return <>
    {connection !== "online" ? <div className={`alert-strip ${connection === "stale" ? "alert-info" : "alert-warning"}`}>
      <Icon name="bell" />
      <div><strong>Aloqa {connection === "stale" ? "yangilanmoqda" : "uzilgan"}.</strong> Oxirgi aloqa: {relativeMinutes(dashboard.site.minutes_since_seen)}. Yangi ma’lumot kelguncha oxirgi tasdiqlangan raqamlar ko‘rsatiladi.</div>
    </div> : null}

    <div className="metric-grid metric-grid-5">
      <StatCard
        label="Tashrif buyuruvchilar"
        value={formatNumber(entered)}
        icon="users"
        tone="blue"
        series={hourly.map(item => Number(item.entered) || 0)}
        deltaPercent={changePercent}
        deltaNote="kechagiga nisbatan"
      />
      <StatCard
        label="Faol kameralar"
        value={`${formatNumber(dashboard.site.cameras_active)} / ${formatNumber(dashboard.site.cameras_expected)}`}
        note={connection === "online" ? "Onlayn" : "Oxirgi ma’lumot"}
        icon="camera"
        tone={connection === "online" ? "green" : "red"}
      />
      {attendance.available && attendance.rows ? <StatCard
        label="Xodimlar ishda"
        value={`${formatNumber(onDuty)} / ${formatNumber(scheduled)}`}
        note="Bugungi jadval bo‘yicha"
        icon="users"
        tone="green"
      /> : null}
      <StatCard
        label="AI ogohlantirishlar"
        value={formatNumber(alerts)}
        note={alerts ? "Bugun qayd etilgan" : "Muammo qayd etilmadi"}
        icon="bell"
        tone={alerts ? "red" : "green"}
      />
      {dwellAverage ? <StatCard
        label="O‘rtacha to‘xtash"
        value={String(asDuration(dwellAverage))}
        note="Kuzatilayotgan zonalarda"
        icon="clock"
        tone="yellow"
      /> : null}
    </div>

    <div className="home-grid">
      <div className="stack">
        {cameras}

        <div className="split-grid">
          <Card>
            <div className="card-head">
              <div><h2>Mijozlar oqimi</h2><p>Bugun, soat bo‘yicha</p></div>
              <button className="btn" onClick={() => onNavigate("traffic")}>Batafsil</button>
            </div>
            {flowPoints.some(point => point.value > 0)
              ? <LineChart series={[{ name: "Tashriflar", points: flowPoints }]} />
              : <EmptyState icon="chart" title="Bugun hali tashrif yo‘q" detail="Kamera birinchi kirishni qayd qilgach grafik shu yerda to‘ladi." />}
          </Card>

          <Card>
            <div className="card-head">
              <div><h2>Faol zonalar</h2><p>Mijozlar ko‘p to‘plangan joylar</p></div>
              <button className="btn" onClick={() => onNavigate("heatmap")}>Xarita</button>
            </div>
            {dwellZones.length ? <div className="zone-list">
              {dwellZones.slice(0, 5).map(zone => {
                const item = zone as unknown as { zone: string; count: number; average_sec: number };
                const peak = Math.max(...dwellZones.map(entry => entry.count || 0), 1);
                return <div className="zone-row" key={item.zone}>
                  <div className="zone-name"><b>{item.zone}</b><small>{asDuration(item.average_sec)} o‘rtacha</small></div>
                  <div className="zone-bar"><i style={{ width: `${Math.max(6, ((item.count || 0) / peak) * 100)}%` }} /></div>
                  <span className="list-value">{formatNumber(item.count)}</span>
                </div>;
              })}
            </div> : <EmptyState icon="heat" title="Zona belgilanmagan" detail="O‘rnatuvchi zona chizgach, mijozlar qancha turgani shu yerda ko‘rinadi." />}
          </Card>
        </div>

        <Card>
          <div className="card-head"><div><h2>Filiallar ko‘rsatkichlari</h2><p>Aloqa va kamera holati</p></div><button className="btn" onClick={() => onNavigate("branches")}>Barchasi</button></div>
          <div className="table-wrap">
            <table>
              <thead><tr><th>Filial</th><th>Kameralar</th><th>Aloqa</th></tr></thead>
              <tbody>
                {sites.map(site => <tr key={site.id}>
                  <td><div className="table-title">{site.name}{site.id === siteId ? <span className="chip-self">Siz</span> : null}</div><small>{site.address || "Manzil kiritilmagan"}</small></td>
                  <td>{formatNumber(site.cameras_active)} / {formatNumber(site.cameras_expected)}</td>
                  <td><Pill state={site.connection}>{site.connection === "online" ? "Onlayn" : site.connection === "stale" ? "Eskirgan" : "Oflayn"}</Pill></td>
                </tr>)}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      <div className="stack">
        <Card>
          <div className="card-head"><div><h2>AI hodisalari</h2><p>So‘nggi qayd etilganlar</p></div><button className="btn btn-icon" aria-label="Barchasini ko‘rish" onClick={() => onNavigate("alerts")}><Icon name="bell" /></button></div>
          {dashboard.events.length ? <>
            <div className="event-list">
              {dashboard.events.slice(0, 6).map((item, index) => <div className="event-row" key={item.id || index}>
                <div className="event-name">
                  <StatusDot state={item.event_type?.startsWith("camera") ? "offline" : "online"} />
                  <div><b>{item.label || item.event_type}</b><small>{item.camera_id || "Tizim"}</small></div>
                </div>
                <span className="list-value">{String(item.occurred_at || item.created_at || "").slice(11, 16) || "—"}</span>
              </div>)}
            </div>
            <button className="btn btn-wide" onClick={() => onNavigate("alerts")}>Barchasini ko‘rish</button>
          </> : <EmptyState icon="shield" title="Yangi hodisa yo‘q" detail="Bu yaxshi belgi. Tizim yangi muhim holatni shu yerda ko‘rsatadi." />}
        </Card>

        {attendance.available && attendance.rows?.length ? <Card>
          <div className="card-head"><div><h2>Xodimlar ish rejimi</h2><p>Bugungi davomat</p></div><button className="btn btn-icon" aria-label="Xodimlar" onClick={() => onNavigate("employees")}><Icon name="users" /></button></div>
          <div className="staff-list">
            {attendance.rows.slice(0, 8).map(row => {
              const label = ATTENDANCE_LABEL[row.status] || { text: row.status, tone: "" };
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
          <div className="card-head"><div><h2>Joriy tarif</h2><p>{dashboard.subscription?.status === "active" ? "Obuna faol" : "Holatni tekshiring"}</p></div><Pill state={dashboard.subscription?.status}>{dashboard.site.plan?.name || "Tarif"}</Pill></div>
          <div className="card-body">
            <div className="simple-row"><span>Oylik to‘lov</span><b>{formatMoney(dashboard.subscription?.monthly_price_uzs)}</b></div>
            {dashboard.subscription?.subscription_until
              ? <div className="simple-row"><span>Faol muddat</span><b>{formatDateShort(dashboard.subscription.subscription_until)} gacha</b></div>
              : null}
            <div className="simple-row"><span>Kameralar</span><b>{formatNumber(dashboard.site.cameras_expected)} tagacha</b></div>
            <button className="btn btn-wide" onClick={() => onNavigate("billing")}>Tarifni boshqarish</button>
          </div>
        </Card>

        <Card>
          <div className="card-head">
            <div><h2>Telegram bot</h2><p>Ogohlantirishlar shu yerga keladi</p></div>
            {members == null ? <Icon name="telegram" /> : <Pill state={members ? "active" : "pending"}>{members ? "Ulangan" : "Ulanmagan"}</Pill>}
          </div>
          <div className="card-body">
            {members ? <div className="simple-row"><span>Xabar oluvchilar</span><b>{formatNumber(members)} ta</b></div> : null}
            <p className="metric-note">Muhim kamera va tizim holatlari, kunlik xulosa hamda panel havolasi botga yuboriladi.</p>
            <div className="page-actions">
              <button className="btn btn-wide" onClick={() => onNavigate("telegram")}>{members ? "Sozlamalarni ochish" : "Telegramga ulash"}</button>
              {botUrl ? <a className="btn" href={botUrl} target="_blank" rel="noreferrer">Botni ochish</a> : null}
            </div>
          </div>
        </Card>
      </div>
    </div>
  </>;
}
