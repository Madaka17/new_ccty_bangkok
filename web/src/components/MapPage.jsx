import { useEffect, useMemo, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import Hls from 'hls.js';
import { fetchTrafficSummary, fetchLongdoCameras, fetchWaterSummary, fetchAirStations, fetchWindGrid, fetchFloodStatus, fetchFloodStations, fetchFloodReports, fetchHdmsFloods, fetchFloodCameras, fetchUserReports, fetchRoadEvents, fetchNationalFloods, fetchNasaFires, fetchNasaEvents } from '../lib/api.js';
import { enrichCamerasWithFloodRisk } from '../lib/floodRisk.js';
import { fmtTime } from './dashboard/format.js';
import { accuracyText, roughWarning, showAccuracy, frameFix } from '../lib/geo.js';
import { Icon } from './dashboard/icons.jsx';
import { Button } from './dashboard/ui.jsx';
import { PageHeader } from './dashboard/primitives.jsx';
import { PAGE_TITLES } from './Sidebar.jsx';


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

// AI flood watch on the BMA cameras (flood_cam_service.py): a camera pill, the colour is what the AI saw
const CAM_FLOOD_STYLE = {
  severe: { color: '#7f1d1d', label: 'น้ำท่วมหนัก' },
  flooded: { color: '#dc2626', label: 'น้ำท่วมถนน' },
  puddle: { color: '#f59e0b', label: 'น้ำขังเล็กน้อย' },
  none: { color: '#16a34a', label: 'ไม่มีน้ำท่วม' },
  unclear: { color: '#94a3b8', label: 'มองไม่ชัด' },
};
const CAM_WET = ['severe', 'flooded', 'puddle'];
// Flood reports sent by the public from the Water Forecast map (user_reports.py)
const USER_REPORT_COLOR = '#0891b2';

// Citizen flood reports (Traffy Fondue): a speech-bubble pin, hotter the fresher the report
const REPORT_COLOR = '#7c3aed';
const REPORT_FRESH_S = 3600;
// Flooded highways from the Department of Highways (HDMS): a road-sign pin, faded once the ticket is closed
const HDMS_COLOR = '#be185d';

const POI_MAX = 70;
const POI_MIN_ZOOM = 15;
// Label priority: public buildings first, then services, shops last (and capped) so a mall's
// tenants do not crowd out the hospital next door
const POI_TIER = (cls) => (['shop', 'grocery', 'clothing_store', 'department_store', 'lodging', 'hotel', 'parking', 'fuel', 'charging_station', 'bank', 'pharmacy', 'clinic', 'doctors'].includes(cls) ? 2
  : ['mall', 'market', 'park', 'museum', 'attraction', 'monument', 'theatre', 'cinema', 'stadium', 'sports_centre', 'golf', 'post', 'embassy'].includes(cls) ? 1 : 0);
const POI_TIER_MAX = [POI_MAX, 30, 15];
const poiKindOf = (p) => POI_KIND[p.class] || POI_KIND[p.subclass];
const poiTierOf = (p) => POI_TIER(POI_KIND[p.class] ? p.class : p.subclass);

const KIND_TH = { accident: 'อุบัติเหตุ', breakdown: 'รถเสีย' };
const CLOSURE_COLOR = { closed: '#b91c1c', diversion: '#ea580c' };
const closureTh = (c) => (c.kind === 'diversion' ? 'ปิดบางช่วง / เบี่ยงจราจร' : c.reason === 'flood' ? 'ถนนปิด (น้ำท่วม ผ่านไม่ได้)' : 'ถนนปิด');
const sourceTh = (i) => (i.source === 'camera' ? 'กล้อง AI เห็น' : i.source === 'bma' ? 'ศูนย์จราจร กทม.' : 'ข่าวจราจร');
// "เขตวัฒนา กรุงเทพฯ" / "อ.เสนา จ.พระนครศรีอยุธยา", from the province and district the server found
const placeTh = (i) => {
  if (!i.province) return '';
  const bkk = i.province === 'กรุงเทพมหานคร';
  return `${i.amphoe ? `${bkk ? 'เขต' : 'อ.'}${i.amphoe} ` : ''}${bkk ? 'กรุงเทพฯ' : `จ.${i.province}`}`;
};
const TH_MON = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.'];
// Longdo 'YYYY-MM-DD HH:MM:SS' -> "4 ต.ค. 09:30 น."
const feedTimeTh = (t) => {
  const d = t ? new Date(t.replace(' ', 'T')) : null;
  if (!d || Number.isNaN(d.getTime())) return '';
  return `${d.getDate()} ${TH_MON[d.getMonth()]} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')} น.`;
};
const THAILAND = [[97.3, 5.6], [105.7, 20.5]];
const NATION_FLOOD_COLOR = { road: '#0284c7', river: '#1e3a8a' };

// Flooded road: a sky-blue drop-shaped pin with waves; river over the bank: a navy square
function nationFloodEl(f) {
  const el = document.createElement('button');
  el.type = 'button';
  el.className = 'cursor-pointer';
  el.setAttribute('aria-label', f.kind === 'river' ? 'แม่น้ำล้นตลิ่ง' : 'ถนนน้ำท่วม');
  const color = NATION_FLOOD_COLOR[f.kind];
  const shape = f.kind === 'river' ? 'border-radius:5px' : 'border-radius:999px 999px 999px 3px';
  el.style.cssText = `width:22px;height:22px;${shape};background:${color};border:2px solid #fff;box-shadow:0 1px 4px rgba(15,23,42,.35);color:#fff;font:700 13px/1 var(--font-sans);display:flex;align-items:center;justify-content:center;padding:0`;
  el.textContent = '≈';
  return el;
}
const METRO_PROVINCES = ['กรุงเทพมหานคร', 'นนทบุรี', 'ปทุมธานี', 'สมุทรปราการ', 'นครปฐม', 'สมุทรสาคร'];
const agoTh = (ts) => {
  const m = Math.round((Date.now() / 1000 - ts) / 60);
  return m < 1 ? 'เมื่อสักครู่' : m < 60 ? `${m} นาทีก่อน` : `${Math.round(m / 60)} ชม.ก่อน`;
};
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// Closed road: a no-entry sign; diversion: an orange square with an arrow
function closureEl(c) {
  const el = document.createElement('button');
  el.type = 'button';
  el.className = 'cursor-pointer';
  el.setAttribute('aria-label', closureTh(c));
  const color = CLOSURE_COLOR[c.kind];
  if (c.kind === 'diversion') {
    el.style.cssText = `width:24px;height:24px;border-radius:6px;background:${color};border:2px solid #fff;box-shadow:0 1px 4px rgba(15,23,42,.35);color:#fff;font:700 14px/1 var(--font-sans);display:flex;align-items:center;justify-content:center;padding:0`;
    el.textContent = '↪';
  } else {
    el.style.cssText = `width:26px;height:26px;border-radius:999px;background:${color};border:2px solid #fff;box-shadow:0 0 0 4px ${color}33,0 1px 4px rgba(15,23,42,.35);display:flex;align-items:center;justify-content:center;padding:0`;
    const bar = document.createElement('span');
    bar.style.cssText = 'display:block;width:13px;height:4px;border-radius:2px;background:#fff';
    el.appendChild(bar);
  }
  return el;
}

// Pulsing warning marker for an incident
function incidentEl(kind) {
  const el = document.createElement('button');
  el.type = 'button';
  el.className = 'cursor-pointer incident-pin';
  el.setAttribute('aria-label', KIND_TH[kind] || 'เหตุบนถนน');
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

// Collapsible block of layers in the map side panel; the header says how many of its layers are on,
// so a closed group still shows what is drawn on the map.
// One line about a NASA EONET event: wind (storms report knots), distance to Thailand and which way it moves
const TREND_TH = { closer: 'กำลังเข้าใกล้ไทย', away: 'กำลังออกห่างจากไทย', steady: 'ระยะห่างจากไทยพอ ๆ เดิม' };
function nasaEventLine(e) {
  const wind = e.unit === 'kts' && e.magnitude ? `ลม ${Math.round(e.magnitude * 1.852)} กม./ชม. · ` : '';
  const where = e.km_to_thailand ? `ห่างไทย ${e.km_to_thailand.toLocaleString()} กม.` : 'อยู่ในประเทศไทย';
  return `${wind}${where}${TREND_TH[e.trend] ? ` · ${TREND_TH[e.trend]}` : ''}`;
}

function LayerGroup({ title, hint, on = 0, defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-lg border border-cream-200 bg-white shrink-0">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="cursor-pointer w-full flex items-center gap-2 px-3 py-2.5 text-left rounded-lg hover:bg-slate-50 transition-colors duration-150"
      >
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-semibold text-ink-900">{title}</span>
          {hint && <span className="block text-[11px] text-slate-500 truncate" title={hint}>{hint}</span>}
        </span>
        {on > 0 && <span className="shrink-0 rounded-md bg-blue-50 text-blue-700 px-1.5 text-[11px] font-medium tabular-nums">เปิด {on}</span>}
        <svg viewBox="0 0 20 20" fill="currentColor" className={`w-4 h-4 shrink-0 text-slate-500 transition-transform duration-150 ${open ? 'rotate-180' : ''}`} aria-hidden="true">
          <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.06l3.71-3.83a.75.75 0 111.08 1.04l-4.25 4.39a.75.75 0 01-1.08 0L5.21 8.27a.75.75 0 01.02-1.06z" clipRule="evenodd" />
        </svg>
      </button>
      {open && (
        <div className="px-3 pb-3 pt-3 border-t border-cream-200 flex flex-col divide-y divide-slate-100 [&>*]:py-3 [&>*:first-child]:pt-0 [&>*:last-child]:pb-0">
          {children}
        </div>
      )}
    </div>
  );
}

export default function MapPage({ isActive, cameras, active, incidents, onToggle, onOpenAI, onToast }) {
  const mapEl = useRef(null);
  const mapRef = useRef(null);
  const markersRef = useRef({});
  const incidentMarkersRef = useRef([]);
  const incidentByIdRef = useRef({});
  const closureMarkersRef = useRef([]);
  const nationFloodMarkersRef = useRef([]);
  const [nationFloods, setNationFloods] = useState(null);
  const closureByIdRef = useRef({});
  // Accidents and closed roads in every province (/api/road/events); null until loaded
  const [roadEvents, setRoadEvents] = useState(null);
  const [longdoCameras, setLongdoCameras] = useState([]);
  const [showTraffic, setShowTraffic] = useState(true);
  const [showRail, setShowRail] = useState(false);
  const [summary, setSummary] = useState(null);
  const [waterSummary, setWaterSummary] = useState(null);
  const [showRainRadar, setShowRainRadar] = useState(false);
  // Map legend check boxes: which pin kinds are drawn (the rain radar box is showRainRadar)
  // cctv draws every camera; floodcam marks the flood-watch ones (and draws just those when cctv is off)
  const [pinsOn, setPinsOn] = useState({ cctv: true, floodcam: false, accident: true, breakdown: false, closure: true, flood: true });
  const togglePins = (k) => setPinsOn((p) => ({ ...p, [k]: !p[k] }));
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
  const [reportsFailed, setReportsFailed] = useState(false);   // this page's last request for the reports failed
  const reportMarkersRef = useRef([]);
  // AI flood watch on every BMA camera: on by default, the map shows only the cameras with water
  const [showCamFlood, setShowCamFlood] = useState(true);
  const [camFloodDry, setCamFloodDry] = useState(false);
  const [camFlood, setCamFlood] = useState(null);
  const camFloodMarkersRef = useRef([]);
  const [showUserReports, setShowUserReports] = useState(true);
  const [userReports, setUserReports] = useState(null);
  const userReportMarkersRef = useRef([]);
  const meMarkerRef = useRef(null);   // "ไปที่ตำแหน่งของฉัน": one dot, moved on every click
  const [showHdms, setShowHdms] = useState(false);
  const [hdms, setHdms] = useState(null);
  const hdmsMarkersRef = useRef([]);
  const gaugeMarkersRef = useRef([]);
  // Building details: flat footprints in 2D, POI name labels (DOM markers) and click-for-info on any building
  const [showPlaces, setShowPlaces] = useState(false);
  // Phones: the options panel is a sheet over the map, opened from a button on it (desktop keeps it at the side)
  const [panelOpen, setPanelOpen] = useState(false);
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
  // The Longdo list covers the whole country; say how many of its cameras are in Bangkok and around it
  const metroCameraCount = useMemo(() => currentCameras.filter((c) => METRO_PROVINCES.includes(c.province)).length, [currentCameras]);

  // Create map once
  useEffect(() => {
    if (!isActive || !mapEl.current || mapRef.current) return;
    const map = new maplibregl.Map({ container: mapEl.current, style: mapStyle(), center: [100.55, 13.78], zoom: 11, attributionControl: { compact: true } });
    map.addControl(new maplibregl.NavigationControl({ showCompass: true, visualizePitch: true }), 'top-right');
    mapRef.current = map;
    window.__bkkMap = map; // devtools access
    map.on('error', (e) => console.warn('[map]', e?.error?.message || e));
    // A place picked in the options sheet moves the map: close the sheet so the phone shows where it went
    map.on('movestart', (e) => {
      if (!e.originalEvent) setPanelOpen(false);
    });
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
            '<br><span style="color:#94a3b8;font-size:11px">ข้อมูล OpenStreetMap</span></div>'
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

  // AI flood watch on the BMA cameras; a camera is re-checked every ~10 min (5 while it has water)
  useEffect(() => {
    if (!isActive || !showCamFlood) return;
    let alive = true;
    const tick = () => fetchFloodCameras({ all: camFloodDry }).then((d) => alive && setCamFlood(d)).catch(() => {});
    tick();
    const id = setInterval(tick, 60000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [isActive, showCamFlood, camFloodDry]);

  // Flood reports from the public (published after the AI check), shown for 6 h
  useEffect(() => {
    if (!isActive || !showUserReports) return;
    let alive = true;
    const tick = () => fetchUserReports().then((d) => alive && setUserReports(d)).catch(() => {});
    tick();
    const id = setInterval(tick, 60000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [isActive, showUserReports]);

  // Traffy Fondue flood complaints; the server refreshes them every 5 min
  useEffect(() => {
    if (!isActive) return;
    let alive = true;
    const tick = () =>
      fetchFloodReports()
        .then((d) => {
          if (!alive) return;
          setReports(d);
          setReportsFailed(false);
        })
        .catch(() => alive && setReportsFailed(true));
    tick();
    const id = setInterval(tick, 300000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [isActive]);

  // Department of Highways flood tickets; the server refreshes them every 10 min
  useEffect(() => {
    if (!isActive) return;
    let alive = true;
    const tick = () => fetchHdmsFloods().then((d) => alive && setHdms(d)).catch(() => {});
    tick();
    const id = setInterval(tick, 600000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [isActive]);

  const hdmsPoints = useMemo(() => (hdms?.items || []).filter((h) => h.lat && h.lng), [hdms]);
  const hdmsActive = useMemo(() => hdmsPoints.filter((h) => h.active).length, [hdmsPoints]);
  // Districts with the most open tickets, busiest first
  const hdmsAreas = useMemo(() => {
    const by = {};
    for (const h of hdmsPoints) {
      if (!h.active) continue;
      const name = !h.amphoe ? h.province : h.province === 'กรุงเทพมหานคร' ? `เขต${h.amphoe}` : `อ.${h.amphoe} จ.${h.province}`;
      (by[name] ||= []).push(h);
    }
    return Object.entries(by).map(([name, items]) => ({ name, items })).sort((a, b) => b.items.length - a.items.length).slice(0, 5);
  }, [hdmsPoints]);

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

  // One pill per camera the AI saw water on (plus a dot per dry / unclear camera when asked); faded when the frame is old
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    for (const m of camFloodMarkersRef.current) m.remove();
    camFloodMarkersRef.current = [];
    if (!showCamFlood || !camFlood) return;
    for (const c of camFlood.items || []) {
      if (c.lat == null || c.lng == null) continue;
      const sty = CAM_FLOOD_STYLE[c.level] || CAM_FLOOD_STYLE.unclear;
      const wet = CAM_WET.includes(c.level);
      const el = document.createElement('button');
      el.type = 'button';
      el.title = `กล้อง ${c.title}: ${sty.label}${c.stale ? ' (ภาพเก่า)' : ''}`;
      if (wet) {
        el.style.cssText = `display:flex;align-items:center;gap:3px;padding:2px 7px 2px 5px;border-radius:6px;background:${sty.color};color:#fff;font:700 11px/1 var(--font-sans);border:2px ${c.stale ? 'dashed' : 'solid'} #fff;box-shadow:0 0 0 ${c.stale ? 2 : 5}px ${sty.color}44,0 1px 4px rgba(15,23,42,.35);cursor:pointer;opacity:${c.stale ? 0.6 : 1}`;
        el.innerHTML = `<span style="font-size:11px">📷</span><span>${esc(sty.label)}</span>`;
      } else {
        el.style.cssText = `width:10px;height:10px;border-radius:3px;background:${sty.color};border:2px solid #fff;box-shadow:0 1px 3px rgba(15,23,42,.3);cursor:pointer;padding:0;opacity:${c.stale ? 0.45 : 0.85}`;
      }
      const popup = new maplibregl.Popup({ offset: 12, closeButton: true, maxWidth: '320px' }).setHTML(
        `<div style="font-size:13px;line-height:1.45">
          <b>${esc(c.title)}</b>
          <br><span style="color:#64748b">${[c.road, c.district ? `เขต${c.district}` : c.province].filter(Boolean).map(esc).join(' · ')}${c.road || c.district || c.province ? ' · ' : ''}${c.kind === 'itic' ? `กล้อง ${esc(c.organization || 'iTIC')}` : 'กล้อง กทม.'}</span>
          <br><span style="color:${sty.color};font-weight:700">${sty.label}</span>
          <span style="color:#64748b">· AI มั่นใจ ${Math.round((c.confidence || 0) * 100)}%</span>
          ${c.note_th ? `<br><span>${esc(c.note_th)}</span>` : ''}
          <img src="/api/flood/cameras/${encodeURIComponent(c.camid)}/image?t=${c.checked_at}" alt="ภาพที่ AI ดู จากกล้อง ${esc(c.title)}" loading="lazy" style="display:block;margin-top:6px;width:100%;aspect-ratio:352/288;object-fit:cover;border-radius:6px;background:#e2e8f0">
          ${wet && c.wet_since ? `<span style="color:#64748b">เห็นน้ำตั้งแต่ ${fmtTime(c.wet_since)} น.</span><br>` : ''}
          <span style="color:${c.stale ? '#b45309' : '#94a3b8'};font-size:11px">ภาพเมื่อ ${fmtTime(c.frame_ts)} น. (${agoTh(c.frame_ts)})${c.stale ? ' · ภาพเก่า กล้องยังไม่ส่งภาพใหม่' : ''}</span>
          <br><span style="color:#94a3b8;font-size:11px">AI ดูจากภาพกล้อง อาจผิดพลาดได้</span>
        </div>`
      );
      // a wet pill stands just above its point, so it does not cover the CCTV pin of the same (iTIC) camera
      const place = wet ? { anchor: 'bottom', offset: [0, -10] } : {};
      camFloodMarkersRef.current.push(new maplibregl.Marker({ element: el, ...place }).setLngLat([c.lng, c.lat]).setPopup(popup).addTo(map));
    }
  }, [camFlood, showCamFlood]);

  // One pin per report from the public, with its photo in the popup
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    for (const m of userReportMarkersRef.current) m.remove();
    userReportMarkersRef.current = [];
    if (!showUserReports || !userReports) return;
    for (const u of userReports.items || []) {
      const el = document.createElement('button');
      el.type = 'button';
      el.title = `ประชาชนแจ้งน้ำท่วม ${agoTh(u.ts)} · น้ำสูง${u.depth_th}`;
      el.style.cssText = `width:26px;height:26px;border-radius:999px 999px 999px 3px;background:${USER_REPORT_COLOR};border:2px solid #fff;box-shadow:0 0 0 4px ${USER_REPORT_COLOR}44,0 1px 4px rgba(15,23,42,.35);color:#fff;font-size:13px;line-height:1;display:flex;align-items:center;justify-content:center;cursor:pointer;padding:0`;
      el.textContent = u.photo ? '📷' : '💧';
      const popup = new maplibregl.Popup({ offset: 14, closeButton: true, maxWidth: '300px' }).setHTML(
        `<div style="font-size:13px;line-height:1.45">
          <b style="color:${USER_REPORT_COLOR}">ประชาชนแจ้ง ยังไม่ยืนยัน</b> <span style="color:#64748b">· ${agoTh(u.ts)}</span>
          <br>น้ำสูง<b>${esc(u.depth_th)}</b> <span style="color:#64748b">(~${u.depth_cm} ซม.)</span>
          ${u.note ? `<br><span>${esc(u.note)}</span>` : ''}
          ${u.photo ? `<img src="${esc(u.photo)}" alt="รูปจากผู้แจ้ง" loading="lazy" style="display:block;margin-top:6px;width:100%;max-height:200px;object-fit:cover;border-radius:6px;background:#e2e8f0">` : ''}
          ${u.photo && u.ai_level_th ? `<span style="color:#64748b;font-size:11px">AI ดูรูปแล้ว: ${esc(u.ai_level_th)}${u.ai_note ? ` · ${esc(u.ai_note)}` : ''}</span>` : ''}
        </div>`
      );
      userReportMarkersRef.current.push(new maplibregl.Marker({ element: el }).setLngLat([u.lng, u.lat]).setPopup(popup).addTo(map));
    }
  }, [userReports, showUserReports]);

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

  // One pin per highway flood ticket: solid while open, faded once closed
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    for (const m of hdmsMarkersRef.current) m.remove();
    hdmsMarkersRef.current = [];
    if (!showHdms) return;
    for (const h of hdmsPoints) {
      const el = document.createElement('button');
      el.type = 'button';
      el.title = `กรมทางหลวง: ${h.place || h.title}${h.depth_cm ? ` · ${h.depth_cm} ซม.` : ''}`;
      el.style.cssText = `width:24px;height:24px;border-radius:6px;background:${HDMS_COLOR};border:2px solid #fff;box-shadow:0 1px 4px rgba(15,23,42,.35);color:#fff;font-size:12px;line-height:1;display:flex;align-items:center;justify-content:center;cursor:pointer;padding:0;opacity:${h.active ? 1 : 0.5}`;
      el.textContent = '🛣';
      const popup = new maplibregl.Popup({ offset: 14, closeButton: true, maxWidth: '300px' }).setHTML(
        `<div style="font-size:13px;line-height:1.45">
          <b style="color:${HDMS_COLOR}">ทางหลวงน้ำท่วม (กรมทางหลวง)</b> <span style="color:#64748b">· ${agoTh(h.ts)}</span>
          <br><b>${esc(h.place || h.title)}</b>
          <br><span>${esc(h.title)}</span>
          ${h.depth_cm ? `<br>ระดับน้ำ: <b>${esc(h.depth_cm)} ซม.</b>` : ''}
          ${h.closure || h.lane_closure ? `<br>${esc(h.closure || 'ปิดช่องจราจร')}` : ''}
          ${h.relief ? `<br><span style="color:#475569">${esc(h.relief)}</span>` : ''}
          <br><span style="color:#64748b">${h.amphoe ? `${esc(h.amphoe)} · ` : ''}${esc(h.province)}${h.depot ? ` · ${esc(h.depot)}` : ''}</span>
          <br><span style="color:#64748b">สถานะ: ${h.active ? 'ยังมีน้ำท่วม' : 'คลี่คลายแล้ว'}</span>
        </div>`
      );
      hdmsMarkersRef.current.push(new maplibregl.Marker({ element: el }).setLngLat([h.lng, h.lat]).setPopup(popup).addTo(map));
    }
  }, [hdmsPoints, showHdms]);

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
          <br><span style="color:#64748b">${g.kind === 'river' ? 'จุดวัดน้ำแม่น้ำ' : 'จุดวัดน้ำคลอง'}${g.district ? ` · ${esc(g.district)}` : ''}${g.province ? ` · ${esc(g.province)}` : ''}</span>
          <br><span style="color:${sty.color};font-weight:700">${sty.label}</span>${g.storage_pct != null ? ` น้ำเต็ม <b>${g.storage_pct}%</b>` : ''}
          ${g.msl != null ? `<br><span style="color:#64748b">ระดับน้ำ ${g.msl} ม.${g.bank != null ? ` · ตลิ่ง ${g.bank} ม.` : ''} (วัดจากระดับน้ำทะเล)</span>` : ''}
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
      el.title = `${s.name}: ฝุ่น PM2.5 ${s.pm25} (${s.label})`;
      el.style.cssText = `display:flex;align-items:center;justify-content:center;width:30px;height:22px;border-radius:7px;background:${s.color};color:#0f172a;font:700 11px/1 var(--font-sans);border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.35);cursor:pointer;padding:0`;
      el.textContent = Math.round(s.pm25);
      const t = s.ts ? new Date(s.ts * 1000).toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' }) : '';
      const popup = new maplibregl.Popup({ offset: 14, closeButton: true, maxWidth: '260px' }).setHTML(
        `<div style="font-size:13px;line-height:1.4"><b>${s.name}</b><br><span style="color:#64748b">${s.area} ${s.province}</span><br>` +
          `ฝุ่น PM2.5 <b style="color:${s.color}">${s.pm25}</b> · ${s.label}` +
          (t ? `<br><span style="color:#64748b;font-size:11px">ข้อมูล ${t} น. · ${s.source_label || 'Air4Thai (คพ.)'}</span>` : '') +
          '</div>'
      );
      pmMarkersRef.current.push(new maplibregl.Marker({ element: el }).setLngLat([s.lng, s.lat]).setPopup(popup).addTo(map));
    }
  }, [air, showPm]);

  // NASA satellite layers (nasa_feeds.py): FIRMS fire hotspots and EONET storms / natural events. Read when a
  // layer is first turned on, then every 30 minutes while the page is open (the server reads NASA hourly).
  const [showFires, setShowFires] = useState(false);
  const [showStorms, setShowStorms] = useState(false);
  const [nasaFires, setNasaFires] = useState(null);
  const [nasaEvents, setNasaEvents] = useState(null);
  const nasaEventsRef = useRef(null);   // for the event popup, which is wired once
  nasaEventsRef.current = nasaEvents;
  const nasaWanted = showFires || showStorms;
  useEffect(() => {
    if (!isActive || !nasaWanted) return;
    let alive = true;
    const tick = () => {
      fetchNasaFires().then((d) => alive && d && setNasaFires(d)).catch(() => {});
      fetchNasaEvents().then((d) => alive && d && setNasaEvents(d)).catch(() => {});
    };
    tick();
    const id = setInterval(tick, 1800000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [isActive, nasaWanted]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const apply = () => {
      const fires = {
        type: 'FeatureCollection',
        features: (nasaFires?.points || []).map(([lat, lng, frp, conf, ts, province]) => ({
          type: 'Feature', geometry: { type: 'Point', coordinates: [lng, lat] }, properties: { frp, conf, ts, province },
        })),
      };
      const storms = (nasaEvents?.items || []);
      const events = {
        type: 'FeatureCollection',
        features: [
          ...storms.filter((e) => e.track.length > 1).map((e) => ({
            type: 'Feature', geometry: { type: 'LineString', coordinates: e.track.map(([a, b]) => [b, a]) }, properties: { id: e.id },
          })),
          ...storms.map((e) => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [e.lng, e.lat] }, properties: { id: e.id, kind: e.kind } })),
        ],
      };
      for (const [id, data] of [['nasa-fires', fires], ['nasa-events', events]]) {
        if (map.getSource(id)) map.getSource(id).setData(data);
        else map.addSource(id, { type: 'geojson', data });
      }
      if (!map.getLayer('nasa-fires')) {
        map.addLayer({
          id: 'nasa-fires', type: 'circle', source: 'nasa-fires',
          paint: {
            'circle-radius': ['interpolate', ['linear'], ['zoom'], 5, 3, 10, 6, 14, 9],
            'circle-color': ['case', ['>=', ['get', 'frp'], 20], '#dc2626', ['>=', ['get', 'frp'], 5], '#f97316', '#fbbf24'],
            'circle-stroke-color': '#ffffff', 'circle-stroke-width': 1, 'circle-opacity': 0.9,
          },
        });
        map.addLayer({ id: 'nasa-track', type: 'line', source: 'nasa-events', filter: ['==', ['geometry-type'], 'LineString'],
          paint: { 'line-color': '#7c3aed', 'line-width': 2, 'line-dasharray': [2, 1.5] } });
        map.addLayer({ id: 'nasa-event', type: 'circle', source: 'nasa-events', filter: ['==', ['geometry-type'], 'Point'],
          paint: { 'circle-radius': 8, 'circle-color': ['match', ['get', 'kind'], 'severeStorms', '#7c3aed', 'floods', '#2563eb', 'volcanoes', '#b91c1c', '#64748b'],
            'circle-stroke-color': '#ffffff', 'circle-stroke-width': 2 } });
        map.on('click', 'nasa-fires', (ev) => {
          const p = ev.features[0].properties;
          const when = new Date(p.ts * 1000).toLocaleString('th-TH', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
          new maplibregl.Popup({ maxWidth: '260px' }).setLngLat(ev.lngLat).setHTML(
            `<div style="font-size:13px;line-height:1.45"><b>จุดความร้อนจากดาวเทียม</b><br>${p.province ? `จ.${p.province}` : 'นอกประเทศไทย'} · ${when} น.<br>` +
            `ความแรงของไฟ ${p.frp} MW${p.frp >= 20 ? ' (ไฟแรง)' : p.frp >= 5 ? ' (ปานกลาง)' : ' (เล็ก)'} · ความมั่นใจ${p.conf === 'h' ? 'สูง' : 'ปกติ'}<br>` +
            '<span style="color:#64748b;font-size:11px">NASA FIRMS (VIIRS) · อาจเป็นไฟป่า การเผาในไร่ หรือโรงงาน</span></div>'
          ).addTo(map);
        });
        map.on('click', 'nasa-event', (ev) => {
          const e = (nasaEventsRef.current?.items || []).find((x) => x.id === ev.features[0].properties.id);
          if (!e) return;
          new maplibregl.Popup({ maxWidth: '280px' }).setLngLat(ev.lngLat).setHTML(
            `<div style="font-size:13px;line-height:1.45"><b>${e.kind_th}: ${e.title}</b><br>${nasaEventLine(e)}` +
            (e.link ? `<br><a href="${e.link}" target="_blank" rel="noopener" style="color:#2563eb">ที่มาของข้อมูล</a>` : '') +
            '<br><span style="color:#64748b;font-size:11px">NASA EONET</span></div>'
          ).addTo(map);
        });
        for (const id of ['nasa-fires', 'nasa-event']) {
          map.on('mouseenter', id, () => { map.getCanvas().style.cursor = 'pointer'; });
          map.on('mouseleave', id, () => { map.getCanvas().style.cursor = ''; });
        }
      }
      map.setLayoutProperty('nasa-fires', 'visibility', showFires ? 'visible' : 'none');
      for (const id of ['nasa-track', 'nasa-event']) map.setLayoutProperty(id, 'visibility', showStorms ? 'visible' : 'none');
    };
    if (map.isStyleLoaded()) apply();
    else map.once('load', apply);
  }, [nasaFires, nasaEvents, showFires, showStorms]);

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
      .filter((c) => c.latitude && c.longitude && (pinsOn.cctv || (pinsOn.floodcam && c.floodRisk)))
      .forEach((c) => {
        const on = active.includes(c.camid);
        const pinColor = PIN_COLOR[c.province] || PIN;
        const el = pinEl(pinColor, on, pinsOn.floodcam ? c.floodRisk : null);
        el.setAttribute('aria-label', c.short_title || c.title);

        const orgTag = c.organization ? `<span style="display:inline-block;padding:2px 6px;border-radius:4px;font-size:10px;font-weight:600;background:#e0f2fe;color:#0369a1;margin-bottom:6px">${esc(c.organization)}</span>` : '';

        const floodHtml = c.floodRisk
          ? `<div style="background:${c.floodRisk.isOverflow ? '#fef2f2' : '#fffbeb'};border:1px solid ${c.floodRisk.isOverflow ? '#fecaca' : '#fde68a'};border-radius:6px;padding:6px 8px;margin-bottom:8px;font-size:11px;color:${c.floodRisk.isOverflow ? '#991b1b' : '#92400e'}">
              <div style="font-weight:700;display:flex;align-items:center;gap:4px">
                ${esc(c.floodRisk.badgeText)} · น้ำเต็ม ${c.floodRisk.storagePct}%
              </div>
              <div style="font-size:10px;margin-top:2px;color:${c.floodRisk.isOverflow ? '#b91c1c' : '#b45309'}">
                จุดวัดน้ำใกล้กล้อง: ${esc(c.floodRisk.stationName)} ห่าง ${c.floodRisk.distanceKm} กม.
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
              <button data-act="ai" data-camid="${c.camid}" style="cursor:pointer;border:0;border-radius:8px;padding:6px 12px;background:#f1f5f9;color:#0f172a;border:1px solid #cbd5e1;font-size:12px;font-family:inherit">${c.floodRisk ? 'ถาม AI เรื่องน้ำท่วม' : 'ถาม AI'}</button>
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
          const fail = () => status && (status.textContent = 'ยังดูภาพจากกล้องนี้ไม่ได้ ลองใหม่อีกครั้ง');

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
  }, [currentCameras, active, isActive, pinsOn.cctv, pinsOn.floodcam]);

  useEffect(() => {
    if (!isActive) return undefined;
    const load = () => {
      fetchRoadEvents().then(setRoadEvents).catch(() => {});
      fetchNationalFloods().then(setNationFloods).catch(() => {});
    };
    load();
    const id = setInterval(load, 60000);
    return () => clearInterval(id);
  }, [isActive]);

  // Camera-confirmed incidents + reported ones in every province (Bangkok's Longdo list until those load)
  const incidentList = useMemo(
    () => [...(incidents?.camera || []), ...(roadEvents?.incidents || incidents?.longdo || [])],
    [incidents, roadEvents],
  );
  const closures = useMemo(() => (roadEvents?.closures || []).filter((c) => c.latitude && c.longitude), [roadEvents]);

  // Sync incident markers
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    incidentMarkersRef.current.forEach((m) => m.remove());
    incidentMarkersRef.current = [];
    incidentByIdRef.current = {};
    const all = incidentList
      .filter((i) => i.latitude && i.longitude && (i.kind === 'breakdown' ? pinsOn.breakdown : pinsOn.accident));
    all.forEach((i) => {
      const when = i.source === 'camera' ? agoTh(i.ts) : i.start ? `เริ่ม ${esc(i.start).slice(11, 16)}` : '';
      const html = `<div style="width:260px">
          <p style="margin:0 0 4px;font-weight:600;color:${i.kind === 'breakdown' ? '#b85f41' : '#d9534f'};font-size:13px">${KIND_TH[i.kind] || 'เหตุบนถนน'} · ${sourceTh(i)}</p>
          <p style="margin:0 0 6px;color:#0f172a;font-size:13px;line-height:1.35">${esc(i.title)}</p>
          ${placeTh(i) ? `<p style="margin:0 0 6px;color:#475569;font-size:12px">${esc(placeTh(i))}</p>` : ''}
          ${i.image ? `<img src="${i.image}" alt="" style="display:block;width:100%;border-radius:8px;margin-bottom:6px" />` : ''}
          ${i.description ? `<p style="margin:0 0 6px;color:#475569;font-size:12px;line-height:1.4">${esc(i.description)}</p>` : ''}
          <p style="margin:0;color:#94a3b8;font-size:11px">${when}${i.stopped_s ? ` · รถจอดนิ่งมา ${Math.max(1, Math.round(i.stopped_s / 60))} นาที` : ''}</p>
          ${i.camid ? `<div style="margin-top:8px"><button data-act="ai" data-camid="${esc(i.camid)}" style="cursor:pointer;border:0;border-radius:8px;padding:6px 12px;background:#2563eb;color:#fff;font-size:12px;font-family:inherit">ดูภาพสดกล้องนี้</button></div>` : ''}
        </div>`;
 const popup = new maplibregl.Popup({ offset: 18, closeButton: true, maxWidth: '300px', anchor: 'bottom' }).setHTML(html);
 const m = new maplibregl.Marker({ element: incidentEl(i.kind) }).setLngLat([i.longitude, i.latitude]).setPopup(popup).addTo(map);
 incidentMarkersRef.current.push(m);
 incidentByIdRef.current[i.id] = m;
    });
  }, [incidentList, isActive, pinsOn.accident, pinsOn.breakdown]);

  // Sync closed-road markers
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    closureMarkersRef.current.forEach((m) => m.remove());
    closureMarkersRef.current = [];
    closureByIdRef.current = {};
    if (!pinsOn.closure) return;
    closures.forEach((c) => {
      const until = feedTimeTh(c.stop);
      const html = `<div style="width:260px">
          <p style="margin:0 0 4px;font-weight:600;color:${CLOSURE_COLOR[c.kind]};font-size:13px">${closureTh(c)}</p>
          <p style="margin:0 0 4px;color:#0f172a;font-size:13px;line-height:1.35">${esc(c.title)}</p>
          ${placeTh(c) ? `<p style="margin:0 0 6px;color:#475569;font-size:12px">${esc(placeTh(c))}</p>` : ''}
          ${c.description ? `<p style="margin:0 0 6px;color:#475569;font-size:12px;line-height:1.4">${esc(c.description)}</p>` : ''}
          <p style="margin:0;color:#94a3b8;font-size:11px">${until ? `ถึง ${until} · ` : ''}${sourceTh(c)}</p>
        </div>`;
      const popup = new maplibregl.Popup({ offset: 16, closeButton: true, maxWidth: '300px', anchor: 'bottom' }).setHTML(html);
      const m = new maplibregl.Marker({ element: closureEl(c) }).setLngLat([c.longitude, c.latitude]).setPopup(popup).addTo(map);
      closureMarkersRef.current.push(m);
      closureByIdRef.current[c.id] = m;
    });
  }, [closures, isActive, pinsOn.closure]);

  // Flooded places in every province. An impassable road is already a closed-road pin while those are shown.
  const nationFloodPoints = useMemo(
    () => (nationFloods?.items || []).filter((f) => f.lat && f.lng && !(pinsOn.closure && f.passable === false)),
    [nationFloods, pinsOn.closure],
  );
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    nationFloodMarkersRef.current.forEach((m) => m.remove());
    nationFloodMarkersRef.current = [];
    if (!pinsOn.flood) return;
    nationFloodPoints.forEach((f) => {
      const label = f.kind === 'river' ? 'แม่น้ำล้นตลิ่ง' : f.passable === false ? 'ถนนน้ำท่วม รถผ่านไม่ได้' : f.passable ? 'ถนนน้ำท่วม รถยังผ่านได้' : 'ถนนน้ำท่วม';
      const html = `<div style="width:260px">
          <p style="margin:0 0 4px;font-weight:600;color:${NATION_FLOOD_COLOR[f.kind]};font-size:13px">${label}${f.depth_cm ? ` · น้ำลึก ${esc(f.depth_cm)} ซม.` : ''}</p>
          <p style="margin:0 0 4px;color:#0f172a;font-size:13px;line-height:1.35">${esc(f.title)}</p>
          ${placeTh(f) ? `<p style="margin:0 0 6px;color:#475569;font-size:12px">${esc(placeTh(f))}</p>` : ''}
          ${f.description ? `<p style="margin:0 0 6px;color:#475569;font-size:12px;line-height:1.4">${esc(f.description)}</p>` : ''}
          <p style="margin:0;color:#94a3b8;font-size:11px">${f.ts ? `${agoTh(f.ts)} · ` : ''}${esc(f.source)}</p>
        </div>`;
      const popup = new maplibregl.Popup({ offset: 14, closeButton: true, maxWidth: '300px', anchor: 'bottom' }).setHTML(html);
      nationFloodMarkersRef.current.push(new maplibregl.Marker({ element: nationFloodEl(f) }).setLngLat([f.lng, f.lat]).setPopup(popup).addTo(map));
    });
  }, [nationFloodPoints, isActive, pinsOn.flood]);

  const flyToClosure = (c) => {
    const map = mapRef.current;
    if (!map) return;
    map.flyTo({ center: [c.longitude, c.latitude], zoom: 14, duration: 800 });
    if (!pinsOn.closure) setPinsOn((p) => ({ ...p, closure: true }));
    setTimeout(() => closureByIdRef.current[c.id]?.togglePopup(), 850);
  };
  const showThailand = () => mapRef.current?.fitBounds(THAILAND, { padding: 30, duration: 800 });

 const flyToIncident = (i) => {
 const map = mapRef.current;
 if (!map || !i.latitude) return;
 map.flyTo({ center: [i.longitude, i.latitude], zoom: 15, duration: 800 });
 // a kind switched off in the legend comes back on, so the picked incident has a pin to open
 const kind = i.kind === 'breakdown' ? 'breakdown' : 'accident';
 if (!pinsOn[kind]) setPinsOn((p) => ({ ...p, [kind]: true }));
 setTimeout(() => incidentByIdRef.current[i.id]?.togglePopup(), 850);
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

 // The accuracy circle shows how far off the fix may be: a computer on a LAN cable is placed by its IP address
 const locateMe = () => {
 if (!navigator.geolocation) return onToast('เบราว์เซอร์นี้ไม่รองรับตำแหน่ง');
 navigator.geolocation.getCurrentPosition(
      (p) => {
 const map = mapRef.current;
 if (!map) return;
 const { longitude: lng, latitude: lat, accuracy } = p.coords;
 if (!meMarkerRef.current) {
 const dot = document.createElement('span');
 dot.style.cssText = 'display:block;width:18px;height:18px;border-radius:999px;background:#8a72c4;border:3px solid #fff;box-shadow:0 0 0 6px rgba(138,114,196,.25)';
 meMarkerRef.current = new maplibregl.Marker({ element: dot });
        }
 meMarkerRef.current.setLngLat([lng, lat]).addTo(map);
 showAccuracy(map, lng, lat, accuracy);
 frameFix(map, lng, lat, accuracy, 15);
 onToast(roughWarning(accuracy) || `ตำแหน่งของคุณ แม่นยำ ${accuracyText(accuracy)}`);
      },
      () => onToast('ขอตำแหน่งไม่สำเร็จ'),
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
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

  const trafficOn = (showTraffic ? 1 : 0) + (showRail ? 1 : 0) + Object.values(pinsOn).filter(Boolean).length;
  const waterOn = [showRainRadar, showCamFlood, showUserReports, showFlood, showReports, showHdms, showGauges].filter(Boolean).length;
  const optionsOn = trafficOn + waterOn + (showPm ? 1 : 0) + (showWind ? 1 : 0) + (showPlaces ? 1 : 0) + (showFires ? 1 : 0) + (showStorms ? 1 : 0);
  // What the NASA numbers mean, in plain words (the panel's analysis lines)
  const fireNotes = [];
  if (nasaFires) {
    const { th_24h: now, th_prev_24h: prev, near_bkk_24h: nearBkk, border_24h: border, regions } = nasaFires;
    if (!now) fireNotes.push('ไม่พบไฟในประเทศไทยใน 24 ชั่วโมงที่ผ่านมา');
    else {
      const change = prev ? Math.round(((now - prev) / prev) * 100) : null;
      fireNotes.push(`${now.toLocaleString()} จุดในไทย ${prev ? `(วันก่อน ${prev.toLocaleString()} จุด ${change >= 0 ? `เพิ่มขึ้น ${change}%` : `ลดลง ${-change}%`})` : '(วันก่อนไม่มี)'}`);
      if (regions?.[0]) fireNotes.push(`มากที่สุดที่${regions[0].region} ${regions[0].count} จุด`);
    }
    if (nearBkk) fireNotes.push(`มีไฟห่าง กทม. ไม่เกิน ${nasaFires.near_bkk_km} กม. ${nearBkk} จุด ถ้าลมพัดเข้า กทม. ฝุ่นอาจสูงขึ้น เปิดชั้นลมและฝุ่น PM2.5 ดูประกอบได้`);
    if (border > now) fireNotes.push(`ฝั่งเพื่อนบ้านใกล้ชายแดนมีไฟมากกว่าในไทย (${border.toLocaleString()} จุด) ควันอาจลอยข้ามมาภาคเหนือและอีสาน`);
  }
  const nearStorms = (nasaEvents?.items || []).filter((e) => e.kind === 'severeStorms' && e.km_to_thailand <= (nasaEvents?.near_km || 1500));
  const flyToNasa = (lat, lng, zoom) => mapRef.current?.flyTo({ center: [lng, lat], zoom, duration: 900 });
  const camCounts = camFlood?.counts || {};
  const camWet = CAM_WET.reduce((n, k) => n + (camCounts[k] || 0), 0);
  const camWetList = (camFlood?.items || []).filter((c) => CAM_WET.includes(c.level));
  // Until Traffy has answered once, its empty list is not "0 reports"
  const reportHint = reports?.updated_at ? `คนแจ้ง ${reportPoints.length} เรื่อง (6 ชม.)` : reports || reportsFailed ? 'คนแจ้ง: ยังโหลดไม่ได้' : 'คนแจ้ง: กำลังโหลด';
  const waterHint = flood
    ? `${camFlood ? `กล้องเห็นน้ำ ${camWet} จุด · ` : ''}ถนนท่วม ${floodCounts.flood + floodCounts.slight} จุด · ${reportHint}`
    : 'ฝนตก น้ำท่วมถนน คนแจ้งน้ำท่วม และระดับน้ำ';

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={PAGE_TITLES.map}
        description="สีของถนนบอกว่ารถติดแค่ไหน กดหมุดกล้องเพื่อดูภาพสด เลือกสิ่งที่จะแสดงบนแผนที่ได้ที่แผงตัวเลือก"
        actions={
          <Button size="sm" onClick={locateMe}>
            <Icon name="pin" /> ไปที่ตำแหน่งของฉัน
          </Button>
        }
      />
      <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-4 lg:h-[calc(100vh-13rem)] min-h-[520px]">
      {panelOpen && (
        <button type="button" aria-label="ปิดตัวเลือกแผนที่" onClick={() => setPanelOpen(false)} className="lg:hidden fixed inset-0 z-40 bg-slate-900/50 cursor-pointer" />
      )}
      <aside
        id="map-options"
        aria-label="สิ่งที่แสดงบนแผนที่"
        className={`${panelOpen ? 'flex' : 'hidden'} fixed inset-x-0 bottom-0 z-50 max-h-[75dvh] rounded-t-2xl pb-[calc(1rem+env(safe-area-inset-bottom))] shadow-2xl lg:static lg:z-auto lg:flex lg:max-h-none lg:rounded-xl lg:pb-4 lg:shadow-none lg:order-1 glass p-4 flex-col gap-3 overflow-y-auto scroll-soft`}
      >
        <div className="lg:hidden flex items-center justify-between gap-2 -mt-1">
          <p className="text-sm font-semibold text-ink-900">เลือกสิ่งที่แสดงบนแผนที่</p>
          <Button size="sm" onClick={() => setPanelOpen(false)}>
            เสร็จ
          </Button>
        </div>
        <LayerGroup title="รถติดและกล้อง" hint="สีรถติด กล้อง อุบัติเหตุ และรถไฟฟ้า" on={trafficOn} defaultOpen>
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="inline-flex items-center gap-2 text-sm text-ink-900 cursor-pointer">
                <input type="checkbox" checked={showTraffic} onChange={(e) => setShowTraffic(e.target.checked)} className="accent-lavender-600 w-4 h-4" />
                สีรถติดบนถนน
              </label>
              {summary && (
                <span className={`inline-flex items-center gap-1 text-[11px] rounded-lg px-2 py-0.5 ${summary.online ? 'bg-sage-50 text-sage-700' : 'bg-gold-50 text-gold-700'}`}>
                  {summary.online ? `สด ${updated}` : `ไม่อัปเดต ${updated || ''}`}
                </span>
              )}
            </div>
            <div className="grid grid-cols-3 gap-1.5 text-[11px] text-ink-600">
              <span className="inline-flex items-center gap-1.5"><span className="w-5 h-1.5 rounded-full" style={{ background: '#54C00C' }} />คล่องตัว</span>
              <span className="inline-flex items-center gap-1.5"><span className="w-5 h-1.5 rounded-full" style={{ background: '#FEDE04' }} />ชะลอตัว</span>
              <span className="inline-flex items-center gap-1.5"><span className="w-5 h-1.5 rounded-full" style={{ background: '#FF2020' }} />ติดขัด</span>
            </div>
            {summary?.ready && (
              <p className="mt-2 text-xs text-ink-600">
                ถนนทั้งเมืองติดขัด (สีแดง) <span className="text-base text-ink-900">{summary.red_pct}%</span>
              </p>
            )}
          </div>

          <div className="flex flex-col gap-2.5 text-xs">
            <p className="text-sm text-ink-900 font-medium">หมุดบนแผนที่</p>
            {/* กล้องจราจร */}
            <label className={`flex items-center gap-2.5 cursor-pointer ${pinsOn.cctv ? '' : 'opacity-50'}`}>
              <input type="checkbox" checked={pinsOn.cctv} onChange={() => togglePins('cctv')} className="accent-blue-600 w-4 h-4 shrink-0" />
              <span className="w-5 h-5 rounded-full bg-blue-600 border-2 border-white/90 shadow-xs shrink-0 flex items-center justify-center" />
              <div className="flex flex-col min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="font-medium text-ink-900">กล้องจราจร</span>
                  <span className="text-[10px] bg-blue-50 text-blue-700 px-1.5 py-0.5 rounded font-medium">{currentCameras.length} ตัว</span>
                </div>
                <span className="text-[11px] text-ink-600 leading-tight">
                  ใน กทม. และปริมณฑล {metroCameraCount} ตัว ที่เหลืออยู่ต่างจังหวัด · กดหมุดเพื่อดูภาพสด
                </span>
              </div>
            </label>

            {/* กล้องจุดเสี่ยงน้ำท่วม */}
            <label className={`flex items-center gap-2.5 cursor-pointer ${pinsOn.floodcam ? '' : 'opacity-50'}`}>
              <input type="checkbox" checked={pinsOn.floodcam} onChange={() => togglePins('floodcam')} className="accent-blue-600 w-4 h-4 shrink-0" />
              <span className="relative w-5 h-5 rounded-full bg-blue-600 border-2 border-amber-400 shadow-xs shrink-0 flex items-center justify-center">
                <span className="absolute -top-1.5 -right-1.5 text-[9px] leading-none pointer-events-none">🌊</span>
              </span>
              <div className="flex flex-col min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="font-medium text-ink-900">กล้องจุดเสี่ยงน้ำท่วม</span>
                  {floodRiskCount > 0 && (
                    <span className="text-[10px] bg-amber-50 text-amber-700 px-1.5 py-0.5 rounded font-medium">{floodRiskCount} จุด</span>
                  )}
                </div>
                <span className="text-[11px] text-ink-600 leading-tight">กล้องใกล้แม่น้ำหรือคลองที่น้ำสูง</span>
              </div>
            </label>

            {/* อุบัติเหตุ */}
            <label className={`flex items-center gap-2.5 cursor-pointer ${pinsOn.accident ? '' : 'opacity-50'}`}>
              <input type="checkbox" checked={pinsOn.accident} onChange={() => togglePins('accident')} className="accent-blue-600 w-4 h-4 shrink-0" />
              <span className="w-5 h-5 rounded-full bg-red-600 border-2 border-white/90 shadow-xs text-white font-bold text-[11px] flex items-center justify-center shrink-0 leading-none">
                !
              </span>
              <div className="flex flex-col min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="font-medium text-ink-900">อุบัติเหตุ</span>
                  <span className="text-[10px] bg-red-50 text-red-700 px-1.5 py-0.5 rounded font-medium">{incidentList.filter((i) => i.kind !== 'breakdown').length} จุด</span>
                </div>
                <span className="text-[11px] text-ink-600 leading-tight">ทั่วประเทศ จากกล้อง AI และข่าวจราจร</span>
              </div>
            </label>

            {/* น้ำท่วมทั่วประเทศ */}
            <label className={`flex items-center gap-2.5 cursor-pointer ${pinsOn.flood ? '' : 'opacity-50'}`}>
              <input type="checkbox" checked={pinsOn.flood} onChange={() => togglePins('flood')} className="accent-blue-600 w-4 h-4 shrink-0" />
              <span className="w-5 h-5 border-2 border-white/90 shadow-xs text-white font-bold text-[12px] flex items-center justify-center shrink-0 leading-none" style={{ background: NATION_FLOOD_COLOR.road, borderRadius: '999px 999px 999px 3px' }}>
                ≈
              </span>
              <div className="flex flex-col min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="font-medium text-ink-900">น้ำท่วม</span>
                  <span className="text-[10px] bg-blue-50 text-blue-700 px-1.5 py-0.5 rounded font-medium">{nationFloods?.counts?.road ?? 0} ถนน · {nationFloods?.counts?.river ?? 0} แม่น้ำ</span>
                </div>
                <span className="text-[11px] text-ink-600 leading-tight">ทั่วประเทศ ถนนน้ำท่วม (หยดฟ้า) และแม่น้ำล้นตลิ่ง (สี่เหลี่ยมน้ำเงิน) · ถนนที่ผ่านไม่ได้ขึ้นเป็นถนนปิด</span>
              </div>
            </label>

            {/* ถนนปิด */}
            <label className={`flex items-center gap-2.5 cursor-pointer ${pinsOn.closure ? '' : 'opacity-50'}`}>
              <input type="checkbox" checked={pinsOn.closure} onChange={() => togglePins('closure')} className="accent-blue-600 w-4 h-4 shrink-0" />
              <span className="w-5 h-5 rounded-full border-2 border-white/90 shadow-xs flex items-center justify-center shrink-0" style={{ background: CLOSURE_COLOR.closed }}>
                <span className="block w-2.5 h-[3px] rounded-sm bg-white" />
              </span>
              <div className="flex flex-col min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="font-medium text-ink-900">ถนนปิด</span>
                  <span className="text-[10px] bg-red-50 text-red-700 px-1.5 py-0.5 rounded font-medium">{closures.length} จุด</span>
                </div>
                <span className="text-[11px] text-ink-600 leading-tight">ทั่วประเทศ ปิดทั้งสาย ปิดเพราะน้ำท่วม และเบี่ยงจราจร (สี่เหลี่ยมส้ม)</span>
              </div>
            </label>

            {/* รถจอดเสีย */}
            <label className={`flex items-center gap-2.5 cursor-pointer ${pinsOn.breakdown ? '' : 'opacity-50'}`}>
              <input type="checkbox" checked={pinsOn.breakdown} onChange={() => togglePins('breakdown')} className="accent-blue-600 w-4 h-4 shrink-0" />
              <span className="w-5 h-5 rounded-full bg-amber-500 border-2 border-white/90 shadow-xs text-white font-bold text-[11px] flex items-center justify-center shrink-0 leading-none">
                !
              </span>
              <div className="flex flex-col min-w-0">
                <span className="font-medium text-ink-900">รถเสีย</span>
                <span className="text-[11px] text-ink-600 leading-tight">รถจอดเสียขวางถนน</span>
              </div>
            </label>
          </div>

          {/* BTS / MRT overlay toggle */}
          <div>
            <label className="inline-flex items-center gap-2 text-sm text-ink-900 cursor-pointer font-medium">
              <input type="checkbox" checked={showRail} onChange={(e) => setShowRail(e.target.checked)} className="accent-blue-600 w-4 h-4" />
              🚇 รถไฟฟ้า
            </label>
            <p className="text-[11px] text-slate-500 mt-1">BTS MRT แอร์พอร์ตลิงก์ และสายสีแดง · กดสถานีเพื่อดูชื่อ</p>
          </div>
        </LayerGroup>

        <LayerGroup title="น้ำท่วมและฝน" hint={waterHint} on={waterOn}>
          {/* Rain radar overlay toggle */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="inline-flex items-center gap-2 text-sm text-ink-900 cursor-pointer font-medium">
                <input
                  type="checkbox"
                  checked={showRainRadar}
                  onChange={(e) => setShowRainRadar(e.target.checked)}
                  className="accent-blue-600 w-4 h-4"
                />
                <Icon name="rain" /> ฝนตกตอนนี้ (เรดาร์)
              </label>
              {radarTime && (
                <span className="text-[11px] text-blue-600 font-semibold bg-blue-50 px-2 py-0.5 rounded-full">
                  สด {radarTime}
                </span>
              )}
            </div>
            <p className="text-[11px] text-slate-500 mb-1.5">แสดงบริเวณที่ฝนกำลังตก</p>
            {showRainRadar && (
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-slate-400 shrink-0">ความเข้มของสี</span>
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

          {/* AI ดูน้ำท่วมจากภาพกล้อง กทม. ทุกตัว */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="inline-flex items-center gap-2 text-sm text-ink-900 cursor-pointer font-medium">
                <input type="checkbox" checked={showCamFlood} onChange={(e) => setShowCamFlood(e.target.checked)} className="accent-blue-600 w-4 h-4" />
                <span aria-hidden="true">📷</span> AI เห็นน้ำท่วมในภาพกล้อง
              </label>
              {camFlood?.last_check && <span className="text-[11px] text-slate-500">{fmtTime(camFlood.last_check)} น.</span>}
            </div>
            {camFlood ? (
              <>
                <p className="text-[11px] text-slate-500 mb-1.5">
                  {camWet > 0
                    ? `ท่วมหนัก ${camCounts.severe} · ท่วม ${camCounts.flooded} · น้ำขัง ${camCounts.puddle} จุด`
                    : 'ไม่พบน้ำท่วมบนถนนในภาพกล้อง'}
                  {` · ดูแล้ว ${camFlood.checked} จาก ${camFlood.total} กล้อง`}
                  {camFlood.stale_wet > 0 ? ` · ${camFlood.stale_wet} จุดเป็นภาพเก่า` : ''}
                  {!camFlood.enabled ? ' · AI ยังไม่พร้อม' : camFlood.error ? ' · AI ขัดข้อง กำลังลองใหม่' : ''}
                </p>
                <div className="flex flex-wrap gap-x-2 gap-y-1 text-[11px] text-slate-600 mb-1.5">
                  {CAM_WET.map((k) => (
                    <span key={k} className="inline-flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm" style={{ background: CAM_FLOOD_STYLE[k].color }} />{CAM_FLOOD_STYLE[k].label}</span>
                  ))}
                </div>
                <label className="inline-flex items-center gap-2 text-[11px] text-slate-600 cursor-pointer">
                  <input type="checkbox" checked={camFloodDry} onChange={(e) => setCamFloodDry(e.target.checked)} className="accent-blue-600" disabled={!showCamFlood} />
                  แสดงกล้องที่ไม่มีน้ำท่วมหรือภาพไม่ชัดด้วย
                </label>
                {camWetList.length > 0 && (
                  <ul className="mt-2 flex flex-col gap-1">
                    {camWetList.slice(0, 8).map((c) => (
                      <li key={c.camid}>
                        <button
                          type="button"
                          onClick={() => mapRef.current?.easeTo({ center: [c.lng, c.lat], zoom: 15.5, duration: 800 })}
                          className={`cursor-pointer w-full flex items-center justify-between gap-2 rounded-lg border border-slate-200 px-2 py-1 text-left hover:border-slate-400 transition-colors ${c.stale ? 'opacity-60' : ''}`}
                        >
                          <span className="min-w-0 truncate text-[12px] text-ink-900">{c.title}</span>
                          <span className="shrink-0 text-[11px] font-semibold" style={{ color: CAM_FLOOD_STYLE[c.level].color }}>{CAM_FLOOD_STYLE[c.level].label}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </>
            ) : (
              <p className="text-[11px] text-slate-500">{showCamFlood ? 'กำลังโหลด ...' : 'เปิดเพื่อดูจุดที่ AI เห็นน้ำท่วมในภาพกล้อง'}</p>
            )}
            <p className="text-[11px] text-slate-400 mt-1">AI ดูภาพกล้องทุก ~10 นาที อาจผิดพลาดได้ · กดหมุดเพื่อดูภาพ</p>
          </div>

          {/* ประชาชนแจ้งน้ำท่วมผ่านเว็บนี้ (พร้อมรูป ผ่าน AI ตรวจ) */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="inline-flex items-center gap-2 text-sm text-ink-900 cursor-pointer font-medium">
                <input type="checkbox" checked={showUserReports} onChange={(e) => setShowUserReports(e.target.checked)} className="accent-blue-600 w-4 h-4" />
                <span aria-hidden="true">📷</span> คนแจ้งผ่านเว็บนี้
              </label>
              {userReports && <span className="text-[11px] text-slate-500">{userReports.total} เรื่อง</span>}
            </div>
            <p className="text-[11px] text-slate-500">
              {userReports ? (userReports.total ? `${userReports.total} เรื่องใน ${userReports.hours} ชม. · AI ดูรูปก่อนขึ้นแผนที่` : `ยังไม่มีใครแจ้งใน ${userReports.hours} ชม.`) : 'เปิดเพื่อดูจุดที่คนแจ้งพร้อมรูป'}
            </p>
            <a href="#/report" className="text-[11px] text-blue-700 hover:underline">เห็นน้ำท่วม? กดตรงนี้เพื่อแจ้ง</a>
          </div>

          {/* น้ำท่วมขังถนน (เซ็นเซอร์ กทม.) + ระดับน้ำแม่น้ำ/คลอง (ปริมณฑล) */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="inline-flex items-center gap-2 text-sm text-ink-900 cursor-pointer font-medium">
                <input type="checkbox" checked={showFlood} onChange={(e) => setShowFlood(e.target.checked)} className="accent-blue-600 w-4 h-4" />
                <Icon name="water" /> น้ำท่วมบนถนน กทม. (เครื่องวัด)
              </label>
              {flood?.feed_time && <span className="text-[11px] text-slate-500">{fmtTime(flood.feed_time)} น.</span>}
            </div>
            {flood ? (
              <>
                <p className="text-[11px] text-slate-500 mb-1.5">
                  {floodCounts.flood + floodCounts.slight > 0
                    ? `ท่วม ${floodCounts.flood} จุด · เล็กน้อย ${floodCounts.slight} จุด จาก ${flood.total} จุดวัด`
                    : `ตอนนี้ไม่มีถนนน้ำท่วม (วัด ${flood.total} จุด)`}
                  {floodCounts.offline > 0 ? ` · เครื่องวัดเสีย ${floodCounts.offline}` : ''}
                </p>
                <div className="flex flex-wrap gap-x-2 gap-y-1 text-[11px] text-slate-600 mb-1.5">
                  <span className="inline-flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full" style={{ background: FLOOD_STYLE.flood.color }} />ท่วม &gt;10 ซม.</span>
                  <span className="inline-flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full" style={{ background: FLOOD_STYLE.slight.color }} />เล็กน้อย 5-10</span>
                  <span className="inline-flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full" style={{ background: FLOOD_STYLE.normal.color }} />ปกติ &le;5</span>
                </div>
                <label className="inline-flex items-center gap-2 text-[11px] text-slate-600 cursor-pointer">
                  <input type="checkbox" checked={floodDry} onChange={(e) => setFloodDry(e.target.checked)} className="accent-blue-600" disabled={!showFlood} />
                  แสดงจุดวัดที่ไม่มีน้ำท่วมด้วย
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
              <p className="text-[11px] text-slate-500">กำลังโหลด ...</p>
            )}
            <p className="text-[11px] text-slate-400 mt-1">เครื่องวัดน้ำบนถนนมีเฉพาะใน กทม.</p>
          </div>

          {/* ประชาชนแจ้งน้ำท่วม (Traffy Fondue) */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="inline-flex items-center gap-2 text-sm text-ink-900 cursor-pointer font-medium">
                <input type="checkbox" checked={showReports} onChange={(e) => setShowReports(e.target.checked)} className="accent-blue-600 w-4 h-4" />
                <span aria-hidden="true">📣</span> คนแจ้งน้ำท่วม (Traffy Fondue)
              </label>
              {reports?.updated_at && <span className="text-[11px] text-slate-500">{fmtTime(reports.updated_at)} น.</span>}
            </div>
            {reports ? (
              <>
                <p className="text-[11px] text-slate-500 mb-1.5">
                  {!reports.updated_at
                    ? 'ยังโหลดเรื่องจาก Traffy ไม่ได้ ระบบจะลองใหม่เอง'
                    : reportPoints.length > 0
                      ? `${reportPoints.length} เรื่องใน 6 ชม. · ชั่วโมงล่าสุด ${reportFresh} เรื่อง`
                      : 'ไม่มีคนแจ้งน้ำท่วมใน 6 ชม.'}
                  {(reports.error || reportsFailed) && reports.updated_at ? ' · อัปเดตล่าสุดไม่สำเร็จ' : ''}
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
              <p className="text-[11px] text-slate-500">{reportsFailed ? 'ยังโหลดเรื่องจาก Traffy ไม่ได้ ระบบจะลองใหม่เอง' : 'กำลังโหลด ...'}</p>
            )}
            <p className="text-[11px] text-slate-400 mt-1">เรื่องที่คนแจ้ง กทม. ผ่านแอป Traffy Fondue ยังไม่ได้ตรวจสอบโดยเขต</p>
          </div>

          {/* ทางหลวงน้ำท่วม (กรมทางหลวง HDMS) */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="inline-flex items-center gap-2 text-sm text-ink-900 cursor-pointer font-medium">
                <input type="checkbox" checked={showHdms} onChange={(e) => setShowHdms(e.target.checked)} className="accent-blue-600 w-4 h-4" />
                <span aria-hidden="true">🛣</span> ทางหลวงน้ำท่วม
              </label>
              {hdms?.updated_at && <span className="text-[11px] text-slate-500">{fmtTime(hdms.updated_at)} น.</span>}
            </div>
            {hdms ? (
              <>
                <p className="text-[11px] text-slate-500 mb-1.5">
                  {hdmsPoints.length > 0
                    ? `ยังท่วม ${hdmsActive} จุด · น้ำลดแล้วใน 3 ชม. ${hdmsPoints.length - hdmsActive} จุด`
                    : 'ไม่มีทางหลวงน้ำท่วมในกรุงเทพฯ และปริมณฑล'}
                  {hdms.error ? ' · อัปเดตล่าสุดไม่สำเร็จ' : ''}
                </p>
                {hdmsAreas.length > 0 && (
                  <ul className="flex flex-col gap-1">
                    {hdmsAreas.map((d) => (
                      <li key={d.name}>
                        <button
                          type="button"
                          onClick={() => { setShowHdms(true); mapRef.current?.easeTo({ center: [d.items[0].lng, d.items[0].lat], zoom: 14.5, duration: 800 }); }}
                          className="cursor-pointer w-full flex items-center justify-between gap-2 rounded-lg border border-slate-200 px-2 py-1 text-left hover:border-slate-400 transition-colors"
                        >
                          <span className="min-w-0 truncate text-[12px] text-ink-900">{d.name}</span>
                          <span className="shrink-0 text-[11px] font-semibold tabular-nums" style={{ color: HDMS_COLOR }}>{d.items.length} จุด</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </>
            ) : (
              <p className="text-[11px] text-slate-500">กำลังโหลด ...</p>
            )}
            <p className="text-[11px] text-slate-400 mt-1">ข้อมูลจากกรมทางหลวง เฉพาะกรุงเทพฯ และปริมณฑล</p>
          </div>

          {/* ระดับน้ำแม่น้ำ / คลอง ทั่วเขตปริมณฑล (คลังข้อมูลน้ำแห่งชาติ) */}
          <div>
            <label className="inline-flex items-center gap-2 text-sm text-ink-900 cursor-pointer font-medium">
              <input type="checkbox" checked={showGauges} onChange={(e) => setShowGauges(e.target.checked)} className="accent-blue-600 w-4 h-4" />
              <Icon name="water" /> น้ำในแม่น้ำและคลอง
            </label>
            {gauges.length > 0 ? (
              <>
                <p className="text-[11px] text-slate-500 mt-1 mb-1.5">
                  {gauges.length} จุดวัดใน {provinceCount} จังหวัด ·
                  {gaugeCounts.overflow > 0 ? ` ล้นตลิ่ง ${gaugeCounts.overflow} จุด` : ' ไม่มีจุดที่ล้นตลิ่ง'}
                  {gaugeCounts.high > 0 ? ` · น้ำมาก ${gaugeCounts.high}` : ''}
                </p>
                <div className="flex flex-wrap gap-x-2 gap-y-1 text-[11px] text-slate-600">
                  <span className="inline-flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm" style={{ background: GAUGE_STYLE.overflow.color }} />ล้นตลิ่ง</span>
                  <span className="inline-flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm" style={{ background: GAUGE_STYLE.high.color }} />น้ำมาก</span>
                  <span className="inline-flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm" style={{ background: GAUGE_STYLE.normal.color }} />ปกติ</span>
                </div>
                <p className="text-[11px] text-slate-400 mt-1">บอกว่าน้ำในแม่น้ำหรือคลองเต็มแค่ไหน ไม่ใช่น้ำบนถนน</p>
              </>
            ) : (
              <p className="text-[11px] text-slate-500 mt-1">กำลังโหลด ...</p>
            )}
          </div>
        </LayerGroup>

        <LayerGroup title="อากาศ" hint={air?.avg_pm25 != null ? `ฝุ่น PM2.5 เฉลี่ย ${air.avg_pm25} · ลม` : 'ฝุ่น PM2.5 และลม'} on={(showPm ? 1 : 0) + (showWind ? 1 : 0)}>
          {/* PM2.5 station toggle */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="inline-flex items-center gap-2 text-sm text-ink-900 cursor-pointer font-medium">
                <input type="checkbox" checked={showPm} onChange={(e) => setShowPm(e.target.checked)} className="accent-blue-600 w-4 h-4" />
                <Icon name="mask" /> ฝุ่น PM2.5
              </label>
              {air?.avg_pm25 != null && (
                <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-700">เฉลี่ย {air.avg_pm25}</span>
              )}
            </div>
            <p className="text-[11px] text-slate-500 mb-1.5">
              {air ? `${air.total} จุดวัด · แตะจุดเพื่อดูรายละเอียด` : 'กำลังโหลด ...'}
            </p>
            <div className="flex flex-wrap gap-x-2 gap-y-1 text-[11px] text-slate-600">
              {[['#3BA0FF', 'ดีมาก ≤15'], ['#4CC74A', 'ดี ≤25'], ['#FFD400', 'ปานกลาง ≤37.5'], ['#FF8C00', 'เริ่มมีผลต่อสุขภาพ ≤75'], ['#E3272C', 'มีผลต่อสุขภาพ >75']].map(([c, l]) => (
                <span key={l} className="inline-flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full" style={{ background: c }} />{l}</span>
              ))}
            </div>
          </div>

          {/* Wind overlay toggle (own layer, Open-Meteo) */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="inline-flex items-center gap-2 text-sm text-ink-900 cursor-pointer font-medium">
                <input type="checkbox" checked={showWind} onChange={(e) => setShowWind(e.target.checked)} className="accent-blue-600 w-4 h-4" />
                <Icon name="wind" /> ลม (สด)
              </label>
              {wind?.points?.[24]?.time && <span className="text-[11px] text-slate-500">{wind.points[24].time.slice(11, 16)} น.</span>}
            </div>
            <p className="text-[11px] text-slate-500 mb-1.5">ลูกศรชี้ทางที่ลมพัดไป สีบอกความแรงลม (กม./ชม.)</p>
            <div className="flex flex-wrap gap-x-2 gap-y-1 text-[11px] text-slate-600">
              {[['#60a5fa', '<10 เบา'], ['#22c55e', '10-20'], ['#f59e0b', '20-35 แรง'], ['#ef4444', '>35 พายุ']].map(([c, l]) => (
                <span key={l} className="inline-flex items-center gap-1"><span className="w-3 h-1 rounded-full" style={{ background: c }} />{l}</span>
              ))}
            </div>
          </div>
        </LayerGroup>

        <LayerGroup title="ดาวเทียม NASA" hint="ไฟป่าและการเผา · พายุที่กำลังมา" on={(showFires ? 1 : 0) + (showStorms ? 1 : 0)}>
          {/* FIRMS fire hotspots */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="inline-flex items-center gap-2 text-sm text-ink-900 cursor-pointer font-medium">
                <input type="checkbox" checked={showFires} onChange={(e) => setShowFires(e.target.checked)} className="accent-blue-600 w-4 h-4" />
                จุดไฟจากดาวเทียม
              </label>
              {nasaFires && <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-orange-50 text-orange-700">{nasaFires.th_24h} จุดในไทย</span>}
            </div>
            <p className="text-[11px] text-slate-500 mb-1.5">จุดที่ดาวเทียมเห็นความร้อนผิดปกติใน 24 ชม. เช่น ไฟป่า การเผาในไร่ หรือโรงงาน หนึ่งจุดคือพื้นที่ราว 1 ตร.กม.</p>
            {showFires && (nasaFires ? (
              <>
                <ul className="text-[12px] text-ink-900 flex flex-col gap-1 mb-1.5 list-disc pl-4">
                  {fireNotes.map((t) => <li key={t}>{t}</li>)}
                </ul>
                {nasaFires.provinces?.length > 0 && (
                  <p className="text-[11px] text-slate-600 mb-1.5">จังหวัดที่มีไฟมากที่สุด: {nasaFires.provinces.slice(0, 5).map((p) => `${p.province} ${p.count}`).join(' · ')}</p>
                )}
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-slate-600">
                  {[['#fbbf24', 'ไฟเล็ก'], ['#f97316', 'ปานกลาง'], ['#dc2626', 'ไฟแรง']].map(([c, l]) => (
                    <span key={l} className="inline-flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-full" style={{ background: c }} />{l}</span>
                  ))}
                  <button type="button" onClick={() => mapRef.current?.fitBounds([[97.3, 5.6], [105.7, 20.5]], { padding: 30, duration: 900 })} className="cursor-pointer ml-auto text-blue-700 hover:underline">ดูทั้งประเทศ</button>
                </div>
              </>
            ) : <p className="text-[11px] text-slate-500">กำลังโหลด ... (ครั้งแรกใช้เวลาราว 2 นาที)</p>)}
          </div>

          {/* EONET storms and other natural events */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="inline-flex items-center gap-2 text-sm text-ink-900 cursor-pointer font-medium">
                <input type="checkbox" checked={showStorms} onChange={(e) => setShowStorms(e.target.checked)} className="accent-blue-600 w-4 h-4" />
                พายุและภัยธรรมชาติ
              </label>
              {nasaEvents && <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${nearStorms.length ? 'bg-violet-100 text-violet-800' : 'bg-slate-100 text-slate-700'}`}>{nearStorms.length ? `พายุใกล้ไทย ${nearStorms.length}` : 'ไม่มีพายุใกล้ไทย'}</span>}
            </div>
            <p className="text-[11px] text-slate-500 mb-1.5">พายุหมุนเขตร้อนตั้งแต่อินเดียถึงแปซิฟิก พร้อมเส้นทางที่ผ่านมา (เส้นประ) ระยะห่างจากไทย และกำลังเข้าใกล้หรือออกห่าง</p>
            {showStorms && (nasaEvents ? (
              <>
                <p className="text-[12px] text-ink-900 mb-1.5">
                  {nearStorms.length ? `มีพายุ ${nearStorms.length} ลูกในระยะ ${(nasaEvents.near_km || 1500).toLocaleString()} กม. จากไทย ติดตามประกาศกรมอุตุฯ` : `ไม่มีพายุในระยะ ${(nasaEvents.near_km || 1500).toLocaleString()} กม. จากไทย`}
                </p>
                <ul className="flex flex-col gap-1.5">
                  {(nasaEvents.items || []).slice(0, 6).map((e) => (
                    <li key={e.id} className="text-[12px] flex items-start gap-2">
                      <span className="min-w-0 flex-1"><b className="text-ink-900">{e.kind_th}: {e.title}</b><span className="block text-[11px] text-slate-500">{nasaEventLine(e)}</span></span>
                      <button type="button" onClick={() => flyToNasa(e.lat, e.lng, 4)} className="cursor-pointer shrink-0 text-[11px] text-blue-700 hover:underline">ดูบนแผนที่</button>
                    </li>
                  ))}
                  {!nasaEvents.items?.length && <li className="text-[12px] text-slate-500">ตอนนี้ไม่มีพายุหรือภัยธรรมชาติที่ NASA ติดตามในภูมิภาคนี้</li>}
                </ul>
              </>
            ) : <p className="text-[11px] text-slate-500">กำลังโหลด ...</p>)}
            <p className="text-[10px] text-slate-400 mt-1.5">ข้อมูลจาก NASA FIRMS และ EONET อัปเดตทุกชั่วโมง</p>
          </div>
        </LayerGroup>

        <LayerGroup title="อาคารและสถานที่" hint="อาคาร 3 มิติ และชื่อสถานที่เมื่อซูมเข้าใกล้" on={showPlaces ? 1 : 0}>
          {/* Buildings: 3D is automatic from zoom 15; this only adds footprints and names */}
          <div>
            <p className="text-sm text-ink-900 font-medium inline-flex items-center gap-2"><Icon name="building" /> อาคาร 3 มิติ</p>
            <p className="text-[11px] text-slate-500 mt-1">ซูมเข้าใกล้แล้วอาคารจะขึ้นเป็น 3 มิติเอง · คลิกขวาค้างแล้วลากเพื่อหมุนแผนที่</p>
            <label className="mt-2 inline-flex items-center gap-2 text-sm text-ink-900 cursor-pointer font-medium">
              <input type="checkbox" checked={showPlaces} onChange={(e) => setShowPlaces(e.target.checked)} className="accent-blue-600 w-4 h-4" />
              <Icon name="pin" /> ชื่อสถานที่และผังอาคาร
            </label>
            <p className="text-[11px] text-slate-500 mt-1">ซูมเข้าใกล้เพื่อดูชื่อโรงพยาบาล โรงเรียน ห้าง วัด ฯลฯ · กดอาคารเพื่อดูชื่อและความสูง</p>
          </div>
        </LayerGroup>

        {incidentList.length > 0 && (
          <div className="rounded-lg bg-red-50 border border-red-200 p-3">
            <p className="text-xs font-semibold text-red-700 mb-1.5">อุบัติเหตุและรถเสียตอนนี้ ({incidentList.length})</p>
            <div className="max-h-36 overflow-y-auto scroll-soft flex flex-col gap-1">
              {incidentList.map((i) => (
                <button key={i.id} type="button" onClick={() => flyToIncident(i)} className="cursor-pointer text-left rounded-lg px-2.5 py-1.5 text-sm text-ink-900 hover:bg-white transition-colors duration-200">
                  <span className="line-clamp-1">{i.title}</span>
                  <span className="block text-[11px] text-ink-600">{KIND_TH[i.kind] || 'เหตุบนถนน'} · {placeTh(i) || sourceTh(i)}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {closures.length > 0 && (
          <div className="rounded-lg bg-orange-50 border border-orange-200 p-3">
            <div className="flex items-center justify-between gap-2 mb-1.5">
              <p className="text-xs font-semibold text-orange-800">ถนนปิดตอนนี้ ({closures.length})</p>
              <button type="button" onClick={showThailand} className="cursor-pointer text-[11px] font-medium text-blue-700 hover:underline">ดูทั้งประเทศ</button>
            </div>
            <div className="max-h-48 overflow-y-auto scroll-soft flex flex-col gap-1">
              {[...closures].sort((a, b) => (a.province || 'ฮ').localeCompare(b.province || 'ฮ', 'th')).map((c) => (
                <button key={c.id} type="button" onClick={() => flyToClosure(c)} className="cursor-pointer text-left rounded-lg px-2.5 py-1.5 text-sm text-ink-900 hover:bg-white transition-colors duration-200">
                  <span className="line-clamp-1">{c.title}</span>
                  <span className="block text-[11px] text-ink-600">{closureTh(c)}{placeTh(c) ? ` · ${placeTh(c)}` : ''}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="flex-1 min-h-40 flex flex-col">
          <p className="text-xs text-ink-600 mb-2">กล้องที่เปิดอยู่ ({activeCams.length})</p>
          {activeCams.length === 0 ? (
            <p className="text-sm text-ink-400">ยังไม่ได้เปิดกล้อง กดหมุดกล้องบนแผนที่ได้เลย</p>
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

      <section aria-label="แผนที่จราจร" className="order-1 lg:order-2 glass rounded-xl overflow-hidden min-h-[560px] relative">
        <div ref={mapEl} className="w-full h-full min-h-[540px]" />
        <button
          type="button"
          onClick={() => setPanelOpen(true)}
          aria-expanded={panelOpen}
          aria-controls="map-options"
          className="lg:hidden absolute left-3 bottom-8 z-10 inline-flex items-center gap-2 h-11 px-4 rounded-full bg-white border border-slate-300 text-sm font-semibold text-slate-900 shadow-lg cursor-pointer"
        >
          <Icon name="legend" /> ตัวเลือกแผนที่
          {optionsOn > 0 && <span className="rounded-full bg-blue-600 text-white text-[11px] px-2 py-0.5 tabular-nums">เปิด {optionsOn}</span>}
        </button>
      </section>
    </div>
    </div>
  );
}
