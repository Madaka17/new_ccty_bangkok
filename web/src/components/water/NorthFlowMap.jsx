// Map of the northern water on its way to Bangkok, tilted in 3D: every RID gauge, dam and the Nonthaburi station
// as a labelled marker, joined by raised bands of water. Band height and width = discharge, colour = status now
// or at the 4-day outlook peak, and white drops run along the top of each band the way the water flows (faster =
// more water). The bands join the gauges straight; the river itself is on the base map.
// The roads the AI expects to flood once the water arrives are dots, with a button that zooms to them.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { baseStyle, bounds } from './WaterMap.jsx';
import { Card, SectionHeader, Segmented, FOCUS } from '../dashboard/ui.jsx';
import { fmtDay, fmtNum, fmtTime } from '../dashboard/format.js';
import { fullness, nowOf } from './NorthFlowExplain.jsx';

const COLORS = { overflow: '#dc2626', high: '#d97706', normal: '#059669', offline: '#94a3b8', dam: '#2563eb' };
const LEGEND = [
  ['overflow', 'ล้นตลิ่ง ≥ 100%'],
  ['high', 'น้ำมาก ≥ 70%'],
  ['normal', 'ปกติ'],
  ['dam', 'น้ำระบายจากเขื่อน'],
  ['offline', 'ไม่มีข้อมูล'],
];
const EMPTY = { type: 'FeatureCollection', features: [] };
const ROAD_COLOR = { สูง: '#dc2626', ปานกลาง: '#d97706', เฝ้าระวัง: '#2563eb' };
const fmtQ = (q) => (q == null ? '–' : fmtNum(Math.round(q)));
const inText = (h) => (h < 36 ? `~${h} ชม.` : `~${(h / 24).toFixed(1).replace('.0', '')} วัน`);

// Shapes are drawn in metres: metres per degree of longitude / latitude near a latitude
const mPerDeg = (lat) => [111320 * Math.cos((lat * Math.PI) / 180), 110540];

// A strip w metres wide from a to z ([lng, lat] each), as a closed polygon ring
function strip(a, z, w) {
  const [kx, ky] = mPerDeg((a[1] + z[1]) / 2);
  const dx = (z[0] - a[0]) * kx;
  const dy = (z[1] - a[1]) * ky;
  const len = Math.hypot(dx, dy) || 1;
  const ox = ((-dy / len) * w) / 2 / kx;
  const oy = ((dx / len) * w) / 2 / ky;
  return [[a[0] + ox, a[1] + oy], [z[0] + ox, z[1] + oy], [z[0] - ox, z[1] - oy], [a[0] - ox, a[1] - oy], [a[0] + ox, a[1] + oy]];
}

// A square of side `side` metres centred on p
function square(p, side) {
  const [kx, ky] = mPerDeg(p[1]);
  const hx = side / 2 / kx;
  const hy = side / 2 / ky;
  return [[p[0] - hx, p[1] - hy], [p[0] + hx, p[1] - hy], [p[0] + hx, p[1] + hy], [p[0] - hx, p[1] + hy], [p[0] - hx, p[1] - hy]];
}

const TILT = { pitch: 55, bearing: -12 };

// Every point on the map, keyed the way `edges` names them: gauge code, "dam:<name>" or "BKK"
function buildNodes(data, view) {
  const out = {};
  for (const s of data.stations || []) {
    if (s.lat == null || s.lng == null) continue;
    const peak = view === 'peak' && s.peak ? s.peak : null;
    const n = nowOf(s);
    out[s.code] = {
      id: s.code,
      kind: 'gauge',
      lat: s.lat,
      lng: s.lng,
      label: s.code,
      value: peak ? `${fmtQ(peak.q)}` : n.q != null ? fmtQ(n.q) : s.below_bank != null ? (s.below_bank > 0 ? `-${s.below_bank.toFixed(2)} ม.` : `+${(-s.below_bank).toFixed(2)} ม.`) : '–',
      q: peak ? peak.q : n.q,
      status: peak ? peak.status || s.status : s.status,
      s,
    };
  }
  for (const d of data.dams || []) {
    if (d.lat == null || d.lng == null) continue;
    out[`dam:${d.name}`] = { id: `dam:${d.name}`, kind: 'dam', lat: d.lat, lng: d.lng, label: `เขื่อน${d.name}`, value: d.storage_pct != null ? `${Math.round(d.storage_pct)}%` : '–', q: d.released_m3s, status: 'dam', d };
  }
  const b = data.bangkok;
  if (b?.lat != null) {
    const over = b.over_bank_t != null;
    out.BKK = { id: 'BKK', kind: 'bkk', lat: b.lat, lng: b.lng, label: 'นนทบุรี-กทม.', value: `${(view === 'peak' ? b.peak_msl : b.now_msl ?? b.peak_msl).toFixed(2)} ม.`, q: null, status: view === 'peak' && over ? 'overflow' : (b.now_msl ?? -99) >= (b.bank ?? 99) ? 'overflow' : 'normal', b };
  }
  return out;
}

