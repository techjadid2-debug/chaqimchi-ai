/* «ENES Edu» sahifasining mantiqi (test, progress, bo'limlar).
 *
 * Inline `<script>` dan chiqarildi: CSP `script-src` da
 * `'unsafe-inline'` yo'q. */
(function () {
  "use strict";

  /* Narxlar SERVERDAN keladi (`/api/v1/public/edu-pricing` →
     `enes/licensing/edu.py`).  Ular shu yerga yozilsa,
     narx o'zgarganda sahifa eskisini ko'rsatib turaverardi va buni
     hech kim sezmasdi. */
  var data = null;
  var state = { kind: "maktab", people: 355, cameras: null, modules: ["faceid"], branches: 0 };

  function $(id) { return document.getElementById(id); }
  function esc(value) {
    return String(value).replace(/[&<>"']/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
    });
  }
  function money(value) {
    return String(Math.round(value)).replace(/\B(?=(\d{3})+(?!\d))/g, " ") + " so‘m";
  }

  /* ── Serverdagi funksiyalarning aynan nusxasi ──────────────────
     Bu yerdagi mantiq `edu.py` bilan bir xil bo'lishi shart.
     Raqamlar esa nusxalanmaydi — ular `data` dan olinadi. */

  function personFee(people) {
    var remaining = Math.max(0, people), previous = 0, total = 0;
    for (var i = 0; i < data.person_bands.length; i++) {
      var band = data.person_bands[i];
      if (band.up_to === null) { total += Math.max(0, remaining - previous) * band.uzs; break; }
      var counted = Math.min(Math.max(0, remaining - previous), band.up_to - previous);
      total += counted * band.uzs;
      previous = band.up_to;
      if (remaining <= band.up_to) break;
    }
    return total;
  }

  function estimateCameras(people, kind) {
    for (var i = 0; i < data.camera_table.length; i++) {
      var row = data.camera_table[i];
      if (row.up_to === null || people <= row.up_to) return row[kind];
    }
    return data.camera_table[data.camera_table.length - 1][kind];
  }

  function moduleCameras(cameras, code) {
    if (code === "faceid") return cameras ? Math.max(1, Math.floor(cameras / 8)) : 0;
    if (code === "monitoring" || code === "deep" || code === "fight") return Math.floor(cameras / 4);
    return 0;
  }

  function moduleById(code) {
    for (var i = 0; i < data.modules.length; i++) {
      if (data.modules[i].code === code) return data.modules[i];
    }
    return null;
  }

  /* Chuqur tahlil oddiy monitoring O'RNIGA ishlaydi — ikkalasi
     birga hisoblanmaydi, aks holda mijoz bir ish uchun ikki marta
     to'lardi. */
  function chosenModules() {
    var picked = state.modules.slice();
    if (picked.indexOf("deep") >= 0) {
      picked = picked.filter(function (code) { return code !== data.deep_replaces; });
    }
    return picked;
  }

  function computeLoad(cameras, modules) {
    var total = cameras;
    modules.forEach(function (code) {
      var mod = moduleById(code);
      if (!mod || !mod.load) return;
      total += mod.load * moduleCameras(cameras, code);
    });
    return Math.round(total * 100) / 100;
  }

  function edgeForLoad(load) {
    for (var i = 0; i < data.edge_catalog.length; i++) {
      if (load <= data.edge_catalog[i].max_load) return data.edge_catalog[i];
    }
    return null;
  }

  function compute() {
    var picked = chosenModules();
    var cameras = Math.max(data.included.cameras, state.cameras || 0);
    var rows = [];
    var institution = null;
    for (var i = 0; i < data.institutions.length; i++) {
      if (data.institutions[i].code === state.kind) institution = data.institutions[i];
    }
    rows.push({ label: institution.name + " — bazaviy obuna", uzs: institution.base_uzs });

    var people = personFee(state.people);
    if (people) {
      rows.push({
        label: Math.max(0, state.people - data.included.people) + " kishi (bosqichli)",
        uzs: people
      });
    }

    var extra = Math.max(0, cameras - data.included.cameras);
    if (extra) rows.push({ label: extra + " ta qo‘shimcha AI kamera", uzs: extra * data.extra_camera_uzs });

    picked.forEach(function (code) {
      if (code === "branch") return;
      var mod = moduleById(code);
      if (mod) rows.push({ label: mod.name, uzs: mod.uzs });
    });

    var branchMod = moduleById("branch");
    if (state.branches > 0 && branchMod) {
      rows.push({ label: state.branches + " ta qo‘shimcha filial", uzs: state.branches * branchMod.uzs });
    }

    var raw = rows.reduce(function (sum, row) { return sum + row.uzs; }, 0);
    var step = data.round_to_uzs;
    var load = computeLoad(cameras, picked);
    return {
      rows: rows,
      total: Math.ceil(raw / step) * step,
      load: load,
      edge: edgeForLoad(load),
      cameras: cameras,
      institution: institution.name,
      modules: picked
    };
  }

  /* ── Chizish ──────────────────────────────────────────────── */

  function drawPickers() {
    $("kindPick").innerHTML = data.institutions.map(function (item) {
      return '<button type="button" data-kind="' + esc(item.code) + '" aria-pressed="' +
        (item.code === state.kind) + '">' + esc(item.name) + "</button>";
    }).join("");

    var sellable = data.modules.map(function (mod) {
      var on = state.modules.indexOf(mod.code) >= 0;
      return '<label class="edu-mod"><input type="checkbox" data-mod="' + esc(mod.code) + '"' +
        (on ? " checked" : "") + '><span>' + esc(mod.name) + "</span><b>" +
        money(mod.uzs) + "/oy</b></label>";
    });
    // Rejadagilar narxsiz va checkbox'siz chiziladi: narx ko'rsatilgan
    // zahoti sotuvchi ham, mijoz ham buni tayyor xizmat deb tushunadi.
    var planned = (data.planned_modules || []).map(function (mod) {
      return '<div class="edu-mod edu-mod-planned"><span>' + esc(mod.name) +
        "</span><b>rejada</b></div>";
    });
    $("modPick").innerHTML = sellable.concat(planned).join("");
  }

  function draw() {
    var result = compute();

    $("total").textContent = money(result.total);
    $("totalNote").textContent = result.institution + " · " + state.people +
      " kishi · " + result.cameras + " ta AI kamera";

    $("rows").innerHTML = result.rows.map(function (row) {
      return '<div class="edu-row"><span>' + esc(row.label) + "</span><b>" + money(row.uzs) + "</b></div>";
    }).join("");

    var own = $("ownPc").checked;
    if (own) {
      $("edgeName").textContent = "Qurilma kerak emas — 0 so‘m";
      $("edgeSpec").textContent = "Mavjud kompyuteringiz ishlatiladi. Uning quvvati yetishini o‘rnatishdan oldin bepul tekshiramiz.";
      $("edgePrice").textContent = "";
    } else if (result.edge) {
      $("edgeName").textContent = "Tavsiya: " + result.edge.name;
      $("edgeSpec").textContent = result.edge.spec;
      $("edgePrice").textContent = "Bir martalik mo‘ljal narx: " + money(result.edge.price_uzs) +
        " (oylik obunaga kirmaydi).";
    } else {
      $("edgeName").textContent = "Bir nechta qurilma kerak";
      $("edgePrice").textContent = "";
      $("edgeSpec").textContent = "Hisoblash yuki bitta qurilma imkoniyatidan yuqori — " +
        "taqsimlangan yechim tuzamiz. Bog‘laning.";
    }

    $("cameraCount").value = String(result.cameras);
    $("eduMessage").value = "EDU | " + result.institution + " | " + state.people +
      " kishi | " + result.cameras + " kamera | " +
      (result.modules.length ? result.modules.join("+") : "modulsiz") +
      " | ~" + result.total + " so'm/oy | yuklama " + result.load +
      " | Edge: " + (own ? "o'z kompyuteri" : (result.edge ? result.edge.name : "bir nechta"));
  }

  function syncCameraEstimate() {
    var estimate = estimateCameras(state.people, state.kind);
    state.cameras = estimate;
    $("cameras").value = String(estimate);
    $("cameraHint").textContent = "Taxmin: " + estimate +
      " ta. Aniq bilsangiz o‘zgartiring — bu muassasadagi barcha kameralar emas, " +
      "faqat AI tahlil qiladiganlari.";
  }

  /* ── Hodisalar ────────────────────────────────────────────── */

  function bind() {
    $("kindPick").addEventListener("click", function (event) {
      var button = event.target.closest("button[data-kind]");
      if (!button) return;
      state.kind = button.getAttribute("data-kind");
      drawPickers();
      syncCameraEstimate();
      draw();
    });

    $("modPick").addEventListener("change", function (event) {
      var box = event.target.closest("input[data-mod]");
      if (!box) return;
      var code = box.getAttribute("data-mod");
      if (box.checked) {
        if (state.modules.indexOf(code) < 0) state.modules.push(code);
        // Chuqur tahlil va oddiy monitoring bir-birini almashtiradi.
        if (code === "deep") state.modules = state.modules.filter(function (item) { return item !== data.deep_replaces; });
        if (code === data.deep_replaces) state.modules = state.modules.filter(function (item) { return item !== "deep"; });
      } else {
        state.modules = state.modules.filter(function (item) { return item !== code; });
      }
      drawPickers();
      draw();
    });

    $("people").addEventListener("input", function () {
      state.people = Math.max(0, parseInt(this.value, 10) || 0);
      syncCameraEstimate();
      draw();
    });

    $("cameras").addEventListener("input", function () {
      state.cameras = Math.max(0, parseInt(this.value, 10) || 0);
      draw();
    });

    $("branches").addEventListener("input", function () {
      state.branches = Math.max(0, parseInt(this.value, 10) || 0);
      draw();
    });

    $("ownPc").addEventListener("change", draw);
  }

  /* ── Ariza ────────────────────────────────────────────────── */

  function bindForm() {
    var form = $("eduForm");
    if (!form) return;
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var status = $("eduStatus");
      var button = form.querySelector("button[type=submit]");
      var body = {};
      new FormData(form).forEach(function (value, key) { body[key] = value; });
      body.consent = true;
      body.cameras = parseInt(body.cameras, 10) || 4;

      status.className = "form-status";
      status.textContent = "Yuborilmoqda…";
      button.disabled = true;

      fetch("/api/v1/public/leads", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      }).then(function (response) {
        return response.json().then(function (payload) { return { ok: response.ok, payload: payload }; });
      }).then(function (result) {
        if (!result.ok) throw new Error(result.payload.detail || "Yuborilmadi");
        status.className = "form-status ok";
        status.textContent = "Qabul qilindi. Tez orada bog‘lanamiz.";
        form.reset();
      }).catch(function (error) {
        status.className = "form-status err";
        status.textContent = error.message + " Telegram: @fibotai";
      }).then(function () {
        button.disabled = false;
      });
    });
  }

  fetch("/api/v1/public/edu-pricing").then(function (response) {
    return response.json();
  }).then(function (payload) {
    data = payload;
    drawPickers();
    syncCameraEstimate();
    bind();
    draw();
  }).catch(function () {
    $("totalNote").textContent = "Narxlar yuklanmadi. Sahifani yangilang yoki @fibotai ga yozing.";
  });

  bindForm();
})();
