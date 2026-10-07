// Map of cameras for the live camera page and the camera map page. Nearby cameras gather into a numbered circle
// (a tap zooms in); a single camera is a dot coloured by what it shows (live video, a picture, or only on its
// owner's site), ringed pink where our AI flood watch sees water. A tap on a dot opens the camera large.
// RainViewer's newest rain radar picture always lies under the dots (one every 10 minutes; its free service has
// no forecast and no detail past zoom 7). Moving wind lines (Open-Meteo's hourly wind through our server) drift
// over it; a button turns them off, and the choice is remembered. The map frames the cameras again whenever
// frameKey changes, and tells onView what part of the map is on screen after every move.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { baseStyle, bounds } from '../water/WaterMap.jsx';
import { FOCUS } from '../dashboard/ui.jsx';
import { fetchWindField } from '../../lib/api.js';
import { WindLayer } from './windLayer.js';
import { kindOf } from './Tiles.jsx';

export { kindOf };
export const KINDS = [
  { id: 'live', label: 'กล้องสด', color: '#22c55e' },
  { id: 'still', label: 'กล้องภาพนิ่ง', color: '#38bdf8' },
  { id: 'link', label: 'ดูที่เว็บเจ้าของ', color: '#94a3b8' },
];
const COLOR = Object.fromEntries(KINDS.map((k) => [k.id, k.color]));
const FLOOD = '#ec4899';
const CLUSTER = '#0ea5e9';
const THAILAND = [[97.3, 5.6], [105.7, 20.5]];
const RADAR_LIST = 'https://api.rainviewer.com/public/weather-maps.json';
const RADAR_REFRESH_MS = 5 * 60000;
const radarTiles = (host, frame) => [`${host}${frame.path}/256/{z}/{x}/{y}/2/1_1.png`];
const clock = (t) => new Date(t * 1000).toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' });
const BTN = `h-8 px-3 rounded-lg bg-white border border-slate-300 text-xs font-medium text-slate-800 shadow-sm hover:bg-slate-50 ${FOCUS}`;
const isDark = () => document.documentElement.classList.contains('dark');
const WIND_REFRESH_MS = 30 * 60000;   // the server refreshes its copy every 3 hours
const WIND_KEY = 'cameraMap.wind';
const windColor = () => (isDark() ? '#f8fafc' : '#1e3a8a');
const EMPTY = { type: 'FeatureCollection', features: [] };

// Wind lines on unless this viewer turned them off, or asks for less motion
function windDefault() {
  try {
    const saved = localStorage.getItem(WIND_KEY);
    if (saved) return saved === '1';
  } catch { /* storage blocked: use the default */ }
  return !window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
}

// The style has no glyphs, so cluster counts are small DOM labels over the circles
function clusterLabels(map) {
  let shown = {};
  const update = () => {
    if (!map.getSource('cams') || !map.isSourceLoaded('cams')) return;
    const next = {};
    for (const f of map.querySourceFeatures('cams')) {
      const p = f.properties;
      if (!p.cluster || next[p.cluster_id]) continue;
      let m = shown[p.cluster_id];
      if (!m) {
        const el = document.createElement('div');
        el.textContent = p.point_count_abbreviated;
        el.style.cssText = 'pointer-events:none;color:#fff;font:600 11px/1 sans-serif;text-shadow:0 1px 2px rgba(0,0,0,.5)';
        m = new maplibregl.Marker({ element: el }).setLngLat(f.geometry.coordinates).addTo(map);
      }
      next[p.cluster_id] = m;
    }
    for (const id of Object.keys(shown)) if (!next[id]) shown[id].remove();
    shown = next;
  };
  const clear = () => {
    Object.values(shown).forEach((m) => m.remove());
    shown = {};
  };
  return { update, clear };
}

