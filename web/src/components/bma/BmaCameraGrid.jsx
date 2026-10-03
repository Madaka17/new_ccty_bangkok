import { useEffect, useMemo, useState } from 'react';
import { getBmaSnapshotUrl } from '../../lib/api.js';
import { distanceKm } from '../../lib/store.js';
import { Card, Badge, Button, Segmented, Skeleton, EmptyState, Truncate, FOCUS } from '../dashboard/ui.jsx';
import { agoText } from '../dashboard/format.js';
import { levelOf } from './BmaOverview.jsx';
import BmaCameraModal from './BmaCameraModal.jsx';

const PAGE = 60;
const SELECT = `h-9 rounded-lg border border-slate-300 bg-white px-2.5 text-sm text-slate-800 ${FOCUS}`;

// Every BMA camera as a card: real-time snapshot + counts. Click for the live YOLO stream.
export default function BmaCameraGrid({ cameras, loading, filters, onFilters }) {
  const { query, district, level, sort } = filters;
  const [limit, setLimit] = useState(PAGE);
  const [open, setOpen] = useState(null);
  const [realtime, setRealtime] = useState(false);
  const [tick, setTick] = useState(Date.now());
  const [pos, setPos] = useState(null);
  const [posMsg, setPosMsg] = useState('');

  // "ใกล้ฉัน" sort: ask the browser for the position (it stays in the browser; nothing is sent to the server)
  useEffect(() => {
    if (sort !== 'near' || pos) return;
    const fallback = (msg) => {
      setPosMsg(msg);
      onFilters((f) => ({ ...f, sort: 'total_desc' }));
    };
    if (!navigator.geolocation) return fallback('เบราว์เซอร์นี้ไม่รองรับตำแหน่ง');
    setPosMsg('กำลังหาตำแหน่งของคุณ...');
    navigator.geolocation.getCurrentPosition(
      (p) => {
        setPos({ lat: p.coords.latitude, lng: p.coords.longitude });
        setPosMsg('');
      },
      () => fallback('ไม่ได้รับตำแหน่งของคุณ จึงเรียงตามรถมากสุดแทน'),
      { timeout: 8000, maximumAge: 60000 },
    );
  }, [sort, pos, onFilters]);

  // Auto-refresh snapshots when real-time mode is on
  useEffect(() => {
    if (!realtime) return;
    const id = setInterval(() => setTick(Date.now()), 3500);
    return () => clearInterval(id);
  }, [realtime]);

  const districts = useMemo(() => Array.from(new Set(cameras.map((c) => c.district).filter((d) => d && d !== 'กรุงเทพมหานคร'))).sort((a, b) => a.localeCompare(b, 'th')), [cameras]);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    let list = cameras;
    if (q) list = list.filter((c) => [c.title, c.short_title, c.road, c.district, c.camera_code, c.camid].some((v) => String(v || '').toLowerCase().includes(q)));
    if (district !== 'all') list = list.filter((c) => c.district === district);
    if (level === 'has') list = list.filter((c) => (c.total || 0) > 0);
    else if (level !== 'all') list = list.filter((c) => c.level === level);
    if (sort === 'near' && pos) {
      return list
        .map((c) => ({ ...c, _km: c.latitude && c.longitude ? distanceKm(pos, { lat: c.latitude, lng: c.longitude }) : Infinity }))
        .sort((a, b) => a._km - b._km);
    }
    return [...list].sort((a, b) => {
      if (sort === 'total_desc') return (b.total || 0) - (a.total || 0);
      if (sort === 'total_asc') return (a.total || 0) - (b.total || 0);
      if (sort === 'road') return (a.road || '').localeCompare(b.road || '', 'th');
      return parseInt(a.camid || 0, 10) - parseInt(b.camid || 0, 10);
    });
  }, [cameras, query, district, level, sort, pos]);

  const set = (patch) => {
    onFilters({ ...filters, ...patch });
    setLimit(PAGE);
  };
  const hasFilter = query || district !== 'all' || level !== 'all';

  return (
    <div className="flex flex-col gap-4">
      <Card className="p-4 flex flex-wrap items-center gap-3">
        <label className="sr-only" htmlFor="bma-search">
          ค้นหากล้อง
        </label>
        <input
          id="bma-search"
          type="search"
          value={query}
          onChange={(e) => set({ query: e.target.value })}
          placeholder="ค้นหาแยก ถนน เขต หรือรหัสกล้อง"
          className={`flex-1 min-w-[220px] ${SELECT}`}
        />
        <label className="sr-only" htmlFor="bma-district">
          เขต
        </label>
        <select id="bma-district" value={district} onChange={(e) => set({ district: e.target.value })} className={SELECT}>
          <option value="all">ทุกเขต</option>
          {districts.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
        <Segmented
          label="รถติดแค่ไหน"
          value={level}
          onChange={(v) => set({ level: v })}
          options={[
            ['all', 'ทั้งหมด'],
            ['has', 'มีรถ'],
            ['heavy', 'ติดขัด'],
            ['moderate', 'ชะลอตัว'],
            ['free', 'คล่องตัว'],
          ]}
        />
        <label className="sr-only" htmlFor="bma-sort">
          เรียงตาม
        </label>
        <select id="bma-sort" value={sort} onChange={(e) => set({ sort: e.target.value })} className={SELECT}>
          <option value="near">ใกล้ฉันก่อน</option>
          <option value="total_desc">รถมากสุดก่อน</option>
          <option value="total_asc">รถน้อยสุดก่อน</option>
          <option value="road">ตามชื่อถนน</option>
          <option value="camid">ตามรหัสกล้อง</option>
        </select>
        {hasFilter && (
          <Button size="sm" variant="ghost" onClick={() => set({ query: '', district: 'all', level: 'all' })}>
            ล้างตัวกรอง
          </Button>
        )}
        <button
          type="button"
          onClick={() => setRealtime((v) => !v)}
          className={`cursor-pointer inline-flex items-center gap-2 h-9 px-3 rounded-lg text-xs font-semibold transition-all ${
            realtime
              ? 'bg-emerald-600 text-white shadow-sm ring-2 ring-emerald-400/50 hover:bg-emerald-700'
              : 'border border-slate-300 bg-white text-slate-700 hover:bg-slate-50'
          }`}
          title="ดูภาพสดจากกล้อง กทม. และให้ AI นับรถใหม่ทุก 3.5 วินาที"
        >
          <span className={`w-2 h-2 rounded-full ${realtime ? 'bg-white animate-ping' : 'bg-slate-400'}`} />
          {realtime ? 'ภาพสด: เปิดอยู่' : 'เปิดภาพสด'}
        </button>
        {posMsg && <span className="text-xs text-slate-600">{posMsg}</span>}
        <span className="text-xs text-slate-500 ml-auto">
          แสดง {Math.min(limit, shown.length)} จาก {shown.length} กล้อง
        </span>
      </Card>

      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          {[...Array(8)].map((_, i) => (
            <Skeleton key={i} className="h-56 w-full" />
          ))}
        </div>
      ) : !shown.length ? (
        <EmptyState title="ไม่พบกล้องตามเงื่อนไข" action={hasFilter ? <Button size="sm" onClick={() => set({ query: '', district: 'all', level: 'all' })}>ล้างตัวกรอง</Button> : null} />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          {shown.slice(0, limit).map((cam) => {
            const lv = levelOf(cam.level);
            const offline = cam.status !== 'online';
            return (
              <Card as="article" key={cam.camid} className="overflow-hidden flex flex-col group hover:shadow-md transition-shadow">
                <button
                  type="button"
                  onClick={() => setOpen(cam)}
                  className={`cursor-pointer relative aspect-[4/3] bg-slate-900 block w-full overflow-hidden ${FOCUS}`}
                  aria-label={`ดูภาพสด ${cam.title}`}
                >
                  <img
                    src={getBmaSnapshotUrl(cam.camid, realtime, tick)}
                    alt=""
                    loading="lazy"
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                  />
                  <span className="absolute top-2 right-2 rounded-md bg-slate-900/80 text-white text-xs font-medium px-2 py-0.5 tabular-nums backdrop-blur-xs">
                    {cam.total || 0} คัน
                  </span>
                  {realtime && !offline && (
                    <span className="absolute top-2 left-2 rounded-md bg-emerald-600/90 text-white text-[11px] font-medium px-1.5 py-0.5 flex items-center gap-1 shadow backdrop-blur-xs">
                      <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
                      สด AI
                    </span>
                  )}
                  {offline && <span className="absolute inset-0 flex items-center justify-center bg-slate-900/70 text-slate-200 text-sm">ไม่มีภาพ</span>}
                  <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity flex items-end p-2.5">
                    <span className="text-xs font-medium text-white flex items-center gap-1">
                      <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" /> แตะเพื่อดูภาพสด
                    </span>
                  </div>
                </button>
                <div className="p-3 flex flex-col gap-1.5">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <Truncate text={cam.short_title || cam.title} className="text-sm font-medium text-slate-900" />
                      <Truncate
                        text={`${cam.district || 'กทม.'} · ${cam.camera_code || cam.camid}${
                          Number.isFinite(cam._km) ? ` · ${cam._km < 1 ? `${Math.round(cam._km * 1000)} ม.` : `${cam._km.toFixed(1)} กม.`}` : ''
                        }`}
                        className="text-xs text-slate-500"
                      />
                    </div>
                    <Badge tone={offline ? 'neutral' : lv.tone}>{offline ? 'ไม่มีภาพ' : lv.label}</Badge>
                  </div>
                  <div className="flex items-center justify-between text-xs text-slate-600">
                    <span className="tabular-nums">
                      รถยนต์ {cam.cars || 0} · มอไซ {cam.motorcycles || 0} · บรรทุก {cam.trucks || 0}
                    </span>
                    <span className="text-slate-500">{agoText(cam.ts)}</span>
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      )}
      {shown.length > limit && (
        <div className="flex justify-center">
          <Button onClick={() => setLimit((l) => l + PAGE)}>แสดงเพิ่มอีก {Math.min(PAGE, shown.length - limit)} กล้อง</Button>
        </div>
      )}

      <BmaCameraModal key={open?.camid} cam={open} onClose={() => setOpen(null)} />
    </div>
  );
}
