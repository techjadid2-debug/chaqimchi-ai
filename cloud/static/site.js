(() => {
  // `message` — adminga ketadigan texnik izoh; `successText` — mijozga
  // ko'rinadigan javob.  Ilgari ikkalasi bitta bo'lgani uchun har qanday
  // `message` berilgan forma "To'lov havolasi bo'yicha bog'lanamiz" degan
  // javobni ko'rsatardi — bu tarif konfiguratori uchun to'g'ri, "xabar
  // bering" formasi uchun esa chalg'ituvchi.
  async function submitLead(form, status, button, message, successText, cameras = 1) {
    if (!form.reportValidity()) return;
    button.disabled = true;
    status.className = "form-status";
    status.textContent = "So‘rov yuborilmoqda…";
    const data = new FormData(form);
    const payload = {
      full_name: String(data.get("full_name") || "").trim(),
      phone: String(data.get("phone") || "").trim(),
      company: String(data.get("company") || "").trim() || null,
      city: String(data.get("city") || "").trim() || null,
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

  const leadForm = document.getElementById("leadForm");
  if (leadForm) {
    leadForm.addEventListener("submit", (event) => {
      event.preventDefault();
      submitLead(leadForm, document.getElementById("formStatus"), leadForm.querySelector("button[type=submit]"));
    });
  }

  // Yuklab olish bo'limi serverdan so'raladi: dastur nashr qilinganmi va
  // hajmi qancha.  Sahifaga qo'lda "115 MB" deb yozib qo'yish aynan shu
  // yerda xatoga olib kelgan edi — matn turardi, fayl esa yo'q edi va
  // tugma 503 qaytarardi.
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
        const size = release.size_mb ? ` (${release.size_mb} MB)` : "";
        const button = document.getElementById("downloadBtn");
        if (button) button.textContent = `⬇️ Windows uchun yuklab olish${size}`;
        // Versiyani ko'rsatamiz.  Ilgari faqat hajm chiqardi, u esa har
        // relizda bir xil (68 MB) — natijada yangi fayl chiqqanini
        // sahifadan bilib bo'lmasdi va eski fayl qayta yuklab olinardi.
        const label = document.getElementById("downloadVersion");
        if (label && release.version) {
          label.textContent = `Versiya ${release.version}`;
          label.hidden = false;
        }
        downloadReady.hidden = false;
        notifyForm.hidden = true;
      })
      .catch(() => {
        // Nashr qilinmagan yoki server javob bermadi — mijozga buzuq
        // tugma emas, "xabar bering" formasi ko'rsatiladi.
        downloadReady.hidden = true;
        notifyForm.hidden = false;
        const heading = document.getElementById("downloadHeading");
        const lead = document.getElementById("downloadLead");
        if (heading) heading.textContent = "Windows dasturi tayyorlanmoqda";
        if (lead) {
          lead.textContent =
            "Mustaqil o‘rnatiladigan Windows dasturi hozir yakuniy sinovdan o‘tmoqda. " +
            "Kutishni istamasangiz, mutaxassisimiz bugunoq kelib o‘rnatib beradi.";
        }
      });
  }

  const purchaseForm = document.getElementById("purchaseForm");

  if (!purchaseForm) return;

  const output = {
    headline: document.getElementById("baseHeadline"), includes: document.getElementById("baseIncludes"),
    list: document.getElementById("featureList"), features: document.getElementById("summaryFeatures"),
    base: document.getElementById("basePrice"), addOns: document.getElementById("featuresPrice"),
    total: document.getElementById("totalPrice"), label: document.getElementById("totalLabel"),
    saving: document.getElementById("savingNote"), message: document.getElementById("purchaseMessage"),
    status: document.getElementById("purchaseStatus"), buy: purchaseForm.querySelector("button[type=submit]"),
  };

  let billing = "monthly";
  let currency = "uzs";
  let pricing = null;

  const groups = (value) => String(value).replace(/\B(?=(\d{3})+(?!\d))/g, " ");

  // Serverdagi `(cents * rate + 99) // 100` bilan bir xil: sayt va hisob-faktura
  // bitta so‘mni ham farq qilmasligi kerak.
  const toUzs = (cents) => Math.floor((cents * pricing.usd_rate_uzs + 99) / 100);

  function money(cents) {
    if (currency === "usd") {
      const dollars = cents / 100;
      return `$${Number.isInteger(dollars) ? dollars : dollars.toFixed(2)}`;
    }
    return `${groups(toUzs(cents))} so‘m`;
  }

  const escape = (value) => String(value).replace(/[&<>"]/g, (char) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[char]
  ));

  // ── Tayyor paketlar ───────────────────────────────────────────────────
  //
  // Faqat tarkib e'lon qilinadi; narx `pricing` dan hisoblanadi.  Shu sabab
  // katalogda narx o'zgarsa yoki yangi funksiya qo'shilsa paket kartalari
  // o'zini yangilaydi — bu yerda hech narsa tuzatilmaydi.
  const PRESETS = [
    {
      id: "start",
      name: "Boshlang‘ich",
      note: "Kichik do‘kon uchun: nechta mijoz kirdi va qachon gavjum.",
      items: [{ code: "person_count", cameras: 2 }],
    },
    {
      id: "shop",
      name: "Do‘kon",
      badge: "Ommabop",
      note: "Mijozlar oqimi va kassadagi navbat birga — eng ko‘p tanlanadi.",
      items: [
        { code: "person_count", cameras: 4 },
        { code: "queue_length", cameras: 4 },
      ],
    },
    {
      id: "full",
      name: "To‘liq",
      note: "Yuqoridagilar ustiga tungi harakat, taqiqlangan zona va kamera nazorati.",
      items: [
        { code: "person_count", cameras: 4 },
        { code: "queue_length", cameras: 4 },
        { code: "store_security", cameras: 4 },
      ],
    },
  ];

  function presetCents(preset) {
    return preset.items.reduce((total, item) => {
      const feature = pricing.features.find((entry) => entry.code === item.code);
      return total + (feature ? feature.monthly_usd_cents * item.cameras : 0);
    }, pricing.base.monthly_usd_cents);
  }

  function renderPresets() {
    const grid = document.getElementById("presetGrid");
    if (!grid) return;
    const months = billing === "yearly" ? pricing.yearly_months_charged : 1;
    const suffix = billing === "yearly" ? "/yil" : "/oy";

    grid.innerHTML = PRESETS.map((preset) => {
      const names = preset.items
        .map((item) => pricing.features.find((entry) => entry.code === item.code))
        .filter(Boolean)
        .map((feature) => escape(feature.name));
      const cameras = Math.max(...preset.items.map((item) => item.cameras));
      return `
        <article class="preset${preset.badge ? " preset-featured" : ""}" role="listitem">
          ${preset.badge ? `<span class="preset-badge">${escape(preset.badge)}</span>` : ""}
          <h3>${escape(preset.name)}</h3>
          <p class="preset-note">${escape(preset.note)}</p>
          <ul class="preset-items">${names.map((name) => `<li>${name}</li>`).join("")}</ul>
          <p class="preset-cameras">${cameras} kameragacha</p>
          <p class="preset-price"><b>${money(presetCents(preset) * months)}</b><span>${suffix}</span></p>
          <button class="button${preset.badge ? " button-light" : ""}" type="button" data-preset="${preset.id}">Shu paketni tanlash</button>
        </article>`;
    }).join("");

    grid.querySelectorAll("[data-preset]").forEach((button) => {
      button.addEventListener("click", () => applyPreset(button.dataset.preset));
    });
  }

  function applyPreset(id) {
    const preset = PRESETS.find((item) => item.id === id);
    if (!preset) return;
    output.list.querySelectorAll(".feature-choice").forEach((row) => {
      const wanted = preset.items.find((item) => item.code === row.dataset.code);
      const box = row.querySelector("input[type=checkbox]");
      box.checked = Boolean(wanted);
      if (wanted) setCameras(row, wanted.cameras);
      syncRow(row);
    });
    updateQuote();
    document.getElementById("purchaseForm").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // ── Kamera soni: +/− ──────────────────────────────────────────────────
  //
  // Ilgari bu `<select>` edi va funksiya belgilanmaguncha `opacity: .45`
  // bilan o'chib turardi — mijoz uni umuman payqamasdi.  Endi u belgilanmagan
  // qatorda umuman ko'rinmaydi, belgilanganda esa katta +/− tugmalari
  // chiqadi (telefonda barmoq bilan bosish uchun).
  function cameraCount(row) {
    return Number(row.dataset.cameras || 1);
  }

  function setCameras(row, value) {
    const max = pricing.max_cameras;
    const next = Math.min(max, Math.max(1, value));
    row.dataset.cameras = String(next);
    const readout = row.querySelector("[data-readout]");
    if (readout) readout.textContent = String(next);
    row.querySelector("[data-step='-1']").disabled = next <= 1;
    row.querySelector("[data-step='1']").disabled = next >= max;
  }

  /** Qator ko'rinishini belgilash holatiga moslaydi. */
  function syncRow(row) {
    const checked = row.querySelector("input[type=checkbox]").checked;
    row.classList.toggle("is-on", checked);
    row.querySelector(".feature-stepper").hidden = !checked;
  }

  function renderCatalog() {
    output.headline.textContent = `${money(pricing.base.monthly_usd_cents)}/oy`;
    output.includes.innerHTML = pricing.base.includes.map((item) => `<li>${escape(item)}</li>`).join("");

    output.list.innerHTML = pricing.features.map((feature) => `
      <div class="feature-choice" data-code="${escape(feature.code)}" data-cameras="1">
        <label class="feature-head">
          <input type="checkbox">
          <span class="feature-name">${escape(feature.name)}${feature.available ? "" : ' <i class="soon">Tez orada</i>'}</span>
        </label>
        <div class="feature-stepper" hidden>
          <button type="button" class="step" data-step="-1" aria-label="${escape(feature.name)}: kamerani kamaytirish">−</button>
          <output data-readout aria-live="polite">1</output>
          <span class="step-unit">kamera</span>
          <button type="button" class="step" data-step="1" aria-label="${escape(feature.name)}: kamera qo‘shish">+</button>
        </div>
        <b class="feature-sum" data-price="${feature.monthly_usd_cents}"></b>
      </div>`).join("");

    output.list.querySelectorAll(".feature-choice").forEach((row) => {
      const box = row.querySelector("input[type=checkbox]");
      box.addEventListener("change", () => { syncRow(row); updateQuote(); });

      row.querySelectorAll("[data-step]").forEach((button) => {
        button.addEventListener("click", () => {
          setCameras(row, cameraCount(row) + Number(button.dataset.step));
          updateQuote();
        });
      });

      // Klaviatura: stepper ustida o'q tugmalari ham ishlaydi — sichqonchasiz
      // foydalanuvchi har safar tugmaga o'tishga majbur bo'lmasin.
      row.querySelector(".feature-stepper").addEventListener("keydown", (event) => {
        const delta = { ArrowRight: 1, "+": 1, ArrowUp: 1, ArrowLeft: -1, "-": -1, ArrowDown: -1 }[event.key];
        if (!delta) return;
        event.preventDefault();
        setCameras(row, cameraCount(row) + delta);
        updateQuote();
      });

      setCameras(row, 1);
      syncRow(row);
    });

    renderPresets();
  }

  function selection() {
    return [...output.list.querySelectorAll(".feature-choice")]
      .filter((row) => row.querySelector("input[type=checkbox]").checked)
      .map((row) => {
        const code = row.dataset.code;
        const feature = pricing.features.find((item) => item.code === code);
        const cameras = cameraCount(row);
        return { code, name: feature.name, available: feature.available, cameras, cents: feature.monthly_usd_cents * cameras };
      });
  }

  function updateQuote() {
    if (!pricing) return;
    const selected = selection();
    const addOnCents = selected.reduce((total, item) => total + item.cents, 0);
    const monthlyCents = pricing.base.monthly_usd_cents + addOnCents;
    const isYearly = billing === "yearly";
    const months = isYearly ? pricing.yearly_months_charged : 1;
    const suffix = isYearly ? " / yil" : " / oy";

    // Har funksiya yonida uning **o'z** summasi: "$5/kamera" ni 4 ga
    // ko'paytirishni mijozga qoldirmaslik kerak.
    output.list.querySelectorAll(".feature-choice").forEach((row) => {
      const cell = row.querySelector(".feature-sum");
      const unit = Number(cell.dataset.price);
      cell.innerHTML = row.querySelector("input[type=checkbox]").checked
        ? `<b>${money(unit * cameraCount(row) * months)}</b><small>${suffix}</small>`
        : `<small>${money(unit)} / kamera</small>`;
    });

    output.features.innerHTML = selected.length
      ? selected.map((item) => `<li>${escape(item.name)} · ${item.cameras} kamera · ${money(item.cents * months)}</li>`).join("")
      : "<li>Qo‘shimcha funksiya tanlanmagan</li>";
    output.base.textContent = money(pricing.base.monthly_usd_cents * months) + suffix;
    output.addOns.textContent = money(addOnCents * months) + suffix;
    output.total.textContent = money(monthlyCents * months);
    output.label.textContent = isYearly ? "Jami yiliga" : "Jami oyiga";

    const stickyTotal = document.getElementById("stickyTotal");
    const stickyLabel = document.getElementById("stickyLabel");
    if (stickyTotal) stickyTotal.textContent = money(monthlyCents * months);
    if (stickyLabel) stickyLabel.textContent = isYearly ? "Jami yiliga" : "Jami oyiga";

    // Tugma matni **haqiqatga** mos bo'lishi kerak: forma to'lov sahifasiga
    // olib bormaydi, u ariza yuboradi va biz qo'ng'iroq qilamiz.
    const pending = selected.filter((item) => !item.available);
    if (pending.length) {
      output.buy.textContent = "Navbatga yozilish";
      output.saving.textContent = `${pending.map((item) => item.name).join(", ")} — ishga tushirilmoqda. Tayyor bo‘lganda birinchi bo‘lib sizga ulanadi.`;
    } else {
      output.buy.textContent = "So‘rov yuborish";
      output.saving.textContent = isYearly
        ? `${money(monthlyCents * (12 - pricing.yearly_months_charged))} tejaysiz — 2 oy bepul.`
        : "Yillik to‘lovda 2 oy bepul.";
    }

    const setupModeInput = purchaseForm.querySelector("input[name=setup_mode]:checked");
    const isTurnkey = setupModeInput && setupModeInput.value === "turnkey";
    const setupModeText = isTurnkey
      ? "Qurilma va Usta bilan o‘rnatish"
      : "Mustaqil (O‘z kompyuteriga) o‘rnatish";
    const turnkeyNote = document.getElementById("turnkeyNote");
    if (turnkeyNote) turnkeyNote.hidden = !isTurnkey;

    output.message.value = [
      `Sotib olish so‘rovi (${setupModeText})`,
      `To‘lov: ${isYearly ? "yillik" : "oylik"}`,
      `Funksiyalar: ${selected.length ? selected.map((item) => `${item.name} (${item.cameras} kamera)`).join(", ") : "yo‘q"}`,
      `Hisob: $${(monthlyCents * months) / 100}${isYearly ? "/yil" : "/oy"} · ${groups(toUzs(monthlyCents * months))} so‘m`,
    ].join(" | ");
  }


  /** Almashtirgichni tanlaydi va ekran o'quvchiga holatni aytadi. */
  function activate(button) {
    button.parentElement.querySelectorAll("button").forEach((item) => {
      const on = item === button;
      item.classList.toggle("active", on);
      item.setAttribute("aria-checked", String(on));
    });
  }

  purchaseForm.querySelectorAll("[data-billing]").forEach((button) => button.addEventListener("click", () => {
    billing = button.dataset.billing;
    activate(button);
    renderPresets();
    updateQuote();
  }));
  purchaseForm.querySelectorAll("[data-currency]").forEach((button) => button.addEventListener("click", () => {
    currency = button.dataset.currency;
    activate(button);
    output.headline.textContent = `${money(pricing.base.monthly_usd_cents)}/oy`;
    renderPresets();
    updateQuote();
  }));

  // Mobil narx paneli faqat konfigurator ekranda turganda ko'rinadi; shu
  // paytda Telegram tugmasi yashiriladi, aks holda ikkisi bir-birining
  // ustiga tushardi.
  const stickyPrice = document.getElementById("stickyPrice");
  const mobileCta = document.querySelector(".mobile-lead-cta");
  const stickyCta = document.getElementById("stickyCta");
  if (stickyCta) {
    stickyCta.addEventListener("click", () => {
      purchaseForm.querySelector("input[name=phone]").focus();
      purchaseForm.scrollIntoView({ behavior: "smooth", block: "end" });
    });
  }
  if (stickyPrice && "IntersectionObserver" in window) {
    const observer = new IntersectionObserver((entries) => {
      const visible = entries.some((entry) => entry.isIntersecting);
      stickyPrice.hidden = !visible;
      if (mobileCta) mobileCta.classList.toggle("is-hidden", visible);
    }, { threshold: 0 });
    observer.observe(purchaseForm);
  }

  purchaseForm.querySelectorAll("input[name=setup_mode]").forEach((radio) => {
    radio.addEventListener("change", updateQuote);
  });

  purchaseForm.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!pricing) return;
    updateQuote();
    const cameras = selection().reduce((most, item) => Math.max(most, item.cameras), 1);
    submitLead(
      purchaseForm,
      output.status,
      output.buy,
      output.message.value,
      "So‘rovingiz qabul qilindi. Jamoamiz bog‘lanib, narxni tasdiqlaydi va o‘rnatishni kelishadi.",
      cameras,
    );
  });

  fetch("/api/v1/public/pricing")
    .then((response) => response.json())
    .then((data) => {
      pricing = data;
      currency = data.currency_default === "usd" ? "usd" : "uzs";
      renderCatalog();

      // Hero'dagi narx ilgagi.  Qiymat sahifaga yozilmaydi: katalogda baza
      // narxi o'zgarsa hero ham o'zi yangilanadi.
      const heroPrice = document.getElementById("heroPrice");
      if (heroPrice) {
        heroPrice.textContent = `${money(pricing.base.monthly_usd_cents)}/oydan`;
        heroPrice.hidden = false;
      }

      // Funksiyalar hali sotuvga ochilmagan bo'lsa (qabul testi tugamagan),
      // uchta "Tez orada" qatori mijozga "bu sayt hech narsa sotmaydi" deb
      // ko'rinadi.  Bitta aniq izoh buni tushuntiradi.
      const note = document.getElementById("featureNote");
      if (note && pricing.features.length && pricing.features.every((item) => !item.available)) {
        note.textContent =
          "AI funksiyalari hozir birinchi do‘konlarda sinovdan o‘tmoqda. " +
          "Hozir navbatga yozilishingiz mumkin — ishga tushganda birinchi bo‘lib sizga ulanadi.";
        note.hidden = false;
      }

      updateQuote();
    })
    .catch(() => {
      output.list.textContent = "Narxlarni yuklab bo‘lmadi. Sahifani yangilang yoki bizga qo‘ng‘iroq qiling.";
      const grid = document.getElementById("presetGrid");
      if (grid) grid.remove();
      const hint = document.getElementById("presetHint");
      if (hint) hint.remove();
    });
})();
