import { eventLabel, t } from "./i18n";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, formatTimeUz, hoursSince, mediaObjectUrl, hasFeature, tashkentDay, tashkentToday } from "./api";
import { Card, EmptyState, ErrorStrip, PageHeader, PlanLock, Skeleton } from "./components";
import { EventTimeline } from "./EventTimeline";
import { Icon } from "./icons";
import type { Dashboard } from "./types";

type Event = { id?: string; event_id?: string; event_type: string; label?: string; camera_id?: string; site_id?: string; site_name?: string; occurred_at?: string; created_at?: string; snapshot_key?: string; clip_key?: string; has_snapshot?: boolean; has_clip?: boolean; media_expected?: boolean };

/* Kadr holati — TO'RT javob, va ularni chalkashtirish mumkin emas.
 *
 * Jonli bazada media bayrog'i bor-u kaliti yo'q 39 ta qator bor edi va
 * panel ular uchun 404 beradigan tugma ko'rsatardi.  Bundan ham
 * yomoni — "kadr hali yuklanmagan" bilan "bu turda kadr UMUMAN
 * olinmaydi" bir xil ko'rinardi: birinchisi kutish, ikkinchisi qoida.
 *
 * Muddat serverdan keladi (`dashboard.media_retention_hours`).  48 ni
 * shu faylga yozish "ikki fayldagi ikki son bir-birini inkor qiladi"
 * tuzog'i bo'lardi.
 */
type MediaState = "bor" | "saqlanmaydi" | "kutilmoqda" | "muddati_otdi";

export function mediaState(item: Event, retentionHours: number): MediaState {
  if (item.has_snapshot || item.has_clip) return "bor";
  if (item.media_expected === false) return "saqlanmaydi";
  const age = hoursSince(item.occurred_at || item.created_at);
  if (age != null && age > retentionHours) return "muddati_otdi";
  return "kutilmoqda";
}

function MediaNote({ state, retentionHours }: { state: MediaState; retentionHours: number }) {
  if (state === "bor") return null;
  if (state === "saqlanmaydi") {
    return <p className="media-note">{t("panel.evidence.media_not_kept")}</p>;
  }
  if (state === "kutilmoqda") return <p className="media-note">{t("panel.evidence.media_pending")}</p>;
  return <p className="media-note">{t("panel.evidence.media_expired", { hours: retentionHours })} <b>{t("panel.evidence.media_expired_kept")}</b> {t("panel.evidence.media_expired_detail")}</p>;
}

