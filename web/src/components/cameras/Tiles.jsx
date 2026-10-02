// Camera tiles for the live camera page and the camera map page. Video tiles play while on screen, at most
// MAX_VIDEOS at once (about 0.5 Mbps each); picture tiles refresh while on screen; the rest show a note. `flood`
// is the AI's flood label for the camera, shown as a badge.
import { forwardRef, useCallback, useEffect, useRef, useState } from 'react';
import Hls from 'hls.js';
import { getBmaSnapshotUrl } from '../../lib/api.js';

export const MAX_VIDEOS = 18;
const BMA_TILE_REFRESH_MS = 60000;
const IMAGE_TILE_REFRESH_MS = 120000;   // other sources' pictures: the BMA flood centre's take ~9 s each
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
    if (video && cam.video_url) {
      video.src = cam.video_url;
      video.onerror = () => dead.current();
      return () => {
        video.removeAttribute('src');
        video.load();
      };
    }
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
  }, [cam.hls_url, cam.video_url]);
  if (!cam.hls_url && !cam.video_url) return <img src={cam.vdourl} alt="" onError={() => dead.current()} className="absolute inset-0 w-full h-full object-cover" />;
  return <video ref={ref} muted playsInline autoPlay className="absolute inset-0 w-full h-full object-cover" />;
}

const TileNote = ({ text }) => <span className="absolute inset-0 flex items-center justify-center text-[11px] text-slate-500">{text}</span>;

const Tile = forwardRef(function Tile({ cam, pinned, flood, onOpen, children }, ref) {
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
        {flood && <span className="absolute top-1.5 right-1.5 rounded-md bg-pink-600 px-1.5 py-0.5 text-[10px] font-medium text-white" title="AI เห็นน้ำบนถนนจากภาพกล้องนี้">{flood}</span>}
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

function IticTile({ cam, pinned, flood, onOpen }) {
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
    <Tile ref={ref} cam={cam} pinned={pinned} flood={flood} onOpen={onOpen}>
      {playing && !dead && <TileVideo cam={cam} onDead={markDead} />}
      {dead ? <TileNote text="ไม่มีสัญญาณ" /> : onScreen && !playing && <TileNote text="รอคิวเล่น" />}
    </Tile>
  );
}

// A refreshed picture: the BMA scanner's last frame, or another source's JPEG (media "image")
const stillUrl = (cam, t) => (cam.source === 'bma'
  ? getBmaSnapshotUrl(cam.bma_id, false, t || null, false)
  : t ? `${cam.imgurl}${cam.imgurl.includes('?') ? '&' : '?'}t=${t}` : cam.imgurl);

function StillTile({ cam, pinned, flood, onOpen }) {
  const ref = useRef(null);
  const onScreen = useOnScreen(ref);
  const [t, setT] = useState(null);   // null until the tile first comes on screen
  const [missing, setMissing] = useState(false);   // no picture: asked again on the next refresh
  useEffect(() => {
    if (!onScreen) return undefined;
    setT((x) => x ?? 0);
    const id = setInterval(() => {
      setT(Date.now());
      setMissing(false);
    }, cam.source === 'bma' ? BMA_TILE_REFRESH_MS : IMAGE_TILE_REFRESH_MS);
    return () => clearInterval(id);
  }, [onScreen, cam.source]);
  return (
    <Tile ref={ref} cam={cam} pinned={pinned} flood={flood} onOpen={onOpen}>
      {t !== null && !missing && (
        <img src={stillUrl(cam, t)} alt="" onError={() => setMissing(true)} className="absolute inset-0 w-full h-full object-cover" />
      )}
      {missing && <TileNote text="ยังไม่มีรูป" />}
    </Tile>
  );
}

// No preview on the wall: the source's own player (media "iframe") or Pattaya's site (media "link")
function OpenTile({ cam, pinned, flood, onOpen }) {
  return (
    <Tile cam={cam} pinned={pinned} flood={flood} onOpen={onOpen}>
      <TileNote text={cam.media === 'link' ? 'แตะเพื่อไปดูที่เว็บเมืองพัทยา' : 'แตะเพื่อดูภาพสด'} />
    </Tile>
  );
}

export default function CamTile(props) {
  const { cam } = props;
  if (cam.source === 'bma' || cam.media === 'image') return <StillTile {...props} />;
  if (cam.media === 'iframe' || cam.media === 'link') return <OpenTile {...props} />;
  return <IticTile {...props} />;
}

