import { useEffect, useState } from "react";
import { api, formatNumber, hasFeature } from "./api";
import { Card, EmptyState, PlanLock } from "./components";
import { t } from "./i18n";
import type { Dashboard, Demografiya } from "./types";

/* "Mijoz portreti" — do'konga kirganlarning anonim jins va yosh
 * yig'indisi.
 *
 * Ma'lumot qayerdan keladi: qurilma odam kirish chizig'ini kesib
 * o'tganda BIR MARTA taxminiy yosh va jinsni baholaydi va uni
 * `line_crossed` hodisasining metadatasiga qo'shadi.  Rasm ham,
 * yuz namunasi ham saqlanmaydi va yuborilmaydi — mijoz tanilmaydi
 * va uning ikkinchi tashrifi birinchisi bilan bog'lanmaydi.
 *
 * IKKI MANBA, bitta karta:
 *
 * * **Bugun** — `dashboard.today.demografiya`, xom hodisalardan
 *   jonli hisoblanadi (kun hali tugamagan);
 * * **hafta / oy / yil** — `/api/v1/owner/demography`, kunlik
 *   yig'indi jadvalidan.  Xom hodisalar tarif muddatida o'chiriladi,
 *   ya'ni o'tgan oy yoki yil ular bilan umuman hisoblanmasdi.
 *
 * Bugungi kun yig'indi jadvaliga KIRMAYDI — aks holda bir xil kun
 * ikki manbadan ikki xil ko'rinardi. */

/** Guruh tartibi YOSH bo'yicha qotirilgan.
 *
 * Songa qarab saralansa ustunlar har kuni joyini almashtirardi va
 * o'q o'z ma'nosini yo'qotardi: «18-30» bugun birinchi, ertaga
 * uchinchi bo'lib turardi. */
const AGE_ORDER = ["<18", "18-30", "31-45", "46-60", "60+"];

/** `<18` do'kon egasi uchun so'z bilan.
 *
 * 0-12 va 13-17 ga ATAYLAB bo'linmaydi: model yoshni ~7 yil xato
 * bilan baholaydi, ya'ni bunday bo'linish aniqdek ko'rinib,
 * ishonchsiz bo'lardi. */
function ageLabel(key: string): string {
  if (key === "<18") return t("panel.demo.age.under18");
  if (key === "60+") return t("panel.demo.age.over60");
  return t("panel.demo.age.range", { range: key });
}

/* Matn kalitda, chizishda `t()` bilan ochiladi: modul yuklanganda til
   hali tanlanmagan bo'ladi (`initLang` keyin chaqiriladi), ya'ni shu
   yerda `t()` chaqirilsa doim o'zbekcha qolardi. */
const PERIODS: { id: string; label: string; days: number }[] = [
  { id: "today", label: "panel.common.today", days: 0 },
  { id: "week", label: "panel.common.week", days: 7 },
  { id: "month", label: "panel.common.month", days: 30 },
  { id: "year", label: "panel.demo.period.year", days: 365 },
];

function periodNote(item: { id: string; days: number }): string {
  return item.id === "today" ? t("panel.demo.period.today_note") : t("panel.demo.period.last_days", { count: item.days });
}

type RangeAnswer = Demografiya & { kunlar?: number; mijozli_kunlar?: number; kirgan?: number };

