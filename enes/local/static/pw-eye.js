/* Parol maydonlariga "ko'z" (ko'rsatish/yashirish) tugmasi.
 *
 * Sahifadagi BARCHA `input[type=password]` avtomatik boyitiladi —
 * keyin qo'shilganlari ham (masalan admin panel modal oynalari):
 * `focusin` da hali boyitilmagan parol maydoni ushlab olinadi.
 *
 * Yagona manba shu fayl: lokal sehrgar `/assets/pw-eye.js` dan,
 * cloud sahifalari `/vendor/pw-eye.js` dan oladi (zone-editor.js
 * bilan bir xil naqsh) — ikki nusxa saqlansa bittasi jimgina
 * eskirardi.
 */
(function () {
  "use strict";

  var EYE =
    '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/></svg>';
  var EYE_OFF =
    '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<path d="M3 3l18 18"/><path d="M10.6 5.2A11.7 11.7 0 0 1 12 5c6.5 0 10 6 10 6a17.8 17.8 0 0 1-3.3 3.9"/>' +
    '<path d="M6.5 6.6C3.7 8.4 2 12 2 12s3.5 6 10 6c1.4 0 2.7-.3 3.9-.7"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/></svg>';

  /* CSS shu yerda in'ektsiya qilinadi — uch xil sahifa uch xil css
     fayl ishlatadi, hammasiga alohida yozish bittasini unutish demak. */
  var style = document.createElement("style");
  style.textContent =
    ".pw-wrap{position:relative;display:block;width:100%}" +
    ".pw-wrap>input{width:100%;padding-right:40px;box-sizing:border-box}" +
    ".pw-eye{position:absolute;right:6px;top:50%;transform:translateY(-50%);" +
    "display:flex;align-items:center;justify-content:center;width:30px;height:30px;" +
    "padding:0;border:0;background:none;cursor:pointer;color:#5f6368;border-radius:8px}" +
    ".pw-eye:hover{color:#1a73e8;background:rgba(26,115,232,.08)}";
  document.head.appendChild(style);

  function enhance(input) {
    if (!input || input.closest(".pw-wrap")) return;
    var wrap = document.createElement("span");
    wrap.className = "pw-wrap";
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);

    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "pw-eye";
    btn.setAttribute("aria-label", "Parolni ko'rsatish");
    btn.tabIndex = -1; /* Tab tartibini buzmasin — sichqoncha/barmoq uchun. */
    btn.innerHTML = EYE;
    btn.addEventListener("click", function () {
      var show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.innerHTML = show ? EYE_OFF : EYE;
      btn.setAttribute("aria-label", show ? "Parolni yashirish" : "Parolni ko'rsatish");
      input.focus();
    });
    wrap.appendChild(btn);
  }

  function enhanceAll(root) {
    (root || document).querySelectorAll('input[type="password"]').forEach(enhance);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { enhanceAll(); });
  } else {
    enhanceAll();
  }
  /* Keyin qo'shilgan maydonlar (modal oynalar): fokus tushganda o'raladi.
     appendChild fokus holatini buzishi mumkin — qaytarib beramiz. */
  document.addEventListener("focusin", function (event) {
    var target = event.target;
    if (target && target.matches && target.matches('input[type="password"]') && !target.closest(".pw-wrap")) {
      enhance(target);
      target.focus();
    }
  });
})();
