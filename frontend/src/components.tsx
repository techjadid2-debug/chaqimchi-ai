import { useEffect, useRef, useState, type InputHTMLAttributes, type ReactNode } from "react";
import { copyText } from "./api";
import { Icon, Logo } from "./icons";
import { Sparkline, Delta } from "./charts";
import { applyTheme, nextTheme, readTheme, saveTheme, themeLabel, THEME_ICON, type Theme } from "./theme";
import { getLang, LANG_SHORT, LANGS, setLang, t, type Lang } from "./i18n";

/** Qo'llab-quvvatlash raqami.
 *
 * Sayt sahifalarida ham shu raqam turadi (`cloud/static/*.html`) va
 * `tests/test_panel_v2.py` ikkalasi bir xilligini tekshiradi: mijozga
 * ikki xil raqam ko'rsatilishi eng bilinmaydigan xatolardan biri. */
export const SUPPORT_PHONE = "+998932225070";
export const SUPPORT_PHONE_LABEL = "+998 93 222 50 70";

export type NavItem = { id: string; label: string; icon: string };

/** Tema tugmasi: yorug' → qorong'i → tizim.
 *
 * Nega uchinchi holat ko'rinadi: "tizim bo'yicha" ni yashirsak, odam
 * bir marta qo'lda tanlagach tizimga qaytolmaydi va kechqurun
 * kompyuter qorong'iga o'tganda panel yorug' bo'lib qolaveradi. */
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(() => readTheme());

  /* Tizim rejimi tanlangan bo'lsa, foydalanuvchi OS sozlamasini
     o'zgartirganda sahifa QAYTA YUKLANMASDAN moslashsin. */
  useEffect(() => {
    if (theme !== "system") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const sync = () => applyTheme("system");
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, [theme]);

  function toggle() {
    const next = nextTheme(theme);
    setTheme(next);
    saveTheme(next);
    applyTheme(next);
  }

  return <button
    className="btn btn-icon theme-toggle"
    onClick={toggle}
    title={themeLabel(theme)}
    aria-label={t("panel.theme.switch", { mode: themeLabel(theme) })}
  ><Icon name={THEME_ICON[theme]}/></button>;
}

/** Til tanlagich — namunadagidek UZ · RU · EN.
 *
 * Tanlangach sahifa qayta yuklanadi (`i18n/index.ts` dagi izohga
 * qarang): serverdan keladigan matn ham yangi tilda bo'lishi kerak,
 * aks holda ekranda ikki til aralashardi. */
export function LangSwitch() {
  const active = getLang();
  return <div className="lang-switch" role="group" aria-label={t("panel.lang.choose")}>
    {LANGS.map((lang: Lang) => <button
      key={lang}
      className={lang === active ? "active" : ""}
      onClick={() => setLang(lang)}
      aria-current={lang === active}
    >{LANG_SHORT[lang]}</button>)}
  </div>;
}

export function StatusDot({ state }: { state: string }) {
  /* Yorliq odam tilida: ekran o'quvchi «stale» emas, «Kechikmoqda» desin.
     Katalogda bo'lmagan holat uchun kalitning o'zi chiqmasin — umumiy so'z. */
  const key = `panel.cameras.state_${state}`;
  const label = t(key);
  return <span className={`status-dot status-${state}`} aria-label={label === key ? t("panel.cameras.state_unknown") : label} />;
}

export function Pill({ state, children }: { state?: string; children: ReactNode }) {
  return <span className={`pill ${state ? `pill-${state}` : ""}`}>{children}</span>;
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`card ${className}`}>{children}</section>;
}

/** Ko'rsatkich kartasi: raqam + ixtiyoriy o'zgarish + ixtiyoriy
 *  tendensiya chizig'i.
 *
 *  `series` va `deltaPercent` — IXTIYORIY.  Server hali bermaydigan
 *  ko'rsatkich uchun karta ularsiz chiziladi: bo'sh sparkline yoki
 *  "0%" degan yolg'on o'sish ko'rsatgandan ko'ra hech narsa
 *  ko'rsatmagan yaxshi.
 *
 *  Ilgari yonida `MetricCard` ham turardi — aynan shu karta,
 *  o'zgarish va sparkline'siz.  Ega paneli `StatCard` ga o'tgach
 *  admin eskisida qolib ketdi va ikkita KO'RSATKICH KARTASI ikki
 *  panelda boshqacha ko'rinardi.  O'chirildi (2026-09-12): ixtiyoriy
 *  proplarni bermaslik yetarli. */