export function Demography({ dashboard, siteId, onNavigate }: {
  dashboard: Dashboard;
  siteId: string;
  onNavigate: (id: string) => void;
}) {
  const open = hasFeature(dashboard, "demografiya");
  const [period, setPeriod] = useState("today");
  const [range, setRange] = useState<RangeAnswer | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open || period === "today") { setRange(null); setError(""); return; }
    let stopped = false;
    setLoading(true);
    api<RangeAnswer>(`/api/v1/owner/demography?period=${period}`, "owner", { siteId })
      .then(answer => { if (!stopped) { setRange(answer); setError(""); } })
      .catch(reason => { if (!stopped) setError(reason instanceof Error ? reason.message : t("panel.demo.load_failed")); })
      .then(() => { if (!stopped) setLoading(false); });
    return () => { stopped = true; };
  }, [open, period, siteId]);

  /* Tarif TEKSHIRUVI birinchi.
   *
   * Boshlang'ich tarifda server kalitni butunlay o'chiradi, ya'ni
   * «tarifda yopiq» ham, «bugun hali hech kim kirmagan» ham bir xil
   * ko'rinadi (`demografiya === undefined`).  Ularni faqat shu
   * tekshiruv ajratadi. */
  if (!open) {
    return <Card>
      <div className="card-head">
        <div><h2>{t("panel.demo.title")}</h2><p>{t("panel.demo.subtitle_today")}</p></div>
      </div>
      <PlanLock
        title={t("panel.demo.lock.title")}
        detail={t("panel.demo.lock.detail")}
        onUpgrade={() => onNavigate("billing")}
      />
    </Card>;
  }

  const active = PERIODS.find(item => item.id === period) || PERIODS[0];
  const data: Demografiya | undefined = period === "today" ? dashboard.today.demografiya : range || undefined;
  const counted = Number(data?.hisoblangan || 0);
  /* Qamrov: portret faqat yuz kameraga ko'ringan kirishlarda yoziladi,
     shuning uchun "kirdi" har doim "portret"dan katta yoki teng.  Ikkalasi
     yonma-yon ko'rsatiladi — aks holda ega "nega kirganlar 128, portret 40?"
     deb tizim buzilgan deb o'ylardi. */
  const entered = period === "today"
    ? Number((dashboard.today.traffic as Record<string, unknown> | undefined)?.entered || 0)
    : Number(range?.kirgan || 0);

  const tabs = <div className="segmented">
    {PERIODS.map(item => (
      <button key={item.id} className={item.id === period ? "active" : ""} onClick={() => setPeriod(item.id)}>
        {t(item.label)}
      </button>
    ))}
  </div>;

  const head = <div className="card-head">
    <div>
      <h2>{t("panel.demo.title")}</h2>
      <p>{counted
        ? t("panel.demo.summary", { entered: formatNumber(entered), counted: formatNumber(counted), note: periodNote(active) })
        : periodNote(active)}</p>
    </div>
    {tabs}
  </div>;

  if (error) {
    return <Card>{head}<EmptyState icon="users" title={t("panel.demo.error_title")} detail={error} /></Card>;
  }
  if (loading && !data) {
    return <Card>{head}<EmptyState icon="users" title={t("panel.demo.loading.title")} detail={t("panel.demo.loading.detail")} /></Card>;
  }
  if (!data || counted <= 0) {
    /* Uch xil "bo'sh"ning uch xil sababi bor va ular egaga TURLICHA
       aytiladi: chiziq chizilmagan (tuzatsa bo'ladi), qurilma oflayn
       (tekshirsin) yoki chindan hali mijoz kirmagan (kutish to'g'ri).
       Avval hammasi "birinchi tashrifni kuting" edi — birinchi ikkisida
       bu hech qachon bajarilmaydigan va'da bo'lardi. */
    const geometry = dashboard.capabilities?.geometry;
    const offline = dashboard.site.connection !== "online";
    const empty = geometry && !geometry.lines_drawn
      ? { title: t("panel.demo.empty.no_line.title"), detail: t("panel.demo.empty.no_line.detail") }
      : offline
        ? { title: t("panel.demo.empty.offline.title"), detail: t("panel.demo.empty.offline.detail") }
        : { title: period === "today" ? t("panel.demo.empty.today.title") : t("panel.demo.empty.period.title"), detail: t("panel.demo.empty.wait.detail") };
    return <Card>
      {head}
      <EmptyState icon="users" title={empty.title} detail={empty.detail} />
    </Card>;
  }

  const ages = data.yosh || {};
  // Nolga bo'linish bo'lmasin: hamma guruh bo'sh bo'lishi mumkin.
  const peak = Math.max(...AGE_ORDER.map(key => Number(ages[key] || 0)), 1);

  return <Card>
    {head}

    <div className="mini-metrics">
      {/* SON birinchi, foiz qavsda — ega "nechtasi" deb so'raydi.
          Eski cloud `jins_soni` bermasa foizning o'zi ko'rinadi. */}
      <div><span>{t("panel.demo.women")}</span><b>{data.jins_soni?.ayol != null
        ? t("panel.demo.count_share", { count: formatNumber(data.jins_soni.ayol), share: Math.round(Number(data.jins?.ayol || 0)) })
        : `${Math.round(Number(data.jins?.ayol || 0))}%`}</b></div>
      <div><span>{t("panel.demo.men")}</span><b>{data.jins_soni?.erkak != null
        ? t("panel.demo.count_share", { count: formatNumber(data.jins_soni.erkak), share: Math.round(Number(data.jins?.erkak || 0)) })
        : `${Math.round(Number(data.jins?.erkak || 0))}%`}</b></div>
      <div><span>{t("panel.demo.children")}</span><b>{t("panel.demo.count_pcs", { count: formatNumber(Number((data.yosh || {})["<18"] || 0)) })}</b></div>
    </div>

    <div className="zone-list">
      {AGE_ORDER.map(key => {
        const count = Number(ages[key] || 0);
        const share = counted ? Math.round((count / counted) * 100) : 0;
        return <div className="zone-row" key={key}>
          <div className="zone-name"><b>{ageLabel(key)}</b><small>{share}%</small></div>
          <div className="zone-bar"><i style={{ width: `${Math.max(6, (count / peak) * 100)}%` }} /></div>
          <span className="list-value">{formatNumber(count)}</span>
        </div>;
      })}
    </div>

    <div className="card-body">
      <p className="metric-note">
        {t("panel.demo.note")}
        {/* Ikki son ataylab: 30 kundan faqat 5 tasida mijoz
            qayd etilgan bo'lsa, qurilma o'sha kunlari ishlamagan —
            va buni do'kon egasi bilishi kerak. */}
        {range?.kunlar
          ? ` ${t("panel.demo.days_with_customers", { days: range.kunlar, with: range.mijozli_kunlar ?? 0 })}`
          : ""}
      </p>
    </div>
  </Card>;
}
