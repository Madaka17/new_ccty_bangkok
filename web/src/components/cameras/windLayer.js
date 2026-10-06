// Moving wind lines over a MapLibre map, like earth.nullschool: short-lived particles drift with the wind and
// leave fading trails. The field is the hourly grid from /api/weather/wind_field (u, v in m/s); the two hours
// around now are blended, so the lines change with the clock between refreshes. Drawn on a 2D canvas inside
// the map's canvas container (under DOM markers, over the map); hidden while the map moves.
const SPEED = 0.18;          // screen px per frame for each m/s, the same at every zoom
const AREA_PER_LINE = 380;   // one line per this many screen px²
const MAX_LINES = 2600;
const MAX_AGE = 90;          // frames a line lives at most
const FADE = 0.93;           // share of a trail kept each frame
const FRAME_MS = 33;         // about 30 frames a second
const BLEND_MS = 60000;      // how often the field is re-blended for the time now
// [up to m/s, line width, alpha]: stronger wind draws bolder lines
const BANDS = [[3, 0.8, 0.45], [6, 1.1, 0.65], [10, 1.4, 0.85], [Infinity, 1.8, 1]];

function blend(data, nowSec) {
  const frames = data?.frames || [];
  if (!frames.length) return null;
  let k = frames.findIndex((f) => f.t > nowSec) - 1;
  if (k === -2) k = frames.length - 1;   // now is past the last hour: hold the last one
  if (k < 0) k = 0;
  const a = frames[k];
  const b = frames[k + 1];
  const w = b ? Math.min(1, Math.max(0, (nowSec - a.t) / (b.t - a.t))) : 0;
  const u = b ? a.u.map((x, i) => x + (b.u[i] - x) * w) : a.u;
  const v = b ? a.v.map((x, i) => x + (b.v[i] - x) * w) : a.v;
  const hour = b && w >= 0.5 ? b.t : a.t;
  return { lat0: data.lat0, lng0: data.lng0, step: data.step, nx: data.nx, ny: data.ny, u, v, hour };
}

// Bilinear (u, v) at a point, or null outside the grid
function sample(f, lng, lat) {
  const x = (lng - f.lng0) / f.step;
  const y = (lat - f.lat0) / f.step;
  if (!(x >= 0 && y >= 0 && x <= f.nx - 1 && y <= f.ny - 1)) return null;
  const i = Math.min(Math.floor(x), f.nx - 2);
  const j = Math.min(Math.floor(y), f.ny - 2);
  const fx = x - i;
  const fy = y - j;
  const at = (arr, ii, jj) => arr[jj * f.nx + ii];
  const lerp = (arr) => (at(arr, i, j) * (1 - fx) + at(arr, i + 1, j) * fx) * (1 - fy)
    + (at(arr, i, j + 1) * (1 - fx) + at(arr, i + 1, j + 1) * fx) * fy;
  return [lerp(f.u), lerp(f.v)];
}

export class WindLayer {
  constructor(map, { color }) {
    this.map = map;
    this.color = color;
    this.data = null;
    this.field = null;
    this.blendedAt = 0;
    this.lines = [];
    this.on = false;
    this.moving = false;
    this.raf = 0;
    this.last = 0;
    this.canvas = document.createElement('canvas');
    this.canvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;pointer-events:none';
    map.getCanvasContainer().appendChild(this.canvas);
    this.ctx = this.canvas.getContext('2d');
    this.onMoveStart = () => {
      this.moving = true;
      this.clear();
    };
    this.onMoveEnd = () => {
      this.moving = false;
      this.reset();
    };
    map.on('movestart', this.onMoveStart);
    map.on('moveend', this.onMoveEnd);
    map.on('resize', this.onMoveEnd);
    this.tick = this.tick.bind(this);
  }

  // The hour shown now (epoch seconds), or null with no data
  get hour() {
    return this.field?.hour ?? null;
  }

  setData(data) {
    this.data = data;
    this.blendedAt = 0;
    this.reblend();
    this.reset();
  }

