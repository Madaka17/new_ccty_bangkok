// ปุ่มฉุกเฉิน: a round button over every page. It opens the hotlines (tel: links), the 3 nearest BMA shelters and
// the 3 nearest hospitals, and "แชร์ตำแหน่งฉัน" that hands a map link of the user's position to the share sheet
// (or the clipboard). Shelters and hospitals are static files (web/public/riskbkk/shelter.geojson,
// hospital.geojson from local/pipeline/build_hospitals.py) sorted in the browser: the position leaves the
// device only when the user shares it.
import { useCallback, useEffect, useRef, useState } from 'react';
import { Badge } from './dashboard/ui.jsx';
import { distanceKm, fmtKm, accuracyText, roughWarning } from '../lib/geo.js';

const HOTLINES = [
  ['1669', 'เจ็บป่วยฉุกเฉิน', 'เรียกรถพยาบาล'],
  ['191', 'แจ้งเหตุด่วน', 'ตำรวจ'],
  ['199', 'ไฟไหม้ กู้ภัย', 'ดับเพลิงและกู้ภัย'],
  ['1784', 'ภัยพิบัติ น้ำท่วม', 'ปภ.'],
  ['1555', 'เรื่องเดือดร้อนใน กทม.', 'กรุงเทพมหานคร'],
];
const NEAREST = 3;
const FRESH_MS = 120000;   // a position younger than this is shared as it is
const GEO_ERROR = {
  1: 'ไม่ได้รับอนุญาตให้ใช้ตำแหน่ง เปิดสิทธิ์ตำแหน่งให้เว็บนี้ในเบราว์เซอร์',
  2: 'หาตำแหน่งไม่ได้ ลองเปิด GPS แล้วกดใหม่',
  3: 'หาตำแหน่งนานเกินไป ลองกดใหม่',
};

const loadPoints = (file) => fetch(`/riskbkk/${file}`).then((r) => (r.ok ? r.json() : Promise.reject(new Error(file)))).then((d) => d.features || []);

function nearest(features, pos) {
  return features
    .map((f) => ({ ...f, km: distanceKm(pos.lat, pos.lng, f.geometry.coordinates[1], f.geometry.coordinates[0]) }))
    .sort((a, b) => a.km - b.km)
    .slice(0, NEAREST);
}

function PlaceRow({ f, badge }) {
  const [lng, lat] = f.geometry.coordinates;
  const p = f.properties;
  return (
    <li className="py-2 flex flex-col gap-1">
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-medium text-slate-900 min-w-0">{p.title}</p>
        <Badge tone="blue">{fmtKm(f.km)}</Badge>
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        {badge}
        <a
          href={`https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}`}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center h-11 px-4 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700"
        >
          นำทาง
        </a>
        {p.tel?.slice(0, 1).map((t) => (
          <a key={t} href={`tel:${t.replace(/[^\d+]/g, '')}`} className="inline-flex items-center h-11 px-4 rounded-lg border border-slate-300 text-sm font-medium text-slate-800 hover:bg-slate-50">
            โทร {t}
          </a>
        ))}
      </div>
    </li>
  );
}

