// The 2D pipeline graph of the Workflow page (index.html loads it with a dynamic import).
// mount(el, {onPick}) draws Api.flow()'s nodes and edges as one static SVG and returns {update(flow), dispose()}.
// Stage columns run left to right; every node is coloured by the collector's state, every edge by the state of its ends.
// No animation loop: the page only redraws when a poll brings new data (the 3D view cost the Pi ~1.8 cores).

const SVGNS = "http://www.w3.org/2000/svg";
const COLOR = { ok: "#3ecf8e", warn: "#f5a524", fail: "#f0556a", idle: "#6b7280", stopped: "#4b5563" };
const ACCENT = "#5b8cff", EDGE_IDLE = "#3a4049", NODE_BG = "#13171c", NODE_LINE = "#2a313a", TEXT = "#e6e8eb", MUTED = "#8b949e";
const NW = 150, NH = 30, COL = 200, SUB = 165, ROW = 42, SPLIT = 8, PAD = 24, HEAD = 34, MAXCH = 19;

const colorOf = s => COLOR[s] || COLOR.idle;
const edgeKey = e => e.from + ">" + e.to;
const short = s => (s.length > MAXCH ? s.slice(0, MAXCH - 1) + "…" : s);

function svg(tag, attrs, parent) {
  const n = document.createElementNS(SVGNS, tag);
  for (const k in attrs) n.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(n);
  return n;
}

// Column x for each stage (a stage bigger than SPLIT takes two sub-columns), and each node's top-left corner.
export function layout(nodes, stageCount) {
  const byStage = new Map();
  nodes.forEach(n => { if (!byStage.has(n.stage)) byStage.set(n.stage, []); byStage.get(n.stage).push(n); });
  const stages = Math.max(stageCount || 0, ...nodes.map(n => n.stage + 1), 0);
  const colX = [], cols = [];
  let x = PAD, tallest = 0;
  for (let s = 0; s < stages; s++) {
    const list = byStage.get(s) || [];
    const sub = list.length > SPLIT ? 2 : 1;
    colX.push(x);
    cols.push({ list, sub, per: Math.ceil(list.length / sub) || 0 });
    tallest = Math.max(tallest, Math.ceil(list.length / sub));
    x += COL + (sub - 1) * SUB;
  }
  const height = HEAD + Math.max(tallest, 1) * ROW + PAD;
  const pos = new Map();
  cols.forEach((c, s) => c.list.forEach((n, i) => {
    const r = Math.floor(i / c.per), k = i % c.per, m = Math.min(c.per, c.list.length - r * c.per);
    const top = HEAD + (tallest - m) * ROW / 2 + k * ROW;   // each column centred on the tallest one
    pos.set(n.id, { x: colX[s] + r * SUB, y: top });
  }));
  return { pos, colX, width: x - COL + NW + PAD, height };
}

