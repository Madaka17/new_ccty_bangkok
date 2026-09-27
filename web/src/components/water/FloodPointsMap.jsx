// แผนที่จุดน้ำท่วมตอนนี้: only the places with water on the road right now, from five feeds on one map.
//   - AI on the BMA and iTIC cameras (/api/flood/cameras: puddle / flooded / severe)
//   - BMA road water-level sensors (/api/water/map roads: flood > 10 cm, slight 5-10 cm)
//   - Department of Highways HDMS tickets still open, and flood reports on Longdo Traffic (iTIC / FM91)
//   - reports sent by the public from the report page (/api/flood/user-reports, checked by AI)
// Dry sensors, broken sensors and closed reports are left out. Top of the "ถนนน้ำท่วม" tab of the Water Forecast page.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { fetchWaterMap, fetchFloodCameras, fetchUserReports } from '../../lib/api.js';
import { Card, SectionHeader, Skeleton, Button, FOCUS } from '../dashboard/ui.jsx';
import { agoText, fmtTime } from '../dashboard/format.js';
import { baseStyle, bounds } from './WaterMap.jsx';

const POLL_MS = 60000;
// Feeds in drawing order (last on top): the measured and camera-seen points over the many reports
const SOURCES = [
  { id: 'report', label: 'รายงาน iTIC / FM91', color: '#7c3aed', r: 4 },
  { id: 'hdms', label: 'ทางหลวง (กรมทางหลวง)', color: '#be185d', r: 5 },
  { id: 'user', label: 'ประชาชนแจ้งผ่านเว็บ', color: '#0891b2', r: 6 },
  { id: 'sensor', label: 'เซ็นเซอร์ กทม.', color: '#dc2626', r: 6 },
  { id: 'cam', label: 'AI กล้อง', color: '#b91c1c', r: 7 },
];
const CAM_LEVEL = {
  severe: { label: 'น้ำท่วมหนัก', color: '#7f1d1d' },
  flooded: { label: 'น้ำท่วมผิวจราจร', color: '#dc2626' },
  puddle: { label: 'น้ำขังเล็กน้อย', color: '#f59e0b' },
};
const SENSOR_LEVEL = { flood: { label: 'ท่วมขัง > 10 ซม.', color: '#dc2626' }, slight: { label: 'ท่วมเล็กน้อย 5-10 ซม.', color: '#d97706' } };

// One shape for every feed: where, how bad (label + colour), what was measured or seen, when
function toPoints(roads, cams, users) {
  const out = [];
  for (const u of users?.items || []) {
    out.push({
      id: `user-${u.id}`, src: 'user', lat: u.lat, lng: u.lng, name: u.note || 'ประชาชนแจ้งน้ำท่วม', color: '#0891b2',
      label: 'ประชาชนแจ้ง ยังไม่ยืนยัน', value: `น้ำสูง${u.depth_th} ~${u.depth_cm} ซม.`, ts: u.ts, via: 'แจ้งผ่านเว็บนี้',
      note: u.photo && u.ai_level_th ? `AI ดูรูปแล้ว: ${u.ai_level_th}${u.ai_note ? ` · ${u.ai_note}` : ''}` : '', image: u.photo,
    });
  }
  for (const c of cams?.items || []) {
    const lv = CAM_LEVEL[c.level];
    if (!lv || c.lat == null || c.lng == null) continue;
    out.push({
      id: `cam-${c.camid}`, src: 'cam', lat: c.lat, lng: c.lng, name: c.title, color: lv.color, label: lv.label, faded: c.stale,
      area: [c.road, c.district ? `เขต${c.district}` : c.province].filter(Boolean).join(' · '),
      value: `AI มั่นใจ ${Math.round((c.confidence || 0) * 100)}%`, note: c.note_th, ts: c.frame_ts,
      via: c.kind === 'itic' ? `กล้อง iTIC${c.organization ? ` (${c.organization})` : ''}` : 'กล้อง กทม.',
      image: `/api/flood/cameras/${encodeURIComponent(c.camid)}/image?t=${c.checked_at}`,
    });
  }
  for (const p of roads || []) {
    if (p.lat == null || p.lng == null) continue;
    const area = [p.road, p.district ? (p.province === 'กรุงเทพมหานคร' ? `เขต${p.district}` : p.district) : null, p.province !== 'กรุงเทพมหานคร' ? p.province : null].filter(Boolean).join(' · ');
    if (p.kind === 'sensor' && SENSOR_LEVEL[p.status]) {
      const lv = SENSOR_LEVEL[p.status];
      out.push({ id: p.id, src: 'sensor', lat: p.lat, lng: p.lng, name: p.name, color: lv.color, label: lv.label, area,
        value: `${Math.round(p.depth_cm)} ซม.${p.max_cm != null ? ` · สูงสุด ${Math.round(p.max_cm)} ซม.` : ''}`, ts: p.ts, via: 'เซ็นเซอร์ สำนักการระบายน้ำ กทม.' });
    } else if (p.kind === 'hdms' && p.status === 'hdms') {
      out.push({ id: p.id, src: 'hdms', lat: p.lat, lng: p.lng, name: p.name, color: '#be185d', label: 'ทางหลวงน้ำท่วม', area,
        value: p.depth_cm ? `${String(p.depth_cm).trim()} ซม. (ประเมินด้วยตา)` : '', note: p.description, ts: p.ts, via: 'กรมทางหลวง (HDMS)' });
    } else if (p.kind === 'report' && p.status === 'report') {
      out.push({ id: p.id, src: 'report', lat: p.lat, lng: p.lng, name: p.name, color: '#7c3aed', label: 'มีรายงานน้ำท่วม', area,
        note: p.description, ts: p.ts, via: 'Longdo Traffic (iTIC / FM91)' });
    }
  }
  return out;
}

