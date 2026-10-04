import { useEffect, useRef } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { baseStyle } from './water/WaterMap.jsx';

// The route the chat bot planned around the floods: the line, the water it went round or still meets,
// the jams on it, and a button that opens the same way (via its waypoints) in Google Maps.
const KINDS = {
  avoided: { color: '#dc2626', label: 'น้ำท่วมที่อ้อมให้' },
  flood: { color: '#b91c1c', label: 'น้ำท่วมบนเส้นทาง' },
  wet: { color: '#d97706', label: 'น้ำขังเล็กน้อย' },
};

function features(route) {
  const out = [];
  const add = (list, kind) => {
    for (const h of list || []) {
      if (h.lat != null && h.lng != null) out.push({ type: 'Feature', geometry: { type: 'Point', coordinates: [h.lng, h.lat] }, properties: { color: KINDS[kind].color } });
    }
  };
  add(route.avoided, 'avoided');
  add([...(route.flood_on_route || []), ...(route.flood_at_ends || [])], 'flood');
  add(route.wet_on_route, 'wet');
  return out;
}

export default function RouteCard({ route }) {
  const el = useRef(null);

  useEffect(() => {
    if (!el.current || !route?.line?.length) return undefined;
    const line = route.line.map(([lat, lng]) => [lng, lat]);
    const map = new maplibregl.Map({ container: el.current, style: baseStyle(), bounds: lineBounds(line), fitBoundsOptions: { padding: 28 }, attributionControl: { compact: true }, cooperativeGestures: true });
    map.on('load', () => {
      map.addSource('route', { type: 'geojson', data: { type: 'Feature', geometry: { type: 'LineString', coordinates: line } } });
      map.addLayer({ id: 'route-casing', type: 'line', source: 'route', layout: { 'line-join': 'round', 'line-cap': 'round' }, paint: { 'line-color': '#ffffff', 'line-width': 8 } });
      map.addLayer({ id: 'route', type: 'line', source: 'route', layout: { 'line-join': 'round', 'line-cap': 'round' }, paint: { 'line-color': '#2563eb', 'line-width': 5 } });
      map.addSource('spots', { type: 'geojson', data: { type: 'FeatureCollection', features: features(route) } });
      map.addLayer({ id: 'spots', type: 'circle', source: 'spots', paint: { 'circle-radius': 7, 'circle-color': ['get', 'color'], 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 2 } });
    });
    const pin = (p, color, text) => new maplibregl.Marker({ color }).setLngLat(p).setPopup(new maplibregl.Popup({ offset: 24 }).setText(text)).addTo(map);
    pin(line[0], '#16a34a', `ต้นทาง: ${route.origin?.label || ''}`);
    pin(line[line.length - 1], '#1d4ed8', `ปลายทาง: ${route.destination?.label || ''}`);
    return () => map.remove();
  }, [route]);

  const avoided = route.avoided?.length || 0;
  const floods = (route.flood_on_route?.length || 0) + (route.flood_at_ends?.length || 0);
  const jams = route.jams?.length || 0;
  return (
    <div className="mt-3 rounded-lg border border-cream-200 bg-white overflow-hidden whitespace-normal">
      <div ref={el} className="h-56 w-full" role="img" aria-label="แผนที่เส้นทาง" />
      <div className="px-3 py-2.5 space-y-2 text-[13px] text-ink-700">
        <div className="font-semibold text-ink-900">
          {route.km} กม. · ประมาณ {route.minutes[0]}-{route.minutes[1]} นาที
        </div>
        <div className="flex flex-wrap gap-1.5">
          {avoided > 0 && <span className="rounded-md bg-sage-50 border border-sage-100 px-2 py-0.5 text-sage-700">อ้อมน้ำท่วม {avoided} จุด</span>}
          {floods > 0 && <span className="rounded-md bg-red-50 border border-red-100 px-2 py-0.5 text-red-700">น้ำท่วมบนทาง {floods} จุด</span>}
          {jams > 0 && <span className="rounded-md bg-orange-50 border border-orange-100 px-2 py-0.5 text-orange-700">รถติด {jams} ช่วง</span>}
          {!avoided && !floods && !jams && route.flood_checked && <span className="rounded-md bg-sage-50 border border-sage-100 px-2 py-0.5 text-sage-700">ไม่พบน้ำท่วมบนเส้นทาง</span>}
          {!route.flood_checked && (
            <span className="rounded-md bg-amber-50 border border-amber-100 px-2 py-0.5 text-amber-700">
              {route.flood_missing?.length > 0 ? `ตรวจน้ำท่วมได้ไม่ครบ (ขาด ${route.flood_missing.join(', ')})` : 'ยังตรวจน้ำท่วมไม่ได้'}
            </span>
          )}
        </div>
        <div className="flex flex-wrap gap-x-3 gap-y-1 text-[12px] text-ink-500" aria-label="คำอธิบายสี">
          <Legend color="#2563eb" line>เส้นทางแนะนำ</Legend>
          {avoided > 0 && <Legend color={KINDS.avoided.color}>{KINDS.avoided.label}</Legend>}
          {floods > 0 && <Legend color={KINDS.flood.color}>{KINDS.flood.label}</Legend>}
          {route.wet_on_route?.length > 0 && <Legend color={KINDS.wet.color}>{KINDS.wet.label}</Legend>}
        </div>
        <a href={route.google_maps} target="_blank" rel="noopener noreferrer" className="inline-flex items-center justify-center w-full rounded-lg bg-blue-600 text-white px-4 py-2.5 text-sm font-semibold hover:bg-blue-700 transition-colors duration-200">
          นำทางใน Google Maps
        </a>
      </div>
    </div>
  );
}

function Legend({ color, line, children }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={line ? 'w-4 h-1 rounded' : 'w-2.5 h-2.5 rounded-full'} style={{ background: color }} />
      {children}
    </span>
  );
}

function lineBounds(line) {
  let [w, s, e, n] = [180, 90, -180, -90];
  for (const [lng, lat] of line) {
    w = Math.min(w, lng);
    e = Math.max(e, lng);
    s = Math.min(s, lat);
    n = Math.max(n, lat);
  }
  return [[w, s], [e, n]];
}
