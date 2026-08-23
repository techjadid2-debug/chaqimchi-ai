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

  // ── Asosiy CTA: ikki maydonli ariza ───────────────────────────────────
  const leadForm = document.getElementById("leadForm");
  const leadMessage = document.getElementById("leadMessage");

  if (leadForm) {
    leadForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const status = document.getElementById("formStatus");
      const button = leadForm.querySelector("button[type=submit]");
      submitLead(leadForm, status, button, leadMessage ? leadMessage.value : null,
        "So‘rovingiz qabul qilindi. Tez orada bog‘lanamiz.");
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
      goToForm("Chaqimchi AI biznes paneli bo'yicha demo so'rayman");
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

  // ── Tariflar: uchta karta ─────────────────────────────────────────────
  //
  // Qaror (2026-08-21): bitta tarif o'rniga uchta — Boshlang'ich, Biznes,
  // Tarmoq.  Bitta tarif ikki tomondan zarar keltirardi: kichik do'kon
  // uchun kirish nuqtasi yo'q edi, katta mijozdan ko'proq pul olishning
  // yo'li ham yo'q edi.
  //
  // Uchta TENG ustun qaror qabul qilishni qiyinlashtiradi, shuning uchun
  // o'rtadagisi ajratilgan ("Eng ommabop") va ko'z birinchi o'shanga
  // tushadi.
  //
  // So'm summasi bu yerda HISOBLANMAYDI — serverdan tayyor keladi.  Ilgari
  // formula (`cents * rate + 99) / 100`) shu faylda qaytadan yozilgan edi
  // va u hisob-faktura formulasidan uzoqlashib ketishi mumkin edi: sayt
  // bir narxni, hisob boshqasini ko'rsatardi.
  let pricing = null;

  const groups = (value) => String(value).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  const money = (uzs) => `${groups(uzs)} so‘m`;
  // Serverdan kelgan nom, izoh va tariflar HTML sifatida talqin qilinmasin.
  // Bu funksiya CTA oqimidan ajratilgan: narx kartalari ham unga tayanadi.
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
      ? `<p class="preset-price"><b>${esc(plan.price_label || "So‘rov bo‘yicha")}</b></p>`
      : `<p class="preset-price"><b>${esc(money(plan.monthly_uzs))}</b><span>/oy</span></p>`;
    const note = plan.note
      ? `<p class="preset-note">${esc(plan.note)}</p>`
      : "";
    // Punkt = ikonka + 2-3 so'z; batafsili BOSILGANDA o'sha joyda
    // ochiladi.  Ilgari har kartada oltita uzun jumla turardi va do'kon
    // egasi ularni o'qimay, faqat narxga qarab qaror qilardi.
    //
    // `<details>` ataylab: klaviatura (Enter/Bo'sh joy), ekran o'quvchi
    // va telefon xatti-harakati brauzerdan tekin keladi — `aria-expanded`
    // ni qo'lda boshqarish shart emas.  `name` bir kartada bittasi ochiq
    // turishini ta'minlaydi (qo'llab-quvvatlamagan brauzerda bir nechtasi
    // ochiladi — bu ham yomon emas).
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
    // `?v=` faqat KEYINGI yuklashga ta'sir qiladi, hozirgi mijozda esa
    // eski JS ishlab turadi.  Bunday holatda karta bo'sh qolmasin.
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
                data-plan-cta="${esc(plan.code)}">${esc(plan.cta || "Tanlash")}</button>
      </article>`;
  }

  function renderPlans() {
    const grid = document.getElementById("planGrid");
    if (!grid) return;
    const plans = pricing.plans || [];
    grid.innerHTML = plans.map(planCard).join("");

    // Uchala tugma ham bitta qisqa formaga olib boradi. Tanlangan tarif
    // faqat operator uchun xabardagi izohga yoziladi.
    grid.querySelectorAll("[data-plan-cta]").forEach((button) => {
      button.addEventListener("click", () => {
        const code = button.getAttribute("data-plan-cta");
        const plan = plans.find((item) => item.code === code);
        if (!plan) return;
        if (plan.price_kind === "on_request") {
          // Tarmoqda narx yo'q — bu ariza, ro'yxatdan o'tish emas.
          goToForm(`Tarif: ${plan.name} — bir nechta do‘kon, bog‘lanishingizni so‘rayman`);
          return;
        }
        goToForm(`Tarif: ${plan.name} | Oyiga ${money(plan.monthly_uzs)}`);
      });
    });

    // Hero'dagi narx ilgagi — eng arzon tarifdan.
    const cheapest = plans.find((item) => item.price_kind === "fixed");
    const heroPrice = document.getElementById("heroPrice");
    if (heroPrice && cheapest) {
      heroPrice.textContent = `${money(cheapest.monthly_uzs)}/oydan`;
      heroPrice.hidden = false;
    }
  }

  fetch("/api/v1/public/pricing")
    .then((response) => response.json())
    .then((data) => {
      pricing = data;

      // Funksiyalar hali qabul sinovidan o'tmagan bo'lsa buni
      // yashirmaymiz — bitta halol izoh.
      const note = document.getElementById("featureNote");
      if (note && pricing.features.length && pricing.features.every((item) => !item.available)) {
        note.textContent =
          "AI funksiyalari hozir birinchi do‘konlarda sinovdan o‘tmoqda. " +
          "Hozir so‘rov qoldirsangiz — ishga tushganda birinchi bo‘lib sizga ulanadi.";
        note.hidden = false;
      }

      renderPlans();
    })
    .catch(() => {
      const grid = document.getElementById("planGrid");
      if (grid) {
        grid.innerHTML =
          '<p class="preset-hint">Narxni yuklab bo\u2018lmadi. Sahifani yangilang yoki ' +
          '<a href="https://t.me/fibotai" target="_blank" rel="noopener noreferrer">@fibotai</a> ga yozing.</p>';
      }
    });
})();
