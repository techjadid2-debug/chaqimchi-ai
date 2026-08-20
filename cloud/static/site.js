(() => {
  // Sahifa mantig'i ataylab kichik: bitta lead forma, yuklab olish tugmasi
  // holati va tayyor paketlar.  Ilgari bu fayl to'liq tarif konfiguratorini
  // (checkbox, stepper, valyuta, sticky panel) olib yurardi — mijozlar uni
  // to'ldirmasdi, faqat chalg'irdi.  Chuqur minimalizm qarori: paket bosildi
  // → forma to'ldiriladi → biz qo'ng'iroq qilamiz.

  async function submitLead(form, status, button, message, successText, cameras = 4) {
    if (!form.reportValidity()) return;
    button.disabled = true;
    status.className = "form-status";
    status.textContent = "So‘rov yuborilmoqda…";
    const data = new FormData(form);
    const payload = {
      // Asosiy formada ism maydoni yo'q; yuklab olish formasi uni hali
      // yashirin maydonda yuboradi.
      full_name: String(data.get("full_name") || "").trim() || null,
      phone: String(data.get("phone") || "").trim(),
      company: String(data.get("company") || "").trim() || null,
      city: null,
      cameras,
      message: message || String(data.get("message") || "").trim() || null,
      consent: data.get("consent") === "on",
      website: String(data.get("website") || ""),
    };
    try {
      const response = await fetch("/api/v1/public/leads", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "So‘rov yuborilmadi");
      status.className = "form-status ok";
      status.textContent = successText || body.message;
      form.reset();
    } catch (error) {
      status.className = "form-status error";
      status.textContent = error.message || "Xatolik yuz berdi. Qayta urinib ko‘ring.";
    } finally { button.disabled = false; }
  }

  // ── Ro'yxatdan o'tish: do'kon o'zi ochiladi ───────────────────────────
  //
  // Ilgari bu forma faqat telefon raqamini yuborardi va qolgan hammasi
  // qo'lda edi: admin do'kon ochib, parol yaratib, uni Telegramda
  // yuborardi.  Endi mijoz login/parolni o'zi tanlaydi va javobda darhol
  // ULANISH KODI bilan yuklab olish havolasini oladi — dastur cloudga
  // o'zi ulanadi.
  const leadForm = document.getElementById("leadForm");
  const leadMessage = document.getElementById("leadMessage");
  const trialResult = document.getElementById("trialResult");

  function showTrial(data) {
    const link = document.getElementById("trialDownload");
    const hint = document.getElementById("trialHint");
    if (link) link.href = data.download_windows_url || "/api/v1/public/download-installer";
    if (hint) {
      const login = data.login_error
        ? "Panel logini tayyor emas — biz bog‘lanamiz."
        : `Panel: <b>${esc(data.owner_url || "")}</b> · login: <b>${esc(data.username || "")}</b>`;
      hint.innerHTML =
        `Fayl nomida ulanish kodi bor — o‘rnatgach dastur cloudga <b>o‘zi</b> ulanadi. ` +
        `${login}. Parolni faqat siz bilasiz: yo‘qotsangiz biz tiklaymiz. ` +
        `<b>${Number(data.months) || 3} oy bepul</b>, karta kerak emas.`;
    }
    if (leadForm) leadForm.hidden = true;
    if (trialResult) trialResult.hidden = false;
  }

  /** Matnni HTML'ga xavfsiz qo'yish (login mijozdan keladi). */
  function esc(value) {
    return String(value).replace(/[&<>"']/g, (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char],
    );
  }

  async function startTrial(form, status, button) {
    if (!form.reportValidity()) return;
    button.disabled = true;
    status.className = "form-status";
    status.textContent = "Do‘kon ochilmoqda…";
    const data = new FormData(form);
    const payload = {
      phone: String(data.get("phone") || "").trim(),
      username: String(data.get("username") || "").trim().toLowerCase(),
      password: String(data.get("password") || ""),
      company: String(data.get("company") || "").trim() || null,
      consent: data.get("consent") === "on",
      website: String(data.get("website") || ""),
    };
    try {
      const response = await fetch("/api/v1/public/quick-trial", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
      });
      const body = await response.json();
      if (response.status === 503) {
        // Sinov o'rinlari to'ldi — berk ko'cha bo'lmasin: o'sha raqam
        // bilan odatdagi ariza yuboriladi.
        status.className = "form-status";
        status.textContent = body.detail || "O‘rinlar to‘ldi — so‘rovingiz yuborilmoqda…";
        button.disabled = false;
        submitLead(form, status, button, "Sinov o'rinlari to'lgan paytdagi so'rov",
          "So‘rovingiz qabul qilindi. Joy ochilishi bilan bog‘lanamiz.");
        return;
      }
      if (!response.ok) throw new Error(body.detail || "Ro‘yxatdan o‘tib bo‘lmadi");
      status.className = "form-status ok";
      status.textContent = body.message || "Do‘koningiz ochildi.";
      showTrial(body);
    } catch (error) {
      status.className = "form-status error";
      status.textContent = error.message || "Xatolik yuz berdi. Qayta urinib ko‘ring.";
    } finally { button.disabled = false; }
  }

  if (leadForm) {
    leadForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const status = document.getElementById("formStatus");
      const button = leadForm.querySelector("button[type=submit]");
      // Login maydoni bo'lmasa (eski keshdagi sahifa) — eski yo'l bilan
      // ariza yuboriladi, tugma baribir ishlaydi.
      if (leadForm.querySelector("#username")) {
        startTrial(leadForm, status, button);
      } else {
        submitLead(leadForm, status, button, leadMessage ? leadMessage.value : null,
          "So‘rovingiz qabul qilindi. Tez orada bog‘lanamiz.");
      }
    });
  }

  /** Formaga texnik izoh yozib, mijozni formaga olib boradi. */
  function goToForm(message) {
    if (leadMessage) leadMessage.value = message;
    const section = document.getElementById("aloqa");
    if (section) section.scrollIntoView({ behavior: "smooth", block: "start" });
    const phone = document.getElementById("phone");
    if (phone) setTimeout(() => phone.focus({ preventScroll: true }), 400);
  }

  const turnkeyLink = document.getElementById("turnkeyLink");
  if (turnkeyLink) {
    turnkeyLink.addEventListener("click", () => {
      goToForm("Kompyuterim yo'q — usta va qurilma bo'yicha maslahat kerak");
    });
  }

  // ── Yuklab olish holati ───────────────────────────────────────────────
  //
  // Sahifaga qo'lda "115 MB" deb yozib qo'yish aynan shu yerda xatoga olib
  // kelgan edi — matn turardi, fayl esa yo'q edi va tugma 503 qaytarardi.
  // Shuning uchun holat serverdan so'raladi.
  const notifyForm = document.getElementById("notifyForm");
  const downloadReady = document.getElementById("downloadReady");

  if (notifyForm) {
    notifyForm.addEventListener("submit", (event) => {
      event.preventDefault();
      submitLead(
        notifyForm,
        document.getElementById("notifyStatus"),
        notifyForm.querySelector("button[type=submit]"),
        "Windows dasturi tayyor bo‘lganda xabar berilsin",
        "Raqamingiz qabul qilindi. Dastur tayyor bo‘lgan kuni birinchilardan bo‘lib sizga yuboramiz.",
      );
    });
  }

  if (notifyForm && downloadReady) {
    fetch("/api/v1/public/windows-release")
      .then((response) => response.json())
      .then((release) => {
        if (!release.available) throw new Error("hali nashr qilinmagan");
        // Versiya ko'rinishi shart: usiz yangi reliz chiqqanini sahifadan
        // bilib bo'lmaydi va eski fayl qayta yuklab olinadi.
        const label = document.getElementById("downloadVersion");
        if (label && release.version) {
          const size = release.size_mb ? ` · ${release.size_mb} MB` : "";
          label.textContent = `Versiya ${release.version}${size}`;
          label.hidden = false;
        }
        downloadReady.hidden = false;
        notifyForm.hidden = true;
      })
      .catch(() => {
        downloadReady.hidden = true;
        notifyForm.hidden = false;
      });
  }

  // ── Tarif: bitta "Chaqimchi Lite" kartasi ─────────────────────────────
  //
  // Qaror (2026-08-17): 3 ta paket o'rniga bitta tarif — $20/oy, hammasi
  // ichida.  Narx sahifaga yozilmaydi: serverdan keladi (kurs bilan),
  // ya'ni narx o'zgarsa sayt o'zi yangilanadi.
  let pricing = null;

  const groups = (value) => String(value).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  // Serverdagi `(cents * rate + 99) // 100` bilan bir xil: sayt va
  // hisob-faktura bitta so'mni ham farq qilmasligi kerak.
  const toUzs = (cents) => Math.floor((cents * pricing.usd_rate_uzs + 99) / 100);
  const money = (cents) => `${groups(toUzs(cents))} so‘m`;

  function renderLite() {
    const cents = pricing.base.monthly_usd_cents;
    const usd = cents % 100 ? (cents / 100).toFixed(2) : String(cents / 100);
    const priceEl = document.getElementById("litePrice");
    if (priceEl) priceEl.textContent = money(cents);
    const usdEl = document.getElementById("litePriceUsd");
    if (usdEl) usdEl.textContent = `Bu — oyiga $${usd}. So‘m narxi kurs bo‘yicha hisoblanadi.`;
    const list = document.getElementById("liteIncludes");
    if (list) {
      list.innerHTML = (pricing.base.includes || [])
        .map((item) => `<li>${String(item).replace(/[&<>"]/g, (c) => (
          { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]
        ))}</li>`)
        .join("");
    }
    const cta = document.getElementById("liteCta");
    if (cta) {
      cta.addEventListener("click", () => {
        goToForm(`Tarif: Chaqimchi Lite | Oyiga ${money(cents)} ($${usd})`);
      });
    }
  }

  fetch("/api/v1/public/pricing")
    .then((response) => response.json())
    .then((data) => {
      pricing = data;

      // Hero'dagi narx ilgagi: mijoz "qancha turadi?" degan savol bilan
      // keladi va javob uchun pastga tushishga majbur bo'lmasligi kerak.
      const heroPrice = document.getElementById("heroPrice");
      if (heroPrice) {
        heroPrice.textContent = `${money(pricing.base.monthly_usd_cents)}/oydan`;
        heroPrice.hidden = false;
      }

      // Funksiyalar hali qabul sinovidan o'tmagan bo'lsa buni
      // yashirmaymiz — bitta halol izoh.
      const note = document.getElementById("featureNote");
      if (note && pricing.features.length && pricing.features.every((item) => !item.available)) {
        note.textContent =
          "AI funksiyalari hozir birinchi do‘konlarda sinovdan o‘tmoqda. " +
          "Hozir so‘rov qoldirsangiz — ishga tushganda birinchi bo‘lib sizga ulanadi.";
        note.hidden = false;
      }

      renderLite();
    })
    .catch(() => {
      const card = document.getElementById("liteCard");
      if (card) {
        card.innerHTML =
          '<p class="preset-hint">Narxni yuklab bo‘lmadi. Sahifani yangilang yoki ' +
          '<a href="https://t.me/fibotai" target="_blank" rel="noopener noreferrer">@fibotai</a> ga yozing.</p>';
      }
    });
})();
