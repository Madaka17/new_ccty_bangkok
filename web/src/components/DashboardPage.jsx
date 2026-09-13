import { useEffect, useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  CarIcon,
  BikeIcon,
  TruckIcon,
  CameraIcon,
  MapPinIcon,
  SparkleIcon,
  RefreshIcon,
  CheckIcon,
  CloseIcon,
  StarIcon,
} from './Icons.jsx';
import {
  fetchAIHistory,
  fetchAIStats,
  fetchCountCameras,
  fetchSurveyRanking,
  fetchTrafficSummary,
  setCountCameras,
} from '../lib/api.js';

// Status palette (CVD-safe, high-contrast, modern tones)
const STATUS = { green: '#38a169', yellow: '#d69e2e', red: '#e53e3e' };
const LEVEL_CLS = {
  โล่ง: 'bg-emerald-50 text-emerald-700 border border-emerald-200/60',
  ปานกลาง: 'bg-amber-50 text-amber-700 border border-amber-200/60',
  ติดขัด: 'bg-rose-50 text-rose-700 border border-rose-200/60',
};

// UI icons
function TrendingUpIcon({ className = 'w-4 h-4' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="23 6 13.5 15.5 8.5 10.5 1 18" />
      <polyline points="17 6 23 6 23 12" />
    </svg>
  );
}

function TrendingDownIcon({ className = 'w-4 h-4' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="23 18 13.5 8.5 8.5 13.5 1 6" />
      <polyline points="17 18 23 18 23 12" />
    </svg>
  );
}

function ActivityIcon({ className = 'w-4 h-4' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  );
}

function ShieldAlertIcon({ className = 'w-5 h-5' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      <line x1="12" y1="8" x2="12" y2="12" />
      <line x1="12" y1="16" x2="12.01" y2="16" />
    </svg>
  );
}

function ArrowRightIcon({ className = 'w-3.5 h-3.5' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="5" y1="12" x2="19" y2="12" />
      <polyline points="12 5 19 12 12 19" />
    </svg>
  );
}

function levelOf(flow) {
  if (flow == null)
    return {
      text: 'กำลังโหลดข้อมูล',
      cls: 'bg-cream-200 text-ink-600',
      hint: 'รอสัญญาณประมวลผลเส้นทางจราจรสักครู่',
      color: '#8a72c4',
      bgGlow: 'rgba(138, 114, 196, 0.12)',
      badgeCls: 'bg-lavender-50 text-lavender-700 border border-lavender-200',
    };
  if (flow >= 75)
    return {
      text: 'ถนนโล่งสบายมาก',
      cls: 'bg-emerald-50 text-emerald-700',
      hint: 'การจราจรไหลลื่น เดินทางได้สะดวกตามปกติ',
      color: '#38a169',
      bgGlow: 'rgba(56, 161, 105, 0.14)',
      badgeCls: 'bg-emerald-50 text-emerald-700 border border-emerald-200',
    };
  if (flow >= 45)
    return {
      text: 'การจราจรปานกลาง',
      cls: 'bg-amber-50 text-amber-700',
      hint: 'รถเคลื่อนตัวได้เรื่อย ๆ มีจุดชะลอตัวบางช่วง เผื่อเวลาเดินทาง',
      color: '#d69e2e',
      bgGlow: 'rgba(214, 158, 46, 0.14)',
      badgeCls: 'bg-amber-50 text-amber-700 border border-amber-200',
    };
  return {
    text: 'การจราจรหนาแน่น',
    cls: 'bg-rose-50 text-rose-700',
    hint: 'มีรถสะสมและติดขัดหลายจุด แนะนำตรวจสอบเส้นทางเลี่ยง',
    color: '#e53e3e',
    bgGlow: 'rgba(229, 62, 62, 0.14)',
    badgeCls: 'bg-rose-50 text-rose-700 border border-rose-200',
  };
}

// Circular Radial Progress Gauge
function RadialFlowGauge({ flow = 0, color = '#38a169', label = 'ดัชนีการระบายรถ' }) {
  const size = 136;
  const strokeWidth = 10;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const validFlow = Math.min(100, Math.max(0, flow || 0));
  const offset = circumference - (validFlow / 100) * circumference;

  return (
    <div className="relative flex flex-col items-center justify-center shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="transform -rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#efeae4"
          strokeWidth={strokeWidth}
          className="opacity-70"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          className="transition-all duration-1000 ease-out"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
        <span className="font-serif text-4xl sm:text-[2.6rem] font-bold text-ink-900 leading-none tabular-nums tracking-tight">
          {flow ?? '–'}
        </span>
        <span className="text-[10px] font-medium text-ink-400 mt-1 uppercase tracking-wider">/ 100 FLOW</span>
      </div>
    </div>
  );
}

