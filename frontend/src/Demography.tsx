import { useEffect, useState } from "react";
import { api, formatNumber, hasFeature } from "./api";
import { Card, EmptyState, PlanLock } from "./components";
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
const AGE_LABEL: Record<string, string> = {
  "<18": "Bolalar va o‘smirlar",
  "18-30": "18-30 yosh",
  "31-45": "31-45 yosh",
  "46-60": "46-60 yosh",
  "60+": "60 dan katta",
};

const PERIODS: { id: string; label: string; note: string }[] = [
  { id: "today", label: "Bugun", note: "bugun kirgan mijozlar" },
  { id: "week", label: "Hafta", note: "oxirgi 7 kun" },
  { id: "month", label: "Oy", note: "oxirgi 30 kun" },
  { id: "year", label: "Yil", note: "oxirgi 365 kun" },
];

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
      .catch(reason => { if (!stopped) setError(reason instanceof Error ? reason.message : "Olinmadi"); })
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
        <div><h2>Mijoz portreti</h2><p>Bugun kirgan mijozlarning anonim tavsifi</p></div>
      </div>
      <PlanLock
        title="Mijoz portreti Biznes tarifida"
        detail="Do‘koningizga kim ko‘proq kelishini ko‘rasiz: yosh guruhi va jins. Baho anonim — rasm saqlanmaydi, yuz tanilmaydi."
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
        {item.label}
      </button>
    ))}
  </div>;

  const head = <div className="card-head">
    <div>
      <h2>Mijoz portreti</h2>
      <p>{counted
        ? `Kirdi: ${formatNumber(entered)} · portret ${formatNumber(counted)} mijozda · ${active.note}`
        : active.note}</p>
    </div>
    {tabs}
  </div>;

  if (error) {
    return <Card>{head}<EmptyState icon="users" title="Ma’lumot olinmadi" detail={error} /></Card>;
  }
  if (loading && !data) {
    return <Card>{head}<EmptyState icon="users" title="Yig‘ilmoqda…" detail="Tanlangan davr uchun raqamlar tayyorlanmoqda." /></Card>;
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
      ? { title: "Portret uchun kirish chizig‘i kerak", detail: "Kirish chizig‘i chizilmagani uchun mijozlar (va ularning yosh-jinsi) sanalmayapti. «Chiziq va zonalar» bo‘limida eshik ustiga chiziq qo‘ying." }
      : offline
        ? { title: "Do‘kon kompyuteri bilan aloqa yo‘q", detail: "Portret do‘kondagi kompyuterda hisoblanadi. Kompyuter yoqilib bulutga ulanganida raqamlar shu yerda paydo bo‘ladi." }
        : { title: period === "today" ? "Bugun hali portret yig‘ilmadi" : "Bu davrda ma’lumot yo‘q", detail: "Mijoz eshikdan kirganda uning taxminiy yoshi va jinsi anonim qayd etiladi. Birinchi tashrifdan keyin shu yerda ko‘rinadi." };
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
      <div><span>Ayollar</span><b>{data.jins_soni?.ayol != null
        ? `${formatNumber(data.jins_soni.ayol)} ta (${Math.round(Number(data.jins?.ayol || 0))}%)`
        : `${Math.round(Number(data.jins?.ayol || 0))}%`}</b></div>
      <div><span>Erkaklar</span><b>{data.jins_soni?.erkak != null
        ? `${formatNumber(data.jins_soni.erkak)} ta (${Math.round(Number(data.jins?.erkak || 0))}%)`
        : `${Math.round(Number(data.jins?.erkak || 0))}%`}</b></div>
      <div><span>Bolalar</span><b>{formatNumber(Number((data.yosh || {})["<18"] || 0))} ta</b></div>
    </div>

    <div className="zone-list">
      {AGE_ORDER.map(key => {
        const count = Number(ages[key] || 0);
        const share = counted ? Math.round((count / counted) * 100) : 0;
        return <div className="zone-row" key={key}>
          <div className="zone-name"><b>{AGE_LABEL[key]}</b><small>{share}%</small></div>
          <div className="zone-bar"><i style={{ width: `${Math.max(6, (count / peak) * 100)}%` }} /></div>
          <span className="list-value">{formatNumber(count)}</span>
        </div>;
      })}
    </div>

    <div className="card-body">
      <p className="metric-note">
        Yosh — taxminiy baho (bolalarda aniqlik pastroq). Xodimlar hisobga kirmaydi.
        Rasm saqlanmaydi va yuborilmaydi. Portret faqat yuzi kameraga ko‘ringan
        kirishlarda yoziladi — shuning uchun u kirganlar sonidan kam bo‘ladi.
        {/* Ikki son ataylab: 30 kundan faqat 5 tasida mijoz
            qayd etilgan bo'lsa, qurilma o'sha kunlari ishlamagan —
            va buni do'kon egasi bilishi kerak. */}
        {range?.kunlar
          ? ` ${range.kunlar} kundan ${range.mijozli_kunlar ?? 0} tasida mijoz qayd etilgan.`
          : ""}
      </p>
    </div>
  </Card>;
}
