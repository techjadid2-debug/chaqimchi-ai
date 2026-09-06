/* Yorug'/qorong'i tema — bitta joyda.
 *
 * Uch holat: `light`, `dark` va `system`.  Nega uchinchisi kerak:
 * ikkitasi bo'lsa "tizim qorong'iga o'tdi" degan holat hech qachon
 * kuzatilmasdi — odam kechqurun panelni qo'lda almashtirishi kerak
 * bo'lardi.  `system` da esa `prefers-color-scheme` o'zi hal qiladi
 * (`cloud/static/tokens.css` dagi media so'rovi).
 *
 * Standart — `system`.  Do'kon egasining kompyuteri odatda yorug'
 * rejimda, ya'ni panel ham yorug' ochiladi; kechasi kamerani
 * telefondan ko'radigan odam esa qorong'i oladi.
 *
 * Tanlov `localStorage` da: u brauzerdan chiqmaydi va serverga
 * yuborilmaydi.  Xususiy oynada o'qish xato bersa (ba'zi brauzerlar
 * saytga saqlashni taqiqlaydi) — jim `system` ga tushamiz, panel
 * baribir ochiladi.
 */

export type Theme = "light" | "dark" | "system";

/** Saqlash kaliti.  Qobiqdagi boot skripti ham AYNAN shuni o'qiydi —
 *  ikkisi ajralib ketsa sahifa bir zumga noto'g'ri rangda ochiladi. */
export const THEME_KEY = "enes_theme";

/** Brauzer manzil qatorining rangi (mobil).  Tokendagi sath rangi
 *  bilan bir xil bo'lsin, aks holda telefonda panel tepasida boshqa
 *  rangli chiziq turadi. */
const META_COLOR: Record<"light" | "dark", string> = {
  light: "#ffffff",
  dark: "#11161f",
};

export function readTheme(): Theme {
  try {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved === "light" || saved === "dark" || saved === "system") return saved;
  } catch {
    /* saqlash yopiq — standart holat */
  }
  return "system";
}

/** Tanlov `system` bo'lsa tizim nimani xohlayotgani. */
export function resolveTheme(theme: Theme): "light" | "dark" {
  if (theme !== "system") return theme;
  try {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  } catch {
    return "light";
  }
}

export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  /* `system` da atribut UMUMAN qo'yilmaydi: tokenlar faylidagi
     `:root:not([data-theme="light"])` media bloki shundagina ishlaydi. */
  if (theme === "system") delete root.dataset.theme;
  else root.dataset.theme = theme;

  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", META_COLOR[resolveTheme(theme)]);
}

export function saveTheme(theme: Theme): void {
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    /* saqlanmasa ham joriy sahifada tema ishlaydi */
  }
}

/** Tugma bosilganda keyingi holat: yorug' → qorong'i → tizim → … */
export function nextTheme(theme: Theme): Theme {
  return theme === "light" ? "dark" : theme === "dark" ? "system" : "light";
}

export const THEME_LABEL: Record<Theme, string> = {
  light: "Yorug' rejim",
  dark: "Tungi rejim",
  system: "Tizim bo'yicha",
};

export const THEME_ICON: Record<Theme, string> = {
  light: "sun",
  dark: "moon",
  system: "display",
};
