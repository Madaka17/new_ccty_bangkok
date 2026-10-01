// Live camera page: every camera as a wall, six to a row on a wide screen, under two tabs: iTIC and BMA.
// iTIC tiles play their video while on screen, at most MAX_VIDEOS at once (about 0.5 Mbps each); BMA tiles
// show the BMA scanner's last frame, plain (without its YOLO boxes). A tap opens the camera large, where it
// can be liked or kept open on top.
import { forwardRef, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Hls from 'hls.js';
import VideoSlot from './VideoSlot.jsx';
import ViewSwitch from './ViewSwitch.jsx';
import { Button, Skeleton } from './dashboard/ui.jsx';
import { distanceKm } from '../lib/store.js';
import { fetchBmaScanStatus, getBmaSnapshotUrl } from '../lib/api.js';
import BmaSiteNotice from './bma/BmaSiteNotice.jsx';

const CHIP_OFF = 'bg-white text-slate-700 border-slate-300 hover:bg-slate-50';
const CHIP_ON = 'bg-blue-600 text-white border-blue-600';
const CHIPS = [
  { id: 'all', label: 'ทั้งหมด' },
  { id: 'bkk', label: 'กรุงเทพฯ' },
  { id: 'near', label: 'ใกล้ฉัน' },
  { id: 'fav', label: 'รายการโปรด' },
];
const GRID = 'grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-3';
const MAX_VIDEOS = 18;
const BMA_TILE_REFRESH_MS = 60000;
const TAB_KEY = 'camwall_tab';   // the tab this viewer had open last time

function readTab() {
  try {
    return localStorage.getItem(TAB_KEY) === 'bma' ? 'bma' : 'itic';
  } catch {
    return 'itic';
  }
}

// One IntersectionObserver for all tiles: each tile learns when it comes near the screen and when it leaves
const watchers = new Map();
let observer;
function watch(el, onChange) {
  observer ||= new IntersectionObserver(
    (entries) => entries.forEach((e) => watchers.get(e.target)?.(e.isIntersecting)),
    { rootMargin: '200px 0px' },
  );
  watchers.set(el, onChange);
  observer.observe(el);
  return () => {
    observer.unobserve(el);
    watchers.delete(el);
  };
}

function useOnScreen(ref) {
  const [on, setOn] = useState(false);
  useEffect(() => watch(ref.current, setOn), [ref]);
  return on;
}

// Video slots: a tile on screen asks for one and starts playing when it gets it. The returned function gives
// the slot back (to the next tile waiting) or leaves the queue.
const slots = { used: 0, queue: [] };
function takeSlot(start) {
  let granted = false;
  const grant = () => {
    granted = true;
    slots.used += 1;
    start();
  };
  if (slots.used < MAX_VIDEOS) grant();
  else slots.queue.push(grant);
  return () => {
    const i = slots.queue.indexOf(grant);
    if (i >= 0) slots.queue.splice(i, 1);
    else if (granted) {
      granted = false;
      slots.used -= 1;
      slots.queue.shift()?.();
    }
  };
}

function TileVideo({ cam, onDead }) {
  const ref = useRef(null);
  const dead = useRef(onDead);
  dead.current = onDead;
  useEffect(() => {
    const video = ref.current;
    if (!video || !cam.hls_url) return undefined;
    let hls;
    if (Hls.isSupported()) {
      hls = new Hls({ enableWorker: true, lowLatencyMode: true, maxBufferLength: 6, backBufferLength: 10, manifestLoadingTimeOut: 8000 });
      hls.loadSource(cam.hls_url);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, () => video.play().catch(() => {}));
      hls.on(Hls.Events.ERROR, (_, data) => data.fatal && dead.current());
    } else {
      video.src = cam.hls_url;   // Safari plays HLS by itself
      video.onerror = () => dead.current();
    }
    return () => {
      hls?.destroy();
      video.removeAttribute('src');
      video.load();
    };
  }, [cam.hls_url]);
  if (!cam.hls_url) return <img src={cam.vdourl} alt="" onError={() => dead.current()} className="absolute inset-0 w-full h-full object-cover" />;
  return <video ref={ref} muted playsInline autoPlay className="absolute inset-0 w-full h-full object-cover" />;
}

const TileNote = ({ text }) => <span className="absolute inset-0 flex items-center justify-center text-[11px] text-slate-500">{text}</span>;

const Tile = forwardRef(function Tile({ cam, pinned, onOpen, children }, ref) {
  return (
    <button
      ref={ref}
      type="button"
      onClick={() => onOpen(cam)}
      title={cam.title}
      className={`text-left rounded-xl border bg-white overflow-hidden cursor-pointer transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${
        pinned ? 'border-blue-500 ring-1 ring-blue-500' : 'border-slate-200 hover:border-slate-400'
      }`}
    >
      <div className="relative aspect-video bg-slate-100">
        {children}
        {pinned && <span className="absolute top-1.5 left-1.5 rounded-md bg-blue-600 px-1.5 py-0.5 text-[10px] font-medium text-white">เปิดค้างไว้</span>}
      </div>
      <div className="px-2.5 py-2 min-w-0">
        <p className="text-[13px] font-medium text-slate-900 truncate">{cam.short_title || cam.title}</p>
        <p className="text-[11px] text-slate-500 truncate">
          {cam.province}
          {typeof cam._km === 'number' && ` · ${cam._km < 1 ? `${Math.round(cam._km * 1000)} ม.` : `${cam._km.toFixed(1)} กม.`}`}
        </p>
      </div>
    </button>
  );
});

