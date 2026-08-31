import { useCallback, useEffect, useRef, useState } from "react";
import { api, formatTimeUz, tashkentDay, tashkentHour, tashkentToday, tokenFor } from "./api";
import { Card, EmptyState, PageHeader, Skeleton } from "./components";
import { EventTimeline } from "./EventTimeline";
import { Icon } from "./icons";

type Settings = { consented: boolean; audio_reply_enabled: boolean; provider_configured: boolean };
type Source = { event_id: string; camera_id?: string; occurred_at?: string; label?: string; event_type?: string; has_snapshot?: boolean; has_clip?: boolean; observation?: { summary?: string; confidence?: number } };
/* `parsed` — savolning offlayn tahlili (`cloud/vision_agent.py:parse_query`).
   U javobga allaqachon qo'shiladi, ya'ni "qaysi kun haqida so'ralgan"
   savoliga backendga yangi maydon qo'shmasdan javob bor. */
type Job = { job_id: string; status: "queued" | "running" | "completed" | "failed"; error?: string; has_audio_reply?: boolean; result?: { answer?: string; sources?: Source[]; parsed?: { start_at?: string; end_at?: string; camera_id?: string | null } } };

/** Javob qaysi kunga tegishli.
 *
 * Avval savolning O'ZI tahlil qilingan oynasi (`parsed.start_at`), keyin
 * birinchi manba.  Ikkalasi ham bo'lmasa bugun: manba topilmagan javob
 * ostida ham lenta turishi kerak — "14:00-16:00 da hech kim kirmadi"
 * matnining eng qimmatli davomi o'sha kuni NIMA bo'lgani. */
function agentDay(job: Job): string {
  return tashkentDay(job.result?.parsed?.start_at) || tashkentDay(job.result?.sources?.[0]?.occurred_at) || tashkentToday();
}

/** Manbalar turgan soatlar — lentada belgilanadi (bosilmaydi). */
function markedHours(job: Job): number[] {
  const day = agentDay(job);
  const hours = (job.result?.sources || [])
    .filter(source => tashkentDay(source.occurred_at) === day)
    .map(source => tashkentHour(source.occurred_at))
    .filter((hour): hour is number => hour != null);
  return Array.from(new Set(hours));
}

