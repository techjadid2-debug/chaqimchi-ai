import { getLang, t, tList } from "./i18n";
import type { Dashboard } from "./types";

export type ApiOptions = RequestInit & { siteId?: string };

const OWNER_TOKEN = "enes_owner_token";
const ADMIN_TOKEN = "enes_admin_token";
const INSTALLER_TOKEN = "enes_installer_token";

/** Panel turi.  Uchta panel bitta `api()` dan o'tadi; farq faqat
 *  tokenning qayerda yashashi va chiqish manzilida. */
export type PanelKind = "owner" | "admin" | "installer";

/* Do'kon egasi va o'rnatuvchi tokeni `localStorage` da, admin tokeni
 * `sessionStorage` da.
 *
 * Farq ataylab.  Egasi panelga Telegram botdagi havoladan va telefon
 * ekranidan kiradi; `sessionStorage` da token yorliq yopilishi bilan
 * o'chib, u har safar qaytadan kirishi kerak bo'lardi.  O'rnatuvchi
 * ham xuddi shunday ishlaydi — obyektda, telefon brauzerida, NVR
 * parolini terib turib: yorliq almashtirilganda qaytadan kirish uni
 * ishning o'rtasida to'xtatardi.  Admin esa kompyuterda va huquqi
 * kengroq — qisqa sessiya xavfsizroq.
 *
 * Kalit nomi eski statik panel bilan AYNAN bir xil
 * (`enes_installer_token`): React'ga ko'chish usta uchun qaytadan
 * kirishni talab qilmasin. */
const storeFor = (kind: PanelKind) => (kind === "admin" ? sessionStorage : localStorage);
const keyFor = (kind: PanelKind) =>
  kind === "owner" ? OWNER_TOKEN : kind === "admin" ? ADMIN_TOKEN : INSTALLER_TOKEN;

export function tokenFor(kind: PanelKind) {
  try {
    return storeFor(kind).getItem(keyFor(kind)) || "";
  } catch {
    return "";
  }
}

export function saveToken(kind: PanelKind, token: string) {
  try {
    storeFor(kind).setItem(keyFor(kind), token);
  } catch {
    /* Telegram ichidagi WebView xotirani taqiqlashi mumkin — token
       shu sessiyada RAM'da qoladi, kirish baribir ishlaydi. */
  }
}

export function clearToken(kind: PanelKind) {
  try {
    storeFor(kind).removeItem(keyFor(kind));
    // Eski versiya tokeni sessionStorage'da qolgan bo'lishi mumkin.
    sessionStorage.removeItem(keyFor(kind));
  } catch {
    /* yuqoridagi izohga qarang */
  }
}

/** Chiqish: avval SERVERDA sessionni bekor qiladi, keyin kalitni o'chiradi.
 *
 * Ilgari «Chiqish» faqat brauzerdagi kalitni o'chirardi — nusxa
 * olingan token 12 soat davomida ishlayverardi.  Tartib muhim: so'rov
 * token o'chirilishidan OLDIN ketishi kerak.  Server javob bermasa
 * ham kalit baribir o'chadi: odam «chiqdim» deb turganda ekranda
 * qolib ketmasin.
 */
export async function logout(kind: PanelKind) {
  /* O'rnatuvchi ham portal hisobi (`portal_accounts`) — chiqish yo'li
     admin bilan bitta; faqat do'kon egasining sessiyasi alohida
     jadvalda yashaydi. */
  const path = kind === "owner" ? "/api/v1/owner/auth/logout" : "/api/v1/auth/logout";
  try {
    await api(path, kind, { method: "POST" });
  } catch {
    /* Tarmoq yo'q yoki token allaqachon yaroqsiz. */
  }
  clearToken(kind);
}

/** Server xatosidan odam o'qiydigan matnni ajratadi.
 *
 * `detail` HAR DOIM satr emas: FastAPI'ning `RequestValidationError`i
 * uni RO'YXAT qilib qaytaradi va ilgari mijoz ekranida `[object Object]`
 * chiqardi.  Shuning uchun tur tekshiriladi va tushunarsiz shakl
 * uchun umumiy matn beriladi.
 */
