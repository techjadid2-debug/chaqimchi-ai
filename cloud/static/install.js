/* O'rnatish yo'riqnomasi sahifasining mantiqi.
 *
 * Inline `<script>` dan chiqarildi: CSP `script-src` da
 * `'unsafe-inline'` yo'q. */
  const PLATFORM = { api: location.origin, dl: location.origin };
  fetch('/api/v1/public/urls').then((r) => r.ok ? r.json() : null).then((d) => { if (d) Object.assign(PLATFORM, d); }).catch(() => {});
// Yuklab olish tugmasi serverdan so'raladi: dastur nashr qilinmagan
// bo'lsa mijoz 503 qaytaradigan buzuq tugmani bosmasligi kerak.
fetch("/api/v1/public/windows-release")
  .then((response) => response.json())
  .then((release) => {
    if (!release.available) return;
    const button = document.getElementById("guideDownloadBtn");
    if (button && release.size_mb) {
      button.textContent = `Windows uchun yuklab olish (${release.size_mb} MB)`;
    }
    // Versiya ko'rinsin: hajm har relizda bir xil (68 MB) va usiz
    // yangi fayl chiqqanini sahifadan bilib bo'lmasdi.
    const label = document.getElementById("guideDownloadVersion");
    if (label && release.version) {
      label.textContent = `Versiya ${release.version}`;
      label.hidden = false;
    }
    // Fayl nomi ham RELIZDAN olinadi — sahifada qo'lda yozilgan raqam
    // turardi va u versiyadan orqada qolardi.
    //
    // Nom `ENES_Setup-<versiya>.exe`: serverdagi fayl
    // `enes-windows-<versiya>.exe` deb saqlanadi, lekin yuklab
    // olishda `content-disposition` uni shu ko'rinishda beradi
    // (`cloud/main.py: public_download_installer`) — mijoz aynan shu
    // nomni ko'radi.  Ikkalasini adashtirish oson, shuning uchun
    // nom SHU YERDA, bitta joyda yasaladi.
    const fileName = document.getElementById("guideFileName");
    if (fileName && release.version) {
      fileName.textContent = `ENES_Setup-${release.version}.exe`;
    }
    document.getElementById("guideDownloadReady").hidden = false;
    document.getElementById("guideDownloadPending").hidden = true;
  })
  .catch(() => {
    /* Tayyor emas — "raqamingizni qoldiring" bloki ko'rinib turaveradi. */
  });

function makeLin() {
  const value = document.getElementById('pairCodeLin').value.trim().toUpperCase();
  const out = document.getElementById('commandLin');
  const copy = document.getElementById('copyCommandLin');
  const status = document.getElementById('copyStatusLin');
  if (!/^[A-F0-9]{6}$/.test(value)) {
    status.textContent = '6 xonali pairing kodni kiriting (masalan: ABC123).';
    status.className = 'form-status error';
    return;
  }
  out.textContent = `curl -fsSL ${PLATFORM.dl}/downloads/sotqin-installer.sh | sudo bash -s -- --cloud ${PLATFORM.api} --code ${value}`;
  copy.hidden = false;
  status.textContent = 'Buyruq tayyor.';
  status.className = 'form-status ok';
}

async function copyText(elemId, statusId) {
  const text = document.getElementById(elemId).textContent;
  const status = document.getElementById(statusId);
  try {
    await navigator.clipboard.writeText(text);
    status.textContent = 'Buyruq nusxalandi.';
    status.className = 'form-status ok';
  } catch (_) {
    status.textContent = 'Matndan qo‘lda nusxalang.';
    status.className = 'form-status error';
  }
}

// Ishlov beruvchilar HTML atributida emas: CSP `script-src` ostida
// `onclick="…"` ishlamaydi.  Naqsh `geometry-panel.js` dagi bilan
// bir xil — tugma NIMA qilishini `data-act` da aytadi.
document.addEventListener("click", (event) => {
  const el = event.target.closest("[data-act]");
  if (!el) return;
  if (el.dataset.act === "make-command") makeLin();
  else if (el.dataset.act === "copy-command") copyText("commandLin", "copyStatusLin");
});
