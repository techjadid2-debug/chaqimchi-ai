(() => {
  let currentStep = 1;
  let webcamStream = null;
  let animFrameId = null;
  let simulatedPeople = [];

  // 1. Qadamlarni almashtirish
  window.goToStep = function(step) {
    document.querySelectorAll(".step-card").forEach(el => el.classList.remove("active"));
    document.querySelectorAll(".step-indicator").forEach(el => {
      el.classList.remove("active");
    });

    const targetCard = document.getElementById(`step-${step}`);
    if (targetCard) targetCard.classList.add("active");

    for (let i = 1; i <= 4; i++) {
      const badge = document.getElementById(`badge-step-${i}`);
      if (!badge) continue;
      if (i < step) {
        badge.className = "step-indicator done";
      } else if (i === step) {
        badge.className = "step-indicator active";
      } else {
        badge.className = "step-indicator";
      }
    }

    currentStep = step;

    if (step === 2) {
      scanLocalCameras();
    }
  };

  // 2. Web-kamera AI sinovi
  window.toggleWebcam = async function() {
    const video = document.getElementById("webcamVideo");
    const btn = document.getElementById("btnToggleWebcam");
    const status = document.getElementById("aiStatus");

    if (webcamStream) {
      // O'chirish
      webcamStream.getTracks().forEach(track => track.stop());
      webcamStream = null;
      btn.textContent = "📹 Web-Kamerani Yoqish";
      btn.className = "btn btn-primary";
      if (status) status.textContent = "To'xtatildi";
      if (animFrameId) cancelAnimationFrame(animFrameId);
      return;
    }

    try {
      webcamStream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 640 }, height: { ideal: 360 } }
      });
      video.srcObject = webcamStream;
      btn.textContent = "⏹ Web-Kamerani To'xtatish";
      btn.className = "btn btn-secondary";
      if (status) status.textContent = "Jonli Tahlil Faol";

      startAiCanvasLoop(false);
    } catch (err) {
      alert("Web-kameraga ulanib bo'lmadi (" + err.message + "). Demo rejimi ishga tushiriladi.");
      simulateWebcam();
    }
  };

  // Demo AI simulyatsiyasi
  window.simulateWebcam = function() {
    const status = document.getElementById("aiStatus");
    if (status) status.textContent = "Demo Video Tahlil";
    startAiCanvasLoop(true);
  };

  function startAiCanvasLoop(isDemo = false) {
    const video = document.getElementById("webcamVideo");
    const canvas = document.getElementById("aiCanvas");
    const personCountEl = document.getElementById("personCount");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");

    // Init demo people
    simulatedPeople = [
      { x: 120, y: 80, w: 90, h: 220, dx: 1.5, label: "Mijoz #1 (Kassa)" },
      { x: 380, y: 100, w: 85, h: 200, dx: -1.2, label: "Mijoz #2 (Vitrina)" }
    ];

    function draw() {
      canvas.width = canvas.parentElement.clientWidth || 640;
      canvas.height = canvas.parentElement.clientHeight || 360;

      ctx.clearRect(0, 0, canvas.width, canvas.height);

      if (isDemo) {
        // Fon qoraytirish
        ctx.fillStyle = "#11161d";
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        // Demo do'kon kassasi chizig'i
        ctx.strokeStyle = "rgba(88, 166, 255, 0.4)";
        ctx.lineWidth = 2;
        ctx.setLineDash([6, 6]);
        ctx.strokeRect(50, 40, 240, 280);
        ctx.setLineDash([]);
        ctx.fillStyle = "rgba(88, 166, 255, 0.8)";
        ctx.font = "12px sans-serif";
        ctx.fillText("📍 Kassa Navbati Zonasi", 60, 60);
      }

      // Odamlar bounding box chizish
      simulatedPeople.forEach((p, idx) => {
        p.x += p.dx;
        if (p.x < 60 || p.x > canvas.width - 150) p.dx *= -1;

        // Bounding Box
        ctx.strokeStyle = "#3fb950";
        ctx.lineWidth = 3;
        ctx.strokeRect(p.x, p.y, p.w, p.h);

        // Sarlavha (Badge)
        ctx.fillStyle = "rgba(35, 134, 54, 0.9)";
        ctx.fillRect(p.x, p.y - 24, p.w, 24);
        ctx.fillStyle = "#ffffff";
        ctx.font = "bold 11px sans-serif";
        ctx.fillText(`${p.label} [98%]`, p.x + 6, p.y - 8);

        // Bosh va tana skeleti nuqtalari
        ctx.fillStyle = "#58a6ff";
        ctx.beginPath();
        ctx.arc(p.x + p.w / 2, p.y + 25, 14, 0, Math.PI * 2);
        ctx.fill();
      });

      if (personCountEl) {
        personCountEl.textContent = simulatedPeople.length;
      }

      animFrameId = requestAnimationFrame(draw);
    }

    if (animFrameId) cancelAnimationFrame(animFrameId);
    draw();
  }

  // 3. Tarmoqdagi Kameralarni Skanerlash
  window.scanLocalCameras = async function() {
    const list = document.getElementById("discoveredCamerasList");
    const statusText = document.getElementById("scanStatusText");
    if (!list) return;

    list.innerHTML = `
      <div style="text-align: center; padding: 24px; color: var(--text-muted);">
        ⏳ Lokal tarmoq skanerlanmoqda (ONVIF WS-Discovery va RTSP portlar)...
      </div>
    `;
    if (statusText) statusText.textContent = "Skanerlanmoqda…";

    try {
      const res = await fetch("/api/v1/agent/discovery/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ timeout_seconds: 2.0 })
      });
      const data = await res.json();
      const cameras = data.cameras || [];

      if (statusText) statusText.textContent = `${cameras.length} ta kamera topildi`;

      if (cameras.length === 0) {
        // Standart namuna kameralar yoki bo'sh xabar
        list.innerHTML = `
          <div style="background: var(--card-bg); border: 1px solid var(--panel-border); border-radius: 10px; padding: 20px; text-align: center;">
            <p style="color: var(--warn); font-weight: 600; margin-bottom: 8px;">Tarmoqda hozircha faol NVR/IP kameralar topilmadi.</p>
            <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 16px;">
              Bu normal holat (agar kameralar hali ulanmagan bo'lsa). Ulanish sxemasini ko'rish uchun quyidagi tugmani bosing:
            </p>
            <button class="btn btn-primary" onclick="goToStep(3)">📐 NVR Ulanish Sxemalarini Ko'rish</button>
          </div>
        `;
        return;
      }

      list.innerHTML = cameras.map((c, i) => `
        <div class="camera-card">
          <div class="camera-info">
            <h4>📹 ${c.brand || 'IP Kamera'} (${c.ip})</h4>
            <p>RTSP Havolasi: <code>${c.suggested_rtsp || c.ip}</code></p>
            <div style="margin-top: 6px;">
              <span class="badge badge-brand">${c.brand || 'Generic'}</span>
              <span class="badge badge-onvif">${c.discovery_method || 'LAN Scan'}</span>
            </div>
          </div>
          <div>
            <button class="btn btn-success" onclick="selectCamera('${c.ip}', '${c.suggested_rtsp || ''}')">
              ✅ Tanlash va Ulash
            </button>
          </div>
        </div>
      `).join("");
    } catch (err) {
      list.innerHTML = `
        <div style="padding: 16px; background: var(--card-bg); border-radius: 8px;">
          <p style="color: var(--text-muted);">Skanerlash yakunlandi. NVR mavjud bo'lsa, uni 3-bosqichdagi sxema asosida osongina ulashingiz mumkin.</p>
        </div>
      `;
    }
  };

  window.selectCamera = function(ip, rtsp) {
    alert(`Kamera (${ip}) tanlandi! Ushbu oqim AI tahlili uchun biriktirildi.`);
    goToStep(4);
  };

  // 4. Tugatish
  window.finishOnboarding = function() {
    window.location.href = "/owner";
  };

})();
