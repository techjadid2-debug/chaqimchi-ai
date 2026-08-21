/* Chiziq va zona sozlash paneli — usta va admin panellari uchun UMUMIY.
 *
 * Nega alohida fayl: bu bo'lim ilgari faqat `installer.html` ichida,
 * inline yozilgan edi.  Admin panelida ham kerak bo'lgach ikki nusxa
 * paydo bo'lardi va ular albatta bir-biridan uzoqlashardi.
 *
 * Nega inline `onclick` YO'Q: `admin.html` da ular taqiqlangan
 * (`tests/test_static_pages.py: test_admin_panel_has_no_inline_event_handlers`).
 * Shu sabab hamma narsa `data-act` va delegatsiya orqali.
 *
 * Chizishning o'zi `zone-editor.js` da (`ZoneEditor`) — u qurilmadagi
 * sehrgar bilan UMUMIY va oddiy JS holida qoladi.
 *
 * Bu modul faqat "atrofini" bajaradi: kamera tanlash, kadr yuklash,
 * shakllar ro'yxati va saqlash.  Manzillar tashqaridan beriladi, ya'ni
 * modul usta va admin API'lari orasidagi farqni bilmaydi.
 */
(function (global) {
  "use strict";

  function esc(value) {
    return String(value == null ? "" : value).replace(
      /[&<>"']/g,
      (ch) =>
        ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch],
    );
  }

  /* `opts`:
   *   els      — {canvas, camera, mode, status, list, save, reload}
   *   api      — panelning o'z `api(path, init)` funksiyasi
   *   paths    — {config, cameras, preview(id), askPreview(id)}
   *   onSaved  — saqlangandan keyin (ixtiyoriy)
   */
  function mount(opts) {
    const els = opts.els;
    const api = opts.api;
    const paths = opts.paths;
    if (!els.canvas || typeof global.ZoneEditor === "undefined") return null;

    let config = null;
    const editor = new global.ZoneEditor(els.canvas, {
      askName: (title, fallback) => {
        const value = prompt(title, fallback);
        return value === null ? null : value.trim() || fallback;
      },
      confirm: (message) => confirm(message),
      onChange: renderShapes,
    });

    function status(text) {
      if (els.status) els.status.textContent = text || "";
    }

    function loadPreviewImage() {
      const cameraId = els.camera.value;
      if (!cameraId) {
        editor.setImage(null);
        return;
      }
      const image = new Image();
      image.onload = () => editor.setImage(image);
      // Kadr hali kelmagan bo'lsa 404 — bu xato emas, shunchaki bo'sh
      // fon bilan chiziladi.
      image.onerror = () => editor.setImage(null);
      image.src = paths.preview(cameraId) + "?t=" + Date.now();
    }

    async function load() {
      try {
        const [conf, cams] = await Promise.all([api(paths.config), api(paths.cameras)]);
        config = conf.config;
        const list = cams.cameras || [];
        els.camera.innerHTML = list.length
          ? list
              .map(
                (c) =>
                  `<option value="${esc(c.camera_id)}">${esc(c.camera_id)} · ${esc(
                    c.label || c.camera_id,
                  )}</option>`,
              )
              .join("")
          : '<option value="">Kamera yo‘q</option>';
        const first = list.length ? list[0].camera_id : "";
        editor.load(config, first);
        els.camera.value = first;
        loadPreviewImage();
        renderShapes();
      } catch (err) {
        status(err.message);
      }
    }

    async function reloadFrame() {
      const cameraId = els.camera.value;
      if (!cameraId) return;
      status("Kadr so‘ralmoqda…");
      try {
        await api(paths.askPreview(cameraId), { method: "POST" });
        // Qurilma buyruqni keyingi "salom"da ko'radi — 20 soniyagacha.
        status("So‘raldi. Kadr 20 soniyagacha kelishi mumkin.");
        setTimeout(loadPreviewImage, 3000);
      } catch (err) {
        status(err.message);
      }
    }

    /* Zona belgilari (taqiqlangan/navbat/uzoq turish) va chiziq yo'nalishi
     * kadr USTIDA emas, ro'yxatda o'zgartiriladi — kichik tugmalarni kadr
     * ichiga sig'dirib bo'lmaydi. */
    function renderShapes() {
      if (!els.list) return;
      const rows = [];
      editor.visibleLines().forEach((line) => {
        const i = editor.lines.indexOf(line);
        rows.push(
          `<div class="shape"><b>Chiziq:</b> ${esc(line.name)}` +
            `<button type="button" class="button small" data-act="swap" data-i="${i}">Yo‘nalishni almashtirish</button>` +
            `<button type="button" class="button small" data-act="drop-line" data-i="${i}">O‘chirish</button></div>`,
        );
      });
      editor.visibleZones().forEach((zone) => {
        const i = editor.zones.indexOf(zone);
        rows.push(
          `<div class="shape"><b>Zona:</b> ${esc(zone.name)}` +
            `<label><input type="checkbox" data-act="restricted" data-i="${i}"${
              zone.restricted ? " checked" : ""
            }> taqiqlangan</label>` +
            `<label><input type="checkbox" data-act="queue" data-i="${i}"${
              zone.queue ? " checked" : ""
            }> navbat</label>` +
            `<label>uzoq turish (s) <input type="number" min="5" max="86400" data-act="dwell" data-i="${i}" value="${
              zone.dwell_sec || ""
            }"></label>` +
            `<button type="button" class="button small" data-act="drop-zone" data-i="${i}">O‘chirish</button></div>`,
        );
      });
      els.list.innerHTML = rows.length
        ? rows.join("")
        : '<p class="hint">Bu kamerada hali chiziq/zona yo‘q. Kirish kamerasida kamida bitta chiziq bo‘lishi SHART — aks holda kirganlar sanalmaydi. Navbat uchun esa zonaga «navbat» belgisi kerak.</p>';
    }

    async function save() {
      if (!config) return;
      const shapes = editor.serialise();
      try {
        const saved = await api(paths.config, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ...config,
            zones: shapes.zones,
            lines: shapes.lines,
          }),
        });
        config = saved.config;
        status(
          `Saqlandi: ${shapes.lines.length} chiziq, ${shapes.zones.length} zona. ` +
            "Qurilma bir daqiqada qabul qiladi.",
        );
        if (opts.onSaved) opts.onSaved(saved);
      } catch (err) {
        status(err.message);
      }
    }

    // ── Hodisalar ──────────────────────────────────────────────────────
    els.mode.addEventListener("change", () => {
      editor.setMode(els.mode.value);
      renderShapes();
    });
    els.camera.addEventListener("change", () => {
      editor.setCamera(els.camera.value);
      loadPreviewImage();
      renderShapes();
    });
    if (els.save) els.save.addEventListener("click", save);
    if (els.reload) els.reload.addEventListener("click", reloadFrame);

    if (els.list) {
      els.list.addEventListener("click", (event) => {
        const button = event.target.closest("[data-act]");
        if (!button || button.tagName !== "BUTTON") return;
        const i = Number(button.dataset.i);
        const act = button.dataset.act;
        if (act === "swap") {
          editor.lines[i].swap_direction = !editor.lines[i].swap_direction;
        } else if (act === "drop-line") {
          editor.lines.splice(i, 1);
        } else if (act === "drop-zone") {
          editor.zones.splice(i, 1);
        } else return;
        editor.draw();
        renderShapes();
      });
      els.list.addEventListener("change", (event) => {
        const input = event.target.closest("[data-act]");
        if (!input || input.tagName !== "INPUT") return;
        const i = Number(input.dataset.i);
        const act = input.dataset.act;
        if (act === "restricted" || act === "queue") {
          editor.zones[i][act] = input.checked;
        } else if (act === "dwell") {
          editor.zones[i].dwell_sec = input.value ? Number(input.value) : null;
        } else return;
        editor.draw();
        renderShapes();
      });
    }

    editor.setMode(els.mode.value);
    load();
    return { load, save, reloadFrame };
  }

  global.GeometryPanel = { mount: mount };
})(window);
