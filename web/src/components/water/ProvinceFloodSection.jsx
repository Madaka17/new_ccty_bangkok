// "น้ำท่วมทั่วประเทศ" tab of the Water page: the flood situation in every province (/api/flood/provinces,
// built from Thai Water's river and rain gauges, the Department of Highways' flooded highways and the floods
// people report), those points on a map, and the AI's overview and per-province analysis.
// A tap on a province (card or point) frames it on the map.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { Badge, Card, ErrorState, FOCUS, SectionHeader, Skeleton } from '../dashboard/ui.jsx';
import { StatusBanner } from '../dashboard/primitives.jsx';
import { agoText, fmtDateTime } from '../dashboard/format.js';
import { baseStyle, bounds } from './WaterMap.jsx';

const POLL_MS = 5 * 60000;
const REGIONS = ['ภาคเหนือ', 'ภาคอีสาน', 'ภาคกลาง', 'ภาคตะวันออก', 'ภาคตะวันตก', 'ภาคใต้'];
const LEVEL = {
  critical: { label: 'วิกฤต', tone: 'red' },
  flood: { label: 'น้ำล้นตลิ่ง/ท่วม', tone: 'yellow' },
  watch: { label: 'เฝ้าระวัง', tone: 'blue' },
  normal: { label: 'ปกติ', tone: 'green' },
};
const POINT = {
  over: { label: 'น้ำล้นตลิ่ง', color: '#dc2626' },
  high: { label: 'น้ำสูงใกล้ตลิ่ง', color: '#f59e0b' },
  road: { label: 'ทางหลวงน้ำท่วม', color: '#7c3aed' },
  report: { label: 'คนแจ้งน้ำท่วม', color: '#db2777' },
};
const THAILAND = [[97.3, 5.6], [105.7, 20.5]];
const CHIP_OFF = 'bg-white text-slate-700 border-slate-300 hover:bg-slate-50';
const CHIP_ON = 'bg-blue-600 text-white border-blue-600';
const TREND = { 1: '↑ ขึ้น', '-1': '↓ ลด', 0: 'ทรงตัว' };

async function fetchProvinces() {
  const res = await fetch('/api/flood/provinces');
  if (!res.ok) throw new Error('provinces');
  return res.json();
}

// Every gauge over the bank or high and every flooded highway, as map points
function toPoints(provinces) {
  const out = [];
  for (const p of provinces) {
    p.gauges.forEach((g, i) => out.push({
      id: `${p.province}-g${i}`, province: p.province, kind: g.level >= 5 ? 'over' : 'high', lat: g.lat, lng: g.lng,
      name: `${g.name}${g.river && g.river !== g.name ? ` (${g.river})` : ''} · ${p.province} · ${Math.round(g.pct ?? 0)}% ของตลิ่ง`,
    }));
    p.highways.forEach((h, i) => h.lat != null && out.push({
      id: `${p.province}-h${i}`, province: p.province, kind: 'road', lat: h.lat, lng: h.lng,
      name: `ทางหลวงน้ำท่วม ${h.place || ''}${h.depth_cm ? ` · น้ำ ${h.depth_cm} ซม.` : ''} · ${p.province}`,
    }));
    (p.reports || []).forEach((r, i) => r.lat != null && out.push({
      id: `${p.province}-r${i}`, province: p.province, kind: 'report', lat: r.lat, lng: r.lng,
      name: `คนแจ้ง: ${r.title}${r.depth ? ` · น้ำ${r.depth}` : ''} · ${p.province} (${r.source})`,
    }));
  }
  return out;
}