function errorText(body: unknown, status = 0): string {
  const data = (body ?? {}) as { detail?: unknown; message?: unknown };
  /* Server 500 bergan yoki FastAPI'ning o'z standart matni («Not Found»,
     «Internal Server Error») kelgan — bu ega uchun ma'nosiz inglizcha
     satr; o'rniga umumiy matn va HTTP kodi (qo'llab-quvvatlashga aytish
     uchun).  Serverning O'Z xabari (`X-Lang` bilan tarjima qilingan
     `detail`) esa qoladi. */
  const generic = status >= 500 || (typeof data.detail === "string" && GENERIC_DETAILS.has(data.detail));
  if (generic) return `${t("panel.error.request_failed")} (HTTP ${status})`;
  if (typeof data.detail === "string" && data.detail) return data.detail;
  if (typeof data.message === "string" && data.message) return data.message;
  if (Array.isArray(data.detail)) {
    const first = data.detail[0] as { msg?: unknown } | undefined;
    if (first && typeof first.msg === "string") return first.msg;
  }
  return t("panel.error.request_failed");
}

/** FastAPI/Starlette'ning o'zi yozadigan `detail` matnlari — tarjimasiz. */
const GENERIC_DETAILS = new Set([
  "Not Found", "Internal Server Error", "Method Not Allowed", "Unauthorized",
  "Forbidden", "Not authenticated", "Bad Request", "Service Unavailable",
  "Bad Gateway", "Gateway Timeout",
]);

export async function api<T>(path: string, kind: PanelKind, options: ApiOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const token = tokenFor(kind);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.siteId) headers.set("X-Owner-Site-Id", options.siteId);
  /* Server chizadigan matn (xato izohi, hodisa nomi) so'rovchining
     tilida qaytsin.  Zanjir `cloud/i18n.py: resolve_lang` da. */
  headers.set("X-Lang", getLang());
  if (options.body && !headers.has("Content-Type") && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(path, { ...options, headers });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(errorText(body, response.status)) as Error & { status?: number; code?: string };
    error.status = response.status;
    /* Mashina o'qiydigan kod: matn tarjima qilinsa ham o'zgarmaydi,
       shuning uchun shart tekshiruvi va testlar shunga bog'lanadi. */
    const code = (body as { code?: unknown }).code;
    if (typeof code === "string") error.code = code;
    throw error;
  }
  return body as T;
}

/** Himoyalangan rasm/video endpointini brauzerga xavfsiz Blob URL qilib beradi.
 * `<img src>` Authorization header yubora olmaydi; shu sabab kamera scan va
 * hodisa dalillari ilgari 401 bilan jim bo'sh ko'rinardi. */
export async function mediaObjectUrl(path: string, kind: PanelKind, siteId?: string): Promise<string> {
  const headers = new Headers();
  const token = tokenFor(kind);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (siteId) headers.set("X-Owner-Site-Id", siteId);
  const response = await fetch(path, { headers });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const text = errorText(body, response.status);
    throw new Error(text === t("panel.error.request_failed") ? t("panel.error.media_open_failed") : text);
  }
  return URL.createObjectURL(await response.blob());
}

/** Blob'ni faylga saqlaydi.
 *
 * Uchta tafsilot muhim va ular to'rtta chaqiruv joyida alohida yozilib
 * xato bo'lgan edi:
 *
 * 1. `<a>` DOMga QO'SHILADI.  Safari va ba'zi WebView'lar hujjatda
 *    turmagan elementning `click()` ini jimgina tashlab yuboradi —
 *    tugma bosiladi, hech narsa yuklanmaydi va xato ham chiqmaydi.
 * 2. `revokeObjectURL` DARHOL chaqirilmaydi.  Brauzer yuklashni
 *    boshlashga ulgurmasdan manzil bekor qilinsa fayl bo'sh yoki
 *    umuman kelmaydi; shuning uchun bir soniyadan keyin.
 * 3. `rel="noopener"` — havola yangi kontekst ochsa ham.
 */
