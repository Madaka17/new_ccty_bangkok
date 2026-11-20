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
.chart svg { display: block; }
.chart-head {
  display: flex; flex-wrap: wrap; gap: 8px 12px; align-items: center; justify-content: space-between;
  margin: 0 0 8px;
}
.chart-summary { margin: 0; font-size: 14px; color: var(--text-2); font-variant-numeric: tabular-nums; }
.seg { display: inline-flex; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
.seg button {
  font: inherit; font-size: 14px; background: var(--surface); color: var(--text-2);
  border: 0; padding: 6px 14px; min-width: 64px; cursor: pointer;
}
.seg button + button { border-left: 1px solid var(--border); }
.seg button[aria-pressed="true"] { background: var(--series-1); color: var(--bg); }
.seg button:focus-visible { outline: 2px solid var(--series-1); outline-offset: -2px; }
.bucket-details { margin-top: 10px; font-size: 14px; }
.bucket-details summary { cursor: pointer; color: var(--text-2); padding: 4px 0; }
.bucket-table { min-width: 0; }
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

<h2>กราฟ 1 ชั่วโมงล่าสุด (จุดละ 5 นาที)</h2>
<div class="chart-head">
  <p class="chart-summary" id="chartSummary"></p>
  <div class="seg" role="group" aria-label="เลือกว่าจะดูเป็นจำนวนครั้งหรือ token">
    <button type="button" id="mCalls" aria-pressed="true">ครั้ง</button>
    <button type="button" id="mTokens" aria-pressed="false">token</button>
  </div>
</div>
<div class="chart" id="chart">
  <svg id="chartSvg" viewBox="0 0 960 240" role="img" aria-label="กราฟการใช้งาน 1 ชั่วโมงล่าสุด จุดละ 5 นาที"></svg>
  <div class="tip" id="tip" hidden></div>
</div>
<details class="bucket-details">
  <summary>ดูเป็นตาราง</summary>
  <div class="table-wrap">
    <table class="bucket-table">
      <thead><tr><th>ช่วงเวลา</th><th class="num">ครั้ง</th><th class="num">token</th></tr></thead>
      <tbody id="bucketRows"></tbody>
    </table>
  </div>
</details>

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

  // The chart shows 12 buckets of 5 minutes. The metric is calls ("ครั้ง") or tokens,
  // chosen with the toggle and remembered in localStorage when the browser allows it.
  var METRIC_KEY = "bionicChartMetric";
  var metric = readMetric();
  var lastChart = null;

  function readMetric() {
    try {
      return localStorage.getItem(METRIC_KEY) === "tokens" ? "tokens" : "calls";
    } catch (err) {
      return "calls";
    }
  }

  function saveMetric(value) {
    try {
      localStorage.setItem(METRIC_KEY, value);
    } catch (err) {
      // storage blocked (private window): the choice lasts until the page reloads
    }
  }

  function shortNum(value) {
    function trim(x) { return String(Math.round(x * 10) / 10); }
    if (value >= 1000000) return trim(value / 1000000) + "M";
    if (value >= 1000) return trim(value / 1000) + "k";
    return nf.format(Math.round(value));
  }

  function unitText() { return metric === "tokens" ? "token" : "ครั้ง"; }
  function shortVal(value) { return metric === "tokens" ? shortNum(value) : num(value); }
  function bucketStart(chart, i) { return chart.start + i * chart.bucket_minutes * 60; }

  function bucketRange(chart, i) {
    var a = bucketStart(chart, i), b = a + chart.bucket_minutes * 60;
    return fmtMin.format(new Date(a * 1000)) + "–" + fmtMin.format(new Date(b * 1000));
  }

  function applyMetricButtons() {
    $("mCalls").setAttribute("aria-pressed", metric === "calls" ? "true" : "false");
    $("mTokens").setAttribute("aria-pressed", metric === "tokens" ? "true" : "false");
  }

  function setMetric(value) {
    metric = value;
    saveMetric(value);
    applyMetricButtons();
    $("tip").hidden = true;
    if (lastChart) drawChart(lastChart);
  }

  function setSummary(chart, data) {
    var box = $("chartSummary");
    if (data.total <= 0) {
      box.textContent = "ยังไม่มีการใช้งานใน 1 ชม. ล่าสุด";
      return;
    }
    var text = "1 ชม. ล่าสุด: " + num(data.total) + " " + unitText() +
      " · เฉลี่ย " + num(data.average) + " " + unitText() + "/" + chart.bucket_minutes + " นาที";
    if (data.peak_index != null) {
      text += " · สูงสุด " + num(data.peak) + " (" + bucketRange(chart, data.peak_index) + ")";
    }
    box.textContent = text;
  }

  function renderBucketTable(chart) {
    var body = $("bucketRows");
    body.textContent = "";
    for (var i = 0; i < chart.count; i++) {
      var tr = document.createElement("tr");
      var label = bucketRange(chart, i) + (i === chart.count - 1 ? " (กำลังเก็บ)" : "");
      var cells = [label, num(chart.calls.values[i]), num(chart.tokens.values[i])];
      for (var c = 0; c < cells.length; c++) {
        var td = document.createElement("td");
        td.textContent = cells[c];
        if (c > 0) td.className = "num";
        tr.appendChild(td);
      }
      body.appendChild(tr);
    }
  }

  // ---- chart: one line over 12 five-minute buckets (calls or tokens) ----
  // The SVG is drawn at the container's own pixel width, so 1 SVG unit = 1 CSS px and the
  // text keeps the page's small size on any screen. It is redrawn on resize.
  var CHART_H = 240;
  var CHART_PAD_L = 52, CHART_PAD_R = 84, CHART_T = 32, CHART_B = 196;
  var SVG_NS = "http://www.w3.org/2000/svg";
  var geo = null;          // geometry of the last drawing, used by the hover code
  var hoverIndex = null;   // bucket under the pointer, or null
  var guideGroup = null;   // hover group (guide line and marker) inside the svg
  var guideLine = null;
  var guideDot = null;

  function svgEl(name, attrs, text) {
    var node = document.createElementNS(SVG_NS, name);
    Object.keys(attrs || {}).forEach(function (key) { node.setAttribute(key, String(attrs[key])); });
    if (text != null) node.textContent = text;
    return node;
  }

  function xOf(i) { return geo.L + (i + 0.5) * geo.slot; }
  function yOf(v) { return geo.B - (v / geo.top) * (geo.B - geo.T); }

  function chartWidth() {
    return Math.max(260, $("chart").clientWidth - 20); // minus the box padding
  }

  function drawChart(chart) {
    lastChart = chart;
    var data = chart[metric];
    var n = chart.count;
    var W = chartWidth(), H = CHART_H;
    var L = CHART_PAD_L, R = W - CHART_PAD_R, T = CHART_T, B = CHART_B;
    var slot = (R - L) / n;
    var top = data.axis_top, step = data.axis_step;
    geo = { W: W, L: L, R: R, T: T, B: B, slot: slot, top: top, n: n };

    var svg = $("chartSvg");
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    svg.setAttribute("width", String(W));
    svg.setAttribute("height", String(H));
    svg.textContent = "";

    svg.appendChild(svgEl("text", { x: L, y: 14, "font-size": 12, fill: "var(--text-2)" },
      metric === "tokens" ? "token ต่อ 5 นาที" : "ครั้ง ต่อ 5 นาที"));

    // solid hairline gridlines at each round step, with the value at the left
    var rows = Math.round(top / step);
    for (var k = 0; k <= rows; k++) {
      var gy = yOf(k * step);
      svg.appendChild(svgEl("line", { x1: L, x2: R, y1: gy, y2: gy, stroke: "var(--grid)", "stroke-width": 1 }));
      svg.appendChild(svgEl("text", { x: L - 8, y: gy + 4, "text-anchor": "end", "font-size": 12,
        fill: "var(--text-3)" }, shortVal(k * step)));
    }

    var pts = [];
    for (var i = 0; i < n; i++) pts.push({ x: xOf(i), y: yOf(data.values[i]) });
    var last = n - 1;

    // light area under the whole series
    var areaD = "M" + pts[0].x.toFixed(1) + "," + B;
    pts.forEach(function (p) { areaD += " L" + p.x.toFixed(1) + "," + p.y.toFixed(1); });
    areaD += " L" + pts[last].x.toFixed(1) + "," + B + " Z";
    svg.appendChild(svgEl("path", { d: areaD, fill: "var(--series-1)", "fill-opacity": 0.12,
      stroke: "none", "pointer-events": "none" }));

    // average: a thin muted dashed line, labelled in the right margin so no point is covered
    if (data.total > 0) {
      var ay = yOf(data.average);
      svg.appendChild(svgEl("line", { x1: L, x2: R, y1: ay, y2: ay, stroke: "var(--text-3)", "stroke-width": 1,
        "stroke-dasharray": "4 3", "pointer-events": "none" }));
      svg.appendChild(svgEl("text", { x: R + 6, y: ay + 4, "font-size": 12, fill: "var(--text-2)",
        "pointer-events": "none" }, "เฉลี่ย " + shortVal(data.average)));
    }

    // the series line: solid 2px through the complete buckets, dotted to the filling one
    var solid = "";
    for (var s = 0; s < last; s++) solid += (s === 0 ? "M" : " L") + pts[s].x.toFixed(1) + "," + pts[s].y.toFixed(1);
    if (solid) {
      svg.appendChild(svgEl("path", { d: solid, fill: "none", stroke: "var(--series-1)", "stroke-width": 2,
        "stroke-linejoin": "round", "stroke-linecap": "round", "pointer-events": "none" }));
    }
    if (last >= 1) {
      svg.appendChild(svgEl("line", { x1: pts[last - 1].x, y1: pts[last - 1].y, x2: pts[last].x, y2: pts[last].y,
        stroke: "var(--series-1)", "stroke-width": 2, "stroke-dasharray": "2 4", "stroke-linecap": "round",
        "pointer-events": "none" }));
    }
    for (var d = 0; d < n; d++) {
      if (d === last) {
        // the still-filling bucket: a hollow point
        svg.appendChild(svgEl("circle", { cx: pts[d].x, cy: pts[d].y, r: 4, fill: "var(--surface)",
          stroke: "var(--series-1)", "stroke-width": 2, "pointer-events": "none" }));
      } else {
        svg.appendChild(svgEl("circle", { cx: pts[d].x, cy: pts[d].y, r: 3.5, fill: "var(--series-1)",
          "pointer-events": "none" }));
      }
    }

    // time labels every 15 minutes (Bangkok time), at the start of the bucket
    for (var t = 0; t < n; t++) {
      var at = bucketStart(chart, t);
      if (at % 900 === 0) {
        svg.appendChild(svgEl("text", { x: L + t * slot, y: B + 16, "text-anchor": "middle", "font-size": 12,
          fill: "var(--text-3)", "pointer-events": "none" }, fmtMin.format(new Date(at * 1000))));
      }
    }
    svg.appendChild(svgEl("text", { x: R, y: B + 34, "text-anchor": "end", "font-size": 12, fill: "var(--text-2)",
      "pointer-events": "none" }, "ตอนนี้"));

    // hover guide, hidden until the pointer moves over the chart
    guideGroup = svgEl("g", { visibility: "hidden", "pointer-events": "none" });
    guideLine = svgEl("line", { x1: 0, x2: 0, y1: T, y2: B, stroke: "var(--text-3)", "stroke-width": 1 });
    guideDot = svgEl("circle", { cx: 0, cy: 0, r: 5, fill: "var(--series-1)", stroke: "var(--surface)",
      "stroke-width": 2 });
    guideGroup.appendChild(guideLine);
    guideGroup.appendChild(guideDot);
    svg.appendChild(guideGroup);

    setSummary(chart, data);
    renderBucketTable(chart);
    if (hoverIndex != null) showHover(hoverIndex);
  }

  function tipText(i) {
    var c = lastChart;
    var filling = i === c.count - 1;
    var label = bucketRange(c, i) + (filling ? " (กำลังเก็บ ยังไม่ครบ " + c.bucket_minutes + " นาที)" : "");
    return label + ": " + num(c[metric].values[i]) + " " + unitText();
  }

  function showTipAt(i, x, y) {
    var tip = $("tip"), box = $("chart");
    var svgRect = $("chartSvg").getBoundingClientRect(), boxRect = box.getBoundingClientRect();
    var left = svgRect.left - boxRect.left + x;
    tip.textContent = tipText(i);
    tip.hidden = false;
    var tx = left + 12;
    if (tx + tip.offsetWidth > box.clientWidth) tx = left - 12 - tip.offsetWidth;
    tip.style.left = Math.max(0, tx) + "px";
    tip.style.top = Math.max(0, svgRect.top - boxRect.top + y - 36) + "px";
  }

  function showHover(i) {
    if (!geo || !guideGroup) return;
    if (i == null) {
      guideGroup.setAttribute("visibility", "hidden");
      $("tip").hidden = true;
      return;
    }
    var x = xOf(i), y = yOf(lastChart[metric].values[i]);
    guideLine.setAttribute("x1", x);
    guideLine.setAttribute("x2", x);
    guideDot.setAttribute("cx", x);
    guideDot.setAttribute("cy", y);
    guideGroup.setAttribute("visibility", "visible");
    showTipAt(i, x, y);
  }

  // The bucket nearest the pointer (or the tap), from its x position in svg units.
  function nearestIndex(clientX) {
    var rect = $("chartSvg").getBoundingClientRect();
    var x = (clientX - rect.left) * (geo.W / rect.width);
    var i = Math.round((x - geo.L) / geo.slot - 0.5);
    return Math.max(0, Math.min(geo.n - 1, i));
  }

  function onPointer(evt) {
    if (!lastChart || !geo) return;
    hoverIndex = nearestIndex(evt.clientX);
    showHover(hoverIndex);
  }

  function onLeave() {
    hoverIndex = null;
    showHover(null);
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
      ["เว็บจริงบน Pi :8000",
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
    if (s.chart) drawChart(s.chart);
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

  $("chartSvg").addEventListener("pointermove", onPointer);
  $("chartSvg").addEventListener("pointerdown", onPointer);
  $("chartSvg").addEventListener("pointerleave", onLeave);
  if (typeof ResizeObserver === "function") {
    new ResizeObserver(function () { if (lastChart) drawChart(lastChart); }).observe($("chart"));
  } else {
    window.addEventListener("resize", function () { if (lastChart) drawChart(lastChart); });
  }
  $("mCalls").addEventListener("click", function () { setMetric("calls"); });
  $("mTokens").addEventListener("click", function () { setMetric("tokens"); });
  applyMetricButtons();
  setInterval(updateElapsed, 500);
  poll();
})();
</script>
</body>
</html>
"""
