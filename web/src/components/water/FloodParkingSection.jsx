// จุดจอดรถหนีน้ำ: the car parks the BMA, a mall or a building has announced for cars fleeing a flood
// (config/flood_parking.json through /api/flood/parking, flood_parking.py). Only announced spots are listed, each
// with its source. Anyone can press "แจ้งว่าเต็มแล้ว"; that note fades by itself unless someone presses again.
// Tab of the Water Forecast page.
import { useEffect, useMemo, useState } from 'react';
import { Card, Badge, Button, SectionHeader, Skeleton, EmptyState, ErrorState } from '../dashboard/ui.jsx';
import { fmtNum, fmtTime, fmtDateTime } from '../dashboard/format.js';
import { distanceKm, fmtKm } from '../../lib/geo.js';
import { fetchFloodParking, postParkingFull } from '../../lib/api.js';

const STATUS_TONE = { open: 'green', near_full: 'yellow', full: 'red' };
const REFRESH_MS = 60000;

function SpotRow({ s, pressed, onFull }) {
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const full = s.user_full;
  const press = async () => {
    setSending(true);
    setError('');
    try {
      await onFull(s.id);
    } catch (e) {
      setError(e.message);
    }
    setSending(false);
  };
  return (
    <li className="py-3 flex flex-col gap-1.5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="text-sm font-semibold text-slate-900 min-w-0">{s.name}</p>
        <div className="flex items-center gap-1.5 shrink-0">
          {s.km != null && <Badge tone="blue">{fmtKm(s.km)}</Badge>}
          {s.status && <Badge tone={STATUS_TONE[s.status]}>{s.status_th}</Badge>}
        </div>
      </div>
      <p className="text-[13px] text-slate-600 leading-5">
        {[s.capacity && `ราว ${fmtNum(s.capacity)} คัน`, s.fee && `ค่าจอด ${s.fee}`, s.hours && `เปิด ${s.hours}`, s.until && `จอดได้ถึง ${fmtDateTime(s.until)}`].filter(Boolean).join(' · ')}
      </p>
      {full && (
        <p className="text-[13px] font-medium text-red-700">
          มีคนแจ้งว่าเต็มแล้ว {fmtNum(full.count)} คน ล่าสุด {fmtTime(full.last_ts)} น.
        </p>
      )}
      <p className="text-xs text-slate-500">
        ข้อมูลจาก{' '}
        <a href={s.source_url} target="_blank" rel="noopener noreferrer" className="underline hover:text-slate-700">{s.source}</a>
        {s.status_at && ` · สถานะอัปเดต ${fmtDateTime(s.status_at)}`}
      </p>
      <div className="flex flex-wrap items-center gap-2 mt-0.5">
        <a
          href={`https://www.google.com/maps/dir/?api=1&destination=${s.lat},${s.lng}`}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center h-10 px-4 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700"
        >
          นำทาง
        </a>
        <Button onClick={press} loading={sending} disabled={pressed}>
          {pressed ? 'แจ้งแล้ว ขอบคุณ' : 'แจ้งว่าเต็มแล้ว'}
        </Button>
        {error && <span role="alert" className="text-xs text-red-700">{error}</span>}
      </div>
    </li>
  );
}

export default function FloodParkingSection({ isActive }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const [pos, setPos] = useState(null);
  const [locating, setLocating] = useState(false);
  const [geoError, setGeoError] = useState('');
  const [pressed, setPressed] = useState(() => new Set());

  const load = () =>
    fetchFloodParking()
      .then((d) => { setData(d); setError(false); })
      .catch(() => setError(true));

  useEffect(() => {
    if (!isActive) return undefined;
    load();
    const id = setInterval(load, REFRESH_MS);
    return () => clearInterval(id);
  }, [isActive]); // eslint-disable-line react-hooks/exhaustive-deps

  const locate = () => {
    if (!window.isSecureContext || !navigator.geolocation) {
      setGeoError('เบราว์เซอร์นี้ไม่ให้ใช้ตำแหน่ง');
      return;
    }
    setLocating(true);
    setGeoError('');
    navigator.geolocation.getCurrentPosition(
      (p) => { setPos({ lat: p.coords.latitude, lng: p.coords.longitude }); setLocating(false); },
      () => { setGeoError('หาตำแหน่งไม่ได้ ลองเปิด GPS แล้วกดใหม่'); setLocating(false); },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 },
    );
  };

  const onFull = async (id) => {
    const r = await postParkingFull(id);
    setPressed((s) => new Set(s).add(id));
    setData((d) => ({ ...d, spots: d.spots.map((s) => (s.id === id ? { ...s, user_full: r.user_full } : s)) }));
  };

  const spots = useMemo(() => {
    const list = (data?.spots || []).map((s) => ({ ...s, km: pos ? distanceKm(pos.lat, pos.lng, s.lat, s.lng) : null }));
    return pos ? list.sort((a, b) => a.km - b.km) : list;
  }, [data, pos]);

  if (error && !data) return <ErrorState message="โหลดจุดจอดรถหนีน้ำไม่สำเร็จ" onRetry={load} />;
  if (!data) return <Skeleton className="h-[240px] rounded-xl" />;

  return (
    <Card className="p-4 flex flex-col gap-3">
      <SectionHeader
        title="จุดจอดรถหนีน้ำ"
        description="เฉพาะที่ กทม. ห้าง หรืออาคารประกาศให้จอดได้ ก่อนไปควรโทรถามอีกครั้ง"
      />
      {spots.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="primary" onClick={locate} loading={locating}>
            {pos ? 'อัปเดตตำแหน่งของฉัน' : 'เรียงจากใกล้ฉัน'}
          </Button>
          {geoError && <span role="alert" className="text-sm text-red-700">{geoError}</span>}
        </div>
      )}
      {spots.length ? (
        <>
          <ul className="divide-y divide-slate-100">
            {spots.map((s) => <SpotRow key={s.id} s={s} pressed={pressed.has(s.id)} onFull={onFull} />)}
          </ul>
          <p className="text-xs text-slate-500">
            คำว่า "มีคนแจ้งว่าเต็มแล้ว" จะหายเองใน {Math.round(data.report_minutes / 60 * 10) / 10} ชม. ถ้าไม่มีคนแจ้งซ้ำ
          </p>
        </>
      ) : (
        <EmptyState
          title="ยังไม่มีจุดจอดรถหนีน้ำที่ประกาศในตอนนี้"
          description="เมื่อ กทม. ห้าง หรืออาคารประกาศเปิดให้จอดรถหนีน้ำ จุดนั้นจะขึ้นที่นี่"
        />
      )}
    </Card>
  );
}
