import { useEffect, useState } from "react";
import { claimDevice, login, peekConnect, registerTrial, type PendingDevice } from "./api";
import { PasswordInput } from "./components";
import { t } from "./i18n";
import { Icon, Logo } from "./icons";

/* Do'kon kompyuterini hisobga ulash ekrani.
 *
 * Dastur o'rnatilgach brauzerni `/owner?connect=<token>` da ochadi.
 * Bu yerda ikki holat bo'lishi mumkin:
 *
 *   1. Odam hali ro'yxatdan o'tmagan — do'kon ochadi (login va parolni
 *      O'ZI tanlaydi) yoki mavjud hisobiga kiradi;
 *   2. Allaqachon kirgan — shunchaki "shu kompyuterni ulaymizmi?"
 *      degan tasdiq.
 *
 * Ikkala yo'l ham bitta narsa bilan tugaydi: `claimDevice(token)`.
 */

function VerifyCard({ device }: { device: PendingDevice | null }) {
  if (!device) return null;
  return (
    <div className="verify-card">
      <div className="verify-head">
        <Icon name="server" />
        <div>
          <b>{device.label || t("panel.connect.device_default")}</b>
          <small>
            {device.os_name || device.product_name}
            {device.local_ip_masked ? ` · ${device.local_ip_masked}` : ""}
          </small>
        </div>
      </div>
      {/* Kodni ikkala ekranda solishtirish — "qo'shnining kompyuterini
          tasdiqlab yubordim" xatosining yagona to'sig'i. */}
      <div className="verify-code">
        <span>{t("panel.connect.code_label")}</span>
        <b>{device.verify_code}</b>
      </div>
      <p className="verify-hint">
        {t("panel.connect.code_hint")}
      </p>
    </div>
  );
}

