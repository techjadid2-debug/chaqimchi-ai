import { useState } from "react";
import { api, formatNumber } from "./api";
import { Card } from "./components";
import { t } from "./i18n";
import type { Conversion, Dashboard, DailySales, DoorCount } from "./types";

/* «Raqamlar» — kunning marketing yakuni bitta kartada.
 *
 * Ilgari bu raqamlar panel bo'ylab tarqoq turardi: tashrif bosh
 * sahifada, demografiya alohida kartada, eshik taqsimoti esa umuman
 * ko'rsatilmasdi (server uni yozib turardi-yu hech kim o'qimasdi).
 * Do'kon egasining savoli esa bitta: «bugun qanday o'tdi».
 *
 * IKKI MANBA, bir karta:
 *
 * * kirdi/chiqdi, eshik taqsimoti, gavjum soat — BIZDAN (kameradan);
 * * chek soni — EGADAN.  Kassa integratsiyasi yo'q, shuning uchun
 *   konversiyaning surati faqat qo'lda kiritiladi.
 *
 * Konversiya foizini panel O'ZI hisoblamaydi — u serverdan tayyor
 * keladi (`cloud/value.py`).  Sababi: «kichik namunadan foiz
 * chiqarmang» qoidasi ikki joyda yozilsa, ular albatta uzoqlashadi va
 * Telegram xabari bilan panel bir kun haqida ikki xil gapiradi. */

type Traffic = {
  entered?: number;
  exited?: number;
  xodim_chiqarilgan?: number;
  by_door?: DoorCount[];
  busiest_hour?: { hour: number; entered: number } | null;
};

export function Numbers({ dashboard, siteId }: { dashboard: Dashboard; siteId: string }) {
  const traffic = ((dashboard.today as Record<string, unknown>).traffic || {}) as Traffic;
  /* Saqlagandan keyin serverning javobi ustun turadi: `dashboard`
     keyingi yangilanishgacha eski qiymatni ko'rsatib turardi va ega
     "saqlanmadi shekilli" deb ikkinchi marta bosardi. */
  const [saved, setSaved] = useState<{ sales: DailySales; conversion: Conversion | null } | null>(null);
  const sales = saved ? saved.sales : dashboard.today.sales || null;
  const conversion = saved ? saved.conversion : dashboard.today.conversion || null;

  const entered = Number(traffic.entered || 0);
  const exited = Number(traffic.exited || 0);
  const staff = Number(traffic.xodim_chiqarilgan || 0);
  const doors = traffic.by_door;
  const busiest = traffic.busiest_hour;

  return <Card>
    <div className="card-head">
      <div>
        <h2>{t("panel.numbers.title")}</h2>
        <p>{t("panel.numbers.subtitle")}</p>
      </div>
    </div>

    {/* `.summary-strip` mavjud naqsh — yangi to'r kiritilmaydi. */}
    <div className="summary-strip">
      <div><span>{t("panel.numbers.entered")}</span><b>{formatNumber(entered)}</b></div>
      <div><span>{t("panel.numbers.exited")}</span><b>{formatNumber(exited)}</b></div>
      {/* Xodim o'tishi sanoqdan CHIQARILGANI ochiq aytiladi: aks holda
          "kecha 210 edi, bugun 190" farqini ega tushuntira olmaydi. */}
      <div><span>{t("panel.numbers.staff_excluded")}</span><b>{formatNumber(staff)}</b></div>
      <div>
        <span>{t("panel.numbers.busiest_hour")}</span>
        <b>{busiest ? `${String(busiest.hour).padStart(2, "0")}:00` : "—"}</b>
      </div>
    </div>

    <ReceiptsBlock
      siteId={siteId}
      entered={entered}
      sales={sales}
      conversion={conversion}
      onSaved={setSaved}
    />

    <DoorSplit doors={doors} />
  </Card>;
}

