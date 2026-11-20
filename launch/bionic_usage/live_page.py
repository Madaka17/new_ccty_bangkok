"""The live page served at / by live.py. Self-contained: inline CSS, JS and SVG.

The page polls /api/state every 2 seconds. The chart is an inline SVG redrawn on
each update. Colors are CSS custom properties on :root, with a dark set under
prefers-color-scheme and a data-theme override. Only one series is drawn, so the
bars use the single series blue and need no legend.
"""

PAGE_HTML = r"""<!doctype html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bionic สด</title>
<style>
:root {
  color-scheme: light;
  --bg: #fcfcfb;
  --surface: #ffffff;
  --text: #0b0b0b;
  --text-2: #52514e;
  --text-3: #7a7974;
  --border: #e4e3de;
  --grid: #e9e8e3;
  --series-1: #2a78d6;
  --ok: #1f7a4d;
  --error: #c4362f;
  --warn-bg: #fff4e5;
  --warn-text: #7a4a00;
  --flash: #e3eefb;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --bg: #1a1a19;
    --surface: #222220;
    --text: #f0efec;
    --text-2: #c3c2b7;
    --text-3: #98978e;
    --border: #35342f;
    --grid: #2d2c28;
    --series-1: #3987e5;
    --ok: #5cc68e;
    --error: #e66767;
    --warn-bg: #3a2c14;
    --warn-text: #f3c77a;
    --flash: #223246;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --bg: #1a1a19;
  --surface: #222220;
  --text: #f0efec;
  --text-2: #c3c2b7;
  --text-3: #98978e;
  --border: #35342f;
  --grid: #2d2c28;
  --series-1: #3987e5;
  --ok: #5cc68e;
  --error: #e66767;
  --warn-bg: #3a2c14;
  --warn-text: #f3c77a;
  --flash: #223246;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 16px;
  background: var(--bg);
  color: var(--text);
  font-family: "Leelawadee UI", "Tahoma", "Segoe UI", sans-serif;
  font-size: 15px;
  line-height: 1.45;
}
h1 { font-size: 22px; margin: 4px 0 10px; }
h2 { font-size: 17px; margin: 22px 0 8px; }
.top { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; justify-content: space-between; }
.status {
  display: inline-flex; gap: 8px; align-items: center; flex-wrap: wrap;
  background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
  padding: 8px 12px; font-size: 14px;
}
.dot { width: 10px; height: 10px; border-radius: 50%; background: var(--text-3); display: inline-block; }
.dot.up { background: var(--ok); }
.dot.down { background: var(--error); }
.muted { color: var(--text-2); }
.banner {
  display: none; background: var(--warn-bg); color: var(--warn-text);
  border-radius: 8px; padding: 10px 12px; margin-top: 12px; font-size: 14px;
}
.banner.show { display: block; }
.card {
  background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px;
}
.tiles {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px;
}
.tile .label { color: var(--text-2); font-size: 14px; }
.tile .big { font-size: 26px; font-weight: 600; margin: 2px 0; font-variant-numeric: tabular-nums; }
.tile .small { color: var(--text-2); font-size: 13px; font-variant-numeric: tabular-nums; }
.tile .err { color: var(--error); font-size: 13px; }
.flight {
  display: grid; grid-template-columns: 1fr auto; gap: 4px 12px;
  padding: 8px 0; border-top: 1px solid var(--border);
}
.flight:first-child { border-top: none; padding-top: 0; }
.flight .who { font-weight: 600; overflow-wrap: anywhere; }
.flight .job { color: var(--text-2); font-size: 13px; overflow-wrap: anywhere; }
.flight .clock { font-variant-numeric: tabular-nums; font-size: 18px; text-align: right; }
.flight .stage { color: var(--text-2); font-size: 13px; text-align: right; }
.bar { grid-column: 1 / -1; height: 6px; background: var(--grid); border-radius: 3px; overflow: hidden; }
.bar > span { display: block; height: 100%; background: var(--series-1); border-radius: 3px; }
.chart { position: relative; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 10px; }
.chart svg { width: 100%; height: auto; display: block; }
.tip {
  position: absolute; pointer-events: none; background: var(--text); color: var(--bg);
  border-radius: 6px; padding: 4px 8px; font-size: 13px; white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.table-wrap {
  overflow-x: auto; background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
}
table { border-collapse: collapse; width: 100%; min-width: 640px; font-size: 14px; }
th, td { padding: 7px 10px; border-bottom: 1px solid var(--border); white-space: nowrap; text-align: left; }
th { color: var(--text-2); font-weight: 600; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
tr:last-child td { border-bottom: none; }
td.bad { color: var(--error); }
tr.row-new td { animation: flash 2.5s ease-out; }
@keyframes flash { from { background: var(--flash); } to { background: transparent; } }
@media (prefers-reduced-motion: reduce) { tr.row-new td { animation: none; } }
.hops { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.hop {
  flex: 1 1 150px; background: var(--surface); border: 1px solid var(--border);
  border-radius: 8px; padding: 8px 10px; min-width: 0;
}
.hop.ok { border-color: var(--ok); }
.hop.bad { border-color: var(--error); border-width: 2px; }
.hop.unknown { border-style: dashed; }
.hop .name { font-weight: 600; font-size: 14px; overflow-wrap: anywhere; }
.hop .st { font-size: 13px; color: var(--text-2); margin-top: 3px; overflow-wrap: anywhere; }
.arrow { color: var(--text-3); font-size: 18px; }
.tun-head { font-weight: 600; margin: 12px 0 4px; }
.tun-line { font-size: 14px; color: var(--text-2); margin: 3px 0; overflow-wrap: anywhere; }
.tun-log {
  font-family: Consolas, "Courier New", monospace; font-size: 12px; color: var(--text-2);
  background: var(--bg); border: 1px solid var(--border); border-radius: 6px;
  padding: 6px 8px; margin-top: 8px; white-space: pre-wrap; overflow-wrap: anywhere;
}
.footer { color: var(--text-3); font-size: 13px; margin: 18px 0 0; }
a { color: var(--series-1); }
</style>
</head>
<body>
<div class="top">
  <h1>การใช้งาน Bionic (สด)</h1>
  <div class="status" id="status" aria-live="polite">
    <span class="dot" id="dot"></span>
    <span id="statusText">กำลังตรวจสอบ</span>
    <span class="muted" id="loaded"></span>
  </div>
</div>
<div class="banner" id="banner" role="alert">ตัวดูสดหยุดทำงาน กำลังลองใหม่ทุก 2 วินาที</div>

<h2>ทางเชื่อม Pi → Bionic</h2>
<div class="card">
  <div class="tun-head" id="tunnelHead">กำลังโหลด...</div>
  <div class="hops" id="tunnelHops"></div>
  <div id="tunnelDetail"></div>
  <div class="tun-log" id="tunnelLog" aria-label="บรรทัดล่าสุดใน log"></div>
</div>

<h2>กำลังทำงานอยู่</h2>
<div class="card" id="flights"><p class="muted" style="margin:0">กำลังโหลด...</p></div>

<h2>สรุป</h2>
<div class="tiles" id="tiles"></div>

<h2>โทเคนต่อนาที (60 นาทีล่าสุด)</h2>
<div class="chart" id="chart">
  <svg id="chartSvg" viewBox="0 0 960 220" role="img" aria-label="กราฟโทเคนต่อนาที 60 นาทีล่าสุด"></svg>
  <div class="tip" id="tip" hidden></div>
</div>
<p class="muted" id="chartNote" style="font-size:13px;margin:6px 0 0"></p>

<h2>ล่าสุด 50 ครั้ง</h2>
<div class="table-wrap">
  <table>
    <thead><tr>
      <th>เวลา</th><th>โมเดล</th><th>งาน</th>
      <th class="num">รับ</th><th class="num">ตอบ</th><th class="num">เหตุผล</th>
      <th class="num">รวม</th><th class="num">ms</th><th>ผล</th>
    </tr></thead>
    <tbody id="rows"><tr><td colspan="9" class="muted">กำลังโหลด...</td></tr></tbody>
  </table>
</div>

<p class="footer" id="footer"></p>
<p class="footer"><a href="/report">ดูรายงานเต็ม</a></p>

<script>
(function () {
  "use strict";
  var POLL_MS = 2000;
  var nf = new Intl.NumberFormat("en-US");
  var tz = "Asia/Bangkok";
  var fmtFull = new Intl.DateTimeFormat("en-GB", { timeZone: tz, hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
  var fmtMin = new Intl.DateTimeFormat("en-GB", { timeZone: tz, hour: "2-digit", minute: "2-digit", hour12: false });
  var seenRows = null;      // keys of the rows shown on the previous update
  var flights = [];         // in-flight list from the last good poll
  var flightFetch = 0;      // performance.now() of the last good poll

  function $(id) { return document.getElementById(id); }

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[c];
    });
  }

  function num(value) {
    return value == null ? "-" : nf.format(Math.round(value));
  }

  function clock(unix) {
    return fmtFull.format(new Date(unix * 1000));
  }

  function secs(total) {
    var s = Math.max(0, Math.floor(total));
    var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
    var mm = (h > 0 ? String(m).padStart(2, "0") : String(m));
    var out = mm + ":" + String(r).padStart(2, "0");
    return h > 0 ? h + ":" + out : out;
  }

  function phaseText(f) {
    if (f.phase === "answering") return "กำลังตอบ";
    if (f.phase === "prompt") return "อ่านคำถาม " + Math.floor(f.percent) + "%";
    return "รอเริ่ม";
  }

  function renderStatus(bionic) {
    var dot = $("dot"), text = $("statusText"), loaded = $("loaded");
    if (bionic.up === true) {
      dot.className = "dot up";
      text.textContent = "Bionic ทำงานอยู่";
    } else if (bionic.up === false) {
      dot.className = "dot down";
      text.textContent = "Bionic ไม่ตอบ";
    } else {
      dot.className = "dot";
      text.textContent = "กำลังตรวจสอบ";
    }
    if (bionic.up === true && bionic.loaded && bionic.loaded.length) {
      loaded.textContent = "โหลดอยู่: " + bionic.loaded.join(", ");
    } else if (bionic.up === true) {
      loaded.textContent = "ยังไม่มีโมเดลที่โหลด";
    } else {
      loaded.textContent = "";
    }
  }

  function renderFlights(list) {
    var box = $("flights");
    if (!list.length) {
      box.innerHTML = '<p class="muted" style="margin:0">ตอนนี้ไม่มีคำขอ</p>';
      return;
    }
    box.innerHTML = list.map(function (f, i) {
      var bar = f.percent == null ? "" :
        '<div class="bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="' +
        Math.floor(f.percent) + '"><span style="width:' + Math.min(100, f.percent) + '%"></span></div>';
      return '<div class="flight">' +
        '<div><div class="who">' + esc(f.model) + '</div><div class="job">' + esc(f.job) + '</div></div>' +
        '<div><div class="clock" data-elapsed="' + Number(f.elapsed_s) + '" data-i="' + i + '">' + secs(f.elapsed_s) + '</div>' +
        '<div class="stage">' + esc(phaseText(f)) + '</div></div>' + bar + '</div>';
    }).join("");
  }

  function updateElapsed() {
    var extra = flightFetch ? (performance.now() - flightFetch) / 1000 : 0;
    var els = document.querySelectorAll("[data-elapsed]");
    for (var i = 0; i < els.length; i++) {
      els[i].textContent = secs(Number(els[i].getAttribute("data-elapsed")) + extra);
    }
  }

  function renderTiles(totals) {
    var rows = [["hour", "60 นาทีล่าสุด"], ["today", "วันนี้"], ["all", "ทั้งหมด"]];
    $("tiles").innerHTML = rows.map(function (r) {
      var t = totals[r[0]];
      return '<div class="card tile"><div class="label">' + r[1] + '</div>' +
        '<div class="big">' + num(t.calls) + ' ครั้ง</div>' +
        '<div class="small">โทเคน ' + num(t.tokens) + '</div>' +
        '<div class="small">รับ ' + num(t.prompt) + ' · ตอบ ' + num(t.completion) + '</div>' +
        '<div class="err">ผิดพลาด ' + num(t.errors) + '</div></div>';
    }).join("");
  }

  var chartNow = { per: [], start: 0 };

  function drawChart(perMinute, minuteStart) {
    var W = 960, L = 56, R = 944, T = 16, B = 190;
    var n = perMinute.length;
    var peak = Math.max.apply(null, perMinute.concat([0])) || 1;
    var plotH = B - T, slot = (R - L) / n, gap = 2, rMax = 4;
    var parts = [];
    [0, 0.5, 1].forEach(function (f) {
      var y = B - f * plotH;
      parts.push('<line x1="' + L + '" x2="' + R + '" y1="' + y.toFixed(1) + '" y2="' + y.toFixed(1) +
        '" stroke="var(--grid)" stroke-width="1"/>');
      parts.push('<text x="' + (L - 8) + '" y="' + (y + 4).toFixed(1) + '" text-anchor="end" font-size="12" ' +
        'fill="var(--text-3)">' + nf.format(Math.round(peak * f)) + '</text>');
    });
    for (var i = 0; i < n; i++) {
      var v = perMinute[i];
      var x0 = L + i * slot, w = slot - gap;
      if (v > 0) {
        var h = Math.max(1, v / peak * plotH);
        var r = Math.min(rMax, h / 2, w / 2);
        var left = x0 + gap / 2, right = left + w, top = B - h;
        var d = "M" + left.toFixed(1) + "," + B + " V" + (top + r).toFixed(1) +
          " Q" + left.toFixed(1) + "," + top.toFixed(1) + " " + (left + r).toFixed(1) + "," + top.toFixed(1) +
          " H" + (right - r).toFixed(1) +
          " Q" + right.toFixed(1) + "," + top.toFixed(1) + " " + right.toFixed(1) + "," + (top + r).toFixed(1) +
          " V" + B + " Z";
        parts.push('<path d="' + d + '" fill="var(--series-1)"/>');
      }
      // A transparent column over each minute is the hover target.
      parts.push('<rect data-i="' + i + '" x="' + x0.toFixed(1) + '" y="' + T + '" width="' + slot.toFixed(1) +
        '" height="' + plotH + '" fill="transparent"/>');
      if (i % 10 === 0) {
        var label = fmtMin.format(new Date((minuteStart + i * 60) * 1000));
        parts.push('<text x="' + (x0 + slot / 2).toFixed(1) + '" y="' + (B + 18) + '" text-anchor="middle" ' +
          'font-size="12" fill="var(--text-3)">' + label + '</text>');
      }
    }
    $("chartSvg").innerHTML = parts.join("");
    chartNow.per = perMinute;
    chartNow.start = minuteStart;
    var total = perMinute.reduce(function (a, b) { return a + b; }, 0);
    $("chartNote").textContent = total > 0 ? "รวม " + num(total) + " โทเคนใน 60 นาที" : "ยังไม่มีการใช้งานใน 60 นาทีนี้";
  }

  function showTip(evt) {
    var target = evt.target;
    var tip = $("tip");
    var box = $("chart");
    if (!target || target.tagName !== "rect" || target.getAttribute("data-i") == null) {
      tip.hidden = true;
      return;
    }
    var i = Number(target.getAttribute("data-i"));
    var when = fmtMin.format(new Date((chartNow.start + i * 60) * 1000));
    tip.textContent = when + ": " + num(chartNow.per[i]) + " โทเคน";
    tip.hidden = false;
    var rect = box.getBoundingClientRect();
    var x = evt.clientX - rect.left + 12;
    if (x > rect.width - 170) x = evt.clientX - rect.left - 170;
    tip.style.left = x + "px";
    tip.style.top = "12px";
  }

  function renderRows(rows) {
    var keys = {};
    var html = rows.map(function (r) {
      var key = r.ts + "|" + r.model + "|" + r.job + "|" + r.prompt + "|" + r.completion + "|" + r.reasoning;
      keys[key] = true;
      var isNew = seenRows !== null && !seenRows[key];
      var total = r.prompt + r.completion;
      return '<tr' + (isNew ? ' class="row-new"' : '') + '>' +
        '<td>' + clock(r.ts) + '</td>' +
        '<td>' + esc(r.model) + '</td>' +
        '<td>' + esc(r.job) + '</td>' +
        '<td class="num">' + num(r.prompt) + '</td>' +
        '<td class="num">' + num(r.completion) + '</td>' +
        '<td class="num">' + num(r.reasoning) + '</td>' +
        '<td class="num">' + num(total) + '</td>' +
        '<td class="num">' + num(r.total_ms) + '</td>' +
        (r.ok ? '<td>สำเร็จ</td>' : '<td class="bad">ผิดพลาด</td>') +
        '</tr>';
    });
    $("rows").innerHTML = html.length ? html.join("") :
      '<tr><td colspan="9" class="muted">ยังไม่มีรายการ</td></tr>';
    seenRows = keys;
  }

  function ago(seconds) {
    if (seconds == null) return "-";
    var s = Math.max(0, Math.round(seconds));
    return s < 60 ? s + " วินาทีก่อน" : Math.round(s / 60) + " นาทีก่อน";
  }

  function hop(name, state, detail) {
    var icon = state === "ok" ? "✓ ปกติ" : state === "bad" ? "! มีปัญหา" : "? ไม่ทราบ";
    return '<div class="hop ' + state + '"><div class="name">' + esc(name) + '</div>' +
      '<div class="st">' + esc(icon + " · " + detail) + '</div></div>';
  }

  // Draws the five hops of the path and the details. Text and icons carry the state,
  // so the colour is never the only signal. The log line is set with textContent only.
  function renderTunnel(t, now) {
    var head = $("tunnelHead"), hops = $("tunnelHops"), detail = $("tunnelDetail"), log = $("tunnelLog");
    if (!t || t.available === false) {
      head.textContent = "ทางเชื่อม Pi → Bionic: ใช้ไม่ได้ตอนนี้";
      hops.innerHTML = "";
      detail.innerHTML = '<div class="tun-line"></div>';
      detail.firstChild.textContent = (t && t.reason_th) || "";
      log.textContent = "";
      return;
    }
    var pi = t.pi;
    var piErr = pi ? (pi.errors_5min || 0) : null;
    var steps = [
      ["เทสบน Pi :8001",
        !pi ? "unknown" : (piErr > 0 ? "bad" : "ok"),
        !pi ? "ยังไม่เช็ก" : (piErr > 0 ? "error " + piErr + " ครั้งใน 5 นาที" : "ไม่มี error ใน 5 นาที")],
      ["Pi 127.0.0.1:1235",
        !pi || pi.http == null ? "unknown" : (pi.http === 200 ? "ok" : "bad"),
        !pi || pi.http == null ? "ไม่ทราบ" : (pi.http === 200 ? "ตอบ 200" : "ตอบ " + pi.http)],
      ["ทางเชื่อม SSH",
        t.link_up ? "ok" : "bad",
        t.link_up ? "ต่ออยู่" : "ไม่ต่อถึง Pi"],
      ["ssh.exe บน PC",
        t.ssh_pid ? "ok" : "bad",
        t.ssh_pid ? "ทำงานอยู่ (pid " + t.ssh_pid + ")" : "ไม่ได้รัน"],
      ["Bionic :1235",
        t.bionic_listening ? "ok" : "bad",
        t.bionic_listening ? "เปิดอยู่" : "ไม่ได้เปิด"]
    ];
    hops.innerHTML = steps.map(function (s, i) {
      return (i > 0 ? '<span class="arrow" aria-hidden="true">→</span>' : "") + hop(s[0], s[1], s[2]);
    }).join("");

    var stateText = t.state === "ok" ? "ปกติ" : t.state === "degraded" ? "มีปัญหาบางอย่าง" :
      t.state === "down" ? "ใช้งานไม่ได้" : "ยังไม่มีข้อมูล";
    head.textContent = stateText + " · " + (t.reason_th || "");

    var clients = (t.local_clients || []).map(function (c) {
      return c.name + " (" + c.conns + " การเชื่อมต่อ)";
    });
    var piText = !pi ? "ยังไม่เคยเช็ก" :
      (pi.error ? "เช็กไม่ได้ (" + pi.error + ")" :
        "HTTP " + pi.http + " · " + (pi.ms == null ? "-" : Math.round(pi.ms) + " ms") +
        " · error 5 นาที " + (pi.errors_5min == null ? "-" : pi.errors_5min) +
        " · เช็กเมื่อ " + ago(now - (pi.checked_ts || now)));
    var rows = [
      "การเชื่อมต่อจาก Pi ตอนนี้: " + num(t.pi_conns),
      "อย่างน้อย " + num(t.pi_seen_60s) + " ครั้งใน 60 วินาทีล่าสุด (นับต่ำกว่าจริงได้) · รวมตั้งแต่เปิด " + num(t.pi_seen_total),
      "โปรแกรมบน PC ที่เรียก Bionic ตรง: " + (clients.length ? clients.join(", ") : "ไม่มี"),
      "เช็ก Pi: " + piText
    ];
    if (t.local_error) rows.push("ตรวจทางเชื่อมบน PC ไม่ได้: " + t.local_error);
    detail.innerHTML = rows.map(function (r) { return '<div class="tun-line"></div>'; }).join("");
    var lines = detail.querySelectorAll(".tun-line");
    rows.forEach(function (r, i) { lines[i].textContent = r; });

    var tail = t.log_tail || [];
    log.textContent = tail.length ? tail[tail.length - 1] : "ยังไม่มีบรรทัดใน log ของทางเชื่อม";
  }

  function render(s) {
    renderStatus(s.bionic || {});
    try {
      renderTunnel(s.tunnel, s.now);
    } catch (err) {
      $("tunnelHead").textContent = "แสดงทางเชื่อมไม่ได้ในตอนนี้";
    }
    flights = s.in_flight || [];
    flightFetch = performance.now();
    renderFlights(flights);
    updateElapsed();
    renderTiles(s.totals);
    drawChart(s.per_minute, s.minute_start);
    renderRows(s.recent || []);
    var newest = s.newest_log_ts ? clock(s.newest_log_ts) : "-";
    var text = "อัปเดตล่าสุด " + clock(s.now) + " · ข้อมูลล่าสุดในบันทึก " + newest;
    if (s.db_error) text += " · อ่านฐานข้อมูลไม่ได้";
    $("footer").textContent = text;
  }

  function setBanner(show) {
    $("banner").className = show ? "banner show" : "banner";
  }

  var serverId = null;
  function poll() {
    fetch("/api/state", { cache: "no-store" })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (s) {
        // a restarted server (new code, or started again after its idle exit): load the page it serves now
        if (serverId && s.server_id && s.server_id !== serverId) {
          location.reload();
          return;
        }
        serverId = serverId || s.server_id;
        setBanner(false);
        render(s);
      })
      .catch(function () {
        setBanner(true);
      })
      .then(function () {
        setTimeout(poll, POLL_MS);
      });
  }

  $("chartSvg").addEventListener("pointermove", showTip);
  $("chartSvg").addEventListener("pointerdown", showTip);
  $("chartSvg").addEventListener("pointerleave", function () { $("tip").hidden = true; });
  setInterval(updateElapsed, 500);
  poll();
})();
</script>
</body>
</html>
"""