export function StatCard({ label, value, note, icon, tone = "blue", series, deltaPercent, deltaNote, goodWhenDown }: {
  label: string;
  value: ReactNode;
  note?: ReactNode;
  icon: string;
  tone?: string;
  series?: number[];
  deltaPercent?: number | null;
  deltaNote?: string;
  goodWhenDown?: boolean;
}) {
  return <Card className="metric-card stat-card">
    <div className="stat-head">
      <div className={`metric-icon tone-${tone}`}><Icon name={icon} /></div>
      <div className="metric-label">{label}</div>
    </div>
    <div className="metric-value">{value}</div>
    <Delta percent={deltaPercent} note={deltaNote} goodWhenDown={goodWhenDown} />
    {note ? <div className="metric-note">{note}</div> : null}
    {series && series.length > 1 ? <Sparkline points={series} tone={tone === "red" ? "red" : tone === "green" ? "green" : "blue"} /> : null}
  </Card>;
}

export function EmptyState({ icon = "report", title, detail }: { icon?: string; title: string; detail: string }) {
  return <div className="empty-state"><span><Icon name={icon} size={26} /></span><b>{title}</b><p>{detail}</p></div>;
}

/** Xato chizig'i — panelda BITTA ko'rinishda.
 *
 * Ilgari xato to'rt xil chiqardi: ko'k «ma'lumot» chizig'i qo'ng'iroq
 * bilan (bildirishnomaga o'xshardi), sariq chiziq, kartadan tashqarida
 * yalang'och qizil matn va karta ichidagi qizil matn.  Ega qaysi biri
 * xato, qaysi biri eslatma ekanini ajratolmasdi.  Endi xato doim qizil,
 * `role="alert"` bilan (ekran o'quvchi darhol o'qiydi) va iloji bo'lsa
 * «Qayta urinish» tugmasi bilan — javobsiz xato tuzatib bo'lmaydigan
 * xatodek ko'rinadi. */
export function ErrorStrip({ title, detail, onRetry, className = "" }: { title?: string; detail: string; onRetry?: () => void; className?: string }) {
  return <div className={`alert-strip alert-warning ${className}`} role="alert">
    <Icon name="shield"/>
    <div>{title ? <><strong>{title}</strong> </> : null}{detail}</div>
    {onRetry ? <button className="btn" onClick={onRetry}>{t("panel.common.retry")}</button> : null}
  </div>;
}

/** Tarifda yopiq bo'lim.
 *
 * Bo'lim YO'QOLMAYDI — mijoz nimani ololishini ko'rsin.  Yo'q bo'lib
 * qolgan karta «buzilibdi» degan taassurot beradi, qulf esa
 * «ko'tarish mumkin» degani.
 */
export function PlanLock({ title, detail, onUpgrade }: { title: string; detail: string; onUpgrade: () => void }) {
  return <>
    <EmptyState icon="card" title={title} detail={detail} />
    <div className="card-body"><button className="btn btn-wide" onClick={onUpgrade}>{t("panel.lock.view_plan")}</button></div>
  </>;
}

export function Skeleton({ height = 80 }: { height?: number }) {
  return <div className="skeleton" style={{ height }} aria-label={t("panel.common.loading")} />;
}

/** Bo'lim ichidagi tablar (Kameralar → Jonli | Ulash | Chiziq va zonalar).
 *
 *  Tab — manzilning ikkinchi segmenti (`/owner/cameras/zones`), ya'ni
 *  havola qilib bo'ladi va brauzerning «Orqaga»si ishlaydi.  Tugmalar
 *  44 px: telefonda barmoq bilan bosiladi. */