function Evidence({ item, kind, siteId, focused = false, retentionHours = 0, autoPhoto = false }: { item: Event; kind: "owner" | "admin"; siteId?: string; focused?: boolean; retentionHours?: number; autoPhoto?: boolean }) {
  const [image, setImage] = useState(""); const [video, setVideo] = useState(""); const [error, setError] = useState("");
  const id = item.id || item.event_id || ""; const targetSite = siteId || item.site_id || "";
  // Server ro'yxatda saqlagich kalitlarini bermaydi (ataylab) — bor-yo'qlik
  // faqat bayroqlardan o'qiladi.
  const hasSnapshot = Boolean(item.has_snapshot); const hasClip = Boolean(item.has_clip);
  const base = kind === "owner" ? `/api/v1/owner/events/${encodeURIComponent(id)}` : `/api/v1/admin/sites/${encodeURIComponent(targetSite)}/events/${encodeURIComponent(id)}`;
  /* blob URL'lar ref'da: tozalash FAQAT unmount'da.  Avval cleanup har
     [image, video] o'zgarishida ishlab, kadr ochiq turganda klip ochilsa
     ko'rinib turgan rasm URL'i bekor qilinar va <img> sinardi.
     Kadr endi O'ZI yuklanadi, ya'ni bir vaqtda o'nlab blob ochiq
     bo'lishi mumkin — shu tozalash endi ancha muhimroq. */
  const urls = useRef<{image:string; video:string}>({ image: "", video: "" });
  const open = useCallback(async (part: "snapshot" | "clip") => {
    try {
      const url = await mediaObjectUrl(`${base}/${part}`, kind, targetSite || undefined);
      if (part === "snapshot") {
        if (urls.current.image) URL.revokeObjectURL(urls.current.image);
        urls.current.image = url; setImage(url);
      } else {
        if (urls.current.video) URL.revokeObjectURL(urls.current.video);
        urls.current.video = url; setVideo(url);
      }
      setError("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : t("panel.evidence.open_failed")); }
  }, [base, kind, targetSite]);
  useEffect(() => () => { if (urls.current.image) URL.revokeObjectURL(urls.current.image); if (urls.current.video) URL.revokeObjectURL(urls.current.video); }, []);
  /* Kartochka RASMLI bo'lishi kerak — ega hodisani o'qib emas, ko'rib
     tushunadi.  Shuning uchun kadr tugma kutmasdan ochiladi. */
  useEffect(() => { if (autoPhoto && hasSnapshot) void open("snapshot"); }, [autoPhoto, hasSnapshot, open]);
  /* AI yordamchisidan "Dalilni ochish" bosilganda aynan SHU hodisa
     ochiladi va ekranga suriladi.  Ilgari tugma `event_id` ni umuman
     ishlatmasdi va faqat umumiy ro'yxatni ochardi — ya'ni nomi
     va'da qilgan narsani bajarmasdi. */
  const card = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!focused) return;
    card.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    if (hasSnapshot) void open("snapshot");
  }, [focused, hasSnapshot, open]);
  const when = item.occurred_at || item.created_at;
  const state = kind === "owner" ? mediaState(item, retentionHours) : "bor";
  return <article className={`evidence-card${focused ? " is-focused" : ""}`} ref={card}><div className="event-row"><div className="event-name"><div className="metric-icon tone-blue" style={{position:"static",width:34,height:34}}><Icon name="pulse" size={17}/></div><div><b>{eventLabel(item.event_type)}</b><small>{item.site_name ? `${item.site_name} · ` : ""}{item.camera_id || t("panel.evidence.system")} · {kind === "owner" ? formatTimeUz(when) : when || "—"}</small></div></div><div className="page-actions">{hasSnapshot && !image ? <button className="btn" onClick={() => void open("snapshot")}>{t("panel.evidence.photo")}</button> : null}{hasClip ? <button className="btn" onClick={() => void open("clip")}>{t("panel.evidence.clip")}</button> : null}</div></div>{error ? <p className="media-error">{error}</p> : null}{image ? <img className="event-media" src={image} alt={t("panel.event.evidence_alt", { label: eventLabel(item.event_type) })} /> : null}{video ? <video className="event-media" src={video} controls playsInline /> : null}{!image && !video && !error ? <MediaNote state={state} retentionHours={retentionHours}/> : null}</article>;
}

/** Bir marta ko'rsatiladigan kartochka soni.
 *
 * Kadr endi o'zi yuklanadi, ya'ni har kartochka bitta blob degani.
 * Cheklovsiz ro'yxat gavjum kunda telefon xotirasini yeb qo'yardi. */
const PAGE = 20;

