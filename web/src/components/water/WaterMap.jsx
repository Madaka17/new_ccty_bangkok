import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { fetchWaterMap } from '../../lib/api.js';
import { Card, SectionHeader, Button, Segmented, Skeleton, FOCUS } from '../dashboard/ui.jsx';
import { agoText } from '../dashboard/format.js';

const POLL_MS = 120000;
const SELECT = `h-10 w-full rounded-lg border border-slate-300 bg-white px-2.5 text-sm text-slate-800 ${FOCUS}`;

// Status scale per layer, in legend order. Colours read on the light OSM base in both themes.
const LAYERS = {
  water: {
    label: 'ระดับน้ำ',
    note: 'คลอง: เทียบตลิ่งที่ต่ำกว่า (สนน. กทม.) · แม่น้ำ: เทียบตลิ่ง (สสน.)',
    status: [
      ['overflow', 'ล้นตลิ่ง', '#dc2626'],
      ['high', 'ใกล้ล้น', '#d97706'],
      ['normal', 'ปกติ', '#059669'],
      ['low', 'น้ำน้อย', '#0284c7'],
      ['offline', 'ขาดข้อมูล', '#94a3b8'],
    ],
  },
  rain: {
    label: 'ฝน 24 ชม.',
    note: 'ฝนสะสม 24 ชม. รายสถานี (คลังข้อมูลน้ำแห่งชาติ) · เกณฑ์กรมอุตุนิยมวิทยา',
    status: [
      ['extreme', 'หนักมาก > 90 มม.', '#7c3aed'],
      ['heavy', 'หนัก 50-90 มม.', '#dc2626'],
      ['moderate', 'ปานกลาง 20-50 มม.', '#d97706'],
      ['light', 'เล็กน้อย ≤ 20 มม.', '#0284c7'],
      ['none', 'ไม่มีฝน', '#94a3b8'],
    ],
  },
  dams: {
    label: 'เขื่อนและน้ำเหนือ',
    note: 'เขื่อนหลักลุ่มเจ้าพระยา รายงานรายวัน (กรมชลประทาน ผ่านคลังข้อมูลน้ำแห่งชาติ)',
    status: [
      ['high', 'น้ำมาก ≥ 90%', '#dc2626'],
      ['normal', 'ปกติ 50-90%', '#059669'],
      ['low', 'น้ำน้อย < 50%', '#d97706'],
    ],
  },
};

const fmt = (v, d = 2) => (v == null ? '–' : Number(v).toFixed(d));
const colorOf = (layer, status) => (LAYERS[layer].status.find((s) => s[0] === status) || [])[2] || '#94a3b8';

// Short value shown in the detail box and the station list
function valueText(p) {
  if (p.kind === 'rain') return `${fmt(p.rain_24h, 1)} มม.`;
  if (p.kind === 'dam') return `${fmt(p.storage_pct, 0)}%`;
  if (p.diff_bank != null) {
    const cm = Math.round(Math.abs(p.diff_bank) * 100);
    return p.diff_bank > 0 ? `ต่ำกว่าตลิ่ง ${cm} ซม.` : `เกินตลิ่ง ${cm} ซม.`;
  }
  return p.msl != null ? `${fmt(p.msl)} ม.รทก.` : '–';
}

function baseStyle() {
  return {
    version: 8,
    sources: {
      base: { type: 'raster', tiles: [`${window.location.origin}/api/tiles/base/{z}/{x}/{y}.png`], tileSize: 256, maxzoom: 19, attribution: '© OpenStreetMap contributors' },
    },
    layers: [{ id: 'base', type: 'raster', source: 'base', paint: { 'raster-saturation': -0.35 } }],
  };
}

function bounds(points) {
  if (!points.length) return null;
  let [w, s, e, n] = [180, 90, -180, -90];
  for (const p of points) {
    w = Math.min(w, p.lng);
    e = Math.max(e, p.lng);
    s = Math.min(s, p.lat);
    n = Math.max(n, p.lat);
  }
  return [[w, s], [e, n]];
}

