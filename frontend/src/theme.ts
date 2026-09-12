import { t } from "./i18n";

/* Yorug'/qorong'i tema — bitta joyda.
 *
 * Uch holat: `light`, `dark` va `system`.  Nega uchinchisi kerak:
 * ikkitasi bo'lsa "tizim qorong'iga o'tdi" degan holat hech qachon
 * kuzatilmasdi — odam kechqurun panelni qo'lda almashtirishi kerak
 * bo'lardi.  `system` da esa `prefers-color-scheme` o'zi hal qiladi
 * (`cloud/static/tokens.css` dagi media so'rovi).
 *
 * Standart — `dark` (2026-09-11, dizayn-3): namuna to'liq qorong'i va
 * kamera kadri qorong'i sathda yaxshi o'qiladi — kadr atrofidagi oq
 * maydon ko'zni kadrdan tortadi.  Yorug' rejim va «tizim» qoladi —
 * egasi bir bosishda almashtiradi.
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

/** Brauzer manzil qatorining rangi (mobil).
 *
 *  Qiymat `tokens.css` dagi `--surface` dan O'QILADI: bu yerda qo'lda
 *  yozilsa palitra o'zgarganda telefonda panel tepasida boshqa rangli
 *  chiziq qolib ketardi va buni faqat qurilmada ko'rish mumkin edi.
 *
 *  Zaxira qiymat baribir kerak: bu funksiya birinchi chizishdan OLDIN
 *  ishlaydi (`owner.html` dagi bootstrap) va o'sha paytda stil hali
 *  yuklanmagan bo'lishi mumkin — u holda `getComputedStyle` bo'sh
 *  satr qaytaradi.  Zaxira tokenning joriy qiymati bilan bir xil. */
const META_FALLBACK: Record<"light" | "dark", string> = {
  light: "#ffffff",
  dark: "#11161f",
};

function metaColor(mode: "light" | "dark"): string {
  try {
    const value = getComputedStyle(document.documentElement)
      .getPropertyValue("--surface")
      .trim();
    if (value) return value;
  } catch {
    /* Stil hali yo'q yoki muhit brauzer emas (test). */
  }
  return META_FALLBACK[mode];
}

export function readTheme(): Theme {
  try {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved === "light" || saved === "dark" || saved === "system") return saved;
  } catch {
    /* saqlash yopiq — standart holat */
  }
  return "dark";
}

/** Tanlov `system` bo'lsa tizim nimani xohlayotgani. */
export function resolveTheme(theme: Theme): "light" | "dark" {
  if (theme !== "system") return theme;
  try {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  } catch {
    return "dark";
  }
}

export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  /* `system` da atribut UMUMAN qo'yilmaydi: tokenlar faylidagi
     `:root:not([data-theme="light"])` media bloki shundagina ishlaydi. */
  if (theme === "system") delete root.dataset.theme;
  else root.dataset.theme = theme;

  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", metaColor(resolveTheme(theme)));
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

/** Tugma yozuvi — katalogdan (uch tilda). */
export function themeLabel(theme: Theme): string {
  return t(`panel.theme.${theme}`);
}

export const THEME_ICON: Record<Theme, string> = {
  light: "sun",
  dark: "moon",
  system: "display",
};