export function downloadBlobUrl(url: string, filename: string): void {
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.rel = "noopener";
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  window.setTimeout(() => {
    link.remove();
    URL.revokeObjectURL(url);
  }, 1000);
}

/** Matnni CSV fayl qilib beradi.  BOM saqlanadi: usiz Excel kirillni
 *  buzadi (`cloud/main.py` dagi CSV yo'li bilan bir xil sabab). */
export function downloadCsv(csv: string, filename: string): void {
  downloadBlobUrl(
    URL.createObjectURL(new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8" })),
    filename,
  );
}

/** Hisob roli qaysi panelga tegishli.  Rol paneldan BOSHQA bo'lsa
 *  token saqlanmaydi: aks holda odam «kirdim» deb o'ylab, keyin har
 *  so'rovda 403 ko'rardi. */
const ROLE_FOR: Record<PanelKind, string> = { owner: "customer", admin: "admin", installer: "installer" };
const WRONG_ROLE_KEY: Record<PanelKind, string> = {
  owner: "panel.login.not_owner_account",
  admin: "panel.login.admin_required",
  installer: "panel.installer.login.wrong_account",
};

export async function login(username: string, password: string, kind: PanelKind) {
  const result = await api<{ access_token: string; account: { role: string; full_name?: string } }>(
    "/api/v1/auth/login",
    kind,
    { method: "POST", body: JSON.stringify({ username, password }) },
  );
  if (result.account.role !== ROLE_FOR[kind]) throw new Error(t(WRONG_ROLE_KEY[kind]));
  saveToken(kind, result.access_token);
  return result;
}

export type PortalAccount = {
  id: string;
  username: string;
  full_name?: string;
  role: string;
  status: string;
  company?: string;
};

/** «Men kimman?» — panel har ochilishda so'raydi.
 *
 * Nega token yetarli emas: o'rnatuvchi hisobi `pending` holatida ham
 * token oladi (u yo'riqnomani darhol ko'rishi kerak), lekin vazifalar
 * ro'yxati unga BERILMAYDI.  Ikkalasini ajratmasa panel bo'sh ro'yxat
 * ko'rsatib «obyekt yo'q» deb yolg'on aytardi. */
export async function whoAmI(kind: PanelKind) {
  const result = await api<{ account: PortalAccount }>("/api/v1/auth/me", kind);
  return result.account;
}

export type InstallerRegistration = {
  full_name: string;
  phone: string;
  company: string;
  username: string;
  password: string;
  consent: boolean;
};

/** O'rnatuvchi o'zini ro'yxatdan o'tkazadi.
 *
 * Hisob `pending` bo'lib tushadi — obyekt biriktirishni admin qiladi.
 * Token darhol beriladi: usta yo'riqnomani va o'z holatini tasdiqni
 * kutib turib ham ko'rishi kerak. */
export async function registerInstaller(body: InstallerRegistration) {
  const result = await api<{ access_token: string; message?: string }>(
    "/api/v1/auth/installer/register",
    "installer",
    { method: "POST", body: JSON.stringify({ ...body, company: body.company || null }) },
  );
  saveToken("installer", result.access_token);
  return result;
}

/** Telegram botdagi bir martalik havola bilan kirish (`/owner?key=...`).
 *
 * Bot egaga aynan shunday havola yuboradi — usiz u parol eslab qolishi
 * kerak bo'lardi.  Kalit ishlatilgach manzil qatoridan olib tashlanadi:
 * u bir marta ishlaydi va tarixda, ulashilgan skrinshotda yoki
 * `Referer` sarlavhasida qolib ketmasligi kerak. */
export async function loginWithLinkKey(): Promise<boolean> {
  const params = new URLSearchParams(window.location.search);
  const key = params.get("key");
  if (!key) return false;
  try {
    const result = await api<{ access_token: string }>("/api/v1/owner/auth/link", "owner", {
      method: "POST",
      body: JSON.stringify({ key }),
    });
    saveToken("owner", result.access_token);
    return true;
  } finally {
    params.delete("key");
    const query = params.toString();
    window.history.replaceState(
      null,
      "",
      `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`,
    );
  }
}

/* ── Do'kon kompyuterini ulash ─────────────────────────────────────
 *
 * Qurilma o'zini bulutga tanishtiradi va brauzerni
 * `/owner?connect=<token>` da ochadi.  Ega shu sahifada ro'yxatdan
 * o'tadi (yoki kiradi) va kompyuterni o'z do'koniga biriktiradi. */

export type PendingDevice = {
  pending_id: string;
  verify_code: string;
  label: string;
  product_name: string;
  app_version: string;
  os_name: string;
  local_ip_masked: string;
};

/** Manzildan `connect` tokenini oladi va uni DARHOL olib tashlaydi.
 *
 * Token tarixda, ulashilgan skrinshotda yoki `Referer` sarlavhasida
 * qolib ketmasligi kerak — `loginWithLinkKey()` dagi bilan bir xil
 * mulohaza. */
export function takeConnectToken(): string {
  const params = new URLSearchParams(window.location.search);
  const token = params.get("connect");
  if (!token) return "";
  params.delete("connect");
  const query = params.toString();
  window.history.replaceState(
    null,
    "",
    `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`,
  );
  return token;
}

/** Tasdiqdan oldin: qaysi kompyuter ulanmoqchi?
 *
 * Autentifikatsiyasiz endpoint, shuning uchun undan faqat ko'z bilan
 * solishtirish uchun kerak bo'lgan narsa keladi. */
export async function peekConnect(token: string): Promise<PendingDevice | null> {
  try {
    return await api<PendingDevice>(
      `/api/v1/public/device-connect?token=${encodeURIComponent(token)}`,
      "owner",
    );
  } catch {
    return null;
  }
}

export type TrialBody = {
  phone: string;
  full_name: string;
  company: string;
  username: string;
  password: string;
  consent: boolean;
  plan?: string;
};

/** Yangi do'kon ochadi — mijoz login va parolni O'ZI tanlaydi. */
export async function registerTrial(body: TrialBody) {
  return api<{ site_id: string; username: string; trial_days: number }>(
    "/api/v1/public/quick-trial",
    "owner",
    { method: "POST", body: JSON.stringify({ ...body, website: "" }) },
  );
}

export async function claimDevice(connectToken: string) {
  return api<{ site_id: string; label: string; verify_code: string }>(
    "/api/v1/owner/devices/claim",
    "owner",
    { method: "POST", body: JSON.stringify({ connect_token: connectToken }) },
  );
}

/* ── Kamera qidirish ──────────────────────────────────────────────── */

export type ScanKind = "lan_scan" | "onvif" | "channels" | "probe";

export type CameraRole = "entrance" | "checkout" | "sales" | "storage";

export type ScanStream = {
  stream_ref: number;
  safe_url: string;
  name?: string;
  encoding?: string;
  width?: number;
  height?: number;
  works?: boolean;
  warning?: string;
  ip?: string;
  vendor_hint?: string;
  has_onvif?: boolean;
  has_rtsp?: boolean;
  // Server hisoblagan rol taklifi (nom + o'lchamdan).  Bo'sh —
  // ishonchli belgi yo'q, tanlov odamniki.
  suggested_role?: CameraRole | "";
  suggestion_reasons?: string[];
  face_id_ok?: boolean | null;
  keep?: boolean;
};

export type ScanJob = {
  job_id: string;
  kind: ScanKind;
  status: "queued" | "running" | "done" | "failed" | "expired";
  progress: number;
  note: string;
  error: string;
  has_frame: boolean;
  result?: { streams?: ScanStream[]; cameras?: ScanStream[] };
};

export async function startScan(siteId: string, params: Record<string, unknown>) {
  const result = await api<{ job: ScanJob }>("/api/v1/owner/scan", "owner", {
    method: "POST",
    siteId,
    body: JSON.stringify(params),
  });
  return result.job;
}

export async function pollScan(siteId: string, jobId: string) {
  const result = await api<{ job: ScanJob }>(`/api/v1/owner/scan/${encodeURIComponent(jobId)}`, "owner", { siteId });
  return result.job;
}

export async function saveCameraFromScan(
  siteId: string,
  body: {
    job_id: string;
    stream_ref: number;
    label: string;
    camera_id?: string;
    // Bo'sh — rol tanlanmagan (yaroqli holat, server saqlanganiga tegmaydi).
    role?: CameraRole | "";
  },
) {
  return api<{ camera: { camera_id: string }; config_revision: number }>(
    "/api/v1/owner/cameras/from-scan",
    "owner",
    { method: "POST", siteId, body: JSON.stringify(body) },
  );
}

export async function saveCameraManually(
  siteId: string,
  cameraId: string,
  body: { label: string; rtsp_url: string; role?: CameraRole | "" },
) {
  return api<{ camera: { camera_id: string } }>(
    `/api/v1/owner/cameras/${encodeURIComponent(cameraId)}`,
    "owner",
    { method: "PUT", siteId, body: JSON.stringify({ ...body, enabled: true }) },
  );
}

/** Telegram Mini App ichida parolsiz kirish. */
export async function loginWithTelegram(): Promise<boolean> {
  const telegram = (window as Window & {
    Telegram?: { WebApp?: { initData?: string; ready?: () => void; expand?: () => void } };
  }).Telegram?.WebApp;
  if (!telegram?.initData) return false;
  telegram.ready?.();
  telegram.expand?.();
  const result = await api<{ access_token: string }>("/api/v1/owner/auth/telegram-webapp", "owner", {
    method: "POST",
    body: JSON.stringify({ init_data: telegram.initData }),
  });
  saveToken("owner", result.access_token);
  return true;
}

/** Bot manzili — server `owner.html` qobig'iga o'rnatib beradi. */
/** Matnni buferga nusxalaydi.  Muvaffaqiyatni `boolean` bilan aytadi.
 *
 * `navigator.clipboard` HAR JOYDA yo'q: HTTP ustida, eski Android
 * WebView'da va Telegram Mini App ichida u `undefined` bo'lishi mumkin.
 * Ilgari kod `navigator.clipboard?.writeText(...)` deb yozilgan edi —
 * ya'ni bunday muhitda tugma bosilardi va **jimgina hech narsa
 * bo'lmasdi**.  Do'kon egasi uchun bu buzuq tugma.
 *
 * Zaxira yo'l `execCommand("copy")` — eskirgan, lekin aynan o'sha
 * muhitlarda ishlaydi.
 */
export async function copyText(value: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return true;
    }
  } catch {
    /* Ruxsat berilmadi — pastdagi zaxira yo'l sinaladi. */
  }
  try {
    const field = document.createElement("textarea");
    field.value = value;
    // Ekrandan tashqarida, lekin `readOnly` EMAS: iOS faqat
    // tahrirlanadigan maydondan nusxa oladi.
    field.style.cssText = "position:fixed;top:-1000px;opacity:0";
    document.body.appendChild(field);
    field.select();
    field.setSelectionRange(0, value.length);
    const ok = document.execCommand("copy");
    document.body.removeChild(field);
    return ok;
  } catch {
    return false;
  }
}

