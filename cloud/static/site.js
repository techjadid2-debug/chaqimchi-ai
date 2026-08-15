(() => {
  async function submitLead(form, status, button, message, cameras = 1) {
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
      status.textContent = message ? "Tanlovingiz qabul qilindi. To‘lov havolasi va dasturiy paket bo‘yicha jamoamiz bog‘lanadi." : body.message;
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

  window.startQuickTrial = async function() {
    const phoneInput = document.getElementById("trialPhone");
    const companyInput = document.getElementById("trialCompany");
    const btn = document.getElementById("trialBtn");
    const status = document.getElementById("trialStatus");

    const phone = phoneInput ? phoneInput.value.trim() : "";
    const company = companyInput ? companyInput.value.trim() : "";
    if (!phone) {
      if (status) {
        status.className = "form-status error";
        status.textContent = "Iltimos, telefon raqamingizni kiriting.";
      }
      return;
    }

    if (btn) btn.disabled = true;
    if (status) {
      status.className = "form-status";
      status.textContent = "14 kunlik bepul sinov tayyorlanmoqda…";
    }

    try {
      const res = await fetch("/api/v1/public/quick-trial", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone, company }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Xatolik yuz berdi");

      if (status) {
        status.className = "form-status ok";
        status.innerHTML = `✅ <b>Tayyor!</b> O‘rnatuvchi yuklab olinmoqda…<br><small>Yuklangan faylni 1 marta bosing, u avtomatik ulanadi.</small>`;
      }

      const downloadLink = document.createElement("a");
      downloadLink.href = data.download_windows_url;
      downloadLink.download = "Chaqimchi_AI_Ornatish.bat";
      document.body.appendChild(downloadLink);
      downloadLink.click();
      setTimeout(() => {
        try { document.body.removeChild(downloadLink); } catch(_) {}
      }, 500);
    } catch (err) {
      if (status) {
        status.className = "form-status error";
        status.textContent = err.message || "Xatolik yuz berdi";
      }
    } finally {
      if (btn) btn.disabled = false;
    }
  };

  const quickTrialForm = document.getElementById("quickTrialForm");
  if (quickTrialForm) {
    quickTrialForm.addEventListener("submit", (event) => {
      event.preventDefault();
      window.startQuickTrial();
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
    submitLead(purchaseForm, output.status, output.buy, output.message.value, cameras);
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
