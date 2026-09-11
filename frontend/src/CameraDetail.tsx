import { formatNumber, tashkentToday } from "./api";
import { CamerasBlock } from "./Cameras";
import { Card, EmptyState, PageHeader, StatCard, Tabs } from "./components";
import { EventEvidence } from "./EventEvidence";
import { EventTimeline } from "./EventTimeline";
import { HeatmapThumb } from "./Heatmap";
import { t } from "./i18n";
import { useOverview } from "./overview";
import type { Dashboard } from "./types";

/* Alohida kamera sahifasi — dizayn-3 «Camera 01» ekrani: jonli kadr,
 * shu kameraning tahlili va hodisalari.  Manzil: `/owner/cameras/<id>/<tab>`.
 *
 * Tablar `TABS` ro'yxatiga QO'SHILMAYDI: u bo'lim tablari (jonli/ulash/
 * chiziq) — kamera tablari boshqa darajada va o'z ro'yxatida turadi.
 * Ma'lumot yangi endpoint talab qilmaydi: heatmap, hodisalar va lenta
 * allaqachon `camera_id` bilan filtrlanadi, eshik sanog'i esa
 * `overview.by_door` da kamera bo'yicha keladi. */

export const CAMERA_TABS = ["live", "analytics", "alerts"] as const;

export function CameraDetail({ dashboard, siteId, cameraId, tab, onNavigate }: {
  dashboard: Dashboard;
  siteId: string;
  cameraId: string;
  tab: string;
  onNavigate: (id: string, param?: string, sub?: string) => void;
}) {
  const camera = dashboard.cameras.find(item => item.camera_id === cameraId);
  const state = dashboard.camera_states.find(item => item.camera_id === cameraId);
  const stateId = state?.state || "unknown";
  /* 7 kun — «bu kamera umuman sanaydimi?» savoliga yetarli; davr
     tanlagichi bosh sahifada, bu yerda takrorlanmaydi. */
  const { overview } = useOverview(siteId, 7);
  const door = (overview?.by_door || []).find(item => item.camera_id === cameraId);
  const back = <button className="btn" onClick={() => onNavigate("cameras")}>{t("panel.common.back")}</button>;

  if (!camera) {
    return <>
      <PageHeader title={cameraId} subtitle={t("panel.camera.missing")} actions={back}/>
      <Card><EmptyState icon="camera" title={t("panel.camera.missing")} detail={t("panel.camera.missing_detail")}/></Card>
    </>;
  }
  const label = camera.label || camera.camera_id;
  const stateKey = `panel.cameras.state_${stateId}`;
  const stateText = t(stateKey) === stateKey ? t("panel.cameras.state_unknown") : t(stateKey);

  return <>
    <PageHeader title={label} subtitle={state?.reason || t("panel.cameras.state_loading")} actions={back}/>
    <Tabs items={CAMERA_TABS.map(id => ({ id, label: t(`panel.camera.tab_${id}`) }))} active={tab} onSelect={id => onNavigate("cameras", cameraId, id)}/>
    {tab === "analytics" ? <>
      <div className="metric-grid metric-grid-3">
        <StatCard label={t("panel.numbers.entered")} value={door ? formatNumber(door.entered) : "—"} note={door ? t("panel.camera.last_7_days") : t("panel.camera.no_door_note")} icon="entry" tone="blue"/>
        <StatCard label={t("panel.numbers.exited")} value={door ? formatNumber(door.exited) : "—"} note={door ? t("panel.camera.last_7_days") : t("panel.camera.no_door_note")} icon="entry" tone="green"/>
        <StatCard label={t("panel.camera.state")} value={stateText} note={state?.reason || ""} icon="camera" tone={stateId === "online" ? "green" : stateId === "stale" ? "yellow" : "red"}/>
      </div>
      <Card className="section-gap">
        <div className="card-head">
          <div><h2>{t("panel.heat.title")}</h2><p>{t("panel.camera.heat_subtitle")}</p></div>
          <button className="btn" onClick={() => onNavigate("customers", "heatmap")}>{t("panel.home.heat.open")}</button>
        </div>
        <div className="heat-thumb-wrap"><HeatmapThumb siteId={siteId} cameraId={cameraId} width={960} height={540}/></div>
      </Card>
      <Card className="section-gap">
        <div className="card-head"><div><h2>{t("panel.evidence.day_title")}</h2><p>{t("panel.camera.timeline_subtitle")}</p></div></div>
        <EventTimeline siteId={siteId} date={tashkentToday()} cameraId={cameraId}/>
      </Card>
    </>
    : tab === "alerts" ? <EventEvidence kind="owner" siteId={siteId} cameraId={cameraId} dashboard={dashboard} onNavigate={onNavigate}/>
    : <CamerasBlock dashboard={dashboard} siteId={siteId} only={cameraId} expanded/>}
  </>;
}
