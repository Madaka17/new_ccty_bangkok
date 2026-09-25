import { useEffect, useMemo, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { motion } from 'framer-motion';
import Hls from 'hls.js';
import { fetchTrafficSummary, fetchLongdoCameras, fetchWaterSummary, fetchAirStations, fetchWindGrid, fetchFloodStatus, fetchFloodStations, fetchFloodReports } from '../lib/api.js';
import { enrichCamerasWithFloodRisk } from '../lib/floodRisk.js';
import { fmtTime } from './dashboard/format.js';
import { Icon } from './dashboard/icons.jsx';


// Vite bundles maplibre into one chunk, so its worker module must be served separately (see public/assets/)
maplibregl.setWorkerUrl(`${window.location.origin}/assets/maplibre-gl-worker.mjs`);

// Pin color
const PIN = '#2563eb';
const PIN_COLOR = {
  กรุงเทพมหานคร: '#2563eb',
  นนทบุรี: '#0891b2',
  นครปฐม: '#059669',
  สมุทรปราการ: '#7c3aed',
  ปทุมธานี: '#d97706',
  ชลบุรี: '#ea580c',
  ฉะเชิงเทรา: '#4f46e5',
};

// Traffic line widths follow Longdo's own style (r_char = road class, 1 = biggest)
const CLASS = ['to-number', ['coalesce', ['get', 'r_char'], 4]];
const LINE_WIDTH = ['interpolate', ['linear'], ['zoom'], 9, 1.5, 12, ['case', ['<=', CLASS, 2], 4, ['<=', CLASS, 5], 2.5, 1.5], 14, ['case', ['<=', CLASS, 2], 7, ['<=', CLASS, 5], 4, 2.5]];
const OFFSET = (dir) => ['interpolate', ['linear'], ['zoom'], 9, 1.5 * dir, 13, 3 * dir];

function mapStyle() {
  const origin = window.location.origin;
  return {
    version: 8,
    sources: {
      base: { type: 'raster', tiles: [`${origin}/api/tiles/base/{z}/{x}/{y}.png`], tileSize: 256, maxzoom: 19, attribution: '© OpenStreetMap contributors' },
      traffic: { type: 'vector', tiles: [`${origin}/api/traffic/tile/{z}/{x}/{y}.pbf`], minzoom: 5, maxzoom: 12, attribution: 'Traffic © Longdo' },
      // OpenFreeMap (OpenMapTiles schema) only for the 3D building footprints + heights
      omt: { type: 'vector', url: 'https://tiles.openfreemap.org/planet', attribution: '© OpenFreeMap' },
      // BTS / MRT / ARL / SRT Red lines + stations, a static snapshot of OSM route relations
      rail: { type: 'geojson', data: `${origin}/rail_bkk.geojson`, attribution: 'Rail © OpenStreetMap' },
    },
    layers: [
      { id: 'base', type: 'raster', source: 'base', paint: { 'raster-saturation': -0.45, 'raster-brightness-min': 0.05, 'raster-contrast': -0.08 } },
      // Flat building footprints for the "รายละเอียดสิ่งปลูกสร้าง" toggle
      {
        id: 'buildings-2d',
        type: 'fill',
        source: 'omt',
        'source-layer': 'building',
        minzoom: 14,
        layout: { visibility: 'none' },
        paint: {
          'fill-color': ['interpolate', ['linear'], ['coalesce', ['get', 'render_height'], 8], 0, '#dbe4ee', 40, '#b6c4d6', 120, '#8fa3bd', 250, '#6b82a3'],
          'fill-opacity': 0.55,
          'fill-outline-color': '#64748b',
        },
      },
      {
        id: 'traffic-forward',
        type: 'line',
        source: 'traffic',
        'source-layer': 'traffic',
        filter: ['!=', ['get', 'fillcolor'], ''],
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-opacity': 0.9, 'line-color': ['concat', '#', ['get', 'fillcolor']], 'line-width': LINE_WIDTH, 'line-offset': OFFSET(-1) },
      },
      {
        id: 'traffic-reverse',
        type: 'line',
        source: 'traffic',
        'source-layer': 'traffic',
        filter: ['!=', ['get', 'fillcolor_r'], ''],
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-opacity': 0.9, 'line-color': ['concat', '#', ['get', 'fillcolor_r']], 'line-width': LINE_WIDTH, 'line-offset': OFFSET(1) },
      },
      // Rail: a white casing under each coloured line so it reads apart from the traffic colours
      { id: 'rail-casing', type: 'line', source: 'rail', filter: ['==', ['get', 'kind'], 'line'], layout: { visibility: 'none', 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#ffffff', 'line-width': ['interpolate', ['linear'], ['zoom'], 9, 4, 14, 8] } },
      { id: 'rail-line', type: 'line', source: 'rail', filter: ['==', ['get', 'kind'], 'line'], layout: { visibility: 'none', 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': ['get', 'colour'], 'line-width': ['interpolate', ['linear'], ['zoom'], 9, 2, 14, 4.5] } },
      {
        id: 'rail-station',
        type: 'circle',
        source: 'rail',
        filter: ['==', ['get', 'kind'], 'station'],
        layout: { visibility: 'none' },
        paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 2.5, 14, 6], 'circle-color': '#ffffff', 'circle-stroke-color': ['get', 'colour'], 'circle-stroke-width': ['interpolate', ['linear'], ['zoom'], 10, 1.5, 14, 3] },
      },
      // 3D buildings (OpenFreeMap heights) from zoom 15, drawn over the flat buildings baked into the base
      // raster; the map tilts itself when zoomed in (auto-tilt effect). Overlay layers (risk layers,
      // heatmaps) are inserted below it.
      {
        id: 'buildings-3d',
        type: 'fill-extrusion',
        source: 'omt',
        'source-layer': 'building',
        minzoom: 15,
        filter: ['!', ['coalesce', ['get', 'hide_3d'], false]],
        paint: {
          'fill-extrusion-color': ['interpolate', ['linear'], ['coalesce', ['get', 'render_height'], 8], 0, '#cbd5e1', 40, '#94a3b8', 120, '#64748b', 250, '#334155'],
          'fill-extrusion-height': ['interpolate', ['linear'], ['zoom'], 15, 0, 15.6, ['coalesce', ['get', 'render_height'], 8]],
          'fill-extrusion-base': ['interpolate', ['linear'], ['zoom'], 15, 0, 15.6, ['coalesce', ['get', 'render_min_height'], 0]],
          'fill-extrusion-opacity': 0.85,
        },
      },
      // Invisible points so the OpenFreeMap POIs (hospitals, schools, malls, temples ...) are loaded
      // and queryable; their Thai names are drawn as DOM markers (the style has no glyphs for text)
      { id: 'poi-pts', type: 'circle', source: 'omt', 'source-layer': 'poi', minzoom: 14, paint: { 'circle-radius': 1, 'circle-opacity': 0 } },
    ],
  };
}

// OpenMapTiles poi classes worth a label, with an icon and a Thai name
const POI_KIND = {
  hospital: ['🏥', 'โรงพยาบาล', '#dc2626'], clinic: ['🏥', 'คลินิก', '#dc2626'], doctors: ['🏥', 'คลินิก', '#dc2626'], pharmacy: ['💊', 'ร้านขายยา', '#dc2626'],
  school: ['🏫', 'โรงเรียน', '#2563eb'], college: ['🏫', 'วิทยาลัย', '#2563eb'], university: ['🎓', 'มหาวิทยาลัย', '#2563eb'], kindergarten: ['🏫', 'อนุบาล', '#2563eb'],
  shop: ['🛍️', 'ร้านค้า', '#7c3aed'], grocery: ['🛒', 'ซูเปอร์มาร์เก็ต', '#7c3aed'], mall: ['🏬', 'ห้างสรรพสินค้า', '#7c3aed'], department_store: ['🏬', 'ห้างสรรพสินค้า', '#7c3aed'],
  town_hall: ['🏛️', 'หน่วยงานราชการ', '#b45309'], townhall: ['🏛️', 'หน่วยงานราชการ', '#b45309'], police: ['🚓', 'สถานีตำรวจ', '#b45309'], fire_station: ['🚒', 'สถานีดับเพลิง', '#b45309'], post: ['📮', 'ไปรษณีย์', '#b45309'], bank: ['🏦', 'ธนาคาร', '#b45309'], embassy: ['🏛️', 'สถานทูต', '#b45309'],
  place_of_worship: ['🛕', 'ศาสนสถาน', '#d97706'],
  railway: ['🚉', 'สถานีรถไฟ', '#059669'], bus: ['🚌', 'ป้ายรถเมล์', '#059669'], ferry_terminal: ['⛴️', 'ท่าเรือ', '#059669'], airport: ['✈️', 'สนามบิน', '#059669'], aerodrome: ['✈️', 'สนามบิน', '#059669'],
  lodging: ['🏨', 'โรงแรม', '#0891b2'], hotel: ['🏨', 'โรงแรม', '#0891b2'],
  park: ['🌳', 'สวนสาธารณะ', '#16a34a'], stadium: ['🏟️', 'สนามกีฬา', '#16a34a'], sports_centre: ['🏟️', 'ศูนย์กีฬา', '#16a34a'], golf: ['⛳', 'สนามกอล์ฟ', '#16a34a'],
  museum: ['🏛️', 'พิพิธภัณฑ์', '#9333ea'], attraction: ['📍', 'สถานที่ท่องเที่ยว', '#9333ea'], monument: ['🗿', 'อนุสาวรีย์', '#9333ea'], theatre: ['🎭', 'โรงละคร', '#9333ea'], cinema: ['🎬', 'โรงภาพยนตร์', '#9333ea'],
  parking: ['🅿️', 'ที่จอดรถ', '#475569'], fuel: ['⛽', 'ปั๊มน้ำมัน', '#475569'], charging_station: ['🔌', 'จุดชาร์จ EV', '#475569'],
  market: ['🧺', 'ตลาด', '#ea580c'],
};
// Water layer. Two different measurements share it, so they get two different marker shapes:
//  * road sensors (BMA drainage, Bangkok only) - centimetres of water ON the road, a depth badge
//  * river / canal gauges (ThaiWater, whole metro area) - % of bank capacity, a round dot
const FLOOD_STYLE = {
  flood: { color: '#dc2626', ring: 'rgba(220,38,38,.28)', label: 'น้ำท่วม' },
  slight: { color: '#f59e0b', ring: 'rgba(245,158,11,.28)', label: 'น้ำท่วมเล็กน้อย' },
  normal: { color: '#0ea5e9', ring: 'rgba(14,165,233,.18)', label: 'ปกติ' },
  offline: { color: '#94a3b8', ring: 'rgba(148,163,184,.18)', label: 'เครื่องวัดขัดข้อง' },
};
const GAUGE_STYLE = {
  overflow: { color: '#dc2626', label: 'ล้นตลิ่ง' },
  high: { color: '#f59e0b', label: 'น้ำมาก' },
  normal: { color: '#0284c7', label: 'ปกติ' },
  low: { color: '#94a3b8', label: 'น้ำน้อย' },
};

// Citizen flood reports (Traffy Fondue): a speech-bubble pin, hotter the fresher the report
const REPORT_COLOR = '#7c3aed';
const REPORT_FRESH_S = 3600;

const POI_MAX = 70;
const POI_MIN_ZOOM = 15;
// Label priority: public buildings first, then services, shops last (and capped) so a mall's
// tenants do not crowd out the hospital next door
const POI_TIER = (cls) => (['shop', 'grocery', 'clothing_store', 'department_store', 'lodging', 'hotel', 'parking', 'fuel', 'charging_station', 'bank', 'pharmacy', 'clinic', 'doctors'].includes(cls) ? 2
  : ['mall', 'market', 'park', 'museum', 'attraction', 'monument', 'theatre', 'cinema', 'stadium', 'sports_centre', 'golf', 'post', 'embassy'].includes(cls) ? 1 : 0);
const POI_TIER_MAX = [POI_MAX, 30, 15];
const poiKindOf = (p) => POI_KIND[p.class] || POI_KIND[p.subclass];
const poiTierOf = (p) => POI_TIER(POI_KIND[p.class] ? p.class : p.subclass);

const KIND_TH = { accident: 'อุบัติเหตุ', breakdown: 'รถเสีย / จอดกีดขวาง' };
const agoTh = (ts) => {
  const m = Math.round((Date.now() / 1000 - ts) / 60);
  return m < 1 ? 'เมื่อสักครู่' : m < 60 ? `${m} นาทีก่อน` : `${Math.round(m / 60)} ชม.ก่อน`;
};
// BMA risk-map traffic layers (cpudapp.bangkok.go.th/riskbkk), slimmed by local/pipeline/build_riskbkk_layers.py
// into web/public/riskbkk/<id>.geojson; each is loaded only when first switched on.
const RISK_LAYERS = [
  // accident: Thai RSC cases 2566-2568 pooled into ~110 m cells (n cases, i injured, k killed, y per year, d district, p place)
  { id: 'accident', label: 'จุดเกิดอุบัติเหตุ ปี 2566–2568 (ThaiRSC)', color: '#dc2626', heat: true, weight: 'n', source: 'ศูนย์ข้อมูลอุบัติเหตุ Thai RSC' },
  { id: 'accident_risk', label: 'จุดเสี่ยงอุบัติเหตุ ปี 2566–2568', color: '#be123c' },
  { id: 'risk100', label: '100 จุดเสี่ยงจราจร', color: '#ea580c' },
  { id: 'risk100_solve', label: 'ผลการแก้ไขจุดเสี่ยง (เขียว = เสร็จ)', color: ['case', ['get', 'done'], '#16a34a', '#f59e0b'], legend: '#16a34a' },
  { id: 'friction', label: 'จุดฝืด (รถติดประจำ)', color: '#9333ea' },
  { id: 'js100', label: 'เหตุจราจร จส.100 / FM91 (ข้อมูลเก่า ก.ย. 67)', color: '#e11d48' },
  { id: 'construction', label: 'สถานที่ก่อสร้างอาคารใหญ่', color: '#ca8a04' },
  { id: 'crosswalk', label: 'ทางม้าลาย', color: '#e2e8f0', minzoom: 13 },
  { id: 'rail_crossing', label: 'จุดตัดทางรถไฟ', color: '#78350f' },
  { id: 'bus_stop', label: 'ป้ายรถเมล์', color: '#0284c7', minzoom: 13 },
  { id: 'motorcycle_taxi', label: 'วินมอเตอร์ไซค์', color: '#f97316', minzoom: 13 },
  { id: 'parking', label: 'ที่จอดรถ', color: '#2563eb' },
];

const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// Pulsing warning marker for an incident
function incidentEl(kind) {
  const el = document.createElement('button');
  el.type = 'button';
  el.className = 'cursor-pointer incident-pin';
  el.setAttribute('aria-label', KIND_TH[kind] || 'เหตุการณ์');
  const color = kind === 'breakdown' ? '#d97706' : '#dc2626';
  el.style.cssText = `width:30px;height:30px;border-radius:999px;background:${color};border:3px solid #fff;box-shadow:0 0 0 6px ${color}33,0 2px 8px rgba(15,23,42,.3);color:#fff;font-weight:700;font-size:16px;line-height:1;display:flex;align-items:center;justify-content:center;animation:incident-pulse 1.6s ease-out infinite`;
  el.textContent = '!';
  return el;
}

function pinEl(color, active, floodRisk) {
  const el = document.createElement('button');
  el.type = 'button';
  el.className = 'cursor-pointer';
  if (floodRisk) {
    const borderCol = floodRisk.isOverflow ? '#ef4444' : '#f59e0b';
    const shadow = floodRisk.isOverflow
      ? '0 0 0 4px rgba(239,68,68,0.4), 0 2px 6px rgba(0,0,0,0.3)'
      : '0 0 0 3px rgba(245,158,11,0.4), 0 2px 6px rgba(0,0,0,0.3)';
    el.style.cssText = `width:22px;height:22px;border-radius:999px;background:${color};border:3px solid ${borderCol};box-shadow:${shadow};position:relative;${active ? 'outline:3px solid #0f172a;outline-offset:1px;' : ''}`;
    const badge = document.createElement('span');
    badge.textContent = '🌊';
    badge.style.cssText = 'position:absolute;top:-10px;right:-9px;font-size:11px;line-height:1;pointer-events:none;filter:drop-shadow(0 1px 1px rgba(0,0,0,0.4));';
    el.appendChild(badge);
  } else {
    el.style.cssText = `width:20px;height:20px;border-radius:999px;background:${color};border:3px solid #fff;box-shadow:0 1px 4px rgba(15,23,42,.3);${active ? 'outline:3px solid #0f172a;outline-offset:1px;' : ''}`;
  }
  return el;
}

export default function MapPage({ isActive, cameras, active, incidents, onToggle, onOpenAI, onToast }) {
  const mapEl = useRef(null);
  const mapRef = useRef(null);
  const markersRef = useRef({});
  const incidentMarkersRef = useRef([]);
  const [longdoCameras, setLongdoCameras] = useState([]);
  const [showTraffic, setShowTraffic] = useState(true);
  const [showRail, setShowRail] = useState(false);
  const [riskOn, setRiskOn] = useState({}); // RISK_LAYERS id -> visible
  const [summary, setSummary] = useState(null);
  const [waterSummary, setWaterSummary] = useState(null);
  const [showRainRadar, setShowRainRadar] = useState(false);
  const [radarOpacity, setRadarOpacity] = useState(0.65);
  const [radarTileUrl, setRadarTileUrl] = useState(null);
  const [radarTime, setRadarTime] = useState(null);
  const [showPm, setShowPm] = useState(false);
  // Water layer: BMA road-flood sensors (Bangkok) + ThaiWater river / canal gauges (metro area)
  const [showFlood, setShowFlood] = useState(false);
  const [floodDry, setFloodDry] = useState(false);
  const [showGauges, setShowGauges] = useState(false);
  const [flood, setFlood] = useState(null);
  const [floodAll, setFloodAll] = useState(null);
  const floodMarkersRef = useRef([]);
  const [showReports, setShowReports] = useState(false);
  const [reports, setReports] = useState(null);
  const reportMarkersRef = useRef([]);
  const gaugeMarkersRef = useRef([]);
  // Building details: flat footprints in 2D, POI name labels (DOM markers) and click-for-info on any building
  const [showPlaces, setShowPlaces] = useState(false);
  const showPlacesRef = useRef(false);
  const poiMarkersRef = useRef([]);
  // Wind overlay drawn by us (Open-Meteo grid) so nothing sits on top of the traffic map
  const [showWind, setShowWind] = useState(false);
  const [wind, setWind] = useState(null);
  const windMarkersRef = useRef([]);

  useEffect(() => {
    if (!isActive) return;
    let alive = true;
    const tick = () => fetchWindGrid().then((w) => alive && setWind(w)).catch(() => {});
    tick();
    const id = setInterval(tick, 900000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [isActive]);

  // Arrow per grid point: rotation = direction the wind blows TO, length/colour = speed
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !wind) return;
    for (const m of windMarkersRef.current) m.remove();
    windMarkersRef.current = [];
    if (!showWind) return;
    for (const p of wind.points || []) {
      if (p.speed == null || p.dir == null) continue;
      const kmh = p.speed;
      const color = kmh < 10 ? '#60a5fa' : kmh < 20 ? '#22c55e' : kmh < 35 ? '#f59e0b' : '#ef4444';
      const len = Math.min(34, 14 + kmh * 0.7);
      const el = document.createElement('div');
      el.style.cssText = 'pointer-events:none;display:flex;flex-direction:column;align-items:center;gap:1px';
      el.innerHTML =
        `<svg width="36" height="36" viewBox="-18 -18 36 36" style="transform:rotate(${(p.dir + 180) % 360}deg);opacity:.85">` +
        `<line x1="0" y1="${len / 2}" x2="0" y2="${-len / 2}" stroke="${color}" stroke-width="3" stroke-linecap="round"/>` +
        `<path d="M -5 ${-len / 2 + 7} L 0 ${-len / 2} L 5 ${-len / 2 + 7}" fill="none" stroke="${color}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>` +
        `<span style="font:600 10px/1 var(--font-sans);color:#0f172a;background:rgba(255,255,255,.75);padding:1px 4px;border-radius:4px">${Math.round(kmh)}</span>`;
      windMarkersRef.current.push(new maplibregl.Marker({ element: el }).setLngLat([p.lng, p.lat]).addTo(map));
    }
  }, [wind, showWind]);
  const [air, setAir] = useState(null);

  // PM2.5 stations (Air4Thai) every 10 min while the page is open
  useEffect(() => {
    if (!isActive) return;
    let alive = true;
    const tick = () => fetchAirStations().then((a) => alive && setAir(a)).catch(() => {});
    tick();
    const id = setInterval(tick, 600000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [isActive]);

  // Load Longdo cameras exclusively
  useEffect(() => {
    let alive = true;
    fetchLongdoCameras()
      .then((items) => {
        if (alive && items && items.length) setLongdoCameras(items);
      })
      .catch(() => {
        if (alive && cameras && cameras.length) setLongdoCameras(cameras);
      });
    return () => {
      alive = false;
    };
  }, [cameras]);

  // Water telemetry summary (river, canals, flood risk)
  useEffect(() => {
    if (!isActive) return;
    let alive = true;
    const tick = () => fetchWaterSummary().then((w) => alive && setWaterSummary(w)).catch(() => {});
    tick();
    const id = setInterval(tick, 60000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [isActive]);

  // Current camera list: strictly Longdo Map enriched with real-time flood risk
  const currentCameras = useMemo(() => {
    const base = longdoCameras.length ? longdoCameras : cameras || [];
    return enrichCamerasWithFloodRisk(base, waterSummary);
  }, [longdoCameras, cameras, waterSummary]);

  const floodRiskCount = useMemo(() => {
    return currentCameras.filter((c) => c.floodRisk).length;
  }, [currentCameras]);

  // Create map once
  useEffect(() => {
    if (!isActive || !mapEl.current || mapRef.current) return;
    const map = new maplibregl.Map({ container: mapEl.current, style: mapStyle(), center: [100.55, 13.78], zoom: 11, attributionControl: { compact: true } });
    map.addControl(new maplibregl.NavigationControl({ showCompass: true, visualizePitch: true }), 'top-right');
    mapRef.current = map;
    window.__bkkMap = map; // devtools access
    map.on('error', (e) => console.warn('[map]', e?.error?.message || e));
    return () => {
      map.remove();
      mapRef.current = null;
      markersRef.current = {};
    };
  }, [isActive]);

  // Traffic summary (timestamp + online flag)
  useEffect(() => {
    if (!isActive) return;
    let alive = true;
    const tick = () => fetchTrafficSummary(3).then((s) => alive && setSummary(s)).catch(() => {});
    tick();
    const id = setInterval(tick, 60000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [isActive]);

  // Refresh traffic tiles every 2 min so the colours stay live
  useEffect(() => {
    if (!isActive) return;
    const id = setInterval(() => {
      const map = mapRef.current;
      const src = map?.getSource('traffic');
      if (src?.setTiles) src.setTiles([`${window.location.origin}/api/traffic/tile/{z}/{x}/{y}.pbf?t=${Date.now()}`]);
    }, 60000);
    return () => clearInterval(id);
  }, [isActive]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const apply = () => {
      ['traffic-forward', 'traffic-reverse'].forEach((id) => map.getLayer(id) && map.setLayoutProperty(id, 'visibility', showTraffic ? 'visible' : 'none'));
    };
    if (map.isStyleLoaded()) apply();
    else map.once('load', apply);
  }, [showTraffic]);

  // BMA risk layers: add source + layers the first time one is switched on, then only toggle visibility.
  // Dense layers (accidents) are a heatmap when zoomed out and points from z13.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const onClick = (e) => {
      const p = e.features[0].properties;
      const layer = RISK_LAYERS.find((l) => `risk-${l.id}-pt` === e.features[0].layer.id);
      let title = p.title;
      let info = JSON.parse(p.info || '[]');
      if (p.n != null) {
        // an accident cell: build the text from its short properties
        const years = JSON.parse(p.y || '[]');
        title = `อุบัติเหตุ ${p.n} ครั้ง (ปี 2566–2568)`;
        info = [
          [2566, 2567, 2568].map((yr, i) => (years[i] ? `ปี ${yr}: ${years[i]}` : '')).filter(Boolean).join(' · '),
          `บาดเจ็บ ${p.i} · เสียชีวิต ${p.k}`,
          p.p ? `สถานที่: ${p.p}` : '',
          p.d ? `เขต${p.d}` : '',
        ].filter(Boolean);
      }
      new maplibregl.Popup({ offset: 8, closeButton: true, maxWidth: '300px' })
        .setLngLat(e.features[0].geometry.coordinates)
        .setHTML(
          `<div style="font-size:13px;line-height:1.45"><b>${esc(title)}</b>` +
            info.map((l) => `<br><span style="font-size:12px">${esc(l)}</span>`).join('') +
            `<br><span style="color:#94a3b8;font-size:11px">${esc(layer?.source || 'ข้อมูลจุดเสี่ยง กทม. (riskbkk)')}</span></div>`
        )
        .addTo(map);
    };
    const apply = () => {
      for (const l of RISK_LAYERS) {
        const on = !!riskOn[l.id];
        const src = `risk-${l.id}`;
        if (!map.getSource(src)) {
          if (!on) continue;
          map.addSource(src, { type: 'geojson', data: `${window.location.origin}/riskbkk/${l.id}.geojson`, attribution: 'จุดเสี่ยง © กรุงเทพมหานคร' });
          if (l.heat) {
            const weight = l.weight ? { 'heatmap-weight': ['interpolate', ['linear'], ['get', l.weight], 1, 0.2, 50, 1] } : {};
            map.addLayer({ id: `${src}-heat`, type: 'heatmap', source: src, maxzoom: 13, paint: { ...weight, 'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 9, 6, 13, 14], 'heatmap-opacity': 0.6, 'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 9, 0.08, 13, 0.4] } }, 'buildings-3d');
          }
          map.addLayer(
            {
              id: `${src}-pt`,
              type: 'circle',
              source: src,
              minzoom: l.heat ? 13 : l.minzoom || 0,
              paint: { 'circle-radius': l.weight ? ['interpolate', ['linear'], ['get', l.weight], 1, 3, 20, 6, 200, 11] : ['interpolate', ['linear'], ['zoom'], 10, 3, 15, 6], 'circle-color': l.color, 'circle-stroke-color': '#0f172a', 'circle-stroke-width': 1, 'circle-opacity': 0.9 },
            },
            'buildings-3d'
          );
          map.on('click', `${src}-pt`, onClick);
          map.on('mouseenter', `${src}-pt`, () => (map.getCanvas().style.cursor = 'pointer'));
          map.on('mouseleave', `${src}-pt`, () => (map.getCanvas().style.cursor = ''));
        }
        [`${src}-heat`, `${src}-pt`].forEach((id) => map.getLayer(id) && map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none'));
      }
    };
    if (map.getLayer('buildings-3d')) apply();
    else map.once('styledata', apply);
  }, [riskOn]);

  // BTS / MRT layer toggle; a station click shows its name and line
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const onStationClick = (e) => {
      const p = e.features[0].properties;
      new maplibregl.Popup({ offset: 8, closeButton: true, maxWidth: '260px' })
        .setLngLat(e.features[0].geometry.coordinates)
        .setHTML(
          `<div style="font-size:13px;line-height:1.45"><b>🚇 ${esc(p.name)}</b>` +
            (p.name_en ? `<br><span style="color:#64748b">${esc(p.name_en)}</span>` : '') +
            `<br><span style="color:${esc(p.colour)};font-weight:600">${esc(p.line)}</span></div>`
        )
        .addTo(map);
    };
    const apply = () => {
      ['rail-casing', 'rail-line', 'rail-station'].forEach((id) => map.getLayer(id) && map.setLayoutProperty(id, 'visibility', showRail ? 'visible' : 'none'));
    };
    if (map.getLayer('rail-station')) apply();
    else map.once('styledata', apply);
    map.on('click', 'rail-station', onStationClick);
    return () => map.off('click', 'rail-station', onStationClick);
  }, [showRail]);

  // Fetch RainViewer radar timestamp & tile url
  useEffect(() => {
    if (!isActive) return;
    let alive = true;
    const fetchRadar = () => {
      fetch('https://api.rainviewer.com/public/weather-maps.json')
        .then((res) => {
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          return res.json();
        })
        .then((data) => {
          if (!alive || !data?.host || !data?.radar?.past?.length) return;
          const latest = data.radar.past[data.radar.past.length - 1];
          // Color 2: smooth radar colors
          const url = `${data.host}${latest.path}/256/{z}/{x}/{y}/2/1_1.png`;
          setRadarTileUrl(url);
          const d = new Date(latest.time * 1000);
          setRadarTime(d.toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' }));
        })
        .catch((err) => console.warn('[RainViewer]', err));
    };
    fetchRadar();
    const interval = setInterval(fetchRadar, 60000);
    return () => {
      alive = false;
      clearInterval(interval);
    };
  }, [isActive]);

  // 3D buildings: tilt to 45° when zoomed in to 15+ so the heights show, flat again below 15. A tilt the
  // user sets by hand is left alone until they zoom back out.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    let auto = false;
    let manual = false;
    const onZoom = () => {
      const near = map.getZoom() >= 15;
      if (near && !manual && !auto && map.getPitch() < 10) {
        auto = true;
        map.easeTo({ pitch: 45, duration: 700 });
      } else if (!near && (auto || manual)) {
        if (auto) map.easeTo({ pitch: 0, bearing: 0, duration: 700 });
        auto = manual = false;
      }
    };
    const onPitch = (e) => {
      if (e.originalEvent) manual = true;   // a drag / touch, not our easeTo
    };
    map.on('zoomend', onZoom);
    map.on('pitchstart', onPitch);
    return () => {
      map.off('zoomend', onZoom);
      map.off('pitchstart', onPitch);
    };
  }, [isActive]);

  // Building details toggle: 2D footprints + POI labels + click info. Labels are rebuilt on every
  // moveend from the vector tiles in view (rank = OpenMapTiles importance, lower is bigger).
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    showPlacesRef.current = showPlaces;
    const clearPois = () => {
      for (const m of poiMarkersRef.current) m.remove();
      poiMarkersRef.current = [];
    };
    let lastSig = '';
    const drawPois = () => {
      if (!showPlacesRef.current || map.getZoom() < POI_MIN_ZOOM || !map.getLayer('poi-pts')) {
        clearPois();
        lastSig = '';
        return;
      }
      const raw = map.queryRenderedFeatures({ layers: ['poi-pts'] });
      // same POIs in the same place as last time (tiles unchanged): keep the markers as they are
      const c = map.getCenter();
      const sig = `${raw.length}|${map.getZoom().toFixed(2)}|${c.lng.toFixed(5)},${c.lat.toFixed(5)}`;
      if (sig === lastSig) return;
      lastSig = sig;
      clearPois();
      const seen = new Set();
      const feats = raw
        .map((f) => ({ p: f.properties, c: f.geometry?.coordinates }))
        .filter((f) => f.c && f.p.name && poiKindOf(f.p))
        .map((f) => ({ ...f, tier: poiTierOf(f.p) }))
        .sort((a, b) => a.tier - b.tier || (a.p.rank ?? 99) - (b.p.rank ?? 99));
      const perTier = [0, 0, 0];
      const placed = [];   // screen positions of labels already drawn: skip one that would overlap
      for (const f of feats) {
        if (poiMarkersRef.current.length >= POI_MAX) break;
        if (perTier[f.tier] >= POI_TIER_MAX[f.tier]) continue;
        const key = `${f.p.name}|${Math.round(f.c[0] * 2000)}|${Math.round(f.c[1] * 2000)}`;
        if (seen.has(key)) continue;
        seen.add(key);
        const pt = map.project(f.c);
        if (placed.some((q) => Math.abs(q.x - pt.x) < 110 && Math.abs(q.y - pt.y) < 22)) continue;
        placed.push(pt);
        perTier[f.tier] += 1;
        const [icon, kindTh, color] = poiKindOf(f.p);
        const nameEn = f.p['name:en'] || f.p.name_en;
        const el = document.createElement('button');
        el.type = 'button';
        el.className = 'poi-label';
        el.style.cssText = `display:flex;align-items:center;gap:3px;max-width:170px;padding:2px 6px 2px 4px;border-radius:999px;background:rgba(255,255,255,.92);border:1.5px solid ${color};color:#0f172a;font:500 11px/1.2 var(--font-sans);box-shadow:0 1px 3px rgba(15,23,42,.25);cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis`;
        el.innerHTML = `<span style="font-size:12px">${icon}</span><span style="overflow:hidden;text-overflow:ellipsis">${esc(f.p.name)}</span>`;
        el.title = `${kindTh}: ${f.p.name}`;
        const popup = new maplibregl.Popup({ offset: 12, closeButton: true, maxWidth: '260px' }).setHTML(
          `<div style="font-size:13px;line-height:1.4"><b>${esc(f.p.name)}</b>${nameEn ? `<br><span style="color:#64748b">${esc(nameEn)}</span>` : ''}` +
            `<br><span style="color:${color};font-weight:600">${icon} ${kindTh}</span>${f.p.subclass && f.p.subclass !== f.p.class ? ` <span style="color:#64748b">· ${esc(f.p.subclass)}</span>` : ''}` +
            '<br><span style="color:#94a3b8;font-size:11px">ข้อมูล OpenStreetMap / OpenFreeMap</span></div>'
        );
        poiMarkersRef.current.push(new maplibregl.Marker({ element: el, anchor: 'bottom', offset: [0, -4] }).setLngLat(f.c).setPopup(popup).addTo(map));
      }
    };
    const onBuildingClick = (e) => {
      if (!showPlacesRef.current) return;
      const layers = ['buildings-3d', 'buildings-2d'].filter((id) => map.getLayer(id));
      const hit = map.queryRenderedFeatures(e.point, { layers })[0];
      if (!hit) return;
      const h = Number(hit.properties.render_height ?? 0);
      const base = Number(hit.properties.render_min_height ?? 0);
      const floors = h > 0 ? Math.max(1, Math.round(h / 3.2)) : null;
      // the nearest named POI inside ~40 px is very likely this building's name
      const near = map.queryRenderedFeatures([[e.point.x - 40, e.point.y - 40], [e.point.x + 40, e.point.y + 40]], { layers: ['poi-pts'] })
        .filter((f) => f.properties.name && poiKindOf(f.properties))
        .sort((a, b) => poiTierOf(a.properties) - poiTierOf(b.properties) || (a.properties.rank ?? 99) - (b.properties.rank ?? 99))[0];
      const kind = near && poiKindOf(near.properties);
      new maplibregl.Popup({ offset: 6, closeButton: true, maxWidth: '260px' })
        .setLngLat(e.lngLat)
        .setHTML(
          `<div style="font-size:13px;line-height:1.45"><b>${near ? esc(near.properties.name) : 'อาคาร'}</b>` +
            (kind ? `<br><span style="color:${kind[2]};font-weight:600">${kind[0]} ${kind[1]}</span>` : '') +
            (h > 0 ? `<br>สูงประมาณ <b>${Math.round(h)} ม.</b> (~${floors} ชั้น)${base > 0 ? ` · ยกจากพื้น ${Math.round(base)} ม.` : ''}` : '<br><span style="color:#64748b">ไม่มีข้อมูลความสูง</span>') +
            `<br><span style="color:#94a3b8;font-size:11px">${e.lngLat.lat.toFixed(5)}, ${e.lngLat.lng.toFixed(5)} · OpenStreetMap</span></div>`
        )
        .addTo(map);
    };
    const apply = () => {
      if (map.getLayer('buildings-2d')) map.setLayoutProperty('buildings-2d', 'visibility', showPlaces ? 'visible' : 'none');
      if (showPlaces && map.getZoom() < POI_MIN_ZOOM) map.easeTo({ zoom: POI_MIN_ZOOM, duration: 700 });
      drawPois();
    };
    // idle fires each time the map finishes rendering (also when late tiles come in); moveend covers pans
    const onIdle = () => drawPois();
    // getLayer = the style JSON is applied (isStyleLoaded() is false whenever tiles are still loading)
    if (map.getLayer('poi-pts')) apply();
    else map.once('styledata', apply);
    map.on('idle', onIdle);
    map.on('moveend', onIdle);
    map.on('click', onBuildingClick);
    return () => {
      map.off('idle', onIdle);
      map.off('moveend', onIdle);
      map.off('click', onBuildingClick);
      clearPois();
    };
  }, [showPlaces]);

  // Road-flood sensors: the wet ones every minute, the whole network only when dry ones are shown
  useEffect(() => {
    if (!isActive) return;
    let alive = true;
    const tick = () => fetchFloodStatus().then((d) => alive && setFlood(d)).catch(() => {});
    tick();
    const id = setInterval(tick, 60000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [isActive]);

  useEffect(() => {
    if (!isActive || !floodDry) return;
    let alive = true;
    fetchFloodStations({ limit: 1000 }).then((d) => alive && setFloodAll(d.items)).catch(() => {});
    const id = setInterval(() => fetchFloodStations({ limit: 1000 }).then((d) => alive && setFloodAll(d.items)).catch(() => {}), 300000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [isActive, floodDry]);

  // Traffy Fondue flood complaints; the server refreshes them every 5 min
  useEffect(() => {
    if (!isActive) return;
    let alive = true;
    const tick = () => fetchFloodReports().then((d) => alive && setReports(d)).catch(() => {});
    tick();
    const id = setInterval(tick, 300000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [isActive]);

  const reportPoints = useMemo(() => (reports?.items || []).filter((r) => r.lat && r.lng), [reports]);
  const reportFresh = useMemo(() => reportPoints.filter((r) => Date.now() / 1000 - r.ts <= REPORT_FRESH_S).length, [reportPoints]);
  // Districts with the most reports, busiest first: that is where the sois are under water
  const reportDistricts = useMemo(() => {
    const by = {};
    for (const r of reportPoints) (by[r.district || 'ไม่ระบุเขต'] ||= []).push(r);
    return Object.entries(by).map(([name, items]) => ({ name, items })).sort((a, b) => b.items.length - a.items.length).slice(0, 5);
  }, [reportPoints]);

  const floodPoints = useMemo(() => {
    if (!flood) return [];
    return floodDry && floodAll ? floodAll : flood.wet;
  }, [flood, floodAll, floodDry]);

  const floodCounts = flood?.counts || { flood: 0, slight: 0, normal: 0, offline: 0 };
  const floodTop = useMemo(() => (flood?.wet || []).slice(0, 6), [flood]);

  // River + canal gauges for the six metro provinces, from the water summary already polled above
  const gauges = useMemo(() => {
    const out = [];
    for (const r of waterSummary?.river || []) {
      if (r.lat && r.lng) out.push({ ...r, kind: 'river' });
    }
    for (const c of waterSummary?.canals || []) {
      if (c.lat && c.lng) out.push({ ...c, kind: 'canal' });
    }
    return out;
  }, [waterSummary]);

  const gaugeCounts = useMemo(() => {
    const c = { overflow: 0, high: 0, normal: 0, low: 0 };
    for (const g of gauges) c[g.level] = (c[g.level] || 0) + 1;
    return c;
  }, [gauges]);

  const provinceCount = useMemo(() => new Set(gauges.map((g) => g.province).filter(Boolean)).size, [gauges]);

  // One marker per road sensor: a depth badge when wet, a small dot when dry or broken
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    for (const m of floodMarkersRef.current) m.remove();
    floodMarkersRef.current = [];
    if (!showFlood) return;
    for (const st of floodPoints) {
      const sty = FLOOD_STYLE[st.status] || FLOOD_STYLE.offline;
      const wet = st.status === 'flood' || st.status === 'slight';
      const el = document.createElement('button');
      el.type = 'button';
      el.title = `${st.short_name}: ${sty.label}${st.level_cm != null ? ` ${st.level_cm} ซม.` : ''}`;
      if (wet) {
        el.style.cssText = `display:flex;align-items:center;gap:3px;padding:2px 7px 2px 5px;border-radius:999px;background:${sty.color};color:#fff;font:700 11px/1 var(--font-sans);border:2px solid #fff;box-shadow:0 0 0 5px ${sty.ring},0 1px 4px rgba(15,23,42,.35);cursor:pointer`;
        el.innerHTML = `<span style="font-size:11px">💧</span><span>${Math.round(st.level_cm)} ซม.</span>`;
      } else {
        el.style.cssText = `width:12px;height:12px;border-radius:999px;background:${sty.color};border:2px solid #fff;box-shadow:0 1px 3px rgba(15,23,42,.3);cursor:pointer;padding:0;opacity:.85`;
      }
      const popup = new maplibregl.Popup({ offset: 12, closeButton: true, maxWidth: '280px' }).setHTML(
        `<div style="font-size:13px;line-height:1.45">
          <b>${esc(st.short_name)}</b>
          ${st.road ? `<br><span style="color:#64748b">${esc(st.road)}${st.district ? ` · เขต${esc(st.district)}` : ''}</span>` : ''}
          <br><span style="color:${sty.color};font-weight:700">${sty.label}</span>
          ${st.level_cm != null && st.status !== 'offline' ? ` <b>${st.level_cm} ซม.</b>` : ''}
          ${st.trend_th ? ` <span style="color:#64748b">· ${esc(st.trend_th)}</span>` : ''}
          ${st.kind === 'tunnel' ? `<br><span style="color:#64748b">อุโมงค์ทางลอด${st.side ? ` · ${esc(st.side)}` : ''}</span>` : ''}
          ${st.started ? `<br><span style="color:#64748b">เริ่มท่วม ${esc(st.started)}</span>` : ''}
          ${st.max_cm ? `<br><span style="color:#64748b">สูงสุด ${st.max_cm} ซม.</span>` : ''}
          ${st.ts_th ? `<br><span style="color:#94a3b8;font-size:11px">ข้อมูล ${esc(st.ts_th)} · สำนักการระบายน้ำ กทม.</span>` : ''}
        </div>`
      );
      floodMarkersRef.current.push(new maplibregl.Marker({ element: el }).setLngLat([st.lng, st.lat]).setPopup(popup).addTo(map));
    }
  }, [floodPoints, showFlood]);

  // One pin per citizen report: solid and ringed in the last hour, faded when older
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    for (const m of reportMarkersRef.current) m.remove();
    reportMarkersRef.current = [];
    if (!showReports) return;
    for (const r of reportPoints) {
      const fresh = Date.now() / 1000 - r.ts <= REPORT_FRESH_S;
      const el = document.createElement('button');
      el.type = 'button';
      el.title = `ประชาชนแจ้งน้ำท่วม ${agoTh(r.ts)}${r.district ? ` · เขต${r.district}` : ''}`;
      el.style.cssText = `width:24px;height:24px;border-radius:999px 999px 999px 3px;background:${REPORT_COLOR};border:2px solid #fff;box-shadow:${fresh ? `0 0 0 5px ${REPORT_COLOR}44,` : ''}0 1px 4px rgba(15,23,42,.35);color:#fff;font-size:12px;line-height:1;display:flex;align-items:center;justify-content:center;cursor:pointer;padding:0;opacity:${fresh ? 1 : 0.6}`;
      el.textContent = '📣';
      const popup = new maplibregl.Popup({ offset: 14, closeButton: true, maxWidth: '300px' }).setHTML(
        `<div style="font-size:13px;line-height:1.45">
          <b style="color:${REPORT_COLOR}">ประชาชนแจ้งน้ำท่วม</b> <span style="color:#64748b">· ${agoTh(r.ts)}</span>
          ${r.depth ? `<br>ระดับน้ำ: <b>${esc(r.depth)}</b>` : ''}
          <br><span>${esc(r.text.length > 180 ? `${r.text.slice(0, 180)}…` : r.text)}</span>
          ${r.photo ? `<br><img src="${esc(r.photo)}" alt="" loading="lazy" style="margin-top:6px;width:100%;max-height:160px;object-fit:cover;border-radius:6px">` : ''}
          <br><span style="color:#64748b">${esc(r.address)}</span>
          <br><span style="color:#64748b">สถานะ: ${esc(r.state || '-')}</span>
          · <a href="${esc(r.url)}" target="_blank" rel="noopener noreferrer" style="color:#2563eb">ดูใน Traffy Fondue</a>
        </div>`
      );
      reportMarkersRef.current.push(new maplibregl.Marker({ element: el }).setLngLat([r.lng, r.lat]).setPopup(popup).addTo(map));
    }
  }, [reportPoints, showReports]);

  // River / canal gauges: a dot whose colour is the bank level, with the % of capacity inside
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    for (const m of gaugeMarkersRef.current) m.remove();
    gaugeMarkersRef.current = [];
    if (!showGauges) return;
    for (const g of gauges) {
      const sty = GAUGE_STYLE[g.level] || GAUGE_STYLE.normal;
      const alarm = g.level === 'overflow' || g.level === 'high';
      const el = document.createElement('button');
      el.type = 'button';
      el.title = `${g.name} (${g.province}): ${sty.label}${g.storage_pct != null ? ` ${g.storage_pct}%` : ''}`;
      if (alarm) {
        el.style.cssText = `display:flex;align-items:center;justify-content:center;min-width:34px;height:20px;padding:0 5px;border-radius:6px;background:${sty.color};color:#fff;font:700 10px/1 var(--font-sans);border:2px solid #fff;box-shadow:0 1px 4px rgba(15,23,42,.35);cursor:pointer`;
        el.textContent = `${Math.round(g.storage_pct)}%`;
      } else {
        el.style.cssText = `width:10px;height:10px;border-radius:2px;background:${sty.color};border:2px solid #fff;box-shadow:0 1px 3px rgba(15,23,42,.3);cursor:pointer;padding:0;opacity:.8`;
      }
      const popup = new maplibregl.Popup({ offset: 12, closeButton: true, maxWidth: '280px' }).setHTML(
        `<div style="font-size:13px;line-height:1.45">
          <b>${esc(g.name)}</b>
          <br><span style="color:#64748b">${g.kind === 'river' ? 'สถานีแม่น้ำ' : 'สถานีคลอง'}${g.district ? ` · ${esc(g.district)}` : ''}${g.province ? ` · ${esc(g.province)}` : ''}</span>
          <br><span style="color:${sty.color};font-weight:700">${sty.label}</span>${g.storage_pct != null ? ` <b>${g.storage_pct}%</b> ของความจุตลิ่ง` : ''}
          ${g.msl != null ? `<br><span style="color:#64748b">ระดับน้ำ ${g.msl} ม.รทก.${g.bank != null ? ` · ตลิ่ง ${g.bank} ม.` : ''}</span>` : ''}
          ${g.diff_text && g.diff_bank != null ? `<br><span style="color:#64748b">${esc(g.diff_text)} ${g.diff_bank}</span>` : ''}
          ${g.ts ? `<br><span style="color:#94a3b8;font-size:11px">ข้อมูล ${new Date(g.ts * 1000).toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' })} น. · ${g.source === 'bma' ? 'สำนักการระบายน้ำ กทม.' : 'คลังข้อมูลน้ำแห่งชาติ'}</span>` : ''}
        </div>`
      );
      gaugeMarkersRef.current.push(new maplibregl.Marker({ element: el }).setLngLat([g.lng, g.lat]).setPopup(popup).addTo(map));
    }
  }, [gauges, showGauges]);

  // PM2.5 stations as DOM markers (rounded square with the µg/m³ value; the map style ships no
  // glyphs so a symbol layer cannot draw text). Colour = Thai AQI band.
  const pmMarkersRef = useRef([]);
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !air) return;
    for (const m of pmMarkersRef.current) m.remove();
    pmMarkersRef.current = [];
    if (!showPm) return;
    for (const s of air.items || []) {
      const el = document.createElement('button');
      el.type = 'button';
      el.title = `${s.name}: PM2.5 ${s.pm25} µg/m³`;
      el.style.cssText = `display:flex;align-items:center;justify-content:center;width:30px;height:22px;border-radius:7px;background:${s.color};color:#0f172a;font:700 11px/1 var(--font-sans);border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.35);cursor:pointer;padding:0`;
      el.textContent = Math.round(s.pm25);
      const t = s.ts ? new Date(s.ts * 1000).toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' }) : '';
      const popup = new maplibregl.Popup({ offset: 14, closeButton: true, maxWidth: '260px' }).setHTML(
        `<div style="font-size:13px;line-height:1.4"><b>${s.name}</b><br><span style="color:#64748b">${s.area} ${s.province}</span><br>` +
          `PM2.5 <b style="color:${s.color}">${s.pm25} µg/m³</b> · AQI ${s.aqi ?? '-'} · ${s.label}` +
          (t ? `<br><span style="color:#64748b;font-size:11px">ข้อมูล ${t} น. · ${s.source_label || 'Air4Thai (คพ.)'}</span>` : '') +
          '</div>'
      );
      pmMarkersRef.current.push(new maplibregl.Marker({ element: el }).setLngLat([s.lng, s.lat]).setPopup(popup).addTo(map));
    }
  }, [air, showPm]);

  // Sync Rain Radar tile layer to MapLibre with maxzoom: 7 (prevents Zoom Level Not Supported)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !radarTileUrl) return;

    const applyRadar = () => {
      const sourceId = 'rain-radar-source';
      const layerId = 'rain-radar-layer';

      const existingSource = map.getSource(sourceId);
      if (existingSource) {
        if (existingSource.setTiles) {
          existingSource.setTiles([radarTileUrl]);
        }
      } else {
        try {
          map.addSource(sourceId, {
            type: 'raster',
            tiles: [radarTileUrl],
            tileSize: 256,
            maxzoom: 7, // CRITICAL: RainViewer free tiles are z<=7. MapLibre scales up smoothly for z>7 without error boxes!
            attribution: '© RainViewer',
          });
        } catch (e) {
          console.warn('[map] addSource error:', e);
        }
      }

      if (!map.getLayer(layerId)) {
        const beforeLayer = map.getLayer('traffic-forward') ? 'traffic-forward' : undefined;
        try {
          map.addLayer(
            {
              id: layerId,
              type: 'raster',
              source: sourceId,
              paint: {
                'raster-opacity': radarOpacity,
                'raster-fade-duration': 300,
              },
            },
            beforeLayer
          );
        } catch (e) {
          console.warn('[map] addLayer error:', e);
        }
      }

      if (map.getLayer(layerId)) {
        map.setLayoutProperty(layerId, 'visibility', showRainRadar ? 'visible' : 'none');
        map.setPaintProperty(layerId, 'raster-opacity', radarOpacity);
      }
    };

    if (map.isStyleLoaded()) {
      applyRadar();
    } else {
      map.once('load', applyRadar);
    }
  }, [radarTileUrl, showRainRadar, radarOpacity]);

  // Sync camera markers
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    Object.values(markersRef.current).forEach((m) => m.remove());
    markersRef.current = {};

    currentCameras
      .filter((c) => c.latitude && c.longitude)
      .forEach((c) => {
        const on = active.includes(c.camid);
        const pinColor = PIN_COLOR[c.province] || PIN;
        const el = pinEl(pinColor, on, c.floodRisk);
        el.setAttribute('aria-label', c.short_title || c.title);

        const orgTag = c.organization ? `<span style="display:inline-block;padding:2px 6px;border-radius:4px;font-size:10px;font-weight:600;background:#e0f2fe;color:#0369a1;margin-bottom:6px">${esc(c.organization)}</span>` : '';

        const floodHtml = c.floodRisk
          ? `<div style="background:${c.floodRisk.isOverflow ? '#fef2f2' : '#fffbeb'};border:1px solid ${c.floodRisk.isOverflow ? '#fecaca' : '#fde68a'};border-radius:6px;padding:6px 8px;margin-bottom:8px;font-size:11px;color:${c.floodRisk.isOverflow ? '#991b1b' : '#92400e'}">
              <div style="font-weight:700;display:flex;align-items:center;gap:4px">
                <span>🌊</span> ${esc(c.floodRisk.badgeText)} (${c.floodRisk.storagePct}%)
              </div>
              <div style="font-size:10px;margin-top:2px;color:${c.floodRisk.isOverflow ? '#b91c1c' : '#b45309'}">
                ใกล้${esc(c.floodRisk.stationName)} (${c.floodRisk.distanceKm} กม.)
              </div>
            </div>`
          : '';

        const popup = new maplibregl.Popup({ offset: 14, closeButton: true, maxWidth: '300px', anchor: 'bottom' }).setHTML(
          `<div style="width:260px">
            <div style="position:relative;border-radius:8px;overflow:hidden;background:#e2e8f0;aspect-ratio:16/9;margin-bottom:8px">
              <video data-live="${c.camid}" muted autoplay playsinline style="display:none;width:100%;height:100%;object-fit:cover;background:#000"></video>
              <img data-img="${c.camid}" alt="" style="display:block;width:100%;height:100%;object-fit:cover" />
              <span data-status="${c.camid}" style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:12px;color:#475569;background:#f8fafc">กำลังเปิดภาพ...</span>
            </div>
            ${orgTag}
            ${floodHtml}
            <p style="margin:0 0 8px;font-weight:500;color:#0f172a;font-size:13px;line-height:1.35">${esc(c.short_title || c.title)}</p>
            <div style="display:flex;gap:6px;flex-wrap:wrap">
              <button data-act="toggle" data-camid="${c.camid}" style="cursor:pointer;border:0;border-radius:8px;padding:6px 12px;background:${on ? '#fee2e2' : '#2563eb'};color:${on ? '#b91c1c' : '#fff'};font-size:12px;font-family:inherit">${on ? 'ปิดกล้องนี้' : 'เปิดดูกล้องนี้'}</button>
              <button data-act="ai" data-camid="${c.camid}" style="cursor:pointer;border:0;border-radius:8px;padding:6px 12px;background:#f1f5f9;color:#0f172a;border:1px solid #cbd5e1;font-size:12px;font-family:inherit">${c.floodRisk ? 'ถาม AI เช็คน้ำท่วม' : 'ถามผู้ช่วย AI'}</button>
            </div>
          </div>`
        );

        let hls = null;
        popup.on('open', () => {
          map.easeTo({ center: [c.longitude, c.latitude], offset: [0, 130], duration: 400 });
          const root = popup.getElement();
          const video = root?.querySelector(`video[data-live="${c.camid}"]`);
          const img = root?.querySelector(`img[data-img="${c.camid}"]`);
          const status = root?.querySelector(`span[data-status="${c.camid}"]`);
          if (!img || !video) return;
          const hide = () => status && (status.style.display = 'none');
          const fail = () => status && (status.textContent = 'กล้องขอพักสักครู่');

          // Snapshot fallback: iTIC Motion entries carry placeholder X.X.X.X urls, so only real hosts count
          const still = [c.imgurl, c.vdourl].find((u) => u && !u.includes('X.X.X.X'));
          const showImage = () => {
            if (!still) return fail();
            img.onload = hide;
            img.onerror = fail;
            img.src = `${still}${still.includes('?') ? '&' : '?'}t=${Date.now()}`;
          };

          // Prefer the HLS stream (works for every Longdo camera); same setup as VideoSlot
          if (c.hls_url && Hls.isSupported()) {
            video.style.display = 'block';
            img.style.display = 'none';
            hls = new Hls({ enableWorker: true, lowLatencyMode: true, backBufferLength: 30, maxBufferLength: 10, manifestLoadingTimeOut: 8000 });
            hls.loadSource(c.hls_url);
            hls.attachMedia(video);
            hls.on(Hls.Events.MANIFEST_PARSED, () => video.play().catch(() => {}));
            video.onplaying = hide;
            hls.on(Hls.Events.ERROR, (_, data) => {
              if (!data.fatal) return;
              hls.destroy();
              hls = null;
              video.style.display = 'none';
              img.style.display = 'block';
              showImage();
            });
          } else if (c.hls_url && video.canPlayType('application/vnd.apple.mpegurl')) {
            video.style.display = 'block';
            img.style.display = 'none';
            video.src = c.hls_url;
            video.onplaying = hide;
            video.onerror = showImage;
            video.play().catch(() => {});
          } else if (still) {
            showImage();
          } else if (status) {
            status.textContent = 'กล้องนี้ไม่มีภาพสด';
          }
        });

        popup.on('close', () => {
          if (hls) {
            hls.destroy();
            hls = null;
          }
          const root = popup.getElement();
          root?.querySelectorAll('video[data-live]').forEach((v) => {
            v.pause();
            v.removeAttribute('src');
            v.load();
          });
          root?.querySelectorAll('img[data-img]').forEach((img) => (img.src = ''));
        });

        const m = new maplibregl.Marker({ element: el }).setLngLat([c.longitude, c.latitude]).setPopup(popup).addTo(map);
        markersRef.current[c.camid] = m;
      });
  }, [currentCameras, active, isActive]);

  // Sync incident markers (camera-confirmed + Longdo reports)
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    incidentMarkersRef.current.forEach((m) => m.remove());
    incidentMarkersRef.current = [];
    const all = [...(incidents?.camera || []), ...(incidents?.longdo || [])].filter((i) => i.latitude && i.longitude);
    all.forEach((i) => {
      const when = i.source === 'camera' ? agoTh(i.ts) : i.start ? `เริ่ม ${esc(i.start).slice(11, 16)}` : '';
      const html = `<div style="width:260px">
          <p style="margin:0 0 4px;font-weight:600;color:${i.kind === 'breakdown' ? '#b85f41' : '#d9534f'};font-size:13px">${KIND_TH[i.kind] || 'เหตุการณ์'} · ${i.source === 'camera' ? 'กล้อง AI ตรวจพบ' : 'รายงานจราจร'}</p>
          <p style="margin:0 0 6px;color:#0f172a;font-size:13px;line-height:1.35">${esc(i.title)}</p>
          ${i.image ? `<img src="${i.image}" alt="" style="display:block;width:100%;border-radius:8px;margin-bottom:6px" />` : ''}
          ${i.description ? `<p style="margin:0 0 6px;color:#475569;font-size:12px;line-height:1.4">${esc(i.description)}</p>` : ''}
          <p style="margin:0;color:#94a3b8;font-size:11px">${when}${i.confidence ? ` · ความมั่นใจ ${Math.round(i.confidence * 100)}%` : ''}${i.stopped_s ? ` · จอดนิ่ง ${i.stopped_s} วิ` : ''}</p>
          ${i.camid ? `<div style="margin-top:8px"><button data-act="ai" data-camid="${esc(i.camid)}" style="cursor:pointer;border:0;border-radius:8px;padding:6px 12px;background:#2563eb;color:#fff;font-size:12px;font-family:inherit">ดูภาพสดกล้องนี้</button></div>` : ''}
        </div>`;
 const popup = new maplibregl.Popup({ offset: 18, closeButton: true, maxWidth: '300px', anchor: 'bottom' }).setHTML(html);
 const m = new maplibregl.Marker({ element: incidentEl(i.kind) }).setLngLat([i.longitude, i.latitude]).setPopup(popup).addTo(map);
 incidentMarkersRef.current.push(m);
    });
  }, [incidents, isActive]);

 const flyToIncident = (i) => {
 const map = mapRef.current;
 if (!map || !i.latitude) return;
 map.flyTo({ center: [i.longitude, i.latitude], zoom: 15, duration: 800 });
 const idx = [...(incidents?.camera || []), ...(incidents?.longdo || [])].filter((x) => x.latitude && x.longitude).findIndex((x) => x.id === i.id);
 const m = incidentMarkersRef.current[idx];
 if (m) setTimeout(() => m.togglePopup(), 850);
  };

  // Popup button clicks (delegated)
 useEffect(() => {
 const el = mapEl.current;
 if (!el) return;
 const onClick = (e) => {
 const btn = e.target.closest('button[data-camid]');
 if (!btn) return;
 if (btn.dataset.act === 'ai') onOpenAI(btn.dataset.camid);
 else onToggle(btn.dataset.camid);
 markersRef.current[btn.dataset.camid]?.getPopup()?.remove();
    };
 el.addEventListener('click', onClick);
 return () => el.removeEventListener('click', onClick);
  }, [onToggle, onOpenAI]);

 const locateMe = () => {
 if (!navigator.geolocation) return onToast('เบราว์เซอร์นี้ไม่รองรับตำแหน่ง');
 navigator.geolocation.getCurrentPosition(
      (p) => {
 const map = mapRef.current;
 if (!map) return;
 const here = [p.coords.longitude, p.coords.latitude];
 map.flyTo({ center: here, zoom: 13, duration: 1000 });
 const dot = document.createElement('span');
 dot.style.cssText = 'display:block;width:18px;height:18px;border-radius:999px;background:#8a72c4;border:3px solid #fff;box-shadow:0 0 0 6px rgba(138,114,196,.25)';
 new maplibregl.Marker({ element: dot }).setLngLat(here).addTo(map);
      },
      () => onToast('ขอตำแหน่งไม่สำเร็จ'),
      { timeout: 8000 }
    );
  };

 const flyToCam = (c) => {
 const map = mapRef.current;
 const m = markersRef.current[c.camid];
 if (!map || !m) return;
 map.flyTo({ center: [c.longitude, c.latitude], zoom: 15, duration: 800 });
 setTimeout(() => m.togglePopup(), 850);
  };

  const activeCams = active.map((id) => currentCameras.find((c) => c.camid === id) || cameras.find((c) => c.camid === id)).filter(Boolean);
  const updated = summary?.updated_at ? new Date(summary.updated_at * 1000).toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' }) : null;

  return (
    <div className="flex flex-col gap-4">
    <div className="grid grid-cols-1 lg:grid-cols-[300px_1fr] gap-4 lg:h-[calc(100vh-11rem)] min-h-[520px]">
      <aside className="glass rounded-xl p-5 flex flex-col gap-4 overflow-y-auto scroll-soft">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 leading-7">แผนที่จราจร</h1>
          <p className="text-[13px] text-slate-600 mt-0.5">เส้นสีบอกการระบายรถแบบสด จิ้มหมุดเพื่อเปิดกล้อง</p>
        </div>

        {/* Traffic legend + status */}
        <div className="rounded-xl bg-white border border-cream-200 p-3">
          <div className="flex items-center justify-between mb-2">
            <label className="inline-flex items-center gap-2 text-sm text-ink-900 cursor-pointer">
              <input type="checkbox" checked={showTraffic} onChange={(e) => setShowTraffic(e.target.checked)} className="accent-lavender-600 w-4 h-4" />
              เส้นจราจร
            </label>
            {summary && (
              <span className={`inline-flex items-center gap-1 text-[11px] rounded-lg px-2 py-0.5 ${summary.online ? 'bg-sage-50 text-sage-700' : 'bg-gold-50 text-gold-700'}`}>
                {summary.online ? `สด ${updated}` : `ออฟไลน์ ${updated || ''}`}
              </span>
            )}
          </div>
          <div className="grid grid-cols-3 gap-1.5 text-[11px] text-ink-600">
            <span className="inline-flex items-center gap-1.5"><span className="w-5 h-1.5 rounded-full" style={{ background: '#54C00C' }} />โล่ง</span>
            <span className="inline-flex items-center gap-1.5"><span className="w-5 h-1.5 rounded-full" style={{ background: '#FEDE04' }} />ปานกลาง</span>
            <span className="inline-flex items-center gap-1.5"><span className="w-5 h-1.5 rounded-full" style={{ background: '#FF2020' }} />ติดขัด</span>
          </div>
          {summary?.ready && (
            <p className="mt-2 text-xs text-ink-600">
              ทั้งเมืองระบายได้ <span className="text-base text-ink-900">{summary.flow_index}</span>/100 · แดง {summary.red_pct}%
            </p>
          )}

          {/* BTS / MRT overlay toggle */}
          <div className="mt-2.5 pt-2.5 border-t border-slate-100">
            <label className="inline-flex items-center gap-2 text-sm text-ink-900 cursor-pointer font-medium">
              <input type="checkbox" checked={showRail} onChange={(e) => setShowRail(e.target.checked)} className="accent-blue-600 w-4 h-4" />
              🚇 รถไฟฟ้า BTS / MRT
            </label>
            <p className="text-[11px] text-slate-500 mt-1">BTS, MRT, Airport Rail Link และสายสีแดง จาก OpenStreetMap · คลิกสถานีเพื่อดูชื่อ</p>
          </div>

          {/* BMA risk-map traffic layers */}
          <div className="mt-2.5 pt-2.5 border-t border-slate-100">
            <p className="text-sm text-ink-900 font-medium">⚠️ จุดเสี่ยงจราจร กทม.</p>
            <p className="text-[11px] text-slate-500 mt-0.5 mb-1.5">จากแผนที่จุดเสี่ยงกรุงเทพมหานคร (riskbkk) · คลิกจุดเพื่อดูรายละเอียด</p>
            <div className="flex flex-col gap-1">
              {RISK_LAYERS.map((l) => (
                <label key={l.id} className="inline-flex items-center gap-2 text-[13px] text-ink-900 cursor-pointer">
                  <input type="checkbox" checked={!!riskOn[l.id]} onChange={(e) => setRiskOn((s) => ({ ...s, [l.id]: e.target.checked }))} className="accent-blue-600 w-4 h-4" />
                  <span className="w-2.5 h-2.5 rounded-full shrink-0 border border-slate-400" style={{ background: l.legend || l.color }} />
                  {l.label}
                </label>
              ))}
            </div>
            <p className="text-[11px] text-slate-500 mt-1">ทางม้าลาย ป้ายรถเมล์ และวินมอเตอร์ไซค์ แสดงเมื่อซูม ≥ 13</p>
          </div>

          {/* Rain radar overlay toggle */}
          <div className="mt-2.5 pt-2.5 border-t border-slate-100">
            <div className="flex items-center justify-between mb-1">
              <label className="inline-flex items-center gap-2 text-sm text-ink-900 cursor-pointer font-medium">
                <input
                  type="checkbox"
                  checked={showRainRadar}
                  onChange={(e) => setShowRainRadar(e.target.checked)}
                  className="accent-blue-600 w-4 h-4"
                />
                <Icon name="rain" /> ซ้อนเรดาร์ฝน (สด)
              </label>
              {radarTime && (
                <span className="text-[11px] text-blue-600 font-semibold bg-blue-50 px-2 py-0.5 rounded-full">
                  สด {radarTime}
                </span>
              )}
            </div>
            <p className="text-[11px] text-slate-500 mb-1.5">กลุ่มเมฆฝนซ้อนใต้เส้นรถติดและกล้อง CCTV</p>
            {showRainRadar && (
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-slate-400 shrink-0">ความเข้ม</span>
                <input
                  type="range"
                  min="0.2"
                  max="1.0"
                  step="0.05"
                  value={radarOpacity}
                  onChange={(e) => setRadarOpacity(parseFloat(e.target.value))}
                  className="w-full accent-blue-600 h-1 bg-slate-200 rounded-lg cursor-pointer"
                />
                <span className="text-[10px] text-slate-600 font-mono shrink-0">{Math.round(radarOpacity * 100)}%</span>
              </div>
            )}
          </div>
        </div>

        {/* น้ำท่วมขังถนน (เซ็นเซอร์ กทม.) + ระดับน้ำแม่น้ำ/คลอง (ปริมณฑล) */}
        <div className="pt-2.5 border-t border-slate-100">
          <div className="flex items-center justify-between mb-1">
            <label className="inline-flex items-center gap-2 text-sm text-ink-900 cursor-pointer font-medium">
              <input type="checkbox" checked={showFlood} onChange={(e) => setShowFlood(e.target.checked)} className="accent-blue-600 w-4 h-4" />
              <Icon name="water" /> น้ำท่วมขังถนน กทม. (สด)
            </label>
            {flood?.feed_time && <span className="text-[11px] text-slate-500">{fmtTime(flood.feed_time)} น.</span>}
          </div>
          {flood ? (
            <>
              <p className="text-[11px] text-slate-500 mb-1.5">
                {floodCounts.flood + floodCounts.slight > 0
                  ? `ท่วม ${floodCounts.flood} จุด · เล็กน้อย ${floodCounts.slight} จุด จาก ${flood.total} จุดวัด`
                  : `ไม่มีจุดน้ำท่วมขังขณะนี้ (ตรวจ ${flood.total} จุด)`}
                {floodCounts.offline > 0 ? ` · ขัดข้อง ${floodCounts.offline}` : ''}
              </p>
              <div className="flex flex-wrap gap-x-2 gap-y-1 text-[11px] text-slate-600 mb-1.5">
                <span className="inline-flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full" style={{ background: FLOOD_STYLE.flood.color }} />ท่วม &gt;10 ซม.</span>
                <span className="inline-flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full" style={{ background: FLOOD_STYLE.slight.color }} />เล็กน้อย 5-10</span>
                <span className="inline-flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full" style={{ background: FLOOD_STYLE.normal.color }} />ปกติ &le;5</span>
              </div>
              <label className="inline-flex items-center gap-2 text-[11px] text-slate-600 cursor-pointer">
                <input type="checkbox" checked={floodDry} onChange={(e) => setFloodDry(e.target.checked)} className="accent-blue-600" disabled={!showFlood} />
                แสดงจุดวัดที่ยังไม่ท่วมด้วย
              </label>
              {floodTop.length > 0 && (
                <ul className="mt-2 flex flex-col gap-1">
                  {floodTop.map((r) => (
                    <li key={r.code}>
                      <button
                        type="button"
                        onClick={() => mapRef.current?.easeTo({ center: [r.lng, r.lat], zoom: 15.5, duration: 800 })}
                        className="cursor-pointer w-full flex items-center justify-between gap-2 rounded-lg border border-slate-200 px-2 py-1 text-left hover:border-slate-400 transition-colors"
                      >
                        <span className="min-w-0 truncate text-[12px] text-ink-900">{r.short_name}</span>
                        <span className="shrink-0 text-[11px] font-semibold tabular-nums" style={{ color: FLOOD_STYLE[r.status].color }}>{r.level_cm} ซม.</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </>
          ) : (
            <p className="text-[11px] text-slate-500">กำลังโหลดจุดวัดน้ำท่วม ...</p>
          )}
          <p className="text-[11px] text-slate-400 mt-1">เซ็นเซอร์วัดน้ำบนผิวถนนมีเฉพาะ กทม. 50 เขต</p>
        </div>

        {/* ประชาชนแจ้งน้ำท่วม (Traffy Fondue) */}
        <div className="pt-2.5 border-t border-slate-100">
          <div className="flex items-center justify-between mb-1">
            <label className="inline-flex items-center gap-2 text-sm text-ink-900 cursor-pointer font-medium">
              <input type="checkbox" checked={showReports} onChange={(e) => setShowReports(e.target.checked)} className="accent-blue-600 w-4 h-4" />
              <span aria-hidden="true">📣</span> ประชาชนแจ้งน้ำท่วม
            </label>
            {reports?.updated_at && <span className="text-[11px] text-slate-500">{fmtTime(reports.updated_at)} น.</span>}
          </div>
          {reports ? (
            <>
              <p className="text-[11px] text-slate-500 mb-1.5">
                {reportPoints.length > 0
                  ? `${reportPoints.length} เรื่องใน 6 ชม. · ชั่วโมงล่าสุด ${reportFresh} เรื่อง`
                  : 'ไม่มีเรื่องแจ้งน้ำท่วมใน 6 ชม.'}
                {reports.error ? ' · ดึงข้อมูลล่าสุดไม่สำเร็จ' : ''}
              </p>
              {reportDistricts.length > 0 && (
                <ul className="flex flex-col gap-1">
                  {reportDistricts.map((d) => (
                    <li key={d.name}>
                      <button
                        type="button"
                        onClick={() => mapRef.current?.easeTo({ center: [d.items[0].lng, d.items[0].lat], zoom: 14.5, duration: 800 })}
                        className="cursor-pointer w-full flex items-center justify-between gap-2 rounded-lg border border-slate-200 px-2 py-1 text-left hover:border-slate-400 transition-colors"
                      >
                        <span className="min-w-0 truncate text-[12px] text-ink-900">เขต{d.name}</span>
                        <span className="shrink-0 text-[11px] font-semibold tabular-nums" style={{ color: REPORT_COLOR }}>{d.items.length} เรื่อง</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </>
          ) : (
            <p className="text-[11px] text-slate-500">กำลังโหลดเรื่องแจ้งจาก Traffy Fondue ...</p>
          )}
          <p className="text-[11px] text-slate-400 mt-1">จาก Traffy Fondue คัดด้วยคำว่า น้ำท่วม/น้ำขัง ยังไม่ผ่านการตรวจสอบจากเขต</p>
        </div>

        {/* ระดับน้ำแม่น้ำ / คลอง ทั่วเขตปริมณฑล (คลังข้อมูลน้ำแห่งชาติ) */}
        <div className="pt-2.5 border-t border-slate-100">
          <label className="inline-flex items-center gap-2 text-sm text-ink-900 cursor-pointer font-medium">
            <input type="checkbox" checked={showGauges} onChange={(e) => setShowGauges(e.target.checked)} className="accent-blue-600 w-4 h-4" />
            <Icon name="water" /> ระดับน้ำแม่น้ำ/คลอง (ปริมณฑล)
          </label>
          {gauges.length > 0 ? (
            <>
              <p className="text-[11px] text-slate-500 mt-1 mb-1.5">
                {gauges.length} สถานีใน {provinceCount} จังหวัด (กทม. นนทบุรี ปทุมธานี สมุทรปราการ นครปฐม สมุทรสาคร) ·
                {gaugeCounts.overflow > 0 ? ` ล้นตลิ่ง ${gaugeCounts.overflow} สถานี` : ' ไม่มีสถานีล้นตลิ่ง'}
                {gaugeCounts.high > 0 ? ` · น้ำมาก ${gaugeCounts.high}` : ''}
              </p>
              <div className="flex flex-wrap gap-x-2 gap-y-1 text-[11px] text-slate-600">
                <span className="inline-flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm" style={{ background: GAUGE_STYLE.overflow.color }} />ล้นตลิ่ง</span>
                <span className="inline-flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm" style={{ background: GAUGE_STYLE.high.color }} />น้ำมาก</span>
                <span className="inline-flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm" style={{ background: GAUGE_STYLE.normal.color }} />ปกติ</span>
              </div>
              <p className="text-[11px] text-slate-400 mt-1">เป็นระดับน้ำในแม่น้ำ/คลอง เทียบ % ความจุตลิ่ง ไม่ใช่ความลึกของน้ำบนถนน</p>
            </>
          ) : (
            <p className="text-[11px] text-slate-500 mt-1">กำลังโหลดสถานีวัดระดับน้ำ ...</p>
          )}
        </div>

        {/* PM2.5 station toggle */}
        <div className="pt-2.5 border-t border-slate-100">
          <div className="flex items-center justify-between mb-1">
            <label className="inline-flex items-center gap-2 text-sm text-ink-900 cursor-pointer font-medium">
              <input type="checkbox" checked={showPm} onChange={(e) => setShowPm(e.target.checked)} className="accent-blue-600 w-4 h-4" />
              <Icon name="mask" /> ฝุ่น PM2.5 รายสถานี
            </label>
            {air?.avg_pm25 != null && (
              <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-700">เฉลี่ย {air.avg_pm25}</span>
            )}
          </div>
          <p className="text-[11px] text-slate-500 mb-1.5">
            {air ? `${air.total} สถานี (คพ. + กทม.) หน่วย µg/m³ แตะจุดเพื่อดูรายละเอียด` : 'กำลังโหลด AirBKK + Air4Thai'}
          </p>
          <div className="flex flex-wrap gap-x-2 gap-y-1 text-[11px] text-slate-600">
            {[['#3BA0FF', 'ดีมาก ≤15'], ['#4CC74A', 'ดี ≤25'], ['#FFD400', 'ปานกลาง ≤37.5'], ['#FF8C00', 'เริ่มมีผล ≤75'], ['#E3272C', 'มีผล >75']].map(([c, l]) => (
              <span key={l} className="inline-flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full" style={{ background: c }} />{l}</span>
            ))}
          </div>
        </div>

        {/* Buildings: 3D is automatic from zoom 15; this only adds footprints and names */}
        <div className="pt-2.5 border-t border-slate-100">
          <p className="text-sm text-ink-900 font-medium inline-flex items-center gap-2"><Icon name="building" /> อาคาร 3 มิติ</p>
          <p className="text-[11px] text-slate-500 mt-1">ซูม ≥ 15 อาคารขึ้นเป็น 3 มิติตามความสูงจริง (OpenFreeMap) และแผนที่เอียง 45° อัตโนมัติ · คลิกขวา / Ctrl+ลาก เพื่อหมุนหรือเอียงเอง</p>
          <label className="mt-2 inline-flex items-center gap-2 text-sm text-ink-900 cursor-pointer font-medium">
            <input type="checkbox" checked={showPlaces} onChange={(e) => setShowPlaces(e.target.checked)} className="accent-blue-600 w-4 h-4" />
            <Icon name="pin" /> รายละเอียดสิ่งปลูกสร้าง
          </label>
          <p className="text-[11px] text-slate-500 mt-1">ซูม ≥ 15: ชื่อโรงพยาบาล โรงเรียน ห้าง วัด สถานี ฯลฯ บนแผนที่ + ผังอาคาร (2D) · คลิกอาคารดูชื่อ/ความสูง/จำนวนชั้น</p>
        </div>

        {/* Wind overlay toggle (own layer, Open-Meteo) */}
        <div className="pt-2.5 border-t border-slate-100">
          <div className="flex items-center justify-between mb-1">
            <label className="inline-flex items-center gap-2 text-sm text-ink-900 cursor-pointer font-medium">
              <input type="checkbox" checked={showWind} onChange={(e) => setShowWind(e.target.checked)} className="accent-blue-600 w-4 h-4" />
              <Icon name="wind" /> ลูกศรลม (สด)
            </label>
            {wind?.points?.[24]?.time && <span className="text-[11px] text-slate-500">{wind.points[24].time.slice(11, 16)} น.</span>}
          </div>
          <p className="text-[11px] text-slate-500 mb-1.5">ทิศทางและความเร็วลม กม./ชม. ทุก 10 กม. จาก Open-Meteo อัปเดตทุก 15 นาที · ไม่บังแผนที่</p>
          <div className="flex flex-wrap gap-x-2 gap-y-1 text-[11px] text-slate-600">
            {[['#60a5fa', '<10 เบา'], ['#22c55e', '10-20'], ['#f59e0b', '20-35 แรง'], ['#ef4444', '>35 พายุ']].map(([c, l]) => (
              <span key={l} className="inline-flex items-center gap-1"><span className="w-3 h-1 rounded-full" style={{ background: c }} />{l}</span>
            ))}
          </div>
        </div>

        <motion.button
          type="button"
          whileTap={{ scale: 0.96 }}
          onClick={locateMe}
          className="cursor-pointer inline-flex items-center justify-center gap-2 rounded-xl bg-white text-ink-900 border border-cream-200 px-4 py-2.5 text-sm font-medium hover:bg-cream-100 transition-colors duration-200"
        >
          <Icon name="pin" /> ไปที่ตำแหน่งของฉัน
        </motion.button>

        {/* คำอธิบายสัญลักษณ์และไอคอนบนแผนที่ (Map Legend) */}
        <div className="rounded-xl bg-white border border-cream-200 p-3 flex flex-col gap-2.5">
          <div className="flex items-center justify-between pb-2 border-b border-cream-200">
            <p className="text-xs font-semibold text-ink-900 flex items-center gap-1.5">
              <Icon name="legend" /> สัญลักษณ์บนแผนที่
            </p>
            <span className="text-[11px] text-ink-600 font-medium">คำอธิบายหมุด</span>
          </div>

          <div className="flex flex-col gap-2.5 text-xs">
            {/* กล้อง CCTV ปกติ */}
            <div className="flex items-center gap-2.5">
              <span className="w-5 h-5 rounded-full bg-blue-600 border-2 border-white/90 shadow-xs shrink-0 flex items-center justify-center" />
              <div className="flex flex-col min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="font-medium text-ink-900">กล้อง CCTV จราจร</span>
                  <span className="text-[10px] bg-blue-50 text-blue-700 px-1.5 py-0.5 rounded font-medium">{currentCameras.length} ตัว</span>
                </div>
                <span className="text-[11px] text-ink-600 leading-tight">คลิกที่หมุดเพื่อเปิดดูภาพสดและ AI ตรวจนับรถ</span>
              </div>
            </div>

            {/* กล้องจุดเสี่ยงน้ำท่วม */}
            <div className="flex items-center gap-2.5">
              <span className="relative w-5 h-5 rounded-full bg-blue-600 border-2 border-amber-400 shadow-xs shrink-0 flex items-center justify-center">
                <span className="absolute -top-1.5 -right-1.5 text-[9px] leading-none pointer-events-none">🌊</span>
              </span>
              <div className="flex flex-col min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="font-medium text-ink-900">กล้องจุดเฝ้าระวังน้ำท่วม</span>
                  {floodRiskCount > 0 && (
                    <span className="text-[10px] bg-amber-50 text-amber-700 px-1.5 py-0.5 rounded font-medium">{floodRiskCount} จุด</span>
                  )}
                </div>
                <span className="text-[11px] text-ink-600 leading-tight">อยู่ใกล้สถานีวัดน้ำแม่น้ำ/คลองที่น้ำสูงหรือเสี่ยงล้นตลิ่ง</span>
              </div>
            </div>

            {/* อุบัติเหตุ */}
            <div className="flex items-center gap-2.5">
              <span className="w-5 h-5 rounded-full bg-red-600 border-2 border-white/90 shadow-xs text-white font-bold text-[11px] flex items-center justify-center shrink-0 leading-none">
                !
              </span>
              <div className="flex flex-col min-w-0">
                <span className="font-medium text-ink-900">อุบัติเหตุ / กีดขวางทาง</span>
                <span className="text-[11px] text-ink-600 leading-tight">จุดเกิดอุบัติเหตุหรือชนกีดขวาง (ตรวจพบโดย AI / รายงานสด)</span>
              </div>
            </div>

            {/* รถจอดเสีย */}
            <div className="flex items-center gap-2.5">
              <span className="w-5 h-5 rounded-full bg-amber-500 border-2 border-white/90 shadow-xs text-white font-bold text-[11px] flex items-center justify-center shrink-0 leading-none">
                !
              </span>
              <div className="flex flex-col min-w-0">
                <span className="font-medium text-ink-900">รถจอดเสีย / สิ่งกีดขวาง</span>
                <span className="text-[11px] text-ink-600 leading-tight">รถจอดเสียในช่องทางจราจร</span>
              </div>
            </div>

            {/* เรดาร์ฝน */}
            <div className="pt-2 border-t border-cream-200 flex items-center gap-2.5 text-[11px]">
              <span className="shrink-0 w-5 text-center text-blue-500"><Icon name="rain" /></span>
              <div className="flex flex-col min-w-0">
                <span className="font-medium text-ink-900">เรดาร์กลุ่มฝน (สด)</span>
                <span className="text-[10px] text-ink-600 leading-tight">แถบสีฟ้า-เขียว-ส้ม แสดงความหนาแน่นของเมฆฝน</span>
              </div>
            </div>
          </div>
        </div>

        {(() => {
 const list = [...(incidents?.camera || []), ...(incidents?.longdo || [])];
 if (!list.length) return null;
 return (
            <div className="rounded-lg bg-red-50 border border-red-200 p-3">
              <p className="text-xs font-semibold text-red-700 mb-1.5">อุบัติเหตุ / เหตุการณ์ตอนนี้ ({list.length})</p>
              <div className="max-h-36 overflow-y-auto scroll-soft flex flex-col gap-1">
                {list.map((i) => (
                  <button key={i.id} type="button" onClick={() => flyToIncident(i)} className="cursor-pointer text-left rounded-lg px-2.5 py-1.5 text-sm text-ink-900 hover:bg-white transition-colors duration-200">
                    <span className="line-clamp-1">{i.title}</span>
                    <span className="block text-[11px] text-ink-600">{KIND_TH[i.kind] || 'เหตุการณ์'} · {i.source === 'camera' ? 'กล้อง AI' : 'รายงานจราจร'}</span>
                  </button>
                ))}
              </div>
            </div>
          );
        })()}

        <div className="flex-1 min-h-40 flex flex-col">
          <p className="text-xs text-ink-600 mb-2">กล้องที่เปิดอยู่ ({activeCams.length})</p>
          {activeCams.length === 0 ? (
            <p className="text-sm text-ink-400">ยังไม่มีกล้องที่เปิด จิ้มหมุดบนแผนที่ได้เลย</p>
          ) : (
            <div className="flex-1 overflow-y-auto scroll-soft flex flex-col gap-1.5">
              {activeCams.map((c) => (
                <button key={c.camid} type="button" onClick={() => flyToCam(c)} className="cursor-pointer text-left rounded-lg px-3 py-2 text-sm text-ink-900 hover:bg-slate-50 transition-colors duration-200 flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: PIN_COLOR[c.province] || PIN }} />
                  <span className="line-clamp-1">{c.short_title}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </aside>

      <section aria-label="แผนที่จราจร" className="glass rounded-xl overflow-hidden min-h-[560px] relative">
        <div ref={mapEl} className="w-full h-full min-h-[540px]" />
      </section>
    </div>
    </div>
  );
}
