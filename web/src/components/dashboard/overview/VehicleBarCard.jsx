import { useEffect, useRef, useState } from 'react';
import { fetchAIHistory } from '../../../lib/api.js';
import { sumVehicleHistory, thinLabels } from '../../../lib/overviewData.js';
import { fmtNum } from '../format.js';
import { niceMax } from './chartMath.js';
import { ChartTip, EmptyBlock, SeriesLegend, TipRow, useChartWidth } from './ChartParts.jsx';

const H = 240;
const PAD = { l: 36, r: 8, t: 12, b: 26 };
const SERIES = [
  { label: 'รถยนต์', token: 'var(--c-series-a)' },
  { label: 'มอเตอร์ไซค์', token: 'var(--c-series-b)' },
];

// Grouped thin bars per time bucket: cars and motorcycles side by side.
export function VehicleBars({ rows, width = 640 }) {
  const [hover, setHover] = useState(null);
  if (!rows.length || rows.every((r) => !r.cars && !r.motorcycles)) {
    return <EmptyBlock text="ยังไม่มีข้อมูลรถในช่วงนี้" />;
  }

  // one SVG unit is one CSS px: the viewBox is the measured width
  const W = width;
  const n = rows.length;
  const top = niceMax(Math.max(...rows.flatMap((r) => [r.cars, r.motorcycles])));
  const plotW = W - PAD.l - PAD.r;
  const plotH = H - PAD.t - PAD.b;
  const slot = plotW / n;
  // 6 wide bars with 3 between them; when the buckets do not fit, both shrink (bar never below 2)
  const fit = Math.min(1, plotW / (n * 15));
  const barW = Math.max(2, 6 * fit);
  const gap = Math.max(1, 3 * fit);
  const rx = Math.min(3, barW / 2);
  const yOf = (v) => PAD.t + plotH * (1 - v / top);
  const hOf = (v) => plotH * (v / top);
  const cx = (i) => PAD.l + slot * i + slot / 2;
  const step = thinLabels(n, W < 480 ? 6 : 12);
  const ticks = [0, 1, 2, 3, 4].map((k) => Math.round((top * k) / 4));
  const hovered = hover != null ? rows[hover] : null;
  const hoverPct = hover != null ? (cx(hover) / W) * 100 : 0;

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        height={H}
        className="block select-none"
        role="img"
        aria-label={`กราฟรถที่ผ่านกล้อง AI ${n} ช่วงเวลา`}
        onMouseLeave={() => setHover(null)}
      >
        {ticks.map((v, k) => (
          <g key={k}>
            <line x1={PAD.l} x2={W - PAD.r} y1={yOf(v)} y2={yOf(v)} stroke="var(--c-border)" strokeWidth="1" />
            <text x={PAD.l - 6} y={yOf(v) + 4} textAnchor="end" fontSize="12" fill="var(--c-muted)">
              {fmtNum(v)}
            </text>
          </g>
        ))}
        {hover != null && (
          <rect x={PAD.l + slot * hover} y={PAD.t} width={slot} height={plotH} fill="var(--c-raised)" />
        )}
        {rows.map((r, i) => (
          <g key={r.key}>
            <rect x={cx(i) - gap / 2 - barW} y={yOf(r.cars)} width={barW} height={hOf(r.cars)} rx={rx} fill="var(--c-series-a)" />
            <rect x={cx(i) + gap / 2} y={yOf(r.motorcycles)} width={barW} height={hOf(r.motorcycles)} rx={rx} fill="var(--c-series-b)" />
          </g>
        ))}
        {rows.map((r, i) =>
          i % step === 0 ? (
            <text key={r.key} x={cx(i)} y={H - 8} textAnchor="middle" fontSize="12" fill="var(--c-muted)">
              {r.label}
            </text>
          ) : null,
        )}
        {rows.map((r, i) => (
          <rect
            key={`hit-${r.key}`}
            x={PAD.l + slot * i}
            y={PAD.t}
            width={slot}
            height={plotH + PAD.b}
            fill="transparent"
            tabIndex={0}
            aria-label={`${r.label} รถยนต์ ${fmtNum(r.cars)} คัน มอเตอร์ไซค์ ${fmtNum(r.motorcycles)} คัน`}
            onMouseEnter={() => setHover(i)}
            onFocus={() => setHover(i)}
            onBlur={() => setHover(null)}
            className="outline-none focus-visible:stroke-[var(--c-primary)] focus-visible:stroke-2"
          />
        ))}
      </svg>
      {hovered && (
        <ChartTip xPct={hoverPct}>
          <p className="font-semibold">{hovered.label}</p>
          <TipRow token="var(--c-series-a)" label="รถยนต์" value={fmtNum(hovered.cars)} />
          <TipRow token="var(--c-series-b)" label="มอเตอร์ไซค์" value={fmtNum(hovered.motorcycles)} />
        </ChartTip>
      )}
      <table className="sr-only">
        <caption>จำนวนรถที่ผ่านกล้อง AI ตามช่วงเวลา</caption>
        <thead>
          <tr>
            <th scope="col">ช่วงเวลา</th>
            <th scope="col">รถยนต์</th>
            <th scope="col">มอเตอร์ไซค์</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key}>
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

// Vehicles per bucket for the chosen range. Rows go up through onRows so the page can offer a CSV download.
export default function VehicleBarCard({ range, onRows }) {
  const [state, setState] = useState({ loading: true, rows: [], error: false });
  const boxRef = useRef(null);
  const width = useChartWidth(boxRef);

  useEffect(() => {
    let alive = true;
    setState((s) => ({ ...s, loading: true }));
    onRows?.([]);
    fetchAIHistory({ range })
      .then((h) => {
        const rows = sumVehicleHistory(h);
        if (!alive) return;
        setState({ loading: false, rows, error: false });
        onRows?.(rows);
      })
      .catch(() => {
        if (!alive) return;
        setState({ loading: false, rows: [], error: true });
        onRows?.([]);
      });
    return () => {
      alive = false;
    };
    // onRows is read on each load; it is not a reason to refetch
  }, [range]);

  return (
    <section aria-labelledby="vehicle-bar-title" className="dash-card p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <h3 id="vehicle-bar-title" className="text-base font-semibold text-[var(--c-ink)]">
          รถที่ผ่านกล้อง AI
        </h3>
        <SeriesLegend items={SERIES} />
      </div>
      <div className="mt-4" ref={boxRef}>
        {state.loading ? (
          <div className="h-56 rounded-xl bg-[var(--c-raised)] animate-pulse" aria-hidden="true" />
        ) : state.error ? (
          <EmptyBlock text="ยังโหลดข้อมูลรถไม่ได้ ลองกดรีเฟรชอีกครั้ง" />
        ) : (
          <VehicleBars rows={state.rows} width={width} />
        )}
      </div>
    </section>
  );
}