export default function NorthFlowMap({ data, code, onSelect, isActive, texts, roads, nb }) {
  const [view, setView] = useState('now');
  const [picked, setPicked] = useState(null);
  const [tilt, setTilt] = useState(true);   // 3D view, or flat from above
  const mapEl = useRef(null);
  const flowsRef = useRef([]);   // one entry per band: ends, discharge, size, for the moving drops
  const mapRef = useRef(null);
  const readyRef = useRef(false);
  const pushRef = useRef(null);
  const markersRef = useRef([]);

  const nodes = useMemo(() => buildNodes(data, view), [data, view]);

  // The AI's roads (Bangkok and elsewhere), plus every Nonthaburi stretch with a 10% chance or more
  const roadPts = useMemo(() => {
    const out = (roads || []).filter((r) => r.lat != null && r.lng != null && r.province !== 'นนทบุรี').map((r) => ({ ...r, id: r.road }));
    for (const r of nb?.roads || []) {
      (r.stretches || []).forEach((s, i) => {
        if (s.p < 0.1) return;
        out.push({
          id: `${r.road}#${i}`, road: r.road, lat: s.lat, lng: s.lng, province: 'นนทบุรี', district: s.amphoe, p: s.p,
          level: s.p >= 0.6 ? 'สูง' : s.p >= 0.3 ? 'ปานกลาง' : 'เฝ้าระวัง', when: '7 วันนี้',
          why: `${i === 0 ? 'ช่วงที่เสี่ยงที่สุดของถนนนี้' : `ช่วงอันดับ ${i + 1} ของถนนนี้`}: ${s.place} ห่างแม่น้ำเจ้าพระยาราว ${Math.round(s.km * 1000)} ม.`,
        });
      });
    }
    return out;
  }, [roads, nb]);
  const fitRoads = useCallback(() => {
    const b = bounds(roadPts);
    if (b) mapRef.current?.fitBounds(b, { padding: 50, maxZoom: 13, duration: 600 });
  }, [roadPts]);

  const fitAll = useCallback(() => {
    const b = bounds(Object.values(nodes));
    if (b) mapRef.current?.fitBounds(b, { padding: { top: 30, bottom: 30, left: 30, right: 90 }, duration: 600 });
  }, [nodes]);

  useEffect(() => {
    if (!mapEl.current || mapRef.current) return;
    const map = new maplibregl.Map({ container: mapEl.current, style: baseStyle(), center: [100.2, 16.3], zoom: 6, ...TILT, attributionControl: { compact: true } });
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'top-left');
    map.on('load', () => {
      // the water bands, then the drops riding on top of them
      map.addSource('edges', { type: 'geojson', data: EMPTY });
      map.addLayer({
        id: 'edges',
        type: 'fill-extrusion',
        source: 'edges',
        paint: { 'fill-extrusion-color': ['get', 'color'], 'fill-extrusion-height': ['get', 'h'], 'fill-extrusion-base': 0, 'fill-extrusion-opacity': 0.75 },
      });
      map.addSource('drops', { type: 'geojson', data: EMPTY });
      map.addLayer({
        id: 'drops',
        type: 'fill-extrusion',
        source: 'drops',
        paint: { 'fill-extrusion-color': '#e0f2fe', 'fill-extrusion-height': ['get', 'top'], 'fill-extrusion-base': ['get', 'base'], 'fill-extrusion-opacity': 0.95 },
      });
      map.addSource('river', { type: 'geojson', data: EMPTY });
      map.addLayer({ id: 'river', type: 'line', source: 'river', layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#0284c7', 'line-width': ['interpolate', ['linear'], ['zoom'], 8, 2, 13, 6], 'line-opacity': 0.8 } });
      map.addSource('roads', { type: 'geojson', data: EMPTY });
      map.addLayer({
        id: 'roads',
        type: 'circle',
        source: 'roads',
        paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 8, 4, 13, 8], 'circle-color': ['get', 'color'], 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 1.5 },
      });
      map.on('click', 'roads', (e) => {
        const id = e.features?.[0]?.properties?.id;
        if (id) setPicked(`road:${id}`);
      });
      map.on('mouseenter', 'roads', () => (map.getCanvas().style.cursor = 'pointer'));
      map.on('mouseleave', 'roads', () => (map.getCanvas().style.cursor = ''));
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

  // The drops: a few per band, sliding from the upstream end to the downstream end, then round again.
  // `sec` is the running time; each band's speed grows with its discharge.
  const drawDrops = useCallback((sec) => {
    const map = mapRef.current;
    if (!map || !readyRef.current) return;
    const features = [];
    for (const f of flowsRef.current) {
      if (!(f.q > 0)) continue;
      const n = Math.max(3, Math.min(14, Math.round(f.km / 18)));
      const speed = (6 + 24 * f.rel) / f.km;   // share of the band per second (6-30 km a second on screen)
      const side = f.w * 0.45;
      for (let k = 0; k < n; k++) {
        const t = (k / n + sec * speed) % 1;
        const p = [f.a[0] + (f.z[0] - f.a[0]) * t, f.a[1] + (f.z[1] - f.a[1]) * t];
        features.push({ type: 'Feature', geometry: { type: 'Polygon', coordinates: [square(p, side)] }, properties: { base: f.h, top: f.h + side * 0.6 } });
      }
    }
    map.getSource('drops')?.setData({ type: 'FeatureCollection', features });
  }, []);

  // Run the drops while the page is open (~25 frames a second); one still frame for reduced motion
  useEffect(() => {
    if (!isActive) return;
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      drawDrops(0);
      return;
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

  // Bands follow the water: coloured by the gauge the water leaves, as high and wide as what it carries
  // (scaled to the biggest discharge on the map, so the tallest band is always 60 km high)
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const push = () => {
      const pairs = (data.edges || []).map((e) => [nodes[e.from], nodes[e.to]]).filter(([a, z]) => a && z);
      const maxQ = Math.max(1, ...pairs.map(([a]) => a.q ?? 0));
      flowsRef.current = pairs.map(([a, z]) => {
        const q = a.q ?? 0;
        const rel = q / maxQ;
        const [kx, ky] = mPerDeg((a.lat + z.lat) / 2);
        return {
          a: [a.lng, a.lat],
          z: [z.lng, z.lat],
          q,
          rel,
          color: COLORS[a.status] || COLORS.offline,
          w: 5000 + 12000 * Math.sqrt(rel),
          h: q > 0 ? 3000 + 57000 * rel : 1200,
          km: Math.max(1, Math.hypot((z.lng - a.lng) * kx, (z.lat - a.lat) * ky) / 1000),
        };
      });
      map.getSource('edges')?.setData({
        type: 'FeatureCollection',
        features: flowsRef.current.map((f) => ({ type: 'Feature', geometry: { type: 'Polygon', coordinates: [strip(f.a, f.z, f.w)] }, properties: { color: f.color, h: f.h } })),
      });
      map.getSource('river')?.setData({
        type: 'FeatureCollection',
        features: (nb?.river_line || []).map((l) => ({ type: 'Feature', geometry: { type: 'LineString', coordinates: l.map(([la, ln]) => [ln, la]) }, properties: {} })),
      });
      map.getSource('roads')?.setData({
        type: 'FeatureCollection',
        features: roadPts.map((r) => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [r.lng, r.lat] }, properties: { id: r.id, color: ROAD_COLOR[r.level] || '#64748b' } })),
      });

      markersRef.current.forEach((m) => m.remove());
      markersRef.current = Object.values(nodes).map((n) => {
        const el = document.createElement('button');
        el.type = 'button';
        const on = n.id === code || n.id === picked;
        el.className = `flex items-center gap-1 rounded-full border bg-white pl-1 pr-2 py-0.5 text-[11px] leading-4 whitespace-nowrap shadow-sm cursor-pointer ${on ? 'border-blue-600 ring-2 ring-blue-600' : 'border-slate-300'}`;
        el.title = n.kind === 'gauge' ? `${n.s.province} · ${n.s.name}` : n.label;
        const dot = document.createElement('span');
        dot.className = n.kind === 'dam' ? 'w-2.5 h-2.5 rounded-sm shrink-0' : 'w-2.5 h-2.5 rounded-full shrink-0';
        dot.style.background = COLORS[n.status] || COLORS.offline;
        const text = document.createElement('span');
        text.className = 'text-slate-900 tabular-nums';
        text.textContent = `${n.label} ${n.value}`;
        el.append(dot, text);
        el.addEventListener('click', (ev) => {
          ev.stopPropagation();
          setPicked(n.id);
          if (n.kind === 'gauge' && n.s.history?.length) onSelect(n.id);
        });
        return new maplibregl.Marker({ element: el, anchor: 'left', offset: [-6, 0] }).setLngLat([n.lng, n.lat]).addTo(map);
      });
    };
    pushRef.current = push;
    if (readyRef.current) push();
  }, [data, nodes, code, picked, onSelect, roadPts, nb]);

  const road = picked?.startsWith('road:') ? roadPts.find((r) => `road:${r.id}` === picked) : null;
  const sel = road ? null : nodes[picked] || nodes[code];

  return (
    <Card className="p-0 overflow-hidden" aria-labelledby="north-map-title">
      <div className="p-5 pb-4">
        <SectionHeader
          id="north-map-title"
          title="แผนที่เส้นทางน้ำเหนือ → กรุงเทพฯ"
          description="เม็ดน้ำสีขาววิ่งไปทางที่น้ำไหล · แถบยิ่งสูง น้ำยิ่งมาก · ตัวเลข = ลบ.ม./วินาที · แตะจุดเพื่อดูรายละเอียดและกราฟ"
          action={<Segmented label="ช่วงเวลาที่แสดง" value={view} onChange={setView} options={[['now', 'ตอนนี้'], ['peak', 'คาดสูงสุด 4 วัน']]} />}
        />
      </div>
      <div className="relative h-[460px] lg:h-[560px] border-t border-slate-200">
        {/* inline position: maplibre-gl.css sets .maplibregl-map { position: relative } over a class */}
        <div ref={mapEl} style={{ position: 'absolute', inset: 0 }} />
        <div className="absolute top-2.5 right-2.5 flex flex-col items-end gap-1.5">
          <button type="button" onClick={fitAll} className={`h-8 px-3 rounded-lg bg-white border border-slate-300 text-xs font-medium text-slate-800 shadow-sm hover:bg-slate-50 ${FOCUS}`}>
            ดูทั้งเส้นทาง
          </button>
          <button type="button" onClick={() => setTilt((v) => !v)} aria-pressed={tilt} className={`h-8 px-3 rounded-lg bg-white border border-slate-300 text-xs font-medium text-slate-800 shadow-sm hover:bg-slate-50 ${FOCUS}`}>
            {tilt ? 'ดูแบบแบน' : 'ดูแบบ 3 มิติ'}
          </button>
          {roadPts.length > 0 && (
            <button type="button" onClick={fitRoads} className={`h-8 px-3 rounded-lg bg-white border border-slate-300 text-xs font-medium text-slate-800 shadow-sm hover:bg-slate-50 ${FOCUS}`}>
              ถนนเสี่ยง กทม.-นนทบุรี ({new Set(roadPts.map((r) => r.road)).size} สาย)
            </button>
          )}
        </div>
        {road && (
          <div className="absolute bottom-2 left-2 max-w-[320px] rounded-lg border border-slate-200 bg-white p-3 text-xs text-slate-600 shadow-sm">
            <div className="flex items-start justify-between gap-2">
              <b className="text-sm text-slate-900 leading-snug">{road.road}</b>
              <button type="button" onClick={() => setPicked(null)} aria-label="ปิดรายละเอียด" className={`text-slate-400 hover:text-slate-700 ${FOCUS}`}>
                ✕
              </button>
            </div>
            <p className="mt-0.5">
              {road.province === 'กรุงเทพมหานคร' ? `เขต${road.district}` : road.district ? `อ.${road.district} จ.${road.province}` : `จ.${road.province}`} · เสี่ยง{road.level} · {road.when}
              {road.p != null ? ` · โอกาส ${Math.round(road.p * 100)}%` : ''}
            </p>
            <p className="mt-1 text-slate-700 leading-5">{road.why}</p>
          </div>
        )}
        {sel && (
          <div className="absolute bottom-2 left-2 max-w-[300px] rounded-lg border border-slate-200 bg-white p-3 text-xs text-slate-600 shadow-sm">
            <div className="flex items-start justify-between gap-2">
              <b className="text-sm text-slate-900 leading-snug">
                {sel.kind === 'gauge' ? `${sel.s.code} ${sel.s.province}` : sel.kind === 'dam' ? sel.label : 'นนทบุรี-กรุงเทพฯ (สะพานนวลฉวี)'}
              </b>
              {picked && (
                <button type="button" onClick={() => setPicked(null)} aria-label="ปิดรายละเอียด" className={`text-slate-400 hover:text-slate-700 ${FOCUS}`}>
                  ✕
                </button>
              )}
            </div>
            {sel.kind === 'gauge' && (
              <div className="mt-1 space-y-0.5 tabular-nums">
                <p>{sel.s.name}</p>
                <p>
                  ตอนนี้ <span className="font-semibold text-slate-900">{fmtQ(nowOf(sel.s).q)}</span> ลบ.ม./วิ
                  {nowOf(sel.s).pct != null ? ` · เต็ม ${Math.round(nowOf(sel.s).pct)}% ${fullness(nowOf(sel.s).pct)}` : ''}
                  {nowOf(sel.s).t ? ` (${nowOf(sel.s).est ? 'ประมาณ' : 'กรมชลฯ'} ${fmtTime(nowOf(sel.s).t)} น.)` : ''}
                </p>
                {texts?.[sel.id] && (
                  <p className="pt-1 text-slate-700 leading-5">
                    <span className="font-semibold text-blue-700">AI:</span> {texts[sel.id]}
                  </p>
                )}
                {sel.s.below_bank != null && <p>{sel.s.below_bank > 0 ? `ต่ำกว่าตลิ่ง ${sel.s.below_bank.toFixed(2)} ม.` : `สูงกว่าตลิ่ง ${(-sel.s.below_bank).toFixed(2)} ม.`}</p>}
                {sel.s.peak && (
                  <p>
                    คาดสูงสุด {fmtQ(sel.s.peak.q)} ({Math.round(sel.s.peak.pct ?? 0)}%) ใน {inText(sel.s.peak.in_h)}
                  </p>
                )}
                {sel.s.from_c2_h > 0 && <p>น้ำจากนครสวรรค์ถึงที่นี่ใน {inText(sel.s.from_c2_h)}</p>}
              </div>
            )}
            {sel.kind === 'dam' && (
              <p className="mt-1 tabular-nums">
                ความจุ {sel.value} · น้ำไหลเข้า {fmtQ(sel.d.inflow_m3s)} · ระบาย {fmtQ(sel.d.released_m3s)} ลบ.ม./วิ ({sel.d.date || '–'})
              </p>
            )}
            {sel.kind === 'bkk' && (
              <p className="mt-1 tabular-nums">
                ตอนนี้ {sel.b.now_msl != null ? sel.b.now_msl.toFixed(2) : '–'} ม.รทก. · สสน. คาดสูงสุด {sel.b.peak_msl.toFixed(2)} ราว {fmtDay(sel.b.peak_t * 1000)} · ตลิ่ง {sel.b.bank?.toFixed(2) ?? '–'}
              </p>
            )}
          </div>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-3 border-t border-slate-200 text-xs text-slate-600">
        {nb?.river_line?.length > 0 && (
          <span className="inline-flex items-center gap-1.5">
            <span className="w-4 h-1 rounded-full shrink-0" style={{ background: '#0284c7' }} />
            แม่น้ำเจ้าพระยา (นนทบุรี)
          </span>
        )}
        {roadPts.length > 0 && (
          <span className="inline-flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full shrink-0 border border-white" style={{ background: ROAD_COLOR.สูง }} />
            ถนนเสี่ยงน้ำท่วม (จุด = ช่วงถนน)
          </span>
        )}
        {LEGEND.map(([k, text]) => (
          <span key={k} className="inline-flex items-center gap-1.5">
            <span className={`w-2.5 h-2.5 shrink-0 ${k === 'dam' ? 'rounded-sm' : 'rounded-full'}`} style={{ background: COLORS[k] }} />
            {text}
          </span>
        ))}
        <span className="ml-auto text-[11px] text-slate-500">
          {view === 'peak' ? 'สีและตัวเลข = ค่าสูงสุดที่คาดใน 4 วัน (สถานีที่ไม่มีค่าคาดการณ์แสดงค่าปัจจุบัน)' : 'แถบน้ำลากตรงระหว่างสถานี ไม่ใช่แนวลำน้ำจริง · ลากสองนิ้วหรือคลิกขวาค้างเพื่อหมุนแผนที่'}
        </span>
      </div>
    </Card>
  );
}
