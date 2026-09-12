import { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { CarIcon, BikeIcon, TruckIcon, CameraIcon, MapPinIcon, SparkleIcon, RefreshIcon } from './Icons.jsx';
import { fetchAIStats, fetchTrafficSummary } from '../lib/api.js';

// Status palette (validated: CVD-safe, warning needs visible labels)
const STATUS = { green: '#4a9a3f', yellow: '#d6a52a', red: '#d9534f' };
const LEVEL_CLS = { โล่ง: 'bg-sage-100 text-sage-700', ปานกลาง: 'bg-gold-100 text-gold-700', ติดขัด: 'bg-apricot-100 text-apricot-700' };

function levelOf(flow) {
  if (flow == null) return { text: 'กำลังโหลด', cls: 'bg-cream-200 text-ink-600', hint: 'รอเส้นจราจรสักครู่' };
  if (flow >= 75) return { text: 'ถนนโล่งสบาย', cls: 'bg-sage-100 text-sage-700', hint: 'ออกเดินทางได้เลย' };
  if (flow >= 45) return { text: 'รถพอประมาณ', cls: 'bg-gold-100 text-gold-700', hint: 'เผื่อเวลาอีกนิด' };
  return { text: 'รถค่อนข้างเยอะ', cls: 'bg-apricot-100 text-apricot-700', hint: 'เลี่ยงสายหลักที่ติดก่อน' };
}

function StackBar({ green, yellow, red }) {
  const segs = [
    ['green', green, 'โล่ง'],
    ['yellow', yellow, 'ปานกลาง'],
    ['red', red, 'ติดขัด'],
  ].filter(([, v]) => v > 0);
  return (
    <div>
      <div className="flex h-3 rounded-full overflow-hidden gap-[2px]" role="img" aria-label={`โล่ง ${green}% ปานกลาง ${yellow}% ติดขัด ${red}%`}>
        {segs.map(([k, v]) => (
          <div key={k} style={{ width: `${v}%`, background: STATUS[k] }} className="rounded-full" />
        ))}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-600">
        {[
          ['green', green, 'โล่ง'],
          ['yellow', yellow, 'ปานกลาง'],
          ['red', red, 'ติดขัด'],
        ].map(([k, v, label]) => (
          <span key={k} className="inline-flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full" style={{ background: STATUS[k] }} />
            {label} <span className="font-serif text-sm text-ink-900">{v}%</span>
          </span>
        ))}
      </div>
    </div>
  );
}

function Sparkline({ history }) {
  const [hover, setHover] = useState(null);
  const W = 560;
  const H = 120;
  const pad = { l: 28, r: 8, t: 10, b: 22 };
  const pts = useMemo(() => {
    if (!history?.length) return [];
    const n = history.length;
    return history.map((h, i) => ({
      x: pad.l + ((W - pad.l - pad.r) * i) / Math.max(1, n - 1),
      y: pad.t + (H - pad.t - pad.b) * (1 - h.flow / 100),
      flow: h.flow,
      t: new Date(h.t * 1000),
    }));
  }, [history]);

  if (pts.length < 2) return <p className="text-sm text-ink-400 py-6">ยังไม่มีข้อมูลย้อนหลัง จะเริ่มเก็บทุก 3 นาที</p>;
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
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" onMouseMove={onMove} onMouseLeave={() => setHover(null)} role="img" aria-label="แนวโน้มการระบายรถ">
        {[0, 50, 100].map((v) => {
          const y = pad.t + (H - pad.t - pad.b) * (1 - v / 100);
          return (
            <g key={v}>
              <line x1={pad.l} x2={W - pad.r} y1={y} y2={y} stroke="#efeae4" strokeWidth="1" />
              <text x={pad.l - 6} y={y + 4} textAnchor="end" fontSize="10" fill="#9a94a1">{v}</text>
            </g>
          );
        })}
        <path d={area} fill="#d7ccef" opacity="0.35" />
        <path d={d} fill="none" stroke="#8a72c4" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        <text x={pad.l} y={H - 6} fontSize="10" fill="#9a94a1">{fmt(pts[0].t)}</text>
        <text x={W - pad.r} y={H - 6} fontSize="10" fill="#9a94a1" textAnchor="end">{fmt(pts[pts.length - 1].t)}</text>
        {hover && (
          <g>
            <line x1={hover.x} x2={hover.x} y1={pad.t} y2={H - pad.b} stroke="#b5a3de" strokeWidth="1" strokeDasharray="3 3" />
            <circle cx={hover.x} cy={hover.y} r="5" fill="#8a72c4" stroke="#fff" strokeWidth="2" />
          </g>
        )}
      </svg>
      {hover && (
        <div className="absolute top-0 left-1/2 -translate-x-1/2 glass-strong rounded-full px-3 py-1 text-xs text-ink-900 pointer-events-none">
          {fmt(hover.t)} · ระบายได้ <span className="font-serif">{hover.flow}</span>/100
        </div>
      )}
    </div>
  );
}