function FloodMap({ points, selected, onPick }) {
  const el = useRef(null);
  const mapRef = useRef(null);
  const readyRef = useRef(false);
  const pickRef = useRef(onPick);
  pickRef.current = onPick;
  const pointsRef = useRef(points);
  pointsRef.current = points;

  const push = useCallback(() => {
    const map = mapRef.current;
    if (!map || !readyRef.current) return;
    map.getSource('pts')?.setData({
      type: 'FeatureCollection',
      features: pointsRef.current.map((p) => ({
        type: 'Feature', geometry: { type: 'Point', coordinates: [p.lng, p.lat] },
        properties: { province: p.province, name: p.name, color: POINT[p.kind].color },
      })),
    });
  }, []);

  const frame = useCallback((province) => {
    const map = mapRef.current;
    if (!map || !readyRef.current) return;
    const pts = pointsRef.current.filter((p) => !province || p.province === province);
    map.fitBounds(bounds(pts) || THAILAND, { padding: 40, maxZoom: 10, duration: 600 });
  }, []);

  useEffect(() => {
    const map = new maplibregl.Map({ container: el.current, style: baseStyle(), bounds: THAILAND, attributionControl: { compact: true } });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-left');
    const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 8 });
    map.on('load', () => {
      map.addSource('pts', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
      map.addLayer({
        id: 'pts', type: 'circle', source: 'pts',
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 5, 4, 10, 7],
          'circle-color': ['get', 'color'], 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 1.2,
        },
      });
      map.on('click', 'pts', (e) => {
        const province = e.features?.[0]?.properties?.province;
        if (province) pickRef.current(province);
      });
      map.on('mousemove', 'pts', (e) => {
        const f = e.features?.[0];
        if (!f) return;
        map.getCanvas().style.cursor = 'pointer';
        popup.setLngLat(f.geometry.coordinates).setText(f.properties.name).addTo(map);
      });
      map.on('mouseleave', 'pts', () => {
        map.getCanvas().style.cursor = '';
        popup.remove();
      });
      readyRef.current = true;
      push();
      frame(null);
    });
    mapRef.current = map;
    return () => {
      popup.remove();
      map.remove();
      mapRef.current = null;
      readyRef.current = false;
    };
  }, [push, frame]);

  useEffect(push, [points, push]);
  useEffect(() => frame(selected), [selected, frame]);

  return (
    <div className="relative h-[420px] lg:h-[520px] rounded-xl overflow-hidden border border-slate-200 bg-slate-100">
      {/* inline position: maplibre-gl.css sets .maplibregl-map { position: relative } over a class */}
      <div ref={el} style={{ position: 'absolute', inset: 0 }} />
      <div className="absolute bottom-2 left-2 flex flex-col gap-1 rounded-lg bg-white border border-slate-200 px-2.5 py-2 text-[11px] text-slate-700">
        {Object.entries(POINT).map(([k, v]) => (
          <span key={k} className="inline-flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full" style={{ background: v.color }} />
            {v.label} <b className="tabular-nums">{points.filter((p) => p.kind === k).length}</b>
          </span>
        ))}
      </div>
    </div>
  );
}