export default function WaterMap({ isActive, onPickStation }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const [layer, setLayer] = useState('water');
  const [province, setProvince] = useState('');
  const [district, setDistrict] = useState('');
  const [status, setStatus] = useState('');
  const [selected, setSelected] = useState(null);
  const mapEl = useRef(null);
  const mapRef = useRef(null);
  const readyRef = useRef(false);
  const pushRef = useRef(null);   // latest point push, run again once the map has loaded

  const load = useCallback(() => {
    fetchWaterMap()
      .then((d) => {
        setData(d);
        setError(false);
      })
      .catch(() => setError(true));
  }, []);

  useEffect(() => {
    if (!isActive) return;
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [isActive, load]);

  const all = useMemo(() => data?.[layer] || [], [data, layer]);
  const provinces = useMemo(() => [...new Set(all.map((p) => p.province).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'th')), [all]);
  const inArea = useMemo(() => all.filter((p) => (!province || p.province === province) && (!district || p.district === district)), [all, province, district]);
  const districts = useMemo(
    () => [...new Set(all.filter((p) => !province || p.province === province).map((p) => p.district).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'th')),
    [all, province],
  );
  const shown = useMemo(() => inArea.filter((p) => !status || p.status === status), [inArea, status]);
  const counts = useMemo(() => {
    const c = {};
    for (const p of inArea) c[p.status] = (c[p.status] || 0) + 1;
    return c;
  }, [inArea]);

  // Switching layer resets the filters that may not exist on the new one
  const pickLayer = (k) => {
    setLayer(k);
    setProvince('');
    setDistrict('');
    setStatus('');
    setSelected(null);
  };
  const clear = () => {
    setProvince('');
    setDistrict('');
    setStatus('');
    setSelected(null);
  };

  // Map: created once, points pushed in as GeoJSON
  useEffect(() => {
    if (!mapEl.current || mapRef.current) return;
    const map = new maplibregl.Map({ container: mapEl.current, style: baseStyle(), center: [100.55, 13.78], zoom: 9.3, attributionControl: { compact: true } });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-left');
    map.on('load', () => {
      map.addSource('pts', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
      map.addLayer({
        id: 'pts-sel',
        type: 'circle',
        source: 'pts',
        filter: ['==', ['get', 'sel'], true],
        paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 8, 9, 13, 14], 'circle-color': '#1d4ed8', 'circle-opacity': 0.25 },
      });
      map.addLayer({
        id: 'pts',
        type: 'circle',
        source: 'pts',
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 6, ['get', 'r'], 13, ['*', ['get', 'r'], 1.8]],
          'circle-color': ['get', 'color'],
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 1.5,
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

  // A page shown after being hidden needs the canvas re-measured
  useEffect(() => {
    if (isActive) setTimeout(() => mapRef.current?.resize(), 50);
  }, [isActive]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const push = () => {
      // Alarm states drawn last (on top) and a little larger
      const order = LAYERS[layer].status.map((s) => s[0]);
      const sorted = [...shown].sort((a, b) => order.indexOf(b.status) - order.indexOf(a.status));
      map.getSource('pts')?.setData({
        type: 'FeatureCollection',
        features: sorted.map((p) => ({
          type: 'Feature',
          geometry: { type: 'Point', coordinates: [p.lng, p.lat] },
          properties: { id: p.id, color: colorOf(layer, p.status), r: order.indexOf(p.status) <= 1 ? 5 : 4, sel: p.id === selected },
        })),
      });
    };
    pushRef.current = push;
    if (readyRef.current) push();
  }, [shown, layer, selected]);

  const fitAll = useCallback(() => {
    const b = bounds(shown.length ? shown : all);
    if (b) mapRef.current?.fitBounds(b, { padding: 40, maxZoom: 13, duration: 600 });
  }, [shown, all]);

  // Re-frame when the layer or the area filter changes (not on every poll)
  const frameKey = `${layer}|${province}|${district}|${data ? 1 : 0}`;
  useEffect(() => {
    if (data) fitAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [frameKey]);

  const sel = selected ? all.find((p) => p.id === selected) : null;
  const scale = LAYERS[layer].status;
  const total = inArea.length;

  return (
    <Card aria-labelledby="water-map-title" className="p-0 overflow-hidden">
      <div className="p-5 pb-4">
        <SectionHeader
          id="water-map-title"
          title="แผนที่จุดวัดและเฝ้าระวัง"
          description={`ชี้หรือแตะจุดเพื่อดูรายละเอียด · ${LAYERS[layer].note}`}
          action={<Segmented label="ชั้นข้อมูล" value={layer} onChange={pickLayer} options={Object.entries(LAYERS).map(([k, v]) => [k, v.label])} />}
        />
        <div className="mt-4 grid grid-cols-1 sm:grid-cols-[1fr_1fr_1fr_auto] gap-2 items-end">
          <label className="block">
            <span className="text-xs text-slate-600">จังหวัด</span>
            <select
              value={province}
              onChange={(e) => {
                setProvince(e.target.value);
                setDistrict('');
              }}
              className={SELECT}
              disabled={layer === 'dams'}
            >
              <option value="">ทุกจังหวัด</option>
              {provinces.map((p) => (
                <option key={p}>{p}</option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="text-xs text-slate-600">เขต / อำเภอ</span>
            <select value={district} onChange={(e) => setDistrict(e.target.value)} className={SELECT} disabled={layer === 'dams'}>
              <option value="">ทุกเขต / อำเภอ</option>
              {districts.map((d) => (
                <option key={d}>{d}</option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="text-xs text-slate-600">สถานะ</span>
            <select value={status} onChange={(e) => setStatus(e.target.value)} className={SELECT}>
              <option value="">ทุกสถานะ</option>
              {scale.map(([k, text]) => (
                <option key={k} value={k}>
                  {text} ({counts[k] || 0})
                </option>
              ))}
            </select>
          </label>
          <Button variant="secondary" onClick={clear} disabled={!province && !district && !status}>
            ล้าง
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_300px] border-t border-slate-200">
        <div className="relative h-[420px] lg:h-[520px]">
          {/* inline position: maplibre-gl.css sets .maplibregl-map { position: relative } over a class */}
          <div ref={mapEl} style={{ position: 'absolute', inset: 0 }} />
          {!data && !error && <Skeleton className="absolute inset-0 rounded-none" />}
          {error && !data && <div className="absolute inset-0 grid place-items-center text-sm text-slate-600 bg-slate-50">โหลดข้อมูลแผนที่ไม่สำเร็จ</div>}
          <button type="button" onClick={fitAll} className={`absolute top-2.5 right-2.5 h-8 px-3 rounded-lg bg-white border border-slate-300 text-xs font-medium text-slate-800 shadow-sm hover:bg-slate-50 ${FOCUS}`}>
            ดูพื้นที่ทั้งหมด
          </button>
          <span className="absolute bottom-2 left-2 rounded-md bg-white border border-slate-200 px-2 py-1 text-[11px] text-slate-700">
            แสดง {shown.length} จุด{data?.updated_at ? ` · อัปเดต ${agoText(data.updated_at)}` : ''}
          </span>
        </div>

        <aside className="border-t lg:border-t-0 lg:border-l border-slate-200 bg-slate-50 p-4 flex flex-col gap-3 lg:max-h-[520px] overflow-y-auto">
          <div className="flex items-baseline justify-between">
            <span className="text-xs text-slate-600">{layer === 'dams' ? 'เขื่อนที่ติดตาม' : 'จุดวัดในพื้นที่'}</span>
            <span className="text-2xl font-semibold tabular-nums text-slate-900">
              {total} <span className="text-sm font-normal text-slate-500">{layer === 'dams' ? 'แห่ง' : 'จุด'}</span>
            </span>
          </div>
          {total > 0 && (
            <div className="flex h-1.5 rounded-full overflow-hidden bg-slate-200" aria-hidden="true">
              {scale.map(([k, , color]) => (counts[k] ? <div key={k} style={{ width: `${(counts[k] / total) * 100}%`, background: color }} /> : null))}
            </div>
          )}
          <p className="text-[11px] text-slate-500">กดสถานะเพื่อกรองแผนที่</p>
          <div className="grid grid-cols-2 gap-2">
            {scale.map(([k, text, color]) => {
              const on = status === k;
              return (
                <button
                  key={k}
                  type="button"
                  aria-pressed={on}
                  onClick={() => setStatus(on ? '' : k)}
                  className={`text-left rounded-lg border px-3 py-2 transition-colors ${FOCUS} ${on ? 'border-slate-900 bg-white' : 'border-slate-200 bg-white hover:border-slate-400'}`}
                >
                  <span className="block text-lg font-semibold tabular-nums text-slate-900">{counts[k] || 0}</span>
                  <span className="flex items-center gap-1.5 text-[11px] text-slate-600">
                    <span className="w-2 h-2 rounded-full shrink-0" style={{ background: color }} />
                    {text}
                  </span>
                </button>
              );
            })}
          </div>

          {sel ? (
            <div className="rounded-lg border border-slate-200 bg-white p-3 text-sm">
              <div className="flex items-start justify-between gap-2">
                <b className="text-slate-900 leading-snug">{sel.name}</b>
                <button type="button" onClick={() => setSelected(null)} aria-label="ปิดรายละเอียด" className={`text-slate-400 hover:text-slate-700 ${FOCUS}`}>
                  ✕
                </button>
              </div>
              <p className="text-xs text-slate-500">
                {sel.kind === 'river' ? 'สถานีแม่น้ำ' : sel.kind === 'canal' ? 'สถานีคลอง' : sel.kind === 'rain' ? 'สถานีวัดฝน' : 'เขื่อน'}
                {sel.river ? ` · ${sel.river}` : ''}
                {sel.district ? ` · ${sel.district}` : ''}
                {sel.province ? ` · ${sel.province}` : ''}
              </p>
              <p className="mt-1.5 flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full" style={{ background: colorOf(layer, sel.status) }} />
                <span className="font-medium text-slate-900">{(scale.find((s) => s[0] === sel.status) || [])[1] || sel.status}</span>
                <span className="text-slate-700">· {valueText(sel)}</span>
              </p>
              <dl className="mt-1.5 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs text-slate-600">
                {sel.msl != null && (
                  <>
                    <dt>ระดับน้ำ</dt>
                    <dd className="tabular-nums">{fmt(sel.msl)} ม.รทก.</dd>
                  </>
                )}
                {sel.bank != null && (
                  <>
                    <dt>ตลิ่ง</dt>
                    <dd className="tabular-nums">{fmt(sel.bank)} ม.รทก.</dd>
                  </>
                )}
                {sel.control === 'critical' && (
                  <>
                    <dt>ระดับควบคุม</dt>
                    <dd>เกินระดับควบคุม สนน. ({fmt(sel.control_critical)} ม.)</dd>
                  </>
                )}
                {sel.rain_1h != null && (
                  <>
                    <dt>ฝน 1 ชม.</dt>
                    <dd className="tabular-nums">{fmt(sel.rain_1h, 1)} มม.</dd>
                  </>
                )}
                {sel.kind === 'dam' && (
                  <>
                    <dt>ปริมาตร</dt>
                    <dd className="tabular-nums">
                      {fmt(sel.storage, 0)} / {fmt(sel.max_storage, 0)} ล้าน ลบ.ม.
                    </dd>
                    <dt>ไหลเข้า / ระบาย</dt>
                    <dd className="tabular-nums">
                      {fmt(sel.inflow, 1)} / {fmt(sel.released, 1)} ล้าน ลบ.ม.
                    </dd>
                  </>
                )}
                <dt>เวลาวัด</dt>
                <dd>{sel.kind === 'dam' ? sel.date || '–' : agoText(sel.ts)}</dd>
              </dl>
              <div className="mt-2 flex flex-wrap gap-2">
                {sel.kind === 'river' && sel.station_id && onPickStation && (
                  <Button size="sm" variant="secondary" onClick={() => onPickStation(sel.station_id)}>
                    ดูกราฟแนวโน้ม
                  </Button>
                )}
                {sel.url && (
                  <a href={sel.url} target="_blank" rel="noreferrer" className={`inline-flex items-center h-8 px-3 rounded-lg border border-slate-300 text-xs text-slate-800 hover:bg-slate-50 ${FOCUS}`}>
                    หน้าสถานี สนน.
                  </a>
                )}
              </div>
            </div>
          ) : (
            <p className="text-xs text-slate-500">แตะจุดบนแผนที่เพื่อดูระดับน้ำ ตลิ่ง และเวลาวัด</p>
          )}
        </aside>
      </div>

      <div className="flex flex-wrap items-center gap-2 px-5 py-3 border-t border-slate-200">
        {scale.map(([k, text, color]) => (
          <button
            key={k}
            type="button"
            aria-pressed={status === k}
            onClick={() => setStatus(status === k ? '' : k)}
            className={`inline-flex items-center gap-1.5 h-8 px-3 rounded-full border text-xs ${FOCUS} ${status === k ? 'border-slate-900 text-slate-900' : 'border-slate-200 text-slate-700 hover:border-slate-400'}`}
          >
            <span className="w-2.5 h-2.5 rounded-full" style={{ background: color }} />
            {text}
          </button>
        ))}
        <span className="ml-auto text-[11px] text-slate-500">เวลาวัดแต่ละจุดต่างกัน · จุดสีไม่ใช่ขอบเขตน้ำท่วม</span>
      </div>
    </Card>
  );
}
