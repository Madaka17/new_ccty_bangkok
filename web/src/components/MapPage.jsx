import { useEffect, useMemo, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { motion } from 'framer-motion';
import Hls from 'hls.js';
import { fetchTrafficSummary, fetchLongdoCameras, fetchWaterSummary } from '../lib/api.js';
import { enrichCamerasWithFloodRisk } from '../lib/floodRisk.js';

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
    },
    layers: [
      { id: 'base', type: 'raster', source: 'base', paint: { 'raster-saturation': -0.45, 'raster-brightness-min': 0.05, 'raster-contrast': -0.08 } },
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
    ],
  };
}

const KIND_TH = { accident: 'อุบัติเหตุ', breakdown: 'รถเสีย / จอดกีดขวาง' };
const agoTh = (ts) => {
  const m = Math.round((Date.now() / 1000 - ts) / 60);
  return m < 1 ? 'เมื่อสักครู่' : m < 60 ? `${m} นาทีก่อน` : `${Math.round(m / 60)} ชม.ก่อน`;
};
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
  const [summary, setSummary] = useState(null);
  const [waterSummary, setWaterSummary] = useState(null);
  const [showRainRadar, setShowRainRadar] = useState(true);
  const [radarOpacity, setRadarOpacity] = useState(0.65);
  const [radarTileUrl, setRadarTileUrl] = useState(null);
  const [radarTime, setRadarTime] = useState(null);

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
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
    mapRef.current = map;
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
    <div className="grid grid-cols-1 lg:grid-cols-[300px_1fr] gap-4 lg:h-[calc(100vh-11rem)] min-h-[520px]">
      <aside className="glass rounded-xl p-5 flex flex-col gap-4 overflow-hidden">
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
                🌧️ ซ้อนเรดาร์ฝน (สด)
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

        <motion.button
          type="button"
          whileTap={{ scale: 0.96 }}
          onClick={locateMe}
          className="cursor-pointer inline-flex items-center justify-center gap-2 rounded-xl bg-white text-ink-900 border border-cream-200 px-4 py-2.5 text-sm font-medium hover:bg-cream-100 transition-colors duration-200"
        >
          📍 ไปที่ตำแหน่งของฉัน
        </motion.button>

        {/* คำอธิบายสัญลักษณ์และไอคอนบนแผนที่ (Map Legend) */}
        <div className="rounded-xl bg-white border border-cream-200 p-3 flex flex-col gap-2.5">
          <div className="flex items-center justify-between pb-2 border-b border-cream-200">
            <p className="text-xs font-semibold text-ink-900 flex items-center gap-1.5">
              <span>📍</span> สัญลักษณ์บนแผนที่
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
              <span className="text-base leading-none shrink-0 w-5 text-center">🌧️</span>
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

        <div className="flex-1 min-h-0 flex flex-col">
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

      <section aria-label="แผนที่จราจร" className="glass rounded-xl overflow-hidden min-h-[560px]">
        <div ref={mapEl} className="w-full h-full min-h-[540px]" />
      </section>
    </div>
  );
}
