import { useCallback, useEffect, useRef, useState } from "react";
import { api, mediaObjectUrl } from "./api";
import { Card, EmptyState, PageHeader, Skeleton } from "./components";
import { Icon } from "./icons";

type Event = { id?: string; event_id?: string; event_type: string; label?: string; camera_id?: string; site_id?: string; site_name?: string; occurred_at?: string; created_at?: string; snapshot_key?: string; clip_key?: string; has_snapshot?: boolean; has_clip?: boolean };

function Evidence({ item, kind, siteId, focused = false }: { item: Event; kind: "owner" | "admin"; siteId?: string; focused?: boolean }) {
  const [image, setImage] = useState(""); const [video, setVideo] = useState(""); const [error, setError] = useState("");
  const id = item.id || item.event_id || ""; const targetSite = siteId || item.site_id || "";
  // Server ro'yxatda saqlagich kalitlarini bermaydi (ataylab) — bor-yo'qlik
  // faqat bayroqlardan o'qiladi.
  const hasSnapshot = Boolean(item.has_snapshot); const hasClip = Boolean(item.has_clip);
  const base = kind === "owner" ? `/api/v1/owner/events/${encodeURIComponent(id)}` : `/api/v1/admin/sites/${encodeURIComponent(targetSite)}/events/${encodeURIComponent(id)}`;
  /* blob URL'lar ref'da: tozalash FAQAT unmount'da.  Avval cleanup har
     [image, video] o'zgarishida ishlab, kadr ochiq turganda klip ochilsa
     ko'rinib turgan rasm URL'i bekor qilinar va <img> sinardi. */
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
  return <article className={`evidence-card${focused ? " is-focused" : ""}`} ref={card}><div className="event-row"><div className="event-name"><div className="metric-icon tone-blue" style={{position:"static",width:34,height:34}}><Icon name="pulse" size={17}/></div><div><b>{item.label || item.event_type}</b><small>{item.site_name ? `${item.site_name} · ` : ""}{item.camera_id || "Tizim"} · {item.occurred_at || item.created_at || "—"}</small></div></div><div className="page-actions">{hasSnapshot ? <button className="btn" onClick={() => void open("snapshot")}>Kadr</button> : null}{hasClip ? <button className="btn" onClick={() => void open("clip")}>Klip</button> : null}</div></div>{error ? <p className="media-error">{error}</p> : null}{image ? <img className="event-media" src={image} alt={`${item.label || item.event_type} dalili`} /> : null}{video ? <video className="event-media" src={video} controls playsInline /> : null}</article>;
}

export function EventEvidence({ kind, siteId, sites, focusEventId = "" }: { kind: "owner" | "admin"; siteId?: string; sites?: Array<{id:string;name:string}>; focusEventId?: string }) {
  const [events, setEvents] = useState<Event[] | null>(null); const [error, setError] = useState(""); const [selected, setSelected] = useState(siteId || "");
  const load = useCallback(() => { const path = kind === "owner" ? "/api/v1/owner/events?limit=100" : `/api/v1/admin/events${selected ? `?site_id=${encodeURIComponent(selected)}` : ""}`; api<{events:Event[]}>(path, kind, { siteId: kind === "owner" ? siteId : undefined }).then(result => { setEvents(result.events || []); setError(""); }).catch(reason => setError(reason instanceof Error ? reason.message : "Hodisalar olinmadi")); }, [kind, selected, siteId]);
  useEffect(() => { void load(); }, [load]);
  return <><PageHeader title="Hodisalar va dalillar" subtitle="Kadr yoki klip faqat u mavjud bo‘lgan eventda ochiladi." actions={kind === "admin" ? <select className="select" value={selected} onChange={event => setSelected(event.target.value)}><option value="">Barcha filiallar</option>{sites?.map(site => <option value={site.id} key={site.id}>{site.name}</option>)}</select> : <button className="btn" onClick={load}>Yangilash</button>}/>
    {/* Nima uchun ko'p hodisada tugma yo'qligi ANIQ aytiladi: kirish-chiqish
        qatorlarida rasm bo'lmasligi mijozga "buzilgan"day ko'rinardi. */}
    <div className="alert-strip alert-info"><Icon name="shield"/><div>Rasm va klip maxfiylik uchun faqat <b>xavfsizlik hodisalarida</b> saqlanadi: kamera to‘silsa, ish vaqtidan keyin harakat bo‘lsa yoki taqiqlangan zonaga kirilsa. Oddiy kirish-chiqishlarda tasvir saqlanmaydi.</div></div>
    {error ? <div className="alert-strip alert-info"><Icon name="bell"/>{error}</div> : null}<Card>{events === null ? <div className="card-body"><Skeleton height={180}/></div> : events.length ? <div className="evidence-list">{events.map((item, index) => <Evidence key={item.id || item.event_id || index} item={item} kind={kind} siteId={kind === "owner" ? siteId : selected || item.site_id} focused={Boolean(focusEventId) && (item.id === focusEventId || item.event_id === focusEventId)}/>)}</div> : <EmptyState icon="pulse" title="Hodisa yo‘q" detail="Qurilma AI hodisa yuborgach uning vaqti va dalili shu yerda ko‘rinadi."/>}</Card></>;
}