// StackBar with modern pill design & badges
function StackBar({ green = 0, yellow = 0, red = 0 }) {
  const segs = [
    { key: 'green', val: green, label: 'โล่ง', color: STATUS.green, bg: 'bg-emerald-50', text: 'text-emerald-700' },
    { key: 'yellow', val: yellow, label: 'ปานกลาง', color: STATUS.yellow, bg: 'bg-amber-50', text: 'text-amber-700' },
    { key: 'red', val: red, label: 'ติดขัด', color: STATUS.red, bg: 'bg-rose-50', text: 'text-rose-700' },
  ];

  return (
    <div className="w-full">
      <div
        className="flex h-3.5 w-full rounded-full overflow-hidden bg-cream-200/80 p-0.5 gap-1 shadow-inner"
        role="img"
        aria-label={`โล่ง ${green}% ปานกลาง ${yellow}% ติดขัด ${red}%`}
      >
        {segs
          .filter((s) => s.val > 0)
          .map((s) => (
            <div
              key={s.key}
              style={{ width: `${s.val}%`, backgroundColor: s.color }}
              className="h-full rounded-full transition-all duration-700 first:rounded-l-full last:rounded-r-full shadow-xs"
            />
          ))}
      </div>
      <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2 text-xs">
        {segs.map((s) => (
          <div
            key={s.key}
            className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full ${s.bg} ${s.text} font-medium border border-black/5`}
          >
            <span className="w-2 h-2 rounded-full shrink-0 shadow-xs" style={{ backgroundColor: s.color }} />
            <span>{s.label}</span>
            <span className="font-serif font-bold text-sm leading-none tabular-nums">{s.val}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// 24-Hour Trend Sparkline with high-res curves and interactive tooltips
function Sparkline({ history }) {
  const [hover, setHover] = useState(null);
  const W = 620;
  const H = 140;
  const pad = { l: 32, r: 16, t: 16, b: 24 };

  const pts = useMemo(() => {
    if (!history?.length) return [];
    const n = history.length;
    return history.map((h, i) => ({
      x: pad.l + ((W - pad.l - pad.r) * i) / Math.max(1, n - 1),
      y: pad.t + (H - pad.t - pad.b) * (1 - (h.flow || 0) / 100),
      flow: h.flow,
      t: new Date(h.t * 1000),
    }));
  }, [history]);

  if (pts.length < 2)
    return (
      <div className="py-8 text-center text-sm text-ink-400 bg-cream-100/50 rounded-2xl border border-dashed border-cream-200">
        ยังไม่มีข้อมูลย้อนหลังเพียงพอ ระบบจะเก็บและบันทึกข้อมูลทุก ๆ 3 นาที
      </div>
    );

  const d = pts.map((p, i) => `${i ? 'L' : 'M'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
  const area = `${d} L${pts[pts.length - 1].x},${H - pad.b} L${pts[0].x},${H - pad.b} Z`;

  const onMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * W;
    let best = pts[0];
    for (const p of pts) if (Math.abs(p.x - x) < Math.abs(best.x - x)) best = p;
    setHover(best);
  };

  const fmt = (t) => t.toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' });

  return (
    <div className="relative select-none">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full h-auto"
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
        role="img"
        aria-label="กราฟแนวโน้มการระบายรถ 24 ชั่วโมง"
      >
        <defs>
          <linearGradient id="trendGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#8a72c4" stopOpacity="0.4" />
            <stop offset="100%" stopColor="#8a72c4" stopOpacity="0.0" />
          </linearGradient>
        </defs>

        {/* Grid lines */}
        {[0, 50, 100].map((v) => {
          const y = pad.t + (H - pad.t - pad.b) * (1 - v / 100);
          return (
            <g key={v}>
              <line x1={pad.l} x2={W - pad.r} y1={y} y2={y} stroke="#efeae4" strokeWidth="1" strokeDasharray="3 3" />
              <text x={pad.l - 8} y={y + 3.5} textAnchor="end" fontSize="10" fill="#9a94a1" fontFamily="sans-serif">
                {v}
              </text>
            </g>
          );
        })}

        {/* Area & curve */}
        <path d={area} fill="url(#trendGradient)" />
        <path d={d} fill="none" stroke="#8a72c4" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />

        {/* Start / End time */}
        <text x={pad.l} y={H - 6} fontSize="10" fill="#9a94a1" fontWeight="500">
          {fmt(pts[0].t)}
        </text>
        <text x={W - pad.r} y={H - 6} fontSize="10" fill="#9a94a1" fontWeight="500" textAnchor="end">
          {fmt(pts[pts.length - 1].t)}
        </text>

        {/* Interactive hover crosshair & dot */}
        {hover && (
          <g>
            <line x1={hover.x} x2={hover.x} y1={pad.t} y2={H - pad.b} stroke="#8a72c4" strokeWidth="1.5" strokeDasharray="4 4" />
            <circle cx={hover.x} cy={hover.y} r="6" fill="#8a72c4" stroke="#ffffff" strokeWidth="2.5" />
          </g>
        )}
      </svg>

      {hover && (
        <div
          className="absolute top-1 left-1/2 -translate-x-1/2 glass-strong rounded-full px-4 py-1.5 text-xs text-ink-900 pointer-events-none shadow-md border border-lavender-200/80 flex items-center gap-2"
        >
          <span className="w-2 h-2 rounded-full bg-lavender-600 animate-ping" />
          <span>เวลา <b>{fmt(hover.t)} น.</b></span>
          <span className="text-ink-400">·</span>
          <span>ดัชนีระบายรถ: <span className="font-serif font-bold text-lavender-700">{hover.flow}</span>/100</span>
        </div>
      )}
    </div>
  );
}

// Enhanced Road Row with rank medals, mini progress meter, and ask AI chip
function RoadRow({ r, rank, onOpen, type = 'congested' }) {
  const isTop3 = rank <= 3;
  const medalClass =
    rank === 1
      ? 'bg-gradient-to-br from-amber-300 to-amber-500 text-amber-950 font-bold shadow-xs'
      : rank === 2
      ? 'bg-gradient-to-br from-slate-200 to-slate-400 text-slate-900 font-bold shadow-xs'
      : rank === 3
      ? 'bg-gradient-to-br from-orange-300 to-orange-400 text-orange-950 font-bold shadow-xs'
      : 'bg-cream-100 text-ink-600 font-medium';

  return (
    <li className="group">
      <button
        type="button"
        onClick={() => onOpen(r.name)}
        title={`แตะเพื่อเปิดกล้องบน ${r.name}`}
        className="cursor-pointer w-full text-left rounded-2xl p-2.5 sm:px-3 sm:py-3 hover:bg-white/90 hover:shadow-soft border border-transparent hover:border-cream-200/80 transition-all duration-200 flex items-center gap-3"
      >
        {/* Rank Medal */}
        <span className={`w-7 h-7 rounded-xl flex items-center justify-center text-xs font-serif shrink-0 ${medalClass}`}>
          {rank}
        </span>

        {/* Road Info & Mini Visual Ratio */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm sm:text-[15px] font-medium text-ink-900 line-clamp-1 group-hover:text-lavender-700 transition-colors">
              {r.name}
            </span>
            <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-[11px] font-medium ${LEVEL_CLS[r.level] || 'bg-cream-100 text-ink-600'}`}>
              {r.level}
            </span>
          </div>

          <div className="mt-1 flex items-center gap-3">
            {/* Visual Mini Progress Bar */}
            <div className="w-20 sm:w-28 h-1.5 rounded-full overflow-hidden bg-cream-200/80 flex shrink-0">
              {r.green_pct > 0 && <div style={{ width: `${r.green_pct}%` }} className="bg-emerald-500 h-full" />}
              {r.yellow_pct > 0 && <div style={{ width: `${r.yellow_pct}%` }} className="bg-amber-400 h-full" />}
              {r.red_pct > 0 && <div style={{ width: `${r.red_pct}%` }} className="bg-rose-500 h-full" />}
            </div>

            <span className="text-xs text-ink-600 line-clamp-1">
              {type === 'congested' ? (
                <>
                  ติด <span className="font-semibold text-rose-700">{r.red_km}</span> กม. (จาก {r.length_km} กม.)
                </>
              ) : (
                <>
                  ระบาย <span className="font-semibold text-emerald-700">{r.flow}</span>/100 · โล่ง {r.green_pct}%
                </>
              )}
            </span>
          </div>
        </div>

        {/* Hover hint: opens the cameras on this road */}
        <span className="opacity-0 group-hover:opacity-100 transition-opacity duration-200 shrink-0 inline-flex items-center gap-1 rounded-full bg-lavender-100/90 text-lavender-800 text-[11px] px-2.5 py-1 font-medium shadow-xs">
          <CameraIcon className="w-3 h-3" />
          เปิดกล้อง
        </span>
      </button>
    </li>
  );
}

const RANGES = [
  ['24h', '24 ชม.'],
  ['7d', '7 วัน'],
  ['30d', '30 วัน'],
];
const pad2 = (v) => String(v).padStart(2, '0');
const THAI_MONTHS = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.'];
const fmtDay = (key) => {
  const d = new Date(key);
  return `${d.getDate()} ${THAI_MONTHS[d.getMonth()]}`;
};
const bucketLabel = (bucket, key) => (bucket === 'hour' ? `${pad2(new Date(key).getHours())}:00` : fmtDay(key));
const bucketTitle = (bucket, key) => {
  if (bucket === 'day') return fmtDay(key);
  const h = new Date(key).getHours();
  return `${pad2(h)}:00 - ${pad2((h + 1) % 24)}:00 น.`;
};

// Sleek bar chart for hourly vehicle counts
function CountBars({ bucket, keys, series, onPickDay }) {
  const [hover, setHover] = useState(null);
  const vals = keys.map((k) => series[k]?.total || 0);
  const max = Math.max(1, ...vals);
  const W = 560;
  const H = 110;
  const pad = { l: 8, r: 8, t: 16, b: 20 };
  const gap = 3;
  const bw = (W - pad.l - pad.r) / Math.max(1, keys.length);
  const peakIdx = vals.indexOf(Math.max(...vals));
  const shownIdx = hover ?? (vals[peakIdx] > 0 ? peakIdx : null);
  const labelEvery = bucket === 'hour' ? 6 : keys.length > 10 ? 5 : 1;
  const clickable = bucket === 'day' && onPickDay;

  return (
    <div className="relative select-none">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className={`w-full h-auto ${clickable ? 'cursor-pointer' : ''}`}
        onMouseLeave={() => setHover(null)}
        role="img"
        aria-label="จำนวนรถที่ผ่านกล้อง"
      >
        <line x1={pad.l} x2={W - pad.r} y1={H - pad.b} y2={H - pad.b} stroke="#efeae4" strokeWidth="1" />
        {keys.map((k, i) => {
          const v = vals[i];
          const h = v ? Math.max(4, ((H - pad.t - pad.b) * v) / max) : 0;
          const x = pad.l + i * bw + gap / 2;
          const y = H - pad.b - h;
          const on = shownIdx === i;
          return (
            <g key={k} onMouseEnter={() => setHover(i)} onClick={() => clickable && v > 0 && onPickDay(k)}>
              <rect x={x} y={pad.t} width={Math.max(2, bw - gap)} height={H - pad.t - pad.b} fill="transparent" />
              {v > 0 && (
                <rect
                  x={x}
                  y={y}
                  width={Math.max(2, bw - gap)}
                  height={h}
                  rx="4"
                  fill={on ? '#8a72c4' : '#b5a3de'}
                  className="transition-colors duration-200"
                />
              )}
              {i % labelEvery === 0 && (
                <text x={x + (bw - gap) / 2} y={H - 5} textAnchor="middle" fontSize="10" fill="#9a94a1" fontWeight="500">
                  {bucketLabel(bucket, k)}
                </text>
              )}
              {on && v > 0 && (
                <text x={x + (bw - gap) / 2} y={y - 4} textAnchor="middle" fontSize="10" fill="#2e2a33" fontWeight="bold">
                  {v}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      <div className="text-[12px] text-ink-600 mt-1.5 min-h-[1.25rem] flex items-center justify-between">
        {shownIdx != null && series[keys[shownIdx]] ? (
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-semibold text-ink-900">{bucketTitle(bucket, keys[shownIdx])}:</span>
            <span className="inline-flex items-center gap-1 text-emerald-700">🚗 {series[keys[shownIdx]].cars}</span>
            <span className="inline-flex items-center gap-1 text-amber-700">🏍️ {series[keys[shownIdx]].motorcycles}</span>
            <span className="inline-flex items-center gap-1 text-rose-700">🚛 {series[keys[shownIdx]].trucks}</span>
          </div>
        ) : (
          <span className="text-ink-400">{clickable ? 'แตะแท่งกราฟเพื่อดูสถิติรายชั่วโมงของวันนั้น' : ''}</span>
        )}
      </div>
    </div>
  );
}

// Camera Card with vehicle count pills & live tracking indicator
function CameraCard({ cam, live, bucket, keys, onPickDay }) {
  const status = live?.active
    ? { text: `กำลังตรวจจับ · ${live.fps} FPS`, cls: 'bg-emerald-50 text-emerald-700 border border-emerald-200', active: true }
    : live
    ? { text: live.error || 'กำลังเชื่อมต่อ', cls: 'bg-amber-50 text-amber-700 border border-amber-200', active: false }
    : null;

  return (
    <article className="rounded-3xl bg-white/80 border border-cream-200/90 p-5 flex flex-col gap-3.5 shadow-soft hover:shadow-lift transition-all duration-300">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h4 className="text-[15px] font-semibold text-ink-900 line-clamp-2 leading-snug">
            {cam.title || cam.camid}
          </h4>
        </div>
        {status && (
          <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium flex items-center gap-1.5 ${status.cls}`}>
            {status.active && <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />}
            {status.text}
          </span>
        )}
      </div>

      <div className="flex items-baseline gap-2">
        <span className="font-serif text-3xl font-bold text-ink-900 leading-none tabular-nums">
          {cam.total.toLocaleString()}
        </span>
        <span className="text-sm text-ink-600 font-medium">คันที่ผ่านทั้งหมด</span>
      </div>

      {/* Vehicle Type Breakdown Chips */}
      <div className="flex flex-wrap gap-2 text-xs">
        <div className="flex items-center gap-1.5 rounded-full bg-emerald-50 text-emerald-800 px-3 py-1 border border-emerald-200/60 font-medium">
          <CarIcon className="w-4 h-4" />
          <span>รถยนต์:</span>
          <span className="font-serif font-bold">{cam.cars.toLocaleString()}</span>
        </div>
        <div className="flex items-center gap-1.5 rounded-full bg-amber-50 text-amber-800 px-3 py-1 border border-amber-200/60 font-medium">
          <BikeIcon className="w-4 h-4" />
          <span>มอไซค์:</span>
          <span className="font-serif font-bold">{cam.motorcycles.toLocaleString()}</span>
        </div>
        <div className="flex items-center gap-1.5 rounded-full bg-rose-50 text-rose-800 px-3 py-1 border border-rose-200/60 font-medium">
          <TruckIcon className="w-4 h-4" />
          <span>รถบรรทุก:</span>
          <span className="font-serif font-bold">{cam.trucks.toLocaleString()}</span>
        </div>
      </div>

      <div className="pt-2 border-t border-cream-200/70">
        <CountBars bucket={bucket} keys={keys} series={cam.series} onPickDay={onPickDay} />
      </div>
    </article>
  );
}

// Camera Picker
function CameraPicker({ cameras, selected, max, onChange, onClose }) {
  const [q, setQ] = useState('');
  const list = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const src = cameras.filter((c) => c.hls_url || c.vdourl);
    const hit = needle ? src.filter((c) => (c.short_title || c.title || '').toLowerCase().includes(needle)) : src;
    return [...hit.filter((c) => selected.includes(c.camid)), ...hit.filter((c) => !selected.includes(c.camid))].slice(0, 60);
  }, [cameras, q, selected]);

  const toggle = (id) => {
    if (selected.includes(id)) onChange(selected.filter((x) => x !== id));
    else if (selected.length < max) onChange([...selected, id]);
  };

  return (
    <div className="rounded-3xl bg-white/95 border border-cream-200/90 p-5 shadow-lift">
      <div className="flex items-center gap-2 mb-3">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="ค้นหาชื่อกล้อง / ชื่อถนน..."
          className="flex-1 min-w-0 rounded-full bg-cream-100 px-4 py-2 text-sm text-ink-900 outline-none focus:ring-2 focus:ring-lavender-400"
        />
        <span className="text-xs font-medium text-ink-600 shrink-0 bg-cream-100 px-3 py-2 rounded-full">
          เลือกแล้ว {selected.length}/{max}
        </span>
        <button
          type="button"
          onClick={onClose}
          aria-label="ปิด"
          className="cursor-pointer w-8 h-8 rounded-full hover:bg-cream-100 flex items-center justify-center text-ink-600 transition-colors"
        >
          <CloseIcon className="w-4 h-4" />
        </button>
      </div>
      <ul className="max-h-64 overflow-y-auto scroll-soft divide-y divide-cream-100">
        {list.map((c) => {
          const on = selected.includes(c.camid);
          const full = !on && selected.length >= max;
          return (
            <li key={c.camid}>
              <button
                type="button"
                onClick={() => toggle(c.camid)}
                disabled={full}
                aria-pressed={on}
                className={`w-full text-left px-3 py-2.5 flex items-center gap-3 transition-colors duration-150 ${
                  full ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer hover:bg-cream-50'
                } ${on ? 'bg-lavender-50/70 font-medium' : ''}`}
              >
                <span
                  className={`w-5 h-5 rounded-full border flex items-center justify-center shrink-0 transition-colors ${
                    on ? 'bg-lavender-600 border-lavender-600 text-white' : 'border-cream-300'
                  }`}
                >
                  {on && <CheckIcon className="w-3 h-3" />}
                </span>
                <span className="flex-1 min-w-0 text-sm text-ink-900 line-clamp-1">{c.short_title || c.title}</span>
                <span className="text-[11px] text-ink-400 shrink-0">{c.province}</span>
              </button>
            </li>
          );
        })}
        {!list.length && <li className="text-sm text-ink-400 py-4 text-center">ไม่พบกล้องที่ตรงกับคำค้น</li>}
      </ul>
    </div>
  );
}

