import { useMemo, useState } from 'react';
import { Card, SectionHeader, EmptyState } from './ui.jsx';
import { fmtTime } from './format.js';

const W = 640;
const H = 160;
const PAD = { l: 32, r: 12, t: 12, b: 24 };
const ACCENT = '#2563eb';

export default function TrendChart({ history }) {
  const [hover, setHover] = useState(null);

  const pts = useMemo(() => {
    if (!history?.length) return [];
    const n = history.length;
    return history.map((h, i) => ({
      x: PAD.l + ((W - PAD.l - PAD.r) * i) / Math.max(1, n - 1),
      y: PAD.t + (H - PAD.t - PAD.b) * (1 - (h.flow || 0) / 100),
      flow: h.flow,
      red: h.red_pct,
      ts: h.t,
    }));
  }, [history]);

  const span = pts.length ? Math.round((pts[pts.length - 1].ts - pts[0].ts) / 3600) : 0;

  const onMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * W;
    let best = pts[0];
    for (const p of pts) if (Math.abs(p.x - x) < Math.abs(best.x - x)) best = p;
    setHover(best);
  };

  const d = pts.map((p, i) => `${i ? 'L' : 'M'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
  const shown = hover ?? pts[pts.length - 1];

  return (
    <Card aria-labelledby="trend-title" className="p-5">
      <SectionHeader
        id="trend-title"
        title="แนวโน้มการระบายรถ"
        description={`ดัชนี 0 = ติดหนัก, 100 = โล่ง · บันทึกทุก 3 นาที${span ? ` · ย้อนหลัง ${span} ชม.` : ''}`}
        action={
          shown ? (
            <div className="text-right">
              <p className="text-xs text-slate-500">{hover ? `${fmtTime(shown.ts)} น.` : 'ล่าสุด'}</p>
              <p className="text-sm font-semibold text-slate-900 tabular-nums">
                {shown.flow}
                <span className="text-slate-500 font-normal">/100</span>
                {shown.red != null && <span className="text-slate-500 font-normal"> · ติดขัด {shown.red}%</span>}
              </p>
            </div>
          ) : null
        }
      />
      <div className="mt-4">
        {pts.length < 2 ? (
          <EmptyState title="ยังไม่มีข้อมูลย้อนหลังพอสำหรับวาดกราฟ" description="ระบบเก็บค่าทุก 3 นาที กราฟจะแสดงเมื่อมีอย่างน้อย 2 จุด" />
        ) : (
          <svg
            viewBox={`0 0 ${W} ${H}`}
            className="w-full h-auto select-none"
            onMouseMove={onMove}
            onMouseLeave={() => setHover(null)}
            role="img"
            aria-label="กราฟแนวโน้มดัชนีการระบายรถ"
          >
            {[0, 50, 100].map((v) => {
              const y = PAD.t + (H - PAD.t - PAD.b) * (1 - v / 100);
              return (
                <g key={v}>
                  <line x1={PAD.l} x2={W - PAD.r} y1={y} y2={y} stroke="#e2e8f0" strokeWidth="1" />
                  <text x={PAD.l - 8} y={y + 3.5} textAnchor="end" fontSize="10" fill="#64748b">
                    {v}
                  </text>
                </g>
              );
            })}
            <path d={d} fill="none" stroke={ACCENT} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
            <text x={PAD.l} y={H - 6} fontSize="10" fill="#64748b">
              {fmtTime(pts[0].ts)}
            </text>
            <text x={W - PAD.r} y={H - 6} fontSize="10" fill="#64748b" textAnchor="end">
              {fmtTime(pts[pts.length - 1].ts)}
            </text>
            {hover && (
              <g>
                <line x1={hover.x} x2={hover.x} y1={PAD.t} y2={H - PAD.b} stroke="#94a3b8" strokeWidth="1" strokeDasharray="3 3" />
                <circle cx={hover.x} cy={hover.y} r="4" fill={ACCENT} stroke="#fff" strokeWidth="2" />
              </g>
            )}
          </svg>
        )}
      </div>
    </Card>
  );
}
