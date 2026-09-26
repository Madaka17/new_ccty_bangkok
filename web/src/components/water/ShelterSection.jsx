// จุดพักพิงใกล้ฉัน: the 263 BMA temporary shelters (สถานที่พักพิงชั่วคราว, from the BMA risk map, slimmed into
// web/public/riskbkk/shelter.geojson by local/pipeline/build_riskbkk_layers.py) sorted by distance from the
// user's position. Everything runs in the browser: the position never leaves the device. Without a position
// (denied, or the page is not on https / localhost) the user picks a district instead. Tab of the Water
// Forecast page.
import { useEffect, useMemo, useState } from 'react';
import { Card, Badge, Button, SectionHeader, Skeleton, EmptyState, ErrorState } from '../dashboard/ui.jsx';
import { fmtNum } from '../dashboard/format.js';

const SHOWN = 10;   // nearest shelters listed before "แสดงเพิ่ม"
const SELECT = 'h-10 rounded-lg border border-slate-300 bg-white px-2 text-sm text-slate-700';
const GEO_ERROR = {
  1: 'ไม่ได้รับอนุญาตให้ใช้ตำแหน่ง เปิดสิทธิ์ตำแหน่งให้เว็บนี้ในเบราว์เซอร์ หรือเลือกเขตด้านล่างแทน',
  2: 'หาตำแหน่งไม่ได้ ลองเปิด GPS แล้วกดใหม่ หรือเลือกเขตด้านล่างแทน',
  3: 'หาตำแหน่งนานเกินไป ลองกดใหม่ หรือเลือกเขตด้านล่างแทน',
};

// Great-circle distance in km
function distanceKm(lat1, lng1, lat2, lng2) {
  const rad = (d) => (d * Math.PI) / 180;
  const a = Math.sin(rad(lat2 - lat1) / 2) ** 2 + Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(rad(lng2 - lng1) / 2) ** 2;
  return 6371 * 2 * Math.asin(Math.sqrt(a));
}

const fmtKm = (km) => (km < 1 ? `${Math.round(km * 1000)} ม.` : `${km.toFixed(1)} กม.`);

function ShelterRow({ s }) {
  const [lng, lat] = s.geometry.coordinates;
  const p = s.properties;
  return (
    <li className="py-3 flex flex-col gap-1.5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-slate-900">{p.title}</p>
          <p className="text-[13px] text-slate-600 leading-5">{p.address || `เขต${p.district}`}</p>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {s.km != null && <Badge tone="blue">{fmtKm(s.km)}</Badge>}
          <Badge tone={p.capacity ? 'green' : 'neutral'}>{p.capacity ? `รับได้ ${fmtNum(p.capacity)} คน` : 'ไม่ระบุความจุ'}</Badge>
        </div>
      </div>
      {p.facilities?.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {p.facilities.map((f) => <Badge key={f}>{f}</Badge>)}
        </div>
      )}
      {p.info?.length > 0 && <p className="text-xs text-slate-500 leading-5">{p.info.join(' · ')}</p>}
      <div className="flex flex-wrap items-center gap-2 mt-0.5">
        <a
          href={`https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}`}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center h-8 px-3 rounded-lg bg-blue-600 text-white text-xs font-medium hover:bg-blue-700"
        >
          นำทาง
        </a>
        {p.tel?.map((t) => (
          <a key={t} href={`tel:${t.replace(/[^\d+]/g, '')}`} className="inline-flex items-center h-8 px-3 rounded-lg border border-slate-300 text-xs font-medium text-slate-800 hover:bg-slate-50">
            โทร {t}
          </a>
        ))}
      </div>
    </li>
  );
}

