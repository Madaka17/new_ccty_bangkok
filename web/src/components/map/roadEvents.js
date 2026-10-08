// Road events on the traffic map in every province: accidents and breakdowns (camera-confirmed and reported),
// closed roads and flooded places, with the side panel's "fly to" for an incident or a closure.
import { useEffect, useMemo, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import { fetchRoadEvents, fetchNationalFloods } from '../../lib/api.js';
import { KIND_TH, CLOSURE_COLOR, closureTh, sourceTh, placeTh, feedTimeTh, NATION_FLOOD_COLOR, nationFloodEl, agoTh, esc, closureEl, incidentEl } from './markers.js';

export function useRoadEvents(mapRef, isActive, incidents, pinsOn, setPinsOn) {
  const incidentMarkersRef = useRef([]);
  const incidentByIdRef = useRef({});
  const closureMarkersRef = useRef([]);
  const nationFloodMarkersRef = useRef([]);
  const [nationFloods, setNationFloods] = useState(null);
  const closureByIdRef = useRef({});
  // Accidents and closed roads in every province (/api/road/events); null until loaded
  const [roadEvents, setRoadEvents] = useState(null);

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

  const flyToIncident = (i) => {
    const map = mapRef.current;
    if (!map || !i.latitude) return;
    map.flyTo({ center: [i.longitude, i.latitude], zoom: 15, duration: 800 });
    // a kind switched off in the legend comes back on, so the picked incident has a pin to open
    const kind = i.kind === 'breakdown' ? 'breakdown' : 'accident';
    if (!pinsOn[kind]) setPinsOn((p) => ({ ...p, [kind]: true }));
    setTimeout(() => incidentByIdRef.current[i.id]?.togglePopup(), 850);
  };
  return { incidentList, closures, flyToClosure, flyToIncident, nationFloods };
}
