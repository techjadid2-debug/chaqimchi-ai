/* Do'kon paneli.
 *
 * Panel faqat **haqiqiy** raqamlarni ko'rsatadi: hammasi hodisalar
 * navbatidan (`outbox.db`) o'qiladi.  Demo qiymat, taxminiy son yoki
 * "namuna uchun" grafik yo'q — do'kon egasi shu raqamga qarab xodim
 * jadvalini tuzadi.
 */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const esc = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]),
    );

  const EVENT_LABELS = {
    line_crossed: "Kirish/chiqish",
    queue_threshold_exceeded: "Navbat uzun",
    occupancy_exceeded: "Do‘konda odam ko‘p",
    dwell_exceeded: "Zonada uzoq turdi",
    loitering: "Uzoq turish",
    zone_entered: "Taqiqlangan zonaga kirish",
    after_hours_presence: "Ish vaqtidan tashqari harakat",
    camera_tampered: "Kamera yopildi yoki burildi",
    camera_offline: "Kamera javob bermayapti",
    camera_recovered: "Kamera tiklandi",
    stream_frozen: "Tasvir qotib qoldi",
    person_detected: "Odam aniqlandi",
  };

  async function api(path, options = {}) {
    const response = await fetch(path, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "So‘rov bajarilmadi");
    return data;
  }

  function banner(kind, title, body, action) {
    $("alertArea").innerHTML = `<div class="note ${kind}"><b>${esc(title)}</b>${esc(body || "")}${
      action ? ` <a href="${esc(action.href)}">${esc(action.text)}</a>` : ""
    }</div>`;
  }

  /* ── Holat ───────────────────────────────────────────────────────────── */

  //: Bulut paneli manzili — `drawCloud` to'ldiradi, `drawStatus` o'qiydi.
  //  Ikkalasi bitta `refresh()` da chaqiriladi, ya'ni qiymat doim shu
  //  aylanishga tegishli.
  const cloudPanel = { url: "" };

  function drawStatus(status) {
    const dot = $("serviceDot");
    const text = $("serviceText");

    if (!status.ready) {
      dot.className = "dot off";
      text.textContent = "Sozlanmagan";
      // Ulangan bo'lsa mijozni BULUT paneliga yuboramiz: kamera ham,
      // chiziq ham endi o'sha yerda sozlanadi va u shu kompyuter
      // oldida o'tirishi shart emas.
      banner("warn", "Sozlash tugallanmagan.", "Kamera qo‘shing va kirish chizig‘ini chizing.", {
        href: cloudPanel.url || "/setup",
        text: cloudPanel.url ? "Panelda sozlash →" : "Sozlashni davom ettirish →",
      });
    } else if (!status.running) {
      dot.className = "dot off";
      text.textContent = "To‘xtatilgan";
      banner(
        "err",
        "Nazorat ishlamayapti.",
        status.error || "“Ishga tushirish” tugmasini bosing.",
      );
    } else if (status.status_stale) {
      // Jarayon tirik, lekin holat fayli yangilanmayapti — zanjir qotib
      // qolgan.  Mijoz uchun bu "ishlamayapti" bilan bir xil, shuning uchun
      // yashil chiroq ko'rsatish yolg'on bo'lardi.
      dot.className = "dot off";
      text.textContent = "Javob bermayapti";
      banner(
        "err",
        "AI xizmati javob bermayapti.",
        "Qayta ishga tushiring; takrorlansa jurnalni ko‘ring.",
      );
    } else if (status.cameras_configured && !status.cameras_active) {
      dot.className = "dot off";
      text.textContent = "Kamera ulanmadi";
      banner(
        "err",
        "Birorta kameradan tasvir kelmayapti.",
        "NVR yoqilganini va tarmoq kabelini tekshiring.",
      );
    } else {
      dot.className = "dot on";
      text.textContent = "Ishlayapti";
      $("alertArea").innerHTML = "";
    }

    $("startBtn").disabled = status.running || !status.ready;
    $("restartBtn").disabled = !status.ready;
    $("stopBtn").disabled = !status.running;

    if (status.running && status.uptime_sec) {
      const hours = Math.floor(status.uptime_sec / 3600);
      const minutes = Math.floor((status.uptime_sec % 3600) / 60);
      $("uptimeText").textContent = `Uzluksiz ishlayapti: ${hours} soat ${minutes} daqiqa · ${status.cameras_active}/${status.cameras_configured} kamera ulangan`;
    } else {
      $("uptimeText").textContent = status.error || "Xizmat to‘xtatilgan.";
    }

    // Sog'liq zanjirdan keladi (`cameras`), nomlar esa sozlamadan
    // (`cameras_list`).  Ro'yxat ikkalasining BIRLASHMASI: zanjir hali
    // ochmagan kamera ham qatorda ko'rinsin, aks holda mijoz "kamera
    // yo'qolib qoldi" deb o'ylaydi.
    const health = status.cameras || {};
    const saved = status.cameras_list || [];
    const names = new Map(saved.map((c) => [c.camera_id, c.label]));
    const rows = [...new Set([...saved.map((c) => c.camera_id), ...Object.keys(health)])];
    const online = (id) => Boolean(health[id] && health[id].connected && !health[id].offline);
    const activeCount = rows.filter(online).length;
    $("cameraCount").textContent = rows.length
      ? `${rows.length} kameradan ${activeCount} tasi ulangan`
      : "";
    $("cameraStatus").innerHTML = rows.length
      ? rows
          .map((id) => {
            const known = Object.prototype.hasOwnProperty.call(health, id);
            const up = online(id);
            const state = up
              ? "tasvir kelmoqda"
              : known
                ? "javob bermayapti"
                : "hali ulanmadi";
            return `
        <div class="camera-row">
          <span class="dot ${up ? "on" : "off"}"></span>
          <div class="meta">
            <b>${esc(names.get(id) || id)}</b>
            <code>${state}</code>
          </div>
        </div>`;
          })
          .join("")
      : '<p class="hint">Kamera qo‘shilmagan. «Sozlash» bo‘limidan kamera qo‘shing.</p>';

    drawFeatures(status);
  }

  /* ── Funksiyalar holati ──────────────────────────────────────────────── */
  //
  // "Yashil chiroq yolg'oni"ga qarshi: xizmat ishlayotgani hali hamma
  // funksiya ishlayotganini bildirmaydi.  Har biri alohida ko'rsatiladi,
  // ishlamayotganiga esa aniq sabab yoziladi.

  function drawFeatures(status) {
    const box = $("featureList");
    if (!box) return;
    const features = status.features || [];
    if (!features.length) {
      box.innerHTML = '<p class="hint">Ma’lumot kelmadi.</p>';
      return;
    }
    let html = features
      .map(
        (f) => `
      <div class="camera-row">
        <span class="dot ${f.active ? "on" : "off"}"></span>
        <div class="meta">
          <b>${esc(f.name)}</b>
          <code>${f.active ? "ishlayapti" : esc(f.reason || "sozlanmagan")}</code>
        </div>
      </div>`,
      )
      .join("");
    // Tarif filtri hodisalarni tashlayotgan bo'lsa — bu alohida, jiddiy
    // ogohlantirish: qurilma ishlayapti, lekin hisobot cloudga bormayapti.
    if (status.plan_filtered) {
      html += `<div class="note warn" style="margin-top:10px"><b>Diqqat:</b> ${Number(
        status.plan_filtered,
      )} ta hodisa tarif faollashtirilmagani uchun cloudga yuborilmadi. Administrator bilan bog‘laning.</div>`;
    }
    box.innerHTML = html;
  }

  /* ── Hisobot ─────────────────────────────────────────────────────────── */

  function drawReport(report) {
    $("reportDate").textContent = report.date;
    $("entered").textContent = report.entered;
    $("exited").textContent = report.exited;
    $("inside").textContent = `Hozir ichkarida ~${report.inside_estimate} kishi`;
    $("alertCount").textContent = report.alert_count;

    if (report.busiest_hour) {
      $("busiest").textContent = String(report.busiest_hour.hour).padStart(2, "0") + ":00";
      $("busiestCount").textContent = `${report.busiest_hour.entered} kishi kirdi`;
    } else {
      $("busiest").textContent = "—";
      $("busiestCount").textContent = "Hali kirish qayd etilmadi";
    }

    const peak = Math.max(1, ...report.hourly.map((item) => item.entered));
    $("hourly").innerHTML = report.hourly
      .map((item) => {
        const isPeak = report.busiest_hour && item.hour === report.busiest_hour.hour && item.entered;
        const height = Math.round((item.entered / peak) * 100);
        return `<div class="${isPeak ? "peak" : ""}" title="${String(item.hour).padStart(2, "0")}:00 — ${item.entered} kishi">
          <i style="height:${height}%"></i><b>${item.hour % 3 === 0 ? item.hour : ""}</b>
        </div>`;
      })
      .join("");
  }

  function drawEvents(events) {
    $("eventRows").innerHTML = events.length
      ? events
          .map((event) => {
            const when = new Date(event.occurred_at);
            const detail = [
              event.zone,
              event.direction === "in" ? "kirdi" : event.direction === "out" ? "chiqdi" : "",
              event.queue_length ? `${event.queue_length} kishi navbatda` : "",
            ]
              .filter(Boolean)
              .join(" · ");
            return `<tr>
              <td>${isNaN(when) ? esc(event.occurred_at) : esc(when.toLocaleString())}</td>
              <td>${esc(event.camera_id)}</td>
              <td>${esc(EVENT_LABELS[event.event_type] || event.event_type)}</td>
              <td>${esc(detail || "—")}</td>
            </tr>`;
          })
          .join("")
      : '<tr><td colspan="4"><span class="hint">Hozircha hodisa yo‘q. Birinchi mijoz kirganda shu yerda paydo bo‘ladi.</span></td></tr>';
  }

  /* ── Boshqaruv ───────────────────────────────────────────────────────── */

  /* Ulanish kartasi — sahifadagi asosiy javob.
   *
   * Uch holat, uchtasi ham aniq: ulangan (panelga o'ting), ulanmagan
   * (havola va tekshiruv kodi), internet yo'q (nazorat DAVOM ETADI).
   * Oxirgisi ataylab alohida: mijoz internet uzilganda kamera ham
   * o'chgan deb o'ylardi va zanjirni qo'lda to'xtatib qo'yardi.
   */
  function drawConnect(cloud) {
    const card = $("connectCard");
    if (!card) return;
    const title = $("connectTitle");
    const text = $("connectText");
    const actions = $("connectActions");
    const eyebrow = $("connectEyebrow");
    const verify = $("verifyBlock");

    card.classList.remove("linked", "offline");
    verify.hidden = true;
    actions.innerHTML = "";

    if (cloud.connected) {
      const panel = cloud.panel_url || cloud.owner_url || "";
      card.classList.add("linked");
      eyebrow.textContent = "Bulutga ulangan";
      title.textContent = "Boshqaruv panelingiz tayyor";
      text.textContent =
        "To‘liq hisobot, kamera sozlamalari va Telegram xabarlari — hammasi " +
        "panelda. Uni telefondan ham ochsangiz bo‘ladi.";
      if (panel) {
        actions.innerHTML =
          `<a class="button primary" href="${esc(panel)}" target="_blank" rel="noopener noreferrer">` +
          "Boshqaruv panelini ochish</a>";
      }
    } else if (cloud.connect_url) {
      eyebrow.textContent = "Bir qadam qoldi";
      title.textContent = "Bu kompyuterni hisobingizga ulang";
      text.textContent =
        "Ulash sahifasini oching va quyidagi kod ekrandagi kod bilan bir xil " +
        "ekaniga ishonch hosil qiling.";
      $("verifyCode").textContent = cloud.verify_code || "——————";
      verify.hidden = !cloud.verify_code;
      actions.innerHTML =
        `<a class="button primary" href="${esc(cloud.connect_url)}" target="_blank" rel="noopener noreferrer">` +
        "Ulash sahifasini ochish</a>";
    } else {
      // Havola yo'q — demak bulut bilan aloqa yo'q.  Eng muhim gap
      // birinchi jumlada: nazorat ishlayapti.
      card.classList.add("offline");
      eyebrow.textContent = "Internet yo‘q";
      title.textContent = "Nazorat ishlashda davom etmoqda";
      text.textContent =
        "Kameralar kuzatilmoqda va hodisalar shu kompyuterda saqlanmoqda. " +
        "Internet tiklangach ular o‘zi bulutga jo‘naydi.";
      actions.innerHTML =
        '<a class="button ghost" href="/setup">Usta rejimi — qo‘lda ulash</a>';
    }
  }

  function drawCloud(cloud) {
    const version = $("appVersion");
    if (version && cloud.app_version) version.textContent = "v" + cloud.app_version;
    cloudPanel.url = cloud.connected ? cloud.panel_url || cloud.owner_url || "" : "";
    drawConnect(cloud);
    $("connectCard").hidden = false;
    drawCloudWarnings(cloud);
  }

  /* Diagnostika — faqat AYTADIGAN gap bo'lganda ko'rinadi.
   *
   * Ilgari bu yerda "Cloudga ulangan" degan doimiy yozuv turardi va
   * ogohlantirish uning dumiga yopishtirilardi — ya'ni "2730 hodisa
   * yo'qoldi" yashil yozuv ichida ko'rinmay ketardi. */
  function drawCloudWarnings(cloud) {
    const bar = $("cloudBar");
    if (!bar) return;
    const parts = [];

    // Navbat o'sib borsa "ulangan" yozuvi yolg'on bo'lib qoladi — aloqa
    // uzilgan bo'lsa hodisalar to'planaveradi.
    const pending = Number(cloud.pending_events || 0);
    if (cloud.connected && pending > 20) {
      parts.push(`${pending} hodisa yuborilmagan — internetni tekshiring`);
    }
    // Tashlangan hodisa — YO'QOLGAN hodisa.  Soni ham, sababi ham
    // ko'rinsin: sababsiz raqamni tuzatib bo'lmaydi.
    const poisoned = Number(cloud.poisoned_events || 0);
    if (poisoned) {
      const why = (cloud.poisoned_reasons || [])[0];
      parts.push(`${poisoned} hodisa yo‘qoldi${why ? ` (${esc(why)})` : ""}`);
    }
    // Sozlama masofadan kelgan bo'lsa buni aytish kerak: mijoz kamerani
    // shu yerdan o'zgartirmoqchi bo'lsa, o'zgarishi keyingi sinxronda
    // qaytib ketishini bilishi lozim.
    if (cloud.remote_config) {
      parts.push("Kameralar bulutdan boshqariladi — bu yerdagi o‘zgarish qaytib ketadi");
    }

    bar.hidden = parts.length === 0;
    bar.className = poisoned || pending > 20 ? "note warn" : "note";
    bar.innerHTML = parts.map((line) => `<span>${line}</span>`).join("<br>");
  }

  async function refresh() {
    try {
      const [status, report, events, cameraList, cloud] = await Promise.all([
        api("/api/status"),
        api("/api/report"),
        api("/api/events?limit=50"),
        api("/api/setup/cameras"),
        api("/api/setup/cloud-status"),
      ]);
      // Bulut BIRINCHI: `drawStatus` dagi "sozlashni davom ettirish"
      // havolasi ulangan bo'lsa bulut paneliga ketishi kerak, ya'ni u
      // `cloudPanel.url` to'lgan bo'lishini kutadi.
      drawCloud(cloud);
      // `cameras_list` endi `/api/status` ning o'zida bor; `/api/setup/cameras`
      // esa qo'shimcha (manzil, format) beradi — nomlar ikkalasida bir xil.
      drawStatus({ ...status, cameras_list: cameraList.cameras || status.cameras_list });
      drawReport(report);
      drawEvents(events.events);
    } catch (error) {
      banner("err", "Dastur bilan aloqa yo‘q.", error.message);
    }
  }

  async function control(path, button) {
    button.disabled = true;
    try {
      await api(path, { method: "POST" });
      await refresh();
    } catch (error) {
      banner("err", "Buyruq bajarilmadi.", error.message);
    } finally {
      button.disabled = false;
    }
  }

  $("startBtn").addEventListener("click", (e) => control("/api/service/start", e.currentTarget));
  $("restartBtn").addEventListener("click", (e) => control("/api/service/restart", e.currentTarget));
  $("stopBtn").addEventListener("click", (e) => {
    if (!confirm("Nazorat to‘xtatilsinmi? Do‘konda hech narsa qayd etilmaydi.")) return;
    control("/api/service/stop", e.currentTarget);
  });

  $("logBtn").addEventListener("click", async () => {
    const box = $("logBox");
    if (!box.classList.contains("hidden")) {
      box.classList.add("hidden");
      return;
    }
    try {
      const data = await api("/api/service/log");
      box.textContent = data.lines.length
        ? data.lines.join("\n")
        : "Jurnal hali bo‘sh — xizmat bir marta ham ishga tushmagan.";
      box.classList.remove("hidden");
      box.scrollTop = box.scrollHeight;
    } catch (error) {
      banner("err", "Jurnal o‘qilmadi.", error.message);
    }
  });

  refresh();
  // Har 20 soniyada yangilanadi: bundan tez-tez qilish do'kon kompyuterini
  // bekorga band qiladi, sekinroq qilsa kamera uzilgani kech ko'rinadi.
  setInterval(refresh, 20000);
})();
