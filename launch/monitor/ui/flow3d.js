// The 3D pipeline graph of the Workflow page (index.html loads it with a dynamic import).
// mount(el, {onPick}) draws Api.flow()'s nodes and edges with the vendored Three.js and returns {update(flow), dispose()}.
// Stage columns run along X; every node is coloured by the collector's state, every edge by the state of its ends.
import * as THREE from "three";
import { OrbitControls } from "three/addons/OrbitControls.js";
import { CSS2DRenderer, CSS2DObject } from "three/addons/CSS2DRenderer.js";

const COLOR = { ok: "#3ecf8e", warn: "#f5a524", fail: "#f0556a", idle: "#6b7280", stopped: "#4b5563" };
const ACCENT = "#5b8cff", EDGE_IDLE = "#3a4049", BG = "#0b0d10", GRID = "#1f242b";
const DX = 17, DY = 3.2, SUB_X = 4.6, SPLIT = 8;   // column spacing, node spacing, half gap of a split stage's two sub-columns, size at which a stage splits
const LOOP_S = 2.5, PULSE_S = 1.2, PARTS = 3;    // particle loop, fail pulse, particles per ok edge

const colorOf = s => COLOR[s] || COLOR.idle;
const edgeKey = e => e.from + ">" + e.to;

export function mount(el, opts = {}) {
  const reduce = !!(window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches);
  if (getComputedStyle(el).position === "static") el.style.position = "relative";

  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setClearColor(BG, 1);
  const labels = new CSS2DRenderer();
  for (const d of [renderer.domElement, labels.domElement]) { d.style.position = "absolute"; d.style.top = "0"; d.style.left = "0"; }
  el.appendChild(renderer.domElement);
  el.appendChild(labels.domElement);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(BG);
  const camera = new THREE.PerspectiveCamera(55, 1, 0.1, 400);
  camera.position.set(0, 9, 52);
  scene.add(new THREE.AmbientLight(0xffffff, 0.6));
  const sun = new THREE.DirectionalLight(0xffffff, 2.2);
  sun.position.set(10, 30, 25);
  scene.add(sun);

  const controls = new OrbitControls(camera, labels.domElement);   // the label layer is on top, so it takes the mouse
  controls.enableDamping = true;
  controls.autoRotate = !reduce;
  controls.autoRotateSpeed = 0.4;
  controls.addEventListener("start", () => { controls.autoRotate = false; });   // the first drag (or wheel) hands the view to the user

  // shared by every node and edge, disposed once in dispose()
  const boxGeo = new THREE.BoxGeometry(2.6, 1.1, 1.1);
  const outlineGeo = new THREE.EdgesGeometry(new THREE.BoxGeometry(2.9, 1.4, 1.4));
  const dotGeo = new THREE.SphereGeometry(0.16, 10, 8);
  const dotMat = new THREE.MeshBasicMaterial({ color: ACCENT });
  const outlineMat = new THREE.LineBasicMaterial({ color: "#e6e8eb" });
  const shared = new Set([boxGeo, outlineGeo, dotGeo, dotMat, outlineMat]);

  const world = new THREE.Group();   // everything that update() may rebuild
  scene.add(world);
  const raycaster = new THREE.Raycaster();

  let nodes = new Map();   // id -> {node, mesh, mat, outline, label, dot, name, det}
  let edges = new Map();   // "from>to" -> {state, obj, mat, parts, curve}
  let shape = "", selected = null, hovered = null, raf = 0, disposed = false, lastW = 0, lastH = 0;

  function free(root) {
    root.traverse(o => {
      if (o.isCSS2DObject) o.element.remove();
      if (o.geometry && !shared.has(o.geometry)) o.geometry.dispose();
      if (o.material && !shared.has(o.material)) o.material.dispose();
    });
  }
  function clear() {
    for (const c of [...world.children]) { world.remove(c); free(c); }
    nodes = new Map(); edges = new Map(); hovered = null;
  }

  /* ---------- nodes ---------- */
  function layout(list) {
    const pos = new Map(), byStage = new Map();
    list.forEach(n => { if (!byStage.has(n.stage)) byStage.set(n.stage, []); byStage.get(n.stage).push(n); });
    for (const [stage, col] of byStage) {
      const rows = col.length > SPLIT ? 2 : 1, per = Math.ceil(col.length / rows);
      col.forEach((n, i) => {
        const r = Math.floor(i / per), k = i % per, m = Math.min(per, col.length - r * per);
        // a big stage splits into two side-by-side sub-columns: rows behind each other hid their labels
        const y = ((m - 1) / 2 - k) * DY;
        pos.set(n.id, new THREE.Vector3((stage - 2) * DX + (rows === 1 ? 0 : (r ? SUB_X : -SUB_X)), y, 0));
      });
    }
    return pos;
  }
  function paintNode(r, n) {
    r.node = n;
    const c = colorOf(n.state);
    r.mat.color.set(c); r.mat.emissive.set(c);
    r.dot.className = "f3-dot " + (COLOR[n.state] ? n.state : "idle");
    r.name.textContent = n.label;
    r.det.textContent = [n.state, n.detail].filter(Boolean).join(" · ");
  }
  function addNode(n, p) {
    const mat = new THREE.MeshStandardMaterial({ roughness: 0.5, metalness: 0.1, emissiveIntensity: 0.25 });
    const mesh = new THREE.Mesh(boxGeo, mat);
    mesh.position.copy(p);
    const outline = new THREE.LineSegments(outlineGeo, outlineMat);
    outline.visible = false;
    mesh.add(outline);
    const div = document.createElement("div");
    div.className = "f3-lbl";
    const dot = document.createElement("span"), name = document.createElement("span"), det = document.createElement("div");
    name.className = "f3-name"; det.className = "f3-det";
    div.append(dot, name, det);
    const label = new CSS2DObject(div);
    label.position.set(0, -1.25, 0);   // under the box
    mesh.add(label);
    mesh.userData.id = n.id;
    world.add(mesh);
    const r = { node: n, mesh, mat, outline, label, dot, name, det };
    paintNode(r, n);
    nodes.set(n.id, r);
  }

  /* ---------- edges ---------- */
  function addEdge(e) {
    const a = nodes.get(e.from), b = nodes.get(e.to);
    if (!a || !b) return;
    const curve = new THREE.QuadraticBezierCurve3(a.mesh.position, a.mesh.position.clone().add(b.mesh.position).multiplyScalar(0.5).add(new THREE.Vector3(0, 2, 0)), b.mesh.position);
    const geo = new THREE.BufferGeometry().setFromPoints(curve.getPoints(28));
    let mat, line, parts = [];
    if (e.state === "fail") {
      mat = new THREE.LineDashedMaterial({ color: COLOR.fail, dashSize: 0.6, gapSize: 0.4 });
      line = new THREE.Line(geo, mat);
      line.computeLineDistances();
    } else if (e.state === "ok") {
      mat = new THREE.LineBasicMaterial({ color: ACCENT, transparent: true, opacity: 0.55 });
      line = new THREE.Line(geo, mat);
      if (!reduce) for (let i = 0; i < PARTS; i++) { const m = new THREE.Mesh(dotGeo, dotMat); m.userData.off = i / PARTS; line.add(m); parts.push(m); }
    } else {
      mat = new THREE.LineBasicMaterial({ color: EDGE_IDLE });
      line = new THREE.Line(geo, mat);
    }
    world.add(line);
    edges.set(edgeKey(e), { state: e.state, obj: line, curve, parts });
  }

  function build(flow) {
    clear();
    const list = flow.nodes || [], pos = layout(list);
    list.forEach(n => addNode(n, pos.get(n.id)));
    (flow.edges || []).forEach(addEdge);
    // stage titles on one line above the columns, and a faint floor under the lowest node
    let top = -Infinity, low = Infinity;
    pos.forEach(p => { top = Math.max(top, p.y); low = Math.min(low, p.y); });
    if (!list.length) { top = 0; low = 0; }
    (flow.stages || []).forEach((title, i) => {
      const d = document.createElement("div");
      d.className = "f3-stage"; d.textContent = title;
      const o = new THREE.Object3D();
      const l = new CSS2DObject(d);
      o.add(l); o.position.set((i - 2) * DX, top + 3.2, 0);
      world.add(o);
    });
    const grid = new THREE.GridHelper(110, 55, GRID, GRID);
    grid.position.y = low - 3;
    world.add(grid);
    if (selected && !nodes.has(selected)) selected = null;
    paintSelection();
  }

  function shapeOf(flow) {
    return (flow.nodes || []).map(n => n.id + "@" + n.stage).join("|") + "#" + (flow.edges || []).map(edgeKey).join("|") + "#" + (flow.stages || []).join("|");
  }

  /* ---------- selection and hover ---------- */
  function paintSelection() {
    nodes.forEach((r, id) => { r.outline.visible = id === selected; r.label.element.classList.toggle("sel", id === selected); });
  }
  function hit(ev) {
    const rc = labels.domElement.getBoundingClientRect();
    raycaster.setFromCamera(new THREE.Vector2(((ev.clientX - rc.left) / rc.width) * 2 - 1, -((ev.clientY - rc.top) / rc.height) * 2 + 1), camera);
    const h = raycaster.intersectObjects([...nodes.values()].map(r => r.mesh), false)[0];
    return h ? h.object.userData.id : null;
  }
  let down = null;
  const onDown = ev => { down = { x: ev.clientX, y: ev.clientY }; };
  const onUp = ev => {
    if (!down || ev.button !== 0) return;
    const moved = Math.hypot(ev.clientX - down.x, ev.clientY - down.y) > 5;   // a drag orbits, it does not pick
    down = null;
    if (moved) return;
    const id = hit(ev);
    selected = id;
    paintSelection();
    if (opts.onPick) opts.onPick(id ? nodes.get(id).node : null);
  };
  const onMove = ev => {
    if (down) return;
    const id = hit(ev);
    if (id === hovered) return;
    if (hovered && nodes.has(hovered)) nodes.get(hovered).label.element.classList.remove("hover");
    hovered = id;
    if (id) nodes.get(id).label.element.classList.add("hover");
    labels.domElement.style.cursor = id ? "pointer" : "";
  };
  const onLeave = () => { down = null; onMove({ clientX: -1e5, clientY: -1e5 }); };
  const dom = labels.domElement;
  dom.addEventListener("pointerdown", onDown);
  dom.addEventListener("pointerup", onUp);
  dom.addEventListener("pointermove", onMove);
  dom.addEventListener("pointerleave", onLeave);

  /* ---------- loop ---------- */
  function resize() {
    const w = Math.max(el.clientWidth, 1), h = Math.max(el.clientHeight, 1);
    if (w === lastW && h === lastH) return;
    lastW = w; lastH = h;
    renderer.setSize(w, h);
    labels.setSize(w, h);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  function frame(now) {
    raf = 0;
    if (disposed || document.hidden) return;   // a hidden window draws nothing; visibilitychange restarts the loop
    raf = requestAnimationFrame(frame);
    const t = now / 1000;
    resize();
    controls.update();
    nodes.forEach(r => {
      const fail = r.node.state === "fail";
      r.mat.emissiveIntensity = fail ? (reduce ? 0.6 : 0.55 + 0.45 * Math.sin((t / PULSE_S) * Math.PI * 2)) : 0.25;
    });
    edges.forEach(e => e.parts.forEach(m => m.position.copy(e.curve.getPoint(((t / LOOP_S) + m.userData.off) % 1))));
    renderer.render(scene, camera);
    labels.render(scene, camera);
  }
  const onVisible = () => { if (!document.hidden && !raf && !disposed) raf = requestAnimationFrame(frame); };
  window.addEventListener("resize", resize);
  document.addEventListener("visibilitychange", onVisible);
  resize();
  raf = requestAnimationFrame(frame);

  /* ---------- API ---------- */
  // Same nodes and edges as last time: only recolour and retext (an edge whose state changed is redrawn). Otherwise rebuild.
  function update(flow) {
    if (disposed || !flow) return;
    const sh = shapeOf(flow);
    if (sh !== shape) { shape = sh; build(flow); return; }
    (flow.nodes || []).forEach(n => { const r = nodes.get(n.id); if (r) paintNode(r, n); });
    (flow.edges || []).forEach(e => {
      const cur = edges.get(edgeKey(e));
      if (!cur || cur.state === e.state) return;
      world.remove(cur.obj); free(cur.obj); edges.delete(edgeKey(e));
      addEdge(e);
    });
  }
  function dispose() {
    if (disposed) return;
    disposed = true;
    if (raf) cancelAnimationFrame(raf);
    raf = 0;
    window.removeEventListener("resize", resize);
    document.removeEventListener("visibilitychange", onVisible);
    dom.removeEventListener("pointerdown", onDown);
    dom.removeEventListener("pointerup", onUp);
    dom.removeEventListener("pointermove", onMove);
    dom.removeEventListener("pointerleave", onLeave);
    controls.dispose();
    clear();
    shared.forEach(x => x.dispose());
    renderer.dispose();
    renderer.domElement.remove();
    labels.domElement.remove();
  }
  return { update, dispose };
}