function IticTile({ cam, pinned, onOpen }) {
  const ref = useRef(null);
  const onScreen = useOnScreen(ref);
  const [playing, setPlaying] = useState(false);
  const [dead, setDead] = useState(false);
  useEffect(() => {
    if (!onScreen || dead) return undefined;
    const release = takeSlot(() => setPlaying(true));
    return () => {
      release();
      setPlaying(false);
    };
  }, [onScreen, dead]);
  const markDead = useCallback(() => setDead(true), []);
  return (
    <Tile ref={ref} cam={cam} pinned={pinned} onOpen={onOpen}>
      {playing && !dead && <TileVideo cam={cam} onDead={markDead} />}
      {dead ? <TileNote text="ไม่มีสัญญาณ" /> : onScreen && !playing && <TileNote text="รอคิวเล่น" />}
    </Tile>
  );
}

function BmaTile({ cam, pinned, onOpen }) {
  const ref = useRef(null);
  const onScreen = useOnScreen(ref);
  const [t, setT] = useState(null);   // null until the tile first comes on screen
  const [missing, setMissing] = useState(false);   // no plain frame kept yet: asked again on the next refresh
  useEffect(() => {
    if (!onScreen) return undefined;
    setT((x) => x ?? 0);
    const id = setInterval(() => {
      setT(Date.now());
      setMissing(false);
    }, BMA_TILE_REFRESH_MS);
    return () => clearInterval(id);
  }, [onScreen]);
  return (
    <Tile ref={ref} cam={cam} pinned={pinned} onOpen={onOpen}>
      {t !== null && !missing && (
        <img src={getBmaSnapshotUrl(cam.bma_id, false, t || null, false)} alt="" onError={() => setMissing(true)} className="absolute inset-0 w-full h-full object-cover" />
      )}
      {missing && <TileNote text="ยังไม่มีรูป" />}
    </Tile>
  );
}

function Section({ id, title, hint, count, loading, children }) {
  return (
    <section aria-labelledby={id} className="flex flex-col gap-3">
      <div>
        <h2 id={id} className="text-[15px] font-semibold text-slate-900">
          {title} <span className="text-sm font-normal text-slate-500">{loading ? '' : `${count} กล้อง`}</span>
        </h2>
        <p className="text-[13px] text-slate-600">{hint}</p>
      </div>
      {loading ? (
        <div className={GRID}>{Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="aspect-video rounded-xl" />)}</div>
      ) : count ? (
        children
      ) : (
        <p className="text-sm text-slate-500 py-4">ไม่มีกล้องที่ตรงกับที่ค้นหา</p>
      )}
    </section>
  );
}

function FocusView({ cam, onClose, camStatus, incidents, pinned, fav, onTogglePin, onToggleFav, onOpenAI }) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  return (
    <div role="dialog" aria-modal="true" aria-label={cam.short_title || cam.title} className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6">
      <button type="button" aria-label="ปิดภาพใหญ่" onClick={onClose} className="absolute inset-0 bg-slate-900/70 cursor-pointer" />
      <div className="relative w-full max-w-4xl flex flex-col gap-2">
        <div className="grid h-[60vh] sm:h-[70vh]">
          <VideoSlot
            cam={cam}
            status={camStatus[cam.camid]}
            incident={(incidents?.camera || []).find((i) => i.camid === cam.camid)}
            onClose={onClose}
            onOpenAI={onOpenAI}
          />
        </div>
        <div className="flex flex-wrap justify-end gap-2">
          <Button size="sm" onClick={onToggleFav}>{fav ? 'เอาออกจากรายการโปรด' : 'เพิ่มในรายการโปรด'}</Button>
          <Button size="sm" variant={pinned ? 'secondary' : 'primary'} onClick={onTogglePin}>
            {pinned ? 'เลิกเปิดค้างไว้' : 'เปิดค้างไว้ด้านบน'}
          </Button>
        </div>
      </div>
    </div>
  );
}

