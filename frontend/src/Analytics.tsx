import { useState } from "react";
import { formatNumber, hasFeature } from "./api";
import { Bars, Delta, Donut, GroupedBars, LineChart, type Point } from "./charts";
import { Card, EmptyState, ErrorStrip, PageHeader, PlanLock, Skeleton } from "./components";
import { t } from "./i18n";
import { PeriodBar, dayLabel, eventSegments, eventTotal, hasAnyReceipts, periodDays, readPeriod, savePeriod, useOverview, type Period } from "./overview";
import type { Dashboard } from "./types";

/* «Tahlil» — to'rt grafik, kunlar kesimida.
 *
 * Bosh sahifadagi «Mijozlar tahlili» kartasi shu sahifaning qisqa
 * ko'rinishi; to'lig'i shu yerda: kirish trendi, eshik bo'yicha
 * kirdi/chiqdi, hodisalar taqsimoti va konversiya.  Hammasi bitta
 * so'rovdan (`useOverview`).  Ma'lumot bo'lmasa grafik chizilmaydi —
 * nima yetishmayotgani va uni qayerdan olish aytiladi. */

const OPTIONS: Period[] = ["7", "14", "30"];

export function Analytics({ dashboard, siteId, onNavigate }: { dashboard: Dashboard; siteId: string; onNavigate: (id: string, param?: string) => void }) {
  /* «Bugun» bu sahifada ma'nosiz (kunlar kesimi) — saqlangan tanlov
     «Bugun» bo'lsa 7 kunga tushadi, saqlangan qiymat esa buzilmaydi. */
  const [period, setPeriod] = useState<Period>(() => { const stored = readPeriod("7"); return stored === "today" ? "7" : stored; });
  const { overview, loading, error } = useOverview(siteId, periodDays(period));
  const choose = (next: Period) => { setPeriod(next); savePeriod(next); };

  const daily = overview?.daily || [];
  const totals = overview?.totals;
  const trend: Point[] = daily.map(day => ({ label: dayLabel(day.date), value: day.entered }));
  const doors = (overview?.by_door || []).filter(door => door.entered || door.exited);
  const segments = eventSegments(overview?.events);
  const securityOpen = hasFeature(dashboard, "xavfsizlik");
  const withReceipts = hasAnyReceipts(daily);
  const conversion = totals?.conversion;

  return <>
    <PageHeader title={t("panel.nav.analytics")} subtitle={t("panel.analytics.subtitle")} actions={<PeriodBar value={period} options={OPTIONS} onChange={choose}/>}/>
    {error ? <ErrorStrip detail={error}/> : null}
    <div className="analytics-grid">
      <Card>
        <div className="card-head">
          <div><h2>{t("panel.analytics.trend.title")}</h2><p>{t("panel.analytics.trend.subtitle")}</p></div>
          {totals ? <div className="card-figure"><b>{t("panel.analytics.trend.total", { count: formatNumber(totals.entered) })}</b><Delta percent={totals.change_percent} note={t("panel.period.vs_previous")}/></div> : null}
        </div>
        {loading && !overview ? <div className="card-body"><Skeleton height={150}/></div>
          : totals && totals.entered > 0 ? <Bars items={trend} height={170}/>
          : <EmptyState icon="chart" title={t("panel.analytics.trend.empty_title")} detail={t("panel.analytics.trend.empty_detail")}/>}
      </Card>

      <Card>
        <div className="card-head"><div><h2>{t("panel.analytics.doors.title")}</h2><p>{t("panel.analytics.doors.subtitle")}</p></div></div>
        {loading && !overview ? <div className="card-body"><Skeleton height={150}/></div>
          : doors.length ? <GroupedBars groups={doors.map(door => ({
              label: door.label || door.line || door.camera_id,
              values: [
                { name: t("panel.numbers.entered"), value: door.entered, tone: "blue" },
                { name: t("panel.numbers.exited"), value: door.exited, tone: "green" },
              ],
            }))}/>
          : <EmptyState icon="shapes" title={t("panel.analytics.doors.empty_title")} detail={t("panel.analytics.doors.empty_detail")}/>}
      </Card>

      <Card>
        <div className="card-head"><div><h2>{t("panel.home.mix.title")}</h2><p>{t("panel.home.mix.subtitle")}</p></div></div>
        {!securityOpen ? <PlanLock title={t("panel.home.mix.lock_title")} detail={t("panel.home.mix.lock_detail")} onUpgrade={() => onNavigate("settings", "billing")}/>
          : loading && !overview ? <div className="card-body"><Skeleton height={150}/></div>
          : segments.length ? <Donut segments={segments} centerValue={formatNumber(eventTotal(overview?.events))} centerLabel={t("panel.home.mix.center")}/>
          : <EmptyState icon="shield" title={t("panel.home.mix.empty_title")} detail={t("panel.home.mix.empty_detail")}/>}
      </Card>

      <Card>
        <div className="card-head">
          <div><h2>{t("panel.analytics.conversion.title")}</h2><p>{t("panel.analytics.conversion.subtitle")}</p></div>
          {conversion ? <div className="card-figure"><b>{conversion.percent == null
            ? t("panel.analytics.conversion.counts", { receipts: formatNumber(conversion.receipts), entered: formatNumber(conversion.entered) })
            : t("panel.analytics.conversion.percent", { percent: conversion.percent })}</b></div> : null}
        </div>
        {loading && !overview ? <div className="card-body"><Skeleton height={150}/></div>
          : withReceipts ? <LineChart series={[
              { name: t("panel.numbers.entered"), points: trend },
              /* Chek kiritilmagan kun NOL emas — o'sha nuqta chiziqdan tushib qoladi. */
              { name: t("panel.analytics.conversion.receipts"), points: daily.map(day => ({ label: dayLabel(day.date), value: day.receipts ?? Number.NaN })) },
            ]}/>
          : <EmptyState icon="invoice" title={t("panel.analytics.conversion.empty_title")} detail={t("panel.analytics.conversion.empty_detail")}/>}
      </Card>
    </div>
  </>;
}
