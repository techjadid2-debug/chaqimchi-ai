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

function readId(base: string, ids: readonly string[], fallback: string) {
  const source = pathMode(base)
    ? window.location.pathname.slice(base.length).replace(/^\/+/, "")
    : window.location.hash.replace(/^#\/?/, "");
  const id = source.split(/[/?#]/)[0];
  return ids.includes(id) ? id : fallback;
}

export function usePanelRoute(base: string, ids: readonly string[], fallback: string) {
  const [active, setActive] = useState(() => readId(base, ids, fallback));

  useEffect(() => {
    const sync = () => setActive(readId(base, ids, fallback));
    window.addEventListener("popstate", sync);
    window.addEventListener("hashchange", sync);
    return () => {
      window.removeEventListener("popstate", sync);
      window.removeEventListener("hashchange", sync);
    };
  }, [base, ids, fallback]);

  const navigate = useCallback(
    (id: string) => {
      if (!ids.includes(id)) return;
      setActive(id);
      if (pathMode(base)) {
        const next = `${id === fallback ? base : `${base}/${id}`}${window.location.search}`;
        if (next !== window.location.pathname + window.location.search) {
          window.history.pushState({ panel: id }, "", next);
        }
      } else if (window.location.hash !== `#/${id}`) {
        window.history.pushState({ panel: id }, "", `#/${id}`);
      }
    },
    [base, ids, fallback],
  );

  return [active, navigate] as const;
}
