/* Panel matni — uch tilda.
 *
 * Katalog serverdagi bilan BITTA manbadan keladi
 * (`i18n/{uz,ru,en}.json` → `scripts/build_i18n.py` → shu papkadagi
 * `catalogue.generated.ts`).  Shu sababdan panelda "Navbat uzun" deb
 * yozilgan hodisa Telegramda ham aynan shunday yoziladi.
 *
 * ## Nega React konteksti yo'q
 *
 * Til almashtirilganda sahifa QAYTA YUKLANADI.  Sabab: matnning bir
 * qismini server chizadi (xato izohlari, ba'zi sabab matnlari) va u
 * faqat yangi so'rovda yangi tilda keladi.  Kontekst bilan panelning
 * o'z matni darrov o'zgarib, serverdan kelgani eski tilda qolardi —
 * ya'ni ekranda ikki til aralashardi.  Qayta yuklash buni butunlay
 * yo'q qiladi va til almashtirish kuniga bir marta bo'ladigan amal.
 *
 * ## Nega `Intl` yo'q
 *
 * `api.ts:formatDateUz` izohida yozilgan sabab: Telegram ichidagi
 * WebView'ning ba'zi Android qurilmalarida ICU ma'lumoti kesilgan va
 * `Intl` JIMGINA noto'g'ri natija beradi.  Oy nomlari katalogda —
 * ular server bilan bir xil.
 */

import { CATALOGUE, type CatalogueEntry } from "./catalogue.generated";

export type Lang = "uz" | "ru" | "en";

export const LANGS: Lang[] = ["uz", "ru", "en"];
export const DEFAULT_LANG: Lang = "uz";

/** Saqlash kaliti.  Server bilan kelishuv: shu qiymat har so'rovda
 *  `X-Lang` sarlavhasida ketadi (`api.ts`). */
export const LANG_KEY = "enes_lang";

export const LANG_LABEL: Record<Lang, string> = {
  uz: "O‘zbekcha",
  ru: "Русский",
  en: "English",
};

/** Til tanlagichdagi qisqa yozuv (namunadagidek: UZ · RU · EN). */
export const LANG_SHORT: Record<Lang, string> = { uz: "UZ", ru: "RU", en: "EN" };

function normalize(value: string | null | undefined): Lang | null {
  if (!value) return null;
  const code = value.trim().toLowerCase().replace("_", "-").split("-")[0];
  return (LANGS as string[]).includes(code) ? (code as Lang) : null;
}

let current: Lang = DEFAULT_LANG;

/** Saqlangan tanlov → brauzer tili → `uz`. */
export function readLang(): Lang {
  try {
    const saved = normalize(localStorage.getItem(LANG_KEY));
    if (saved) return saved;
  } catch {
    /* xususiy oyna — brauzer tiliga o'tamiz */
  }
  return normalize(navigator.language) || DEFAULT_LANG;
}

/** Dastur boshlanishida bir marta chaqiriladi. */
export function initLang(): Lang {
  current = readLang();
  document.documentElement.lang = current;
  return current;
}

export function getLang(): Lang {
  return current;
}

export function setLang(lang: Lang): void {
  if (lang === current) return;
  try {
    localStorage.setItem(LANG_KEY, lang);
  } catch {
    /* saqlanmasa ham sahifa yangi tilda ochiladi */
  }
  /* Serverdan keladigan matn ham yangi tilda bo'lishi uchun qayta
     yuklaymiz — yuqoridagi izohga qarang. */
  location.reload();
}

function lookup(key: string, lang: Lang): CatalogueEntry | undefined {
  return CATALOGUE[lang]?.[key] ?? CATALOGUE[DEFAULT_LANG]?.[key];
}

/** Kalit bo'yicha matn.  Topilmasa KALITNING O'ZI qaytadi — bo'sh joy
 *  emas: yetishmayotgan tarjima ekranda darrov ko'rinsin. */
export function t(key: string, params?: Record<string, string | number>): string {
  const value = lookup(key, current);
  if (typeof value !== "string") return key;
  if (!params) return value;
  return value.replace(/\{(\w+)\}/g, (whole, name: string) =>
    name in params ? String(params[name]) : whole,
  );
}

/** Ro'yxatli qiymat: oy va hafta kunlari nomlari. */
export function tList(key: string): string[] {
  const value = lookup(key, current);
  return Array.isArray(value) ? value : [];
}

/** Hodisa turining nomi.  Katalogda bo'lmasa turning o'zi ko'rinadi —
 *  yangi tur qo'shilib tarjimasi unutilsa hodisa YO'QOLMAYDI. */
export function eventLabel(eventType: string): string {
  const key = `event.${eventType}`;
  const label = t(key);
  return label === key ? eventType : label;
}