function EmergencyPanel({ onClose }) {
  const [pos, setPos] = useState(null);            // { lat, lng, accuracy, at }
  const [locating, setLocating] = useState(false);
  const [geoError, setGeoError] = useState('');
  const [places, setPlaces] = useState(null);      // { shelter: [], hospital: [] } once loaded
  const [placesError, setPlacesError] = useState(false);
  const [shareMsg, setShareMsg] = useState('');
  const [shareAgain, setShareAgain] = useState(false);
  const closeRef = useRef(null);
  const panelRef = useRef(null);

  // Modal: focus starts on "ปิด", Tab stays inside the panel, the page behind does not scroll, and focus goes
  // back to the round button on close.
  useEffect(() => {
    const opener = document.activeElement;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    closeRef.current?.focus();
    const onKey = (e) => {
      if (e.key === 'Escape') onClose();
      if (e.key !== 'Tab' || !panelRef.current) return;
      const items = panelRef.current.querySelectorAll('a[href], button:not([disabled])');
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = overflow;
      opener?.focus?.();
    };
  }, [onClose]);

  const locate = () =>
    new Promise((resolve, reject) => {
      if (!window.isSecureContext || !navigator.geolocation) {
        reject(new Error('เบราว์เซอร์นี้ไม่ให้ใช้ตำแหน่ง'));
        return;
      }
      setLocating(true);
      setGeoError('');
      navigator.geolocation.getCurrentPosition(
        (p) => {
          const next = { lat: p.coords.latitude, lng: p.coords.longitude, accuracy: p.coords.accuracy, at: Date.now() };
          setPos(next);
          setLocating(false);
          resolve(next);
        },
        (e) => {
          setLocating(false);
          reject(new Error(GEO_ERROR[e.code] || GEO_ERROR[2]));
        },
        { enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 },
      );
    });

  const findNearby = async () => {
    try {
      await locate();
    } catch (e) {
      setGeoError(e.message);
      return;
    }
    if (places) return;
    setPlacesError(false);
    Promise.all([loadPoints('shelter.geojson'), loadPoints('hospital.geojson')])
      .then(([shelter, hospital]) => setPlaces({ shelter, hospital: hospital.filter((h) => h.properties.emergency !== false) }))
      .catch(() => setPlacesError(true));
  };

  const share = async () => {
    setShareMsg('');
    setShareAgain(false);
    let p = pos && Date.now() - pos.at < FRESH_MS ? pos : null;
    if (!p) {
      try {
        p = await locate();
      } catch (e) {
        setGeoError(e.message);
        return;
      }
    }
    const link = `https://maps.google.com/?q=${p.lat.toFixed(6)},${p.lng.toFixed(6)}`;
    const text = `ฉันอยู่ตรงนี้ (คลาดเคลื่อนได้ ${accuracyText(p.accuracy)}): ${link}`;
    if (navigator.share) {
      try {
        await navigator.share({ title: 'ตำแหน่งของฉัน', text });
        return;
      } catch (e) {
        if (e.name === 'AbortError') return;   // the user closed the share sheet
        if (e.name === 'NotAllowedError') {
          // finding the position took too long for the browser to count it as the same tap
          setShareAgain(true);
          return;
        }
      }
    }
    try {
      await navigator.clipboard.writeText(text);
      setShareMsg('คัดลอกตำแหน่งแล้ว วางในแชตเพื่อส่งให้ญาติหรือกู้ภัยได้เลย');
    } catch {
      setShareMsg(text);
    }
  };

  const shelters = places && pos ? nearest(places.shelter, pos) : [];
  const hospitals = places && pos ? nearest(places.hospital, pos) : [];

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center" role="dialog" aria-modal="true" aria-labelledby="sos-title">
      <button type="button" aria-label="ปิด" onClick={onClose} className="absolute inset-0 bg-slate-900/50" />
      <div ref={panelRef} className="relative w-full sm:max-w-md max-h-[90dvh] overflow-y-auto overscroll-contain rounded-t-2xl sm:rounded-2xl bg-white p-4 pb-[calc(1rem+env(safe-area-inset-bottom))] flex flex-col gap-4 shadow-xl">
        <div className="flex items-center justify-between gap-2">
          <h2 id="sos-title" className="text-lg font-bold text-red-700">ฉุกเฉิน</h2>
          <button ref={closeRef} type="button" onClick={onClose} className="cursor-pointer h-11 px-4 rounded-lg text-sm text-slate-700 hover:bg-slate-100">
            ปิด
          </button>
        </div>

        <section aria-label="เบอร์โทรฉุกเฉิน" className="flex flex-col gap-2">
          <p className="text-sm text-slate-600">กดเบอร์เพื่อโทรทันที</p>
          <ul className="grid grid-cols-1 gap-2">
            {HOTLINES.map(([num, what, who]) => (
              <li key={num}>
                <a href={`tel:${num}`} className="flex items-center gap-3 rounded-xl border border-red-200 bg-red-50 px-3 h-14 hover:bg-red-100">
                  <span className="text-xl font-bold text-red-700 tabular-nums w-16">{num}</span>
                  <span className="min-w-0">
                    <span className="block text-sm font-semibold text-slate-900">{what}</span>
                    <span className="block text-xs text-slate-600">{who}</span>
                  </span>
                </a>
              </li>
            ))}
          </ul>
        </section>

        <section aria-label="แชร์ตำแหน่ง" className="flex flex-col gap-2">
          <button
            type="button"
            onClick={share}
            disabled={locating}
            className="cursor-pointer h-12 rounded-xl bg-blue-600 text-white text-sm font-semibold hover:bg-blue-700 disabled:opacity-60"
          >
            {locating ? 'กำลังหาตำแหน่ง...' : shareAgain ? 'ได้ตำแหน่งแล้ว กดอีกครั้งเพื่อส่ง' : 'แชร์ตำแหน่งฉัน'}
          </button>
          <p className="text-xs text-slate-500">ส่งลิงก์แผนที่ตำแหน่งของคุณให้ญาติหรือกู้ภัย ตำแหน่งจะออกจากเครื่องเมื่อคุณกดส่งเท่านั้น</p>
          {shareMsg && <p role="status" className="text-sm text-slate-800 break-all select-all">{shareMsg}</p>}
        </section>

        <section aria-label="ที่พักพิงและโรงพยาบาลใกล้ฉัน" className="flex flex-col gap-2">
          {!pos || !places ? (
            <button
              type="button"
              onClick={findNearby}
              disabled={locating}
              className="cursor-pointer h-11 rounded-xl border border-slate-300 text-sm font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-60"
            >
              {locating ? 'กำลังหาตำแหน่ง...' : 'หาที่พักพิงและโรงพยาบาลใกล้ฉัน'}
            </button>
          ) : (
            <>
              {roughWarning(pos.accuracy) && <p className="text-xs text-amber-700">{roughWarning(pos.accuracy)}</p>}
              <div>
                <h3 className="text-sm font-semibold text-slate-900">ที่พักพิงชั่วคราวของ กทม. ใกล้ที่สุด</h3>
                <ul className="divide-y divide-slate-100">
                  {shelters.map((f) => (
                    <PlaceRow key={f.properties.title + f.geometry.coordinates} f={f} badge={f.properties.capacity ? <Badge tone="green">รับได้ {f.properties.capacity} คน</Badge> : null} />
                  ))}
                </ul>
              </div>
              <div>
                <h3 className="text-sm font-semibold text-slate-900">โรงพยาบาลใกล้ที่สุด</h3>
                <ul className="divide-y divide-slate-100">
                  {hospitals.map((f) => (
                    <PlaceRow key={f.properties.title + f.geometry.coordinates} f={f} badge={f.properties.emergency ? <Badge tone="red">มีห้องฉุกเฉิน</Badge> : null} />
                  ))}
                </ul>
                <p className="text-xs text-slate-500 mt-1">รายชื่อโรงพยาบาลจาก OpenStreetMap ก่อนไปควรโทรถามก่อน</p>
              </div>
            </>
          )}
          {geoError && <p role="alert" className="text-sm text-red-700">{geoError}</p>}
          {placesError && <p role="alert" className="text-sm text-red-700">โหลดรายชื่อที่พักพิงและโรงพยาบาลไม่สำเร็จ ลองกดใหม่</p>}
        </section>
      </div>
    </div>
  );
}

export default function EmergencyButton() {
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        aria-label="ฉุกเฉิน: เบอร์โทร ที่พักพิง โรงพยาบาล และแชร์ตำแหน่ง"
        className="cursor-pointer fixed z-40 right-5 bottom-[calc(148px+env(safe-area-inset-bottom))] lg:right-8 lg:bottom-26 h-14 w-14 rounded-full bg-red-600 text-white text-xs font-bold shadow-lg ring-4 ring-white/70 hover:bg-red-700 focus-visible:outline-none focus-visible:ring-red-300"
      >
        ฉุกเฉิน
      </button>
      {open && <EmergencyPanel onClose={close} />}
    </>
  );
}
