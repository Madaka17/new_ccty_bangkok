import { motion } from 'framer-motion';
import { Card, Badge, Skeleton, ErrorState } from './ui.jsx';
import { STATUS, flowLevel, fmtTime } from './format.js';

// Horizontal HUD meter: gradient track (red -> amber -> green), threshold ticks at the
// flowLevel cut-offs, glowing marker at the current value. Replaces the old ring gauge.
const ZONES = [
  { from: 0, to: 45, label: 'หนาแน่น', key: 'red' },
  { from: 45, to: 75, label: 'ปานกลาง', key: 'yellow' },
  { from: 75, to: 100, label: 'คล่องตัว', key: 'green' },
];

function Meter({ value, colorHex }) {
  const v = Math.min(100, Math.max(0, value ?? 0));
  return (
    <div className="w-full" role="img" aria-label={`ดัชนีการระบายรถ ${value ?? '-'} จาก 100`}>
      <div className="relative h-4 rounded-full bg-slate-100 overflow-visible">
        {/* muted zone gradient under everything */}
        <div
          className="absolute inset-0 rounded-full opacity-40"
          style={{ background: 'linear-gradient(90deg, #dc2626 0%, #dc2626 45%, #d97706 45%, #d97706 75%, #059669 75%, #059669 100%)' }}
        />
        {/* lit portion up to the value */}
        <motion.div
          className="absolute inset-y-0 left-0 rounded-full"
          initial={{ width: 0 }}
          animate={{ width: `${v}%` }}
          transition={{ type: 'spring', stiffness: 60, damping: 18 }}
          style={{ background: `linear-gradient(90deg, ${colorHex}66, ${colorHex})`, boxShadow: `0 0 14px ${colorHex}80` }}
        />
        {/* moving sheen */}
        <motion.div
          className="absolute inset-y-0 w-16 rounded-full pointer-events-none"
          style={{ background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.45), transparent)' }}
          animate={{ left: ['-4rem', '100%'] }}
          transition={{ duration: 2.6, repeat: Infinity, ease: 'linear', repeatDelay: 1.2 }}
        />
        {/* threshold ticks */}
        {[45, 75].map((t) => (
          <span key={t} className="absolute top-[-4px] bottom-[-4px] w-px bg-slate-300" style={{ left: `${t}%` }} aria-hidden="true" />
        ))}
        {/* marker */}
        <motion.div
          className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2"
          initial={{ left: 0 }}
          animate={{ left: `${v}%` }}
          transition={{ type: 'spring', stiffness: 60, damping: 18 }}
          aria-hidden="true"
        >
          <span className="block w-6 h-6 rounded-full border-2 border-white" style={{ background: colorHex, boxShadow: `0 0 0 3px ${colorHex}33, 0 0 18px ${colorHex}` }} />
        </motion.div>
      </div>
      <div className="relative mt-2 h-4 text-[11px] text-slate-500">
        {ZONES.map((z) => (
          <span
            key={z.key}
            className={`absolute top-0 text-center ${v >= z.from && v < (z.to === 100 ? 101 : z.to) ? `${STATUS[z.key].text} font-medium` : ''}`}
            style={{ left: `${z.from}%`, width: `${z.to - z.from}%` }}
          >
            {z.label}
          </span>
        ))}
      </div>
    </div>
  );
}

function Delta({ history }) {
  // Change vs ~1 hour ago (60 samples x 1 min)
  if (!history) return null;
  // BMA history is one point per hour; Longdo history is one point per minute
  const step = history[history.length - 1]?.hourly ? 1 : 60;
  if (history.length <= step) return <p className="text-xs text-slate-500">ยังไม่ครบ 1 ชม. สำหรับเทียบแนวโน้ม</p>;
  const d = history[history.length - 1].flow - history[history.length - 1 - step].flow;
  if (!Number.isFinite(d)) return null;
  if (Math.abs(d) <= 2) return <p className="text-xs text-slate-500">ใกล้เคียงกับ 1 ชม.ก่อน</p>;
  const up = d > 0;
  return (
    <p className={`text-xs font-medium ${up ? 'text-emerald-700' : 'text-red-700'}`}>
      {up ? '▲' : '▼'} {up ? 'ดีขึ้น' : 'ชะลอลง'} {Math.abs(d)} จุด จาก 1 ชม.ก่อน
    </p>
  );
}

export default function FlowOverview({ summary, error, onRetry, retrying }) {
  const level = flowLevel(summary?.flow_index);
  const status = STATUS[level.key];

  return (
    <Card aria-labelledby="flow-title" className="p-5 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="flow-title" className="text-[15px] font-semibold text-slate-900">
          {summary?.is_bma ? 'ภาพรวมการจราจรจากกล้อง CCTV กทม. (BMA)' : 'ภาพรวมการจราจร กรุงเทพฯ และปริมณฑล'}
        </h2>
        {summary ? (
          <Badge tone={summary.online === false ? 'yellow' : 'green'} dot>
            {summary.online === false ? 'ข้อมูลล่าช้า' : 'อัปเดต'} {fmtTime(summary.updated_at)} น.
          </Badge>
        ) : (
          <Skeleton className="h-6 w-28" />
        )}
      </div>

      {error && !summary && (
        <div className="mt-4">
          <ErrorState message="ดึงข้อมูลสภาพจราจรไม่สำเร็จ ตรวจสอบว่า server ทำงานอยู่" onRetry={onRetry} retrying={retrying} />
        </div>
      )}

      <div className="mt-5 grid grid-cols-1 md:grid-cols-[auto_1fr_auto] gap-6 md:gap-8 items-center">
        {/* score */}
        <div className="flex items-end gap-1.5 shrink-0">
          {summary ? (
            <>
              <span className={`text-5xl font-semibold leading-none tabular-nums ${status.text}`} style={{ textShadow: `0 0 24px ${status.hex}66` }}>
                {summary.flow_index ?? '–'}
              </span>
              <span className="text-sm text-slate-500 pb-1">/ 100</span>
            </>
          ) : (
            <Skeleton className="h-12 w-24" />
          )}
        </div>

        {/* meter */}
        <div className="min-w-0">
          <p className="text-xs text-slate-500 mb-3">ดัชนีการระบายรถ</p>
          {summary ? <Meter value={summary.flow_index} colorHex={status.hex} /> : <Skeleton className="h-4 w-full rounded-full" />}
        </div>

        {/* status */}
        <div className="min-w-0 md:max-w-[260px] md:border-l md:border-slate-200 md:pl-6">
          {summary ? (
            <>
              <p className={`text-xl font-semibold leading-7 ${status.text}`}>{level.label}</p>
              <p className="text-[13px] text-slate-600 mt-0.5 leading-5">{level.hint}</p>
              <div className="mt-2">
                <Delta history={summary.history} />
              </div>
            </>
          ) : (
            <div className="space-y-2 mt-1">
              <Skeleton className="h-6 w-28" />
              <Skeleton className="h-4 w-56" />
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}
