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

  fetch("/health", { cache: "no-store" })
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
