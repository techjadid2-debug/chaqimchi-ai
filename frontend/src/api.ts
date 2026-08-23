export type ApiOptions = RequestInit & { siteId?: string };

const OWNER_TOKEN = "chaqimchi_owner_token_v2";
const ADMIN_TOKEN = "chaqimchi_admin_token_v2";

export function tokenFor(kind: "owner" | "admin") {
  return sessionStorage.getItem(kind === "owner" ? OWNER_TOKEN : ADMIN_TOKEN) || "";
}

export function saveToken(kind: "owner" | "admin", token: string) {
  sessionStorage.setItem(kind === "owner" ? OWNER_TOKEN : ADMIN_TOKEN, token);
}

export function clearToken(kind: "owner" | "admin") {
  sessionStorage.removeItem(kind === "owner" ? OWNER_TOKEN : ADMIN_TOKEN);
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

export function formatNumber(value: number | null | undefined) {
  return typeof value === "number" ? new Intl.NumberFormat("uz-UZ").format(value) : "—";
}

export function formatMoney(value: number | null | undefined) {
  return typeof value === "number" ? `${new Intl.NumberFormat("uz-UZ").format(value)} so‘m` : "—";
}

export function relativeMinutes(value: number | null | undefined) {
  if (value == null) return "hali ma’lumot yo‘q";
  if (value < 1) return "hozir";
  if (value < 60) return `${value} daqiqa oldin`;
  if (value < 1440) return `${Math.floor(value / 60)} soat oldin`;
  return `${Math.floor(value / 1440)} kun oldin`;
}
