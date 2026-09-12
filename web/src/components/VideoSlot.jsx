import { useEffect, useRef, useState } from 'react';
import Hls from 'hls.js';
import { motion } from 'framer-motion';
import { OfflineIllustration, CloseIcon, RefreshIcon, ExpandIcon, SparkleIcon } from './Icons.jsx';
import { PROVINCE_TONE } from '../lib/store.js';

export default function VideoSlot({ cam, onClose, onOpenAI }) {
  const videoRef = useRef(null);
  const [status, setStatus] = useState('loading'); // loading | live | offline
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const video = videoRef.current;
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

  const tone = PROVINCE_TONE[cam.province] || 'bg-cream-200 text-ink-600';

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
      className="glass rounded-[1.75rem] overflow-hidden flex flex-col"
    >
      <div className="px-4 py-2.5 flex items-center gap-2">
        <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium shrink-0 ${tone}`}>{cam.province}</span>
        <p className="flex-1 min-w-0 truncate text-sm font-medium text-ink-900" title={cam.title}>
          {cam.short_title || cam.title}
        </p>
        {status === 'live' && (
          <span className="hidden sm:inline-flex items-center gap-1 text-[11px] text-sage-700">
            <span className="live-dot w-2 h-2 rounded-full bg-sage-400" />
            สด
          </span>
        )}
        <button type="button" onClick={onOpenAI} title="ผู้ช่วย AI" aria-label="เปิดผู้ช่วย AI กับกล้องนี้" className="cursor-pointer w-8 h-8 rounded-full flex items-center justify-center hover:bg-gold-50 transition-colors duration-200">
          <SparkleIcon className="w-4 h-4" />
        </button>
        <button type="button" onClick={fullscreen} title="ขยายเต็มจอ" aria-label="ขยายเต็มจอ" className="cursor-pointer w-8 h-8 rounded-full flex items-center justify-center text-ink-600 hover:bg-lavender-50 transition-colors duration-200">
          <ExpandIcon />
        </button>
        <button type="button" onClick={onClose} title="ปิดกล้องนี้" aria-label="ปิดกล้องนี้" className="cursor-pointer w-8 h-8 rounded-full flex items-center justify-center text-ink-600 hover:bg-apricot-50 hover:text-apricot-700 transition-colors duration-200">
          <CloseIcon className="w-4 h-4" />
        </button>
      </div>

      <div className="relative flex-1 min-h-[180px] bg-cream-100 rounded-[1.5rem] mx-2 mb-2 overflow-hidden">
        <video ref={videoRef} muted playsInline autoPlay className={`w-full h-full object-cover ${status === 'live' ? '' : 'opacity-0'}`} />

        {status === 'loading' && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-ink-600 text-sm">
            <span className="w-8 h-8 rounded-full border-4 border-lavender-100 border-t-lavender-400 animate-spin" />
            กำลังเปิดภาพให้คุณ...
          </div>
        )}

        {status === 'offline' && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-center px-4 bg-gradient-to-b from-cream to-lavender-50">
            <OfflineIllustration />
            <p className="font-medium text-ink-900">กล้องขอพักสักครู่นะ</p>
            <p className="text-xs text-ink-600">สัญญาณยังไม่มา ลองใหม่ได้ทุกเมื่อ</p>
            <motion.button
              type="button"
              whileTap={{ scale: 0.96 }}
              onClick={() => setAttempt((n) => n + 1)}
              className="cursor-pointer mt-1 inline-flex items-center gap-1.5 rounded-full bg-lavender-100 text-lavender-700 border border-lavender-200 px-4 py-2 text-sm font-medium hover:bg-lavender-200 transition-colors duration-200"
            >
              <RefreshIcon />
              ลองอีกครั้ง
            </motion.button>
          </div>
        )}
      </div>
    </motion.div>
  );
}
