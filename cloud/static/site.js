(() => {
  // Sahifa mantig'i ataylab kichik: bitta lead forma, yuklab olish tugmasi
  // holati va tarif kartalari.  Ilgari bu fayl to'liq tarif konfiguratorini
  // olib yurardi — mijozlar uni to'ldirmasdi, faqat chalg'irdi.

  // ── Til ────────────────────────────────────────────────────────────────
  //
  // Satrlar sahifaga QURISH paytida qo'yiladi (`scripts/build_site.py`,
  // `i18n/*.json` dagi `site.js.*` kalitlari).  Skript uchala tilda
  // BITTA fayl: brauzer keshi uchun ham, kesh tokeni uchun ham.  Kalit
  // yo'q bo'lsa kalitning o'zi qaytadi — bo'sh joy emas: yetishmagan
  // tarjima ekranda darrov ko'rinadi (`cloud/i18n.py` qoidasi).
  //
  // Ma'lumot `application/json` blokida, `window.__SITE__` da EMAS:
  // qiymat berish inline skript bo'lardi va CSP `script-src` uni
  // bloklardi.  `type` ijro etilmaydigan qilgani uchun bu blok
  // siyosatdan tashqarida qoladi.
  const holder = document.getElementById("site-data");
  const SITE = holder ? JSON.parse(holder.textContent) : {};
  const LANG = SITE.lang || document.documentElement.lang || "uz";
  const STRINGS = SITE.t || {};
  function T(key, params) {
    let text = Object.prototype.hasOwnProperty.call(STRINGS, key) ? STRINGS[key] : key;
    if (params) {
      for (const name of Object.keys(params)) text = text.split(`{${name}}`).join(String(params[name]));
    }
    return text;
  }

  async function submitLead(form, status, button, message, successText, cameras = 4) {
    if (!form.reportValidity()) return;
    button.disabled = true;
    status.className = "form-status";
    status.textContent = T("sending");
    const data = new FormData(form);
    const payload = {
      // Asosiy CTA faqat ism va telefonni so'raydi; qolgan tafsilotlar
      // jamoa qo'ng'irog'ida aniqlanadi.
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
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Lang": LANG },
        body: JSON.stringify(payload),
      });
      const body = await response.json();
      /* `detail` SATR bo'lsagina ko'rsatiladi.  FastAPI validatsiya
         xatosida u RO'YXAT qaytaradi va `new Error(list)` JavaScriptda
         **`[object Object]`** bo'lib chiqardi — mijoz shuni o'qirdi.
         Server tomonda ham handler qo'yilgan
         (`cloud/main.py: public_validation_error`), bu esa ikkinchi
         qator himoya: eski javob keshdan kelsa ham matn chiqadi. */
      if (!response.ok) {
        throw new Error(typeof body.detail === "string" ? body.detail : T("send_failed"));
      }
      status.className = "form-status ok";
      status.textContent = successText || body.message;
      form.reset();
    } catch (error) {
      status.className = "form-status error";
      status.textContent = error.message || T("error_generic");
    } finally { button.disabled = false; }
  }

  // ── Asosiy CTA: ikki maydonli ariza ───────────────────────────────────
  const leadForm = document.getElementById("leadForm");
  const leadMessage = document.getElementById("leadMessage");

  if (leadForm) {
    leadForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const status = document.getElementById("formStatus");
      const button = leadForm.querySelector("button[type=submit]");
      submitLead(leadForm, status, button, leadMessage ? leadMessage.value : null, T("lead_ok"));
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

  // "Demo olish" — formaga olib boradi va operator uchun izoh yozadi.
  // Izoh o'zbekcha va til belgisi bilan ("(ru)"): operator mijozga qaysi
  // tilda qo'ng'iroq qilishni shundan biladi.
  const demoCta = document.getElementById("demoCta");
  if (demoCta) {
    demoCta.addEventListener("click", (event) => {
      event.preventDefault();
      goToForm(T("demo_message"));
    });
  }

  // ── Telefon menyusi ────────────────────────────────────────────────────
  //
  // `<details>` JS'siz ochiladi; JS faqat YOPADI: langar sahifa ichida
  // (`#narx`) — sahifa yangilanmaydi va menyu ochiq qolib kontentni
  // to'sib turardi.  Escape ham yopadi.
  const menus = Array.from(document.querySelectorAll("details.nav-menu"));
  for (const menu of menus) {
    menu.addEventListener("click", (event) => {
      if (event.target.closest("a")) menu.removeAttribute("open");
    });
  }
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") for (const menu of menus) menu.removeAttribute("open");
  });

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
        T("notify_message"),
        T("notify_ok"),
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
          label.textContent = T("version", { version: release.version }) + size;
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

  // ── Tariflar: uchta karta ─────────────────────────────────────────────
  //
  // Qaror (2026-08-21): bitta tarif o'rniga uchta — Boshlang'ich, Biznes,
  // Tarmoq.  Uchta TENG ustun qaror qabul qilishni qiyinlashtiradi, shuning
  // uchun o'rtadagisi ajratilgan ("Eng ommabop") — ajratish serverdan.
  //
  // So'm summasi bu yerda HISOBLANMAYDI — serverdan tayyor keladi.  Ilgari
  // formula shu faylda qaytadan yozilgan edi va u hisob-faktura formulasidan
  // uzoqlashib ketishi mumkin edi: sayt bir narxni, hisob boshqasini
  // ko'rsatardi.
  let pricing = null;

  const groups = (value) => String(value).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  const money = (uzs) => `${groups(uzs)} ${T("currency")}`;
  // Serverdan kelgan nom, izoh va tariflar HTML sifatida talqin qilinmasin.
  function esc(value) {
    return String(value).replace(/[&<>"']/g, (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char],
    );
  }

  function planCard(plan) {
    const featured = plan.highlight ? " preset-featured" : "";
    const badge = plan.badge
      ? `<span class="preset-badge">${esc(plan.badge)}</span>`
      : "";
    const price = plan.price_kind === "on_request"
      ? `<p class="preset-price"><b>${esc(plan.price_label || T("on_request"))}</b></p>`
      : `<p class="preset-price"><b>${esc(money(plan.monthly_uzs))}</b><span>${esc(T("per_month"))}</span></p>`;
    const note = plan.note
      ? `<p class="preset-note">${esc(plan.note)}</p>`
      : "";
    // Punkt = ikonka + 2-3 so'z; batafsili BOSILGANDA o'sha joyda
    // ochiladi.  `<details>` ataylab: klaviatura, ekran o'quvchi va
    // telefon xatti-harakati brauzerdan tekin keladi.
    const bullets = (plan.bullets || [])
      .map(
        (line) => `
        <li>
          <details class="bullet" name="bullet-${esc(plan.code)}">
            <summary>
              <svg class="icon" aria-hidden="true"><use href="/assets/icons.svg#${esc(line.icon)}"></use></svg>
              <span>${esc(line.label)}</span>
            </summary>
            ${line.detail ? `<p>${esc(line.detail)}</p>` : ""}
            ${line.example ? `<p class="bullet-example">${esc(line.example)}</p>` : ""}
          </details>
        </li>`,
      )
      .join("");

    // Zaxira: keshdagi eski javobda `bullets` bo'lmasligi mumkin —
    // bunday holatda karta bo'sh qolmasin.
    const items = bullets || (plan.includes || [])
      .map((item) => `<li><span>${esc(item)}</span></li>`)
      .join("");
    return `
      <article class="preset${featured}" data-plan="${esc(plan.code)}">
        ${badge}
        <h3>${esc(plan.name)}</h3>
        ${price}
        <ul class="preset-items">${items}</ul>
        ${note}
        <button class="button ${plan.highlight ? "button-light" : "button-ghost"}" type="button"
                data-plan-cta="${esc(plan.code)}">${esc(plan.cta || T("choose"))}</button>
      </article>`;
  }

  function renderPlans() {
    const grid = document.getElementById("planGrid");
    if (!grid) return;
    const plans = pricing.plans || [];
    grid.innerHTML = plans.map(planCard).join("");

    // Uchala tugma ham bitta qisqa formaga olib boradi.  Tanlangan tarif
    // faqat operator uchun xabardagi izohga yoziladi.
    grid.querySelectorAll("[data-plan-cta]").forEach((button) => {
      button.addEventListener("click", () => {
        const code = button.getAttribute("data-plan-cta");
        const plan = plans.find((item) => item.code === code);
        if (!plan) return;
        if (plan.price_kind === "on_request") {
          // Tarmoqda qat'iy narx yo'q, lekin "so'rov bo'yicha" degan
          // javob bilan ketish ham yaxshi emas edi: mijoz kattaligi
          // haqida hech qanday tasavvursiz qolardi.  Avval kalkulyator,
          // ariza esa undan keyin — allaqachon raqam bilan.
          openCalculator();
          return;
        }
        goToForm(T("plan_message", { name: plan.name, price: money(plan.monthly_uzs) }));
      });
    });

    // Hero'dagi narx ilgagi — eng arzon tarifdan (element bo'lsa).
    const cheapest = plans.find((item) => item.price_kind === "fixed");
    const heroPrice = document.getElementById("heroPrice");
    if (heroPrice && cheapest) {
      heroPrice.textContent = T("from_per_month", { price: money(cheapest.monthly_uzs) });
      heroPrice.hidden = false;
    }
  }

  // ── Tarmoq kalkulyatori ───────────────────────────────────────────────
  //
  // Summani SERVER hisoblaydi (`/api/v1/public/quote`).  Bu yerda
  // qo'shish qilinmaydi: narx qoidasi katalogda va u o'zgarganda sayt
  // eski formulada qolib ketardi — `renderPlans` dagi "sayt so'm
  // summasini o'zi hisoblamaydi" qoidasi shu sababdan.

  const calc = document.getElementById("networkCalc");
  let calcTimer = 0;
  let lastQuote = null;

  function calcSelections() {
    return Array.from(calc.querySelectorAll(".calc-feature")).flatMap((row) => {
      const box = row.querySelector("input[type=checkbox]");
      if (!box.checked) return [];
      return [{ feature_code: box.value, camera_count: Number(row.querySelector("select").value) }];
    });
  }

  function renderQuote(quote) {
    lastQuote = quote;
    const total = document.getElementById("calcTotal");
    total.innerHTML =
      T("calc_total", {
        monthly: esc(money(quote.monthly_uzs)),
        per_shop: esc(money(quote.per_shop_monthly_uzs)),
      }) +
      `<small>${esc(
        T("calc_yearly", {
          yearly: money(quote.yearly_uzs),
          months: quote.yearly_months_charged,
        }),
      )}</small>`;
  }

  function requestQuote() {
    const total = document.getElementById("calcTotal");
    const selections = calcSelections();
    if (!selections.length) {
      lastQuote = null;
      total.textContent = T("calc_empty");
      return;
    }
    const shops = Math.max(1, Math.min(100, Number(document.getElementById("calcShops").value) || 1));
    fetch("/api/v1/public/quote", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ shops, selections }),
    })
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error())))
      .then(renderQuote)
      .catch(() => {
        lastQuote = null;
        total.textContent = T("calc_failed");
      });
  }

  // Har bosishda so'rov yubormaymiz: mijoz kamera sonini ketma-ket
  // bosib chiqadi va bu chegaraga (`public-quote`) tez urardi.
  function scheduleQuote() {
    clearTimeout(calcTimer);
    calcTimer = setTimeout(requestQuote, 350);
  }

  function buildCalculator() {
    const box = document.getElementById("calcFeatures");
    if (!box) return;
    const maxCameras = pricing.max_cameras || 4;
    box.innerHTML = (pricing.features || [])
      .map((feature, index) => {
        const options = Array.from({ length: maxCameras }, (_, i) => i + 1)
          .map((n) => `<option value="${n}">${n} ${esc(T("calc_cameras"))}</option>`)
          .join("");
        // Birinchi ikkitasi belgilangan holda ochiladi: bo'sh
        // kalkulyator "nima tanlashim kerak?" degan savol bilan
        // boshlanardi va ko'pchilik shu yerda to'xtardi.
        const checked = index < 2 ? " checked" : "";
        return `<label class="calc-feature">
          <input type="checkbox" value="${esc(feature.code)}"${checked}>
          <span>${esc(feature.name)}</span>
          <select${checked ? "" : " disabled"}>${options}</select>
        </label>`;
      })
      .join("");

    box.addEventListener("change", (event) => {
      const row = event.target.closest(".calc-feature");
      if (!row) return;
      if (event.target.type === "checkbox") {
        row.querySelector("select").disabled = !event.target.checked;
      }
      scheduleQuote();
    });
    document.getElementById("calcShops").addEventListener("input", scheduleQuote);

    document.getElementById("calcCta").addEventListener("click", () => {
      const names = calcSelections()
        .map((item) => {
          const feature = pricing.features.find((f) => f.code === item.feature_code);
          return `${feature ? feature.name : item.feature_code} (${item.camera_count})`;
        })
        .join(", ");
      // Hisob olinmagan bo'lsa ham ariza ketaveradi — operator uni
      // qo'lda hisoblaydi.  Arizasiz qoldirish eng yomon variant.
      goToForm(
        T("calc_lead", {
          shops: document.getElementById("calcShops").value,
          features: names || "—",
          monthly: lastQuote ? money(lastQuote.monthly_uzs) : "—",
        }),
      );
    });
  }

  function openCalculator() {
    if (!calc) return;
    if (calc.hidden) {
      calc.hidden = false;
      buildCalculator();
      requestQuote();
    }
    calc.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  // Tarif matni serverda chiziladi va so'rov tilini `?lang=` dan oladi
  // (`cloud/i18n.py: resolve_lang`).  Katalogga ko'chirilguncha (F5)
  // server o'zbekcha qaytaradi — bu kutilgan oraliq holat.
  fetch(`/api/v1/public/pricing?lang=${encodeURIComponent(LANG)}`)
    .then((response) => response.json())
    .then((data) => {
      pricing = data;

      // Funksiyalar hali qabul sinovidan o'tmagan bo'lsa buni
      // yashirmaymiz — bitta halol izoh.
      const note = document.getElementById("featureNote");
      if (note && pricing.features.length && pricing.features.every((item) => !item.available)) {
        note.textContent = T("feature_note");
        note.hidden = false;
      }

      renderPlans();
    })
    .catch(() => {
      const grid = document.getElementById("planGrid");
      if (grid) {
        grid.innerHTML =
          `<p class="preset-hint">${esc(T("pricing_failed"))} ` +
          '<a href="https://t.me/fibotai" target="_blank" rel="noopener noreferrer">@fibotai</a>' +
          `${esc(T("write_to"))}</p>`;
      }
    });
})();