export function VisionAgent({ siteId, onNavigate }: { siteId: string; onNavigate: (id: string, focus?: string) => void }) {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [question, setQuestion] = useState("");
  const [audioReply, setAudioReply] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");
  const timer = useRef(0);

  const loadSettings = useCallback(async () => {
    try { setSettings(await api<Settings>("/api/v1/owner/agent/settings", "owner", { siteId })); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Sozlama olinmadi"); }
  }, [siteId]);
  useEffect(() => { void loadSettings(); return () => window.clearTimeout(timer.current); }, [loadSettings]);

  /* `ticks` — umumiy kutish (har biri ~1.8 s, ~4 daqiqada to'xtaydi),
     `fails` — ketma-ket tarmoq xatosi.  Ikkalasida ham so'rov OXIR-OQIBAT
     yakunlanadi: avval bitta xato yoki o'lik worker tugmani abadiy
     "Dalillar tekshirilmoqda…" holatida qoldirardi. */
  const poll = useCallback(async (id: string, ticks = 0, fails = 0) => {
    try {
      const next = await api<Job>(`/api/v1/owner/agent/jobs/${encodeURIComponent(id)}`, "owner", { siteId });
      if (next.status === "queued" || next.status === "running") {
        if (ticks >= 130) {
          setJob({ ...next, status: "failed", error: "Javob cho‘zilib ketdi. Savol navbatda qoldi — birozdan so‘ng qayta so‘rang yoki qo‘llab-quvvatlashga yozing." });
          return;
        }
        setJob(next);
        timer.current = window.setTimeout(() => void poll(id, ticks + 1, 0), 1800);
        return;
      }
      setJob(next);
    } catch (reason) {
      if (fails >= 4) {
        setError(reason instanceof Error ? reason.message : "Javob olinmadi");
        setJob(current => current ? { ...current, status: "failed", error: "Server bilan aloqa uzildi — qayta urinib ko‘ring." } : current);
        return;
      }
      timer.current = window.setTimeout(() => void poll(id, ticks + 1, fails + 1), 3000);
    }
  }, [siteId]);

  const ask = async () => {
    const message = question.trim(); if (!message) return;
    setError(""); setJob({ job_id: "", status: "queued" });
    try {
      const next = await api<Job>("/api/v1/owner/agent/queries", "owner", { siteId, method: "POST", body: JSON.stringify({ message, want_audio_reply: audioReply }) });
      setJob(next); void poll(next.job_id);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Savol yuborilmadi"); setJob(null); }
  };

  const askAudio = async (file?: File) => {
    if (!file) return;
    setError(""); setJob({ job_id: "", status: "queued" });
    const form = new FormData(); form.set("audio", file); form.set("want_audio_reply", String(audioReply));
    try {
      const next = await api<Job>("/api/v1/owner/agent/audio", "owner", { siteId, method: "POST", body: form });
      setJob(next); void poll(next.job_id);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Ovozli savol yuborilmadi"); setJob(null); }
  };

  const consent = async () => {
    try {
      const next = await api<Settings>("/api/v1/owner/agent/settings", "owner", { siteId, method: "PUT", body: JSON.stringify({ consented: true, audio_reply_enabled: audioReply }) });
      setSettings({ ...next, provider_configured: settings?.provider_configured || false });
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Rozilik saqlanmadi"); }
  };

  const playAudio = async () => {
    if (!job?.job_id) return;
    const response = await fetch(`/api/v1/owner/agent/jobs/${encodeURIComponent(job.job_id)}/audio`, { headers: { Authorization: `Bearer ${tokenFor("owner")}`, "X-Owner-Site-Id": siteId } });
    if (!response.ok) { setError("Ovozli javob ochilmadi"); return; }
    const url = URL.createObjectURL(await response.blob());
    const audio = new Audio(url); audio.onended = () => URL.revokeObjectURL(url); await audio.play();
  };

  return <>
    <PageHeader title="Chaqimchi yordamchisi" subtitle="Savolni Uzbek tilida bering — javob faqat kamera eventlari va dalillariga tayanadi." />
    {error ? <div className="alert-strip alert-info"><Icon name="bell"/><div>{error}</div></div> : null}
    {settings === null ? <Card><div className="card-body"><Skeleton height={190}/></div></Card>
      : !settings.consented ? <Card><EmptyState icon="shield" title="Agent uchun rozilik kerak" detail="Savol matni va zarur snapshotlar Gemini’ga faqat javob tayyorlash uchun yuboriladi. Audio va media nusxalari suhbat tarixiga saqlanmaydi."/><div className="card-body agent-composer"><label className="consent-row"><input type="checkbox" checked={audioReply} onChange={event => setAudioReply(event.target.checked)}/><span>Native audio javobini ham yoqish</span></label><button className="btn btn-primary" onClick={() => void consent()}>Rozilik berib yoqish</button></div></Card>
      : !settings.provider_configured ? <Card><EmptyState icon="pulse" title="Agent tayyorlanmoqda" detail="Filial roziligi saqlandi. Administrator Gemini providerini sozlagach savollar qabul qilinadi."/></Card>
      : <>
        <Card><div className="card-body agent-composer"><label>Masalan: “Bugun 14:00 dan 16:00 gacha kirishda kimdir kirdimi?”<textarea className="input" value={question} onChange={event => setQuestion(event.target.value)} maxLength={4000} rows={4}/></label>{settings.audio_reply_enabled ? <label className="consent-row"><input type="checkbox" checked={audioReply} onChange={event => setAudioReply(event.target.checked)}/><span>Javobni ovozda ham tayyorlash</span></label> : null}<div className="page-actions"><button className="btn btn-primary" disabled={job?.status === "queued" || job?.status === "running"} onClick={() => void ask()}><Icon name="pulse"/>{job?.status === "queued" || job?.status === "running" ? "Dalillar tekshirilmoqda…" : "Savol berish"}</button><label className="btn upload-btn">Ovoz fayli<input type="file" accept="audio/ogg,audio/opus,audio/mpeg,audio/mp4,audio/wav" capture="user" onChange={event => { void askAudio(event.target.files?.[0]); event.currentTarget.value = ""; }}/></label></div></div></Card>
        {job?.status === "completed" ? <Card className="section-gap"><div className="card-head"><div><h2>Dalilli javob</h2><p>Eventlar Edge tomonidan qayd etilgan, vizual xulosa esa zarur kadrlargina ko‘rilganda beriladi.</p></div>{job.has_audio_reply ? <button className="btn" onClick={() => void playAudio()}><Icon name="pulse"/>Ovozda tinglash</button> : null}</div><div className="card-body"><p className="agent-answer">{job.result?.answer}</p>{agentDay(job) ? <><p className="media-note">Javob tayangan kun: {agentDay(job)}. Manba soatlari lentada belgilangan.</p><EventTimeline siteId={siteId} date={agentDay(job)} markedHours={markedHours(job)}/></> : null}{job.result?.sources?.length ? <div className="simple-list">{job.result.sources.map(source => <div className="simple-row" key={source.event_id}><div><b>{source.label || "Hodisa"}</b><div className="table-sub">{source.camera_id || "Kamera"} · {formatTimeUz(source.occurred_at)}{source.observation?.summary ? ` · ${source.observation.summary}` : ""}</div></div><button className="btn" onClick={() => onNavigate("alerts", source.event_id)}>Dalilni ochish</button></div>)}</div> : <EmptyState icon="report" title="Dalil topilmadi" detail="Tanlangan vaqt oralig‘ida saqlangan event yo‘q."/>}</div></Card> : null}
        {job?.status === "failed" ? <Card className="section-gap"><EmptyState icon="bell" title="Agent javob bera olmadi" detail={job.error || "Keyinroq qayta urinib ko‘ring."}/></Card> : null}
      </>}
  </>;
}
