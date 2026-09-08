/* Ulash sahifasi: juftlik kodidan o'rnatish buyrug'ini yasaydi.
 *
 * Matn `application/json` blokidan (sahifa uch tilda quriladi); u ijro
 * etilmaydi, ya'ni CSP `script-src` unga tegmaydi. */
(function () {
  const TEXT = JSON.parse(document.getElementById("page-text").textContent);

  // Standart — shu hostning o'zi: `/api/v1/public/urls` javob bermasa
  // ham buyruq yasaladi va odam qo'lda tuzata oladi.
  const PLATFORM = { api: location.origin, dl: location.origin };
  fetch("/api/v1/public/urls")
    .then((r) => (r.ok ? r.json() : null))
    .then((d) => {
      if (d) Object.assign(PLATFORM, d);
    })
    .catch(() => {});

  const code = document.getElementById("pairCode");
  const output = document.getElementById("command");
  const copy = document.getElementById("copyCommand");
  const status = document.getElementById("copyStatus");

  function make() {
    const value = code.value.trim().toUpperCase();
    if (!/^[A-F0-9]{6}$/.test(value)) {
      status.textContent = TEXT.badCode;
      status.className = "form-status error";
      return;
    }
    output.textContent =
      `curl -fsSL ${PLATFORM.dl}/downloads/sotqin-installer.sh | sudo bash -s -- ` +
      `--cloud ${PLATFORM.api} --code ${value}`;
    copy.hidden = false;
    status.textContent = TEXT.ready;
    status.className = "form-status ok";
  }

  document.getElementById("makeCommand").addEventListener("click", make);
  copy.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(output.textContent);
      status.textContent = TEXT.copied;
      status.className = "form-status ok";
    } catch (_) {
      status.textContent = TEXT.copyFailed;
      status.className = "form-status error";
    }
  });
})();
