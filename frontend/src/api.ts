import type { Dashboard } from "./types";

export type ApiOptions = RequestInit & { siteId?: string };

const OWNER_TOKEN = "chaqimchi_owner_token_v2";
const ADMIN_TOKEN = "chaqimchi_admin_token_v2";

/* Do'kon egasi tokeni `localStorage` da, admin tokeni `sessionStorage` da.
 *
 * Farq ataylab.  Egasi panelga Telegram botdagi havoladan va telefon
 * ekranidan kiradi; `sessionStorage` da token yorliq yopilishi bilan
 * o'chib, u har safar qaytadan kirishi kerak bo'lardi.  Admin esa
 * kompyuterda, ko'pincha begona bo'lmagan joyda ishlaydi va uning
 * huquqi kengroq — qisqa sessiya xavfsizroq. */
const storeFor = (kind: "owner" | "admin") => (kind === "owner" ? localStorage : sessionStorage);
const keyFor = (kind: "owner" | "admin") => (kind === "owner" ? OWNER_TOKEN : ADMIN_TOKEN);

export function tokenFor(kind: "owner" | "admin") {
  try {
    return storeFor(kind).getItem(keyFor(kind)) || "";
  } catch {
    return "";
  }
}

export function saveToken(kind: "owner" | "admin", token: string) {
  try {
    storeFor(kind).setItem(keyFor(kind), token);
  } catch {
    /* Telegram ichidagi WebView xotirani taqiqlashi mumkin — token
       shu sessiyada RAM'da qoladi, kirish baribir ishlaydi. */
  }
}

export function clearToken(kind: "owner" | "admin") {
  try {
    storeFor(kind).removeItem(keyFor(kind));
    // Eski versiya tokeni sessionStorage'da qolgan bo'lishi mumkin.
    sessionStorage.removeItem(keyFor(kind));
  } catch {
    /* yuqoridagi izohga qarang */
  }
}

export async function api<T>(path: string, kind: "owner" | "admin", options: ApiOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const token = tokenFor(kind);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.siteId) headers.set("X-Owner-Site-Id", options.siteId);
  if (options.body && !headers.has("Content-Type") && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(path, { ...options, headers });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(body.detail || body.message || "So‘rov bajarilmadi") as Error & { status?: number };
    error.status = response.status;
    throw error;
  }
  return body as T;
}

/** Himoyalangan rasm/video endpointini brauzerga xavfsiz Blob URL qilib beradi.
 * `<img src>` Authorization header yubora olmaydi; shu sabab kamera scan va
 * hodisa dalillari ilgari 401 bilan jim bo'sh ko'rinardi. */
export async function mediaObjectUrl(path: string, kind: "owner" | "admin", siteId?: string): Promise<string> {
  const headers = new Headers();
  const token = tokenFor(kind);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (siteId) headers.set("X-Owner-Site-Id", siteId);
  const response = await fetch(path, { headers });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || "Media ochilmadi");
  }
  return URL.createObjectURL(await response.blob());
}

export async function login(username: string, password: string, kind: "owner" | "admin") {
  const result = await api<{ access_token: string; account: { role: string; full_name?: string } }>(
    "/api/v1/auth/login",
    kind,
    { method: "POST", body: JSON.stringify({ username, password }) },
  );
  const allowed = kind === "owner" ? result.account.role === "customer" : result.account.role === "admin";
  if (!allowed) throw new Error(kind === "owner" ? "Bu login biznes paneliga tegishli emas" : "Admin ruxsati talab qilinadi");
  saveToken(kind, result.access_token);
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
  body: { job_id: string; stream_ref: number; label: string; camera_id?: string },
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
  body: { label: string; rtsp_url: string },
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
export function telegramBotUrl(): string {
  const raw = (window as Window & { __CHAQIMCHI_BOT_URL__?: string }).__CHAQIMCHI_BOT_URL__ || "";
  return raw.startsWith("http") ? raw : "";
}

const MONTHS_UZ = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr"];
const WEEKDAYS_UZ = ["yakshanba", "dushanba", "seshanba", "chorshanba", "payshanba", "juma", "shanba"];

/** "2026-yil 24-avgust, dushanba".
 *
 * `Intl` ishlatilmaydi: panel Telegram ichidagi WebView'da ochiladi va
 * u yerdagi ba'zi Android qurilmalarda `uz-UZ` uchun ICU ma'lumoti
 * yo'q — sana "M08 24, Mon" bo'lib chiqadi.  O'n ikki oy nomi bilan
 * bu xavf butunlay yo'qoladi. */
export function formatDateUz(date: Date = new Date(), withWeekday = true) {
  const base = `${date.getFullYear()}-yil ${date.getDate()}-${MONTHS_UZ[date.getMonth()]}`;
  return withWeekday ? `${base}, ${WEEKDAYS_UZ[date.getDay()]}` : base;
}

/** "24.08.2026" — jadval katakchalari uchun qisqa shakl. */
export function formatDateShort(value: string | null | undefined) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return `${String(date.getDate()).padStart(2, "0")}.${String(date.getMonth() + 1).padStart(2, "0")}.${date.getFullYear()}`;
}

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
export function formatTimeUz(value: string | null | undefined) {
  if (!value) return "—";
  // Mintaqasiz ISO satrini JS LOKAL vaqt deb o'qiydi; server esa uni UTC
  // deb yozadi.  Shuning uchun belgisi yo'q bo'lsa "Z" qo'shamiz.
  const text = String(value);
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(text);
  const date = new Date(hasZone ? text : `${text}Z`);
  if (Number.isNaN(date.getTime())) return "—";
  const shifted = new Date(date.getTime() + TASHKENT_OFFSET_MIN * 60_000);
  return `${String(shifted.getUTCHours()).padStart(2, "0")}:${String(shifted.getUTCMinutes()).padStart(2, "0")}`;
}

/** "1 234 567" — mingliklar orasida probel.
 *
 * `Intl` emas: ba'zi WebView'larda `uz-UZ` uchun ICU yo'q va raqam
 * "1,234,567" bo'lib chiqadi — o'zbekcha yozuvda vergul kasr belgisi,
 * ya'ni bu son butunlay boshqacha o'qiladi. */
export function formatNumber(value: number | null | undefined) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  const rounded = Math.round(value * 100) / 100;
  const [whole, fraction] = String(Math.abs(rounded)).split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  return `${rounded < 0 ? "−" : ""}${grouped}${fraction ? `,${fraction}` : ""}`;
}

/** Pul.  Million va undan katta summalar qisqartiriladi: "48,6 mln
 *  so'm" bir qarashda o'qiladi, "48 600 000 so'm" esa kartada ikki
 *  qatorga sinib ketadi va raqamlarni sanashga majbur qiladi. */
export function formatMoney(value: number | null | undefined, { short = true } = {}) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  if (short && Math.abs(value) >= 1_000_000) {
    const millions = Math.round(value / 100_000) / 10;
    return `${formatNumber(millions)} mln so‘m`;
  }
  return `${formatNumber(value)} so‘m`;
}

export function relativeMinutes(value: number | null | undefined) {
  if (value == null) return "hali ma’lumot yo‘q";
  if (value < 1) return "hozir";
  if (value < 60) return `${value} daqiqa oldin`;
  if (value < 1440) return `${Math.floor(value / 60)} soat oldin`;
  return `${Math.floor(value / 1440)} kun oldin`;
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