/** Bot manzili — server qobiqqa qo'ygan `application/json` blokidan.
 *
 * `window.__ENES_BOT_URL__` ga qiymat berish INLINE skript bo'lardi va
 * CSP `script-src` uni bloklardi.  `type="application/json"` bloki esa
 * ijro etilmaydi, ya'ni siyosatdan tashqarida qoladi.  Bot sozlanmagan
 * bo'lsa server bo'sh satr qo'yadi — login ekranida "botdan havola
 * oling" taklifi ko'rsatilmaydi. */
export function telegramBotUrl(): string {
  try {
    const holder = document.getElementById("bot-url");
    const raw = holder ? String(JSON.parse(holder.textContent || '""')) : "";
    return raw.startsWith("http") ? raw : "";
  } catch {
    return "";
  }
}

/** "2026-yil 24-avgust, dushanba" — joriy tilda.
 *
 * `Intl` ishlatilmaydi: panel Telegram ichidagi WebView'da ochiladi va
 * u yerdagi ba'zi Android qurilmalarda `uz-UZ` uchun ICU ma'lumoti
 * yo'q — sana "M08 24, Mon" bo'lib chiqadi.  Oy va kun nomlari
 * katalogdan (`format.*`) keladi — server ham aynan shu nomlarni
 * ishlatadi, ya'ni panel bilan Telegram xabari bir xil yozadi.
 *
 * Hafta kuni: JS `getDay()` yakshanbadan (0) boshlaydi, katalog esa
 * dushanbadan — shuning uchun `(getDay() + 6) % 7`. */