export function mount(el, opts = {}) {
  if (getComputedStyle(el).position === "static") el.style.position = "relative";
  const root = svg("svg", { width: "100%", height: "100%", preserveAspectRatio: "xMidYMid meet", role: "img", "aria-label": "Workflow" });
  el.appendChild(root);
  let nodes = new Map(), shape = "", selected = null, disposed = false;
  root.addEventListener("click", ev => {
    if (ev.target !== root) return;   // a click on empty space clears the selection
    selected = null; paintSelection();
    if (opts.onPick) opts.onPick(null);
  });

  function paintNode(r, n) {
    r.node = n;
    r.dot.setAttribute("fill", colorOf(n.state));
    r.name.textContent = short(n.label);
    r.tip.textContent = [n.label, n.state, n.detail].filter(Boolean).join(" · ");
    r.box.setAttribute("stroke", n.state === "fail" ? COLOR.fail : NODE_LINE);
  }
  function paintSelection() {
    nodes.forEach((r, id) => {
      r.sel.setAttribute("visibility", id === selected ? "visible" : "hidden");
    });
  }
  function edgePath(a, b) {
    if (a.x === b.x) {   // both ends in one column: a loop out to the right side instead of a line through the boxes
      const x = a.x + NW, y1 = a.y + NH / 2, y2 = b.y + NH / 2, out = x + 18 + Math.min(Math.abs(y2 - y1) / 6, 22);
      return `M${x},${y1} C${out},${y1} ${out},${y2} ${x},${y2}`;
    }
    const x1 = a.x + NW, y1 = a.y + NH / 2, x2 = b.x, y2 = b.y + NH / 2, mx = (x1 + x2) / 2;
    return `M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`;
  }
  function edgeStyle(p, state) {
    p.setAttribute("stroke", state === "fail" ? COLOR.fail : state === "ok" ? ACCENT : EDGE_IDLE);
    p.setAttribute("stroke-opacity", state === "ok" ? "0.6" : "1");
    if (state === "fail") p.setAttribute("stroke-dasharray", "6 4"); else p.removeAttribute("stroke-dasharray");
  }

  function build(flow) {
    root.textContent = "";
    nodes = new Map();
    const list = flow.nodes || [], stages = flow.stages || [];
    const L = layout(list, stages.length);
    root.setAttribute("viewBox", `0 0 ${L.width} ${L.height}`);
    stages.forEach((title, i) => {
      if (L.colX[i] === undefined) return;
      const t = svg("text", { x: L.colX[i], y: 18, fill: MUTED, "font-size": 11, "letter-spacing": "0.08em" }, root);
      t.textContent = title.toUpperCase();
    });
    const edgeLayer = svg("g", { fill: "none", "stroke-width": 1.6 }, root);
    const nodeLayer = svg("g", {}, root);
    list.forEach(n => {
      const p = L.pos.get(n.id);
      const g = svg("g", { transform: `translate(${p.x},${p.y})`, cursor: "pointer" }, nodeLayer);
      const tip = svg("title", {}, g);
      const sel = svg("rect", { x: -3, y: -3, width: NW + 6, height: NH + 6, rx: 8, fill: "none", stroke: ACCENT, "stroke-width": 2, visibility: "hidden" }, g);
      const box = svg("rect", { width: NW, height: NH, rx: 6, fill: NODE_BG, "stroke-width": 1 }, g);
      const dot = svg("circle", { cx: 13, cy: NH / 2, r: 4 }, g);
      const name = svg("text", { x: 24, y: NH / 2 + 4, fill: TEXT, "font-size": 12 }, g);
      g.addEventListener("click", () => {
        selected = selected === n.id ? null : n.id;
        paintSelection();
        if (opts.onPick) opts.onPick(selected ? nodes.get(selected).node : null);
      });
      const r = { node: n, g, tip, sel, box, dot, name, pos: p };
      paintNode(r, n);
      nodes.set(n.id, r);
    });
    (flow.edges || []).forEach(e => {
      const a = nodes.get(e.from), b = nodes.get(e.to);
      if (!a || !b) return;
      const path = svg("path", { d: edgePath(a.pos, b.pos), "data-edge": edgeKey(e) }, edgeLayer);
      edgeStyle(path, e.state);
    });
    if (selected && !nodes.has(selected)) selected = null;
    paintSelection();
  }

  function shapeOf(flow) {
    return (flow.nodes || []).map(n => n.id + "@" + n.stage).join("|") + "#" + (flow.edges || []).map(edgeKey).join("|") + "#" + (flow.stages || []).join("|");
  }

  // Same nodes and edges as last time: only recolour and retext. Otherwise rebuild.
  function update(flow) {
    if (disposed || !flow) return;
    const sh = shapeOf(flow);
    if (sh !== shape) { shape = sh; build(flow); return; }
    (flow.nodes || []).forEach(n => { const r = nodes.get(n.id); if (r) paintNode(r, n); });
    (flow.edges || []).forEach(e => {
      const p = root.querySelector(`path[data-edge="${CSS.escape(edgeKey(e))}"]`);
      if (p) edgeStyle(p, e.state);
    });
  }
  function dispose() {
    if (disposed) return;
    disposed = true;
    root.remove();
    nodes = new Map();
  }
  return { update, dispose };
}