export function Tabs({ items, active, onSelect, panelId }: { items: { id: string; label: string }[]; active: string; onSelect: (id: string) => void; panelId?: string }) {
  const list = useRef<HTMLDivElement>(null);
  /* Telefonda tablar qatori aylanadi; faol tab o'ngda qolib ketsa ega uni
     ko'rmaydi — «Tarif va to'lov» sozlamalarda shunday yashirin qolgan edi. */
  useEffect(() => {
    const el = list.current?.querySelector<HTMLElement>("button.active");
    el?.scrollIntoView({ inline: "center", block: "nearest" });
  }, [active]);
  const move = (event: React.KeyboardEvent, index: number) => {
    const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    event.preventDefault();
    onSelect(items[(index + step + items.length) % items.length].id);
  };
  /* `aria-controls` — tab qaysi sohani boshqaradi.  Usiz skrinrider
     tugmani «tab» deb o'qiydi-yu, bosilgandan keyin qayerga borganini
     aytmaydi.  `panelId` berilmasa atribut ham qo'yilmaydi: bo'sh
     havola noto'g'ri id ga ishora qilishdan yaxshiroq. */
  return <div className="tabs" role="tablist" ref={list}>
    {items.map((item, index) => <button key={item.id} id={panelId ? `${panelId}-tab-${item.id}` : undefined} role="tab" aria-selected={active === item.id} aria-controls={panelId} tabIndex={active === item.id ? 0 : -1} className={active === item.id ? "active" : ""} onClick={() => onSelect(item.id)} onKeyDown={event => move(event, index)}>{item.label}</button>)}
  </div>;
}

/** Tab tarkibi — `Tabs` bilan juftlik.  `role="tabpanel"` va
 *  `aria-labelledby` ikkalasi ham SHART: biri sohani e'lon qiladi,
 *  ikkinchisi uni qaysi tab ochganini aytadi. */
export function TabPanel({ id, activeTab, children }: { id: string; activeTab: string; children: ReactNode }) {
  return <div id={id} role="tabpanel" aria-labelledby={`${id}-tab-${activeTab}`}>{children}</div>;
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle: string; actions?: ReactNode }) {
  return <header className="page-header"><div><h1>{title}</h1><p>{subtitle}</p></div>{actions ? <div className="page-actions">{actions}</div> : null}</header>;
}

/** Ism bosh harflaridan doira.  Haqiqiy suratlar yo'q — jadvalda
 *  qatorlarni ko'z bilan ajratish uchun shu yetadi. */
export function Avatar({ name, tone }: { name: string; tone?: number }) {
  const initials = name.trim().split(/\s+/).slice(0, 2).map(part => part[0] || "").join("").toUpperCase() || "?";
  const index = tone ?? Array.from(name).reduce((sum, char) => sum + char.charCodeAt(0), 0);
  return <span className={`avatar avatar-${index % 5}`} aria-hidden="true">{initials}</span>;
}

/** Jadval qatoridagi "…" menyusi. */
export function ActionMenu({ items }: { items: { label: string; onSelect: () => void; danger?: boolean }[] }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => { if (!box.current?.contains(event.target as Node)) setOpen(false); };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", escape); };
  }, [open]);
  if (!items.length) return null;
  return <div className="action-menu" ref={box}>
    <button className="btn btn-icon" aria-label={t("panel.shell.actions")} aria-expanded={open} onClick={() => setOpen(value => !value)}><Icon name="more" /></button>
    {open ? <div className="action-list" role="menu">
      {items.map(item => <button key={item.label} role="menuitem" className={item.danger ? "danger" : ""} onClick={() => { setOpen(false); item.onSelect(); }}>{item.label}</button>)}
    </div> : null}
  </div>;
}

/** Nusxalash tugmasi — natijani KO'RSATADI.
 *
 * Javobsiz tugma buzuq tugmadan farq qilmaydi: foydalanuvchi uni yana
 * bosadi va baribir ishonchi bo'lmaydi.  Nusxalash imkonsiz muhitda
 * halol aytiladi ("qo'lda nusxalang") — jimgina yutilmaydi.
 */
export function CopyButton({ value, label = t("panel.common.copy") }: { value: string; label?: string }) {
  const [state, setState] = useState<"" | "ok" | "fail">("");
  useEffect(() => {
    if (!state) return;
    const timer = window.setTimeout(() => setState(""), 2200);
    return () => window.clearTimeout(timer);
  }, [state]);
  return <button
    className={`btn${state === "ok" ? " btn-copied" : ""}`}
    onClick={() => { void copyText(value).then(ok => setState(ok ? "ok" : "fail")); }}
  >{state === "ok" ? `${t("panel.common.copied")} ✓` : state === "fail" ? t("panel.shell.copy_manually") : label}</button>;
}

export type SearchEntry = { id: string; label: string; hint?: string; onSelect: () => void };