export function formatDateUz(date: Date = new Date(), withWeekday = true) {
  const params = {
    year: date.getFullYear(),
    day: date.getDate(),
    month: tList("format.months")[date.getMonth()] ?? "",
    weekday: tList("format.weekdays")[(date.getDay() + 6) % 7] ?? "",
  };
  return t(withWeekday ? "format.date.long" : "format.date.long_no_weekday", params);
}

/** "24.08.2026" — jadval katakchalari uchun qisqa shakl. */

/** Toshkent vaqti bo'yicha daqiqa: UTC+5, yozgi vaqt yo'q. */
const TASHKENT_OFFSET_MIN = 5 * 60;

/** "14:47" — hodisa vaqti, HAR DOIM Toshkent bo'yicha.
 *
 * Ikki xato bir joyda tuzatildi.
 *
 * 1. `OwnerHome` ISO satridan `slice(11, 16)` bilan soat kesib olardi —
 *    bu XOM UTC.  2026-08-26 da mijoz panelida sarlavha "14:47" deb
 *    turgan payt hodisalar "09:47" ko'rinardi va ega ularni besh soat
 *    eskirgan deb o'yladi.
 * 2. `AdminHome` brauzer mintaqasini ishlatardi — chet eldan ochilganda
 *    panel kunlik hisobot bilan boshqa raqam ko'rsatardi.  Backend esa
 *    hamma joyda `ZoneInfo("Asia/Tashkent")` bilan hisoblaydi
 *    (`cloud/main.py`, `cloud/digest.py`), ya'ni do'konning kuni
 *    Toshkent bo'yicha boshlanadi va tugaydi.
 *
 * `Intl`/`toLocaleTimeString` ATAYLAB ishlatilmadi: `formatNumber` dagi
 * kabi sabab — ba'zi WebView'larda ICU yo'q va `timeZone` jimgina
 * e'tiborsiz qolib, yana brauzer mintaqasi chiqadi.  Qo'lda siljitish
 * har joyda bir xil natija beradi.
 */