function RoadRow({ r, onAsk }) {
  return (
    <li>
      <button type="button" onClick={() => onAsk(r.name)} className="cursor-pointer w-full text-left rounded-2xl px-3 py-2 hover:bg-cream-100 transition-colors duration-200">
        <div className="flex items-center gap-2">
          <span className="flex-1 min-w-0 text-sm text-ink-900 line-clamp-1">{r.name}</span>
          <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${LEVEL_CLS[r.level]}`}>{r.level}</span>
          <span className="font-serif text-base text-ink-900 w-9 text-right tabular-nums">{r.flow}</span>
        </div>
        <div className="mt-1.5 flex h-1.5 rounded-full overflow-hidden gap-[2px]" aria-hidden="true">
          {r.green_pct > 0 && <span style={{ width: `${r.green_pct}%`, background: STATUS.green }} className="rounded-full" />}
          {r.yellow_pct > 0 && <span style={{ width: `${r.yellow_pct}%`, background: STATUS.yellow }} className="rounded-full" />}
          {r.red_pct > 0 && <span style={{ width: `${r.red_pct}%`, background: STATUS.red }} className="rounded-full" />}
        </div>
        <p className="mt-1 text-[11px] text-ink-600">
          ติดขัด {r.red_km} กม. จาก {r.length_km} กม.
        </p>
      </button>
    </li>
  );
}

function Tile({ icon: Icon, label, value, sub, tone }) {
  return (
    <div className={`glass rounded-3xl px-5 py-4 flex items-center gap-4 ${tone}`}>
      <div className="w-12 h-12 rounded-2xl bg-white/80 flex items-center justify-center shrink-0">
        <Icon className="w-7 h-7" />
      </div>
      <div className="min-w-0">
        <p className="text-xs text-ink-600">{label}</p>
        <p className="font-serif text-2xl font-semibold text-ink-900 leading-none mt-0.5 tabular-nums">{value}</p>
        {sub && <p className="text-[11px] text-ink-600 mt-1">{sub}</p>}
      </div>
    </div>
  );
}

export default function DashboardPage({ isActive, liveCount, onAsk, onNavigate }) {
  const [summary, setSummary] = useState(null);
  const [ai, setAi] = useState(null);

  useEffect(() => {
    if (!isActive) return;
    let alive = true;
    const tick = () => {
      fetchTrafficSummary(6).then((s) => alive && setSummary(s)).catch(() => {});
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
  const updated = summary?.updated_at ? new Date(summary.updated_at * 1000).toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' }) : '--:--';

  return (
    <div className="flex flex-col gap-4">
      {/* Hero */}
      <div className="grid grid-cols-1 lg:grid-cols-[1.2fr_1fr] gap-4">
        <motion.section initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="glass rounded-[2rem] p-6 sm:p-7">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="font-serif text-xl font-semibold text-ink-900">ภาพรวมการจราจรวันนี้</h2>
              <p className="text-sm text-ink-600">กรุงเทพฯ และปริมณฑล จากเส้นจราจร {summary?.road_count ?? '…'} สาย</p>
            </div>
            <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs ${summary?.online === false ? 'bg-gold-50 text-gold-700' : 'bg-sage-50 text-sage-700'}`}>
              <RefreshIcon className="w-3 h-3" />
              {summary?.online === false ? 'ออฟไลน์' : 'สด'} {updated}
            </span>
          </div>

          <div className="mt-5 flex flex-wrap items-end gap-5">
            <div>
              <p className="text-xs text-ink-600">ดัชนีการระบายรถ</p>
              <p className="font-serif text-6xl sm:text-7xl font-semibold text-ink-900 leading-none tabular-nums">
                {summary?.flow_index ?? '–'}
                <span className="text-2xl text-ink-400">/100</span>
              </p>
            </div>
            <div className="pb-1">
              <span className={`inline-block rounded-full px-4 py-1.5 text-sm font-medium ${level.cls}`}>{level.text}</span>
              <p className="text-sm text-ink-600 mt-1.5">{level.hint}</p>
            </div>
          </div>

          <div className="mt-6">
            {summary?.ready ? <StackBar green={summary.green_pct} yellow={summary.yellow_pct} red={summary.red_pct} /> : <div className="h-3 rounded-full bg-cream-200 animate-pulse" />}
          </div>
        </motion.section>

        <motion.section initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }} className="glass rounded-[2rem] p-6 sm:p-7">
          <h3 className="font-serif text-lg font-semibold text-ink-900">แนวโน้มช่วงที่ผ่านมา</h3>
          <p className="text-xs text-ink-600 mb-3">ดัชนีการระบายรถ อัปเดตทุก 3 นาที</p>
          <Sparkline history={summary?.history} />
        </motion.section>
      </div>

      {/* Tiles */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
        <Tile icon={MapPinIcon} label="ระยะถนนที่ติดตาม" value={summary ? `${Math.round(summary.total_km).toLocaleString()} กม.` : '–'} sub={`${summary?.road_count ?? 0} สายที่มีชื่อ`} tone="border-sage-100" />
        <Tile icon={CameraIcon} label="กล้องที่คุณเปิดอยู่" value={liveCount} sub="ในหน้าต่างเมือง" tone="border-lavender-100" />
        <Tile icon={CarIcon} label="รถหน้ากล้อง AI" value={ai?.active ? ai.total : '–'} sub={ai?.active ? ai.title : 'ยังไม่ได้เปิดกล้อง AI'} tone="border-gold-100" />
        <div className="glass rounded-3xl px-5 py-4 border-apricot-100 flex items-center gap-3">
          <BikeIcon className="w-6 h-6" />
          <span className="font-serif text-xl text-ink-900 tabular-nums">{ai?.active ? ai.motorcycles : '–'}</span>
          <TruckIcon className="w-6 h-6 ml-2" />
          <span className="font-serif text-xl text-ink-900 tabular-nums">{ai?.active ? ai.trucks : '–'}</span>
          <span className="text-[11px] text-ink-600 ml-auto">มอเตอร์ไซค์ / บรรทุก</span>
        </div>
      </div>

      {/* Lists */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <section className="glass rounded-[2rem] p-5">
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-serif text-lg font-semibold text-ink-900">ติดขัดมากที่สุดตอนนี้</h3>
            <span className="text-[11px] text-ink-600">จัดอันดับตามระยะที่ติด</span>
          </div>
          {summary?.ready ? (
            <ul className="space-y-1">{summary.congested.map((r) => <RoadRow key={r.name} r={r} onAsk={onAsk} />)}</ul>
          ) : (
            <p className="text-sm text-ink-400 py-4">กำลังโหลดเส้นจราจร...</p>
          )}
        </section>
        <section className="glass rounded-[2rem] p-5">
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-serif text-lg font-semibold text-ink-900">สายหลักที่ระบายดี</h3>
            <span className="text-[11px] text-ink-600">flow 85 ขึ้นไป</span>
          </div>
          {summary?.ready ? (
            <ul className="space-y-1">{summary.free_flow.map((r) => <RoadRow key={r.name} r={r} onAsk={onAsk} />)}</ul>
          ) : (
            <p className="text-sm text-ink-400 py-4">กำลังโหลดเส้นจราจร...</p>
          )}
        </section>
      </div>

      <div className="flex flex-wrap gap-2 justify-center">
        <button type="button" onClick={() => onNavigate('map')} className="cursor-pointer inline-flex items-center gap-2 rounded-full bg-white/80 border border-cream-200 px-5 py-2.5 text-sm text-ink-900 hover:bg-sage-50 transition-colors duration-200">
          <MapPinIcon className="w-4 h-4" />
          ดูบนแผนที่จราจร
        </button>
        <button type="button" onClick={() => onAsk('')} className="cursor-pointer inline-flex items-center gap-2 rounded-full bg-gold-400 text-ink-900 px-5 py-2.5 text-sm font-semibold hover:bg-gold-200 transition-colors duration-200">
          <SparkleIcon className="w-4 h-4" />
          ถามผู้ช่วยการจราจร
        </button>
      </div>
    </div>
  );
}