/** ⌘K qidiruv — bo'limlar va mijozlar bo'yicha, brauzer ichida.
 *  Serverga so'rov yubormaydi: ro'yxat allaqachon yuklangan. */
export function SearchPalette({ entries, placeholder = `${t("panel.common.search")}…` }: { entries: SearchEntry[]; placeholder?: string }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); setOpen(true); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const needle = query.trim().toLowerCase();
  const found = needle ? entries.filter(entry => entry.label.toLowerCase().includes(needle) || (entry.hint || "").toLowerCase().includes(needle)).slice(0, 8) : entries.slice(0, 8);
  return <>
    <button className="search-trigger" onClick={() => setOpen(true)}>
      <Icon name="search" size={16} /><span>{placeholder}</span><kbd>⌘K</kbd>
    </button>
    {open ? <PaletteBox onClose={() => setOpen(false)}>
        <div className="palette-input">
          <Icon name="search" size={18} />
          <input autoFocus value={query} placeholder={placeholder} onChange={event => setQuery(event.target.value)} />
        </div>
        {found.length ? <ul>
          {found.map(entry => <li key={entry.id}>
            <button onClick={() => { setOpen(false); setQuery(""); entry.onSelect(); }}>
              <span>{entry.label}</span>{entry.hint ? <em>{entry.hint}</em> : null}
            </button>
          </li>)}
        </ul> : <p className="palette-empty">{t("panel.shell.search_empty")}</p>}
    </PaletteBox> : null}
  </>;
}

/* Palitra qutisi ALOHIDA komponent: `useFocusTrap` hook, ya'ni u faqat
   qutining O'ZI chizilganda ishga tushishi kerak.  `SearchPalette`
   ichida `open` shartida chaqirib bo'lmaydi — hook shartli
   chaqirilmaydi. */
function PaletteBox({ children, onClose }: { children: ReactNode; onClose: () => void }) {
  const box = useFocusTrap(onClose);
  return <div className="palette-backdrop" onClick={onClose}>
    <div ref={box} className="palette" role="dialog" aria-modal="true" aria-label={t("panel.common.search")} onClick={event => event.stopPropagation()}>
      {children}
    </div>
  </div>;
}

export function AppShell({ nav, active, onNavigate, title, subtitle, headerActions, children, onLogout, mobileNav, sidebarFooter }: {
  nav: NavItem[];
  active: string;
  onNavigate: (id: string) => void;
  title: string;
  subtitle: string;
  headerActions?: ReactNode;
  children: ReactNode;
  onLogout: () => void;
  /* Telefon pastidagi menyuda ko'rinadigan bo'limlar.  Ilgari bu
     ro'yxat komponent ichida qotirilgan edi: menyuga yangi bo'lim
     qo'shilsa, u mobil menyuda jimgina yo'q bo'lib qolardi. */
  mobileNav: string[];
  sidebarFooter?: ReactNode;
}) {
  const mobile = nav.filter(item => mobileNav.includes(item.id));
  return <div className="app-shell">
    <aside className="sidebar">
      <div className="sidebar-logo"><Logo /></div>
      <nav aria-label={t("panel.shell.main_menu")}>{nav.map(item => <button key={item.id} className={active === item.id ? "active" : ""} onClick={() => onNavigate(item.id)}><Icon name={item.icon}/><span>{item.label}</span></button>)}</nav>
      <div className="sidebar-foot">
        {sidebarFooter}
        {/* Aloqa panel ICHIDA bo'lsin.  Ilgari u faqat kirish ekranida
            edi: panel to'rt joyda "bizga yozing" deydi-yu, kirgandan
            keyin qayerga yozishni ko'rsatmasdi. */}
        <a className="sidebar-support" href={`tel:${SUPPORT_PHONE}`}>
          <Icon name="bell"/><span>{t("panel.support")}<b>{SUPPORT_PHONE_LABEL}</b></span>
        </a>
        <button className="sidebar-logout" onClick={onLogout}><Icon name="logout"/><span>{t("panel.common.logout")}</span></button>
      </div>
    </aside>
    <main className="main-shell">
      <div className="topbar"><div className="topbar-title"><strong>{title}</strong><span>{subtitle}</span></div><div className="topbar-actions">{headerActions}<LangSwitch/><ThemeToggle/></div></div>
      <div className="content">{children}</div>
    </main>
    <nav className="bottom-nav" aria-label={t("panel.shell.mobile_menu")}>{mobile.map(item => <button key={item.id} className={active === item.id ? "active" : ""} onClick={() => onNavigate(item.id)}><Icon name={item.icon}/><span>{item.label}</span></button>)}<button onClick={() => onNavigate("more")}><Icon name="more"/><span>{t("panel.common.more")}</span></button></nav>
  </div>;
}