export default function CameraWall({
  cameras,
  loading,
  camStatus = {},
  incidents,
  favorites,
  active,
  filter,
  onFilter,
  query,
  onQuery,
  userPos,
  onToggleActive,
  onToggleFav,
  onOpenAI,
  aiIds,
}) {
  const [focus, setFocus] = useState(null);
  const [tab, setTab] = useState(readTab);
  const [site, setSite] = useState(null);   // is the BMA camera site sending pictures (scan_status.source)
  useEffect(() => {
    if (tab !== 'bma') return undefined;
    const load = () => fetchBmaScanStatus().then((s) => setSite(s.source)).catch(() => {});
    load();
    const id = setInterval(load, BMA_TILE_REFRESH_MS);
    return () => clearInterval(id);
  }, [tab]);
  const pickTab = (id) => {
    setTab(id);
    try {
      localStorage.setItem(TAB_KEY, id);
    } catch {}
  };
  const list = useMemo(() => {
    let out = cameras;
    if (filter === 'bkk') out = out.filter((c) => c.province === 'กรุงเทพมหานคร');
    if (filter === 'fav') out = out.filter((c) => favorites.has(c.camid));
    if (query.trim()) {
      const q = query.trim().toLowerCase();
      out = out.filter((c) => `${c.title} ${c.short_title} ${c.province} ${c.camid}`.toLowerCase().includes(q));
    }
    if (filter === 'near' && userPos) {
      out = out
        .filter((c) => c.latitude && c.longitude)
        .map((c) => ({ ...c, _km: distanceKm(userPos, { lat: c.latitude, lng: c.longitude }) }))
        .sort((a, b) => a._km - b._km);
    }
    return out;
  }, [cameras, favorites, filter, query, userPos]);
  const itic = useMemo(() => list.filter((c) => c.source !== 'bma'), [list]);
  const bma = useMemo(() => list.filter((c) => c.source === 'bma'), [list]);
  const pinned = useMemo(() => new Set(active), [active]);
  const close = useCallback(() => setFocus(null), []);

  const tabs = [
    { id: 'itic', label: loading ? 'กล้อง iTIC' : `กล้อง iTIC ${itic.length} ตัว`, icon: 'cameras', hint: 'วิดีโอสดจาก iTIC และกรมทางหลวง' },
    { id: 'bma', label: loading ? 'กล้อง กทม.' : `กล้อง กทม. ${bma.length} ตัว`, icon: 'report', hint: 'รูปจากกล้องจราจรของ กทม.' },
  ];

  return (
    <div className="flex flex-col gap-4">
      <ViewSwitch tabs={tabs} value={tab} onChange={pickTab} label="กลุ่มกล้อง" />
      <div className="glass rounded-xl p-4 flex flex-col gap-3">
        <label htmlFor="cam-search" className="sr-only">ค้นหาถนนหรือแยก</label>
        <input
          id="cam-search"
          type="search"
          value={query}
          onChange={(e) => onQuery(e.target.value)}
          placeholder="ค้นหาถนนหรือแยก..."
          className="w-full rounded-lg bg-white border border-slate-300 px-4 py-2.5 text-base text-ink-900 placeholder:text-ink-400 outline-none focus:border-blue-500"
        />
        <div className="flex flex-wrap items-center gap-2">
          {CHIPS.map((chip) => (
            <button
              key={chip.id}
              type="button"
              onClick={() => onFilter(chip.id)}
              aria-pressed={filter === chip.id}
              className={`cursor-pointer inline-flex items-center gap-1.5 rounded-lg border px-3 h-8 text-xs font-medium transition-colors duration-200 ${filter === chip.id ? CHIP_ON : CHIP_OFF}`}
            >
              {chip.label}
              {chip.id === 'fav' && favorites.size > 0 && <span className="rounded-lg bg-white px-1.5 text-xs text-ink-900">{favorites.size}</span>}
            </button>
          ))}
          <span className="ml-auto text-xs text-slate-600">
            {loading ? 'กำลังโหลดรายชื่อกล้อง...' : `พบ ${(tab === 'bma' ? bma : itic).length} กล้อง`}
            {filter === 'near' && !userPos && ' (กำลังหาตำแหน่งของคุณ...)'}
          </span>
        </div>
      </div>

      {/* only the open tab is on the page: the other one plays and loads nothing */}
      {tab === 'itic' ? (
        <Section id="wall-itic" title="กล้อง iTIC" count={itic.length} loading={loading}
          hint={`วิดีโอสด เล่นพร้อมกันได้ ${MAX_VIDEOS} ช่อง ช่องที่เลื่อนพ้นจอจะหยุดเอง แตะเพื่อดูภาพใหญ่`}>
          <div className={GRID}>
            {itic.map((cam) => <IticTile key={cam.camid} cam={cam} pinned={pinned.has(cam.camid)} onOpen={setFocus} />)}
          </div>
        </Section>
      ) : (
        <Section id="wall-bma" title="กล้อง กทม." count={bma.length} loading={loading}
          hint="รูปล่าสุดจากกล้อง กทม. อัปเดตทุก 1 นาที แตะเพื่อดูรูปใหม่ทุก 3 วินาที">
          <BmaSiteNotice source={site} />
          <div className={GRID}>
            {bma.map((cam) => <BmaTile key={cam.camid} cam={cam} pinned={pinned.has(cam.camid)} onOpen={setFocus} />)}
          </div>
        </Section>
      )}

      {focus && (
        <FocusView
          cam={focus}
          onClose={close}
          camStatus={camStatus}
          incidents={incidents}
          pinned={pinned.has(focus.camid)}
          fav={favorites.has(focus.camid)}
          onTogglePin={() => onToggleActive(focus.camid)}
          onToggleFav={() => onToggleFav(focus.camid)}
          onOpenAI={!aiIds || aiIds.has(focus.camid) ? () => onOpenAI(focus.camid) : null}
        />
      )}
    </div>
  );
}
