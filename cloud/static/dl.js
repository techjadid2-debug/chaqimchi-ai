/* Yuklab olish sahifasi: eng yangi Windows relizining versiyasi va hajmi.
 *
 * Matn `application/json` blokidan (sahifa uch tilda quriladi); u ijro
 * etilmaydi, ya'ni CSP `script-src` unga tegmaydi. */
(function () {
  const TEXT = JSON.parse(document.getElementById("page-text").textContent);

  fetch("/api/v1/public/windows-release")
    .then((r) => (r.ok ? r.json() : null))
    .then((d) => {
      const meta = document.getElementById("dlMeta");
      if (d && d.available) {
        meta.textContent = TEXT.version
          .replace("{version}", d.version)
          .replace("{size}", d.size_mb);
      } else {
        // Reliz hali nashr qilinmagan — tugma o'chirilmaydi, xiralashadi:
        // sabab matnda aytiladi, tugma esa yo'qolib qolmaydi.
        meta.textContent = TEXT.pending;
        document.getElementById("dlBtn").style.opacity = ".5";
      }
    })
    .catch(() => {});
})();
