import { useDeferredValue, useEffect, useMemo, useState } from 'react';
import { fetchBmaCameras, fetchCameraHealth } from '../lib/api.js';
import { Card, Badge, Button, Segmented, Skeleton, EmptyState, ErrorState, Truncate, FOCUS } from './dashboard/ui.jsx';
import { levelOf } from './bma/BmaOverview.jsx';
import BmaCameraModal from './bma/BmaCameraModal.jsx';

const PAGE = 50;
const INPUT = `h-10 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-800 ${FOCUS}`;
const LINK = `inline-flex items-center h-8 px-3 rounded-lg border border-slate-300 bg-white text-xs font-medium text-slate-800 hover:bg-slate-50 ${FOCUS}`;
const STATUS = [
  ['all', 'ทุกสถานะ'],
  ['online', 'มีสัญญาณ'],
  ['offline', 'ไม่มีสัญญาณ'],
];

// Case-insensitive, spaces ignored: "พระราม 4" finds "ถ.พระราม4"
const norm = (v) => String(v || '').toLowerCase().replace(/\s+/g, '');

function StatusBadge({ it }) {
  if (it.status === 'checking') return <Badge>กำลังเช็คสัญญาณ</Badge>;
  if (it.status === 'unknown') return <Badge>ไม่ทราบสถานะ</Badge>;
  if (it.status === 'offline') return <Badge tone="red" dot>ไม่มีสัญญาณ</Badge>;
  if (it.src === 'ai') return <Badge tone="green" dot>มีสัญญาณ</Badge>;
  const lv = levelOf(it.level);
  return <Badge tone={lv.tone}>{lv.label}</Badge>;
}

function ResultRow({ it, onOpen }) {
  return (
    <li className="px-4 py-3 flex flex-wrap sm:flex-nowrap items-center gap-x-3 gap-y-2">
      <div className="min-w-0 flex-1 basis-full sm:basis-auto">
        <div className="flex items-center gap-2 min-w-0">
          <Badge tone={it.src === 'ai' ? 'blue' : 'neutral'}>{it.src === 'ai' ? 'AI สด' : 'กทม.'}</Badge>
          {it.fav && (
            <span className="text-amber-500 text-sm" title="กล้องโปรด" aria-label="กล้องโปรด">
              ★
            </span>
          )}
          <Truncate text={it.name} className="text-sm font-medium text-slate-900" />
        </div>
        <Truncate text={`${it.area} · ${it.code}`} className="text-xs text-slate-500 mt-0.5" />
      </div>
      <div className="flex flex-wrap items-center gap-2 shrink-0">
        <StatusBadge it={it} />
        {it.src === 'bma' && it.status === 'online' && <span className="text-xs text-slate-600 tabular-nums">{it.total} คัน</span>}
        {it.lat && it.lng ? (
          <a href={`https://www.google.com/maps?q=${it.lat},${it.lng}`} target="_blank" rel="noreferrer" className={LINK}>
            แผนที่
          </a>
        ) : null}
        <Button size="sm" variant={it.status === 'offline' ? 'secondary' : 'primary'} onClick={() => onOpen(it)}>
          {it.src === 'ai' ? 'ดูสดด้วย AI' : 'ดูภาพสด'}
        </Button>
      </div>
    </li>
  );
}

