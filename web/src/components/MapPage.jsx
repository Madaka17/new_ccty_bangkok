import { useEffect, useMemo, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { fetchTrafficSummary, fetchLongdoCameras, fetchWaterSummary } from '../lib/api.js';
import { enrichCamerasWithFloodRisk } from '../lib/floodRisk.js';
import { fmtTime } from './dashboard/format.js';
import { accuracyText, roughWarning, showAccuracy, frameFix } from '../lib/geo.js';
import { Icon } from './dashboard/icons.jsx';
import { Button } from './dashboard/ui.jsx';
import { PageHeader } from './dashboard/primitives.jsx';
import { PAGE_TITLES } from './Sidebar.jsx';
import { mapStyle } from './map/mapStyle.js';
import { PIN, PIN_COLOR, FLOOD_STYLE, GAUGE_STYLE, CAM_FLOOD_STYLE, CAM_WET, REPORT_COLOR, HDMS_COLOR, KIND_TH, CLOSURE_COLOR, closureTh, sourceTh, placeTh, THAILAND, NATION_FLOOD_COLOR, METRO_PROVINCES, esc } from './map/markers.js';
import { LayerGroup } from './map/LayerGroup.jsx';
import { AirPanel, useAirLayers } from './map/AirLayers.jsx';
import { NasaPanel, useNasaLayers } from './map/NasaLayers.jsx';
import { usePlaceLabels } from './map/placeLabels.js';
import { useRoadFloodLayer, useCamFloodLayer, useUserReportLayer, useTraffyReportLayer, useHdmsLayer, useGaugeLayer } from './map/waterLayers.js';
import { useRainRadar } from './map/rainRadar.js';
import { useRoadEvents } from './map/roadEvents.js';
import { cameraMarker } from './map/cameraPin.js';

// Vite bundles maplibre into one chunk, so its worker module must be served separately (see public/assets/)
maplibregl.setWorkerUrl(`${window.location.origin}/assets/maplibre-gl-worker.mjs`);

export default function MapPage({ isActive, cameras, active, incidents, onToggle, onOpenAI, onToast }) {
  const mapEl = useRef(null);
  const mapRef = useRef(null);
  const markersRef = useRef({});
  const [longdoCameras, setLongdoCameras] = useState([]);
  const [showTraffic, setShowTraffic] = useState(true);
  const [showRail, setShowRail] = useState(false);
  const [summary, setSummary] = useState(null);
  const [waterSummary, setWaterSummary] = useState(null);
  // Map legend check boxes: which pin kinds are drawn (the rain radar box is showRainRadar)
  // cctv draws every camera; floodcam marks the flood-watch ones (and draws just those when cctv is off)
  const [pinsOn, setPinsOn] = useState({ cctv: true, floodcam: false, accident: true, breakdown: false, closure: true, flood: true });
  const togglePins = (k) => setPinsOn((p) => ({ ...p, [k]: !p[k] }));
  const meMarkerRef = useRef(null);   // "ไปที่ตำแหน่งของฉัน": one dot, moved on every click
  // Phones: the options panel is a sheet over the map, opened from a button on it (desktop keeps it at the side)
  const [panelOpen, setPanelOpen] = useState(false);
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

  const { showPlaces, setShowPlaces } = usePlaceLabels(mapRef);

  const { floodCounts, floodTop, showFlood, setShowFlood, floodDry, setFloodDry, flood } = useRoadFloodLayer(mapRef, isActive);
  const { showCamFlood, setShowCamFlood, camFloodDry, setCamFloodDry, camFlood } = useCamFloodLayer(mapRef, isActive);
  const { showUserReports, setShowUserReports, userReports } = useUserReportLayer(mapRef, isActive);
  const { reportPoints, reportFresh, reportDistricts, showReports, setShowReports, reports, reportsFailed } = useTraffyReportLayer(mapRef, isActive);
  const { hdmsPoints, hdmsActive, hdmsAreas, showHdms, setShowHdms, hdms } = useHdmsLayer(mapRef, isActive);
  const { gauges, gaugeCounts, provinceCount, showGauges, setShowGauges } = useGaugeLayer(mapRef, waterSummary);

  const nasa = useNasaLayers(mapRef, isActive);
  const { showFires, showStorms } = nasa;

  const { showRainRadar, setShowRainRadar, radarOpacity, setRadarOpacity, radarTime } = useRainRadar(mapRef, isActive);

  // Sync camera markers
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    Object.values(markersRef.current).forEach((m) => m.remove());
    markersRef.current = {};

    currentCameras
      .filter((c) => c.latitude && c.longitude && (pinsOn.cctv || (pinsOn.floodcam && c.floodRisk)))
      .forEach((c) => {
        markersRef.current[c.camid] = cameraMarker(map, c, active.includes(c.camid), pinsOn.floodcam);
      });
  }, [currentCameras, active, isActive, pinsOn.cctv, pinsOn.floodcam]);

  const { incidentList, closures, flyToClosure, flyToIncident, nationFloods } = useRoadEvents(mapRef, isActive, incidents, pinsOn, setPinsOn);
  const showThailand = () => mapRef.current?.fitBounds(THAILAND, { padding: 30, duration: 800 });

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