export default function ShelterSection({ isActive }) {
  const [shelters, setShelters] = useState(null);
  const [error, setError] = useState(false);
  const [pos, setPos] = useState(null);           // { lat, lng, accuracy }
  const [locating, setLocating] = useState(false);
  const [geoError, setGeoError] = useState('');
  const [district, setDistrict] = useState('');
  const [shown, setShown] = useState(SHOWN);

  const load = () => {
    setError(false);
    fetch('/riskbkk/shelter.geojson')
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error('shelter'))))
      .then((d) => setShelters(d.features || []))
      .catch(() => setError(true));
  };

  useEffect(() => {
    if (isActive && !shelters) load();
  }, [isActive]); // eslint-disable-line react-hooks/exhaustive-deps

  const locate = () => {
    if (!window.isSecureContext || !navigator.geolocation) {
      setGeoError('เบราว์เซอร์ใช้ตำแหน่งได้เฉพาะเว็บที่เปิดผ่าน https หรือ localhost เลือกเขตด้านล่างแทน');
      return;
    }
    setLocating(true);
    setGeoError('');
    navigator.geolocation.getCurrentPosition(
      (p) => {
        setPos({ lat: p.coords.latitude, lng: p.coords.longitude, accuracy: p.coords.accuracy });
        setDistrict('');
        setShown(SHOWN);
        setLocating(false);
      },
      (e) => {
        setGeoError(GEO_ERROR[e.code] || GEO_ERROR[2]);
        setLocating(false);
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 },
    );
  };

  const districts = useMemo(() => [...new Set((shelters || []).map((s) => s.properties.district).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'th')), [shelters]);

  // Nearest first from the user's position; a picked district lists its shelters (by distance too when located)
  const rows = useMemo(() => {
    if (!shelters) return [];
    let list = shelters.map((s) => ({ ...s, km: pos ? distanceKm(pos.lat, pos.lng, s.geometry.coordinates[1], s.geometry.coordinates[0]) : null }));
    if (district) list = list.filter((s) => s.properties.district === district);
    else if (!pos) return [];
    return list.sort((a, b) => (a.km ?? 0) - (b.km ?? 0) || a.properties.title.localeCompare(b.properties.title, 'th'));
  }, [shelters, pos, district]);

  const nearest = pos && !district ? rows[0] : null;

  return (
    <div className="flex flex-col gap-4">
      <Card className="p-4 flex flex-col gap-3">
        <SectionHeader
          title="จุดพักพิงชั่วคราวใกล้ฉัน"
          description={`สถานที่พักพิงชั่วคราวของกรุงเทพมหานคร${shelters ? ` ${fmtNum(shelters.length)} แห่ง` : ''} (โรงเรียน วัด อาคาร กทม.) เรียงจากใกล้ที่สุด ตำแหน่งของคุณใช้คำนวณในเครื่องเท่านั้น ไม่ส่งไปที่เซิร์ฟเวอร์`}
        />
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="primary" onClick={locate} loading={locating} disabled={!shelters}>
            {pos ? 'อัปเดตตำแหน่งของฉัน' : 'ใช้ตำแหน่งของฉัน'}
          </Button>
          <label className="sr-only" htmlFor="shelter-district">เลือกเขต</label>
          <select
            id="shelter-district"
            className={SELECT}
            value={district}
            onChange={(e) => { setDistrict(e.target.value); setShown(SHOWN); }}
            disabled={!shelters}
          >
            <option value="">{pos ? 'ทุกเขต (ใกล้ที่สุด)' : 'หรือเลือกเขต'}</option>
            {districts.map((d) => <option key={d} value={d}>เขต{d}</option>)}
          </select>
          {pos && (
            <span className="text-xs text-slate-500">
              ตำแหน่ง {pos.lat.toFixed(4)}, {pos.lng.toFixed(4)} · แม่นยำ ±{fmtNum(Math.round(pos.accuracy))} ม.
            </span>
          )}
        </div>
        {geoError && <p role="status" className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">{geoError}</p>}
        {nearest && nearest.km > 15 && (
          <p role="status" className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
            จุดที่ใกล้ที่สุดห่าง {fmtKm(nearest.km)} ข้อมูลนี้มีเฉพาะในกรุงเทพมหานคร ถ้าอยู่ปริมณฑลให้ติดต่อ อบต./เทศบาล หรือสายด่วน ปภ. 1784
          </p>
        )}
      </Card>

      {error && <ErrorState message="โหลดรายชื่อจุดพักพิงไม่สำเร็จ" onRetry={load} />}

      {!shelters && !error && (
        <Card as="div" className="p-4 flex flex-col gap-3">
          {[0, 1, 2].map((i) => <Skeleton key={i} className="h-16 w-full" />)}
        </Card>
      )}

      {shelters && rows.length === 0 && (
        <EmptyState title="ยังไม่ได้เลือกตำแหน่ง" description="กด “ใช้ตำแหน่งของฉัน” หรือเลือกเขต เพื่อดูจุดพักพิงที่ใกล้ที่สุด" />
      )}

      {rows.length > 0 && (
        <Card className="px-4 py-1">
          <ul className="divide-y divide-slate-100">
            {rows.slice(0, shown).map((s) => <ShelterRow key={`${s.properties.title}-${s.geometry.coordinates.join(',')}`} s={s} />)}
          </ul>
          {rows.length > shown && (
            <div className="py-3 flex justify-center">
              <Button size="sm" onClick={() => setShown((n) => n + SHOWN)}>แสดงเพิ่ม ({fmtNum(rows.length - shown)} แห่ง)</Button>
            </div>
          )}
        </Card>
      )}

      <p className="text-xs text-slate-500 leading-5 px-1">
        แหล่งข้อมูล: สถานที่พักพิงชั่วคราว แผนที่เสี่ยงภัยกรุงเทพมหานคร (cpudapp.bangkok.go.th/riskbkk) ข้อมูลไม่ระบุวันที่ปรับปรุง
        ก่อนเดินทางควรโทรยืนยันว่าเปิดรับผู้อพยพ · ระยะทางเป็นเส้นตรง ไม่ใช่ระยะทางถนน · เหตุฉุกเฉิน โทร 199 (ดับเพลิงและกู้ภัย) · 1784 (ปภ.) · 1669 (เจ็บป่วยฉุกเฉิน)
      </p>
    </div>
  );
}
