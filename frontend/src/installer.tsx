import { StrictMode, useCallback, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { api, clearToken, login, logout as serverLogout, registerInstaller, tokenFor, whoAmI, type PortalAccount } from "./api";
import { AppShell, Avatar, Card, EmptyState, LangSwitch, LoginScreen, Modal, PageHeader, PasswordInput, Skeleton, SUPPORT_PHONE, SUPPORT_PHONE_LABEL, ThemeToggle, useToast, type NavItem } from "./components";
import { InstallerJobs, InstallerSite, SITE_TABS, type Assignment } from "./InstallerJobs";
import { usePanelRoute } from "./router";
import { Icon, Logo } from "./icons";
import { initLang, t } from "./i18n";
import { applyTheme, readTheme } from "./theme";
import "./styles.css";

/* O'rnatuvchi (usta) paneli.
 *
 * 2026-09-12 gacha bu yakka qo'lda yozilgan `cloud/static/installer.html`
 * edi — oxirgi eski statik panel.  Natijasi: faqat o'zbekcha, telefon
 * uchun QA qilinmagan, API yiqilsa xato KO'RSATMASDI va brauzer
 * oynalari (`alert`/`confirm`) bilan ishlardi — Telegram WebView'da
 * ular ko'rsatilmasligi mumkin va amal jimgina o'lardi.  Usta esa
 * aynan obyektda, telefondan ishlaydi.
 *
 * Qobiq `owner.tsx`/`admin.tsx` naqshida: `AppShell`, `LoginScreen`,
 * `PageHeader`, `Card`, `usePanelRoute`.
 */

/* Yorliq matn emas, katalog KALITI: modul yuklanganda til hali
   tanlanmagan (`initLang()` shu faylning oxirida chaqiriladi), ya'ni bu
   yerda `t()` ishlatilsa menyu DOIM o'zbekcha qolardi — adminda aynan
   shunday bitta yorliq qotib qolgan edi. */
const NAV_ITEMS: Array<{ id: string; key: string; icon: string }> = [
  { id: "jobs", key: "panel.installer.nav.jobs", icon: "store" },
  { id: "help", key: "panel.installer.nav.help", icon: "report" },
];

const ROUTE_IDS = NAV_ITEMS.map(item => item.id);
/* Telefon pastidagi menyu: ikki bo'limning ikkalasi ham.  Ro'yxat
   `AppShell` ga ATAYLAB propda beriladi — ilgari u komponent ichida
   qotirilgan edi va yangi bo'lim mobil menyuda jimgina yo'q bo'lardi. */
const MOBILE_NAV = ROUTE_IDS;

/** Ro'yxatdan o'tish — MODAL oynada.
 *
 * Eski panelda kirish va ro'yxatdan o'tish formalari yonma-yon turardi:
 * telefonda ikkinchisi ekrandan tushib ketar va yangi usta uni umuman
 * ko'rmasdi.  Oyna ichida fokus tuzoqda (`Modal` → `useFocusTrap`) —
 * Telegram WebView'da bu shart, u yerda brauzer oynalari yo'q. */
function RegisterModal({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    if (!data.get("consent")) { setError(t("panel.installer.register.consent_required")); return; }
    setBusy(true);
    setError("");
    try {
      await registerInstaller({
        full_name: String(data.get("full_name") || ""),
        phone: String(data.get("phone") || ""),
        company: String(data.get("company") || ""),
        username: String(data.get("username") || ""),
        password: String(data.get("password") || ""),
        consent: true,
      });
      onDone();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("panel.installer.register.failed"));
    } finally {
      setBusy(false);
    }
  };

  return <Modal title={t("panel.installer.register.title")} onClose={onClose}>
    <form onSubmit={submit}>
      <p className="modal-text">{t("panel.installer.register.text")}</p>
      <label className="field-label">{t("panel.installer.register.full_name")}
        <input className="input" name="full_name" required minLength={2} maxLength={120} autoComplete="name"/>
      </label>
      <label className="field-label">{t("panel.installer.register.phone")}
        <input className="input" name="phone" required inputMode="tel" autoComplete="tel" placeholder="+998 90 000 00 00"/>
      </label>
      <label className="field-label">{t("panel.installer.register.company")} <small>{t("panel.common.optional")}</small>
        <input className="input" name="company" maxLength={160} autoComplete="organization"/>
      </label>
      <label className="field-label">{t("panel.installer.register.username")}
        <input className="input" name="username" required minLength={3} autoComplete="username"/>
      </label>
      <label className="field-label">{t("panel.installer.register.password")}
        <PasswordInput className="input" name="password" required minLength={10} autoComplete="new-password"/>
        <small>{t("panel.installer.register.password_hint")}</small>
      </label>
      <label className="consent-row">
        <input type="checkbox" name="consent"/>
        <span>{t("panel.installer.register.consent")}</span>
      </label>
      {error ? <div className="form-error" role="alert">{error}</div> : null}
      <button className="btn btn-primary btn-wide" disabled={busy}>
        {busy ? t("panel.common.saving") : t("panel.installer.register.submit")}
      </button>
    </form>
  </Modal>;
}

