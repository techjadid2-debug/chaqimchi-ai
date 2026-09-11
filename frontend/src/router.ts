import { useCallback, useEffect, useState } from "react";

/* Panel navigatsiyasi manzil qatoriga bog'lanadi.
 *
 * Ilgari faol bo'lim oddiy `useState` edi: sahifani yangilash bosh
 * sahifaga qaytarardi, "Kameralar" ni hamkasbga havola qilib bo'lmasdi
 * va brauzerning "orqaga" tugmasi panelni butunlay tark etardi.
 *
 * Kutubxona qo'shilmadi — bu yerda kerak bo'lgani `history.pushState`
 * va `popstate`, ya'ni ~40 qator.  Backend `/owner/*` va `/admin/*`
 * yo'llarini o'sha qobiqqa beradi (`cloud/main.py` catch-all), shuning
 * uchun to'g'ridan-to'g'ri ochilgan manzil ham ishlaydi.
 */

/** Dev-serverda sahifa `/assets/v2/owner.html` da turadi — u yerda
 *  `pushState('/owner/cameras')` qilinsa, yangilashda 404 chiqadi.
 *  Shuning uchun manzil bazaga mos kelmasa, hash rejimiga tushamiz. */
function pathMode(base: string) {
  const path = window.location.pathname;
  return path === base || path.startsWith(`${base}/`);
}

/** Eski bo'lim nomi → yangi bo'lim va ichki tab.
 *
 *  Menyu 14 bo'limdan 8 taga qisqarganda (2026-09-10) eski manzillar
 *  Telegram xabarlarida, xatcho'plarda va bot tugmalarida qolib
 *  ketgan.  Ular 404 yoki bosh sahifa emas, aynan o'sha joyni ochsin. */
export type LegacyRoutes = Readonly<Record<string, readonly [string, string]>>;

function readRoute(base: string, ids: readonly string[], fallback: string, legacy: LegacyRoutes = {}): { id: string; param: string; sub: string } {
  const source = pathMode(base)
    ? window.location.pathname.slice(base.length).replace(/^\/+/, "")
    : window.location.hash.replace(/^#\/?/, "");
  const [rawId, param = "", sub = ""] = source.split(/[?#]/)[0].split("/");
  const moved = legacy[rawId];
  const id = moved ? moved[0] : rawId;
  if (!ids.includes(id)) return { id: fallback, param: "", sub: "" };
  if (moved) return { id, param: moved[1], sub: "" };
  // Ikkinchi segment — bo'lim ichidagi obyekt (`customers/<site_id>`).
  // Faqat xavfsiz belgilar: manzil qatoridan kelgan narsa to'g'ridan-
  // to'g'ri API yo'liga qo'yiladi.  Uchinchi segment — obyekt ichidagi
  // tab (`cameras/camera-01/alerts`): faqat kichik harflar.
  return {
    id,
    param: /^[A-Za-z0-9_.-]{1,64}$/.test(param) ? decodeURIComponent(param) : "",
    sub: /^[a-z]{1,16}$/.test(sub) ? sub : "",
  };
}

/** Bo'lim va (ixtiyoriy) obyekt: `/admin/customers/<id>`.
 *
 *  `param` — chuqur havola uchun: «diqqat talab qiladi» ro'yxatidan
 *  mijozga to'g'ridan-to'g'ri o'tiladi va brauzerning Orqasi ishlaydi
 *  (eski admin qoidasi, `#/mijozlar/<id>`). */
export function usePanelRoute(base: string, ids: readonly string[], fallback: string, legacy: LegacyRoutes = {}) {
  const [route, setRoute] = useState(() => readRoute(base, ids, fallback, legacy));
  const active = route.id;
  const param = route.param;
  const sub = route.sub;
  const setActive = (id: string, next = "", nextSub = "") => setRoute({ id, param: next, sub: nextSub });

  useEffect(() => {
    const sync = () => setRoute(readRoute(base, ids, fallback, legacy));
    window.addEventListener("popstate", sync);
    window.addEventListener("hashchange", sync);
    return () => {
      window.removeEventListener("popstate", sync);
      window.removeEventListener("hashchange", sync);
    };
  }, [base, ids, fallback]);

  const navigate = useCallback(
    (target: string, targetParam = "", targetSub = "") => {
      /* Kod ichidagi eski chaqiruvlar (`onNavigate("billing")`) ham
         manzil qatoridagi eski havola bilan bir xil yo'ldan o'tadi —
         xarita bitta, ikki joyda emas. */
      const moved = legacy[target];
      const id = moved ? moved[0] : target;
      const param = moved ? moved[1] : targetParam;
      if (!ids.includes(id)) return;
      const sub = moved ? "" : targetSub;
      setActive(id, param, sub);
      const tail = param ? `/${encodeURIComponent(param)}${sub ? `/${sub}` : ""}` : "";
      if (pathMode(base)) {
        const next = `${id === fallback && !param ? base : `${base}/${id}${tail}`}${window.location.search}`;
        if (next !== window.location.pathname + window.location.search) {
          window.history.pushState({ panel: id, param, sub }, "", next);
        }
      } else if (window.location.hash !== `#/${id}${tail}`) {
        window.history.pushState({ panel: id, param, sub }, "", `#/${id}${tail}`);
      }
    },
    [base, ids, fallback, legacy],
  );

  return [active, navigate, param, sub] as const;
}
