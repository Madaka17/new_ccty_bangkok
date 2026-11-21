import { useMemo, useRef, useState } from 'react';
import { bmaHourlyLines, thinLabels } from '../../../lib/overviewData.js';
import { fmtNum } from '../format.js';
import { linePath, niceMax } from './chartMath.js';
import { ChartTip, EmptyBlock, SeriesLegend, TipRow, useChartWidth } from './ChartParts.jsx';

const H = 200;
const PAD = { l: 36, r: 12, t: 12, b: 26 };
const SERIES = [
  { label: 'รถยนต์', token: 'var(--c-series-a)' },
  { label: 'มอเตอร์ไซค์', token: 'var(--c-series-b)' },
];

// Per-camera averages per hour as two smooth lines, with a crosshair on hover or touch.
function BmaLines({ rows, width = 640 }) {
  const [hover, setHover] = useState(null);
  // one SVG unit is one CSS px: the viewBox is the measured width
  const W = width;
  const n = rows.length;
  const top = niceMax(Math.max(...rows.flatMap((r) => [r.cars, r.motorcycles])));
  const plotW = W - PAD.l - PAD.r;
  const plotH = H - PAD.t - PAD.b;
  const xOf = (i) => PAD.l + (n > 1 ? (plotW * i) / (n - 1) : plotW / 2);
  const yOf = (v) => PAD.t + plotH * (1 - v / top);
  const carPts = rows.map((r, i) => ({ x: xOf(i), y: yOf(r.cars) }));
  const motorPts = rows.map((r, i) => ({ x: xOf(i), y: yOf(r.motorcycles) }));
  const step = thinLabels(n, W < 480 ? 6 : 12);
  const ticks = [0, 1, 2, 3, 4].map((k) => Math.round((top * k) / 4));
  const hovered = hover != null ? rows[hover] : null;

  const onMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * W;
    const idx = n > 1 ? Math.round(((x - PAD.l) / plotW) * (n - 1)) : 0;
    setHover(Math.min(n - 1, Math.max(0, idx)));
  };

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        height={H}
        className="block select-none"
        role="img"
        aria-label={`กราฟรถเฉลี่ยต่อกล้องรายชั่วโมง ${n} ช่วงเวลา`}
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
      >
        {ticks.map((v, k) => (
          <g key={k}>
            <line x1={PAD.l} x2={W - PAD.r} y1={yOf(v)} y2={yOf(v)} stroke="var(--c-border)" strokeWidth="1" />
            <text x={PAD.l - 6} y={yOf(v) + 4} textAnchor="end" fontSize="12" fill="var(--c-muted)">
              {fmtNum(v)}
            </text>
          </g>
        ))}
        <path d={linePath(carPts)} fill="none" stroke="var(--c-series-a)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        <path d={linePath(motorPts)} fill="none" stroke="var(--c-series-b)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        {rows.map((r, i) =>
          i % step === 0 ? (
            <text key={r.hour ?? r.t} x={xOf(i)} y={H - 8} textAnchor="middle" fontSize="12" fill="var(--c-muted)">
              {r.label}
            </text>
          ) : null,
        )}
        {hovered && (
          <g>
            <line x1={xOf(hover)} x2={xOf(hover)} y1={PAD.t} y2={H - PAD.b} stroke="var(--c-border-strong)" strokeWidth="1" strokeDasharray="3 3" />
            <circle cx={xOf(hover)} cy={yOf(hovered.cars)} r="4" fill="var(--c-series-a)" stroke="var(--c-surface)" strokeWidth="2" />
            <circle cx={xOf(hover)} cy={yOf(hovered.motorcycles)} r="4" fill="var(--c-series-b)" stroke="var(--c-surface)" strokeWidth="2" />
          </g>
        )}
      </svg>
      {hovered && (
        <ChartTip xPct={(xOf(hover) / W) * 100}>
          <p className="font-semibold">{hovered.label}</p>
          <TipRow token="var(--c-series-a)" label="รถยนต์" value={fmtNum(hovered.cars)} />
          <TipRow token="var(--c-series-b)" label="มอเตอร์ไซค์" value={fmtNum(hovered.motorcycles)} />
        </ChartTip>
      )}
      <table className="sr-only">
        <caption>รถเฉลี่ยต่อกล้องรายชั่วโมง กทม.</caption>
        <thead>
          <tr>
            <th scope="col">ช่วงเวลา</th>
            <th scope="col">รถยนต์</th>
            <th scope="col">มอเตอร์ไซค์</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.hour ?? r.t}>
              <th scope="row">{r.label}</th>
              <td>{r.cars}</td>
              <td>{r.motorcycles}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// City-wide average per camera per hour, from the BMA hourly trends.
export default function BmaLineCard({ hourly }) {
  const lines = useMemo(() => bmaHourlyLines(hourly), [hourly]);
  const boxRef = useRef(null);
  const width = useChartWidth(boxRef);
  // The big number is the last hour that has finished: the hour still running is only partly counted
  const now = new Date();
  const thisHourStart = new Date(now.getFullYear(), now.getMonth(), now.getDate(), now.getHours()).getTime() / 1000;
  const last = lines[lines.length - 1];
  const latest = lines.length >= 2 && last.t >= thisHourStart ? lines[lines.length - 2] : last;

  return (
    <section aria-labelledby="bma-line-title" className="dash-card p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 id="bma-line-title" className="text-base font-semibold text-[var(--c-ink)]">
            รถเฉลี่ยต่อกล้อง กทม.
          </h3>
          {latest && (
            <p className="mt-1 flex flex-wrap items-baseline gap-2">
              <span className="num text-[28px] font-bold leading-9 text-[var(--c-ink)]">
                {fmtNum(Math.round((latest.cars + latest.motorcycles) * 10) / 10)}
              </span>
              <span className="text-xs text-[var(--c-muted)]">คันต่อกล้อง · ล่าสุด {latest.label}</span>
            </p>
          )}
        </div>
        <SeriesLegend items={SERIES} />
      </div>
      <div className="mt-4" ref={boxRef}>
        {lines.length ? <BmaLines rows={lines} width={width} /> : <EmptyBlock text="ยังไม่มีข้อมูลรายชั่วโมงของ กทม." />}
      </div>
    </section>
  );
}
