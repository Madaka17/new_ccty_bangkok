import { useEffect, useRef, useState } from 'react';
import Hls from 'hls.js';
import { motion } from 'framer-motion';
import { OfflineIllustration, CloseIcon, RefreshIcon, ExpandIcon, SparkleIcon } from './Icons.jsx';
import { PROVINCE_TONE, CAM_LEVEL, camStatusText } from '../lib/store.js';

export default function VideoSlot({ cam, status: aiStatus, incident, onClose, onOpenAI }) {
 const videoRef = useRef(null);
 const [status, setStatus] = useState('loading'); // loading | live | offline
 const [attempt, setAttempt] = useState(0);

 useEffect(() => {
 const video = videoRef.current;
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
  }, [cam?.hls_url, attempt]);

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
        <button type="button" onClick={onOpenAI} title="ผู้ช่วย AI" aria-label="เปิดผู้ช่วย AI กับกล้องนี้" className="cursor-pointer w-8 h-8 rounded-full flex items-center justify-center hover:bg-slate-100 transition-colors duration-200">
          <SparkleIcon className="w-4 h-4" />
        </button>
        <button type="button" onClick={fullscreen} title="ขยายเต็มจอ" aria-label="ขยายเต็มจอ" className="cursor-pointer w-8 h-8 rounded-full flex items-center justify-center text-ink-600 hover:bg-lavender-50 transition-colors duration-200">
          <ExpandIcon />
        </button>
        <button type="button" onClick={onClose} title="ปิดกล้องนี้" aria-label="ปิดกล้องนี้" className="cursor-pointer w-8 h-8 rounded-full flex items-center justify-center text-ink-600 hover:bg-slate-100 hover:text-red-700 transition-colors duration-200">
          <CloseIcon className="w-4 h-4" />
        </button>
      </div>

      <div className="relative flex-1 min-h-[180px] bg-cream-100 rounded-lg mx-2 mb-2 overflow-hidden">
        <video ref={videoRef} muted playsInline autoPlay className={`w-full h-full object-cover ${status === 'live' ? '' : 'opacity-0'}`} />
        {status === 'mjpeg' && (
          <img src={`${cam.vdourl}${cam.vdourl.includes('?') ? '&' : '?'}t=${attempt}`} alt="" onError={() => setStatus('offline')} className="absolute inset-0 w-full h-full object-cover" />
        )}

        {(status === 'live' || status === 'mjpeg') && (
          <div className="absolute bottom-2 left-2 flex items-center gap-1.5">
            {incident ? (
              <span className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-xs font-semibold bg-red-600 text-white " title={incident.description || ''}>
                {incident.kind === 'breakdown' ? 'รถเสียกีดขวาง' : 'อุบัติเหตุ'}
              </span>
            ) : level ? (
              <span className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium  ${level.cls}`} title={camStatusText(aiStatus)}>
                <span className="w-2 h-2 rounded-full" style={{ background: level.dot }} />
                {level.text}
                <span className="opacity-70 font-normal">· {aiStatus.rate_per_min} คัน/นาที</span>
              </span>
            ) : (
              <span className="rounded-lg px-2.5 py-1 text-xs bg-white text-slate-500 border border-slate-200">รอ AI วัด</span>
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
            <OfflineIllustration />
            <p className="font-medium text-ink-900">ไม่มีสัญญาณภาพ</p>
            <p className="text-xs text-ink-600">กล้องออฟไลน์ กำลังนำออกจากจอ...</p>
            <div className="flex items-center gap-2 mt-1">
              <button
 type="button"
 onClick={onClose}
 className="cursor-pointer inline-flex items-center gap-1 rounded-lg bg-white text-red-700 border border-slate-300 px-3 py-1.5 text-xs font-medium hover:bg-slate-50 transition-colors duration-200"
              >
                <CloseIcon className="w-3.5 h-3.5" />
                นำออกทันที
              </button>
              <button
 type="button"
 onClick={() => setAttempt((n) => n + 1)}
 className="cursor-pointer inline-flex items-center gap-1 rounded-lg bg-blue-600 text-white border border-blue-600 px-3 py-1.5 text-xs font-medium hover:bg-blue-700 transition-colors duration-200"
              >
                <RefreshIcon className="w-3 h-3" />
                ลองใหม่
              </button>
            </div>
          </div>
        )}
      </div>
    </motion.div>
  );
}
