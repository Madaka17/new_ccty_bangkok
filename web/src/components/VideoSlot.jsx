import { useEffect, useRef, useState } from 'react';
import Hls from 'hls.js';
import { motion } from 'framer-motion';
import { PROVINCE_TONE, CAM_LEVEL, camStatusText } from '../lib/store.js';
import { getBmaSnapshotUrl } from '../lib/api.js';

const BMA_REFRESH_MS = 3000;
const STILL_REFRESH_MS = 30000;   // other sources' pictures (media "image"); the BMA flood centre takes ~9 s each

// Cameras without video: show the last picture at once, then a fresh one every few seconds. BMA: the scanner's
// frame, then BMA live. The next picture loads off screen and replaces the shown one only when complete, so the
// picture never blanks.
const firstUrl = (cam) => (cam.source === 'bma' ? getBmaSnapshotUrl(cam.bma_id, false, null, false) : cam.imgurl);
const nextUrl = (cam, t) => (cam.source === 'bma'
  ? getBmaSnapshotUrl(cam.bma_id, true, t, false)
  : `${cam.imgurl}${cam.imgurl.includes('?') ? '&' : '?'}t=${t}`);

function Frames({ cam, everyMs, onOffline }) {
 const [src, setSrc] = useState(() => firstUrl(cam));
 const offline = useRef(onOffline);
 offline.current = onOffline;
 useEffect(() => {
 let alive = true;
 let fails = 0;
 let timer;
 const next = () => {
 const img = new Image();
 img.onload = () => {
 if (!alive) return;
 fails = 0;
 setSrc(img.src);
 timer = setTimeout(next, everyMs);
      };
 img.onerror = () => {
 if (!alive) return;
 if (++fails >= 3) offline.current();
 else timer = setTimeout(next, everyMs);
      };
 img.src = nextUrl(cam, Date.now());
    };
 // BMA asks live at once; the others already show their newest picture
 if (cam.source === 'bma') next();
 else timer = setTimeout(next, everyMs);
 return () => {
 alive = false;
 clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cam.source, cam.bma_id, cam.imgurl, everyMs]);
 return (
    <img
 src={src}
 alt=""
 onLoad={(e) => (e.currentTarget.style.visibility = 'visible')}
 onError={(e) => (e.currentTarget.style.visibility = 'hidden')}
 className="absolute inset-0 w-full h-full object-cover"
    />
  );
}

export default function VideoSlot({ cam, status: aiStatus, incident, onClose, onOpenAI }) {
 const videoRef = useRef(null);
 const [status, setStatus] = useState('loading'); // loading | live | offline | frames | mjpeg | embed | link
 const [attempt, setAttempt] = useState(0);

 useEffect(() => {
 const video = videoRef.current;
 if (cam?.source === 'bma' || cam?.media === 'image') {
 setStatus('frames');
 return;
    }
 if (cam?.media === 'iframe' || cam?.media === 'link') {
 setStatus(cam.media === 'iframe' ? 'embed' : 'link');
 return;
    }
 if (video && cam?.video_url) {
 // A webm stream (Koh Samui): the browser plays it as it is
 setStatus('loading');
 const onData = () => setStatus('live');
 const onErr = () => setStatus('offline');
 video.addEventListener('loadeddata', onData);
 video.addEventListener('error', onErr);
 video.src = cam.video_url;
 return () => {
 video.removeEventListener('loadeddata', onData);
 video.removeEventListener('error', onErr);
 video.removeAttribute('src');
 video.load();
      };
    }
 if (!cam?.hls_url && cam?.vdourl) {
 setStatus('mjpeg');
 return;
    }
 if (!video || !cam?.hls_url) {
 setStatus('offline');
 return;
    }
 setStatus('loading');
 let hls;

 if (Hls.isSupported()) {
 hls = new Hls({ enableWorker: true, lowLatencyMode: true, backBufferLength: 30, maxBufferLength: 10, manifestLoadingTimeOut: 8000 });
 hls.loadSource(cam.hls_url);
 hls.attachMedia(video);
 hls.on(Hls.Events.MANIFEST_PARSED, () => {
 video.play().catch(() => {});
 setStatus('live');
      });
 hls.on(Hls.Events.ERROR, (_, data) => {
 if (!data.fatal) return;
 if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
 if (data.details === Hls.ErrorDetails.MANIFEST_LOAD_ERROR || data.details === Hls.ErrorDetails.MANIFEST_LOAD_TIMEOUT) {
 hls.destroy();
 setStatus('offline');
          } else hls.startLoad();
        } else if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
 hls.recoverMediaError();
        } else {
 hls.destroy();
 setStatus('offline');
        }
      });
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
 video.src = cam.hls_url;
 const onMeta = () => {
 video.play().catch(() => {});
 setStatus('live');
      };
 const onErr = () => setStatus('offline');
 video.addEventListener('loadedmetadata', onMeta);
 video.addEventListener('error', onErr);
 return () => {
 video.removeEventListener('loadedmetadata', onMeta);
 video.removeEventListener('error', onErr);
      };
    } else {
 setStatus('offline');
    }

 return () => {
 if (hls) hls.destroy();
    };
  }, [cam?.hls_url, cam?.source, cam?.media, cam?.video_url, attempt]);

 useEffect(() => {
 if (status === 'offline') {
 const timer = setTimeout(() => {
 onClose?.();
      }, 4000);
 return () => clearTimeout(timer);
    }
  }, [status, onClose]);

 const tone = PROVINCE_TONE[cam.province] || 'bg-cream-200 text-ink-600';
 const level = aiStatus?.ts ? CAM_LEVEL[aiStatus.level] || CAM_LEVEL.free : null;

 const fullscreen = () => {
 const el = videoRef.current?.parentElement;
 if (el?.requestFullscreen) el.requestFullscreen();
  };

 return (
    <motion.div
 layout
 initial={{ opacity: 0, scale: 0.96 }}
 animate={{ opacity: 1, scale: 1 }}
 exit={{ opacity: 0, scale: 0.96 }}
 transition={{ duration: 0.25 }}
 className="glass rounded-xl overflow-hidden flex flex-col"
    >
      <div className="px-4 py-2.5 flex items-center gap-2">
        <span className={`rounded-lg px-2 py-0.5 text-[11px] font-medium shrink-0 ${tone}`}>{cam.province}</span>
        <p className="flex-1 min-w-0 truncate text-sm font-medium text-ink-900" title={cam.title}>
          {cam.short_title || cam.title}
        </p>
        {(status === 'live' || status === 'mjpeg') && (
          <span className="hidden sm:inline-flex items-center gap-1 text-[11px] text-sage-700">
            <span className="live-dot w-2 h-2 rounded-full bg-sage-400" />
            สด
          </span>
        )}
        {status === 'frames' && <span className="hidden sm:inline text-[11px] text-slate-500">รูปทุก {(cam.source === 'bma' ? BMA_REFRESH_MS : STILL_REFRESH_MS) / 1000} วิ</span>}
        {onOpenAI && (
          <button type="button" onClick={onOpenAI} title="ให้ AI นับรถจากกล้องนี้" className="cursor-pointer h-7 px-2 rounded-md text-[11px] text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition-colors duration-200">
            AI
          </button>
        )}
        <button type="button" onClick={fullscreen} title="ขยายเต็มจอ" className="cursor-pointer h-7 px-2 rounded-md text-[11px] text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition-colors duration-200">
          เต็มจอ
        </button>
        <button type="button" onClick={onClose} title="ปิดกล้องนี้" className="cursor-pointer h-7 px-2 rounded-md text-[11px] text-slate-600 hover:bg-slate-100 hover:text-red-700 transition-colors duration-200">
          ปิด
        </button>
      </div>

      <div className="relative flex-1 min-h-[180px] bg-cream-100 rounded-lg mx-2 mb-2 overflow-hidden">
        <video ref={videoRef} muted playsInline autoPlay className={`w-full h-full object-cover ${status === 'live' ? '' : 'opacity-0'}`} />
        {status === 'mjpeg' && (
          <img src={`${cam.vdourl}${cam.vdourl.includes('?') ? '&' : '?'}t=${attempt}`} alt="" onError={() => setStatus('offline')} className="absolute inset-0 w-full h-full object-cover" />
        )}
        {status === 'frames' && <Frames cam={cam} everyMs={cam.source === 'bma' ? BMA_REFRESH_MS : STILL_REFRESH_MS} onOffline={() => setStatus('offline')} />}
 {status === 'embed' && (
 <iframe src={cam.embed_url} title={cam.short_title || cam.title} allow="autoplay; fullscreen" className="absolute inset-0 w-full h-full border-0 bg-black" />
        )}
 {status === 'link' && (
 <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-center px-6 bg-slate-50">
 <p className="font-medium text-ink-900">ดูภาพกล้องนี้ได้ที่เว็บ{cam.organization || 'ของเจ้าของกล้อง'}</p>
 <p className="text-xs text-ink-600">เว็บนั้นให้ยืนยันว่าไม่ใช่บอทก่อน จึงเปิดภาพในหน้านี้ไม่ได้ เปิดเว็บแล้วค้นหาชื่อกล้อง "{cam.short_title || cam.title}"</p>
 <a href={cam.page_url} target="_blank" rel="noopener noreferrer" className="mt-1 inline-flex items-center rounded-lg bg-blue-600 text-white px-4 py-2 text-sm font-medium hover:bg-blue-700">
              เปิดเว็บ{cam.organization || ''}
 </a>
 </div>
        )}

        {(status === 'live' || status === 'mjpeg') && (
          <div className="absolute bottom-2 left-2 flex items-center gap-1.5">
            {incident ? (
              <span className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-xs font-semibold bg-red-600 text-white " title={incident.description || ''}>
                {incident.kind === 'breakdown' ? 'รถเสียขวางถนน' : 'อุบัติเหตุ'}
              </span>
            ) : level ? (
              <span className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium  ${level.cls}`} title={camStatusText(aiStatus)}>
                <span className="w-2 h-2 rounded-full" style={{ background: level.dot }} />
                {level.text}
                <span className="opacity-70 font-normal">· {aiStatus.rate_per_min} คัน/นาที</span>
              </span>
            ) : (
              <span className="rounded-lg px-2.5 py-1 text-xs bg-white text-slate-500 border border-slate-200">AI ยังไม่ได้ดู</span>
            )}
          </div>
        )}

        {status === 'loading' && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-ink-600 text-sm">
            <span className="w-8 h-8 rounded-full border-4 border-slate-200 border-t-blue-600 animate-spin" />
            กำลังเปิดภาพให้คุณ...
          </div>
        )}

        {status === 'offline' && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-center px-4 bg-slate-50">
            <p className="font-medium text-ink-900">ไม่มีสัญญาณภาพ</p>
            <p className="text-xs text-ink-600">กล้องนี้ไม่มีภาพ กำลังนำออกจากจอ...</p>
            <div className="flex items-center gap-2 mt-1">
              <button
 type="button"
 onClick={onClose}
 className="cursor-pointer inline-flex items-center gap-1 rounded-lg bg-white text-red-700 border border-slate-300 px-3 py-1.5 text-xs font-medium hover:bg-slate-50 transition-colors duration-200"
              >
                นำออกทันที
              </button>
              <button
 type="button"
 onClick={() => setAttempt((n) => n + 1)}
 className="cursor-pointer inline-flex items-center gap-1 rounded-lg bg-blue-600 text-white border border-blue-600 px-3 py-1.5 text-xs font-medium hover:bg-blue-700 transition-colors duration-200"
              >
                ลองใหม่
              </button>
            </div>
          </div>
        )}
      </div>
    </motion.div>
  );
}
