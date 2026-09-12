/* Holat sahifasi: cloud tirikmi va QAYSI qismi yiqilgan?
 *
 * Matn HTML ichidagi `application/json` blokidan o'qiladi — u ijro
 * etilmaydigan «data block», ya'ni CSP `script-src` unga tegmaydi.
 * Sahifa uch tilda quriladi, shuning uchun matn shu yerga qotirib
 * yozilmaydi. */
(function () {
  const TEXT = JSON.parse(document.getElementById("page-text").textContent);
  const light = document.getElementById("light");
  const title = document.getElementById("statusTitle");
  const text = document.getElementById("statusText");
  const card = document.getElementById("checksCard");
  const list = document.getElementById("checksList");
  const updated = document.getElementById("checksUpdated");

  function label(name) {
    /* Server ichki nom beradi (`control_db`).  Tarjimasi bo'lmasa
       o'sha nom ko'rsatiladi: yangi tekshiruv qo'shilganda sahifa
       uni JIM tashlab yuborishi ("hammasi joyida" ko'rinishi)
       eng yomon natija bo'lardi. */
    return (TEXT.names && TEXT.names[name]) || name;
  }

  function render(checks) {
    if (!Array.isArray(checks) || !checks.length) return;
    list.innerHTML = "";
    checks.forEach(function (check) {
      const row = document.createElement("li");
      row.className = check.ok ? "is-ok" : "is-down";
      const name = document.createElement("span");
      name.textContent = label(check.name);
      const state = document.createElement("b");
      /* Kechikish faqat ISHLAYOTGAN tekshiruvda ma'noli: yiqilganida
         u "necha soniyada yiqildi" degani va chalkashtiradi. */
      const ms = check.ok && typeof check.ms === "number" ? " · " + check.ms + " ms" : "";
      state.textContent = (check.ok ? TEXT.checkOk : TEXT.checkFailed) + ms;
      row.appendChild(name);
      row.appendChild(state);
      list.appendChild(row);
    });
    const now = new Date();
    const pad = function (value) { return String(value).padStart(2, "0"); };
    updated.textContent = TEXT.updated.replace(
      "{time}",
      pad(now.getHours()) + ":" + pad(now.getMinutes())
    );
    card.hidden = false;
  }

  function down(message) {
    /* Qizil chiroq SHART: ilgari nosozlikda chiroq KULRANG qolardi —
       aynan "hali tekshirilmoqda" bilan bir xil ko'rinish, ya'ni
       sahifa eng kerakli daqiqada hech narsa aytmasdi. */
    light.classList.remove("online");
    light.classList.add("down");
    title.textContent = TEXT.downTitle;
    text.textContent = message || TEXT.downText;
  }

  /* Ataylab `/health` EMAS: u Docker HEALTHCHECK uchun mo'ljallangan va
     hech narsani tekshirmasdan doim 200 qaytaradi — Postgres o'lgan
     bulut ham bu sahifada "ishlayapti" bo'lib ko'rinardi.  `/health/deep`
     bazani, MinIO'ni va diskni tekshiradi va nosozlikda 503 beradi. */
  const controller = typeof AbortController === "function" ? new AbortController() : null;
  /* 8 soniya: `/health/deep` uchta bloklovchi tekshiruv qiladi va
     har biri sekin diskda ~2 soniyaga cho'zilishi mumkin.  Timeoutsiz
     sahifa "Tekshirilmoqda…" da ABADIY qotib qolardi — brauzer
     so'rovni o'zi uzmaydi. */
  const timer = window.setTimeout(function () {
    if (controller) controller.abort();
    else down(TEXT.timeout);
  }, 8000);

  fetch("/health/deep", { cache: "no-store", signal: controller ? controller.signal : undefined })
    .then(function (response) {
      /* 503 ham JSON qaytaradi va uning ichida QAYSI tekshiruv
         yiqilgani bor — javobni tashlab yuborish eng qimmat
         ma'lumotni yo'qotardi. */
      return response.json().then(function (payload) {
        return { ok: response.ok, payload: payload };
      });
    })
    .then(function (result) {
      window.clearTimeout(timer);
      render(result.payload && result.payload.checks);
      if (result.ok) {
        light.classList.add("online");
        title.textContent = TEXT.upTitle;
        text.textContent = TEXT.upText;
        return;
      }
      /* Javob KELDI, lekin bir qismi yiqilgan — bu "aloqa yo'q" dan
         boshqa holat va mijoz uchun farqi bor. */
      light.classList.add("down");
      title.textContent = TEXT.partialTitle;
      text.textContent = TEXT.partialText;
    })
    .catch(function (error) {
      window.clearTimeout(timer);
      down(error && error.name === "AbortError" ? TEXT.timeout : TEXT.downText);
    });
})();
