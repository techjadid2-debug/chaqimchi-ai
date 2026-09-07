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

function readRoute(base: string, ids: readonly string[], fallback: string): { id: string; param: string } {
  const source = pathMode(base)
    ? window.location.pathname.slice(base.length).replace(/^\/+/, "")
    : window.location.hash.replace(/^#\/?/, "");
  const [id, param = ""] = source.split(/[?#]/)[0].split("/");
  if (!ids.includes(id)) return { id: fallback, param: "" };
  // Ikkinchi segment — bo'lim ichidagi obyekt (`customers/<site_id>`).
  // Faqat xavfsiz belgilar: manzil qatoridan kelgan narsa to'g'ridan-
  // to'g'ri API yo'liga qo'yiladi.
  return { id, param: /^[A-Za-z0-9_.-]{1,64}$/.test(param) ? decodeURIComponent(param) : "" };
}

/** Bo'lim va (ixtiyoriy) obyekt: `/admin/customers/<id>`.
 *
 *  `param` — chuqur havola uchun: «diqqat talab qiladi» ro'yxatidan
 *  mijozga to'g'ridan-to'g'ri o'tiladi va brauzerning Orqasi ishlaydi
 *  (eski admin qoidasi, `#/mijozlar/<id>`). */
export function usePanelRoute(base: string, ids: readonly string[], fallback: string) {
  const [route, setRoute] = useState(() => readRoute(base, ids, fallback));
  const active = route.id;
  const param = route.param;
  const setActive = (id: string, next = "") => setRoute({ id, param: next });

  useEffect(() => {
    const sync = () => setRoute(readRoute(base, ids, fallback));
    window.addEventListener("popstate", sync);
    window.addEventListener("hashchange", sync);
    return () => {
      window.removeEventListener("popstate", sync);
      window.removeEventListener("hashchange", sync);
    };
  }, [base, ids, fallback]);

  const navigate = useCallback(
    (id: string, param = "") => {
      if (!ids.includes(id)) return;
      setActive(id, param);
      const tail = param ? `/${encodeURIComponent(param)}` : "";
      if (pathMode(base)) {
        const next = `${id === fallback && !param ? base : `${base}/${id}${tail}`}${window.location.search}`;
        if (next !== window.location.pathname + window.location.search) {
          window.history.pushState({ panel: id, param }, "", next);
        }
      } else if (window.location.hash !== `#/${id}${tail}`) {
        window.history.pushState({ panel: id, param }, "", `#/${id}${tail}`);
      }
    },
    [base, ids, fallback],
  );

  return [active, navigate, param] as const;
}