/** Parol maydoni — "ko'z" (ko'rsatish/yashirish) tugmasi bilan.
 *
 *  Telefon klaviaturasida xato terish oson, xatoni ko'rmasdan tuzatib
 *  bo'lmaydi.  Statik sahifalar uchun xuddi shu naqsh
 *  `enes/local/static/pw-eye.js` da. */
/** Fokusni element ICHIDA ushlab turadi va yopilganda qaytaradi.
 *
 * Izoh bir vaqtlar «fokus oyna ichida» deb YOZILGAN edi, kod esa buni
 * qilmasdi: `aria-modal="true"` faqat skrinriderga aytadi, klaviaturani
 * to'smaydi.  Ya'ni Tab bosgan odam oyna ortidagi sahifaga chiqib
 * ketardi va u yerda ko'rinmas tugmalarni bosardi.  Yopilganda fokus
 * hech qayerga qaytmasdi — klaviatura bilan ishlayotgan odam sahifa
 * boshiga tashlanardi.
 *
 * Telegram WebView'da bu ayniqsa muhim: u yerda brauzer oynalari yo'q
 * va butun panel shu modal oynalarga tayanadi. */
export function useFocusTrap(onClose: () => void) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    /* Birinchi fokuslanadigan element.  `autoFocus` bo'lsa React uni
       o'zi qo'yadi — o'shani buzmaymiz. */
    const focusables = () => Array.from(
      box.current?.querySelectorAll<HTMLElement>(
        'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])',
      ) || [],
    ).filter(el => el.offsetParent !== null);
    if (!box.current?.contains(document.activeElement)) focusables()[0]?.focus();

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") { onClose(); return; }
      if (event.key !== "Tab") return;
      const list = focusables();
      if (!list.length) return;
      const first = list[0];
      const last = list[list.length - 1];
      const active = document.activeElement;
      /* Halqa: oxirgidan Tab — birinchisiga, birinchisidan Shift+Tab —
         oxirgisiga.  Fokus butunlay tashqarida bo'lsa ham qaytariladi
         (masalan sichqoncha bilan fonga bosilgan). */
      if (event.shiftKey ? active === first || !box.current?.contains(active) : active === last) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      /* Fokus chaqirgan elementga qaytadi.  `isConnected` tekshiriladi:
         element o'zi o'chgan bo'lishi mumkin (ro'yxatdagi qatorni
         o'chirish oynasi). */
      if (previous?.isConnected) previous.focus();
    };
  }, [onClose]);
  return box;
}

/** Modal oyna — brauzerning `prompt`/`confirm` o'rniga.
 *
 * Eski admin qoidasi (2026-08-19): brauzer oynasida "auto" yoki "naqd"
 * deb YOZISH kerak edi — bitta harf xato, amal bajarilmasdi.  Modal
 * ichida esa tanlov tugma va ro'yxat bilan.  Escape va orqa fon yopadi;
 * fokus oyna ichida qoladi (`useFocusTrap`). */
export function Modal({ title, children, onClose, wide = false, footer }: { title: string; children: ReactNode; onClose: () => void; wide?: boolean; footer?: ReactNode }) {
  const box = useFocusTrap(onClose);
  return <div className="modal-backdrop" onClick={onClose}>
    <div ref={box} className={`modal${wide ? " modal-wide" : ""}`} role="dialog" aria-modal="true" aria-label={title} onClick={event => event.stopPropagation()}>
      <div className="modal-head"><h2>{title}</h2><button className="btn btn-icon" aria-label={t("panel.common.close")} onClick={onClose}><Icon name="close" /></button></div>
      <div className="modal-body">{children}</div>
      {footer ? <div className="modal-foot">{footer}</div> : null}
    </div>
  </div>;
}

export type ConfirmRequest = {
  title: string;
  text: string;
  confirmLabel?: string;
  danger?: boolean;
  /** Xavfli amal: foydalanuvchi shu matnni TERIB tasdiqlaydi
   *  (obunani to'xtatish — do'kon nomi).  Tasodifiy bosishdan himoya. */
  typed?: string;
};

