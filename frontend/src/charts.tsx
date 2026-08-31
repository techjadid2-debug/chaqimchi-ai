import { useId, useState } from "react";

/* Grafiklar — yalang'och SVG, kutubxonasiz.
 *
 * Bu yerdagi to'rt shakl (sparkline, chiziq, donut, ustun) butun
 * panelga yetadi; ular uchun ~40 KB'lik chizma kutubxonasi olib
 * kelish panel yuklanishini bekorga sekinlashtiradi.
 *
 * Umumiy qoida: MA'LUMOT BO'LMASA — HECH NARSA CHIZILMAYDI.  Har
 * komponent bo'sh massivda `null` qaytaradi, chaqiruvchi esa uni
 * shunchaki joylashtiradi.  Shu tufayli server hali bermaydigan
 * ko'rsatkich (masalan oylik o'zgarish) uchun karta "0%" degan
 * yolg'on raqamni ko'rsatmaydi, balki o'sha satr umuman chiqmaydi.
 */

export type Point = { label: string; value: number };

/** Karta ichidagi mayda tendensiya chizig'i. */
export function Sparkline({ points, tone = "blue" }: { points: number[]; tone?: "blue" | "green" | "red" }) {
  if (!points || points.length < 2) return null;
  const max = Math.max(...points, 1);
  const min = Math.min(...points, 0);
  const span = max - min || 1;
  const coords = points
    .map((value, index) => {
      const x = (index * 100) / (points.length - 1);
      const y = 26 - ((value - min) / span) * 22;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg className={`sparkline spark-${tone}`} viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden="true">
      <polyline points={coords} />
    </svg>
  );
}

/** Foiz o'zgarishi.  `goodWhenDown` — kamayishi yaxshi bo'lgan
 *  ko'rsatkichlar uchun (masalan kutish vaqti). */
export function Delta({ percent, note, goodWhenDown = false }: { percent: number | null | undefined; note?: string; goodWhenDown?: boolean }) {
  if (percent == null || !Number.isFinite(percent)) return null;
  const up = percent >= 0;
  const good = goodWhenDown ? !up : up;
  const value = `${up ? "+" : ""}${percent.toFixed(1).replace(".", ",").replace(",0", "")}%`;
  return (
    <span className={`delta ${good ? "delta-up" : "delta-down"}`}>
      <span aria-hidden="true">{up ? "▲" : "▼"}</span> {value}
      {note ? <em>{note}</em> : null}
    </span>
  );
}

/** Bir yoki ikki qatorli chiziqli grafik.  Nuqta ustiga kelinganda
 *  qiymat chiqadi — namunadagi "10:00 — 246 tashrif" ilgagi. */
export function LineChart({ series, height = 210 }: { series: { name: string; points: Point[]; tone?: string }[]; height?: number }) {
  const gradientId = useId();
  const [hover, setHover] = useState<number | null>(null);
  const primary = series[0]?.points || [];
  if (primary.length < 2) return null;

  const width = 600;
  const top = 12;
  const bottom = height - 26;
  const max = Math.max(1, ...series.flatMap(line => line.points.map(point => point.value)));
  const xFor = (index: number, total: number) => 12 + (index * (width - 24)) / Math.max(1, total - 1);
  const yFor = (value: number) => bottom - (value / max) * (bottom - top);

  const path = (points: Point[]) => points.map((point, index) => `${xFor(index, points.length).toFixed(1)},${yFor(point.value).toFixed(1)}`).join(" ");
  const step = Math.max(1, Math.ceil(primary.length / 8));

  return (
    <div className="chart-wrap">
      <svg
        className="chart"
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={series.map(line => line.name).join(", ")}
        onMouseLeave={() => setHover(null)}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#4285f4" stopOpacity=".22" />
            <stop offset="1" stopColor="#4285f4" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0.25, 0.5, 0.75, 1].map(fraction => (
          <line key={fraction} className="chart-grid" x1="0" y1={top + (bottom - top) * fraction} x2={width} y2={top + (bottom - top) * fraction} />
        ))}
        <polygon className="chart-area" fill={`url(#${gradientId})`} points={`12,${bottom} ${path(primary)} ${width - 12},${bottom}`} />
        {series.map((line, index) => (
          <polyline key={line.name} className={`chart-line ${index ? "chart-line-alt" : ""}`} points={path(line.points)} />
        ))}
        {hover != null && primary[hover] ? (
          <g>
            <line className="chart-cursor" x1={xFor(hover, primary.length)} y1={top} x2={xFor(hover, primary.length)} y2={bottom} />
            <circle className="chart-dot" cx={xFor(hover, primary.length)} cy={yFor(primary[hover].value)} r="5" />
          </g>
        ) : null}
        {/* Sichqoncha uchun ko'rinmas ustunlar: nozik chiziqni emas,
            keng sohani "ushlash" oson. */}
        {primary.map((point, index) => (
          <rect
            key={`${point.label}-${index}`}
            className="chart-hit"
            x={xFor(index, primary.length) - (width - 24) / primary.length / 2}
            y={0}
            width={(width - 24) / primary.length}
            height={height}
            onMouseEnter={() => setHover(index)}
          />
        ))}
      </svg>
      {hover != null && primary[hover] ? (
        <div className="chart-tip" style={{ left: `${(xFor(hover, primary.length) / width) * 100}%` }}>
          <b>{primary[hover].label}</b>
          {series.map(line => (
            <span key={line.name}>
              {line.name}: {line.points[hover]?.value ?? "—"}
            </span>
          ))}
        </div>
      ) : null}
      <div className="chart-labels">
        {primary.map((point, index) => (
          <span key={`${point.label}-${index}`}>{index % step === 0 ? point.label : ""}</span>
        ))}
      </div>
    </div>
  );
}

