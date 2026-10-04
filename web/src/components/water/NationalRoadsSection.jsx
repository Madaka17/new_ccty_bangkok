// "ถนนน้ำท่วม" tab of the Water page: roads in the whole country that are flooded now (Department of Highways)
// and main roads that may flood in the next 7 days because they run near a gauge over the bank or a dam that is
// almost full, with Qwen's chance and reason for each (/api/flood/forecast, national_forecast.py).
import { useEffect, useMemo, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { Badge, Card, ErrorState, SectionHeader, Skeleton } from '../dashboard/ui.jsx';
import { StatusBanner } from '../dashboard/primitives.jsx';
import { agoText, fmtDateTime } from '../dashboard/format.js';
import { baseStyle } from './WaterMap.jsx';
import { CHANCE, useFloodForecast } from './forecastData.js';

const THAILAND = [[97.3, 5.6], [105.7, 20.5]];
const COLOR = { flooded: '#7c3aed', high: '#dc2626', medium: '#f59e0b', low: '#3b82f6' };
const CHANCE_RANK = { high: 0, medium: 1, low: 2 };
const FLOODED_SHOWN = 40;

function RoadMap({ points }) {
  const el = useRef(null);
  const mapRef = useRef(null);
  const pointsRef = useRef(points);
  pointsRef.current = points;

  useEffect(() => {
    const map = new maplibregl.Map({ container: el.current, style: baseStyle(), bounds: THAILAND, attributionControl: { compact: true } });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-left');
    const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 8 });
    map.on('load', () => {
      map.addSource('pts', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
      map.addLayer({
        id: 'pts', type: 'circle', source: 'pts',
        paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 5, 4, 10, 7], 'circle-color': ['get', 'color'],
          'circle-stroke-color': '#ffffff', 'circle-stroke-width': 1.2 },
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
      mapRef.current = map;
      map.getSource('pts').setData(toGeo(pointsRef.current));
    });
    return () => {
      popup.remove();
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    mapRef.current?.getSource('pts')?.setData(toGeo(points));
  }, [points]);

  return (
    <div className="relative h-[380px] lg:h-[480px] rounded-xl overflow-hidden border border-slate-200 bg-slate-100">
      {/* inline position: maplibre-gl.css sets .maplibregl-map { position: relative } over a class */}
      <div ref={el} style={{ position: 'absolute', inset: 0 }} />
      <div className="absolute bottom-2 left-2 flex flex-col gap-1 rounded-lg bg-white border border-slate-200 px-2.5 py-2 text-[11px] text-slate-700">
        {[['flooded', 'ท่วมอยู่ตอนนี้'], ['high', 'เสี่ยงสูงใน 7 วัน'], ['medium', 'เสี่ยงปานกลาง'], ['low', 'เสี่ยงต่ำ']].map(([k, label]) => (
          <span key={k} className="inline-flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full" style={{ background: COLOR[k] }} /> {label}
          </span>
        ))}
      </div>
    </div>
  );
}

function toGeo(points) {
  return {
    type: 'FeatureCollection',
    features: points.map((p) => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [p.lng, p.lat] }, properties: { name: p.name, color: COLOR[p.kind] } })),
  };
}

