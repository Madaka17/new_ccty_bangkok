// 3D map of the water from the North, drawn along the real river courses (north_route.py paths): each stretch is
// a raised band as high and wide as the discharge it carries on the chosen day, coloured by how full the river
// is, with white drops running downstream (faster = more water). A day picker moves from today to +7 days.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { baseStyle, bounds } from './WaterMap.jsx';
import { mPerDeg, square, strip } from './NorthFlowMap.jsx';
import { Card, SectionHeader, FOCUS } from '../dashboard/ui.jsx';
import { fmtNum } from '../dashboard/format.js';

const COLORS = { critical: '#dc2626', flood: '#ea580c', watch: '#d97706', normal: '#059669', dam: '#2563eb', none: '#94a3b8' };
const LEGEND = [['critical', 'ล้นตลิ่ง ≥ 100%'], ['flood', 'ใกล้ล้น ≥ 85%'], ['watch', 'น้ำมาก ≥ 70%'], ['normal', 'ปกติ'], ['dam', 'น้ำที่เขื่อนปล่อย']];
const EMPTY = { type: 'FeatureCollection', features: [] };
const TILT = { pitch: 55, bearing: -12 };
const RIVER_TH = { ping: 'ปิง', wang: 'วัง', yom: 'ยม', nan: 'น่าน', chao_phraya: 'เจ้าพระยา', sakae_krang: 'สะแกกรัง', pasak: 'ป่าสัก' };
const dayLabel = (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString('th-TH', { day: 'numeric', month: 'short' });

// Arc length (km) along a [lng, lat] line, for the drops
function measure(line) {
  const cum = [0];
  for (let i = 1; i < line.length; i++) {
    const [kx, ky] = mPerDeg(line[i][1]);
    cum.push(cum[i - 1] + Math.hypot((line[i][0] - line[i - 1][0]) * kx, (line[i][1] - line[i - 1][1]) * ky) / 1000);
  }
  return cum;
}

function pointAt(line, cum, km) {
  let i = 1;
  while (i < cum.length - 1 && cum[i] < km) i++;
  const t = (km - cum[i - 1]) / ((cum[i] - cum[i - 1]) || 1);
  return [line[i - 1][0] + (line[i][0] - line[i - 1][0]) * t, line[i - 1][1] + (line[i][1] - line[i - 1][1]) * t];
}

export default function NorthRouteMap({ data, isActive }) {
  const [day, setDay] = useState(0);
  const [tilt, setTilt] = useState(true);
  const mapEl = useRef(null);
  const mapRef = useRef(null);
  const readyRef = useRef(false);
  const pushRef = useRef(null);
  const flowsRef = useRef([]);
  const markersRef = useRef([]);

  // Every point the water passes, with what it carries on `day`
  const nodes = useMemo(() => {
    const out = {};
    const shared = {};
    for (const g of data.gauges || []) shared[g.province] = (shared[g.province] || 0) + 1;
    for (const g of data.gauges || []) {
      if (g.lat == null) continue;
      const d = g.days?.[day];
      // a province with more than one gauge names the river too (นครสวรรค์ has the Ping, the Nan and the Chao Phraya)
      const label = shared[g.province] > 1 ? `${g.province} (${RIVER_TH[g.river] || g.river})` : g.province;
      out[g.code] = { lat: g.lat, lng: g.lng, q: d?.q ?? null, pct: d?.pct ?? null, level: d?.level || 'none', kind: d?.kind, label, g };
    }
    for (const d of data.dams || []) {
      if (d.lat == null) continue;
      out[`dam:${d.name}`] = { lat: d.lat, lng: d.lng, q: d.released_m3s, pct: d.storage_pct, level: 'dam', label: `เขื่อน${d.name}`, d };
    }
    const c35 = out['C.35'];
    const bkk = (data.provinces || []).find((p) => p.province === 'นนทบุรี-กรุงเทพฯ');
    if (c35 && bkk) {
      const b = bkk.days.find((x) => x.day === day) || bkk.days[0];
      out.BKK = { lat: 13.94749, lng: 100.53507, q: c35.q, level: b?.level || 'none', label: 'นนทบุรี-กทม.', bkk: b };
    }
    return out;
  }, [data, day]);

  const fitAll = useCallback(() => {
    const b = bounds(Object.values(nodes));
    if (b) mapRef.current?.fitBounds(b, { padding: { top: 30, bottom: 30, left: 30, right: 90 }, duration: 600, ...(tilt ? TILT : { pitch: 0, bearing: 0 }) });
  }, [nodes, tilt]);

  useEffect(() => {
    if (!mapEl.current || mapRef.current) return undefined;
    const map = new maplibregl.Map({ container: mapEl.current, style: baseStyle(), center: [100.2, 16.3], zoom: 6, ...TILT, attributionControl: { compact: true } });
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'top-left');
    map.on('load', () => {
      map.addSource('bands', { type: 'geojson', data: EMPTY });
      map.addLayer({ id: 'bands', type: 'fill-extrusion', source: 'bands',
        paint: { 'fill-extrusion-color': ['get', 'color'], 'fill-extrusion-height': ['get', 'h'], 'fill-extrusion-base': 0, 'fill-extrusion-opacity': 0.8 } });
      map.addSource('drops', { type: 'geojson', data: EMPTY });
      map.addLayer({ id: 'drops', type: 'fill-extrusion', source: 'drops',
        paint: { 'fill-extrusion-color': '#e0f2fe', 'fill-extrusion-height': ['get', 'top'], 'fill-extrusion-base': ['get', 'base'], 'fill-extrusion-opacity': 0.95 } });
      readyRef.current = true;
      pushRef.current?.();
      fitAll();
    });
    mapRef.current = map;
    return () => {
      markersRef.current.forEach((m) => m.remove());
      markersRef.current = [];
      map.remove();
      mapRef.current = null;
      readyRef.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (isActive) setTimeout(() => mapRef.current?.resize(), 50);
  }, [isActive]);

  useEffect(() => {
    if (readyRef.current) mapRef.current?.easeTo({ ...(tilt ? TILT : { pitch: 0, bearing: 0 }), duration: 600 });
  }, [tilt]);

  // Bands along the river: one strip per segment of each stretch, sized by the water leaving its upstream end
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const push = () => {
      const pairs = (data.edges || []).map((e) => [e, nodes[e.from], nodes[e.to]]).filter(([, a, z]) => a && z);
      const maxQ = Math.max(1, ...pairs.map(([, a]) => a.q ?? 0));
      flowsRef.current = pairs.map(([e, a, z]) => {
        const line = data.paths?.[`${e.from}>${e.to}`] || [[a.lng, a.lat], [z.lng, z.lat]];
        const q = a.q ?? 0;
        const rel = q / maxQ;
        const cum = measure(line);
        return { line, cum, km: cum[cum.length - 1] || 1, q, rel, color: COLORS[a.level] || COLORS.none,
          w: 5000 + 15000 * Math.sqrt(rel), h: q > 0 ? 3000 + 57000 * rel : 1000 };
      });
      const features = [];
      for (const f of flowsRef.current) {
        for (let i = 1; i < f.line.length; i++) {
          features.push({ type: 'Feature', geometry: { type: 'Polygon', coordinates: [strip(f.line[i - 1], f.line[i], f.w)] }, properties: { color: f.color, h: f.h } });
        }
      }
      map.getSource('bands')?.setData({ type: 'FeatureCollection', features });

      markersRef.current.forEach((m) => m.remove());
      markersRef.current = Object.entries(nodes).map(([id, n]) => {
        const el = document.createElement('div');
        el.className = 'flex items-center gap-1 rounded-full border border-slate-300 bg-white pl-1 pr-2 py-0.5 text-[11px] leading-4 whitespace-nowrap shadow-sm';
        const dot = document.createElement('span');
        dot.className = id.startsWith('dam:') ? 'w-2.5 h-2.5 rounded-sm shrink-0' : 'w-2.5 h-2.5 rounded-full shrink-0';
        dot.style.background = COLORS[n.level] || COLORS.none;
        const text = document.createElement('span');
        text.className = 'text-slate-900 tabular-nums';
        const value = n.bkk ? (n.bkk.below_bank > 0 ? `ต่ำกว่าตลิ่ง ${n.bkk.below_bank.toFixed(2)} ม.` : `เกินตลิ่ง ${(-n.bkk.below_bank).toFixed(2)} ม.`)
          : n.pct != null ? `${Math.round(n.pct)}%` : '';
        text.textContent = `${n.label} ${value}`;
        el.title = n.g ? `${n.g.name} · ${n.q != null ? `${fmtNum(n.q)} ลบ.ม./วิ` : 'ไม่มีข้อมูล'}${n.kind === 'trend' ? ' (แนวโน้ม)' : ''}` : n.d ? `ปล่อยน้ำ ${fmtNum(n.q)} ลบ.ม./วิ · ความจุ ${Math.round(n.pct ?? 0)}%` : '';
        // normal water: a plain dot (its name on hover), so the busy middle of the map stays readable
        const quiet = n.level === 'normal' || n.level === 'none';
        if (quiet) {
          el.className = 'rounded-full border-2 border-white shadow-sm';
          dot.className = 'block w-3 h-3 rounded-full';
          el.title = `${n.label} ${value} · ${el.title}`;
        }
        el.append(...(quiet ? [dot] : [dot, text]));
        return new maplibregl.Marker({ element: el, anchor: quiet ? 'center' : 'left', offset: quiet ? [0, 0] : [-6, 0] }).setLngLat([n.lng, n.lat]).addTo(map);
      });
    };
    pushRef.current = push;
    if (readyRef.current) push();
  }, [data, nodes]);

  // Drops sliding downstream along each stretch; one still frame for reduced motion
  const drawDrops = useCallback((sec) => {
    const map = mapRef.current;
    if (!map || !readyRef.current) return;
    const features = [];
    for (const f of flowsRef.current) {
      if (!(f.q > 0)) continue;
      const n = Math.max(2, Math.min(16, Math.round(f.km / 15)));
      const speed = 6 + 24 * f.rel;   // km of river per second on screen
      const side = f.w * 0.5;
      for (let k = 0; k < n; k++) {
        const km = ((k / n) * f.km + sec * speed) % f.km;
        features.push({ type: 'Feature', geometry: { type: 'Polygon', coordinates: [square(pointAt(f.line, f.cum, km), side)] }, properties: { base: f.h, top: f.h + side * 0.6 } });
      }
    }
    map.getSource('drops')?.setData({ type: 'FeatureCollection', features });
  }, []);

  useEffect(() => {
    if (!isActive) return undefined;
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      drawDrops(0);
      return undefined;
    }
    const start = performance.now();
    let raf = 0;
    let last = 0;
    const frame = (now) => {
      raf = requestAnimationFrame(frame);
      if (now - last < 40) return;
      last = now;
      drawDrops((now - start) / 1000);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [isActive, drawDrops]);

  const dates = data.dates || [];
  const trendDay = (data.gauges || []).find((g) => g.code === 'C.2')?.days?.[day]?.kind === 'trend';

  return (
    <Card className="p-0 overflow-hidden" aria-labelledby="north-route-map-title">
      <div className="p-4 pb-3 flex flex-col gap-3">
        <SectionHeader id="north-route-map-title" title="แผนที่ทางน้ำเหนือ 3 มิติ"
          description="แถบยิ่งสูงและกว้าง น้ำยิ่งมาก · เม็ดสีขาววิ่งไปทางที่น้ำไหล · ตัวเลข = น้ำเต็มลำน้ำกี่ %" />
        <div role="group" aria-label="เลือกวัน" className="flex gap-1.5 overflow-x-auto pb-1">
          {dates.map((iso, i) => (
            <button key={iso} type="button" aria-pressed={day === i} onClick={() => setDay(i)}
              className={`shrink-0 cursor-pointer rounded-lg border px-2.5 py-1 text-xs font-medium ${FOCUS} ${day === i ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-slate-700 border-slate-300 hover:bg-slate-50'}`}>
              {i === 0 ? 'วันนี้' : `+${i} วัน`}<span className="block text-[10px] font-normal opacity-80">{dayLabel(iso)}</span>
            </button>
          ))}
        </div>
      </div>
      <div className="relative h-[460px] lg:h-[560px] border-t border-slate-200">
        {/* inline position: maplibre-gl.css sets .maplibregl-map { position: relative } over a class */}
        <div ref={mapEl} style={{ position: 'absolute', inset: 0 }} />
        <div className="absolute top-2.5 right-2.5 flex flex-col items-end gap-1.5">
          <button type="button" onClick={fitAll} className={`h-8 px-3 rounded-lg bg-white border border-slate-300 text-xs font-medium text-slate-800 shadow-sm hover:bg-slate-50 ${FOCUS}`}>ดูทั้งเส้นทาง</button>
          <button type="button" onClick={() => setTilt((v) => !v)} aria-pressed={tilt} className={`h-8 px-3 rounded-lg bg-white border border-slate-300 text-xs font-medium text-slate-800 shadow-sm hover:bg-slate-50 ${FOCUS}`}>
            {tilt ? 'ดูแบบแบน' : 'ดูแบบ 3 มิติ'}
          </button>
        </div>
        {trendDay && (
          <p className="absolute bottom-2 left-2 rounded-lg border border-amber-300 bg-amber-50 px-2.5 py-1.5 text-[11px] text-amber-900">
            วันนี้เป็นแนวโน้ม คำนวณต่อจากน้ำที่ไหลลงมาและฝนพยากรณ์ ความแม่นยำน้อยกว่าวันแรก ๆ
          </p>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 border-t border-slate-200 text-xs text-slate-600">
        {LEGEND.map(([k, text]) => (
          <span key={k} className="inline-flex items-center gap-1.5">
            <span className={`w-2.5 h-2.5 shrink-0 ${k === 'dam' ? 'rounded-sm' : 'rounded-full'}`} style={{ background: COLORS[k] }} />{text}
          </span>
        ))}
        <span className="ml-auto text-[11px] text-slate-500">ลากสองนิ้วหรือคลิกขวาค้างเพื่อหมุนแผนที่</span>
      </div>
    </Card>
  );
}