function ProvinceCard({ p, ai, selected, onPick }) {
  const lv = LEVEL[p.level];
  return (
    <article className={`rounded-xl border bg-white p-4 flex flex-col gap-2 ${selected ? 'border-blue-500 ring-1 ring-blue-500' : 'border-slate-200'}`}>
      <button type="button" onClick={() => onPick(p.province)} className={`flex flex-wrap items-center gap-2 text-left cursor-pointer ${FOCUS}`}>
        <h3 className="text-[15px] font-semibold text-slate-900">{p.province}</h3>
        <Badge tone={lv.tone} dot>{lv.label}</Badge>
        <span className="text-xs text-slate-500">{p.region}</span>
        <span className="ml-auto text-xs text-blue-700">ดูบนแผนที่</span>
      </button>
      <p className="text-sm text-slate-800 leading-6">{ai?.summary || p.summary}</p>
      {ai?.analysis && <p className="text-[13px] text-slate-700 leading-6"><b>วิเคราะห์:</b> {ai.analysis}</p>}
      {ai?.advice && <p className="text-[13px] text-slate-700 leading-6"><b>คำแนะนำ:</b> {ai.advice}</p>}
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
        <span>ล้นตลิ่ง <b className="text-slate-900">{p.counts.overflow}</b></span>
        <span>น้ำสูง <b className="text-slate-900">{p.counts.high}</b></span>
        <span>กำลังขึ้น <b className="text-slate-900">{p.counts.rising}</b></span>
        <span>ทางหลวงน้ำท่วม <b className="text-slate-900">{p.counts.highways}</b></span>
        <span>คนแจ้ง <b className="text-slate-900">{p.counts.reports || 0}</b></span>
        <span>ฝน 24 ชม. สูงสุด <b className="text-slate-900">{Math.round(p.rain.max_mm)} มม.</b></span>
      </div>
      {p.gauges.length > 0 && (
        <details className="text-xs text-slate-700">
          <summary className="cursor-pointer text-slate-600">จุดวัดน้ำที่ล้นตลิ่งหรือน้ำสูง {p.gauges.length} จุด</summary>
          <ul className="mt-1.5 flex flex-col gap-1">
            {p.gauges.map((g, i) => (
              <li key={i}>
                {g.name}{g.river && g.river !== g.name ? ` · ${g.river}` : ''}{g.amphoe ? ` · อ.${g.amphoe}` : ''} —{' '}
                <b className={g.level >= 5 ? 'text-red-700' : 'text-amber-700'}>{Math.round(g.pct ?? 0)}% ของตลิ่ง</b> {TREND[g.trend]}
              </li>
            ))}
          </ul>
        </details>
      )}
      {p.highways.length > 0 && (
        <details className="text-xs text-slate-700">
          <summary className="cursor-pointer text-slate-600">ทางหลวงน้ำท่วม {p.highways.length} จุด</summary>
          <ul className="mt-1.5 flex flex-col gap-1">
            {p.highways.map((h, i) => (
              <li key={i}>{h.place || h.title}{h.amphoe ? ` · อ.${h.amphoe}` : ''}{h.depth_cm ? ` · น้ำ ${h.depth_cm} ซม.` : ''}{h.closure ? ` · ${h.closure}` : ''}</li>
            ))}
          </ul>
        </details>
      )}
      {p.reports?.length > 0 && (
        <details className="text-xs text-slate-700">
          <summary className="cursor-pointer text-slate-600">เรื่องที่คนแจ้ง {p.counts.reports} เรื่อง (ยังไม่ยืนยัน)</summary>
          <ul className="mt-1.5 flex flex-col gap-1">
            {p.reports.map((r, i) => (
              <li key={i}>
                <b>{r.title}</b>{r.depth ? ` · น้ำ${r.depth}` : ''}{r.text ? ` · ${r.text.slice(0, 120)}` : ''}
                <span className="text-slate-500"> · {r.source}{r.ts ? `, ${agoText(r.ts)}` : ''}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </article>
  );
}

export default function ProvinceFloodSection({ isActive }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const [region, setRegion] = useState('');
  const [province, setProvince] = useState('');
  const [selected, setSelected] = useState(null);

  const load = useCallback(() => {
    fetchProvinces().then((d) => { setData(d); setError(false); }).catch(() => setError(true));
  }, []);
  useEffect(() => {
    if (!isActive) return undefined;
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [isActive, load]);

  const all = useMemo(() => data?.provinces || [], [data]);
  const inRegion = useMemo(() => all.filter((p) => !region || p.region === region), [all, region]);
  const shown = useMemo(() => inRegion.filter((p) => !province || p.province === province), [inRegion, province]);
  // One province picked: show its card even when its water is normal
  const affected = shown.filter((p) => province || p.level !== 'normal');
  const normal = province ? [] : shown.filter((p) => p.level === 'normal');
  const provinceOptions = useMemo(() => [...inRegion].sort((a, b) => a.province.localeCompare(b.province, 'th')), [inRegion]);
  const points = useMemo(() => toPoints(shown), [shown]);
  const ai = data?.ai;
  const pick = (province) => setSelected((s) => (s === province ? null : province));
  const perRegion = useMemo(() => {
    const n = {};
    for (const p of all) if (p.level !== 'normal') n[p.region] = (n[p.region] || 0) + 1;
    return n;
  }, [all]);

  if (error && !data) return <ErrorState message="โหลดข้อมูลน้ำท่วมรายจังหวัดไม่สำเร็จ" onRetry={load} />;
  if (!data) return <Skeleton className="h-[520px] rounded-xl" />;
  const c = data.counts || {};

  return (
    <div className="flex flex-col gap-4">
      <StatusBanner tone={c.critical ? 'red' : c.flood ? 'yellow' : c.watch ? 'blue' : 'green'}
        label={`วิกฤต ${c.critical || 0} · ล้นตลิ่ง/ท่วม ${c.flood || 0} · เฝ้าระวัง ${c.watch || 0} · ปกติ ${c.normal || 0} จังหวัด`}>
        {ai?.overview || 'สรุปจากจุดวัดระดับน้ำ ฝน และทางหลวงที่น้ำท่วม ในทุกจังหวัด'}
      </StatusBanner>

      <Card className="p-4 flex flex-col gap-3">
        <SectionHeader
          id="province-flood-title"
          title="น้ำท่วมรายจังหวัด"
          description={`อัปเดต ${fmtDateTime(data.updated_at)} (${agoText(data.updated_at)}) · อ่านข้อมูลใหม่ทุก 30 นาที${ai?.generated_at ? ` · AI วิเคราะห์เมื่อ ${fmtDateTime(ai.generated_at)}` : ''}`}
        />
        <div role="group" aria-label="เลือกภาค" className="flex flex-wrap gap-2">
          {[['', 'ทุกภาค'], ...REGIONS.map((r) => [r, r])].map(([id, label]) => (
            <button key={id || 'all'} type="button" aria-pressed={region === id} onClick={() => { setRegion(id); setProvince(''); setSelected(null); }}
              className={`cursor-pointer inline-flex items-center gap-1.5 rounded-lg border px-3 h-8 text-xs font-medium ${FOCUS} ${region === id ? CHIP_ON : CHIP_OFF}`}>
              {label} {id && <span className="tabular-nums opacity-80">{perRegion[id] || 0}</span>}
            </button>
          ))}
          <select aria-label="เลือกจังหวัด" value={province} onChange={(e) => { setProvince(e.target.value); setSelected(e.target.value || null); }}
            className={`cursor-pointer rounded-lg border px-2 h-8 text-xs font-medium ${FOCUS} ${province ? CHIP_ON : CHIP_OFF}`}>
            <option value="">ทุกจังหวัด</option>
            {provinceOptions.map((p) => (
              <option key={p.province} value={p.province}>
                {p.province}{p.level !== 'normal' ? ` · ${LEVEL[p.level].label}` : ''}
              </option>
            ))}
          </select>
        </div>
        <FloodMap points={points} selected={selected} onPick={pick} />
        {data.ai_error && !ai && <p className="text-xs text-slate-500">ยังไม่มีบทวิเคราะห์จาก AI แสดงสรุปจากตัวเลขแทน</p>}
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {affected.map((p) => (
          <ProvinceCard key={p.province} p={p} ai={ai?.provinces?.[p.province]} selected={selected === p.province} onPick={pick} />
        ))}
      </div>
      {normal.length > 0 && (
        <p className="text-xs text-slate-600 px-1">
          ระดับน้ำปกติ {normal.length} จังหวัด: {normal.map((p) => p.province).join(' · ')}
        </p>
      )}
      <p className="text-[11px] text-slate-500 leading-4 px-1">
        ข้อมูลจากคลังข้อมูลน้ำแห่งชาติ (สสน.) จุดวัดระดับน้ำและฝนทั่วประเทศ, กรมทางหลวง (ทางหลวงที่น้ำท่วม) และเรื่องที่คนแจ้ง
        (Longdo Traffic ทั่วประเทศ, แจ้งผ่านเว็บนี้, Traffy Fondue ใน กทม.) ซึ่งยังไม่ได้ยืนยัน ·
        ยังไม่มีจำนวนผู้ประสบภัยของ ปภ. เพราะไม่มีช่องทางดึงข้อมูลอัตโนมัติ · บทวิเคราะห์ AI อาจผิดพลาดได้
      </p>
    </div>
  );
}
