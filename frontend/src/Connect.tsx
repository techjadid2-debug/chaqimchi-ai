import { useEffect, useState } from "react";
import { claimDevice, login, peekConnect, registerTrial, type PendingDevice } from "./api";
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
          <b>{device.label || "Do‘kon kompyuteri"}</b>
          <small>
            {device.os_name || device.product_name}
            {device.local_ip_masked ? ` · ${device.local_ip_masked}` : ""}
          </small>
        </div>
      </div>
      {/* Kodni ikkala ekranda solishtirish — "qo'shnining kompyuterini
          tasdiqlab yubordim" xatosining yagona to'sig'i. */}
      <div className="verify-code">
        <span>Kompyuter ekranidagi kod</span>
        <b>{device.verify_code}</b>
      </div>
      <p className="verify-hint">
        Kod bir xil bo‘lmasa — tasdiqlamang va qo‘llab-quvvatlashga murojaat qiling.
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
      setError(reason instanceof Error ? reason.message : "Ro‘yxatdan o‘tish amalga oshmadi");
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
      setError(reason instanceof Error ? reason.message : "Kirish amalga oshmadi");
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
      setError(reason instanceof Error ? reason.message : "Ulash amalga oshmadi");
    } finally {
      setBusy(false);
    }
  };

  const visual = (
    <section className="login-visual">
      <Logo />
      <div>
        <span className="eyebrow">CHAQIMCHI CLOUD</span>
        <h1>Do‘kon kompyuteringiz tayyor.</h1>
        <p>Bir necha qadamdan keyin kameralaringiz raqamlarga aylanadi.</p>
      </div>
      <div className="login-proof">
        <Icon name="shield" />
        <span>Ma’lumotlar himoyalangan ulanish orqali uzatiladi</span>
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
            <h2>Ulandi</h2>
            <p>Kompyuter bir daqiqa ichida aloqaga chiqadi. Endi kameralarni ulaymiz.</p>
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
            <h2>Havola eskirgan</h2>
            <p>
              Do‘kon kompyuteridagi Chaqimchi dasturini qayta ishga tushiring — u yangi
              havola ochadi.
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
            <span className="eyebrow">KOMPYUTERNI ULASH</span>
            <h2>Shu kompyuterni ulaymizmi?</h2>
            <VerifyCard device={device} />
            {error ? <div className="form-error" role="alert">{error}</div> : null}
            <button className="btn btn-primary btn-wide" disabled={busy} onClick={() => void confirm()}>
              {busy ? "Ulanmoqda…" : "Ha, do‘konimga ulang"}
            </button>
          </div>
        ) : (
          <div className="connect-form">
            <div className="login-mobile-logo"><Logo /></div>
            <VerifyCard device={device} />
            <div className="segmented connect-tabs">
              <button className={mode === "register" ? "active" : ""} onClick={() => setMode("register")}>
                Yangi do‘kon
              </button>
              <button className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>
                Menda hisob bor
              </button>
            </div>

            {mode === "register" ? (
              <form onSubmit={submitRegister}>
                <h2>Do‘kon ochamiz</h2>
                <p>14 kun bepul. Karta so‘ralmaydi.</p>
                <label>Do‘kon nomi<input name="company" required minLength={2} maxLength={120} /></label>
                <label>Ismingiz<input name="full_name" required minLength={2} autoComplete="name" /></label>
                <label>Telefon<input name="phone" required inputMode="tel" autoComplete="tel" placeholder="+998 90 000 00 00" /></label>
                <label>Login<input name="username" required autoComplete="username" placeholder="dokonchi" /></label>
                <label>
                  Parol
                  <input name="password" type="password" required minLength={10} autoComplete="new-password" />
                  <small>Kamida 10 belgi, harf va raqam bo‘lsin</small>
                </label>
                {error ? <div className="form-error" role="alert">{error}</div> : null}
                <button className="btn btn-primary btn-wide" disabled={busy}>
                  {busy ? "Ochilmoqda…" : "Do‘konni ochish va ulash"}
                </button>
                <p className="login-alt">
                  Davom etish orqali <a href="/privacy" target="_blank" rel="noreferrer">maxfiylik shartlari</a>ga
                  rozilik bildirasiz.
                </p>
              </form>
            ) : (
              <form onSubmit={submitLogin}>
                <h2>Hisobingizga kiring</h2>
                <p>Kompyuter shu do‘konga ulanadi.</p>
                <label>Login<input name="username" required autoComplete="username" /></label>
                <label>Parol<input name="password" type="password" required autoComplete="current-password" /></label>
                {error ? <div className="form-error" role="alert">{error}</div> : null}
                <button className="btn btn-primary btn-wide" disabled={busy}>
                  {busy ? "Tekshirilmoqda…" : "Kirish va ulash"}
                </button>
              </form>
            )}
          </div>
        )}
      </section>
    </main>
  );
}