/** Tasdiqlash oynasi.  `window.confirm` ATAYLAB ishlatilmaydi: Telegram
 *  WebView'da u ishonchsiz, matnini esa uslublab bo'lmaydi. */
export function ConfirmDialog({ request, onResolve }: { request: ConfirmRequest; onResolve: (ok: boolean) => void }) {
  const [typed, setTyped] = useState("");
  const blocked = Boolean(request.typed) && typed.trim() !== request.typed;
  return <Modal title={request.title} onClose={() => onResolve(false)} footer={<>
    <button className="btn" onClick={() => onResolve(false)}>{t("panel.common.cancel")}</button>
    <button className={`btn ${request.danger ? "btn-danger" : "btn-primary"}`} disabled={blocked} onClick={() => onResolve(true)}>{request.confirmLabel || t("panel.common.yes")}</button>
  </>}>
    <p className="modal-text">{request.text}</p>
    {request.typed ? <label className="field-label">{t("panel.shell.confirm_typed", { text: request.typed })}<input className="input" value={typed} onChange={event => setTyped(event.target.value)} autoFocus /></label> : null}
  </Modal>;
}

export type PromptRequest = {
  title: string;
  /** Maydonga oldindan yozib qo'yiladigan taklif (masalan «kirish»). */
  initial?: string;
  hint?: string;
  confirmLabel?: string;
};

/** Matn so'raydigan oyna — `window.prompt` o'rniga.
 *
 * `ConfirmDialog` faqat ha/yo'q beradi, chizma nomlash esa MATN talab
 * qiladi va `window.prompt` Telegram WebView'da ko'rsatilmasligi
 * mumkin — u yerda zona nomlash jimgina o'lardi: foydalanuvchi zonani
 * chizadi, oyna chiqmaydi va shakl saqlanmaydi.  Bo'sh nom bekor
 * qilish bilan BIR XIL emas: bo'sh qoldirilsa taklif qilingan nom
 * olinadi (muharrir `null` ni «bekor» deb o'qiydi). */
export function PromptModal({ request, onResolve }: { request: PromptRequest; onResolve: (value: string | null) => void }) {
  const [value, setValue] = useState(request.initial || "");
  const submit = () => onResolve(value.trim() || request.initial || "");
  return <Modal title={request.title} onClose={() => onResolve(null)} footer={<>
    <button className="btn" onClick={() => onResolve(null)}>{t("panel.common.cancel")}</button>
    <button className="btn btn-primary" onClick={submit}>{request.confirmLabel || t("panel.common.save")}</button>
  </>}>
    <label className="field-label">{request.title}
      <input
        className="input"
        value={value}
        maxLength={60}
        autoFocus
        onChange={event => setValue(event.target.value)}
        onKeyDown={event => { if (event.key === "Enter") submit(); }}
      />
    </label>
    {request.hint ? <p className="modal-text">{request.hint}</p> : null}
  </Modal>;
}

/** `const [ask, dialog] = usePrompt(); const name = await ask({...});` */
export function usePrompt(): [(request: PromptRequest) => Promise<string | null>, ReactNode] {
  const [pending, setPending] = useState<{ request: PromptRequest; resolve: (value: string | null) => void } | null>(null);
  const ask = (request: PromptRequest) => new Promise<string | null>(resolve => setPending({ request, resolve }));
  const dialog = pending ? <PromptModal request={pending.request} onResolve={value => { pending.resolve(value); setPending(null); }} /> : null;
  return [ask, dialog];
}

/** `const [confirm, dialog] = useConfirm(); if (await confirm({...})) …` */
export function useConfirm(): [(request: ConfirmRequest) => Promise<boolean>, ReactNode] {
  const [pending, setPending] = useState<{ request: ConfirmRequest; resolve: (ok: boolean) => void } | null>(null);
  const ask = (request: ConfirmRequest) => new Promise<boolean>(resolve => setPending({ request, resolve }));
  const dialog = pending ? <ConfirmDialog request={pending.request} onResolve={ok => { pending.resolve(ok); setPending(null); }} /> : null;
  return [ask, dialog];
}

/** Qisqa xabar (toast) — amal natijasi.  Javobsiz tugma buzuq tugmadan
 *  farq qilmaydi. */