function tashkentMoment(value: string | null | undefined): Date | null {
  if (!value) return null;
  // Mintaqasiz ISO satrini JS LOKAL vaqt deb o'qiydi; server esa uni UTC
  // deb yozadi.  Shuning uchun belgisi yo'q bo'lsa "Z" qo'shamiz.
  const text = String(value);
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(text);
  const date = new Date(hasZone ? text : `${text}Z`);
  if (Number.isNaN(date.getTime())) return null;
  // Qaytgan obyektning UTC maydonlari MAHALLIY qiymatni beradi — atayin:
  // brauzer mintaqasi hisobga olinmasin.
  return new Date(date.getTime() + TASHKENT_OFFSET_MIN * 60_000);
}

/** "06.09.2026" — server vaqtidan, HAR DOIM Toshkent bo'yicha.
 *
 * Ilgari bu funksiya xom `new Date(value)` ishlatardi va ikkita xato
 * bor edi:
 *   1. Server `"2026-09-06 20:14:43"` (mintaqasiz, bo'sh joy bilan)
 *      yuboradi — Safari buni umuman o'qiy olmaydi va `Invalid Date`
 *      qaytaradi, ya'ni sana o'rnida "—" turardi;
 *   2. Chrome uni MAHALLIY vaqt deb o'qiydi, server esa UTC deb
 *      yozgan — kechqurungi yozuv bir kun oldin ko'rinishi mumkin edi.
 * `tashkentMoment` ikkalasini ham hal qiladi. */
