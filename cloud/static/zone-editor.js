/* Chiziq va zona chizish vositasi.
 *
 * Nega kerak: `scene.lines` va `scene.zones` har bir profilda bo'sh, va ularni
 * kiritishning yagona yo'li owner panelidagi "Texnik line/zone sozlamalari"
 * yopiq bo'limidagi xom JSON maydoni edi — normallashtirilgan 0..1
 * koordinatalar bilan. Amalda buni na do'kon egasi, na o'rnatuvchi to'ldirardi,
 * ya'ni `line_crossed`, `dwell_exceeded` va `queue_threshold_exceeded`
 * hech qachon chiqmasdi. Sotiladigan uchta funksiyadan ikkitasi shu sababdan
 * ishlamay turardi.
 *
 * Chiqish formati o'zgarmadi: aynan `SceneLineSettings` va
 * `SceneZoneSettings` (0..1 koordinatalar), shuning uchun cloud validatsiyasi
 * va edge tomonidagi o'qish qismi tegilmadi.
 *
 * Freymvorksiz: bu sahifalar build qadamisiz, bitta fayl bo'lib turadi.
 */
(function (global) {
  "use strict";

  var MIN_POLYGON = 3;
  var HIT_RADIUS = 10; // px — nuqtani "ushlash" masofasi

  function clamp01(value) {
    return Math.max(0, Math.min(1, value));
  }

  function round3(value) {
    return Math.round(value * 1000) / 1000;
  }

  /* Zona rangi nomi bo'yicha barqaror bo'lsin: sahifa qayta yuklanganda
   * zonalar rangini almashtirib yubormasin. */
  function colorFor(name) {
    var hash = 0;
    for (var i = 0; i < name.length; i += 1) {
      hash = (hash * 31 + name.charCodeAt(i)) % 360;
    }
    return hash;
  }

  function ZoneEditor(canvas, options) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.options = options || {};
    this.image = null;
    this.cameraId = "";
    this.mode = "zone"; // zone | line
    this.zones = [];
    this.lines = [];
    this.draft = []; // tugallanmagan poligon yoki chiziq nuqtalari
    this.dragging = null;
    this.onChange = this.options.onChange || function () {};

    canvas.addEventListener("click", this._click.bind(this));
    canvas.addEventListener("dblclick", this._finish.bind(this));
    canvas.addEventListener("contextmenu", this._remove.bind(this));
    canvas.addEventListener("mousedown", this._grab.bind(this));
    canvas.addEventListener("mousemove", this._move.bind(this));
    canvas.addEventListener("mouseup", this._drop.bind(this));
    canvas.addEventListener("mouseleave", this._drop.bind(this));
  }

  /* ── Holat ─────────────────────────────────────────────────────────── */

  ZoneEditor.prototype.load = function (config, cameraId) {
    this.cameraId = cameraId;
    this.zones = (config.zones || []).map(function (zone) {
      return {
        name: zone.name,
        camera_id: zone.camera_id,
        polygon: (zone.polygon || []).map(function (point) {
          return [Number(point[0]), Number(point[1])];
        }),
        restricted: !!zone.restricted,
        queue: !!zone.queue,
        dwell_sec: zone.dwell_sec == null ? null : Number(zone.dwell_sec),
      };
    });
    this.lines = (config.lines || []).map(function (line) {
      return {
        name: line.name,
        camera_id: line.camera_id,
        start: [Number(line.start[0]), Number(line.start[1])],
        end: [Number(line.end[0]), Number(line.end[1])],
        swap_direction: !!line.swap_direction,
      };
    });
    this.draft = [];
    this.draw();
  };

  ZoneEditor.prototype.setImage = function (image) {
    this.image = image;
    this.draw();
  };

  ZoneEditor.prototype.setCamera = function (cameraId) {
    this.cameraId = cameraId;
    this.draft = [];
    this.draw();
  };

  ZoneEditor.prototype.setMode = function (mode) {
    this.mode = mode === "line" ? "line" : "zone";
    this.draft = [];
    this.draw();
  };

  /* Faqat shu kameraga tegishlilari — boshqa kameraning chizig'i bu kadr
   * ustida ma'nosiz bo'lardi. */
  ZoneEditor.prototype.visibleZones = function () {
    var cameraId = this.cameraId;
    return this.zones.filter(function (zone) {
      return zone.camera_id === cameraId;
    });
  };

  ZoneEditor.prototype.visibleLines = function () {
    var cameraId = this.cameraId;
    return this.lines.filter(function (line) {
      return line.camera_id === cameraId;
    });
  };

  ZoneEditor.prototype.value = function () {
    return { zones: this.zones, lines: this.lines };
  };

  /* ── Sichqoncha ────────────────────────────────────────────────────── */

  ZoneEditor.prototype._point = function (event) {
    var box = this.canvas.getBoundingClientRect();
    return [
      clamp01((event.clientX - box.left) / box.width),
      clamp01((event.clientY - box.top) / box.height),
    ];
  };

  ZoneEditor.prototype._click = function (event) {
    if (this.dragging || !this.cameraId) return;
    if (this.movedWhileDown) {
      this.movedWhileDown = false;
      return;
    }
    var point = this._point(event);
    if (this.mode === "line") {
      this.draft.push(point);
      if (this.draft.length === 2) {
        this._commitLine();
      }
    } else {
      this.draft.push(point);
    }
    this.draw();
  };

  ZoneEditor.prototype._finish = function (event) {
    event.preventDefault();
    if (this.mode === "zone" && this.draft.length >= MIN_POLYGON) {
      this._commitZone();
    }
    this.draw();
  };

  ZoneEditor.prototype._commitLine = function () {
    var name = this.options.askName
      ? this.options.askName("Chiziq nomi", "kirish")
      : "kirish";
    if (!name) {
      this.draft = [];
      return;
    }
    this.lines.push({
      name: String(name).slice(0, 60),
      camera_id: this.cameraId,
      start: this.draft[0],
      end: this.draft[1],
      swap_direction: false,
    });
    this.draft = [];
    this.onChange();
  };

  ZoneEditor.prototype._commitZone = function () {
    var name = this.options.askName ? this.options.askName("Zona nomi", "kassa") : "zona";
    if (!name) {
      this.draft = [];
      return;
    }
    this.zones.push({
      name: String(name).slice(0, 60),
      camera_id: this.cameraId,
      polygon: this.draft.slice(),
      restricted: false,
      queue: false,
      dwell_sec: null,
    });
    this.draft = [];
    this.onChange();
  };

  /* O'ng tugma — eng yaqin shaklni o'chiradi. */
  ZoneEditor.prototype._remove = function (event) {
    event.preventDefault();
    if (this.draft.length) {
      this.draft.pop();
      this.draw();
      return;
    }
    var hit = this._hit(this._point(event));
    if (!hit) return;
    var list = hit.kind === "zone" ? this.zones : this.lines;
    var label = hit.kind === "zone" ? "Zona" : "Chiziq";
    var confirmed = this.options.confirm
      ? this.options.confirm(label + ' "' + list[hit.index].name + '" o‘chirilsinmi?')
      : true;
    if (!confirmed) return;
    list.splice(hit.index, 1);
    this.onChange();
    this.draw();
  };

  ZoneEditor.prototype._grab = function (event) {
    this.movedWhileDown = false;
    var hit = this._hitVertex(this._point(event));
    if (hit) {
      this.dragging = hit;
      event.preventDefault();
    }
  };

  ZoneEditor.prototype._move = function (event) {
    if (!this.dragging) return;
    this.movedWhileDown = true;
    var point = this._point(event);
    var target = this.dragging;
    if (target.kind === "zone") {
      this.zones[target.index].polygon[target.vertex] = point;
    } else if (target.vertex === 0) {
      this.lines[target.index].start = point;
    } else {
      this.lines[target.index].end = point;
    }
    this.draw();
  };

  ZoneEditor.prototype._drop = function () {
    if (!this.dragging) return;
    this.dragging = null;
    this.onChange();
  };

  /* ── Urish testi ───────────────────────────────────────────────────── */

  ZoneEditor.prototype._near = function (a, b) {
    var box = this.canvas.getBoundingClientRect();
    var dx = (a[0] - b[0]) * box.width;
    var dy = (a[1] - b[1]) * box.height;
    return Math.sqrt(dx * dx + dy * dy) <= HIT_RADIUS;
  };

  ZoneEditor.prototype._hitVertex = function (point) {
    var self = this;
    var found = null;
    this.zones.forEach(function (zone, index) {
      if (zone.camera_id !== self.cameraId || found) return;
      zone.polygon.forEach(function (vertex, order) {
        if (!found && self._near(point, vertex)) {
          found = { kind: "zone", index: index, vertex: order };
        }
      });
    });
    this.lines.forEach(function (line, index) {
      if (line.camera_id !== self.cameraId || found) return;
      if (self._near(point, line.start)) found = { kind: "line", index: index, vertex: 0 };
      else if (self._near(point, line.end)) found = { kind: "line", index: index, vertex: 1 };
    });
    return found;
  };

  ZoneEditor.prototype._hit = function (point) {
    var vertex = this._hitVertex(point);
    if (vertex) return vertex;
    var self = this;
    var found = null;
    this.zones.forEach(function (zone, index) {
      if (zone.camera_id === self.cameraId && !found && inside(point, zone.polygon)) {
        found = { kind: "zone", index: index };
      }
    });
    return found;
  };

  /* Ray casting — nuqta poligon ichidami. */
  function inside(point, polygon) {
    var result = false;
    for (var i = 0, j = polygon.length - 1; i < polygon.length; j = i, i += 1) {
      var a = polygon[i];
      var b = polygon[j];
      if (
        a[1] > point[1] !== b[1] > point[1] &&
        point[0] < ((b[0] - a[0]) * (point[1] - a[1])) / (b[1] - a[1]) + a[0]
      ) {
        result = !result;
      }
    }
    return result;
  }

  /* ── Chizish ───────────────────────────────────────────────────────── */

  ZoneEditor.prototype.draw = function () {
    var canvas = this.canvas;
    var ctx = this.ctx;
    var width = canvas.width;
    var height = canvas.height;
    ctx.clearRect(0, 0, width, height);
    if (this.image) {
      ctx.drawImage(this.image, 0, 0, width, height);
    } else {
      ctx.fillStyle = "#111820";
      ctx.fillRect(0, 0, width, height);
      ctx.fillStyle = "#8a9382";
      ctx.font = "14px sans-serif";
      ctx.fillText("Avval “Rasmni ko‘rish” tugmasini bosing", 16, 28);
    }

    var self = this;
    this.visibleZones().forEach(function (zone) {
      var hue = colorFor(zone.name);
      ctx.beginPath();
      zone.polygon.forEach(function (point, index) {
        var x = point[0] * width;
        var y = point[1] * height;
        if (index === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.closePath();
      ctx.fillStyle = "hsla(" + hue + ",70%,50%,0.25)";
      ctx.strokeStyle = "hsl(" + hue + ",70%,55%)";
      ctx.lineWidth = 2;
      ctx.fill();
      ctx.stroke();
      zone.polygon.forEach(function (point) {
        self._dot(point, "hsl(" + hue + ",70%,55%)");
      });
      var first = zone.polygon[0];
      if (first) {
        var badge = zone.name;
        if (zone.restricted) badge += " · taqiqlangan";
        if (zone.queue) badge += " · navbat";
        if (zone.dwell_sec) badge += " · " + zone.dwell_sec + "s";
        self._label(badge, first[0] * width, first[1] * height - 8);
      }
    });

    this.visibleLines().forEach(function (line) {
      self._line(line, width, height);
    });

    // Tugallanmagan shakl — punktir bilan.
    if (this.draft.length) {
      ctx.save();
      ctx.setLineDash([6, 4]);
      ctx.strokeStyle = "#d8f14a";
      ctx.lineWidth = 2;
      ctx.beginPath();
      this.draft.forEach(function (point, index) {
        var x = point[0] * width;
        var y = point[1] * height;
        if (index === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();
      ctx.restore();
      this.draft.forEach(function (point) {
        self._dot(point, "#d8f14a");
      });
    }
  };

  ZoneEditor.prototype._dot = function (point, color) {
    var ctx = this.ctx;
    ctx.beginPath();
    ctx.arc(point[0] * this.canvas.width, point[1] * this.canvas.height, 5, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.strokeStyle = "#111820";
    ctx.lineWidth = 1;
    ctx.stroke();
  };

  ZoneEditor.prototype._label = function (text, x, y) {
    var ctx = this.ctx;
    ctx.font = "12px sans-serif";
    var width = ctx.measureText(text).width + 10;
    ctx.fillStyle = "rgba(17,24,32,0.85)";
    ctx.fillRect(x - 4, y - 14, width, 18);
    ctx.fillStyle = "#f4f7f1";
    ctx.fillText(text, x + 1, y - 1);
  };

  /* Chiziq + "ichkari" tomonini ko'rsatuvchi o'q.
   *
   * `SceneLineSettings` shartnomasi: start->end yo'nalishining **chap**
   * tomoni ichkari. `swap_direction` uni teskarisiga o'giradi. O'q aynan
   * shuni ko'rsatadi, aks holda o'rnatuvchi chiziqni teskari chizib qo'yadi
   * va kirish/chiqish o'rin almashadi. */
  ZoneEditor.prototype._line = function (line, width, height) {
    var ctx = this.ctx;
    var x1 = line.start[0] * width;
    var y1 = line.start[1] * height;
    var x2 = line.end[0] * width;
    var y2 = line.end[1] * height;

    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.strokeStyle = "#4fc3f7";
    ctx.lineWidth = 3;
    ctx.stroke();

    var midX = (x1 + x2) / 2;
    var midY = (y1 + y2) / 2;
    var dx = x2 - x1;
    var dy = y2 - y1;
    var length = Math.sqrt(dx * dx + dy * dy) || 1;
    // Chap tomon normali; swap_direction bo'lsa teskari.
    var sign = line.swap_direction ? -1 : 1;
    var nx = (dy / length) * sign;
    var ny = (-dx / length) * sign;
    var tipX = midX + nx * 34;
    var tipY = midY + ny * 34;

    ctx.beginPath();
    ctx.moveTo(midX, midY);
    ctx.lineTo(tipX, tipY);
    ctx.strokeStyle = "#96c11f";
    ctx.lineWidth = 3;
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(tipX, tipY, 5, 0, Math.PI * 2);
    ctx.fillStyle = "#96c11f";
    ctx.fill();

    this._label(line.name + " → ichkari", x1, y1 - 8);
    this._dot(line.start, "#4fc3f7");
    this._dot(line.end, "#4fc3f7");
  };

  /* Saqlashdan oldin koordinatalarni qisqartiramiz: uch xona 640 px kadrda
   * yarim pikseldan aniq va JSON ancha kichik bo'ladi. */
  ZoneEditor.prototype.serialise = function () {
    return {
      zones: this.zones.map(function (zone) {
        return {
          name: zone.name,
          camera_id: zone.camera_id,
          polygon: zone.polygon.map(function (point) {
            return [round3(point[0]), round3(point[1])];
          }),
          restricted: !!zone.restricted,
          queue: !!zone.queue,
          dwell_sec: zone.dwell_sec || null,
        };
      }),
      lines: this.lines.map(function (line) {
        return {
          name: line.name,
          camera_id: line.camera_id,
          start: [round3(line.start[0]), round3(line.start[1])],
          end: [round3(line.end[0]), round3(line.end[1])],
          swap_direction: !!line.swap_direction,
        };
      }),
    };
  };

  global.ZoneEditor = ZoneEditor;
  global.ZoneEditor.inside = inside;
})(window);
