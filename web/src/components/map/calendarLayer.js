// Calendar pins on the map: team events and the coming road closures and big events that have coordinates
// (the whole country, scope 'all'). Off by default; the toggle is "งานใหญ่ ปิดถนนล่วงหน้า".
import { useEffect, useMemo, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import { fetchCalendar } from '../../lib/api.js';
import { kindLabel, sourceLabel, timeRange, mapItemsWithCoords } from '../../lib/events.js';
import { esc } from './markers.js';

const POLL_MS = 60000;
const CAL_COLOR = { closure: '#b91c1c', diversion: '#ea580c', event: '#2563eb', run: '#0f766e', concert: '#7c3aed', ceremony: '#7c3aed' };

// A rounded square with a white dot, coloured by kind (the closure pins are circles, diversions squares)
function calendarEl(item) {
  const el = document.createElement('button');
  el.type = 'button';
  el.className = 'cursor-pointer';
  el.setAttribute('aria-label', `${kindLabel(item.kind)} ${item.title}`);
  const color = CAL_COLOR[item.kind] || '#334155';
  el.style.cssText = `width:22px;height:22px;border-radius:6px;background:${color};border:2px solid #fff;box-shadow:0 1px 4px rgba(15,23,42,.35);display:flex;align-items:center;justify-content:center;padding:0`;
  const dot = document.createElement('span');
  dot.style.cssText = 'display:block;width:6px;height:6px;border-radius:999px;background:#fff';
  el.appendChild(dot);
  return el;
}

export function useCalendarLayer(mapRef, isActive, on) {
  const [items, setItems] = useState(null);
  const markersRef = useRef([]);

  useEffect(() => {
    if (!isActive || !on) return undefined;
    const load = () => {
      fetchCalendar('all')
        .then((c) => setItems(mapItemsWithCoords(c)))
        .catch(() => {});
    };
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [isActive, on]);

  useEffect(() => {
    const map = mapRef.current;
    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];
    if (!map || !on || !items) return;
    items.forEach((i) => {
      const html = `<div style="width:260px">
          <p style="margin:0 0 4px;font-weight:600;color:${CAL_COLOR[i.kind] || '#334155'};font-size:13px">${esc(kindLabel(i.kind))}</p>
          <p style="margin:0 0 4px;color:#0f172a;font-size:13px;line-height:1.35">${esc(i.title)}</p>
          ${i.place || i.district ? `<p style="margin:0 0 6px;color:#475569;font-size:12px">${esc([i.place, i.district ? `เขต${i.district}` : ''].filter(Boolean).join(' · '))}</p>` : ''}
          ${i.detail ? `<p style="margin:0 0 6px;color:#475569;font-size:12px;line-height:1.4">${esc(i.detail)}</p>` : ''}
          <p style="margin:0;color:#334155;font-size:12px">${esc(timeRange(i.start, i.end))}</p>
          <p style="margin:4px 0 0;color:#94a3b8;font-size:11px">${esc(sourceLabel(i.source))}${i.url && /^https?:\/\//.test(i.url) ? ` · <a href="${esc(i.url)}" target="_blank" rel="noreferrer">ดูประกาศ</a>` : ''}</p>
        </div>`;
      const popup = new maplibregl.Popup({ offset: 16, closeButton: true, maxWidth: '300px', anchor: 'bottom' }).setHTML(html);
      markersRef.current.push(new maplibregl.Marker({ element: calendarEl(i) }).setLngLat([i.lng, i.lat]).setPopup(popup).addTo(map));
    });
  }, [items, isActive, on, mapRef]);

  return useMemo(() => ({ calendarCount: on && items ? items.length : null }), [on, items]);
}
