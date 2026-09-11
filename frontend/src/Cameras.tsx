import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, formatTimeUz, tokenFor } from "./api";
import { Card, EmptyState, StatusDot } from "./components";
import { t } from "./i18n";
import { Icon } from "./icons";
import type { Camera, Dashboard } from "./types";

/* Kamera plitkalari — bosh sahifa, «Kameralar» bo'limi va alohida
 * kamera sahifasi BITTA komponentni ishlatadi: jonli oqimni ushlab
 * turish (keepalive), to'xtatish va kadr so'rash mantig'i bir joyda.
 * 2026-09-11 gacha bu `owner.tsx` ichida edi; kamera sahifasi paydo
 * bo'lgach ikki nusxa bo'lib ketmasin deb ko'chirildi. */

export function CameraImage({ camera, siteId, overlay, live }: { camera: Camera; siteId: string; overlay: boolean; live: boolean }) {
  const [src, setSrc] = useState("");
  const [error, setError] = useState(false);
  const [requested, setRequested] = useState(false);
  const [stamp, setStamp] = useState("");
  const [frameAt, setFrameAt] = useState("");
  useEffect(() => {
    let timer = 0;
    let stopped = false;
    let current = "";
    /* Tayanch kadrni bir marta SO'RAB olamiz.
     *
     * Ilgari bu komponent faqat GET qilardi.  Kadr hali yuborilmagan
     * do'konda server 404 qaytarardi va panel abadiy "Kadr hozircha
     * kelmadi" deb turardi — mijozda uni tuzatadigan birorta tugma yo'q
     * edi.  2026-08-26 da jonli do'konda aynan shu ko'rindi: 6 soatda
     * 33 ta GET, hammasi 404, birorta POST yo'q.
     *
     * Kadrni so'raydigan endpoint allaqachon bor
     * (`owner_request_camera_preview`) — panel uni chaqirmasdi.
     * Bir marta: serverda soatiga 30 so'rov chegarasi bor va uni
     * avtomatik takror so'rov yeb qo'yardi. */
    let asked = false;
    const requestFrame = async () => {
      if (asked || live) return;
      asked = true;
      try {
        await api(`/api/v1/owner/cameras/${encodeURIComponent(camera.camera_id)}/preview`, "owner", { method: "POST", siteId });
        if (!stopped) setRequested(true);
      } catch {
        /* Chegara yoki tarmoq — yozuv baribir "kelmadi" bo'lib qoladi. */
      }
    };
    const load = async () => {
      const path = live ? `/api/v1/owner/cameras/${encodeURIComponent(camera.camera_id)}/live-frame?t=${Date.now()}` : `/api/v1/owner/cameras/${encodeURIComponent(camera.camera_id)}/preview?t=${Date.now()}`;
      try {
        const headers: Record<string,string> = { Authorization: `Bearer ${tokenFor("owner")}`, "X-Owner-Site-Id": siteId };
        const response = await fetch(path, { headers });
        if (!response.ok) throw new Error();
        const next = URL.createObjectURL(await response.blob());
        if (stopped) { URL.revokeObjectURL(next); return; }
        if (current) URL.revokeObjectURL(current);
        current = next; setSrc(next); setError(false);
        /* Vaqt KADRNING O'ZINIKI (`X-Frame-At`), klient soati emas.
           Ilgari bu yerda `new Date()` turardi: qurilma kadr yuborishni
           to'xtatsa ham server oxirgi saqlangan rasmni qaytaraverardi
           va panel har javobda vaqtni yangilardi — muzlagan rasm ustida
           soat tikillab turardi va ega uni "jonli" deb o'ylardi. */
        const frameAt = response.headers.get("X-Frame-At") || "";
        setStamp(formatTimeUz(frameAt) || "—");
        setFrameAt(frameAt);
      } catch {
        // `current` — shu effektning O'Z holati.  Ilgari bu yerda
        // `src` tekshirilardi: u effekt yopilmasidan oldingi qiymatni
        // eslab qolgan edi, shuning uchun birinchi muvaffaqiyatli
        // kadrdan keyin ham "Kadr kelmadi" yozuvi chiqib ketardi.
        if (!current) setError(true);
        if (!current && !asked && !live) {
          await requestFrame();
          // Qurilma so'rovni keyingi salomda ko'radi (20 s gacha), keyin
          // kadr yuklanadi.  Uch marta qaraymiz — ~45 soniya.
          for (let attempt = 0; attempt < 3 && !stopped && !current; attempt += 1) {
            await new Promise(resolve => { timer = window.setTimeout(resolve, 15000); });
            if (!stopped && !current) await load();
          }
        }
      }
      if (!stopped && live) timer = window.setTimeout(load, 2500);
    };
    void load();
    return () => { stopped = true; window.clearTimeout(timer); if (current) URL.revokeObjectURL(current); };
  }, [camera.camera_id, live, overlay, siteId]);
  /* Jonli rejimda «Kadr so'raldi, 20 soniya kuting» yolg'on: so'ralmagan,
     oqim kutilmoqda.  Pastdagi «Jonli · 2 soniya oldin» bilan ziddiyat
     QA da ko'ringan edi. */
  const emptyLabel = live ? t("panel.cameras.live_waiting") : error ? (requested ? t("panel.cameras.frame_requested") : t("panel.cameras.frame_missing")) : t("panel.cameras.frame_loading");
  /* Jonli rejimda kadr 2-3 soniyada yangilanadi.  25 soniyadan eski
     bo'lsa oqim uzilgan: buni AYTISH kerak, aks holda ega eski rasmga
     qarab do'konda hozir nima bo'layotgani haqida qaror qabul qiladi. */
  const frameAge = live && frameAt ? (Date.now() - new Date(frameAt).getTime()) / 1000 : 0;
  const frozen = live && frameAt && frameAge > 25;
  return <div className="camera-frame">
    {src ? <img src={src} alt={t("panel.cameras.image_alt", { name: camera.label || camera.camera_id })} /> : <div className="camera-empty"><Icon name="camera" size={28}/><span>{emptyLabel}</span></div>}
    {overlay && src ? <span className="camera-overlay-badge">{t("panel.cameras.ai_badge")}</span> : null}
    {stamp && src ? <span className={`camera-stamp${frozen ? " is-stale" : ""}`}>{frozen ? t("panel.cameras.stamp_stale", { time: stamp }) : stamp}</span> : null}
  </div>;
}