export function formatDateShort(value: string | null | undefined) {
  const shifted = tashkentMoment(value);
  if (!shifted) return "—";
  const day = String(shifted.getUTCDate()).padStart(2, "0");
  const month = String(shifted.getUTCMonth() + 1).padStart(2, "0");
  return `${day}.${month}.${shifted.getUTCFullYear()}`;
}

export function formatTimeUz(value: string | null | undefined) {
  const shifted = tashkentMoment(value);
  if (!shifted) return "—";
  return `${String(shifted.getUTCHours()).padStart(2, "0")}:${String(shifted.getUTCMinutes()).padStart(2, "0")}`;
}

/** Toshkent soati 0..23 — vaqt lentasidagi ustunni topish uchun.
 *
 * `formatTimeUz(x).slice(0, 2)` bilan matndan soat KESIB OLMANG: format
 * o'zgarsa raqam jimgina buziladi va bu yuqorida tuzatilgan xatoning
 * aynan takrori bo'ladi. */
export function tashkentHour(value: string | null | undefined): number | null {
  const shifted = tashkentMoment(value);
  return shifted ? shifted.getUTCHours() : null;
}

/** Toshkent kuni "YYYY-MM-DD".  Server ham kunni shu chegara bilan
 *  kesadi (`ZoneInfo("Asia/Tashkent")`), ya'ni panel va hisobot bitta
 *  kun haqida gapiradi. */
export function tashkentDay(value: string | null | undefined): string | null {
  const shifted = tashkentMoment(value);
  return shifted ? shifted.toISOString().slice(0, 10) : null;
}

/** Hodisadan hozirgacha necha soat o'tdi.  Ochib bo'lmasa `null`.
 *
 * Mintaqa bilan SURILMAYDI: yosh haqiqiy lahzalar farqi, ya'ni uni
 * Toshkentga o'girish 5 soatlik yolg'on qo'shardi. */
export function hoursSince(value: string | null | undefined): number | null {
  if (!value) return null;
  const text = String(value);
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(text);
  const date = new Date(hasZone ? text : `${text}Z`);
  if (Number.isNaN(date.getTime())) return null;
  return (Date.now() - date.getTime()) / 3_600_000;
}

/** Bugun — Toshkent bo'yicha.  `new Date().toISOString().slice(0,10)`
 *  chet eldan ochilganda boshqa kunni berardi. */
export function tashkentToday(): string {
  return tashkentDay(new Date().toISOString()) || "";
}

/** "1 234 567" — mingliklar orasida probel (o'zbekcha va ruscha),
 *  inglizchada "1,234,567".
 *
 * `Intl` emas: ba'zi WebView'larda `uz-UZ` uchun ICU yo'q va raqam
 * "1,234,567" bo'lib chiqadi — o'zbekcha yozuvda vergul kasr belgisi,
 * ya'ni bu son butunlay boshqacha o'qiladi.  Ajratgichlar katalogdan
 * (`format.number.*`): server hisobotida ham xuddi shu belgilar.
 *
 * Katalogdagi ODDIY probel bu yerda UZILMAS probelga (U+00A0)
 * aylanadi.  Telegramda farqi yo'q, brauzerda esa oddiy probel tor
 * kartada raqamni ikki qatorga bo'lib yuboradi — "48 600" ning "48"
 * i bir qatorda, "600" i keyingisida. */
