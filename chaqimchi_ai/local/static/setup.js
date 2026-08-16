/* Sozlash ustasi.
 *
 * Qoida: bu sahifada **soxta natija yo'q**.  Har bir tugma haqiqiy so'rov
 * yuboradi va javobni ko'rsatadi.  Oldingi maketda web-kamera ustiga oldindan
 * yozilgan "Mijoz #1 [98%]" ramkalari chizilardi va pairing kod HTML ichida
 * qotirilgan edi — mijoz ishlayapti deb o'ylardi, aslida hech narsa
 * saqlanmagan edi.
 */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const esc = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]),
    );

  let pendingUrl = ""; // tasdiqlanishi kutilayotgan kamera manzili
  let cameras = [];
  let editor = null;
  let currentStep = 1;

  /* ── Umumiy yordamchilar ───────────────────────────────────────────── */

  async function api(path, options = {}) {
    const response = await fetch(path, {
      headers: options.body ? { "Content-Type": "application/json" } : {},
      ...options,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || "So‘rov bajarilmadi. Qayta urinib ko‘ring.");
    }
    return data;
  }

  function note(container, kind, title, body) {
    $(container).innerHTML =
      `<div class="note ${kind}"><b>${esc(title)}</b>${body ? esc(body) : ""}</div>`;
  }

  function clearNote(container) {
    $(container).innerHTML = "";
  }

  function goToStep(step) {
    currentStep = step;
    document.querySelectorAll("section.step").forEach((section) => {
      section.classList.toggle("hidden", Number(section.dataset.step) !== step);
    });
    document.querySelectorAll(".step-chip").forEach((chip) => {
      const index = Number(chip.dataset.step);
      chip.className =
        "step-chip" + (index === step ? " active" : index < step ? " done" : "");
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
    if (step === 3) setupGeometry();
    if (step === 5) loadCloud();
  }

  /* ── 1-qadam: kamera ────────────────────────────────────────────────── */

  $("brand").addEventListener("change", () => {
    const manual = $("brand").value === "manual";
    $("templateFields").classList.toggle("hidden", manual);
    $("manualField").classList.toggle("hidden", !manual);
  });

  $("scanBtn").addEventListener("click", async () => {
    const button = $("scanBtn");
    button.disabled = true;
    note("scanResult", "warn", "Tarmoq tekshirilmoqda…", "Bu 10–30 soniya olishi mumkin.");
    try {
      const data = await api("/api/setup/scan", { method: "POST" });
      if (!data.count) {
        note(
          "scanResult",
          "warn",
          "Tarmoqda kamera topilmadi.",
          "Bu tez-tez uchraydi: ko‘p NVR o‘zini e’lon qilmaydi. Quyida NVR manzilini qo‘lda kiriting — natija bir xil bo‘ladi.",
        );
        return;
      }
      $("scanResult").innerHTML =
        `<div class="note ok"><b>${data.count} ta qurilma topildi</b>Kerakligini tanlang — manzili quyidagi formaga qo‘yiladi.</div>` +
        '<div class="found-list">' +
        data.devices
          .map(
            (device) => `
          <div class="found">
            <div>
              <b>${esc(device.vendor)}</b><br>
              <code>${esc(device.ip)}</code>
            </div>
            <button class="button ghost small" type="button" data-ip="${esc(device.ip)}">Shuni tanlash</button>
          </div>`,
          )
          .join("") +
        "</div>";
      $("scanResult")
        .querySelectorAll("button[data-ip]")
        .forEach((item) =>
          item.addEventListener("click", () => {
            $("host").value = item.dataset.ip;
            $("host").scrollIntoView({ behavior: "smooth", block: "center" });
            $("username").focus();
          }),
        );
    } catch (error) {
      note("scanResult", "err", "Qidiruv bajarilmadi.", error.message);
    } finally {
      button.disabled = false;
    }
  });

  async function currentRtspUrl() {
    if ($("brand").value === "manual") {
      const value = $("manualUrl").value.trim();
      if (!value) throw new Error("RTSP manzilini kiriting.");
      return value;
    }
    const host = $("host").value.trim();
    if (!host) throw new Error("NVR yoki kamera IP manzilini kiriting.");
    const data = await api("/api/setup/rtsp-template", {
      method: "POST",
      body: JSON.stringify({
        brand: $("brand").value,
        host,
        username: $("username").value,
        password: $("password").value,
        channel: Number($("channel").value || 1),
      }),
    });
    return data.rtsp_url;
  }

  $("testBtn").addEventListener("click", async () => {
    const button = $("testBtn");
    button.disabled = true;
    note("testResult", "warn", "Kameraga ulanmoqda…", "15 soniyagacha kutiladi.");
    try {
      const url = await currentRtspUrl();
      const result = await api("/api/setup/test-camera", {
        method: "POST",
        body: JSON.stringify({ rtsp_url: url }),
      });
      if (!result.ok) {
        note("testResult", "err", result.error, " " + result.hint);
        return;
      }
      clearNote("testResult");
      pendingUrl = url;
      $("confirmImage").src =
        "/api/setup/preview?rtsp_url=" + encodeURIComponent(url) + "&t=" + Date.now();
      goToStep(2);
    } catch (error) {
      note("testResult", "err", "Tekshirib bo‘lmadi.", " " + error.message);
    } finally {
      button.disabled = false;
    }
  });

  // Do'konda odatda bitta NVR va unda bir necha kamera bo'ladi.  Ilgari
  // mijoz har biri uchun IP, login va parolni qaytadan kiritardi — bir
  // xil ma'lumotni to'rt marta.  Endi bir marta kiritadi.
  $("scanChannelsBtn").addEventListener("click", async () => {
    const button = $("scanChannelsBtn");
    if ($("brand").value === "manual") {
      return note("channelResult", "warn", "Bu tugma NVR uchun.", " Brendni yuqorida tanlang.");
    }
    button.disabled = true;
    note("channelResult", "warn", "Kanallar tekshirilmoqda…", " Har biri uchun 15 soniyagacha.");
    try {
      const data = await api("/api/setup/scan-channels", {
        method: "POST",
        body: JSON.stringify({
          brand: $("brand").value,
          host: $("host").value.trim(),
          username: $("username").value,
          password: $("password").value,
        }),
      });
      if (!data.found) {
        return note("channelResult", "err", "Kamera topilmadi.", " " + data.hint);
      }
      $("channelResult").innerHTML =
        `<div class="note ok"><b>${data.found} ta kamera topildi</b>Nomini yozing va saqlang.</div>` +
        data.channels
          .map(
            (item) => `
        <div class="camera-row">
          <span class="dot on"></span>
          <div class="meta">
            <b>${item.channel}-kanal</b>
            <code>${esc(item.safe_url)}</code>
          </div>
          <input type="text" data-name="${item.channel}" placeholder="Masalan: Kirish"
                 style="max-width:190px" value="${item.channel === 1 ? "Kirish eshigi" : ""}">
        </div>`,
          )
          .join("") +
        '<div class="actions"><button class="button primary" id="saveChannelsBtn" type="button">Hammasini saqlash</button></div>';

      $("saveChannelsBtn").addEventListener("click", async () => {
        const btn = $("saveChannelsBtn");
        btn.disabled = true;
        try {
          for (const item of data.channels) {
            const field = document.querySelector(`[data-name="${item.channel}"]`);
            await api("/api/setup/cameras", {
              method: "POST",
              body: JSON.stringify({
                label: (field && field.value.trim()) || `${item.channel}-kanal`,
                rtsp_url: item.rtsp_url,
              }),
            });
          }
          $("password").value = "";
          await loadCameras();
          note("channelResult", "ok", "Kameralar saqlandi.", " Keyingi qadamga o‘tishingiz mumkin.");
        } catch (error) {
          note("channelResult", "err", "Saqlanmadi.", " " + error.message);
        } finally {
          btn.disabled = false;
        }
      });
    } catch (error) {
      note("channelResult", "err", "Tekshirib bo‘lmadi.", " " + error.message);
    } finally {
      button.disabled = false;
    }
  });

  /* ── 2-qadam: kadrni tasdiqlash ─────────────────────────────────────── */

  $("rejectFrame").addEventListener("click", () => {
    pendingUrl = "";
    goToStep(1);
  });

  $("acceptFrame").addEventListener("click", async () => {
    const button = $("acceptFrame");
    button.disabled = true;
    try {
      await api("/api/setup/cameras", {
        method: "POST",
        body: JSON.stringify({
          label: $("label").value.trim(),
          rtsp_url: pendingUrl,
        }),
      });
      pendingUrl = "";
      $("password").value = "";
      $("manualUrl").value = "";
      $("label").value = "";
      await loadCameras();
      goToStep(1);
      note("scanResult", "ok", "Kamera saqlandi.", " Yana qo‘shishingiz yoki keyingi qadamga o‘tishingiz mumkin.");
    } catch (error) {
      note("testResult", "err", "Saqlanmadi.", " " + error.message);
      goToStep(1);
    } finally {
      button.disabled = false;
    }
  });

  async function loadCameras() {
    const data = await api("/api/setup/cameras");
    cameras = data.cameras;
    $("cameraList").innerHTML = cameras.length
      ? cameras
          .map(
            (camera) => `
        <div class="camera-row">
          <span class="dot on"></span>
          <div class="meta">
            <b>${esc(camera.label)}</b>
            <code>${esc(camera.safe_url)}</code>
          </div>
          <button class="button danger small" type="button" data-remove="${esc(camera.camera_id)}">O‘chirish</button>
        </div>`,
          )
          .join("")
      : '<p class="hint">Hali kamera qo‘shilmagan.</p>';

    $("cameraList")
      .querySelectorAll("button[data-remove]")
      .forEach((button) =>
        button.addEventListener("click", async () => {
          const id = button.dataset.remove;
          if (!confirm("Kamera va uning chiziqlari o‘chirilsinmi?")) return;
          await api(`/api/setup/cameras/${encodeURIComponent(id)}`, { method: "DELETE" });
          await loadCameras();
        }),
      );

    $("toStep3").disabled = cameras.length === 0;
    if (cameras.length >= data.max_cameras) {
      $("testBtn").disabled = true;
      note(
        "testResult",
        "warn",
        `Ko‘pi bilan ${data.max_cameras} kamera.`,
        " Bu chegara o‘lchangan sig‘imga asoslangan — ortiqcha kamera tahlilni sekinlashtiradi.",
      );
    } else {
      $("testBtn").disabled = false;
    }
  }

  $("toStep3").addEventListener("click", () => goToStep(3));
  $("backToStep1").addEventListener("click", () => goToStep(1));
  $("backToStep3").addEventListener("click", () => goToStep(3));

  /* ── 3-qadam: chiziq va zona ────────────────────────────────────────── */

  async function setupGeometry() {
    const canvas = $("geoCanvas");
    if (!canvas || typeof ZoneEditor === "undefined") {
      note("geoResult", "err", "Chizish vositasi yuklanmadi.", " Sahifani yangilang.");
      return;
    }
    if (!editor) {
      editor = new ZoneEditor(canvas, {
        askName: (title, fallback) => {
          const value = prompt(title, fallback);
          return value === null ? null : value.trim() || fallback;
        },
        confirm: (message) => confirm(message),
        onChange: renderShapes,
      });
    }

    $("geoCamera").innerHTML = cameras
      .map((camera) => `<option value="${esc(camera.camera_id)}">${esc(camera.label)}</option>`)
      .join("");

    const geometry = await api("/api/setup/geometry");
    const first = cameras.length ? cameras[0].camera_id : "";
    editor.load(geometry, first);
    editor.setMode($("geoMode").value);
    $("geoCamera").value = first;
    suggestLine(first);
    loadFrame();
    renderShapes();
  }

  /**
   * Kamerada chiziq bo'lmasa taxminiy chiziq chizib beradi.
   *
   * Nega: bo'sh kadr oldida "chiziq torting" degan ko'rsatma eng ko'p
   * to'xtatadigan joy edi — mijoz qayerdan qayerga tortishni bilmaydi.
   * Tayyor chiziqni surib to'g'rilash ancha oson.
   *
   * Balandlik 0.62 — eshik odatda kadrning pastki yarmida bo'ladi, lekin
   * eng pastda emas (u yerda pol ko'rinadi).  Bu **taxmin**, shuning
   * uchun mijozga aynan shunday aytiladi va u surib o'zgartira oladi.
   */
  function suggestLine(cameraId) {
    if (!cameraId) return;
    const exists = editor.lines.some((line) => line.camera_id === cameraId);
    if (exists) return;
    editor.lines.push({
      name: "Kirish",
      camera_id: cameraId,
      start: [0.15, 0.62],
      end: [0.85, 0.62],
      swap_direction: false,
    });
    editor.draw();
    note(
      "geoResult",
      "warn",
      "Taxminiy chiziq chizildi.",
      " Uni eshik oldiga surib to‘g‘rilang: nuqtalarni sudrab ko‘chiring. " +
        "Yashil o‘q do‘kon ichkarisini ko‘rsatishi kerak.",
    );
  }

  function loadFrame() {
    const cameraId = $("geoCamera").value;
    if (!cameraId) return;
    const image = new Image();
    image.onload = () => editor.setImage(image);
    image.onerror = () =>
      note("geoResult", "warn", "Kadr yuklanmadi.", " “Kadrni yangilash” tugmasini bosing.");
    image.src = "/api/setup/preview?camera_id=" + encodeURIComponent(cameraId) + "&t=" + Date.now();
  }

  $("geoCamera").addEventListener("change", () => {
    editor.setCamera($("geoCamera").value);
    suggestLine($("geoCamera").value);
    loadFrame();
    renderShapes();
  });
  $("geoMode").addEventListener("change", () => {
    editor.setMode($("geoMode").value);
    renderShapes();
  });
  $("refreshFrame").addEventListener("click", loadFrame);

  function renderShapes() {
    if (!editor) return;
    const rows = [];
    editor.visibleLines().forEach((line) => {
      const index = editor.lines.indexOf(line);
      rows.push(`
        <div class="shape">
          <b>Chiziq:</b> ${esc(line.name)}
          <button class="button ghost small" type="button" data-swap="${index}">Yo‘nalishni almashtirish</button>
          <button class="button danger small" type="button" data-drop-line="${index}">O‘chirish</button>
        </div>`);
    });
    editor.visibleZones().forEach((zone) => {
      const index = editor.zones.indexOf(zone);
      rows.push(`
        <div class="shape">
          <b>Zona:</b> ${esc(zone.name)}
          <label><input type="checkbox" data-zone="${index}" data-field="restricted" ${zone.restricted ? "checked" : ""}> taqiqlangan</label>
          <label><input type="checkbox" data-zone="${index}" data-field="queue" ${zone.queue ? "checked" : ""}> navbat</label>
          <label>uzoq turish (s) <input type="number" min="5" max="86400" data-zone="${index}" data-field="dwell_sec" value="${zone.dwell_sec || ""}"></label>
          <button class="button danger small" type="button" data-drop-zone="${index}">O‘chirish</button>
        </div>`);
    });

    $("shapeList").innerHTML = rows.length
      ? rows.join("")
      : '<p class="hint">Bu kamerada hali chiziq yo‘q. Kirish kamerasida kamida bitta chiziq bo‘lishi shart — aks holda kirganlar sanalmaydi.</p>';

    $("shapeList")
      .querySelectorAll("[data-swap]")
      .forEach((item) =>
        item.addEventListener("click", () => {
          const line = editor.lines[Number(item.dataset.swap)];
          line.swap_direction = !line.swap_direction;
          editor.draw();
        }),
      );
    $("shapeList")
      .querySelectorAll("[data-drop-line]")
      .forEach((item) =>
        item.addEventListener("click", () => {
          editor.lines.splice(Number(item.dataset.dropLine), 1);
          editor.draw();
          renderShapes();
        }),
      );
    $("shapeList")
      .querySelectorAll("[data-drop-zone]")
      .forEach((item) =>
        item.addEventListener("click", () => {
          editor.zones.splice(Number(item.dataset.dropZone), 1);
          editor.draw();
          renderShapes();
        }),
      );
    $("shapeList")
      .querySelectorAll("[data-zone][data-field]")
      .forEach((item) =>
        item.addEventListener("change", () => {
          const zone = editor.zones[Number(item.dataset.zone)];
          const field = item.dataset.field;
          if (field === "dwell_sec") {
            zone.dwell_sec = item.value ? Number(item.value) : null;
          } else {
            zone[field] = item.checked;
          }
          editor.draw();
        }),
      );
  }

  $("toStep4").addEventListener("click", async () => {
    const button = $("toStep4");
    button.disabled = true;
    try {
      const shapes = editor.serialise();
      if (!shapes.lines.length && !shapes.zones.length) {
        note(
          "geoResult",
          "err",
          "Hech narsa chizilmagan.",
          " Kirish eshigi ustidan chiziq torting — usiz odam sanalmaydi.",
        );
        return;
      }
      await api("/api/setup/geometry", {
        method: "PUT",
        body: JSON.stringify(shapes),
      });
      clearNote("geoResult");
      goToStep(4);
    } catch (error) {
      note("geoResult", "err", "Saqlanmadi.", " " + error.message);
    } finally {
      button.disabled = false;
    }
  });

  /* ── 4-qadam: yakun ─────────────────────────────────────────────────── */

  $("finishBtn").addEventListener("click", async () => {
    const button = $("finishBtn");
    button.disabled = true;
    note("finishResult", "warn", "Saqlanmoqda…", "");
    try {
      const from = $("openFrom").value;
      const to = $("openTo").value;
      if (Boolean(from) !== Boolean(to)) {
        note("finishResult", "err", "Ish vaqti to‘liq emas.", " Ochilish va yopilishni birga kiriting yoki ikkalasini bo‘sh qoldiring.");
        return;
      }
      await api("/api/setup/settings", {
        method: "PUT",
        body: JSON.stringify({
          open_from: from || null,
          open_to: to || null,
          occupancy_limit: Number($("occupancy").value || 30),
          queue_limit: Number($("queueLimit").value || 5),
          loitering_sec: Number($("loitering").value || 300),
        }),
      });
      await api("/api/setup/telegram", {
        method: "PUT",
        body: JSON.stringify({ token: $("tgToken").value, chat_id: $("tgChat").value }),
      });

      const status = await api("/api/service/start", { method: "POST" });
      if (!status.running) {
        note(
          "finishResult",
          "err",
          "Sozlama saqlandi, lekin AI ishga tushmadi.",
          " " + (status.error || "Panelda “Nima bo‘ldi?” tugmasi orqali jurnalni ko‘ring."),
        );
        return;
      }
      note("finishResult", "ok", "Tayyor! Nazorat ishlamoqda.", " Endi ixtiyoriy oxirgi qadam.");
      setTimeout(() => goToStep(5), 900);
    } catch (error) {
      note("finishResult", "err", "Saqlanmadi.", " " + error.message);
    } finally {
      button.disabled = false;
    }
  });

  /* ── 5-qadam: cloudga ulash (ixtiyoriy) ─────────────────────────────── */

  function renderCloud(state) {
    const connected = Boolean(state.connected);
    $("cloudConnected").classList.toggle("hidden", !connected);
    $("cloudForm").classList.toggle("hidden", connected);
    // Manzil o'rnatuvchi bilan kelgan bo'lsa mijoz uni yozmaydi.
    if (!connected && state.default_cloud_url && !$("cloudUrl").value) {
      $("cloudUrl").value = state.default_cloud_url;
    }
    if (connected) {
      $("cloudSite").textContent = `Obyekt: ${state.site_id}`;
      const link = $("cloudOwnerLink");
      link.href = state.owner_url || "#";
      link.textContent = state.owner_url || "";
    }
  }

  async function loadCloud() {
    try {
      renderCloud(await api("/api/setup/cloud-status"));
    } catch (_) {
      /* Holat olinmasa forma ko'rinib turaveradi — mijoz baribir ulay oladi. */
    }
  }

  $("pairBtn").addEventListener("click", async () => {
    const button = $("pairBtn");
    button.disabled = true;
    note("pairResult", "warn", "Cloudga ulanmoqda…", "");
    try {
      const result = await api("/api/setup/pair", {
        method: "POST",
        body: JSON.stringify({
          code: $("pairCode").value,
          cloud_url: $("cloudUrl").value,
        }),
      });
      renderCloud(result);
      note(
        "pairResult",
        "ok",
        "Ulandi!",
        " Endi hodisalar cloudga yuboriladi va Telegram ogohlantirishlari ishlaydi.",
      );
    } catch (error) {
      note("pairResult", "err", "Ulanmadi.", " " + error.message);
    } finally {
      button.disabled = false;
    }
  });

  $("unpairBtn").addEventListener("click", async () => {
    if (!confirm("Cloud ulanishi uzilsinmi? Mijoz paneli va Telegram xabarlari to‘xtaydi.")) return;
    try {
      renderCloud(await api("/api/setup/unpair", { method: "POST" }));
      note("pairResult", "warn", "Ulanish uzildi.", " Tizim lokal rejimda ishlashda davom etadi.");
    } catch (error) {
      note("pairResult", "err", "Uzilmadi.", " " + error.message);
    }
  });

  $("backToStep4").addEventListener("click", () => goToStep(4));
  $("skipCloud").addEventListener("click", () => {
    window.location.href = "/panel";
  });

  /* ── Boshlash ───────────────────────────────────────────────────────── */

  (async function boot() {
    try {
      await loadCameras();
      const summary = await api("/api/setup/summary");
      if (!summary.model_available) {
        note(
          "scanResult",
          "err",
          "AI modeli topilmadi.",
          " Kamera qo‘shishingiz mumkin, lekin tahlil ishlamaydi. Dasturni qayta o‘rnating.",
        );
      }
    } catch (error) {
      note("scanResult", "err", "Dastur bilan aloqa yo‘q.", " " + error.message);
    }
  })();
})();