/** Yo'riqnoma va yordam — tasdiq kutayotgan usta uchun ham ochiq.
 *
 * Nega alohida bo'lim: yangi usta birinchi navbatda RASMLI yo'riqnomani
 * ko'rishi kerak, obyektlar esa admin tasdig'idan keyin ochiladi.
 * Aloqa raqami ham shu yerda: panel «bizga yozing» deydi-yu, qayerga
 * yozishni ko'rsatmasligi eski panelning xatosi edi. */
function InstallerHelp({ account }: { account: PortalAccount | null }) {
  return <>
    <PageHeader title={t("panel.installer.help.title")} subtitle={t("panel.installer.help.subtitle")}/>
    <Card>
      <div className="card-head">
        <div><h2>{t("panel.installer.help.guide_title")}</h2><p>{t("panel.installer.help.guide_text")}</p></div>
      </div>
      <div className="card-body">
        <a className="btn btn-primary" href="/installer-guide" target="_blank" rel="noreferrer"><Icon name="report"/>{t("panel.installer.help.guide_button")}</a>
      </div>
    </Card>
    <Card className="section-gap">
      <div className="card-head">
        <div><h2>{t("panel.installer.help.support_title")}</h2><p>{t("panel.installer.help.support_text")}</p></div>
      </div>
      <div className="card-body">
        <a className="btn" href={`tel:${SUPPORT_PHONE}`}><Icon name="bell"/>{SUPPORT_PHONE_LABEL}</a>
      </div>
    </Card>
    {account ? <Card className="section-gap">
      <div className="card-head">
        <div><h2>{t("panel.installer.help.account_title")}</h2><p>{account.username}</p></div>
      </div>
      <div className="card-body">
        <p className="metric-note">{account.full_name || ""}{account.company ? ` · ${account.company}` : ""}</p>
      </div>
    </Card> : null}
  </>;
}

