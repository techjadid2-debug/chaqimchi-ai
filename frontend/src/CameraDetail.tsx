import { formatNumber, tashkentToday } from "./api";
import { CamerasBlock } from "./Cameras";
import { Card, EmptyState, PageHeader, StatCard, TabPanel, Tabs } from "./components";
import { EventEvidence } from "./EventEvidence";
import { EventTimeline } from "./EventTimeline";
import { HeatmapThumb } from "./Heatmap";
import { t } from "./i18n";
import { useOverview } from "./overview";
import type { Camera, Dashboard } from "./types";

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
    <Tabs items={CAMERA_TABS.map(id => ({ id, label: t(`panel.camera.tab_${id}`) }))} active={tab} onSelect={id => onNavigate("cameras", cameraId, id)} panelId="camera-panel"/>
    <TabPanel id="camera-panel" activeTab={tab}>{tab === "analytics" ? <>
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
    : tab === "alerts" ? <EventEvidence kind="owner" siteId={siteId} cameraId={cameraId} dashboard={dashboard} onNavigate={onNavigate} embedded/>
    : <>
      <CamerasBlock dashboard={dashboard} siteId={siteId} only={cameraId} expanded/>
      <FaceIdNote camera={camera}/>
    </>}</TabPanel>
  </>;
}


/* Yuz tanish yaroqliligi — "nima qilish kerak" bilan birga.
 *
 * Plitkadagi belgi faqat NIMA ekanini aytadi; bu yerda joy bor, shuning
 * uchun NEGA va NIMA QILISH ham aytiladi.  Chegaralar serverdan keladi
 * (`face_id_state`) — panel ularni qayta hisoblamaydi, aks holda ikki
 * manba bir-biridan ajralib ketardi (`FACE_MIN_BBOX_RATIO` saboqi). */
function FaceIdNote({ camera }: { camera: Camera }) {
  const state = camera.face_id_state;
  /* Kirish kamerasi bo'lmasa jim turadi: davomat faqat shu rolda
     ishlaydi va boshqa kameraga «720p kerak» yozish shovqin. */
  if (camera.role !== "entrance" || !state) return null;
  const size = camera.width && camera.height ? `${camera.width}×${camera.height}` : "";
  if (state === "ok") {
    return <Card className="section-gap"><div className="card-body">
      <div className="note ok"><b>{t("panel.cameras.face_id_ok")}</b>{size ? ` · ${t("panel.cameras.stream_size", { size })}` : ""}</div>
    </div></Card>;
  }
  if (state === "unknown") {
    return <Card className="section-gap"><div className="card-body">
      <div className="note">{t("panel.cameras.face_id_unknown")}</div>
    </div></Card>;
  }
  return <Card className="section-gap"><div className="card-body">
    <div className={state === "low" ? "note warn" : "note"}>
      <b>{t(state === "low" ? "panel.cameras.face_id_low" : "panel.cameras.face_id_edge")}</b>
      {size ? ` · ${t("panel.cameras.stream_size", { size })}` : ""}
      <p>{t(state === "low" ? "panel.cameras.face_id_hint" : "panel.cameras.face_id_edge_hint")}</p>
    </div>
  </div></Card>;
}
