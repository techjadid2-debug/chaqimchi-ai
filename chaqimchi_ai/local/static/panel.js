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

  function drawStatus(status) {
    const dot = $("serviceDot");
    const text = $("serviceText");

    if (!status.ready) {
      dot.className = "dot off";
      text.textContent = "Sozlanmagan";
      banner("warn", "Sozlash tugallanmagan.", "Kamera qo‘shing va kirish chizig‘ini chizing.", {
        href: "/setup",
        text: "Sozlashni davom ettirish →",
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

    const configured = status.cameras || {};
    const names = new Map((status.cameras_list || []).map((c) => [c.camera_id, c.label]));
    const rows = Object.keys(configured);
    $("cameraStatus").innerHTML = rows.length
      ? rows
          .map((id) => {
            const item = configured[id] || {};
            const online = item.connected && !item.offline;
            return `
        <div class="camera-row">
          <span class="dot ${online ? "on" : "off"}"></span>
          <div class="meta">
            <b>${esc(names.get(id) || id)}</b>
            <code>${online ? "tasvir kelmoqda" : "javob bermayapti"}</code>
          </div>
        </div>`;
          })
          .join("")
      : '<p class="hint">Kameralar holati hali kelmadi. Xizmat ishga tushgach bir daqiqada paydo bo‘ladi.</p>';
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

  function drawCloud(cloud) {
    const bar = $("cloudBar");
    if (!cloud.connected) {
      bar.innerHTML =
        "<b>Faqat shu kompyuterda</b>Hisobot va hodisalar shu yerda saqlanadi. " +
        'Mijoz o‘z telefonidan ko‘rishi va Telegram xabarlari uchun ' +
        '<a href="/setup">cloudga ulang</a>.';
      return;
    }
    // Navbat o'sib borsa "ulangan" yozuvi yolg'on bo'lib qoladi — aloqa
    // uzilgan bo'lsa hodisalar to'planaveradi.
    const pending = cloud.pending_events;
    const queue =
      pending > 20
        ? ` · <b>${pending} hodisa yuborilmagan</b> — internetni tekshiring`
        : "";
    // Sozlama masofadan kelgan bo'lsa buni aytish kerak: mijoz kamerani
    // shu yerdan o'zgartirmoqchi bo'lsa, o'zgarishi keyingi sinxronda
    // qaytib ketishini bilishi lozim.
    const source = cloud.remote_config
      ? " · <b>Kameralar cloud’dan boshqariladi</b>"
      : "";
    bar.innerHTML =
      `<b>Cloudga ulangan</b>Mijoz paneli: <a href="${esc(cloud.owner_url)}" target="_blank" rel="noopener noreferrer">${esc(cloud.owner_url)}</a>${queue}${source}`;
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
      drawStatus({ ...status, cameras_list: cameraList.cameras });
      drawReport(report);
      drawEvents(events.events);
      drawCloud(cloud);
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