export function formatNumber(value: number | null | undefined) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  const rounded = Math.round(value * 100) / 100;
  const [whole, fraction] = String(Math.abs(rounded)).split(".");
  const group = t("format.number.group");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, group === " " ? "\u00a0" : group);
  return `${rounded < 0 ? "−" : ""}${grouped}${fraction ? `${t("format.number.decimal")}${fraction}` : ""}`;
}

/** Pul.  Million va undan katta summalar qisqartiriladi: "48,6 mln
 *  so'm" bir qarashda o'qiladi, "48 600 000 so'm" esa kartada ikki
 *  qatorga sinib ketadi va raqamlarni sanashga majbur qiladi. */
export function formatMoney(value: number | null | undefined, { short = true } = {}) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  if (short && Math.abs(value) >= 1_000_000) {
    const millions = Math.round(value / 100_000) / 10;
    return t("money.mln", { value: formatNumber(millions) });
  }
  return t("money.plain", { value: formatNumber(value) });
}

/** "12 daqiqa oldin" — oxirgi aloqa yoshi.  Chegaralar (60, 1440)
 *  serverdagi `minutes_since_seen` bilan bir xil birlikda: daqiqa. */
export function relativeMinutes(value: number | null | undefined) {
  if (value == null) return t("panel.common.no_data");
  if (value < 1) return t("format.relative.now");
  if (value < 60) return t("format.relative.minutes", { count: value });
  if (value < 1440) return t("format.relative.hours", { count: Math.floor(value / 60) });
  return t("format.relative.days", { count: Math.floor(value / 1440) });
}


/** Tarifda panel bo'limi ochiqmi.
 *
 * Ro'yxat kelmagan bo'lsa (eski bulut yoki javob hali yo'q) bo'lim
 * OCHIQ deb hisoblanadi.  Teskarisi yomonroq: to'lagan mijoz sekin
 * internetda o'z kartasini bir zumga «tarifda yo'q» holida ko'rardi.
 */
export function hasFeature(dashboard: Dashboard, name: string): boolean {
  const list = dashboard.site.plan?.panel_features;
  return !Array.isArray(list) || list.includes(name);
}

/** Telefondagi rasmni JPEG ga aylantiradi.
 *
 * Nega kerak: iPhone galereyadan **HEIC** beradi, server esa faqat
 * JPEG/PNG qabul qiladi (`cloud/main.py`: 415 "Faqat JPEG yoki PNG
 * rasm qabul qilinadi").  Konvertatsiyasiz do'kon egasi xodim rasmini
 * telefonidan umuman yuklay olmasdi — funksiya jimgina ishlamasdi.
 * Eski panelda bu `toJpeg` bilan hal qilingan edi, v2 ga ko'chirilmay
 * qolgan (2026-09-07 da topildi).
 *
 * Yo'l-yo'lakay rasm kichraytiriladi: telefon kamerasi 4000px beradi,
 * yuz shabloni uchun 1600px yetarli va yuklash sezilarli tezlashadi.
 */
export async function toJpeg(file: File, maxSide = 1600, quality = 0.9): Promise<Blob> {
  const url = URL.createObjectURL(file);
  try {
    const image = await new Promise<HTMLImageElement>((resolve, reject) => {
      const element = new Image();
      element.onload = () => resolve(element);
      /* Safari HEIC'ni tizim kodeki bilan ocha oladi; ocholmasa xato
         mijozga ko'rinadi va u boshqa rasm tanlaydi. */
      element.onerror = () => reject(new Error(t("panel.error.image_open_failed")));
      element.src = url;
    });
    const scale = Math.min(1, maxSide / Math.max(image.width, image.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(image.width * scale));
    canvas.height = Math.max(1, Math.round(image.height * scale));
    const context = canvas.getContext("2d");
    if (!context) throw new Error(t("panel.error.image_read_failed"));
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob | null>(resolve =>
      canvas.toBlob(resolve, "image/jpeg", quality),
    );
    if (!blob) throw new Error(t("panel.error.image_save_failed"));
    return blob;
  } finally {
    URL.revokeObjectURL(url);
  }
}
