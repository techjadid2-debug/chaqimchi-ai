/* Holat sahifasi: cloud tirikmi?
 *
 * Matn HTML ichidagi `application/json` blokidan o'qiladi — u ijro
 * etilmaydigan «data block», ya'ni CSP `script-src` unga tegmaydi.
 * Sahifa uch tilda quriladi, shuning uchun matn shu yerga qotirib
 * yozilmaydi. */
(function () {
  const TEXT = JSON.parse(document.getElementById("page-text").textContent);
  const title = document.getElementById("statusTitle");
  const text = document.getElementById("statusText");

  /* Ataylab `/health` EMAS: u Docker HEALTHCHECK uchun mo'ljallangan va
     hech narsani tekshirmasdan doim 200 qaytaradi — Postgres o'lgan
     bulut ham bu sahifada "ishlayapti" bo'lib ko'rinardi, ya'ni sahifa
     aynan kerak bo'lgan daqiqada yolg'on gapirardi.  `/health/deep`
     bazani, MinIO'ni va diskni tekshiradi va nosozlikda 503 beradi. */
  fetch("/health/deep", { cache: "no-store" })
    .then((r) => {
      if (!r.ok) throw new Error();
      return r.json();
    })
    .then(() => {
      document.getElementById("light").classList.add("online");
      title.textContent = TEXT.upTitle;
      text.textContent = TEXT.upText;
    })
    .catch(() => {
      title.textContent = TEXT.downTitle;
      text.textContent = TEXT.downText;
    });
})();
