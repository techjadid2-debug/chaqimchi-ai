import { formatNumber, hasFeature } from "./api";
import { Card, EmptyState, PlanLock } from "./components";
import type { Dashboard } from "./types";

/* "Mijoz portreti" — do'konga kirganlarning anonim jins va yosh
 * yig'indisi.
 *
 * Ma'lumot qayerdan keladi: qurilma odam kirish chizig'ini kesib
 * o'tganda BIR MARTA taxminiy yosh va jinsni baholaydi va uni
 * `line_crossed` hodisasining metadatasiga qo'shadi.  Rasm ham,
 * yuz namunasi ham saqlanmaydi va yuborilmaydi — mijoz tanilmaydi
 * va uning ikkinchi tashrifi birinchisi bilan bog'lanmaydi.
 *
 * Nega alohida sahifa emas, karta: bu sakkizta raqam va faqat
 * BUGUNGI kun uchun (haftalik dinamika hali yig'ilmaydi).  Alohida
 * sahifa asosan bo'sh joy bo'lardi, yon menyu esa yana bir bandga
 * cho'zilardi. */

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

export function Demography({ dashboard, onNavigate }: {
  dashboard: Dashboard;
  onNavigate: (id: string) => void;
}) {
  const head = <div className="card-head">
    <div><h2>Mijoz portreti</h2><p>Bugun kirgan mijozlarning anonim tavsifi</p></div>
  </div>;

  /* Tarif TEKSHIRUVI birinchi.
   *
   * Boshlang'ich tarifda server kalitni butunlay o'chiradi, ya'ni
   * «tarifda yopiq» ham, «bugun hali hech kim kirmagan» ham bir xil
   * ko'rinadi (`demografiya === undefined`).  Ularni faqat shu
   * tekshiruv ajratadi. */
  if (!hasFeature(dashboard, "demografiya")) {
    return <Card>
      {head}
      <PlanLock
        title="Mijoz portreti Biznes tarifida"
        detail="Do‘koningizga kim ko‘proq kelishini ko‘rasiz: yosh guruhi va jins. Baho anonim — rasm saqlanmaydi, yuz tanilmaydi."
        onUpgrade={() => onNavigate("billing")}
      />
    </Card>;
  }

  const demo = dashboard.today.demografiya;
  const counted = Number(demo?.hisoblangan || 0);
  if (!demo || counted <= 0) {
    return <Card>
      {head}
      <EmptyState
        icon="users"
        title="Bugun hali portret yig‘ilmadi"
        detail="Mijoz eshikdan kirganda uning taxminiy yoshi va jinsi anonim qayd etiladi. Birinchi tashrifdan keyin shu yerda ko‘rinadi."
      />
    </Card>;
  }

  const ages = demo.yosh || {};
  // Nolga bo'linish bo'lmasin: hamma guruh bo'sh bo'lishi mumkin.
  const peak = Math.max(...AGE_ORDER.map(key => Number(ages[key] || 0)), 1);

  return <Card>
    <div className="card-head">
      <div><h2>Mijoz portreti</h2><p>Bugun {formatNumber(counted)} mijoz · anonim baho</p></div>
    </div>

    <div className="mini-metrics">
      <div><span>Ayollar</span><b>{Math.round(Number(demo.jins?.ayol || 0))}%</b></div>
      <div><span>Erkaklar</span><b>{Math.round(Number(demo.jins?.erkak || 0))}%</b></div>
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
        Yosh — taxminiy baho. Xodimlar hisobga kirmaydi. Rasm saqlanmaydi va yuborilmaydi.
      </p>
    </div>
  </Card>;
}