  setOn(on) {
    this.on = on;
    this.clear();
    if (on) this.reset();
  }

  reblend() {
    const now = Date.now();
    if (now - this.blendedAt < BLEND_MS) return;
    this.blendedAt = now;
    this.field = blend(this.data, now / 1000);
  }

  clear() {
    this.ctx.setTransform(1, 0, 0, 1, 0, 0);
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
  }

  // Fit the canvas to the map and scatter new lines over the screen
  reset() {
    const dpr = window.devicePixelRatio || 1;
    const w = this.canvas.clientWidth;
    const h = this.canvas.clientHeight;
    if (this.canvas.width !== Math.round(w * dpr) || this.canvas.height !== Math.round(h * dpr)) {
      this.canvas.width = Math.round(w * dpr);
      this.canvas.height = Math.round(h * dpr);
    }
    this.w = w;
    this.h = h;
    this.dpr = dpr;
    this.clear();
    const n = Math.min(MAX_LINES, Math.round((w * h) / AREA_PER_LINE));
    this.lines = Array.from({ length: n }, () => this.spawn({}, true));
    if (this.on && this.field && !this.raf) this.raf = requestAnimationFrame(this.tick);
  }

  // A fresh line at a random spot that has wind data (a few tries, else it waits out one life)
  spawn(p, anyAge) {
    for (let t = 0; t < 6; t++) {
      const x = Math.random() * this.w;
      const y = Math.random() * this.h;
      const ll = this.map.unproject([x, y]);
      if (this.field && sample(this.field, ll.lng, ll.lat)) {
        return Object.assign(p, { x, y, age: anyAge ? Math.floor(Math.random() * MAX_AGE) : 0 });
      }
    }
    return Object.assign(p, { x: -1, y: -1, age: Math.floor(Math.random() * MAX_AGE) });
  }

  tick(ts) {
    this.raf = 0;
    if (!this.on || !this.field) return;
    this.raf = requestAnimationFrame(this.tick);
    if (this.moving || document.hidden || ts - this.last < FRAME_MS) return;
    this.last = ts;
    this.reblend();
    const ctx = this.ctx;
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    // fade the old trails
    ctx.globalCompositeOperation = 'destination-in';
    ctx.fillStyle = `rgba(0,0,0,${FADE})`;
    ctx.fillRect(0, 0, this.w, this.h);
    ctx.globalCompositeOperation = 'source-over';
    const paths = BANDS.map(() => new Path2D());
    for (const p of this.lines) {
      p.age += 1;
      if (p.age > MAX_AGE || p.x < 0) {
        if (p.age > MAX_AGE) this.spawn(p, false);
        continue;
      }
      const ll = this.map.unproject([p.x, p.y]);
      const uv = sample(this.field, ll.lng, ll.lat);
      if (!uv) {
        this.spawn(p, false);
        continue;
      }
      const x = p.x + uv[0] * SPEED;
      const y = p.y - uv[1] * SPEED;
      const speed = Math.hypot(uv[0], uv[1]);
      const band = BANDS.findIndex((b) => speed < b[0]);
      paths[band].moveTo(p.x, p.y);
      paths[band].lineTo(x, y);
      if (x < 0 || y < 0 || x > this.w || y > this.h) this.spawn(p, false);
      else Object.assign(p, { x, y });
    }
    ctx.strokeStyle = this.color();
    ctx.lineCap = 'round';
    BANDS.forEach(([, width, alpha], i) => {
      ctx.lineWidth = width;
      ctx.globalAlpha = alpha;
      ctx.stroke(paths[i]);
    });
    ctx.globalAlpha = 1;
  }

  remove() {
    cancelAnimationFrame(this.raf);
    this.raf = 0;
    this.map.off('movestart', this.onMoveStart);
    this.map.off('moveend', this.onMoveEnd);
    this.map.off('resize', this.onMoveEnd);
    this.canvas.remove();
  }
}
