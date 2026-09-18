import { useEffect, useMemo, useState } from 'react';
import { fetchWaterForecast } from '../../lib/api.js';
import { Card, SectionHeader, Badge, Segmented, Skeleton, EmptyState, ErrorState, FOCUS } from '../dashboard/ui.jsx';
import { fmtTime, fmtDay } from '../dashboard/format.js';

const W = 720;
const H = 240;
const PAD = { l: 44, r: 14, t: 14, b: 30 };
const OBS = '#2563eb';
const EST = '#475569';
const BANK = '#dc2626';
const WARN = '#d97706';

const fmtM = (v) => (v == null ? '–' : `${v.toFixed(2)} ม.`);
const fmtWhen = (ts) => `${fmtDay(ts * 1000)} ${fmtTime(ts)} น.`;

function Legend({ items }) {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
      {items.map((it) => (
        <li key={it.label} className="inline-flex items-center gap-1.5">
          <svg width="22" height="8" aria-hidden="true">
            <line x1="1" x2="21" y1="4" y2="4" stroke={it.color} strokeWidth="2" strokeDasharray={it.dash || undefined} />
          </svg>
          {it.label}
        </li>
      ))}
    </ul>
  );
}

// Station selector + one chart: observed level (48 h) followed by the official HII forecast
// or, where HII has none, the local tide + trend outlook.
export default function ForecastChart({ stations, stationId, onPickStation, anchorRef }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(false);
  const [range, setRange] = useState('48h');
  const [hover, setHover] = useState(null);

  useEffect(() => {
    if (!stationId) return;
    let alive = true;
    setLoading(true);
    setHover(null);
    fetchWaterForecast(stationId)
      .then((d) => {
        if (!alive) return;
        setData(d);
        setError(false);
      })
      .catch(() => alive && setError(true))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [stationId]);

  const station = stations.find((s) => s.id === String(stationId));
  const hasOfficial = !!data?.official?.length;
  useEffect(() => {
    if (!hasOfficial && range === '7d') setRange('48h');
  }, [hasOfficial, range]);

  const chart = useMemo(() => {
    if (!data?.observed?.length) return null;
    const now = data.latest?.t ?? data.observed[data.observed.length - 1].t;
    const horizon = range === '7d' ? 7 * 86400 : 48 * 3600;
    const future = (data.official?.length ? data.official : data.estimate) || [];
    const obs = data.observed;
    const fut = future.filter((p) => p.t <= now + horizon);
    const t0 = obs[0].t;
    const t1 = fut.length ? fut[fut.length - 1].t : now;
    const all = [...obs, ...fut];
    const levels = data.levels || {};
    const ref = [levels.bank, levels.warning].filter((v) => v != null);
    let lo = Math.min(...all.map((p) => p.v), ...ref);
    let hi = Math.max(...all.map((p) => p.v), ...ref);
    const padY = Math.max(0.15, (hi - lo) * 0.12);
    lo -= padY;
    hi += padY;
    const x = (t) => PAD.l + ((W - PAD.l - PAD.r) * (t - t0)) / Math.max(1, t1 - t0);
    const y = (v) => PAD.t + (H - PAD.t - PAD.b) * (1 - (v - lo) / (hi - lo));
    const path = (pts) => pts.map((p, i) => `${i ? 'L' : 'M'}${x(p.t).toFixed(1)},${y(p.v).toFixed(1)}`).join(' ');
    // y ticks at "nice" 0.25 / 0.5 / 1 m steps
    const span = hi - lo;
    const step = span > 4 ? 1 : span > 2 ? 0.5 : 0.25;
    const ticks = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) ticks.push(+v.toFixed(2));
    // x ticks every 12 h (48 h view) or every day (7 d view)
    const xs = [];
    const stepX = range === '7d' ? 86400 : 12 * 3600;
    const first = Math.ceil(t0 / 3600) * 3600;
    for (let t = first; t <= t1; t += 3600) if (new Date(t * 1000).getHours() % (stepX / 3600) === 0) xs.push(t);
    return { now, obs, fut, t0, t1, lo, hi, x, y, path, ticks, xs, levels, isOfficial: !!data.official?.length };
  }, [data, range]);

  const onMove = (e) => {
    if (!chart) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * W;
    const t = chart.t0 + ((px - PAD.l) / (W - PAD.l - PAD.r)) * (chart.t1 - chart.t0);
    const pool = t <= chart.now ? chart.obs : chart.fut;
    if (!pool.length) return;
    let best = pool[0];
    for (const p of pool) if (Math.abs(p.t - t) < Math.abs(best.t - t)) best = p;
    setHover({ ...best, future: t > chart.now });
  };

  const shown = hover ?? (data?.latest ? { ...data.latest, future: false } : null);
  const next = data?.extremes?.find((e) => e.t > (data.latest?.t ?? 0));
  const peak = data?.peak;
  const bank = data?.levels?.bank;

  return (
    <Card aria-labelledby="water-forecast-title" className="p-5 scroll-mt-4" ref={anchorRef}>
      <SectionHeader
        id="water-forecast-title"
        title="แนวโน้มระดับน้ำรายสถานี"
        description="เส้นทึบ = ค่าที่วัดได้ 48 ชม. ล่าสุด · เส้นประ = คาดการณ์ · หน่วย ม.รทก. (เมตรเหนือระดับน้ำทะเลปานกลาง)"
        action={
          <div className="flex flex-wrap items-center gap-2">
            <label htmlFor="water-station" className="sr-only">
              เลือกสถานี
            </label>
            <select
              id="water-station"
              value={stationId || ''}
              onChange={(e) => onPickStation(e.target.value)}
              className={`h-8 rounded-lg border border-slate-300 bg-white px-2 text-xs text-slate-800 max-w-[260px] ${FOCUS}`}
            >
              {stations.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.official_forecast ? '[7 วัน] ' : ''}
                  {s.name} · {s.province}
                </option>
              ))}
            </select>
            <Segmented label="ช่วงคาดการณ์" value={range} onChange={setRange} options={hasOfficial ? [['48h', '48 ชม.'], ['7d', '7 วัน']] : [['48h', '48 ชม.']]} />
          </div>
        }
      />

      {/* Headline numbers */}
      <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Stat label={shown?.future ? `คาดการณ์ ${fmtWhen(shown.t)}` : shown ? `วัดล่าสุด ${fmtWhen(shown.t)}` : 'ระดับล่าสุด'} value={fmtM(shown?.v)} loading={loading && !data} />
        <Stat
          label="ระดับตลิ่ง"
          value={fmtM(bank)}
          sub={bank != null && shown?.v != null ? (shown.v >= bank ? `ล้นตลิ่ง ${(shown.v - bank).toFixed(2)} ม.` : `ต่ำกว่าตลิ่ง ${(bank - shown.v).toFixed(2)} ม.`) : ''}
          tone={bank != null && shown?.v != null && shown.v >= bank ? 'red' : undefined}
          loading={loading && !data}
        />
        <Stat label={next ? (next.kind === 'high' ? 'น้ำขึ้นสูงสุดถัดไป' : 'น้ำลงต่ำสุดถัดไป') : 'จุดสูง/ต่ำถัดไป'} value={fmtM(next?.v)} sub={next ? fmtWhen(next.t) : ''} loading={loading && !data} />
        <Stat
          label={chart?.isOfficial ? 'สูงสุดใน 7 วัน (สสน.)' : 'สูงสุดใน 48 ชม. (ประเมิน)'}
          value={fmtM(peak?.v)}
          sub={peak ? fmtWhen(peak.t) : ''}
          tone={bank != null && peak?.v != null && peak.v >= bank ? 'red' : undefined}
          loading={loading && !data}
        />
      </div>

      <div className="mt-4">
        {error && !data ? (
          <ErrorState message="โหลดข้อมูลคาดการณ์ไม่สำเร็จ" />
        ) : !data && loading ? (
          <Skeleton className="h-56 w-full" />
        ) : !chart ? (
          <EmptyState title="สถานีนี้ยังไม่มีข้อมูลย้อนหลัง" description="ลองเลือกสถานีอื่น" />
        ) : (
          <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto select-none" onMouseMove={onMove} onMouseLeave={() => setHover(null)} role="img" aria-label="กราฟระดับน้ำที่วัดได้และคาดการณ์">
            {chart.ticks.map((v) => (
              <g key={v}>
                <line x1={PAD.l} x2={W - PAD.r} y1={chart.y(v)} y2={chart.y(v)} stroke="#e2e8f0" strokeWidth="1" />
                <text x={PAD.l - 8} y={chart.y(v) + 3.5} textAnchor="end" fontSize="10" fill="#64748b">
                  {v.toFixed(2)}
                </text>
              </g>
            ))}
            {chart.xs.map((t) => (
              <g key={t}>
                <line x1={chart.x(t)} x2={chart.x(t)} y1={PAD.t} y2={H - PAD.b} stroke="#f1f5f9" strokeWidth="1" />
                <text x={chart.x(t)} y={H - 8} textAnchor="middle" fontSize="10" fill="#64748b">
                  {range === '7d' ? fmtDay(t * 1000) : `${fmtDay(t * 1000)} ${fmtTime(t)}`}
                </text>
              </g>
            ))}
            {/* future shading */}
            <rect x={chart.x(chart.now)} y={PAD.t} width={Math.max(0, W - PAD.r - chart.x(chart.now))} height={H - PAD.t - PAD.b} fill="#f8fafc" />
            {chart.levels.bank != null && (
              <g>
                <line x1={PAD.l} x2={W - PAD.r} y1={chart.y(chart.levels.bank)} y2={chart.y(chart.levels.bank)} stroke={BANK} strokeWidth="1.5" strokeDasharray="6 4" />
                <text x={W - PAD.r - 4} y={chart.y(chart.levels.bank) - 4} textAnchor="end" fontSize="10" fill={BANK}>
                  ตลิ่ง {chart.levels.bank.toFixed(2)}
                </text>
              </g>
            )}
            {chart.levels.warning != null && (
              <g>
                <line x1={PAD.l} x2={W - PAD.r} y1={chart.y(chart.levels.warning)} y2={chart.y(chart.levels.warning)} stroke={WARN} strokeWidth="1" strokeDasharray="2 4" />
                <text x={PAD.l + 4} y={chart.y(chart.levels.warning) - 4} fontSize="10" fill={WARN}>
                  เฝ้าระวัง {chart.levels.warning.toFixed(2)}
                </text>
              </g>
            )}
            <path d={chart.path(chart.obs)} fill="none" stroke={OBS} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
            {chart.fut.length > 0 && (
              <path d={chart.path([chart.obs[chart.obs.length - 1], ...chart.fut])} fill="none" stroke={chart.isOfficial ? OBS : EST} strokeWidth="2" strokeDasharray="5 4" strokeLinejoin="round" strokeLinecap="round" />
            )}
            <line x1={chart.x(chart.now)} x2={chart.x(chart.now)} y1={PAD.t} y2={H - PAD.b} stroke="#94a3b8" strokeWidth="1" />
            <text x={chart.x(chart.now) + 4} y={PAD.t + 10} fontSize="10" fill="#64748b">
              ตอนนี้
            </text>
            {hover && (
              <g>
                <line x1={chart.x(hover.t)} x2={chart.x(hover.t)} y1={PAD.t} y2={H - PAD.b} stroke="#94a3b8" strokeWidth="1" strokeDasharray="3 3" />
                <circle cx={chart.x(hover.t)} cy={chart.y(hover.v)} r="4" fill={hover.future && !chart.isOfficial ? EST : OBS} stroke="#fff" strokeWidth="2" />
              </g>
            )}
          </svg>
        )}
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <Legend
          items={[
            { label: 'วัดได้จริง', color: OBS },
            chart?.isOfficial
              ? { label: 'คาดการณ์ สสน. 7 วัน', color: OBS, dash: '5 4' }
              : { label: data?.estimate_model === 'recession' ? 'ประเมินการลดระดับหลังฝน 48 ชม.' : 'ประเมินจากน้ำขึ้นน้ำลง + แนวโน้ม 48 ชม.', color: EST, dash: '5 4' },
            { label: 'ระดับตลิ่ง', color: BANK, dash: '6 4' },
            ...(chart?.levels?.warning != null ? [{ label: 'ระดับเฝ้าระวัง', color: WARN, dash: '2 4' }] : []),
          ]}
        />
        {data && (
          <div className="flex items-center gap-2">
            {data.source === 'hii' ? (
              <Badge tone="blue">คาดการณ์ทางการ สสน.</Badge>
            ) : data.source === 'local' ? (
              <Badge>โมเดลประเมินในเครื่อง{data.estimate_rmse != null ? ` · ค่าคลาดเคลื่อน ±${data.estimate_rmse.toFixed(2)} ม.` : ''}</Badge>
            ) : (
              <Badge>ไม่มีข้อมูลคาดการณ์</Badge>
            )}
            {data.stale && <Badge tone="yellow">ข้อมูลเก่า</Badge>}
          </div>
        )}
      </div>
      {station && (
        <p className="mt-2 text-xs text-slate-500">
          {station.river || 'สถานีโทรมาตร'} · {station.district ? `${station.district} ` : ''}
          {station.province}
          {data?.source === 'local' &&
            (data.estimate_model === 'recession'
              ? ' · สถานีนี้ไม่ขึ้นกับน้ำทะเล ค่าประเมินสมมติว่าไม่มีฝนตกเพิ่มและระดับค่อย ๆ ลดกลับสู่ระดับก่อนฝน'
              : ' · ค่าประเมินใช้ข้อมูลย้อนหลัง 3 วันของสถานีนี้เอง ไม่รวมฝนที่ตกใหม่หรือการเปิด-ปิดประตูระบายน้ำ')}
        </p>
      )}
    </Card>
  );
}

function Stat({ label, value, sub, tone, loading }) {
  return (
    <div className={`rounded-lg border px-3 py-2.5 ${tone === 'red' ? 'border-red-200 bg-red-50' : 'border-slate-200 bg-slate-50'}`}>
      <p className="text-xs text-slate-600 truncate">{label}</p>
      {loading ? <Skeleton className="h-6 w-16 mt-1" /> : <p className={`text-lg font-semibold tabular-nums leading-7 ${tone === 'red' ? 'text-red-700' : 'text-slate-900'}`}>{value}</p>}
      {sub && <p className="text-xs text-slate-500 truncate">{sub}</p>}
    </div>
  );
}