export default function CameraMap({ cameras, flood, onOpen, onView, frameKey, className = 'h-[360px] lg:h-[460px]' }) {
  const el = useRef(null);
  const mapRef = useRef(null);
  const readyRef = useRef(false);
  const labelsRef = useRef(null);
  const byId = useRef(new Map());
  const openRef = useRef(onOpen);
  openRef.current = onOpen;
  const viewRef = useRef(onView);
  viewRef.current = onView;
  const points = useMemo(() => cameras.filter((c) => c.latitude && c.longitude), [cameras]);
  const pointsRef = useRef(points);
  pointsRef.current = points;
  const floodRef = useRef(flood);
  floodRef.current = flood;
  const [radar, setRadar] = useState(null);   // { host, time, path }: the newest rain radar picture
  const windRef = useRef(null);
  const [wind, setWind] = useState(null);       // /api/weather/wind_field answer
  const [windOn, setWindOn] = useState(windDefault);
  const [windHour, setWindHour] = useState(null);
  const counts = useMemo(() => {
    const n = { flood: 0 };
    for (const c of points) {
      n[kindOf(c)] = (n[kindOf(c)] || 0) + 1;
      if (flood?.has(c.camid)) n.flood += 1;
    }
    return n;
  }, [points, flood]);

  const frame = useCallback(() => {
    const map = mapRef.current;
    if (!map || !readyRef.current) return;
    const b = bounds(pointsRef.current.map((c) => ({ lat: c.latitude, lng: c.longitude })));
    map.fitBounds(b || THAILAND, { padding: 40, maxZoom: 13, duration: 600 });
  }, []);

  const push = useCallback(() => {
    const map = mapRef.current;
    if (!map || !readyRef.current) return;
    byId.current = new Map(pointsRef.current.map((c) => [c.camid, c]));
    labelsRef.current?.clear();   // cluster ids change with new data
    map.getSource('cams')?.setData({
      type: 'FeatureCollection',
      features: pointsRef.current.map((c) => ({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [c.longitude, c.latitude] },
        properties: {
          id: c.camid, color: COLOR[kindOf(c)], flood: floodRef.current?.has(c.camid) ? 1 : 0,
          name: [c.short_title || c.title, c.organization].filter(Boolean).join(' · '),
        },
      })),
    });
  }, []);

  const tellView = useCallback(() => {
    const b = mapRef.current?.getBounds();
    if (b) viewRef.current?.({ w: b.getWest(), s: b.getSouth(), e: b.getEast(), n: b.getNorth() });
  }, []);

  const theme = useCallback(() => {
    const map = mapRef.current;
    if (!map?.getLayer('base')) return;
    map.setPaintProperty('base', 'raster-brightness-max', isDark() ? 0.42 : 1);
    map.setPaintProperty('base', 'raster-saturation', isDark() ? -0.8 : -0.35);
  }, []);

  useEffect(() => {
    const map = new maplibregl.Map({ container: el.current, style: baseStyle(), bounds: THAILAND, attributionControl: { compact: true } });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-left');
    const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 8 });
    const labels = clusterLabels(map);
    labelsRef.current = labels;
    map.on('load', () => {
      map.addSource('cams', {
        type: 'geojson', data: { type: 'FeatureCollection', features: [] },
        cluster: true, clusterMaxZoom: 12, clusterRadius: 50,
        clusterProperties: { flood: ['+', ['get', 'flood']] },
      });
      map.addLayer({
        id: 'cams', type: 'circle', source: 'cams', filter: ['!', ['has', 'point_count']],
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 5, 4, 10, 5.5, 15, 8],
          'circle-color': ['get', 'color'],
          'circle-stroke-color': ['case', ['==', ['get', 'flood'], 1], FLOOD, '#0f172a'],
          'circle-stroke-width': ['case', ['==', ['get', 'flood'], 1], 3, 1],
        },
      });
      map.addLayer({
        id: 'clusters', type: 'circle', source: 'cams', filter: ['has', 'point_count'],
        paint: {
          'circle-radius': ['step', ['get', 'point_count'], 13, 20, 16, 100, 20, 500, 25],
          'circle-color': CLUSTER,
          'circle-opacity': 0.9,
          'circle-stroke-color': ['case', ['>', ['get', 'flood'], 0], FLOOD, '#ffffff'],
          'circle-stroke-width': ['case', ['>', ['get', 'flood'], 0], 3, 2],
        },
      });
      map.on('click', 'clusters', async (e) => {
        const f = e.features?.[0];
        if (!f) return;
        const zoom = await map.getSource('cams').getClusterExpansionZoom(f.properties.cluster_id);
        map.easeTo({ center: f.geometry.coordinates, zoom, duration: 500 });
      });
      map.on('click', 'cams', (e) => {
        const cam = byId.current.get(e.features?.[0]?.properties?.id);
        if (cam) openRef.current(cam);
      });
      map.on('mousemove', 'cams', (e) => {
        const f = e.features?.[0];
        if (!f) return;
        map.getCanvas().style.cursor = 'pointer';
        popup.setLngLat(f.geometry.coordinates).setText(f.properties.name).addTo(map);
      });
      map.on('mouseleave', 'cams', () => {
        map.getCanvas().style.cursor = '';
        popup.remove();
      });
      map.on('mouseenter', 'clusters', () => (map.getCanvas().style.cursor = 'pointer'));
      map.on('mouseleave', 'clusters', () => (map.getCanvas().style.cursor = ''));
      map.on('render', labels.update);
      map.on('moveend', tellView);
      // no drawing of its own: only carries the wind credit into the attribution while the lines show
      map.addSource('wind-credit', { type: 'geojson', data: EMPTY, attribution: 'ลม © Open-Meteo' });
      windRef.current = new WindLayer(map, { color: windColor });
      readyRef.current = true;
      theme();
      putRadarRef.current();
      putWindRef.current();
      push();
      frame();
    });
    // Follow the site's light / dark switch
    const watchTheme = new MutationObserver(theme);
    watchTheme.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    mapRef.current = map;
    return () => {
      watchTheme.disconnect();
      windRef.current?.remove();
      windRef.current = null;
      labels.clear();
      popup.remove();
      map.remove();
      mapRef.current = null;
      readyRef.current = false;
    };
  }, [push, frame, tellView, theme]);

  // Newest rain radar picture, asked for again every few minutes
  useEffect(() => {
    const load = () => fetch(RADAR_LIST).then((r) => r.json()).then((d) => {
      const last = d.radar?.past?.at(-1);
      if (last) setRadar((r) => (r?.path === last.path ? r : { host: d.host, ...last }));
    }).catch(() => {});
    load();
    const id = setInterval(load, RADAR_REFRESH_MS);
    return () => clearInterval(id);
  }, []);
  const putRadar = useCallback(() => {
    const map = mapRef.current;
    if (!map || !readyRef.current || !radar) return;
    const src = map.getSource('radar');
    if (src) src.setTiles(radarTiles(radar.host, radar));
    else {
      // under the camera dots
      map.addSource('radar', { type: 'raster', tiles: radarTiles(radar.host, radar), tileSize: 256, maxzoom: 7, attribution: 'เรดาร์ฝน © RainViewer' });
      map.addLayer({ id: 'radar', type: 'raster', source: 'radar', paint: { 'raster-opacity': 0.7 } }, 'cams');
    }
  }, [radar]);
  const putRadarRef = useRef(putRadar);
  putRadarRef.current = putRadar;
  useEffect(putRadar, [putRadar]);

  // Wind field from our server, asked for again every half hour while the lines show
  useEffect(() => {
    if (!windOn) return undefined;
    const load = () => fetchWindField().then((d) => d.frames?.length && setWind(d)).catch(() => {});
    load();
    const id = setInterval(load, WIND_REFRESH_MS);
    return () => clearInterval(id);
  }, [windOn]);
  const putWind = useCallback(() => {
    const map = mapRef.current;
    const layer = windRef.current;
    if (!map || !readyRef.current || !layer) return;
    if (wind && layer.data !== wind) layer.setData(wind);
    const show = windOn && !!wind;
    if (layer.on !== show) layer.setOn(show);
    setWindHour(show ? layer.hour : null);
    const credit = !!map.getLayer('wind-credit');
    if (show && !credit) map.addLayer({ id: 'wind-credit', type: 'line', source: 'wind-credit' });
    if (!show && credit) map.removeLayer('wind-credit');
  }, [wind, windOn]);
  const putWindRef = useRef(putWind);
  putWindRef.current = putWind;
  useEffect(putWind, [putWind]);
  // the hour on the badge moves on with the clock
  useEffect(() => {
    if (!windOn) return undefined;
    const id = setInterval(() => setWindHour(windRef.current?.hour ?? null), 60000);
    return () => clearInterval(id);
  }, [windOn]);
  const toggleWind = () => setWindOn((on) => {
    try {
      localStorage.setItem(WIND_KEY, on ? '0' : '1');
    } catch { /* storage blocked: the choice lasts this visit only */ }
    return !on;
  });

  useEffect(push, [points, flood, push]);
  useEffect(frame, [frameKey, frame]);

  return (
    <div className={`relative ${className} rounded-xl overflow-hidden border border-slate-200 bg-slate-100`}>
      {/* inline position: maplibre-gl.css sets .maplibregl-map { position: relative } over a class */}
      <div ref={el} style={{ position: 'absolute', inset: 0 }} />
      <button type="button" onClick={frame} className={`absolute top-2.5 right-2.5 ${BTN}`}>ดูทุกจุด</button>
      <div className="absolute top-12 right-2.5 flex flex-col items-end gap-1.5">
        {radar && (
          <span className="rounded-lg bg-white border border-slate-300 px-2 py-1 text-xs text-slate-800 shadow-sm tabular-nums">
            เรดาร์ฝน {clock(radar.time)} น.
          </span>
        )}
        <button type="button" onClick={toggleWind} aria-pressed={windOn} className={`${BTN} tabular-nums`}>
          {windOn ? (windHour ? `ลม ${clock(windHour)} น. · ปิด` : 'กำลังโหลดลม…') : 'แสดงลม'}
        </button>
      </div>
      <div className="absolute bottom-2 left-2 flex flex-col gap-1 rounded-lg bg-white border border-slate-200 px-2.5 py-2 text-[11px] text-slate-700">
        {KINDS.filter((k) => counts[k.id]).map((k) => (
          <span key={k.id} className="inline-flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full" style={{ background: k.color }} />
            {k.label} <b className="tabular-nums">{counts[k.id]}</b>
          </span>
        ))}
        <span className="inline-flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full border-2" style={{ borderColor: FLOOD }} />
          AI เห็นน้ำท่วม <b className="tabular-nums">{counts.flood}</b>
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full" style={{ background: CLUSTER }} />
          กลุ่มกล้อง แตะเพื่อซูม
        </span>
        {windOn && windHour && (
          <span className="inline-flex items-center gap-1.5">
            <span className="w-2.5 h-0.5 rounded-full" style={{ background: windColor() }} />
            เส้นลม ไหลไปทางที่ลมพัด
          </span>
        )}
      </div>
    </div>
  );
}
