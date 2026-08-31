import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, formatTimeUz, hoursSince, mediaObjectUrl, hasFeature, tashkentDay, tashkentToday } from "./api";
import { Card, EmptyState, PageHeader, PlanLock, Skeleton } from "./components";
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
    return <p className="media-note">Bu turdagi hodisada tasvir saqlanmaydi — maxfiylik qoidasi.</p>;
  }
  if (state === "kutilmoqda") return <p className="media-note">Kadr hali yuklanmagan.</p>;
  return <p className="media-note">Kadr {retentionHours} soat saqlangan, muddati o‘tdi. <b>Hodisaning o‘zi joyida</b> — vaqti, kamerasi va turi tarif muddatigacha qoladi.</p>;
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
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Dalil ochilmadi"); }
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
  return <article className={`evidence-card${focused ? " is-focused" : ""}`} ref={card}><div className="event-row"><div className="event-name"><div className="metric-icon tone-blue" style={{position:"static",width:34,height:34}}><Icon name="pulse" size={17}/></div><div><b>{item.label || item.event_type}</b><small>{item.site_name ? `${item.site_name} · ` : ""}{item.camera_id || "Tizim"} · {kind === "owner" ? formatTimeUz(when) : when || "—"}</small></div></div><div className="page-actions">{hasSnapshot && !image ? <button className="btn" onClick={() => void open("snapshot")}>Kadr</button> : null}{hasClip ? <button className="btn" onClick={() => void open("clip")}>Klip</button> : null}</div></div>{error ? <p className="media-error">{error}</p> : null}{image ? <img className="event-media" src={image} alt={`${item.label || item.event_type} dalili`} /> : null}{video ? <video className="event-media" src={video} controls playsInline /> : null}{!image && !video && !error ? <MediaNote state={state} retentionHours={retentionHours}/> : null}</article>;
}

/** Bir marta ko'rsatiladigan kartochka soni.
 *
 * Kadr endi o'zi yuklanadi, ya'ni har kartochka bitta blob degani.
 * Cheklovsiz ro'yxat gavjum kunda telefon xotirasini yeb qo'yardi. */
const PAGE = 20;

export function EventEvidence({ kind, siteId, sites, focusEventId = "", dashboard, onNavigate }: { kind: "owner" | "admin"; siteId?: string; sites?: Array<{id:string;name:string}>; focusEventId?: string; dashboard?: Dashboard; onNavigate?: (id: string) => void }) {
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
    const path = kind === "owner" ? `/api/v1/owner/events?${query}` : `/api/v1/admin/events${selected ? `?site_id=${encodeURIComponent(selected)}` : ""}`;
    api<{events:Event[]}>(path, kind, { siteId: kind === "owner" ? siteId : undefined })
      .then(result => { setEvents(result.events || []); setError(""); setShown(PAGE); })
      .catch(reason => setError(reason instanceof Error ? reason.message : "Hodisalar olinmadi"));
  }, [day, hour, kind, selected, siteId]);
  useEffect(() => { void load(); }, [load]);

  const yesterday = useMemo(() => tashkentDay(new Date(Date.now() - 86_400_000).toISOString()) || "", []);
  const pick = (value: string) => { setDay(value); setHour(null); setEvents(null); };

  const dayPicker = kind === "owner" && !locked ? <>
    <div className="segmented">
      <button className={day === tashkentToday() ? "active" : ""} onClick={() => pick(tashkentToday())}>Bugun</button>
      <button className={day === yesterday ? "active" : ""} onClick={() => pick(yesterday)}>Kecha</button>
      <button className={day === "" ? "active" : ""} onClick={() => pick("")}>Oxirgi</button>
    </div>
    <input className="input" type="date" value={day} max={tashkentToday()} onChange={event => pick(event.target.value)} aria-label="Kun tanlash"/>
  </> : null;

  const visible = (events || []).slice(0, shown);

  return <><PageHeader title="Hodisalar va dalillar" subtitle="Kun bo‘ylab nima bo‘lganini bir qarashda ko‘ring; kadr faqat u mavjud bo‘lgan hodisada ochiladi." actions={kind === "admin" ? <select className="select" value={selected} onChange={event => setSelected(event.target.value)}><option value="">Barcha filiallar</option>{sites?.map(site => <option value={site.id} key={site.id}>{site.name}</option>)}</select> : <>{dayPicker}<button className="btn" onClick={load}>Yangilash</button></>}/>
    {/* Nima uchun ko'p hodisada tugma yo'qligi ANIQ aytiladi: kirish-chiqish
        qatorlarida rasm bo'lmasligi mijozga "buzilgan"day ko'rinardi. */}
    <div className="alert-strip alert-info"><Icon name="shield"/><div>Rasm va klip maxfiylik uchun faqat <b>xavfsizlik hodisalarida</b> saqlanadi: kamera to‘silsa, ish vaqtidan keyin harakat bo‘lsa yoki taqiqlangan zonaga kirilsa. Oddiy kirish-chiqishlarda tasvir saqlanmaydi.</div></div>
    {error ? <div className="alert-strip alert-info"><Icon name="bell"/>{error}</div> : null}
    {locked
      ? <Card><PlanLock title="Vaqt lentasi va dalillar Biznes tarifida" detail="Kun bo‘ylab nima bo‘lganini bir qarashda ko‘rasiz: soat bo‘yicha lenta, kadrli kartochkalar va klip." onUpgrade={() => onNavigate?.("billing")}/></Card>
      : <>
        {kind === "owner" && day ? <Card><div className="card-head"><div><h2>Kun bo‘ylab</h2><p>{hour == null ? "Soatga bosing — pastdagi ro‘yxat o‘sha soatdan bo‘ladi" : `Tanlangan soat: ${String(hour).padStart(2, "0")}:00`}</p></div></div><EventTimeline siteId={siteId} date={day} selectedHour={hour} onSelectHour={value => { setHour(value); setEvents(null); }}/></Card> : null}
        <Card className={kind === "owner" && day ? "section-gap" : ""}>{events === null ? <div className="card-body"><Skeleton height={180}/></div> : visible.length ? <><div className="evidence-list">{visible.map((item, index) => <Evidence key={item.id || item.event_id || index} item={item} kind={kind} siteId={kind === "owner" ? siteId : selected || item.site_id} retentionHours={retentionHours} autoPhoto={kind === "owner"} focused={Boolean(focusEventId) && (item.id === focusEventId || item.event_id === focusEventId)}/>)}</div>{events.length > shown ? <div className="card-body"><button className="btn btn-wide" onClick={() => setShown(value => value + PAGE)}>Yana {Math.min(PAGE, events.length - shown)} ta ko‘rsatish</button></div> : null}</> : <EmptyState icon="pulse" title="Hodisa yo‘q" detail={day ? "Tanlangan kun (yoki soat) uchun hodisa qayd etilmagan. Boshqa kunni tanlab ko‘ring." : "Qurilma AI hodisa yuborgach uning vaqti va dalili shu yerda ko‘rinadi."}/>}</Card>
      </>}
  </>;
}
