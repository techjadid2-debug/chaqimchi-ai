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
      full_name: String(data.get("full_name") || "").trim(),
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

  // ── Yagona lead forma ─────────────────────────────────────────────────
  const leadForm = document.getElementById("leadForm");
  const leadMessage = document.getElementById("leadMessage");
  if (leadForm) {
    leadForm.addEventListener("submit", (event) => {
      event.preventDefault();
      submitLead(
        leadForm,
        document.getElementById("formStatus"),
        leadForm.querySelector("button[type=submit]"),
        leadMessage ? leadMessage.value : null,
        "So‘rovingiz qabul qilindi. Tez orada bog‘lanamiz.",
      );
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

  // ── Tayyor paketlar ───────────────────────────────────────────────────
  //
  // Faqat tarkib e'lon qilinadi; narx `/api/v1/public/pricing` dan
  // hisoblanadi.  Katalogda narx o'zgarsa kartalar o'zini yangilaydi.
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

  let pricing = null;
  let billing = "monthly";

  const groups = (value) => String(value).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  // Serverdagi `(cents * rate + 99) // 100` bilan bir xil: sayt va
  // hisob-faktura bitta so'mni ham farq qilmasligi kerak.
  const toUzs = (cents) => Math.floor((cents * pricing.usd_rate_uzs + 99) / 100);
  const money = (cents) => `${groups(toUzs(cents))} so‘m`;

  const escape = (value) => String(value).replace(/[&<>"]/g, (char) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[char]
  ));

  function presetCents(preset) {
    return preset.items.reduce((total, item) => {
      const feature = pricing.features.find((entry) => entry.code === item.code);
      return total + (feature ? feature.monthly_usd_cents * item.cameras : 0);
    }, pricing.base.monthly_usd_cents);
  }

  function presetSummary(preset) {
    const names = preset.items
      .map((item) => pricing.features.find((entry) => entry.code === item.code))
      .filter(Boolean)
      .map((feature) => feature.name);
    const months = billing === "yearly" ? pricing.yearly_months_charged : 1;
    return [
      `Paket: ${preset.name}`,
      `To‘lov: ${billing === "yearly" ? "yillik" : "oylik"}`,
      `Funksiyalar: ${names.join(", ")}`,
      `Hisob: ${money(presetCents(preset) * months)}${billing === "yearly" ? "/yil" : "/oy"}`,
    ].join(" | ");
  }

  function renderPresets() {
    const grid = document.getElementById("presetGrid");
    if (!grid || !pricing) return;
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
      button.addEventListener("click", () => {
        const preset = PRESETS.find((item) => item.id === button.dataset.preset);
        if (preset) goToForm(presetSummary(preset));
      });
    });
  }

  document.querySelectorAll("[data-billing]").forEach((button) => {
    button.addEventListener("click", () => {
      billing = button.dataset.billing;
      button.parentElement.querySelectorAll("button").forEach((item) => {
        const on = item === button;
        item.classList.toggle("active", on);
        item.setAttribute("aria-checked", String(on));
      });
      renderPresets();
    });
  });

  fetch("/api/v1/public/pricing")
    .then((response) => response.json())
    .then((data) => {
      pricing = data;

      const headline = document.getElementById("baseHeadline");
      if (headline) headline.textContent = `${money(pricing.base.monthly_usd_cents)}/oy`;

      // Hero'dagi narx ilgagi: mijoz "qancha turadi?" degan savol bilan
      // keladi va javob uchun pastga tushishga majbur bo'lmasligi kerak.
      const heroPrice = document.getElementById("heroPrice");
      if (heroPrice) {
        heroPrice.textContent = `${money(pricing.base.monthly_usd_cents)}/oydan`;
        heroPrice.hidden = false;
      }

      // Funksiyalar hali sotuvga ochilmagan bo'lsa (qabul sinovi
      // tugamagan), buni yashirmaymiz — bitta aniq izoh chiqadi.
      const note = document.getElementById("featureNote");
      if (note && pricing.features.length && pricing.features.every((item) => !item.available)) {
        note.textContent =
          "AI funksiyalari hozir birinchi do‘konlarda sinovdan o‘tmoqda. " +
          "Hozir so‘rov qoldirsangiz — ishga tushganda birinchi bo‘lib sizga ulanadi.";
        note.hidden = false;
      }

      renderPresets();
    })
    .catch(() => {
      const grid = document.getElementById("presetGrid");
      if (grid) {
        grid.innerHTML =
          '<p class="preset-hint">Narxlarni yuklab bo‘lmadi. Sahifani yangilang yoki ' +
          '<a href="https://t.me/fibotai" target="_blank" rel="noopener noreferrer">@fibotai</a> ga yozing.</p>';
      }
    });
})();