export function CamerasBlock({ dashboard, siteId, expanded = false, only = "", onOpenAll, onOpenCamera }: { dashboard: Dashboard; siteId: string; expanded?: boolean; only?: string; onOpenAll?: () => void; onOpenCamera?: (cameraId: string) => void }) {
  const [overlay, setOverlay] = useState(false);
  const [live, setLive] = useState(false);
  /* `only` — kamera sahifasi: bitta kamera, o'sha jonli/AI mantiq bilan.
     `useMemo` shart: `slice`/`filter` har renderda yangi massiv beradi
     va pastdagi keepalive taymeri qayta qurilardi. */
  const cameras = useMemo(
    () => only ? dashboard.cameras.filter(camera => camera.camera_id === only) : expanded ? dashboard.cameras : dashboard.cameras.slice(0, 4),
    [dashboard.cameras, expanded, only],
  );
  const stateMap = useMemo(() => new Map(dashboard.camera_states.map(item => [item.camera_id, item])), [dashboard.camera_states]);

  /* Kamera ro'yxati `useEffect` bog'liqligi bo'lib ishlatiladi, lekin
     `slice()` har renderda YANGI massiv qaytaradi — usiz keepalive
     taymeri har renderda qayta qurilardi. */
  const cameraIds = useMemo(() => cameras.map(camera => camera.camera_id).join(","), [cameras]);

  const askLive = useCallback(async (body: Record<string, unknown>) => {
    const ids = cameraIds ? cameraIds.split(",") : [];
    await Promise.all(ids.map(id => api(`/api/v1/owner/cameras/${encodeURIComponent(id)}/live`, "owner", { method: "POST", siteId, body: JSON.stringify(body) }).catch(() => null)));
  }, [cameraIds, siteId]);

  /* JONLI REJIMNI USHLAB TURISH.
   *
   * Server so'rovni 90 soniyaga yozadi (`store.request_live`,
   * `ttl_sec=90`) va uning izohida "panel har 60 soniyada qayta
   * chaqiradi" deb yozilgan — lekin panel buni HECH QACHON
   * qilmasdi.  Natijada 90 soniyadan keyin qurilma kadr yuborishni
   * to'xtatardi, panel esa eski kadrni ko'rsatishda davom etardi va
   * yonida soat tikillab turardi: ega 5 daqiqa oldingi rasmni
   * "jonli" deb ko'rardi.
   *
   * 60 soniya — 90 lik muddatga nisbatan bitta o'tkazib yuborilgan
   * so'rovga zaxira qoldiradi. */
  useEffect(() => {
    if (!live || !cameraIds) return;
    let stopped = false;
    void askLive({ overlay });
    const timer = window.setInterval(() => { if (!stopped) void askLive({ overlay }); }, 60000);
    return () => { stopped = true; window.clearInterval(timer); };
  }, [live, overlay, cameraIds, askLive]);

  /* To'xtatish ALOHIDA effektda va faqat `live` ga bog'liq.
   *
   * Yuqoridagi effekt ichida qilinsa `overlay` o'zgarganda ham cleanup
   * ishlab, "to'xtat" va "yoq" ikkitasi yonma-yon ketardi — ikkalasi
   * asinxron, ya'ni "to'xtat" keyinroq yetib borsa jonli ko'rish
   * JIMGINA o'lardi.  Aynan shu tuzatilayotgan xatoning o'zi. */
  const askLiveRef = useRef(askLive);
  useEffect(() => { askLiveRef.current = askLive; }, [askLive]);
  useEffect(() => {
    if (!live) return;
    /* Panel yopilganda oqim to'xtatiladi: aks holda qurilma yana
       90 soniya kadr yuboradi va kunlik byudjetni bekorga yeydi. */
    return () => { void askLiveRef.current({ stop: true }); };
  }, [live]);

  const toggleLive = () => setLive(value => !value);

  /* "AI ramkani ko'rsatish" jonli rejimni O'ZI yoqadi.
   *
   * Ilgari jonli rejim o'chiq bo'lsa bu tugma faqat rasm ustiga
   * "AI tahlil" yorlig'ini qo'yardi — ramka esa chizilmasdi, chunki
   * ramka QURILMADA, faqat jonli kadrga chiziladi.  Ya'ni tugma nomi
   * va'da qilgan narsani bajarmasdi. */
  const toggleOverlay = () => {
    setOverlay(value => !value);
    if (!live) setLive(true);
  };
  return <Card>
    <div className="card-head">
      <div><h2>{t("panel.cameras.live_title")}</h2><p>{t("panel.cameras.live_subtitle")}</p></div>
      <div className="page-actions">
        <button className="btn" onClick={toggleOverlay}><Icon name="eye"/>{overlay ? t("panel.cameras.overlay_hide") : t("panel.cameras.overlay_show")}</button>
        <button className={`btn ${live ? "btn-primary" : ""}`} onClick={toggleLive}><Icon name="pulse"/>{live ? t("panel.cameras.live") : t("panel.cameras.live_start")}</button>
        {!expanded && onOpenAll ? <button className="btn" onClick={onOpenAll}>{t("panel.cameras.open_all")}</button> : null}
      </div>
    </div>
    {cameras.length ? <div className={`live-grid${expanded && !only ? " is-wide" : ""}`}>{cameras.map(camera => {
      const state = stateMap.get(camera.camera_id)?.state || "unknown";
      // Uch holat uch xil so'z bilan: "eskirgan" va "oflayn" bir xil
      // qizil "Aloqa yo'q" bo'lib chiqsa, egasi tuzatib bo'ladigan
      // kechikishni butunlay uzilish deb o'ylaydi.
      const live_label = state === "online" ? t("panel.cameras.live") : state === "stale" ? t("panel.cameras.state_stale") : t("panel.cameras.state_offline");
      const name = camera.label || camera.camera_id;
      const streaming = live && state === "online";
      return <article className={`camera-tile${onOpenCamera ? " is-link" : ""}`} key={camera.camera_id} onClick={onOpenCamera ? () => onOpenCamera(camera.camera_id) : undefined}>
        <CameraImage camera={camera} siteId={siteId} overlay={overlay} live={live}/>
        {/* Kadr ustida BITTA belgi (namunadagi LIVE): jonli oqim — qizil,
            aks holda kamera holati.  Nom kadr ustida takrorlanmaydi —
            u pastda; ikki joyda turishi QA da chalkash chiqqan edi. */}
        <span className={`camera-badge is-${streaming ? "live" : state}`}><i/>{streaming ? t("panel.cameras.live_badge") : live_label}</span>
        {/* Tungi rejim: IR — kamera tunda ko'radi; `dark` — ko'rmaydi (IR
            yo'q).  Ikkinchisi ega uchun harakatga chaqiriq: IR kamera. */}
        {stateMap.get(camera.camera_id)?.night_mode === "ir" ? <span className="camera-night is-ir"><Icon name="moon" size={12}/>{t("panel.cameras.night_ir")}</span>
          : stateMap.get(camera.camera_id)?.night_mode === "dark" ? <span className="camera-night is-dark"><Icon name="moon" size={12}/>{t("panel.cameras.night_dark")}</span> : null}
        <div className="camera-meta">
          <div className="camera-name"><StatusDot state={state}/><span>{name}</span></div>
          <small>{stateMap.get(camera.camera_id)?.reason || t("panel.cameras.state_loading")}</small>
          {onOpenCamera ? <button className="btn btn-icon camera-open" aria-label={t("panel.cameras.open", { name })} onClick={event => { event.stopPropagation(); onOpenCamera(camera.camera_id); }}><Icon name="eye" size={16}/></button> : null}
        </div>
      </article>;
    })}</div> : <EmptyState icon="camera" title={t("panel.cameras.empty_title")} detail={t("panel.cameras.empty_detail")} />}
  </Card>;
}
