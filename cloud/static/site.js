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

  function cameraOptions(max) {
    let html = "";
    for (let n = 1; n <= max; n += 1) html += `<option value="${n}">${n} kamera</option>`;
    return html;
  }

  const escape = (value) => String(value).replace(/[&<>"]/g, (char) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[char]
  ));

  function renderCatalog() {
    output.headline.textContent = `${money(pricing.base.monthly_usd_cents)}/oy`;
    output.includes.innerHTML = pricing.base.includes.map((item) => `<li>${escape(item)}</li>`).join("");
    output.list.innerHTML = pricing.features.map((feature) => `
      <label class="feature-choice" data-code="${escape(feature.code)}">
        <input type="checkbox">
        <span>${escape(feature.name)}${feature.available ? "" : ' <i class="soon">Tez orada</i>'}</span>
        <select class="feature-cameras" aria-label="${escape(feature.name)} — kamera soni" disabled>${cameraOptions(pricing.max_cameras)}</select>
        <b data-price="${feature.monthly_usd_cents}">${money(feature.monthly_usd_cents)} / kamera</b>
      </label>`).join("");
    output.list.querySelectorAll(".feature-choice").forEach((row) => {
      const box = row.querySelector("input");
      const cameras = row.querySelector("select");
      box.addEventListener("change", () => { cameras.disabled = !box.checked; updateQuote(); });
      cameras.addEventListener("change", updateQuote);
    });
  }

  function selection() {
    return [...output.list.querySelectorAll(".feature-choice")]
      .filter((row) => row.querySelector("input").checked)
      .map((row) => {
        const code = row.dataset.code;
        const feature = pricing.features.find((item) => item.code === code);
        const cameras = Number(row.querySelector("select").value || 1);
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

    output.features.textContent = selected.length
      ? selected.map((item) => `${item.name} · ${item.cameras} kamera · ${money(item.cents * months)}`).join("\n")
      : "Qo‘shimcha funksiya tanlanmagan";
    output.features.style.whiteSpace = "pre-line";
    output.base.textContent = money(pricing.base.monthly_usd_cents * months) + suffix;
    output.addOns.textContent = money(addOnCents * months) + suffix;
    output.total.textContent = money(monthlyCents * months);
    output.label.textContent = isYearly ? "Jami yiliga" : "Jami oyiga";

    const pending = selected.filter((item) => !item.available);
    if (pending.length) {
      output.buy.textContent = "Navbatga yozilish";
      output.saving.textContent = `${pending.map((item) => item.name).join(", ")} — ishga tushirilmoqda. Tayyor bo‘lganda birinchi bo‘lib sizga ulanadi.`;
    } else {
      output.buy.textContent = "Sotib olishni boshlash";
      output.saving.textContent = isYearly
        ? `${money(monthlyCents * (12 - pricing.yearly_months_charged))} tejaysiz — 2 oy bepul.`
        : "Yillik to‘lovda 2 oy bepul.";
    }

    const setupModeInput = purchaseForm.querySelector("input[name=setup_mode]:checked");
    const setupModeText = setupModeInput && setupModeInput.value === "turnkey"
      ? "Qurilma va Usta bilan o‘rnatish"
      : "Mustaqil (O‘z kompyuteriga) o‘rnatish";

    output.message.value = [
      `Sotib olish so‘rovi (${setupModeText})`,
      `To‘lov: ${isYearly ? "yillik" : "oylik"}`,
      `Funksiyalar: ${selected.length ? selected.map((item) => `${item.name} (${item.cameras} kamera)`).join(", ") : "yo‘q"}`,
      `Hisob: $${(monthlyCents * months) / 100}${isYearly ? "/yil" : "/oy"} · ${groups(toUzs(monthlyCents * months))} so‘m`,
    ].join(" | ");
  }


  purchaseForm.querySelectorAll("[data-billing]").forEach((button) => button.addEventListener("click", () => {
    billing = button.dataset.billing;
    button.parentElement.querySelectorAll("button").forEach((item) => item.classList.toggle("active", item === button));
    updateQuote();
  }));
  purchaseForm.querySelectorAll("[data-currency]").forEach((button) => button.addEventListener("click", () => {
    currency = button.dataset.currency;
    button.parentElement.querySelectorAll("button").forEach((item) => item.classList.toggle("active", item === button));
    renderPrices();
    updateQuote();
  }));

  function renderPrices() {
    output.headline.textContent = `${money(pricing.base.monthly_usd_cents)}/oy`;
    output.list.querySelectorAll(".feature-choice b").forEach((cell) => {
      cell.textContent = `${money(Number(cell.dataset.price))} / kamera`;
    });
  }

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
      "Tanlovingiz qabul qilindi. To‘lov havolasi va o‘rnatish bo‘yicha jamoamiz bog‘lanadi.",
      cameras,
    );
  });

  fetch("/api/v1/public/pricing")
    .then((response) => response.json())
    .then((data) => {
      pricing = data;
      currency = data.currency_default === "usd" ? "usd" : "uzs";
      renderCatalog();
      updateQuote();
    })
    .catch(() => {
      output.list.textContent = "Narxlarni yuklab bo‘lmadi. Sahifani yangilang yoki bizga qo‘ng‘iroq qiling.";
    });
})();