export default function FloodPointsMap({ isActive, onReport }) {
  const [roads, setRoads] = useState(null);
  const [cams, setCams] = useState(null);
  const [users, setUsers] = useState(null);
  const [error, setError] = useState(false);
  const [on, setOn] = useState({ cam: true, sensor: true, user: true, hdms: true, report: true });
  const [selected, setSelected] = useState(null);
  const mapEl = useRef(null);
  const mapRef = useRef(null);
  const readyRef = useRef(false);
  const pushRef = useRef(null);   // latest point push, run again once the map has loaded

  const load = useCallback(() => {
    fetchWaterMap().then((d) => { setRoads(d.roads || []); setError(false); }).catch(() => setError(true));
    fetchFloodCameras().then(setCams).catch(() => setCams((x) => x || { items: [] }));
    fetchUserReports().then(setUsers).catch(() => setUsers((x) => x || { items: [] }));
  }, []);

  useEffect(() => {
    if (!isActive) return undefined;
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [isActive, load]);

  const all = useMemo(() => toPoints(roads, cams, users), [roads, cams, users]);
  const counts = useMemo(() => {
    const c = {};
    for (const p of all) c[p.src] = (c[p.src] || 0) + 1;
    return c;
  }, [all]);
  const shown = useMemo(() => all.filter((p) => on[p.src]), [all, on]);

  useEffect(() => {
    if (!mapEl.current || mapRef.current) return undefined;
    const map = new maplibregl.Map({ container: mapEl.current, style: baseStyle(), center: [100.55, 13.78], zoom: 9.6, attributionControl: { compact: true } });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-left');
    map.on('load', () => {
      map.addSource('pts', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
      map.addLayer({
        id: 'pts-sel', type: 'circle', source: 'pts', filter: ['==', ['get', 'sel'], true],
        paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 8, 11, 13, 18], 'circle-color': '#1d4ed8', 'circle-opacity': 0.25 },
      });
      map.addLayer({
        id: 'pts', type: 'circle', source: 'pts',
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 6, ['get', 'r'], 13, ['*', ['get', 'r'], 1.8]],
          'circle-color': ['get', 'color'],
          'circle-opacity': ['get', 'op'],
          // camera points get a dark ring, so "seen on camera" reads apart from a sensor of the same colour
          'circle-stroke-color': ['case', ['get', 'cam'], '#0f172a', '#ffffff'],
          'circle-stroke-width': ['case', ['get', 'cam'], 2.5, 1.5],
        },
      });
      map.on('click', 'pts', (e) => {
        const id = e.features?.[0]?.properties?.id;
        if (id) setSelected(id);
      });
      map.on('mouseenter', 'pts', () => (map.getCanvas().style.cursor = 'pointer'));
      map.on('mouseleave', 'pts', () => (map.getCanvas().style.cursor = ''));
      readyRef.current = true;
      pushRef.current?.();
    });
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
      readyRef.current = false;
    };
  }, []);

  // A tab shown after being hidden needs the canvas re-measured
  useEffect(() => {
    if (isActive) setTimeout(() => mapRef.current?.resize(), 50);
  }, [isActive]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const order = SOURCES.map((s) => s.id);
    const push = () => {
      const sorted = [...shown].sort((a, b) => order.indexOf(a.src) - order.indexOf(b.src));
      map.getSource('pts')?.setData({
        type: 'FeatureCollection',
        features: sorted.map((p) => ({
          type: 'Feature',
          geometry: { type: 'Point', coordinates: [p.lng, p.lat] },
          properties: { id: p.id, color: p.color, r: SOURCES.find((s) => s.id === p.src).r, op: p.faded ? 0.45 : 0.95, cam: p.src === 'cam', sel: p.id === selected },
        })),
      });
    };
    pushRef.current = push;
    if (readyRef.current) push();
  }, [shown, selected]);

  const fitAll = useCallback(() => {
    const b = bounds(shown.length ? shown : all);
    if (b) mapRef.current?.fitBounds(b, { padding: 40, maxZoom: 13, duration: 600 });
  }, [shown, all]);

  // Frame the points once, when the first data arrives (not on every poll)
  const loaded = roads !== null && cams !== null && users !== null;
  useEffect(() => {
    if (loaded) fitAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loaded]);

  const sel = selected ? all.find((p) => p.id === selected) : null;
  const staleCams = all.filter((p) => p.src === 'cam' && p.faded).length;

  return (
    <Card aria-labelledby="flood-points-title" className="p-0 overflow-hidden">
      <div className="p-5 pb-4">
        <SectionHeader
          id="flood-points-title"
          title="แผนที่จุดน้ำท่วมตอนนี้"
          description={`เฉพาะจุดที่มีน้ำบนถนน ${all.length ? `${all.length} จุด` : ''} · ไม่รวมเซ็นเซอร์ที่แห้งหรือขัดข้อง และรายงานที่สิ้นสุดแล้ว · แตะจุดเพื่อดูรายละเอียด · รีเฟรชเองทุก 1 นาที`}
          action={onReport && <Button variant="primary" size="sm" onClick={onReport}>📷 แจ้งจุดน้ำท่วม</Button>}
        />
        <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="แหล่งข้อมูลจุดน้ำท่วม">
          {[...SOURCES].reverse().map((s) => (
            <button
              key={s.id}
              type="button"
              aria-pressed={on[s.id]}
              onClick={() => setOn((o) => ({ ...o, [s.id]: !o[s.id] }))}
              className={`inline-flex items-center gap-1.5 h-8 px-3 rounded-full border text-xs ${FOCUS} ${on[s.id] ? 'border-slate-900 text-slate-900' : 'border-slate-200 text-slate-500 opacity-60 hover:border-slate-400'}`}
            >
              <span className="w-2.5 h-2.5 rounded-full" style={{ background: s.color, boxShadow: s.id === 'cam' ? '0 0 0 2px #0f172a' : 'none' }} />
              {s.label}
              <span className="tabular-nums font-semibold">{counts[s.id] || 0}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_300px] border-t border-slate-200">
        <div className="relative h-[420px] lg:h-[500px]">
          {/* inline position: maplibre-gl.css sets .maplibregl-map { position: relative } over a class */}
          <div ref={mapEl} style={{ position: 'absolute', inset: 0 }} />
          {!loaded && !error && <Skeleton className="absolute inset-0 rounded-none" />}
          {error && roads === null && <div className="absolute inset-0 grid place-items-center text-sm text-slate-600 bg-slate-50">โหลดข้อมูลแผนที่ไม่สำเร็จ</div>}
          <button type="button" onClick={fitAll} className={`absolute top-2.5 right-2.5 h-8 px-3 rounded-lg bg-white border border-slate-300 text-xs font-medium text-slate-800 shadow-sm hover:bg-slate-50 ${FOCUS}`}>
            ดูทุกจุด
          </button>
          <span className="absolute bottom-2 left-2 rounded-md bg-white border border-slate-200 px-2 py-1 text-[11px] text-slate-700">แสดง {shown.length} จุด</span>
        </div>

        <aside className="border-t lg:border-t-0 lg:border-l border-slate-200 bg-slate-50 p-4 flex flex-col gap-3 lg:max-h-[500px] overflow-y-auto">
          <div className="flex flex-col gap-1.5 text-[11px] text-slate-600">
            <span className="text-xs font-medium text-slate-700">สีของจุด</span>
            {Object.values(CAM_LEVEL).map((l) => (
              <span key={l.label} className="inline-flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full" style={{ background: l.color, boxShadow: '0 0 0 2px #0f172a' }} />AI กล้อง: {l.label}</span>
            ))}
            {Object.values(SENSOR_LEVEL).map((l) => (
              <span key={l.label} className="inline-flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full" style={{ background: l.color }} />เซ็นเซอร์: {l.label}</span>
            ))}
            {staleCams > 0 && <span className="text-amber-700">จุดจางคือกล้องที่ภาพเก่ากว่า 60 นาที ({staleCams} จุด)</span>}
          </div>

          {sel ? (
            <div className="rounded-lg border border-slate-200 bg-white p-3 text-sm">
              <div className="flex items-start justify-between gap-2">
                <b className="text-slate-900 leading-snug">{sel.name}</b>
                <button type="button" onClick={() => setSelected(null)} aria-label="ปิดรายละเอียด" className={`text-slate-400 hover:text-slate-700 ${FOCUS}`}>
                  ✕
                </button>
              </div>
              <p className="text-xs text-slate-500">{[sel.via, sel.area].filter(Boolean).join(' · ')}</p>
              <p className="mt-1.5 flex flex-wrap items-center gap-1.5">
                <span className="w-2 h-2 rounded-full" style={{ background: sel.color }} />
                <span className="font-medium text-slate-900">{sel.label}</span>
                {sel.value && <span className="text-slate-700">· {sel.value}</span>}
              </p>
              {sel.note && <p className="mt-1.5 text-xs text-slate-700 leading-5">{sel.note}</p>}
              {sel.image && (
                <img src={sel.image} alt={`ภาพที่ AI ใช้ตัดสิน กล้อง ${sel.name}`} loading="lazy" className="mt-2 w-full rounded-md bg-slate-200 object-cover" style={{ aspectRatio: '352 / 288' }} />
              )}
              <p className={`mt-1.5 text-xs ${sel.faded ? 'text-amber-700' : 'text-slate-500'}`}>
                {sel.src === 'cam' ? 'ภาพเมื่อ' : sel.src === 'sensor' ? 'วัดเมื่อ' : 'แจ้งเมื่อ'} {fmtTime(sel.ts)} น. ({agoText(sel.ts)}){sel.faded ? ' · ภาพเก่า กล้องยังไม่ส่งภาพใหม่' : ''}
              </p>
            </div>
          ) : (
            <p className="text-xs text-slate-500">แตะจุดบนแผนที่เพื่อดูระดับน้ำ ภาพ และเวลา · เห็นน้ำท่วมตรงไหน กด "แจ้งจุดน้ำท่วม" ด้านบน</p>
          )}
        </aside>
      </div>

      <p className="px-5 py-3 border-t border-slate-200 text-[11px] text-slate-500 leading-4">
        AI กล้องดูภาพกล้อง กทม. และ iTIC อาจผิดพลาดได้ · เซ็นเซอร์วัดทุก 5 นาที · ทางหลวง รายงาน iTIC / FM91 และประชาชนแจ้งเป็นการแจ้งของคน ยังไม่ผ่านการยืนยัน · จุดสีไม่ใช่ขอบเขตน้ำท่วม
      </p>
    </Card>
  );
}