export function useToast(): [(message: string, ok?: boolean) => void, ReactNode] {
  const [toast, setToast] = useState<{ message: string; ok: boolean } | null>(null);
  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(null), 3200);
    return () => window.clearTimeout(timer);
  }, [toast]);
  const show = (message: string, ok = true) => setToast({ message, ok });
  const node = toast ? <div className={`toast${toast.ok ? "" : " toast-error"}`} role="status">{toast.message}</div> : null;
  return [show, node];
}

/** Oy tanlagich: 1/3/6/12 chip + ixtiyoriy son.  Obuna, hisob va
 *  uzaytirish uchun bitta shakl. */
export function MonthPicker({ value, onChange, max = 60 }: { value: number; onChange: (months: number) => void; max?: number }) {
  return <div className="month-picker">
    <div className="chip-row">
      {[1, 3, 6, 12].map(months => <button key={months} type="button" className={`chip${value === months ? " active" : ""}`} onClick={() => onChange(months)}>{t("panel.shell.months_count", { count: months })}</button>)}
    </div>
    <label className="field-label">{t("panel.shell.other_number")}<input className="input" type="number" min={1} max={max} value={value} onChange={event => onChange(Math.max(1, Math.min(max, Number(event.target.value) || 1)))} /></label>
  </div>;
}

/** Nusxalanadigan maydon: havola yoki kod + tugma. */
export function CopyField({ value, label = t("panel.common.copy") }: { value: string; label?: string }) {
  return <div className="copy-field"><input readOnly value={value} onFocus={event => event.currentTarget.select()} /><CopyButton value={value} label={label} /></div>;
}

export function PasswordInput({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  const [show, setShow] = useState(false);
  return <span className="pw-wrap">
    <input {...rest} className={className} type={show ? "text" : "password"} />
    <button
      type="button"
      className="pw-eye"
      tabIndex={-1}
      aria-label={t(show ? "panel.login.hide_password" : "panel.login.show_password")}
      onClick={() => setShow(value => !value)}
    ><Icon name={show ? "eyeOff" : "eye"} size={18} /></button>
  </span>;
}

export function LoginScreen({ kind, onSubmit, busy, error, botUrl }: { kind: "owner" | "admin"; onSubmit: (username: string, password: string) => void; busy: boolean; error: string; botUrl?: string }) {
  return <main className="login-page">
    <section className="login-visual">
      <Logo />
      <div><span className="eyebrow">ENES CLOUD</span><h1>{t(kind === "owner" ? "panel.login.headline_owner" : "panel.login.headline_admin")}</h1><p>{t("panel.login.tagline")}</p></div>
      <div className="login-proof"><Icon name="shield"/><span>{t("panel.login.secure_note")}</span></div>
    </section>
    <section className="login-panel">
      {/* Tema tugmasi kirish ekranida ham kerak: paneldagisi faqat
          kirgandan keyin ko'rinadi, ya'ni kechasi login sahifasini
          ochgan odam yorug' ekranni almashtira olmasdi. */}
      <div className="login-tools"><LangSwitch/><ThemeToggle/></div>
      <form onSubmit={(event) => { event.preventDefault(); const data = new FormData(event.currentTarget); onSubmit(String(data.get("username") || ""), String(data.get("password") || "")); }}>
        <div className="login-mobile-logo"><Logo /></div>
        <span className="eyebrow">{t(kind === "owner" ? "panel.login.eyebrow_owner" : "panel.login.eyebrow_admin")}</span>
        <h2>{t("panel.login.welcome")}</h2><p>{t("panel.login.intro")}</p>
        <label>{t("panel.login.username")}<input name="username" autoComplete="username" required /></label>
        <label>{t("panel.login.password")}<PasswordInput name="password" autoComplete="current-password" required /></label>
        {error ? <div className="form-error" role="alert">{error}</div> : null}
        <button className="btn btn-primary btn-wide" disabled={busy}>{busy ? t("panel.login.checking") : t("panel.login.submit")}</button>
        {/* Parolsiz yo'l: bot bir martalik havola yuboradi.  Do'kon
            egasi uchun ko'pincha bu yagona qulay kirish usuli. */}
        {botUrl ? <p className="login-alt">{t("panel.login.forgot")} <a href={botUrl} target="_blank" rel="noreferrer">{t("panel.login.bot_link")}</a></p> : null}
      </form>
    </section>
  </main>;
}
