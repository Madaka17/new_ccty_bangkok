import { useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { motion } from 'framer-motion';
import { MapPinIcon, LocateIcon, RefreshIcon } from './Icons.jsx';
import { fetchTrafficSummary } from '../lib/api.js';

// Vite bundles maplibre into one chunk, so its worker module must be served separately (see public/assets/)
maplibregl.setWorkerUrl(`${window.location.origin}/assets/maplibre-gl-worker.mjs`);

// One pin colour: province is a filter, not a status
const PIN = '#2563eb';
const PIN_COLOR = { กรุงเทพมหานคร: PIN, นนทบุรี: PIN, นครปฐม: PIN, สมุทรปราการ: PIN, ปทุมธานี: PIN };
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

function pinEl(color, active) {
 const el = document.createElement('button');
 el.type = 'button';
 el.className = 'cursor-pointer';
 el.style.cssText = `width:20px;height:20px;border-radius:999px;background:${color};border:3px solid #fff;box-shadow:0 1px 4px rgba(15,23,42,.3);${active ? 'outline:3px solid #0f172a;outline-offset:1px;' : ''}`;
 return el;
}

export default function MapPage({ isActive, cameras, active, incidents, onToggle, onOpenAI, onToast }) {
 const mapEl = useRef(null);
 const mapRef = useRef(null);
 const markersRef = useRef({});
 const incidentMarkersRef = useRef([]);
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
 const el = pinEl(PIN_COLOR[c.province] || PIN, on);
 el.setAttribute('aria-label', c.short_title || c.title);
 const popup = new maplibregl.Popup({ offset: 14, closeButton: true, maxWidth: '300px', anchor: 'bottom' }).setHTML(
          `<div style="width:260px">
            <div style="position:relative;border-radius:8px;overflow:hidden;background:#e2e8f0;aspect-ratio:16/9;margin-bottom:8px">
              <img data-live="${c.camid}" alt="" style="display:block;width:100%;height:100%;object-fit:cover" />
              <span data-status="${c.camid}" style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:12px;color:#475569;background:#f8fafc">กำลังเปิดภาพ...</span>
            </div>
            <p style="margin:0 0 8px;font-weight:500;color:#0f172a;font-size:13px;line-height:1.35">${c.short_title || c.title}</p>
            <div style="display:flex;gap:6px;flex-wrap:wrap">
              <button data-act="toggle" data-camid="${c.camid}" style="cursor:pointer;border:0;border-radius:8px;padding:6px 12px;background:${on ? '#fee2e2' : '#2563eb'};color:${on ? '#b91c1c' : '#fff'};font-size:12px;font-family:inherit">${on ? 'ปิดกล้องนี้' : 'เปิดดูกล้องนี้'}</button>
              <button data-act="ai" data-camid="${c.camid}" style="cursor:pointer;border:0;border-radius:8px;padding:6px 12px;background:#f1f5f9;color:#0f172a;border:1px solid #cbd5e1;font-size:12px;font-family:inherit">ถามผู้ช่วย AI</button>
            </div>
          </div>`
        );
        // Live MJPEG preview inside the popup (every camera has vdourl; HLS via MSE does not start inside popups)
 popup.on('open', () => {
 map.easeTo({ center: [c.longitude, c.latitude], offset: [0, 130], duration: 400 });
 const root = popup.getElement();
 const img = root?.querySelector(`img[data-live="${c.camid}"]`);
 const status = root?.querySelector(`span[data-status="${c.camid}"]`);
 if (!img) return;
 const src = c.vdourl || c.imgurl;
 if (!src) {
 if (status) status.textContent = 'กล้องนี้ไม่มีภาพสด';
 return;
          }
 img.onload = () => status && (status.style.display = 'none');
 img.onerror = () => status && (status.textContent = 'กล้องขอพักสักครู่');
 img.src = `${src}${src.includes('?') ? '&' : '?'}t=${Date.now()}`;
        });
 popup.on('close', () => {
          // drop the src so the MJPEG connection closes
 popup.getElement()?.querySelectorAll('img[data-live]').forEach((img) => (img.src = ''));
        });
 const m = new maplibregl.Marker({ element: el }).setLngLat([c.longitude, c.latitude]).setPopup(popup).addTo(map);
 markersRef.current[c.camid] = m;
      });
  }, [cameras, active, provinceFilter, isActive]);

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

 const activeCams = active.map((id) => cameras.find((c) => c.camid === id)).filter(Boolean);
 const updated = summary?.updated_at ? new Date(summary.updated_at * 1000).toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' }) : null;

 return (
    <div className="grid grid-cols-1 lg:grid-cols-[300px_1fr] gap-4 lg:h-[calc(100vh-11rem)] min-h-[520px]">
      <aside className="glass rounded-xl p-5 flex flex-col gap-4 overflow-hidden">
        <div>
          <h2 className="font-serif text-xl font-semibold text-ink-900">แผนที่จราจร</h2>
          <p className="text-sm text-ink-600">เส้นสีบอกการระบายรถแบบสด แผนที่เก็บไว้ในเครื่อง ดูได้แม้เน็ตหลุด</p>
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
 className="cursor-pointer inline-flex items-center justify-center gap-2 rounded-lg bg-white text-slate-800 border border-slate-300 px-4 py-2.5 text-sm font-medium hover:bg-slate-50 transition-colors duration-200"
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
 className={`cursor-pointer rounded-lg px-3 py-1.5 text-xs font-medium border transition-colors duration-200 ${
 provinceFilter === 'all' ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-slate-700 border-slate-300 hover:bg-slate-50'
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
 className="cursor-pointer inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium border transition-colors duration-200"
 style={provinceFilter === p ? { background: PIN, borderColor: PIN, color: '#fff' } : { background: '#fff', borderColor: '#cbd5e1', color: '#334155' }}
              >
                                {p}
              </button>
            ))}
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
          <p className="text-xs text-ink-600 mb-2 flex items-center gap-1.5">
            <MapPinIcon className="w-4 h-4" />
            กล้องที่เปิดอยู่ ({activeCams.length})
          </p>
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