const AI_LEVEL = {
  free: { text: 'โล่ง', cls: 'bg-emerald-50 text-emerald-700 border border-emerald-200' },
  moderate: { text: 'ปานกลาง', cls: 'bg-amber-50 text-amber-700 border border-amber-200' },
  heavy: { text: 'ติดขัด', cls: 'bg-rose-50 text-rose-700 border border-rose-200' },
};
const SORTS = [
  ['busiest', 'รถผ่านมากสุด'],
  ['jammed', 'รถติดสุด'],
  ['quiet', 'รถน้อยสุด'],
];
const agoText = (ts) => {
  if (!ts) return 'ยังไม่ได้วัด';
  const m = Math.round((Date.now() / 1000 - ts) / 60);
  return m < 1 ? 'เมื่อสักครู่' : m < 60 ? `${m} นาทีก่อน` : `${Math.round(m / 60)} ชม.ก่อน`;
};
const jamScore = (c) => (c.level === 'heavy' ? 2 : c.level === 'moderate' ? 1 : 0) * 1000 + (100 - (c.moving_pct ?? 100)) * 5 + (c.visible || 0);

// Camera Ranking
function CameraRanking({ ranking, history, bucket, keys }) {
  const [sort, setSort] = useState('busiest');
  const [showAll, setShowAll] = useState(false);
  const [open, setOpen] = useState(null);
  const seriesById = useMemo(() => Object.fromEntries((history?.cameras || []).map((c) => [c.camid, c])), [history]);

  const rows = useMemo(() => {
    const list = (ranking?.cameras || []).filter((c) => c.ts);
    if (sort === 'busiest') list.sort((a, b) => b.rate_per_min - a.rate_per_min);
    else if (sort === 'quiet') list.sort((a, b) => a.rate_per_min - b.rate_per_min);
    else list.sort((a, b) => jamScore(b) - jamScore(a));
    return list;
  }, [ranking, sort]);

  if (!ranking) return <p className="text-sm text-ink-400 py-4">กำลังโหลดข้อมูลอันดับกล้อง...</p>;
  const shown = showAll ? rows : rows.slice(0, 10);
  const cycleMin = ranking.cycle_seconds ? Math.max(1, Math.round(ranking.cycle_seconds / 60)) : null;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="inline-flex rounded-full bg-cream-100/90 p-1 border border-cream-200" role="tablist">
          {SORTS.map(([k, label]) => (
            <button
              key={k}
              type="button"
              role="tab"
              aria-selected={sort === k}
              onClick={() => setSort(k)}
              className={`cursor-pointer rounded-full px-3.5 py-1 text-xs font-medium transition-all duration-200 ${
                sort === k ? 'bg-white text-ink-900 shadow-soft' : 'text-ink-600 hover:text-ink-900'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <span className="text-[12px] text-ink-500 font-medium">
          วัดแล้ว {rows.length}/{ranking.total_cameras} กล้อง
          {cycleMin ? ` · วนรอบทุก ~${cycleMin} นาที` : ''}
        </span>
      </div>

      <ol className="divide-y divide-cream-100 bg-white/70 rounded-2xl border border-cream-200/80 overflow-hidden">
        {shown.map((c, i) => {
          const lv = AI_LEVEL[c.level] || AI_LEVEL.free;
          const hist = seriesById[c.camid];
          const isOpen = open === c.camid;
          return (
            <li key={c.camid}>
              <button
                type="button"
                onClick={() => setOpen(isOpen ? null : c.camid)}
                aria-expanded={isOpen}
                className="cursor-pointer w-full text-left px-4 py-3 hover:bg-cream-50 transition-colors duration-150 flex items-center gap-3"
              >
                <span className="w-6 text-center font-serif text-sm font-semibold text-ink-400">{i + 1}</span>
                <div className="flex-1 min-w-0">
                  <span className="block text-[14px] font-medium text-ink-900 line-clamp-1">{c.title}</span>
                  <span className="block text-[11px] text-ink-400">
                    {c.source === 'count' ? 'นับต่อเนื่อง' : `สุ่ม ${Math.round(c.seconds || ranking.sample_seconds)} วิ`} · {agoText(c.ts)}
                    {c.error ? <span className="text-rose-600"> · {c.error}</span> : null}
                  </span>
                </div>
                <div className="text-right shrink-0">
                  <span className="block font-serif text-base font-bold text-ink-900 tabular-nums leading-none">
                    {c.rate_per_min} <span className="text-[11px] text-ink-600 font-sans font-normal">คัน/นาที</span>
                  </span>
                  <span className="block text-[11px] text-ink-500 mt-0.5">
                    ในภาพ {Math.round(c.visible)} · วิ่ง {c.moving_pct}%
                  </span>
                </div>
                <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium ${lv.cls}`}>
                  {lv.text}
                </span>
              </button>
              {isOpen && (
                <div className="px-4 pb-4 pt-1 bg-cream-50/50 border-t border-cream-100">
                  {hist ? (
                    <>
                      <p className="text-xs text-ink-600 mb-2 font-medium">
                        {hist.estimated ? '≈ ประมาณการจากการสุ่มภาพ · ' : ''}
                        รถยนต์ <span className="font-serif font-bold text-ink-900">{hist.cars.toLocaleString()}</span> · มอเตอร์ไซค์ <span className="font-serif font-bold text-ink-900">{hist.motorcycles.toLocaleString()}</span> · รถบรรทุก <span className="font-serif font-bold text-ink-900">{hist.trucks.toLocaleString()}</span>
                      </p>
                      <CountBars bucket={bucket} keys={keys} series={hist.series} />
                    </>
                  ) : (
                    <p className="text-xs text-ink-400 py-2">ยังไม่มีข้อมูลสถิติประวัติการนับในช่วงเวลานี้</p>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ol>
      {rows.length > 10 && (
        <button
          type="button"
          onClick={() => setShowAll((v) => !v)}
          className="cursor-pointer self-center text-xs font-medium text-lavender-700 hover:text-lavender-900 underline py-1"
        >
          {showAll ? 'แสดงเพียง 10 อันดับแรก' : `ดูทั้งหมด ${rows.length} กล้อง`}
        </button>
      )}
    </div>
  );
}

// Background count manager
function CameraCounts({ cameras }) {
  const [range, setRange] = useState('24h');
  const [date, setDate] = useState(null);
  const [history, setHistory] = useState(null);
  const [counting, setCounting] = useState(null);
  const [ranking, setRanking] = useState(null);
  const [picking, setPicking] = useState(false);

  useEffect(() => {
    let alive = true;
    const tick = () => {
      fetchAIHistory(date ? { date } : { range }).then((h) => alive && setHistory(h)).catch(() => {});
      fetchCountCameras().then((c) => alive && setCounting(c)).catch(() => {});
      fetchSurveyRanking().then((r) => alive && setRanking(r)).catch(() => {});
    };
    tick();
    const id = setInterval(tick, 30000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [range, date]);

  const selected = counting?.cameras.map((c) => c.camid) || [];
  const liveById = Object.fromEntries((counting?.cameras || []).map((c) => [c.camid, c]));
  const changeSelection = (ids) => {
    setCountCameras(ids).then((c) => setCounting(c)).catch(() => {});
  };

  const cards = useMemo(() => {
    const list = (history?.cameras || []).filter((c) => !c.estimated || selected.includes(c.camid));
    const seen = new Set(list.map((c) => c.camid));
    for (const c of counting?.cameras || []) {
      if (!seen.has(c.camid)) list.push({ camid: c.camid, title: c.title, cars: 0, motorcycles: 0, trucks: 0, total: 0, series: {} });
    }
    return list;
  }, [history, counting, selected]);

  const pickDay = (key) => {
    setDate(key);
    setHistory(null);
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        {date ? (
          <button
            type="button"
            onClick={() => {
              setDate(null);
              setHistory(null);
            }}
            className="cursor-pointer inline-flex items-center gap-1.5 rounded-full bg-lavender-50 text-lavender-700 border border-lavender-200 px-3.5 py-1.5 text-xs font-medium"
          >
            ← กลับ · รายชั่วโมงวันที่ {fmtDay(date)}
          </button>
        ) : (
          <div className="inline-flex rounded-full bg-cream-100/90 p-1 border border-cream-200" role="tablist">
            {RANGES.map(([k, label]) => (
              <button
                key={k}
                type="button"
                role="tab"
                aria-selected={range === k}
                onClick={() => {
                  setRange(k);
                  setHistory(null);
                }}
                className={`cursor-pointer rounded-full px-3.5 py-1.5 text-xs font-medium transition-all duration-200 ${
                  range === k ? 'bg-white text-ink-900 shadow-soft' : 'text-ink-600 hover:text-ink-900'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        )}

        <button
          type="button"
          onClick={() => setPicking((v) => !v)}
          aria-expanded={picking}
          className="cursor-pointer inline-flex items-center gap-2 rounded-full bg-white border border-cream-300 px-4 py-1.5 text-xs font-medium text-ink-900 hover:bg-cream-50 transition-all duration-200 shadow-xs"
        >
          <CameraIcon className="w-4 h-4 text-lavender-600" />
          <span>กล้องที่เลือกนับเบื้องหลัง {counting ? `(${selected.length}/${counting.max_cameras})` : ''}</span>
        </button>
      </div>

      {picking && counting && (
        <CameraPicker
          cameras={cameras}
          selected={selected}
          max={counting.max_cameras}
          onChange={changeSelection}
          onClose={() => setPicking(false)}
        />
      )}

      {!history ? (
        <p className="text-sm text-ink-400 py-6 text-center">กำลังโหลดสถิติการนับรถ...</p>
      ) : !cards.length ? (
        <div className="rounded-2xl border border-dashed border-cream-300 p-8 text-center text-sm text-ink-500 bg-cream-50/50">
          ยังไม่มีกล้องที่นับต่อเนื่อง กรุณากดปุ่ม <b>"กล้องที่เลือกนับเบื้องหลัง"</b> ด้านบน หรือเปิดกล้องในหน้า AI เพื่อเริ่มนับรถอัตโนมัติ
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {cards.map((c) => (
            <CameraCard
              key={c.camid}
              cam={c}
              live={liveById[c.camid]}
              bucket={history.bucket}
              keys={history.keys}
              onPickDay={history.bucket === 'day' ? pickDay : null}
            />
          ))}
        </div>
      )}

      <div className="border-t border-cream-200/80 pt-5 mt-2">
        <div className="flex items-center justify-between mb-2">
          <h4 className="font-serif text-lg font-bold text-ink-900">อันดับการระบายรถทั่วกรุงเทพฯ</h4>
        </div>
        <p className="text-xs text-ink-500 mb-3">
          ระบบสุ่มวิเคราะห์ภาพจากกล้อง CCTV ทุกตัวตัวละ 15 วินาทีหมุนเวียนต่อเนื่อง · แตะที่กล้องเพื่อดูกราฟสถิติย้อนหลัง
        </p>
        <CameraRanking ranking={ranking} history={history} bucket={history?.bucket || 'hour'} keys={history?.keys || []} />
      </div>
    </div>
  );
}

// Modern Executive KPI Card
function ExecutiveTile({ icon: Icon, label, value, sub, tone, badge }) {
  return (
    <div
      className={`glass rounded-3xl p-4 sm:p-5 flex items-start gap-4 transition-all duration-300 hover:shadow-lift hover:-translate-y-0.5 border border-white/80 ${tone}`}
    >
      <div className="w-12 h-12 rounded-2xl bg-white/90 shadow-soft flex items-center justify-center shrink-0 border border-cream-200/50">
        <Icon className="w-6 h-6" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-1">
          <p className="text-xs font-medium text-ink-500 line-clamp-1">{label}</p>
          {badge && (
            <span className="text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full bg-white/70 text-ink-700 border border-cream-200/60 shrink-0">
              {badge}
            </span>
          )}
        </div>
        <p className="font-serif text-2xl sm:text-3xl font-bold text-ink-900 leading-tight mt-0.5 tabular-nums">
          {value}
        </p>
        {sub && <p className="text-xs text-ink-600 mt-1 line-clamp-1 font-medium">{sub}</p>}
      </div>
    </div>
  );
}

export default function DashboardPage({ isActive, liveCount, cameras = [], incidents, onAsk, onOpenRoad, onNavigate, onOpenAI }) {
  const [summary, setSummary] = useState(null);
  const [ai, setAi] = useState(null);
  const [showTrend, setShowTrend] = useState(false);

  useEffect(() => {
    if (!isActive) return;
    let alive = true;
    const tick = () => {
      fetchTrafficSummary(5).then((s) => alive && setSummary(s)).catch(() => {});
      fetchAIStats().then((s) => alive && setAi(s)).catch(() => alive && setAi(null));
    };
    tick();
    const id = setInterval(tick, 30000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [isActive]);

  const level = levelOf(summary?.flow_index);
  const updated = summary?.updated_at
    ? new Date(summary.updated_at * 1000).toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' })
    : '--:--';

  // Change vs ~1 hour ago (20 samples x 3 min)
  const hist = summary?.history || [];
  const delta = hist.length > 20 ? hist[hist.length - 1].flow - hist[hist.length - 21].flow : null;
  const deltaStatus =
    delta == null
      ? null
      : delta > 2
      ? { text: `ดีขึ้น +${delta} จาก 1 ชม.ที่แล้ว`, isGood: true }
      : delta < -2
      ? { text: `ชะลอลง ${delta} จาก 1 ชม.ที่แล้ว`, isGood: false }
      : { text: 'ใกล้เคียง 1 ชม.ก่อน', isGood: null };

  const incidentList = [...(incidents?.camera || []), ...(incidents?.longdo || [])];

  return (
    <div className="flex flex-col gap-5 max-w-5xl mx-auto w-full px-2 sm:px-0">
      {/* High-Priority Accident / Incident Alert Banner */}
      {incidentList.length > 0 && (
        <motion.section
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          role="alert"
          className="rounded-3xl bg-gradient-to-r from-rose-50/90 via-orange-50/80 to-amber-50/90 border border-rose-200/80 p-4 sm:p-5 shadow-soft"
        >
          <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
            <div className="flex items-center gap-2.5">
              <span className="w-8 h-8 rounded-xl bg-rose-500 text-white flex items-center justify-center shrink-0 shadow-xs animate-pulse">
                <ShieldAlertIcon className="w-4 h-4" />
              </span>
              <div>
                <h3 className="font-serif text-base sm:text-lg font-bold text-rose-900 leading-tight">
                  รายงานอุบัติเหตุ / เหตุการณ์ด่วน ({incidentList.length} จุด)
                </h3>
                <p className="text-xs text-rose-700">ตรวจสอบจุดกีดขวางการจราจรก่อนออกเดินทาง</p>
              </div>
            </div>

            <button
              type="button"
              onClick={() => onNavigate('map')}
              className="cursor-pointer inline-flex items-center gap-1.5 rounded-full bg-rose-600 text-white px-4 py-2 text-xs font-semibold hover:bg-rose-700 transition-colors shadow-xs"
            >
              <MapPinIcon className="w-3.5 h-3.5" />
              ดูบนแผนที่สด
            </button>
          </div>

          <ul className="flex flex-col gap-2">
            {incidentList.slice(0, 4).map((i) => (
              <li
                key={i.id}
                className="flex items-start gap-3.5 rounded-2xl bg-white/90 border border-cream-200/60 p-3 shadow-xs hover:shadow-soft transition-all"
              >
                {i.image && (
                  <img
                    src={i.image}
                    alt=""
                    className="w-16 sm:w-20 h-14 object-cover rounded-xl shrink-0 border border-cream-200"
                  />
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={`text-xs font-bold px-2 py-0.5 rounded-full ${
                        i.kind === 'breakdown'
                          ? 'bg-amber-100 text-amber-800'
                          : 'bg-rose-100 text-rose-800'
                      }`}
                    >
                      {i.kind === 'breakdown' ? 'รถเสีย / กีดขวาง' : 'อุบัติเหตุ'}
                    </span>
                    <span className="text-sm font-semibold text-ink-900 line-clamp-1">{i.title}</span>
                  </div>
                  {i.description && <p className="text-xs text-ink-600 line-clamp-1 mt-0.5">{i.description}</p>}
                  <p className="text-[11px] text-ink-400 mt-1">
                    {i.source === 'camera'
                      ? `กล้อง AI ตรวจพบ · ${agoText(i.ts)}${i.confidence ? ` (ความมั่นใจ ${Math.round(i.confidence * 100)}%)` : ''}`
                      : `รายงานจราจร${i.start ? ` · เริ่ม ${i.start.slice(11, 16)} น.` : ''}`}
                  </p>
                </div>
                {i.camid && onOpenAI && (
                  <button
                    type="button"
                    onClick={() => onOpenAI(i.camid)}
                    className="cursor-pointer shrink-0 self-center rounded-full bg-cream-100 hover:bg-cream-200 text-ink-800 px-3 py-1.5 text-xs font-semibold transition-colors"
                  >
                    ดูภาพสด
                  </button>
                )}
              </li>
            ))}
          </ul>
        </motion.section>
      )}

      {/* Hero Section: Executive Flow Score & Stacked Ratio Bar */}
      <motion.section
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass rounded-3xl p-6 sm:p-8 relative overflow-hidden border border-white/90 shadow-lift"
        style={{
          background: `radial-gradient(ellipse at 15% 50%, ${level.bgGlow}, transparent 70%), rgba(255, 255, 255, 0.78)`,
        }}
      >
        {/* Top Header Row */}
        <div className="flex flex-wrap items-center justify-between gap-2 pb-4 border-b border-cream-200/60">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
            <h3 className="text-xs sm:text-sm font-bold uppercase tracking-wider text-ink-600">
              สถานะการจราจรกรุงเทพฯ และปริมณฑล
            </h3>
          </div>
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ${
              summary?.online === false ? 'bg-amber-50 text-amber-700' : 'bg-emerald-50 text-emerald-700'
            } border border-black/5`}
          >
            <RefreshIcon className="w-3 h-3" />
            {summary?.online === false ? 'ออฟไลน์' : 'อัปเดตสด'} {updated} น.
          </span>
        </div>

        {/* Hero Body */}
        <div className="mt-6 grid grid-cols-1 md:grid-cols-[auto_1fr] gap-6 md:gap-10 items-center">
          {/* Radial Flow Gauge & Level Headline */}
          <div className="flex items-center gap-5 sm:gap-6">
            <RadialFlowGauge flow={summary?.flow_index} color={level.color} />
            <div>
              <div className="inline-flex items-center gap-1.5 mb-1.5">
                <span className={`px-3 py-1 rounded-full text-xs font-semibold ${level.badgeCls}`}>
                  {level.text}
                </span>
              </div>
              <h2 className="font-serif text-2xl sm:text-3xl font-bold text-ink-900 leading-tight">
                {level.hint}
              </h2>
              {deltaStatus && (
                <div className="flex items-center gap-1.5 mt-2 text-xs font-medium">
                  {deltaStatus.isGood ? (
                    <span className="text-emerald-700 flex items-center gap-1 bg-emerald-50 px-2 py-0.5 rounded-md">
                      <TrendingUpIcon className="w-3.5 h-3.5" />
                      {deltaStatus.text}
                    </span>
                  ) : deltaStatus.isGood === false ? (
                    <span className="text-rose-700 flex items-center gap-1 bg-rose-50 px-2 py-0.5 rounded-md">
                      <TrendingDownIcon className="w-3.5 h-3.5" />
                      {deltaStatus.text}
                    </span>
                  ) : (
                    <span className="text-ink-500">{deltaStatus.text}</span>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* StackBar Proportion Overview */}
          <div className="flex flex-col justify-center bg-white/60 rounded-2xl p-4 sm:p-5 border border-cream-200/80 shadow-xs">
            <div className="flex items-center justify-between text-xs text-ink-600 mb-2">
              <span className="font-medium">สัดส่วนสภาพถนนรวมทุกสาย</span>
              <span className="font-serif font-bold text-ink-900">
                {summary ? `${Math.round(summary.total_km).toLocaleString()} กม.` : ''}
              </span>
            </div>
            {summary?.ready ? (
              <StackBar green={summary.green_pct} yellow={summary.yellow_pct} red={summary.red_pct} />
            ) : (
              <div className="h-4 rounded-full bg-cream-200 animate-pulse" />
            )}
          </div>
        </div>
      </motion.section>

      {/* KPI Metrics Cards (4 tiles) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <ExecutiveTile
          icon={CameraIcon}
          label="กล้อง CCTV ที่เปิดดู"
          value={liveCount > 0 ? `${liveCount} ตัว` : '0 ตัว'}
          sub="เลือกดูภาพสดได้ในหน้ากล้อง"
          badge="LIVE FEED"
          tone="bg-lavender-50/40"
        />
        <ExecutiveTile
          icon={CarIcon}
          label="รถหน้ากล้อง AI ตอนนี้"
          value={ai?.active ? `${ai.total} คัน` : '–'}
          sub={ai?.active ? ai.title : 'ยังไม่ได้เปิดกล้อง AI'}
          badge={ai?.active ? 'YOLO11x ON' : 'IDLE'}
          tone="bg-amber-50/40"
        />
        <ExecutiveTile
          icon={MapPinIcon}
          label="เครือข่ายถนนที่ติดตาม"
          value={summary ? `${summary.road_count} สาย` : '–'}
          sub="วิเคราะห์จากเส้นจราจรสด"
          badge="14,000+ SEGS"
          tone="bg-emerald-50/40"
        />
        <ExecutiveTile
          icon={ActivityIcon}
          label="สัดส่วนถนนที่คล่องตัว"
          value={summary ? `${summary.green_pct}%` : '–'}
          sub={`ติดขัดสะสม ${summary?.red_pct ?? 0}%`}
          badge="EFFICIENCY"
          tone="bg-teal-50/40"
        />
      </div>

      {/* Avoid / Go Smooth Road Highlights (2 Columns) */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Congested Roads */}
        <section className="glass rounded-3xl p-5 sm:p-6 border border-white/80 shadow-soft">
          <div className="flex items-center justify-between mb-1">
            <h3 className="font-serif text-lg font-bold text-ink-900 flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-rose-500 shadow-xs" />
              ถนนที่ควรหลีกเลี่ยงตอนนี้
            </h3>
            <span className="text-[11px] font-semibold text-rose-700 bg-rose-50 px-2 py-0.5 rounded-full border border-rose-200">
              ติดขัดสะสม
            </span>
          </div>
          <p className="text-xs text-ink-500 mb-3">เรียงตามระยะทางที่ติดขัดมากที่สุด · แตะชื่อถนนเพื่อเปิดกล้อง</p>

          {summary?.ready ? (
            summary.congested.length ? (
              <ul className="flex flex-col gap-1">
                {summary.congested.map((r, i) => (
                  <RoadRow key={r.name} r={r} rank={i + 1} onOpen={onOpenRoad} type="congested" />
                ))}
              </ul>
            ) : (
              <div className="py-8 text-center text-sm text-ink-400 bg-cream-50/50 rounded-2xl border border-dashed border-cream-200">
                🎉 ปัจจุบันไม่มีถนนสายหลักที่มีรถติดขัดหนาแน่น
              </div>
            )
          ) : (
            <div className="space-y-2 py-2">
              {[1, 2, 3, 4].map((n) => (
                <div key={n} className="h-12 rounded-2xl bg-cream-100 animate-pulse" />
              ))}
            </div>
          )}
        </section>

        {/* Free Flow Roads */}
        <section className="glass rounded-3xl p-5 sm:p-6 border border-white/80 shadow-soft">
          <div className="flex items-center justify-between mb-1">
            <h3 className="font-serif text-lg font-bold text-ink-900 flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-emerald-500 shadow-xs" />
              ถนนสายหลักที่วิ่งได้สบาย
            </h3>
            <span className="text-[11px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
              คล่องตัวสูง
            </span>
          </div>
          <p className="text-xs text-ink-500 mb-3">สายยาวที่ระบายรถได้ดีเยื้องต้น · เหมาะแก่การเดินทาง</p>

          {summary?.ready ? (
            summary.free_flow.length ? (
              <ul className="flex flex-col gap-1">
                {summary.free_flow.map((r, i) => (
                  <RoadRow key={r.name} r={r} rank={i + 1} onOpen={onOpenRoad} type="free" />
                ))}
              </ul>
            ) : (
              <div className="py-8 text-center text-sm text-ink-400 bg-cream-50/50 rounded-2xl border border-dashed border-cream-200">
                ไม่มีข้อมูลถนนสายที่วิ่งได้สบาย
              </div>
            )
          ) : (
            <div className="space-y-2 py-2">
              {[1, 2, 3, 4].map((n) => (
                <div key={n} className="h-12 rounded-2xl bg-cream-100 animate-pulse" />
              ))}
            </div>
          )}
        </section>
      </div>

      {/* 24-Hour Traffic Trend Analytics Card */}
      <section className="glass rounded-3xl p-5 sm:p-6 border border-white/80 shadow-soft">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-serif text-lg font-bold text-ink-900 flex items-center gap-2">
              <ActivityIcon className="w-5 h-5 text-lavender-600" />
              แนวโน้มสภาพการจราจร 24 ชั่วโมง
            </h3>
            <p className="text-xs text-ink-500 mt-0.5">
              ดัชนีคะแนนการระบายรถรวม (0 = ติดหนัก, 100 = โล่งสบาย) บันทึกทุก ๆ 3 นาที
            </p>
          </div>
          <button
            type="button"
            onClick={() => setShowTrend((v) => !v)}
            aria-expanded={showTrend}
            className="cursor-pointer text-xs font-semibold rounded-full bg-cream-100 hover:bg-cream-200 text-lavender-700 px-3.5 py-1.5 transition-colors"
          >
            {showTrend ? 'ซ่อนกราฟ' : 'ดูกราฟละเอียด'}
          </button>
        </div>

        <div className="mt-4">
          <Sparkline history={hist} />
        </div>
      </section>

      {/* AI Camera Vehicle Counting & City Survey Section */}
      <section className="glass rounded-3xl p-5 sm:p-6 border border-white/80 shadow-soft">
        <div className="flex items-center justify-between mb-1">
          <h3 className="font-serif text-lg font-bold text-ink-900 flex items-center gap-2">
            <CarIcon className="w-5 h-5 text-lavender-600" />
            สถิติจำนวนรถที่ผ่านกล้อง AI (Vehicle Counter)
          </h3>
        </div>
        <p className="text-xs text-ink-500 mb-4">
          นับรถทุกคันแยกตามประเภท (รถยนต์, มอเตอร์ไซค์, รถบรรทุก) บันทึกลงฐานข้อมูลรายชั่วโมง
        </p>
        <CameraCounts cameras={cameras} />
      </section>

      {/* Bottom Floating Navigation Dock */}
      <div className="flex flex-wrap items-center justify-center gap-2.5 py-3">
        <button
          type="button"
          onClick={() => onNavigate('map')}
          className="cursor-pointer inline-flex items-center gap-2 rounded-full bg-white/90 border border-cream-300 px-5 py-2.5 text-sm font-semibold text-ink-900 hover:bg-emerald-50 hover:border-emerald-200 transition-all shadow-xs"
        >
          <MapPinIcon className="w-4 h-4 text-emerald-600" />
          ดูบนแผนที่จราจรสด
        </button>
        <button
          type="button"
          onClick={() => onNavigate('cameras')}
          className="cursor-pointer inline-flex items-center gap-2 rounded-full bg-white/90 border border-cream-300 px-5 py-2.5 text-sm font-semibold text-ink-900 hover:bg-lavender-50 hover:border-lavender-200 transition-all shadow-xs"
        >
          <CameraIcon className="w-4 h-4 text-lavender-600" />
          เปิดกล้อง CCTV ทั้งหมด
        </button>
        <button
          type="button"
          onClick={() => onAsk('')}
          className="cursor-pointer inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-amber-400 to-amber-500 text-ink-950 px-6 py-2.5 text-sm font-bold hover:brightness-105 transition-all shadow-soft"
        >
          <SparkleIcon className="w-4 h-4" />
          ถาม AI ผู้ช่วยการจราจร
        </button>
      </div>
    </div>
  );
}