export function Connect({
  token,
  authenticated,
  onConnected,
}: {
  token: string;
  authenticated: boolean;
  onConnected: () => void;
}) {
  const [device, setDevice] = useState<PendingDevice | null>(null);
  const [checking, setChecking] = useState(true);
  const [mode, setMode] = useState<"register" | "login">("register");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  useEffect(() => {
    let stopped = false;
    peekConnect(token).then(found => {
      if (stopped) return;
      setDevice(found);
      setChecking(false);
    });
    return () => { stopped = true; };
  }, [token]);

  const attach = async () => {
    await claimDevice(token);
    setDone(true);
    // Ega natijani o'qishga ulgursin — darhol o'tib ketsak "ulandimi?"
    // degan savol qoladi.
    window.setTimeout(onConnected, 1400);
  };

  const submitRegister = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      const username = String(data.get("username") || "");
      const password = String(data.get("password") || "");
      await registerTrial({
        phone: String(data.get("phone") || ""),
        full_name: String(data.get("full_name") || ""),
        company: String(data.get("company") || ""),
        username,
        password,
        consent: true,
      });
      await login(username, password, "owner");
      await attach();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("panel.connect.register_failed"));
    } finally {
      setBusy(false);
    }
  };

  const submitLogin = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      await login(String(data.get("username") || ""), String(data.get("password") || ""), "owner");
      await attach();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("panel.connect.login_failed"));
    } finally {
      setBusy(false);
    }
  };

  const confirm = async () => {
    setBusy(true);
    setError("");
    try {
      await attach();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("panel.connect.attach_failed"));
    } finally {
      setBusy(false);
    }
  };

  const visual = (
    <section className="login-visual">
      <Logo />
      <div>
        <span className="eyebrow">{t("panel.connect.brand")}</span>
        <h1>{t("panel.connect.hero_title")}</h1>
        <p>{t("panel.connect.hero_text")}</p>
      </div>
      <div className="login-proof">
        <Icon name="shield" />
        <span>{t("panel.connect.secure_note")}</span>
      </div>
    </section>
  );

  if (done) {
    return (
      <main className="login-page">
        {visual}
        <section className="login-panel">
          <div className="connect-done">
            <span className="connect-tick"><Icon name="shield" size={26} /></span>
            <h2>{t("panel.connect.done_title")}</h2>
            <p>{t("panel.connect.done_text")}</p>
          </div>
        </section>
      </main>
    );
  }

  // Havola eskirgan yoki allaqachon ishlatilgan.
  if (!checking && !device) {
    return (
      <main className="login-page">
        {visual}
        <section className="login-panel">
          <div className="connect-done">
            <h2>{t("panel.connect.expired_title")}</h2>
            <p>
              {t("panel.connect.expired_text")}
            </p>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="login-page">
      {visual}
      <section className="login-panel">
        {authenticated ? (
          <div className="connect-form">
            <span className="eyebrow">{t("panel.connect.eyebrow")}</span>
            <h2>{t("panel.connect.confirm_title")}</h2>
            <VerifyCard device={device} />
            {error ? <div className="form-error" role="alert">{error}</div> : null}
            <button className="btn btn-primary btn-wide" disabled={busy} onClick={() => void confirm()}>
              {busy ? t("panel.connect.connecting") : t("panel.connect.confirm_button")}
            </button>
          </div>
        ) : (
          <div className="connect-form">
            <div className="login-mobile-logo"><Logo /></div>
            <VerifyCard device={device} />
            <div className="segmented connect-tabs">
              <button className={mode === "register" ? "active" : ""} onClick={() => setMode("register")}>
                {t("panel.connect.tab_register")}
              </button>
              <button className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>
                {t("panel.connect.tab_login")}
              </button>
            </div>

            {mode === "register" ? (
              <form onSubmit={submitRegister}>
                <h2>{t("panel.connect.register_title")}</h2>
                <p>{t("panel.connect.register_text")}</p>
                <label>{t("panel.connect.field.company")}<input name="company" required minLength={2} maxLength={120} /></label>
                <label>{t("panel.connect.field.full_name")}<input name="full_name" required minLength={2} autoComplete="name" /></label>
                <label>{t("panel.connect.field.phone")}<input name="phone" required inputMode="tel" autoComplete="tel" placeholder="+998 90 000 00 00" /></label>
                <label>{t("panel.connect.field.username")}<input name="username" required autoComplete="username" placeholder={t("panel.connect.username_placeholder")} /></label>
                <label>
                  {t("panel.connect.field.password")}
                  <PasswordInput name="password" required minLength={10} autoComplete="new-password" />
                  <small>{t("panel.connect.password_hint")}</small>
                </label>
                {error ? <div className="form-error" role="alert">{error}</div> : null}
                <button className="btn btn-primary btn-wide" disabled={busy}>
                  {busy ? t("panel.connect.opening") : t("panel.connect.register_button")}
                </button>
                {/* Jumla uch bo'lakda: o'zbekchada «-ga» qo'shimchasi
                    havola so'ziga YOPISHIB keladi («shartlariga»), ya'ni
                    havolani bitta matn ichiga joylab bo'lmaydi. */}
                <p className="login-alt">
                  {t("panel.connect.consent_before")} <a href="/privacy" target="_blank" rel="noreferrer">{t("panel.connect.consent_link")}</a>{t("panel.connect.consent_after")}
                </p>
              </form>
            ) : (
              <form onSubmit={submitLogin}>
                <h2>{t("panel.connect.login_title")}</h2>
                <p>{t("panel.connect.login_text")}</p>
                <label>{t("panel.connect.field.username")}<input name="username" required autoComplete="username" /></label>
                <label>{t("panel.connect.field.password")}<PasswordInput name="password" required autoComplete="current-password" /></label>
                {error ? <div className="form-error" role="alert">{error}</div> : null}
                <button className="btn btn-primary btn-wide" disabled={busy}>
                  {busy ? t("panel.connect.checking") : t("panel.connect.login_button")}
                </button>
              </form>
            )}
          </div>
        )}
      </section>
    </main>
  );
}
