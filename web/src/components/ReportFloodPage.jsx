// แจ้งน้ำท่วม (#/report): a page of its own for a flood report from the public. A map to place the pin (tap it,
// drag the pin, or the "ตำแหน่งของฉัน" button on the map), the form beside it on a wide screen and under it on a
// phone. Reports already sent in the last hours show as small dots, so a spot is not reported twice.
// Opened from the nav's แจ้งน้ำท่วม button and the flood map's "แจ้งจุดน้ำท่วม"; the reports show on the maps.
import { useCallback, useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { fetchUserReports } from '../lib/api.js';
import { Card, Button, FOCUS } from './dashboard/ui.jsx';
import { PageHeader } from './dashboard/primitives.jsx';
import { baseStyle } from './water/WaterMap.jsx';
import ReportFloodForm from './water/ReportFloodForm.jsx';

const PIN_COLOR = '#0891b2';
const GEO_ERROR = {
  1: 'เบราว์เซอร์ไม่ได้ให้สิทธิ์ตำแหน่ง เปิดสิทธิ์ในการตั้งค่า หรือแตะแผนที่เพื่อปักหมุดแทน',
  2: 'หาตำแหน่งไม่ได้ตอนนี้ แตะแผนที่เพื่อปักหมุดแทน',
  3: 'หาตำแหน่งนานเกินไป ลองอีกครั้ง หรือแตะแผนที่เพื่อปักหมุดแทน',
};

export default function ReportFloodPage({ isActive, onNavigate }) {
  const [pin, setPin] = useState(null);
  const [locating, setLocating] = useState(false);
  const [geoError, setGeoError] = useState('');
  const [sent, setSent] = useState(null);      // the server's answer (+ the photo) once a report went through
  const [formKey, setFormKey] = useState(0);   // a fresh form for "แจ้งอีกจุด"
  const mapEl = useRef(null);
  const mapRef = useRef(null);
  const markerRef = useRef(null);
  const sideRef = useRef(null);

  const loadReports = useCallback(() => {
    fetchUserReports()
      .then((d) => {
        const src = mapRef.current?.getSource('reports');
        src?.setData({
          type: 'FeatureCollection',
          features: (d.items || []).map((u) => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [u.lng, u.lat] }, properties: {} })),
        });
      })
      .catch(() => {});
  }, []);

  const locate = useCallback(() => {
    if (!navigator.geolocation) {
      setGeoError('เบราว์เซอร์นี้หาตำแหน่งไม่ได้ แตะแผนที่เพื่อปักหมุดแทน');
      return;
    }
    setLocating(true);
    setGeoError('');
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const p = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        setPin(p);
        mapRef.current?.easeTo({ center: [p.lng, p.lat], zoom: 16, duration: 800 });
        setLocating(false);
      },
      (err) => {
        setGeoError(GEO_ERROR[err.code] || GEO_ERROR[2]);
        setLocating(false);
      },
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 30000 },
    );
  }, []);

  // Map: created once; a tap places the pin, reports already sent are faint dots
  useEffect(() => {
    if (!mapEl.current || mapRef.current) return undefined;
    const map = new maplibregl.Map({ container: mapEl.current, style: baseStyle(), center: [100.55, 13.76], zoom: 11, attributionControl: { compact: true } });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-left');
    map.getCanvas().style.cursor = 'crosshair';
    map.on('load', () => {
      map.addSource('reports', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
      map.addLayer({
        id: 'reports', type: 'circle', source: 'reports',
        paint: { 'circle-radius': 6, 'circle-color': PIN_COLOR, 'circle-opacity': 0.45, 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 1.5 },
      });
      loadReports();
    });
    map.on('click', (e) => setPin({ lat: e.lngLat.lat, lng: e.lngLat.lng }));
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
      markerRef.current = null;
    };
  }, [loadReports]);

  // The page is for reporting where you are: ask for the location once when it opens
  useEffect(() => {
    if (isActive) locate();
  }, [isActive, locate]);

  // One draggable pin
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !pin) {
      markerRef.current?.remove();
      markerRef.current = null;
      return;
    }
    if (!markerRef.current) {
      const m = new maplibregl.Marker({ color: PIN_COLOR, draggable: true });
      m.on('dragend', () => {
        const ll = m.getLngLat();
        setPin({ lat: ll.lat, lng: ll.lng });
      });
      markerRef.current = m;
    }
    markerRef.current.setLngLat([pin.lng, pin.lat]).addTo(map);
  }, [pin]);

  const onSent = (r) => {
    setSent(r);
    if (r.status === 'published') loadReports();
    // the result replaces the form: bring it into view (on a phone it sits under the map)
    setTimeout(() => sideRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50);
  };
  const again = () => {
    setSent(null);
    setPin(null);
    setFormKey((k) => k + 1);
  };

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Report Flood"
        description="เห็นน้ำท่วมบนถนน ปักหมุด บอกระดับน้ำ แนบรูป · AI ตรวจรูปก่อนขึ้นแผนที่ · รายงานอยู่บนแผนที่ 6 ชั่วโมง"
      />
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_400px] gap-4 items-start">
        <Card className="p-0 overflow-hidden">
          <div className="relative h-[46vh] min-h-[320px] lg:h-[calc(100vh-13rem)]">
            {/* inline position: maplibre-gl.css sets .maplibregl-map { position: relative } over a class */}
            <div ref={mapEl} style={{ position: 'absolute', inset: 0 }} aria-label="แผนที่สำหรับปักหมุดจุดน้ำท่วม" />
            <span className="absolute top-2.5 left-1/2 -translate-x-1/2 rounded-full bg-white border border-slate-200 px-3 py-1 text-[11px] text-slate-700 shadow-sm pointer-events-none whitespace-nowrap">
              {pin ? 'ลากหมุดหรือแตะที่อื่นเพื่อขยับ' : 'แตะแผนที่ตรงจุดที่น้ำท่วม'}
            </span>
            <button
              type="button"
              onClick={locate}
              disabled={locating}
              className={`absolute bottom-9 right-2.5 inline-flex items-center gap-1.5 h-10 px-3.5 rounded-full bg-white border border-slate-300 text-sm font-medium text-slate-800 shadow-md hover:bg-slate-50 disabled:opacity-70 cursor-pointer ${FOCUS}`}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className={`w-5 h-5 text-cyan-700 ${locating ? 'animate-pulse' : ''}`} aria-hidden="true">
                <circle cx="12" cy="12" r="3.5" />
                <path d="M12 2v3M12 19v3M2 12h3M19 12h3" />
                <circle cx="12" cy="12" r="7.5" />
              </svg>
              {locating ? 'กำลังหาตำแหน่ง…' : 'ตำแหน่งของฉัน'}
            </button>
          </div>
          {geoError && <p role="status" className="px-4 py-2 text-xs text-amber-800 bg-amber-50 border-t border-amber-200">{geoError}</p>}
        </Card>

        <div ref={sideRef} className="flex flex-col gap-3 scroll-mt-20">
          {sent ? (
            <Card className="p-4">
              <p role="status" className={`text-base font-semibold ${sent.status === 'published' ? 'text-emerald-700' : 'text-slate-900'}`}>{sent.message}</p>
              {sent.photo && <img src={sent.photo} alt="รูปที่ส่ง" className="mt-3 w-full max-h-56 object-cover rounded-md" />}
              <p className="mt-2 text-xs text-slate-500">
                {sent.status === 'published' ? 'รายงานนี้ขึ้นบนแผนที่แล้ว ในชั้น "ประชาชนแจ้งผ่านเว็บ"' : 'ระบบจะลองตรวจอีกครั้งอัตโนมัติ ผ่านแล้วจะขึ้นแผนที่เอง'}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button variant="primary" size="sm" onClick={() => onNavigate('map')}>ดูบนแผนที่</Button>
                <Button variant="secondary" size="sm" onClick={again}>แจ้งอีกจุด</Button>
              </div>
            </Card>
          ) : (
            <ReportFloodForm key={formKey} pin={pin} locating={locating} onUseMyLocation={locate} onSent={onSent} />
          )}
          <p className="text-[11px] text-slate-500 leading-4 px-1">
            จุดสีฟ้าจางบนแผนที่คือรายงานที่มีคนแจ้งแล้วใน 6 ชั่วโมง · ถ้ามีคนแจ้งจุดเดียวกันแล้ว ไม่ต้องแจ้งซ้ำ
          </p>
        </div>
      </div>
    </div>
  );
}
