import { useState } from 'react';
import { motion } from 'framer-motion';
import { HeartIcon, CheckIcon, SparkleIcon } from './Icons.jsx';
import { PROVINCE_TONE, CAM_LEVEL, camStatusText } from '../lib/store.js';

export default function CameraCard({ cam, status, isActive, isFav, km, onToggleActive, onToggleFav, onOpenAI }) {
  const [imgOk, setImgOk] = useState(true);
  const tone = PROVINCE_TONE[cam.province] || 'bg-cream-200 text-ink-600';
  const level = status?.ts ? CAM_LEVEL[status.level] || CAM_LEVEL.free : null;

  return (
    <div
      className={`group flex items-center gap-3 rounded-3xl border p-2.5 transition-colors duration-200 ${
        isActive ? 'bg-sage-50/90 border-sage-200' : 'bg-white/80 border-cream-200 hover:border-lavender-200'
      }`}
    >
      {/* Big checkbox */}
      <label className="cursor-pointer shrink-0 relative w-8 h-8">
        <input
          type="checkbox"
          checked={isActive}
          onChange={onToggleActive}
          aria-label={`เปิดกล้อง ${cam.short_title}`}
          className="peer sr-only"
        />
        <span
          className={`absolute inset-0 rounded-xl border-2 flex items-center justify-center transition-colors duration-200 ${
            isActive ? 'bg-sage-400 border-sage-400 text-white' : 'bg-white border-cream-200 peer-focus-visible:border-lavender-400'
          }`}
        >
          {isActive && <CheckIcon className="w-5 h-5" />}
        </span>
      </label>

      {/* Softened thumbnail */}
      <button
        type="button"
        onClick={onToggleActive}
        className="cursor-pointer shrink-0 w-[68px] h-[50px] rounded-2xl overflow-hidden bg-lavender-50 border border-white"
        aria-label={`เปิดกล้อง ${cam.short_title}`}
      >
        {imgOk && cam.imgurl ? (
          <img
            src={cam.imgurl}
            alt=""
            loading="lazy"
            onError={() => setImgOk(false)}
            className="w-full h-full object-cover saturate-[.85] opacity-90"
          />
        ) : (
          <div className="w-full h-full bg-gradient-to-br from-lavender-100 to-apricot-100" />
        )}
      </button>

      {/* Text */}
      <button type="button" onClick={onToggleActive} className="cursor-pointer flex-1 min-w-0 text-left">
        <p className="text-sm font-medium text-ink-900 leading-snug line-clamp-2">{cam.short_title || cam.title}</p>
        <div className="mt-1 flex items-center gap-1.5 flex-wrap">
          <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${tone}`}>{cam.province}</span>
          {level ? (
            <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${level.cls}`} title={camStatusText(status)}>
              <span className="w-1.5 h-1.5 rounded-full" style={{ background: level.dot }} />
              {level.text}
            </span>
          ) : (
            <span className="rounded-full px-2 py-0.5 text-[11px] text-ink-400 bg-cream-100" title="AI ยังไม่ได้วัดกล้องนี้">รอ AI วัด</span>
          )}
          {typeof km === 'number' && (
            <span className="text-[11px] text-lavender-700 font-serif">{km < 1 ? `${Math.round(km * 1000)} ม.` : `${km.toFixed(1)} กม.`}</span>
          )}
        </div>
      </button>

      {/* Actions */}
      <div className="shrink-0 flex flex-col gap-1">
        <motion.button
          type="button"
          whileTap={{ scale: 0.85 }}
          onClick={onToggleFav}
          aria-label={isFav ? 'เอาออกจากรายการโปรด' : 'เพิ่มในรายการโปรด'}
          aria-pressed={isFav}
          className="cursor-pointer w-9 h-9 rounded-full flex items-center justify-center hover:bg-apricot-50 transition-colors duration-200"
        >
          <HeartIcon filled={isFav} />
        </motion.button>
        <button
          type="button"
          onClick={onOpenAI}
          aria-label="เปิดผู้ช่วย AI กับกล้องนี้"
          title="ผู้ช่วย AI"
          className="cursor-pointer w-9 h-9 rounded-full flex items-center justify-center opacity-70 group-hover:opacity-100 hover:bg-gold-50 transition-all duration-200"
        >
          <SparkleIcon className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
