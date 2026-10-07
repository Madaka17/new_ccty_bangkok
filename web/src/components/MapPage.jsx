import { useEffect, useMemo, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import Hls from 'hls.js';
import { fetchTrafficSummary, fetchLongdoCameras, fetchWaterSummary, fetchFloodStatus, fetchFloodStations, fetchFloodReports, fetchHdmsFloods, fetchFloodCameras, fetchUserReports, fetchRoadEvents, fetchNationalFloods } from '../lib/api.js';
import { enrichCamerasWithFloodRisk } from '../lib/floodRisk.js';
import { fmtTime } from './dashboard/format.js';
import { accuracyText, roughWarning, showAccuracy, frameFix } from '../lib/geo.js';
import { Icon } from './dashboard/icons.jsx';
import { Button } from './dashboard/ui.jsx';
import { PageHeader } from './dashboard/primitives.jsx';
import { PAGE_TITLES } from './Sidebar.jsx';
import { mapStyle } from './map/mapStyle.js';
import { POI_MAX, POI_MIN_ZOOM, POI_TIER_MAX, poiKindOf, poiTierOf } from './map/places.js';
import { PIN, PIN_COLOR, FLOOD_STYLE, GAUGE_STYLE, CAM_FLOOD_STYLE, CAM_WET, USER_REPORT_COLOR, REPORT_COLOR, REPORT_FRESH_S, HDMS_COLOR, KIND_TH, CLOSURE_COLOR, closureTh, sourceTh, placeTh, feedTimeTh, THAILAND, NATION_FLOOD_COLOR, nationFloodEl, METRO_PROVINCES, agoTh, esc, closureEl, incidentEl, pinEl } from './map/markers.js';
import { LayerGroup } from './map/LayerGroup.jsx';
import { AirPanel, useAirLayers } from './map/AirLayers.jsx';
import { NasaPanel, useNasaLayers } from './map/NasaLayers.jsx';

// Vite bundles maplibre into one chunk, so its worker module must be served separately (see public/assets/)
maplibregl.setWorkerUrl(`${window.location.origin}/assets/maplibre-gl-worker.mjs`);

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
  // PM2.5 and wind (map/AirLayers.jsx)
  const airLayers = useAirLayers(mapRef, isActive);
  const { showPm, showWind } = airLayers;

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


  const nasa = useNasaLayers(mapRef, isActive);
  const { showFires, showStorms } = nasa;

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

        <AirPanel layers={airLayers} />

        <NasaPanel layers={nasa} mapRef={mapRef} />

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
