import { useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { motion } from 'framer-motion';
import { MapPinIcon, LocateIcon, RefreshIcon } from './Icons.jsx';
import { fetchTrafficSummary } from '../lib/api.js';

// Vite bundles maplibre into one chunk, so its worker module must be served separately (see public/assets/)
maplibregl.setWorkerUrl(`${window.location.origin}/assets/maplibre-gl-worker.mjs`);

const PIN_COLOR = { กรุงเทพมหานคร: '#9dbf92', นนทบุรี: '#b5a3de', นครปฐม: '#f5a88c', สมุทรปราการ: '#edc55c', ปทุมธานี: '#c9c3cc' };
const PROVINCES = Object.keys(PIN_COLOR);

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

function pinEl(color, active) {
  const el = document.createElement('button');
  el.type = 'button';
  el.className = 'cursor-pointer';
  el.style.cssText = `width:20px;height:20px;border-radius:999px;background:${color};border:3px solid #fff;box-shadow:0 2px 8px rgba(46,42,51,.28);${active ? 'outline:3px solid #6b559f;outline-offset:1px;' : ''}`;
  return el;
}

export default function MapPage({ isActive, cameras, active, onToggle, onOpenAI, onToast }) {
  const mapEl = useRef(null);
  const mapRef = useRef(null);
  const markersRef = useRef({});
  const [provinceFilter, setProvinceFilter] = useState('all');
  const [showTraffic, setShowTraffic] = useState(true);
  const [summary, setSummary] = useState(null);

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
    }, 120000);
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

  // Sync camera markers
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    Object.values(markersRef.current).forEach((m) => m.remove());
    markersRef.current = {};

    cameras
      .filter((c) => c.latitude && c.longitude)
      .filter((c) => provinceFilter === 'all' || c.province === provinceFilter)
      .forEach((c) => {
        const on = active.includes(c.camid);
        const el = pinEl(PIN_COLOR[c.province] || '#c9c3cc', on);
        el.setAttribute('aria-label', c.short_title || c.title);
        const popup = new maplibregl.Popup({ offset: 14, closeButton: true, maxWidth: '260px' }).setHTML(
          `<div style="min-width:200px">
            <p style="margin:0 0 8px;font-weight:500;color:#2e2a33;font-size:13px;line-height:1.35">${c.short_title || c.title}</p>
            <div style="display:flex;gap:6px;flex-wrap:wrap">
              <button data-act="toggle" data-camid="${c.camid}" style="cursor:pointer;border:0;border-radius:999px;padding:6px 14px;background:${on ? '#fde6dd' : '#e3eedd'};color:${on ? '#b85f41' : '#557a4b'};font-size:12px;font-family:inherit">${on ? 'ปิดกล้องนี้' : 'เปิดดูกล้องนี้'}</button>
              <button data-act="ai" data-camid="${c.camid}" style="cursor:pointer;border:0;border-radius:999px;padding:6px 14px;background:#fbefd3;color:#a07e2b;font-size:12px;font-family:inherit">ถามผู้ช่วย AI</button>
            </div>
          </div>`
        );
        const m = new maplibregl.Marker({ element: el }).setLngLat([c.longitude, c.latitude]).setPopup(popup).addTo(map);
        markersRef.current[c.camid] = m;
      });
  }, [cameras, active, provinceFilter, isActive]);

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

  const activeCams = active.map((id) => cameras.find((c) => c.camid === id)).filter(Boolean);
  const updated = summary?.updated_at ? new Date(summary.updated_at * 1000).toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' }) : null;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[300px_1fr] gap-4 lg:h-[calc(100vh-11rem)] min-h-[520px]">
      <aside className="glass rounded-[2rem] p-5 flex flex-col gap-4 overflow-hidden">
        <div>
          <h2 className="font-serif text-xl font-semibold text-ink-900">แผนที่จราจร</h2>
          <p className="text-sm text-ink-600">เส้นสีบอกการระบายรถแบบสด แผนที่เก็บไว้ในเครื่อง ดูได้แม้เน็ตหลุด</p>
        </div>

        {/* Traffic legend + status */}
        <div className="rounded-3xl bg-white/70 border border-cream-200 p-3">
          <div className="flex items-center justify-between mb-2">
            <label className="inline-flex items-center gap-2 text-sm text-ink-900 cursor-pointer">
              <input type="checkbox" checked={showTraffic} onChange={(e) => setShowTraffic(e.target.checked)} className="accent-lavender-600 w-4 h-4" />
              เส้นจราจร
            </label>
            {summary && (
              <span className={`inline-flex items-center gap-1 text-[11px] rounded-full px-2 py-0.5 ${summary.online ? 'bg-sage-50 text-sage-700' : 'bg-gold-50 text-gold-700'}`}>
                <RefreshIcon className="w-3 h-3" />
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
              ทั้งเมืองระบายได้ <span className="font-serif text-base text-ink-900">{summary.flow_index}</span>/100 · แดง {summary.red_pct}%
            </p>
          )}
        </div>

        <motion.button
          type="button"
          whileTap={{ scale: 0.96 }}
          onClick={locateMe}
          className="cursor-pointer inline-flex items-center justify-center gap-2 rounded-full bg-lavender-100 text-lavender-700 border border-lavender-200 px-4 py-2.5 text-sm font-medium hover:bg-lavender-200 transition-colors duration-200"
        >
          <LocateIcon />
          ไปที่ตำแหน่งของฉัน
        </motion.button>

        <div>
          <p className="text-xs text-ink-600 mb-2">กล้องตามจังหวัด</p>
          <div className="flex flex-wrap gap-1.5">
            <button
              type="button"
              onClick={() => setProvinceFilter('all')}
              aria-pressed={provinceFilter === 'all'}
              className={`cursor-pointer rounded-full px-3 py-1.5 text-xs font-medium border transition-colors duration-200 ${
                provinceFilter === 'all' ? 'bg-ink-900 text-white border-ink-900' : 'bg-white/80 text-ink-600 border-cream-200 hover:bg-cream-100'
              }`}
            >
              ทั้งหมด
            </button>
            {PROVINCES.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setProvinceFilter(p)}
                aria-pressed={provinceFilter === p}
                className="cursor-pointer inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium border transition-colors duration-200"
                style={provinceFilter === p ? { background: PIN_COLOR[p], borderColor: PIN_COLOR[p], color: '#2e2a33' } : { background: 'rgba(255,255,255,.8)', borderColor: '#efeae4', color: '#6b6572' }}
              >
                <span className="w-2.5 h-2.5 rounded-full border border-white" style={{ background: PIN_COLOR[p] }} />
                {p}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 min-h-0 flex flex-col">
          <p className="text-xs text-ink-600 mb-2 flex items-center gap-1.5">
            <MapPinIcon className="w-4 h-4" />
            กล้องที่เปิดอยู่ ({activeCams.length})
          </p>
          {activeCams.length === 0 ? (
            <p className="text-sm text-ink-400">ยังไม่มีกล้องที่เปิด จิ้มหมุดบนแผนที่ได้เลย</p>
          ) : (
            <div className="flex-1 overflow-y-auto scroll-soft flex flex-col gap-1.5">
              {activeCams.map((c) => (
                <button key={c.camid} type="button" onClick={() => flyToCam(c)} className="cursor-pointer text-left rounded-2xl px-3 py-2 text-sm text-ink-900 hover:bg-sage-50 transition-colors duration-200 flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: PIN_COLOR[c.province] || '#c9c3cc' }} />
                  <span className="line-clamp-1">{c.short_title}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </aside>

      <section aria-label="แผนที่จราจร" className="glass rounded-[2rem] p-3 min-h-[420px]">
        <div ref={mapEl} className="w-full h-full min-h-[400px] rounded-[1.5rem] overflow-hidden" />
      </section>
    </div>
  );
}