export type Segment = { label: string; value: number; tone: string };

/** Halqa diagramma — holat taqsimoti uchun. */
export function Donut({ segments, centerValue, centerLabel }: { segments: Segment[]; centerValue: string; centerLabel: string }) {
  const total = segments.reduce((sum, item) => sum + item.value, 0);
  if (!total) return null;
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;
  return (
    <div className="donut-wrap">
      <svg viewBox="0 0 140 140" className="donut" role="img" aria-label={segments.map(item => `${item.label}: ${item.value}`).join(", ")}>
        {segments
          .filter(item => item.value > 0)
          .map(item => {
            const length = (item.value / total) * circumference;
            const dash = `${length} ${circumference - length}`;
            const element = (
              <circle
                key={item.label}
                className={`donut-seg tone-${item.tone}`}
                cx="70"
                cy="70"
                r={radius}
                strokeDasharray={dash}
                strokeDashoffset={-offset}
              />
            );
            offset += length;
            return element;
          })}
        <text className="donut-value" x="70" y="66">{centerValue}</text>
        <text className="donut-label" x="70" y="86">{centerLabel}</text>
      </svg>
      <ul className="donut-legend">
        {segments.map(item => (
          <li key={item.label}>
            <i className={`tone-${item.tone}`} />
            <span>{item.label}</span>
            <b>{item.value}</b>
            <em>{total ? `${Math.round((item.value / total) * 100)}%` : ""}</em>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Kun bo'ylab vaqt lentasi: 24 ta ustun, har biri turlar bo'yicha bo'lakli.
 *
 * `Bars` bilan bir sinf — kutubxonasiz, CSS ustunlar.  Farqi ikkitasi:
 * ustun ichi bir necha bo'lakdan iborat (qaysi turdagi hodisa) va
 * ustunni bosish mumkin (o'sha soatning kartochkalari ochiladi).
 *
 * `marked` — AI yordamchisi javobining manbalari turgan soatlar.  Ular
 * bosilmaydi, faqat belgilanadi: agent javobi lentada QAYERDA turganini
 * ko'rsatish uchun.
 *
 * Hamma soat nol bo'lsa `null` qaytadi — fayl boshidagi qoida.  Bo'sh
 * kunga 24 ta bo'sh ustun chizish "grafik bor, ma'lumot nol" degan
 * yolg'on taassurot berardi.
 */
export type TimelineSegment = { tone: string; value: number; label?: string };

export function Timeline({
  hours,
  selected = null,
  marked = [],
  onSelect,
  height = 132,
}: {
  hours: { hour: number; segments: TimelineSegment[] }[];
  selected?: number | null;
  marked?: number[];
  onSelect?: (hour: number | null) => void;
  height?: number;
}) {
  const totals = hours.map(item => item.segments.reduce((sum, part) => sum + part.value, 0));
  const peak = Math.max(...totals, 0);
  if (peak <= 0) return null;
  const markedSet = new Set(marked);
  return (
    <div className="timeline" style={{ height }}>
      {hours.map((item, index) => {
        const total = totals[index];
        const isSelected = selected === item.hour;
        const classes = [
          "timeline-col",
          isSelected ? "is-selected" : "",
          markedSet.has(item.hour) ? "is-marked" : "",
          total ? "" : "is-empty",
        ].filter(Boolean).join(" ");
        const title = total
          ? `${String(item.hour).padStart(2, "0")}:00 — ${total} ta`
          : `${String(item.hour).padStart(2, "0")}:00 — hodisa yo‘q`;
        // Bosilmaydigan lentada (agent javobi) ustun tugma bo'lmasin:
        // bosib bo'lmaydigan tugma "buzilibdi" degan taassurot beradi.
        const Tag = onSelect ? "button" : "div";
        return (
          <Tag
            key={item.hour}
            className={classes}
            title={title}
            {...(onSelect
              ? { type: "button" as const, onClick: () => onSelect(isSelected ? null : item.hour) }
              : {})}
          >
            <div className="timeline-stack">
              {total
                ? item.segments
                    .filter(part => part.value > 0)
                    .map((part, partIndex) => (
                      <i
                        key={`${part.tone}-${partIndex}`}
                        className={`tone-${part.tone}`}
                        style={{ height: `${(part.value / peak) * 100}%` }}
                      />
                    ))
                : null}
            </div>
            <span>{item.hour % 3 === 0 ? String(item.hour).padStart(2, "0") : ""}</span>
          </Tag>
        );
      })}
    </div>
  );
}

/** Ustunli diagramma — kunlik to'lovlar kabi diskret qiymatlar uchun. */
export function Bars({ items, height = 120 }: { items: Point[]; height?: number }) {
  if (!items.length) return null;
  const max = Math.max(1, ...items.map(item => item.value));
  const step = Math.max(1, Math.ceil(items.length / 6));
  return (
    <div className="bars" style={{ height }}>
      {items.map((item, index) => (
        <div className="bar-col" key={`${item.label}-${index}`} title={`${item.label}: ${item.value}`}>
          <i style={{ height: `${Math.max(2, (item.value / max) * 100)}%` }} />
          <span>{index % step === 0 ? item.label : ""}</span>
        </div>
      ))}
    </div>
  );
}
