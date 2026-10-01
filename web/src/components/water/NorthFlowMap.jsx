// Map of the northern water on its way to Bangkok: every RID gauge, dam and the Nonthaburi station as a
// labelled marker, joined by arrows in the direction the water flows. Line width = discharge, colour = status
// now or at the 4-day outlook peak. The lines join the gauges straight; the river itself is on the base map.
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

// Right-pointing arrowhead as an SDF icon, so its colour can be set per layer; the line layout turns it
// to follow each line from its first point (upstream) to its last (downstream)
function arrowIcon() {
  const s = 48;
  const c = document.createElement('canvas');
  c.width = c.height = s;
  const g = c.getContext('2d');
  g.fillStyle = '#000';
  g.beginPath();
  g.moveTo(12, 10);
  g.lineTo(40, 24);
  g.lineTo(12, 38);
  g.lineTo(19, 24);
  g.closePath();
  g.fill();
  return g.getImageData(0, 0, s, s);
}

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
  const mapEl = useRef(null);
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
    const map = new maplibregl.Map({ container: mapEl.current, style: baseStyle(), center: [100.2, 16.3], zoom: 6, attributionControl: { compact: true } });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-left');
    map.on('load', () => {
      map.addImage('flow-arrow', arrowIcon(), { sdf: true, pixelRatio: 2 });
      map.addSource('edges', { type: 'geojson', data: EMPTY });
      const width = ['interpolate', ['linear'], ['coalesce', ['get', 'q'], 0], 0, 2, 500, 3.5, 1500, 6, 3000, 9];
      map.addLayer({ id: 'edges-casing', type: 'line', source: 'edges', layout: { 'line-cap': 'round' }, paint: { 'line-color': '#ffffff', 'line-width': ['+', width, 3], 'line-opacity': 0.85 } });
      map.addLayer({ id: 'edges', type: 'line', source: 'edges', layout: { 'line-cap': 'round' }, paint: { 'line-color': ['get', 'color'], 'line-width': width } });
      map.addLayer({
        id: 'edges-arrows',
        type: 'symbol',
        source: 'edges',
        layout: {
          'symbol-placement': 'line',
          'symbol-spacing': 60,
          'icon-image': 'flow-arrow',
          'icon-size': ['interpolate', ['linear'], ['coalesce', ['get', 'q'], 0], 0, 0.75, 3000, 1.25],
          'icon-allow-overlap': true,
          'icon-ignore-placement': true,
          'icon-rotation-alignment': 'map',
          'icon-keep-upright': false,
        },
        paint: { 'icon-color': ['get', 'color'], 'icon-halo-color': '#ffffff', 'icon-halo-width': 2 },
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

  // Lines follow the water: coloured by the gauge the water leaves, as wide as what it carries
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const push = () => {
      const features = [];
      for (const e of data.edges || []) {
        const a = nodes[e.from];
        const z = nodes[e.to];
        if (!a || !z) continue;
        features.push({
          type: 'Feature',
          geometry: { type: 'LineString', coordinates: [[a.lng, a.lat], [z.lng, z.lat]] },
          properties: { color: COLORS[a.status] || COLORS.offline, q: a.q ?? 0 },
        });
      }
      map.getSource('edges')?.setData({ type: 'FeatureCollection', features });
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
          description="ลูกศรชี้ทิศทางน้ำ · เส้นยิ่งหนา น้ำยิ่งมาก · ตัวเลข = ลบ.ม./วินาที · แตะจุดเพื่อดูรายละเอียดและกราฟ"
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
          {view === 'peak' ? 'สีและตัวเลข = ค่าสูงสุดที่คาดใน 4 วัน (สถานีที่ไม่มีค่าคาดการณ์แสดงค่าปัจจุบัน)' : 'ลากเส้นตรงระหว่างสถานี ไม่ใช่แนวลำน้ำจริง'}
        </span>
      </div>
    </Card>
  );
}