export function EventEvidence({ kind, siteId, sites, focusEventId = "", dashboard, onNavigate, cameraId = "" }: { kind: "owner" | "admin"; siteId?: string; sites?: Array<{id:string;name:string}>; focusEventId?: string; dashboard?: Dashboard; onNavigate?: (id: string) => void; cameraId?: string }) {
  const [events, setEvents] = useState<Event[] | null>(null); const [error, setError] = useState(""); const [selected, setSelected] = useState(siteId || "");
  /* "" — sanasiz "oxirgi hodisalar" rejimi.  U ikki holatda kerak:
     AI yordamchisi eski kundagi dalilga yo'naltirganda (kun bo'yicha
     filtr uni yashirib qo'yardi) va ega shunchaki "nima bo'ldi?" deb
     kirganda. */
  const [day, setDay] = useState(focusEventId ? "" : tashkentToday());
  const [hour, setHour] = useState<number | null>(null);
  const [shown, setShown] = useState(PAGE);
  const retentionHours = Number(dashboard?.media_retention_hours) || 48;
  const locked = kind === "owner" && dashboard != null && !hasFeature(dashboard, "xavfsizlik");

  const load = useCallback(() => {
    const query = new URLSearchParams({ limit: "100" });
    if (day) { query.set("date", day); if (hour != null) query.set("hour", String(hour)); }
    // Kamera sahifasi: faqat shu kameraning hodisalari (server filtri).
    if (cameraId) query.set("camera_id", cameraId);
    const path = kind === "owner" ? `/api/v1/owner/events?${query}` : `/api/v1/admin/events${selected ? `?site_id=${encodeURIComponent(selected)}` : ""}`;
    api<{events:Event[]}>(path, kind, { siteId: kind === "owner" ? siteId : undefined })
      .then(result => { setEvents(result.events || []); setError(""); setShown(PAGE); })
      // Xatoda ro'yxat BO'SH bo'ladi, `null` emas: `null` — «hali
      // yuklanmoqda», ya'ni skelet.  Ilgari xato chizig'i bilan yonma-yon
      // skelet abadiy turib qolardi.
      .catch(reason => { setEvents([]); setError(reason instanceof Error ? reason.message : t("panel.evidence.load_failed")); });
  }, [cameraId, day, hour, kind, selected, siteId]);
  useEffect(() => { void load(); }, [load]);

  const yesterday = useMemo(() => tashkentDay(new Date(Date.now() - 86_400_000).toISOString()) || "", []);
  const pick = (value: string) => { setDay(value); setHour(null); setEvents(null); };

  const dayPicker = kind === "owner" && !locked ? <>
    <div className="segmented">
      <button className={day === tashkentToday() ? "active" : ""} onClick={() => pick(tashkentToday())}>{t("panel.common.today")}</button>
      <button className={day === yesterday ? "active" : ""} onClick={() => pick(yesterday)}>{t("panel.common.yesterday")}</button>
      <button className={day === "" ? "active" : ""} onClick={() => pick("")}>{t("panel.evidence.latest")}</button>
    </div>
    <input className="input" type="date" value={day} max={tashkentToday()} onChange={event => pick(event.target.value)} aria-label={t("panel.evidence.pick_day")}/>
  </> : null;

  const visible = (events || []).slice(0, shown);

  return <><PageHeader title={t("panel.evidence.title")} subtitle={t("panel.evidence.subtitle")} actions={kind === "admin" ? <select className="select" value={selected} onChange={event => setSelected(event.target.value)}><option value="">{t("panel.evidence.all_sites")}</option>{sites?.map(site => <option value={site.id} key={site.id}>{site.name}</option>)}</select> : <>{dayPicker}<button className="btn" onClick={load}>{t("panel.common.refresh")}</button></>}/>
    {/* Nima uchun ko'p hodisada tugma yo'qligi ANIQ aytiladi: kirish-chiqish
        qatorlarida rasm bo'lmasligi mijozga "buzilgan"day ko'rinardi. */}
    <div className="alert-strip alert-info"><Icon name="shield"/><div>{t("panel.evidence.privacy_before")} <b>{t("panel.evidence.privacy_bold")}</b> {t("panel.evidence.privacy_after")}</div></div>
    {error ? <ErrorStrip detail={error} onRetry={() => { setEvents(null); void load(); }}/> : null}
    {locked
      ? <Card><PlanLock title={t("panel.evidence.lock_title")} detail={t("panel.evidence.lock_detail")} onUpgrade={() => onNavigate?.("billing")}/></Card>
      : <>
        {kind === "owner" && day ? <Card><div className="card-head"><div><h2>{t("panel.evidence.day_title")}</h2><p>{hour == null ? t("panel.evidence.pick_hour_hint") : t("panel.evidence.selected_hour", { hour: String(hour).padStart(2, "0") })}</p></div></div><EventTimeline siteId={siteId} date={day} selectedHour={hour} onSelectHour={value => { setHour(value); setEvents(null); }}/></Card> : null}
        <Card className={kind === "owner" && day ? "section-gap" : ""}>{events === null ? <div className="card-body"><Skeleton height={180}/></div> : visible.length ? <><div className="evidence-list">{visible.map((item, index) => <Evidence key={item.id || item.event_id || index} item={item} kind={kind} siteId={kind === "owner" ? siteId : selected || item.site_id} retentionHours={retentionHours} autoPhoto={kind === "owner"} focused={Boolean(focusEventId) && (item.id === focusEventId || item.event_id === focusEventId)}/>)}</div>{events.length > shown ? <div className="card-body"><button className="btn btn-wide" onClick={() => setShown(value => value + PAGE)}>{t("panel.evidence.show_more", { count: Math.min(PAGE, events.length - shown) })}</button></div> : null}</> : <EmptyState icon="pulse" title={t("panel.evidence.empty_title")} detail={day ? t("panel.evidence.empty_day") : t("panel.evidence.empty_recent")}/>}</Card>
      </>}
  </>;
}
