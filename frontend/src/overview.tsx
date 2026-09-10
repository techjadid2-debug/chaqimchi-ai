import { useEffect, useState } from "react";
import { api } from "./api";
import { eventLabel, t } from "./i18n";
import type { Segment } from "./charts";
import type { Overview, OverviewDay } from "./types";

/* Davr bo'yicha ko'rinish — bosh sahifa va «Tahlil» uchun umumiy qism.
 *
 * Ikkalasi bitta so'rovdan (`/api/v1/owner/overview`) o'qiydi va bitta
 * davr tanlovini bo'lishadi: ega bosh sahifada «7 kun» ni tanlab
 * «Tahlil»ga o'tsa u yerda ham 7 kun turadi.  Tanlov `localStorage` da
 * — bu qulaylik, ma'lumot emas: o'qib bo'lmasa «Bugun» qaytadi. */

export type Period = "today" | "7" | "14" | "30";
const PERIOD_KEY = "enes_home_period";

export function readPeriod(fallback: Period = "today"): Period {
  try {
    const stored = localStorage.getItem(PERIOD_KEY);
    return stored === "7" || stored === "14" || stored === "30" || stored === "today" ? stored : fallback;
  } catch {
    return fallback;
  }
}

export function savePeriod(period: Period) {
  try { localStorage.setItem(PERIOD_KEY, period); } catch { /* xotira yopiq — tanlov shu sahifada qoladi */ }
}

export function periodDays(period: Period): number {
  return period === "today" ? 0 : Number(period);
}

export function periodLabel(period: Period): string {
  return period === "today" ? t("panel.period.today") : t("panel.period.days", { count: periodDays(period) });
}

/** Davr tugmalari.  `options` — sahifa qaysilarini ko'rsatadi: bosh
 *  sahifada «Bugun» bor, «Tahlil»da yo'q (u kunlar kesimida). */
export function PeriodBar({ value, options, onChange }: { value: Period; options: Period[]; onChange: (period: Period) => void }) {
  return <div className="segmented period-bar" role="group">
    {options.map(option => <button key={option} className={value === option ? "active" : ""} onClick={() => onChange(option)}>{periodLabel(option)}</button>)}
  </div>;
}

/** `days === 0` bo'lsa so'rov yuborilmaydi (bugungi kun dashboard'da bor). */
export function useOverview(siteId: string, days: number) {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!siteId || !days) { setOverview(null); setError(""); return; }
    let stopped = false;
    setLoading(true);
    api<Overview>(`/api/v1/owner/overview?days=${days}`, "owner", { siteId })
      .then(answer => { if (!stopped) { setOverview(answer); setError(""); } })
      .catch(reason => { if (!stopped) setError(reason instanceof Error ? reason.message : t("panel.period.load_failed")); })
      .then(() => { if (!stopped) setLoading(false); });
    return () => { stopped = true; };
  }, [siteId, days]);
  return { overview, loading, error };
}

/** «10.09» — kunlik o'qdagi yorliq.  Yil yozilmaydi: 30 kunlik o'qda joy tor. */
export function dayLabel(date: string): string {
  return `${date.slice(8, 10)}.${date.slice(5, 7)}`;
}

/* Hodisa turlari uch guruhda: qizil — tun va xavfsizlik, sariq —
   savdo zali (navbat, kassa, uzoq turish), ko'k — qolgani.  Panelning
   vaqt lentasi (`EventTimeline.tsx: TONE_BY_TYPE`) bilan bir xil
   ma'no.  Hisobot kalitlari hodisa turidan farq qiladi
   (`restricted_zone`, `queue_alerts`), shuning uchun nom alohida. */
const EVENT_TONE: Record<string, string> = {
  after_hours_presence: "red",
  night_motion: "red",
  camera_tampered: "red",
  restricted_zone: "red",
  queue_alerts: "yellow",
  checkout_unattended: "yellow",
  loitering: "yellow",
};

function eventName(key: string): string {
  if (key === "restricted_zone") return t("panel.analytics.events.restricted_zone");
  if (key === "queue_alerts") return t("panel.analytics.events.queue_alerts");
  return eventLabel(key);
}

/** Donut bo'laklari: nol bo'lganlar tashlanadi, kattasi birinchi. */
export function eventSegments(events: Record<string, number> | undefined): Segment[] {
  return Object.entries(events || {})
    .filter(([, count]) => Number(count) > 0)
    .sort((a, b) => Number(b[1]) - Number(a[1]))
    .map(([key, count]) => ({ label: eventName(key), value: Number(count), tone: EVENT_TONE[key] || "blue" }));
}

/** Tungi hodisalar soni — «shundan tunda: N» uchun. */
export function nightCount(events: Record<string, number> | undefined): number {
  return Number(events?.after_hours_presence || 0) + Number(events?.night_motion || 0);
}

/** Davr ichidagi hodisalar yig'indisi — kartadagi bitta son. */
export function eventTotal(events: Record<string, number> | undefined): number {
  return Object.values(events || {}).reduce((sum, value) => sum + (Number(value) || 0), 0);
}

export function hasAnyReceipts(daily: OverviewDay[]): boolean {
  return daily.some(day => day.receipts != null);
}
