// Air on the traffic map ("อากาศ" in the side panel): PM2.5 stations (Air4Thai, every 10 min) and our wind arrows
// (Open-Meteo grid, every 15 min). useAirLayers draws them; AirPanel is their part of the side panel.
import { useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import { fetchAirStations, fetchWindGrid } from '../../lib/api.js';
import { Icon } from '../dashboard/icons.jsx';
import { LayerGroup } from './LayerGroup.jsx';

export function useAirLayers(mapRef, isActive) {
  const [showPm, setShowPm] = useState(false);
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
  return { air, showPm, setShowPm, wind, showWind, setShowWind };
}

export function AirPanel({ layers }) {
  const { air, showPm, setShowPm, wind, showWind, setShowWind } = layers;
  return (
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
  );
}