function InstallerApp() {
  const [authenticated, setAuthenticated] = useState(() => Boolean(tokenFor("installer")));
  const [account, setAccount] = useState<PortalAccount | null>(null);
  const [checking, setChecking] = useState(() => Boolean(tokenFor("installer")));
  const [busy, setBusy] = useState(false);
  const [loginError, setLoginError] = useState("");
  const [accountError, setAccountError] = useState("");
  const [registering, setRegistering] = useState(false);
  const [jobs, setJobs] = useState<Assignment[] | null>(null);
  const [jobsError, setJobsError] = useState("");
  const [drawer, setDrawer] = useState(false);
  const [active, navigateTo, siteId, subRoute] = usePanelRoute("/installer", ROUTE_IDS, "jobs");
  const [toast, toastNode] = useToast();

  const nav: NavItem[] = useMemo(() => NAV_ITEMS.map(({ id, key, icon }) => ({ id, icon, label: t(key) })), []);

  /* Hisob holati HAR ochilishda so'raladi: token `pending` hisobda ham
     ishlaydi, lekin vazifalar ro'yxati berilmaydi.  Ikkalasini
     ajratmasa panel bo'sh ro'yxat ko'rsatib «obyekt yo'q» deb yolg'on
     aytardi. */
  const refreshAccount = useCallback(async () => {
    setAccountError("");
    try {
      setAccount(await whoAmI("installer"));
    } catch (reason) {
      /* 401 — sessiya bekor qilingan (yoki hisob bloklangan): kalit
         o'chadi va kirish ekraniga qaytamiz.  Boshqa xato — tarmoq
         yoki server; token joyida qoladi va usta «Qayta urinish»ni
         bosadi.  Ikkalasini aralashtirsak obyektdagi bir daqiqalik
         uzilish ustani tizimdan chiqarib yuborardi. */
      const status = (reason as { status?: number } | null)?.status;
      if (status === 401) { clearToken("installer"); setAuthenticated(false); setAccount(null); }
      else setAccountError(reason instanceof Error ? reason.message : t("panel.installer.login.check_failed"));
    } finally {
      setChecking(false);
    }
  }, []);

  useEffect(() => {
    if (!authenticated) { setChecking(false); return; }
    void refreshAccount();
  }, [authenticated, refreshAccount]);

  const loadJobs = useCallback(async () => {
    setJobsError("");
    try {
      const result = await api<{ assignments: Assignment[] }>("/api/v1/installer/assignments", "installer");
      setJobs(result.assignments || []);
    } catch (reason) {
      /* Xatoda ro'yxat BO'SH bo'ladi, `null` emas: `null` «hali
         yuklanmoqda» degani va skelet xato satri ostida abadiy
         qolib ketardi (2026-09-11 QA saboqi). */
      setJobs([]);
      setJobsError(reason instanceof Error ? reason.message : t("panel.installer.jobs.load_failed"));
    }
  }, []);

  const ready = account?.status === "active";
  useEffect(() => {
    if (!authenticated || !ready) return;
    void loadJobs();
  }, [authenticated, ready, loadJobs]);

  const submit = async (username: string, password: string) => {
    setBusy(true);
    setLoginError("");
    try {
      await login(username, password, "installer");
      setAuthenticated(true);
      setChecking(true);
    } catch (reason) {
      setLoginError(reason instanceof Error ? reason.message : t("panel.installer.login.failed"));
    } finally {
      setBusy(false);
    }
  };

  const logout = () => {
    void serverLogout("installer");
    setAuthenticated(false);
    setAccount(null);
    setJobs(null);
  };

  /* «Yana» — yon menyu.  `AppShell` bu tugmani DOIM chizadi, ya'ni uni
     qabul qilmasa telefonda bosiladigan, lekin hech narsa qilmaydigan
     tugma qolardi.  Ichida til va tema tanlagichi: topbardagi
     nusxalari 760 px dan pastda yashiriladi va usta obyektda aynan
     telefonda turadi — ruscha panelga o'tishning boshqa yo'li yo'q. */
  const navigate = (id: string, param = "", sub = "") => {
    if (id === "more") { setDrawer(true); return; }
    navigateTo(id, param, sub);
    setDrawer(false);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  if (!authenticated) {
    return <>
      <LoginScreen
        kind="installer"
        onSubmit={submit}
        busy={busy}
        error={loginError}
        extra={<p className="login-alt">
          {t("panel.installer.login.no_account")}{" "}
          <button type="button" className="link-button" onClick={() => setRegistering(true)}>{t("panel.installer.login.register")}</button>
          {" · "}
          <a href="/installer-guide" target="_blank" rel="noreferrer">{t("panel.installer.login.guide")}</a>
        </p>}
      />
      {registering ? <RegisterModal
        onClose={() => setRegistering(false)}
        onDone={() => { setRegistering(false); setAuthenticated(true); setChecking(true); toast(t("panel.installer.register.done")); }}
      /> : null}
      {toastNode}
    </>;
  }

  if (checking) {
    return <div className="login-page">
      <section className="login-visual"><Logo/><div><span className="eyebrow">{t("panel.installer.login.eyebrow")}</span><h1>{t("panel.common.loading")}</h1></div></section>
      <section className="login-panel"><div style={{ width: "min(390px,100%)" }}><Skeleton height={54}/><div style={{ height: 14 }}/><Skeleton height={150}/></div></section>
    </div>;
  }

  /* Hisob olinmadi (tarmoq yoki server).  Bu holat ALOHIDA chiziladi:
     usiz panel ochilar, lekin `account` bo'sh bo'lgani uchun ish
     ro'yxati abadiy skeletda qolardi — xatoning eng yomon ko'rinishi,
     chunki u ishlayotgandek tuyuladi. */
  if (!account) {
    return <div className="login-page">
      <section className="login-visual"><Logo/><div><span className="eyebrow">{t("panel.installer.login.eyebrow")}</span><h1>{t("panel.installer.login.check_failed")}</h1></div></section>
      <section className="login-panel"><div style={{ width: "min(390px,100%)" }}>
        <p className="metric-note">{accountError || t("panel.error.request_failed")}</p>
        <div className="page-actions" style={{ marginTop: 14 }}>
          <button className="btn btn-primary" onClick={() => { setChecking(true); void refreshAccount(); }}>{t("panel.common.retry")}</button>
          <button className="btn" onClick={logout}>{t("panel.common.logout")}</button>
        </div>
      </div></section>
    </div>;
  }

  const siteTab = (SITE_TABS as readonly string[]).includes(subRoute) ? subRoute : SITE_TABS[0];
  return <AppShell
    nav={nav}
    mobileNav={MOBILE_NAV}
    active={active}
    onNavigate={id => navigate(id)}
    title={nav.find(item => item.id === active)?.label || t("panel.installer.title")}
    subtitle={t("panel.installer.subtitle")}
    onLogout={logout}
    headerActions={<>
      <a className="btn btn-icon" href="/installer-guide" target="_blank" rel="noreferrer" aria-label={t("panel.installer.help.guide_button")}><Icon name="report"/></a>
      {/* Kim kirgani KO'RINSIN: usta bir necha obyektda ishlaydi va
          begona telefondan kirib qolgani ilgari faqat 403 xatosidan
          bilinardi.  Telefonda chip faqat avatarga siqiladi. */}
      <div className="topbar-user"><Avatar name={account.full_name || account.username}/><div><b>{account.full_name || account.username}</b><small>{t("panel.installer.role")}</small></div></div>
    </>}
  >
    {/* Tasdiq kutayotgan hisob: bo'sh ro'yxat KO'RSATILMAYDI.  Eski
        panelda ham shu karta bor edi va uni saqlab qoldik — usta
        «men nimani kutyapman?» degan savolga javob olishi kerak.
        `disabled` holat bu yerga YETIB KELMAYDI: server bunday tokenga
        401 beradi (`_require_portal_principal`) va panel kirish
        ekraniga qaytadi. */}
    {account.status !== "active"
      ? <>
        <PageHeader title={t("panel.installer.pending.title")} subtitle={t("panel.installer.pending.subtitle")}/>
        <Card><div className="card-body">
          <EmptyState icon="shield" title={t("panel.installer.pending.title")} detail={t("panel.installer.pending.text")}/>
          <a className="btn btn-primary btn-wide" href="/installer-guide" target="_blank" rel="noreferrer">{t("panel.installer.help.guide_button")}</a>
        </div></Card>
      </>
      : active === "help"
        ? <InstallerHelp account={account}/>
        : siteId
          ? <InstallerSite
            siteId={siteId}
            tab={siteTab}
            status={(jobs || []).find(job => job.site_id === siteId)?.status || ""}
            onSelectTab={tab => navigate("jobs", siteId, tab)}
            onBack={() => navigate("jobs")}
            onStatusChanged={() => void loadJobs()}
          />
          : <InstallerJobs
            jobs={jobs}
            error={jobsError}
            onRetry={() => void loadJobs()}
            onOpen={id => navigate("jobs", id, SITE_TABS[0])}
          />}
    {drawer ? <div className="drawer-backdrop" onClick={() => setDrawer(false)}>
      <aside className="drawer" onClick={event => event.stopPropagation()}>
        <div className="drawer-head"><Logo/><button className="btn btn-icon" aria-label={t("panel.common.close")} onClick={() => setDrawer(false)}><Icon name="close"/></button></div>
        <nav>
          {nav.map(item => <button key={item.id} className={active === item.id ? "active" : ""} onClick={() => navigate(item.id)}><Icon name={item.icon}/>{item.label}</button>)}
          <button onClick={logout}><Icon name="logout"/>{t("panel.common.logout")}</button>
        </nav>
        <div className="drawer-tools"><LangSwitch/><ThemeToggle/></div>
      </aside>
    </div> : null}
    {toastNode}
  </AppShell>;
}

/* Tema qobiqdagi boot skriptida allaqachon qo'yilgan (chizishdan
 * oldin).  Bu yerda yana bir marta chaqiriladi: skript faqat ATRIBUTNI
 * qo'yadi, `theme-color` metasi esa tizim rejimida ham to'g'ri bo'lishi
 * kerak — uni JS hisoblab beradi. */
/* Til birinchi chizishdan oldin: `document.documentElement.lang` ham shu
 * yerda qo'yiladi — brauzerning imlo tekshiruvi va ekran o'quvchisi
 * to'g'ri tilni bilishi uchun. */
initLang();
applyTheme(readTheme());

createRoot(document.getElementById("root")!).render(<StrictMode><InstallerApp/></StrictMode>);
