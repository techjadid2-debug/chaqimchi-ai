import { useEffect, useState } from "react";
import { api } from "./api";
import { Timeline, type TimelineSegment } from "./charts";
import { Skeleton } from "./components";
import type { TimelineAnswer } from "./types";

/* Vaqt lentasining domen qobig'i.
 *
 * `charts.tsx` dagi `Timeline` shakldan boshqa hech narsani bilmaydi —
 * hodisa turi, uning o'zbekcha nomi va rangi shu yerda.  Ikki joy
 * ishlatadi (hodisalar sahifasi va AI yordamchi javobida), shuning
 * uchun komponent o'z so'rovini o'zi qiladi.
 */

/* Rang — TO'RT ma'no, 15 ta tur emas.
 *
 * Bir qarashda o'qish uchun "xavfsizlik / operatsion / oqim / texnika"
 * yetadi.  Har turga o'z rangini berish lentani chiroyli qilardi va
 * o'qib bo'lmaydigan qilardi: 24 ustunda 15 rang hech narsa aytmaydi.
 */
const TONE_BY_TYPE: Record<string, string> = {
  camera_tampered: "red",
  after_hours_presence: "red",
  zone_entered: "red",
  queue_threshold_exceeded: "yellow",
  checkout_unattended: "yellow",
  checkout_second_till: "yellow",
  loitering: "yellow",
  dwell_exceeded: "yellow",
  occupancy_exceeded: "yellow",
  shelf_empty: "yellow",
  line_crossed: "blue",
  camera_recovered: "green",
};

/** Noma'lum tur kulrang bo'ladi va lentadan TUSHIB QOLMAYDI.  Yangi
 *  hodisa turi qo'shilganda uni bu yerga yozish esdan chiqsa ham ega
 *  uni ko'radi — faqat rangi betaraf bo'ladi. */
export function toneOf(eventType: string | null | undefined): string {
  return TONE_BY_TYPE[String(eventType || "")] || "grey";
}

const TONE_ORDER = ["red", "yellow", "grey", "green", "blue"];

const TONE_LABELS: Record<string, string> = {
  red: "Xavfsizlik",
  yellow: "Do‘kon ishi",
  blue: "Kirish-chiqish",
  green: "Tiklandi",
  grey: "Boshqa",
};

function segmentsFor(byType: Record<string, number>): TimelineSegment[] {
  const totals: Record<string, number> = {};
  for (const [kind, count] of Object.entries(byType || {})) {
    const tone = toneOf(kind);
    totals[tone] = (totals[tone] || 0) + Number(count || 0);
  }
  // Tartib qat'iy: xavfsizlik doim tepada.  Obyekt kalitlari tartibiga
  // tayanish ustunlarni soatdan soatga sakratardi.
  return TONE_ORDER.filter(tone => totals[tone] > 0).map(tone => ({ tone, value: totals[tone] }));
}

export function EventTimeline({
  siteId,
  date,
  selectedHour = null,
  onSelectHour,
  markedHours = [],
}: {
  siteId?: string;
  date: string;
  selectedHour?: number | null;
  onSelectHour?: (hour: number | null) => void;
  markedHours?: number[];
}) {
  const [answer, setAnswer] = useState<TimelineAnswer | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    setAnswer(null);
    setError("");
    const query = new URLSearchParams({ date });
    api<TimelineAnswer>(`/api/v1/owner/events/timeline?${query}`, "owner", { siteId })
      .then(result => { if (alive) setAnswer(result); })
      .catch(reason => { if (alive) setError(reason instanceof Error ? reason.message : "Lenta olinmadi"); });
    return () => { alive = false; };
  }, [date, siteId]);

  if (error) return <p className="media-note">{error}</p>;
  if (!answer) return <div className="card-body"><Skeleton height={132} /></div>;

  const hours = answer.hours.map(item => ({ hour: item.hour, segments: segmentsFor(item.by_type) }));
  // Bo'sh kunda `Timeline` `null` qaytaradi — ustun chizilmaydi.  Bu
  // yerda esa SABAB aytiladi: bo'sh joy "yuklanmayapti" degan taassurot
  // beradi, matn esa aniq javob.
  if (!answer.total) {
    return <p className="media-note">Bu kunda hodisa qayd etilmagan.</p>;
  }

  const tones = TONE_ORDER.filter(tone =>
    answer.types.some(item => toneOf(item.type) === tone),
  );

  return <>
    <Timeline hours={hours} selected={selectedHour} marked={markedHours} onSelect={onSelectHour} />
    {/* Afsona faqat SHU kuni bor turlardan: bo'lmagan turni ko'rsatish
        "nega nol?" degan javobsiz savol tug'diradi. */}
    <div className="timeline-legend">
      {tones.map(tone => <span key={tone}><i className={`tone-${tone}`} />{TONE_LABELS[tone]}</span>)}
      <span>Jami: <b>{answer.total}</b></span>
    </div>
  </>;
}
