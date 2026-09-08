/* To'lov sahifasi: hisob holati va Payme/Click tugmalari.
 *
 * Inline `<script>` dan chiqarildi (CSP `script-src` da `'unsafe-inline'`
 * yo'q).  Server qo'yadigan manzillar (`__APP_URL__`,
 * `__TELEGRAM_REGISTER_URL__`) endi HTML ichidagi `application/json`
 * blokidan o'qiladi — u ijro etilmaydi, ya'ni siyosatdan tashqarida.
 */
(function () {
  const LINKS = JSON.parse(document.getElementById("page-links").textContent);

  // Mijozga sotilgan nom bilan bir xil bo'lishi shart: saytda
  // "Lite" deb yozilgan, bu yerda ichki kod nomi turmasin.
  const PLAN_LABEL = { lite: "ENES Lite" };
  const uzs = (n) => Number(n || 0).toLocaleString("ru-RU") + " so'm";
  const esc = (s) =>
    String(s ?? "").replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]
    );

  // Har boshi berk ko'chada chiqish yo'li bo'lishi kerak.  Ilgari
  // mijozga menejerga murojaat qilish taklif qilinardi, lekin sahifada
  // na telefon, na Telegram bor edi — u pul to'lay olmay qolib ketardi.
  const HELP = `
    <div class="action-row">
      <a class="button button-light" href="${esc(LINKS.telegram)}">Telegramda yozish</a>
      <a class="button button-ghost" href="tel:+998932225070">+998 93 222 50 70</a>
      <a class="button button-ghost" href="${esc(LINKS.app)}">Panelga qaytish</a>
    </div>`;

  const invoiceId = location.pathname.split("/").filter(Boolean).pop();

  function renderPaid(inv) {
    return `
      <div class="status-banner ok">To'lov qabul qilindi
        <span class="sub">${esc(inv.months)} oylik obuna faollashtirildi.</span></div>
      ${HELP}`;
  }

  function renderCancelled() {
    return `
      <div class="status-banner warn">Bu hisob bekor qilingan
        <span class="sub">Yangi hisob ochish uchun bizga yozing.</span></div>
      ${HELP}`;
  }

  function renderPending(inv) {
    const buttons = [
      inv.payme_url
        ? `<a class="pay-btn pay-payme" href="${esc(inv.payme_url)}">Payme orqali to'lash</a>`
        : "",
      inv.click_url
        ? `<a class="pay-btn pay-click" href="${esc(inv.click_url)}">Click orqali to'lash</a>`
        : "",
    ].join("");

    return `
      <div class="hint">${esc(inv.site_name || "")}</div>
      <div class="amount">${uzs(inv.amount_uzs)}</div>
      <div class="hint">${esc(PLAN_LABEL[inv.plan] || inv.plan)} · ${esc(inv.months)} oy</div>
      ${buttons || `
        <div class="note" style="margin-top: 14px"><b>Onlayn to'lov hozircha ulanmagan</b>
          Naqd yoki bank o'tkazmasi uchun bizga yozing — hisobni biz yopamiz.</div>
        ${HELP}`}
      <details style="margin-top: 16px">
        <summary class="hint">Hisob raqami</summary>
        <p class="mono">${esc(inv.id)}</p>
      </details>`;
  }

  (async () => {
    const box = document.getElementById("box");
    try {
      const res = await fetch(`/api/v1/invoices/${encodeURIComponent(invoiceId)}`);
      if (!res.ok) throw new Error("Bu hisob topilmadi yoki muddati o'tgan");
      const inv = await res.json();
      box.innerHTML =
        inv.state === "paid" ? renderPaid(inv)
        : inv.state === "cancelled" ? renderCancelled()
        : renderPending(inv);
    } catch (err) {
      // Xom xato matni ("Failed to fetch") mijozga hech narsa aytmaydi —
      // unga nima qilishni aytadigan yo'l kerak.
      box.innerHTML = `
        <div class="status-banner err">${esc(err.message)}
          <span class="sub">Havolani qaytadan oching yoki bizga yozing.</span></div>
        ${HELP}`;
    }
  })();
})();