/** Chek soni: ko'rsatish va kiritish bitta joyda. */
function ReceiptsBlock({ siteId, entered, sales, conversion, onSaved }: {
  siteId: string;
  entered: number;
  sales: DailySales | null;
  conversion: Conversion | null;
  onSaved: (value: { sales: DailySales; conversion: Conversion | null }) => void;
}) {
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function save() {
    const receipts = Number(draft);
    if (!draft.trim() || !Number.isInteger(receipts) || receipts < 0) {
      setError(t("panel.numbers.receipts_invalid"));
      return;
    }
    setBusy(true);
    setError("");
    try {
      const answer = await api<{ sales: DailySales; conversion: Conversion | null }>(
        "/api/v1/owner/sales",
        "owner",
        { siteId, method: "PUT", body: JSON.stringify({ receipts }) },
      );
      onSaved({ sales: answer.sales, conversion: answer.conversion ?? null });
      setDraft("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("panel.numbers.save_failed"));
    } finally {
      setBusy(false);
    }
  }

  return <div className="receipts">
    {conversion ? (
      <p className="receipts-line">
        {/* Foiz FAQAT server bergan bo'lsa chiqadi.  12 kishilik kunning
            "67% konversiyasi" o'lchov emas, tasodif — bunday kunda ega
            faqat sonlarni ko'radi. */}
        {t("panel.numbers.bought")} <b>{formatNumber(conversion.receipts)}</b>
        {conversion.percent !== null
          ? <> {t("panel.numbers.with_percent", { percent: conversion.percent, entered: formatNumber(conversion.entered) })}</>
          : <> · {t("panel.numbers.without_percent", { entered: formatNumber(conversion.entered) })}</>}
      </p>
    ) : (
      /* Nol emas, BO'SH.  Nol «hech kim sotib olmadi» degani; kiritilmagan
         kun esa «ma'lumot yo'q». */
      <p className="receipts-line receipts-empty">
        {t("panel.numbers.no_receipts")}
      </p>
    )}

    <div className="receipts-form">
      <input
        className="input"
        type="number"
        min={0}
        inputMode="numeric"
        placeholder={sales ? String(sales.receipts) : t("panel.numbers.receipts_placeholder")}
        value={draft}
        onChange={event => setDraft(event.target.value)}
      />
      <button className="btn" onClick={save} disabled={busy}>
        {busy ? t("panel.common.saving") : sales ? t("panel.numbers.update") : t("panel.common.save")}
      </button>
      <span className="receipts-hint">
        {t("panel.numbers.telegram_hint")} <code>/chek 100</code>
      </span>
    </div>
    {error ? <p className="receipts-error">{error}</p> : null}
    {entered === 0 ? (
      <p className="receipts-hint">{t("panel.numbers.no_entries")}</p>
    ) : null}
  </div>;
}

/** Qaysi eshikdan kirishdi.  Ko'p eshikli do'konning birinchi savoli. */
function DoorSplit({ doors }: { doors?: DoorCount[] }) {
  /* Kalitning YO'QLIGI va BO'SH ro'yxati — ikki boshqa javob.
     Yo'q: bu kun eski (taqsimot yozilmagan paytda yig'ilgan).
     Bo'sh: kun yozilgan, lekin o'tish bo'lmagan. */
  if (doors === undefined) {
    return <p className="receipts-hint">{t("panel.numbers.doors_missing")}</p>;
  }
  if (!doors.length) return null;
  const most = Math.max(...doors.map(door => door.entered), 1);
  return <div className="doors">
    <h3>{t("panel.numbers.doors_title")}</h3>
    {doors.map(door => (
      <div className="door-row" key={`${door.camera_id}-${door.line || ""}`}>
        <span className="door-name">{door.label || door.camera_id}</span>
        <span className="door-bar"><i style={{ width: `${Math.round((door.entered / most) * 100)}%` }} /></span>
        <span className="door-count">
          {t("panel.numbers.door_counts", { entered: formatNumber(door.entered), exited: formatNumber(door.exited) })}
        </span>
      </div>
    ))}
  </div>;
}