// Every camera the site can show, in one search: the live-AI cameras (config/cameras_bkk.json, watched with
// the YOLO stream on the live tab) and the BMA cameras (snapshot counts). A live-AI camera opens on the live
// tab; a BMA camera opens its live stream in a dialog. Favorites first, then cameras with a signal.
export default function CameraSearchPage({ isActive, cameras, favorites, onWatchLive }) {
  const [bma, setBma] = useState([]);
  const [bmaState, setBmaState] = useState('loading'); // loading | ready | error
  const [health, setHealth] = useState(null); // null while the server checks the live-AI streams, false if it could not
  const [query, setQuery] = useState('');
  const [source, setSource] = useState('all');
  const [status, setStatus] = useState('all');
  const [limit, setLimit] = useState(PAGE);
  const [open, setOpen] = useState(null);
  const q = useDeferredValue(query);

  const loadBma = () => {
    setBmaState('loading');
    fetchBmaCameras()
      .then((d) => {
        setBma(d.items || []);
        setBmaState('ready');
      })
      .catch(() => setBmaState('error'));
  };

  useEffect(() => {
    if (!isActive) return;
    let alive = true;
    loadBma();
    fetchCameraHealth()
      .then((h) => alive && setHealth(h.items || {}))
      .catch(() => alive && setHealth(false));
    return () => {
      alive = false;
    };
  }, [isActive]);

  const items = useMemo(() => {
    const ai = cameras.map((c) => ({
      key: `ai:${c.camid}`,
      src: 'ai',
      camid: c.camid,
      name: c.short_title || c.title || c.camid,
      area: [c.province, c.organization].filter(Boolean).join(' · '),
      code: c.camid,
      status: health === null ? 'checking' : health === false ? 'unknown' : health[c.camid] || 'offline',
      lat: c.latitude,
      lng: c.longitude,
      fav: favorites?.has(c.camid),
      text: norm([c.title, c.short_title, c.province, c.organization, c.camid].join(' ')),
    }));
    const city = bma.map((c) => ({
      key: `bma:${c.camid}`,
      src: 'bma',
      camid: c.camid,
      name: c.title || c.short_title || c.camid,
      area: [c.district || 'กทม.', c.road].filter(Boolean).join(' · '),
      code: c.camera_code || c.camid,
      status: c.status === 'online' ? 'online' : 'offline',
      level: c.level,
      total: c.total || 0,
      lat: c.latitude,
      lng: c.longitude,
      cam: c,
      text: norm([c.title, c.short_title, c.road, c.district, c.camera_code, c.camid].join(' ')),
    }));
    return [...ai, ...city];
  }, [cameras, bma, health, favorites]);

  const shown = useMemo(() => {
    const words = q.split(/\s+/).map(norm).filter(Boolean);
    let list = items;
    if (source !== 'all') list = list.filter((it) => it.src === source);
    if (status !== 'all') list = list.filter((it) => it.status === status);
    if (words.length) list = list.filter((it) => words.every((w) => it.text.includes(w)));
    const order = (it) => (it.fav ? 0 : 4) + (it.status === 'offline' ? 2 : 0) + (it.src === 'ai' ? 0 : 1);
    return [...list].sort((a, b) => order(a) - order(b) || a.name.localeCompare(b.name, 'th'));
  }, [items, q, source, status]);

  useEffect(() => setLimit(PAGE), [q, source, status]);

  const sources = [
    ['all', `ทุกกล้อง ${cameras.length + bma.length}`],
    ['ai', `กล้องสด AI ${cameras.length}`],
    ['bma', `กล้อง กทม. ${bma.length}`],
  ];
  const filtered = query || source !== 'all' || status !== 'all';
  const reset = () => {
    setQuery('');
    setSource('all');
    setStatus('all');
  };
  const openItem = (it) => (it.src === 'ai' ? onWatchLive(it.camid) : setOpen(it.cam));

  return (
    <div className="flex flex-col gap-4">
      <Card className="p-4 flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <label htmlFor="camera-search" className="sr-only">
            ค้นหากล้อง
          </label>
          <input
            id="camera-search"
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="ค้นหาชื่อแยก ถนน เขต จังหวัด หรือรหัสกล้อง เช่น พระราม 4, สาทร, 1748"
            className={`flex-1 min-w-[240px] ${INPUT}`}
          />
          {filtered && (
            <Button size="sm" variant="ghost" onClick={reset}>
              ล้างตัวกรอง
            </Button>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Segmented label="แหล่งกล้อง" value={source} onChange={setSource} options={sources} />
          <Segmented label="สถานะสัญญาณ" value={status} onChange={setStatus} options={STATUS} />
          <span className="text-xs text-slate-500 sm:ml-auto" aria-live="polite">
            พบ {shown.length} กล้อง
            {health === null && ' · กำลังเช็คสัญญาณกล้องสด AI...'}
            {bmaState === 'loading' && ' · กำลังโหลดกล้อง กทม....'}
          </span>
        </div>
      </Card>

      {bmaState === 'error' && <ErrorState message="โหลดรายชื่อกล้อง กทม. ไม่สำเร็จ ตอนนี้ค้นได้เฉพาะกล้องสด AI" onRetry={loadBma} />}

      {!shown.length && bmaState === 'loading' ? (
        <Card className="p-4 flex flex-col gap-3">
          {[...Array(6)].map((_, i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </Card>
      ) : !shown.length ? (
        <EmptyState
          title={q ? `ไม่พบกล้องที่ตรงกับ "${q}"` : 'ไม่พบกล้องตามเงื่อนไข'}
          description="ลองพิมพ์ชื่อถนนหรือเขตสั้นลง หรือเปลี่ยนตัวกรอง"
          action={filtered ? <Button size="sm" onClick={reset}>ล้างตัวกรอง</Button> : null}
        />
      ) : (
        <Card as="ul" className="divide-y divide-slate-200 overflow-hidden" aria-label="ผลการค้นหากล้อง">
          {shown.slice(0, limit).map((it) => (
            <ResultRow key={it.key} it={it} onOpen={openItem} />
          ))}
        </Card>
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