export default function NationalRoadsSection({ isActive }) {
  const { data, error, load } = useFloodForecast(isActive);
  const [allFlooded, setAllFlooded] = useState(false);
  const items = data?.ai?.roads?.items || {};
  const flooded = useMemo(() => data?.roads?.flooded || [], [data]);
  const risk = useMemo(
    () => (data?.roads?.risk || []).map((r) => ({ ...r, ai: items[`${r.road}|${r.province}`] }))
      .sort((a, b) => CHANCE_RANK[a.ai?.chance || 'low'] - CHANCE_RANK[b.ai?.chance || 'low'] || b.pct - a.pct),
    [data, items],
  );
  const points = useMemo(() => [
    ...flooded.filter((r) => r.lat != null).map((r) => ({ lat: r.lat, lng: r.lng, kind: 'flooded', name: `ท่วมอยู่: ${r.road} · ${r.province}${r.depth_cm ? ` · น้ำ ${r.depth_cm} ซม.` : ''}` })),
    ...risk.map((r) => ({ lat: r.lat, lng: r.lng, kind: r.ai?.chance || 'low', name: `${r.road} · ${r.province} · ใกล้${r.near}` })),
  ], [flooded, risk]);

  if (error && !data) return <ErrorState message="โหลดข้อมูลถนนน้ำท่วมไม่สำเร็จ" onRetry={load} />;
  if (!data) return <Skeleton className="h-[480px] rounded-xl" />;
  if (!data.roads) return <p className="text-sm text-slate-600 px-1">ระบบกำลังรวบรวมถนนน้ำท่วมรอบแรก ลองใหม่ในอีกไม่กี่นาที</p>;

  const high = risk.filter((r) => r.ai?.chance === 'high').length;
  const byProvince = flooded.reduce((m, r) => ({ ...m, [r.province]: [...(m[r.province] || []), r] }), {});
  const provinces = Object.entries(byProvince).sort((a, b) => b[1].length - a[1].length);

  return (
    <div className="flex flex-col gap-4">
      <StatusBanner tone={flooded.length ? 'red' : high ? 'yellow' : 'green'} label={`ท่วมอยู่ ${flooded.length} จุด · เสี่ยงใน 7 วัน ${risk.length} สาย`}>
        {data.ai?.roads?.overview || (flooded.length ? `ทางหลวงน้ำท่วม ${flooded.length} จุด ใน ${provinces.length} จังหวัด` : 'ตอนนี้ไม่มีทางหลวงที่น้ำท่วม')}
      </StatusBanner>

      <Card className="p-4 flex flex-col gap-3">
        <SectionHeader id="roads-map-title" title="แผนที่ถนนน้ำท่วมทั่วประเทศ"
          description={`อัปเดต ${fmtDateTime(data.updated_at)} (${agoText(data.updated_at)})`} />
        <RoadMap points={points} />
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card className="p-4 flex flex-col gap-2">
          <SectionHeader id="roads-risk-title" title={`ถนนที่อาจท่วมใน 7 วัน ${risk.length} สาย`} description="ถนนสายหลักที่อยู่ใกล้จุดน้ำล้นตลิ่ง หรือใกล้เขื่อนที่น้ำเกือบเต็ม" />
          {risk.length === 0 && <p className="text-sm text-slate-600">ยังไม่พบถนนสายหลักที่เสี่ยง</p>}
          <ul className="flex flex-col divide-y divide-slate-100">
            {risk.map((r) => {
              const ch = CHANCE[r.ai?.chance || 'low'];
              return (
                <li key={`${r.road}|${r.province}`} className="py-2.5 flex flex-col gap-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-slate-900">{r.road}</span>
                    <span className="text-xs text-slate-500">{r.province}</span>
                    {r.ai && <Badge tone={ch.tone} dot>{ch.label}</Badge>}
                  </div>
                  <p className="text-xs text-slate-600">ใกล้{r.near} ({r.near_kind === 'dam' ? `น้ำ ${r.pct}% ของเขื่อนใน 7 วัน` : `น้ำ ${r.pct}% ของตลิ่ง`})</p>
                  {r.ai?.note && <p className="text-[13px] text-slate-800 leading-6">{r.ai.note}</p>}
                </li>
              );
            })}
          </ul>
        </Card>

        <Card className="p-4 flex flex-col gap-2">
          <SectionHeader id="roads-now-title" title={`ทางหลวงที่น้ำท่วมตอนนี้ ${flooded.length} จุด`} description="จากกรมทางหลวง" />
          {flooded.length === 0 && <p className="text-sm text-slate-600">ตอนนี้ไม่มีทางหลวงที่น้ำท่วม</p>}
          <ul className="flex flex-col gap-2">
            {provinces.slice(0, allFlooded ? undefined : 12).map(([province, rows]) => (
              <li key={province} className="text-sm">
                <p className="font-medium text-slate-900">{province} <span className="text-xs text-slate-500">{rows.length} จุด</span></p>
                <ul className="mt-0.5 flex flex-col gap-0.5 text-xs text-slate-700">
                  {rows.slice(0, allFlooded ? undefined : 4).map((r, i) => (
                    <li key={i}>{r.road}{r.amphoe ? ` · อ.${r.amphoe}` : ''}{r.depth_cm ? ` · น้ำ ${r.depth_cm} ซม.` : ''}{r.closure ? ` · ${r.closure}` : ''}</li>
                  ))}
                  {!allFlooded && rows.length > 4 && <li className="text-slate-500">และอีก {rows.length - 4} จุด</li>}
                </ul>
              </li>
            ))}
          </ul>
          {(provinces.length > 12 || flooded.length > FLOODED_SHOWN) && (
            <button type="button" onClick={() => setAllFlooded((v) => !v)} className="self-start text-xs text-blue-700 cursor-pointer">
              {allFlooded ? 'ย่อ' : `ดูทั้งหมด ${flooded.length} จุด`}
            </button>
          )}
        </Card>
      </div>

      <p className="text-[11px] text-slate-500 leading-4 px-1">
        ทางหลวงที่น้ำท่วมจากกรมทางหลวง · ถนนเสี่ยงคือถนนสายหลักจาก OpenStreetMap ที่อยู่ห่างจุดวัดน้ำล้นตลิ่งหรือเขื่อนที่น้ำเกือบเต็มไม่เกิน 1.5 กม.
        ไม่ได้รู้ความสูงของถนน · โอกาสท่วมประเมินโดย AI (Qwen) อาจผิดพลาดได้
      </p>
    </div>
  );
}
