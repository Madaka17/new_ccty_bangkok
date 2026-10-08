// NASA satellite layers on the traffic map ("ดาวเทียม NASA" in the side panel): FIRMS fire hotspots and EONET storms /
// natural events (nasa_feeds.py). useNasaLayers reads and draws them; NasaPanel is their part of the side panel.
import { useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import { fetchNasaEvents, fetchNasaFires } from '../../lib/api.js';
import { LayerGroup } from './LayerGroup.jsx';
import { nasaEventLine } from './nasaText.js';

export function useNasaLayers(mapRef, isActive) {
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
  return { showFires, setShowFires, showStorms, setShowStorms, nasaFires, nasaEvents };
}

export function NasaPanel({ layers, mapRef }) {
  const { showFires, setShowFires, showStorms, setShowStorms, nasaFires, nasaEvents } = layers;
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
  return (
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
  );
}
