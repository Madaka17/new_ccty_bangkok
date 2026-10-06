import { useEffect, useMemo, useRef, useState } from 'react';
import { Card, SectionHeader, Badge, Segmented, Skeleton, EmptyState, Truncate } from '../dashboard/ui.jsx';
import { StatTile, StatusBanner } from '../dashboard/primitives.jsx';
import { fmtNum, fmtTime } from '../dashboard/format.js';

const PERIODS = [
  ['day', 'รายวัน'],
  ['week', 'รายสัปดาห์'],
  ['month', 'รายเดือน'],
];
const MODES = [
  ['grouped', 'แยกตามประเภทรถ'],
  ['stacked', 'ยอดรวม'],
];
const TYPES = [
  { key: 'cars', name: 'รถยนต์', short: 'รถยนต์', bar: 'bg-blue-600 dark:bg-blue-500', text: 'text-blue-700 dark:text-blue-300', dot: 'bg-blue-500' },
  { key: 'motorcycles', name: 'มอเตอร์ไซค์', short: 'มอไซ', bar: 'bg-amber-500 dark:bg-amber-400', text: 'text-amber-700 dark:text-amber-300', dot: 'bg-amber-500' },
  { key: 'trucks', name: 'บรรทุก/บัส', short: 'บรรทุก', bar: 'bg-slate-500 dark:bg-slate-400', text: 'text-slate-600 dark:text-slate-300', dot: 'bg-slate-500' },
];
const TYPE_FILTERS = [
  ['all', 'ทั้งหมด'],
  ...TYPES.map((t) => [t.key, <span key={t.key} className="inline-flex items-center gap-1.5"><span aria-hidden="true" className={`w-2 h-2 rounded-full ${t.dot}`} />{t.short}</span>]),
];
const pct = (v) => (v == null ? '–' : `${v >= 0 ? '+' : ''}${v}%`);
const diffTone = (d) => (d == null ? 'neutral' : d > 0 ? 'red' : d < 0 ? 'green' : 'neutral');

function fmtCompact(n) {
  if (n == null || n === 0) return '0';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 10_000) return `${Math.round(n / 1_000)}k`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return fmtNum(n);
}

function CountdownText({ ts }) {
  const m = Math.max(0, Math.round((ts * 1000 - Date.now()) / 60000));
  return <>{m < 60 ? `อีก ${m} นาที` : `อีก ${Math.floor(m / 60)} ชม. ${m % 60} นาที`}</>;
}

// Day / week / month comparison built only from archived cycles (no estimates).
export default function BmaComparison({ data, period, onPeriod, cycle, files, loading }) {
  const [hover, setHover] = useState(null);
  const [chartMode, setChartMode] = useState('grouped'); // 'grouped' | 'stacked'
  const [filterType, setFilterType] = useState('all'); // 'all' | 'cars' | 'motorcycles' | 'trucks'

  const m = data?.metrics;
  const chart = data?.chart_data || [];

  const max = useMemo(() => {
    if (!chart.length) return 1;
    if (chartMode === 'stacked') {
      return Math.max(1, ...chart.map((c) => c.total || 0));
    }
    if (filterType === 'cars') return Math.max(1, ...chart.map((c) => c.cars || 0));
    if (filterType === 'motorcycles') return Math.max(1, ...chart.map((c) => c.motorcycles || 0));
    if (filterType === 'trucks') return Math.max(1, ...chart.map((c) => c.trucks || 0));
    return Math.max(1, ...chart.flatMap((c) => [c.cars || 0, c.motorcycles || 0, c.trucks || 0]));
  }, [chart, chartMode, filterType]);

  const shown = hover ?? chart[chart.length - 1];

  // Many periods scroll sideways: open at the newest, on the right
  const scrollRef = useRef(null);
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollLeft = el.scrollWidth;
  }, [chart, chartMode, filterType]);

  return (
    <div className="flex flex-col gap-4">
      {cycle && (
        <StatusBanner tone="blue" label={`เก็บยอดทุก ${cycle.cycle_minutes} นาที`}>
          ยอดรอบนี้ <b>{fmtNum(cycle.cycle?.total)}</b> คัน (เริ่ม {fmtTime(cycle.cycle_started)} น.) · เก็บยอดครั้งถัดไป <b>{fmtTime(cycle.next_reset)} น.</b> (<CountdownText ts={cycle.next_reset} />)
          {cycle.last_error && <span className="text-red-700"> · เก็บยอดครั้งล่าสุดไม่สำเร็จ</span>}
        </StatusBanner>
      )}

      <Card className="p-5">
        <SectionHeader
          title={data?.title || 'เทียบจำนวนรถ'}
          description="ตัวเลขคือรถที่กล้องเห็นรวมทุกรอบในช่วงนั้น ใช้ดูว่ารถมากขึ้นหรือน้อยลง"
          action={<Segmented label="ช่วงเวลา" value={period} onChange={onPeriod} options={PERIODS} />}
        />
        <div className="mt-4 grid grid-cols-2 lg:grid-cols-4 gap-3">
          <StatTile
            label={`รวม (${data?.curr_label || 'ช่วงนี้'})`}
            value={m ? `${fmtNum(m.current_total)} คัน` : '–'}
            sub={m ? `${data.prev_label}: ${m.previous_total == null ? 'ยังไม่มีข้อมูล' : `${fmtNum(m.previous_total)} คัน`}` : ''}
            badge={m ? <Badge tone={diffTone(m.diff)}>{pct(m.diff_pct)}</Badge> : null}
            loading={loading}
            tone="blue"
          />
          <StatTile label="รถยนต์" value={m ? fmtNum(m.current_cars) : '–'} sub={m ? `${data.prev_label}: ${fmtNum(m.prev_cars)}` : ''} loading={loading} />
          <StatTile label="มอเตอร์ไซค์" value={m ? fmtNum(m.current_motos) : '–'} sub={m ? `${data.prev_label}: ${fmtNum(m.prev_motos)}` : ''} loading={loading} />
          <StatTile label="บรรทุก / บัส" value={m ? fmtNum(m.current_trucks) : '–'} sub={m ? `${data.prev_label}: ${fmtNum(m.prev_trucks)}` : ''} loading={loading} />
        </div>

        {/* Separated bars per vehicle type */}
        <div className="mt-5">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 flex-wrap pb-3 border-b border-slate-100 dark:border-slate-800">
            <p className="text-[13px] text-slate-600 dark:text-slate-300">
              {shown ? (
                <>
                  <b className="text-slate-900 dark:text-slate-100">{shown.label}</b> · {fmtNum(shown.total)} คัน · รถยนต์ {fmtNum(shown.cars)} · มอเตอร์ไซค์ {fmtNum(shown.motorcycles)} · บรรทุก {fmtNum(shown.trucks)}
                </>
              ) : (
                'ยังไม่มีข้อมูลที่เก็บไว้'
              )}
            </p>

            {/* View mode, and which type to show (the dots are the chart's legend) */}
            <div className="flex items-center gap-2 flex-wrap">
              <Segmented label="แบบกราฟ" value={chartMode} onChange={setChartMode} options={MODES} />
              {chartMode === 'grouped' && <Segmented label="ประเภทรถ" value={filterType} onChange={setFilterType} options={TYPE_FILTERS} />}
            </div>
          </div>

          {loading ? (
            <Skeleton className="mt-3 h-56 w-full" />
          ) : !chart.length ? (
            <div className="mt-3">
              <EmptyState title="ยังไม่มีข้อมูลให้เทียบ" description="ระบบจะเก็บยอดแรกเมื่อครบรอบ" />
            </div>
          ) : chartMode === 'grouped' ? (
            /* GROUPED BARS: one column per period, scrolls sideways inside the card when there are many,
               opened at the newest; the date sits under its bars like an axis */
            <div ref={scrollRef} className="mt-4 overflow-x-auto scroll-soft pb-1" onMouseLeave={() => setHover(null)}>
              <div className="grid grid-flow-col auto-cols-[minmax(92px,1fr)] gap-1 border-b border-slate-200 dark:border-slate-800">
                {chart.map((c) => {
                  const isCur = c.period_key === data.current_key;
                  const bars = TYPES.filter((t) => filterType === 'all' || filterType === t.key);
                  return (
                    <button
                      key={c.period_key}
                      type="button"
                      onMouseEnter={() => setHover(c)}
                      onFocus={() => setHover(c)}
                      aria-label={`${c.label} ${fmtNum(c.total)} คัน`}
                      className={`cursor-default flex flex-col items-center gap-1.5 rounded-lg px-1.5 pt-2 pb-2.5 transition-colors ${
                        isCur ? 'bg-blue-50/60 dark:bg-blue-950/25' : 'hover:bg-slate-50 dark:hover:bg-slate-800/40'
                      }`}
                    >
                      <div className="w-full h-44 flex items-end justify-center gap-1">
                        {bars.map((t) => (
                          <div key={t.key} className={`flex-1 ${bars.length === 1 ? 'max-w-[40px]' : 'max-w-[24px]'} flex flex-col items-center`}>
                            <span className={`text-[10px] font-semibold tabular-nums whitespace-nowrap mb-1 ${t.text}`}>{fmtCompact(c[t.key])}</span>
                            <div
                              style={{ height: `${Math.max(3, Math.round(((c[t.key] || 0) / max) * 150))}px` }}
                              className={`w-full rounded-t ${t.bar}`}
                              title={`${t.name}: ${fmtNum(c[t.key])} คัน (${Math.round(((c[t.key] || 0) / (c.total || 1)) * 100)}%)`}
                            />
                          </div>
                        ))}
                      </div>
                      <span className={`text-xs leading-tight text-center ${isCur ? 'font-semibold text-blue-700 dark:text-blue-300' : 'font-medium text-slate-700 dark:text-slate-300'}`}>
                        {c.label}
                        {isCur && <span className="block text-[11px]">{data.curr_label}</span>}
                      </span>
                      <span className="text-[11px] text-slate-500 tabular-nums">รวม {fmtCompact(c.total)}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          ) : (
            /* STACKED BARS: Stacked view with totals */
            <div className="mt-3 h-48 flex items-end gap-2 border-b border-slate-200 dark:border-slate-800 pb-1" onMouseLeave={() => setHover(null)}>
              {chart.map((c) => {
                const isCur = c.period_key === data.current_key;
                return (
                  <button
                    key={c.period_key}
                    type="button"
                    onMouseEnter={() => setHover(c)}
                    onFocus={() => setHover(c)}
                    aria-label={`${c.label} ${c.total} คัน`}
                    className="cursor-default flex-1 h-full flex flex-col justify-end items-center gap-1 min-w-0"
                  >
                    <span className="text-[10px] font-bold text-slate-700 dark:text-slate-300 tabular-nums">
                      {fmtCompact(c.total)}
                    </span>
                    <div className={`w-full max-w-[44px] rounded-t-md overflow-hidden flex flex-col-reverse ${isCur ? 'ring-2 ring-blue-600 ring-offset-1' : ''}`} style={{ height: `${Math.max(4, (c.total / max) * 100)}%` }}>
                      <div className="bg-blue-600 w-full" style={{ height: `${(c.cars / (c.total || 1)) * 100}%` }} title={`รถยนต์: ${fmtNum(c.cars)}`} />
                      <div className="bg-amber-500 w-full" style={{ height: `${(c.motorcycles / (c.total || 1)) * 100}%` }} title={`มอเตอร์ไซค์: ${fmtNum(c.motorcycles)}`} />
                      <div className="bg-slate-500 w-full" style={{ height: `${(c.trucks / (c.total || 1)) * 100}%` }} title={`บรรทุก: ${fmtNum(c.trucks)}`} />
                    </div>
                    <span className={`text-[11px] truncate max-w-full ${isCur ? 'font-semibold text-blue-700 dark:text-blue-400' : 'text-slate-500'}`}>{c.label}</span>
                  </button>
                );
              })}
            </div>
          )}

          {/* Detailed Vehicle Type Breakdown Table */}
          {chart.length > 0 && (
            <div className="mt-5 pt-4 border-t border-slate-100 dark:border-slate-800">
              <div className="flex items-center justify-between mb-2.5">
                <span className="text-xs font-semibold text-slate-800 dark:text-slate-200">
                  จำนวนรถแต่ละประเภท
                </span>
                <span className="text-[11px] text-slate-500">หน่วย: คัน</span>
              </div>
              <div className="overflow-x-auto rounded-xl border border-cream-200 dark:border-slate-800">
                <table className="w-full text-xs text-left">
                  <thead>
                    <tr className="bg-cream-100/60 dark:bg-slate-800/80 text-slate-600 dark:text-slate-400 border-b border-cream-200 dark:border-slate-800">
                      <th className="py-2.5 px-3 font-medium">ช่วงเวลา</th>
                      <th className="py-2.5 px-3 text-right font-medium">ยอดรวมทุกประเภท</th>
                      <th className="py-2.5 px-3 text-right font-medium text-blue-600 dark:text-blue-400">🚙 รถยนต์</th>
                      <th className="py-2.5 px-3 text-right font-medium text-amber-600 dark:text-amber-400">🛵 มอเตอร์ไซค์</th>
                      <th className="py-2.5 px-3 text-right font-medium text-slate-600 dark:text-slate-300">🚚 บรรทุก/บัส</th>
                      <th className="py-2.5 px-3 text-right font-medium text-slate-500">จำนวนรอบที่นับ</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-cream-100 dark:divide-slate-800 bg-white dark:bg-slate-900/60">
                    {chart.map((c) => {
                      const isCur = c.period_key === data.current_key;
                      const cTot = c.total || 1;
                      return (
                        <tr key={c.period_key} className={isCur ? 'bg-blue-50/40 dark:bg-blue-950/20 font-medium' : ''}>
                          <td className="py-2.5 px-3">
                            <span className="font-semibold text-slate-900 dark:text-slate-100">{c.label}</span>
                            {isCur && <span className="ml-1.5 text-[10px] text-blue-600 dark:text-blue-400">({data.curr_label})</span>}
                          </td>
                          <td className="py-2.5 px-3 text-right font-bold tabular-nums text-slate-900 dark:text-slate-100">
                            {fmtNum(c.total)}
                          </td>
                          <td className="py-2.5 px-3 text-right tabular-nums text-blue-700 dark:text-blue-300">
                            {fmtNum(c.cars)} <span className="text-[10px] text-slate-500">({Math.round((c.cars / cTot) * 100)}%)</span>
                          </td>
                          <td className="py-2.5 px-3 text-right tabular-nums text-amber-700 dark:text-amber-300">
                            {fmtNum(c.motorcycles)} <span className="text-[10px] text-slate-500">({Math.round((c.motorcycles / cTot) * 100)}%)</span>
                          </td>
                          <td className="py-2.5 px-3 text-right tabular-nums text-slate-700 dark:text-slate-300">
                            {fmtNum(c.trucks)} <span className="text-[10px] text-slate-500">({Math.round((c.trucks / cTot) * 100)}%)</span>
                          </td>
                          <td className="py-2.5 px-3 text-right tabular-nums text-slate-500">
                            {c.cycles} รอบ
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </Card>

      <Card className="p-5">
        <SectionHeader title="รายถนน" description={`${data?.curr_label || 'ช่วงนี้'} เทียบกับ ${data?.prev_label || 'ช่วงก่อน'} · เรียงจากถนนที่รถมากที่สุด`} />
        <div className="mt-3 overflow-x-auto">
          {loading ? (
            <Skeleton className="h-40 w-full" />
          ) : !data?.road_comparisons?.length ? (
            <EmptyState title="ยังไม่มีข้อมูลรายถนน" />
          ) : (
            <table className="w-full text-sm min-w-[620px]">
              <thead>
                <tr className="text-xs text-slate-500 border-b border-slate-200">
                  <th className="text-left font-medium py-2 pr-2">ถนน</th>
                  <th className="text-right font-medium py-2 pr-2">{data.curr_label}</th>
                  <th className="text-right font-medium py-2 pr-2">{data.prev_label}</th>
                  <th className="text-right font-medium py-2 pr-2">เปลี่ยนแปลง</th>
                  <th className="text-right font-medium py-2 pr-2">รถยนต์</th>
                  <th className="text-right font-medium py-2 pr-2">มอไซ</th>
                  <th className="text-right font-medium py-2">บรรทุก</th>
                </tr>
              </thead>
              <tbody>
                {data.road_comparisons.map((r) => (
                  <tr key={r.road} className="border-b border-slate-100">
                    <td className="py-2 pr-2 max-w-[260px]">
                      <Truncate text={r.road} className="font-medium text-slate-900" />
                    </td>
                    <td className="py-2 pr-2 text-right tabular-nums font-semibold text-slate-900">{fmtNum(r.current_volume)}</td>
                    <td className="py-2 pr-2 text-right tabular-nums text-slate-600">{r.previous_volume == null ? '–' : fmtNum(r.previous_volume)}</td>
                    <td className="py-2 pr-2 text-right">
                      <Badge tone={diffTone(r.diff)}>{r.diff == null ? 'รอข้อมูล' : pct(r.diff_pct)}</Badge>
                    </td>
                    <td className="py-2 pr-2 text-right tabular-nums text-slate-700">{fmtNum(r.cars)}</td>
                    <td className="py-2 pr-2 text-right tabular-nums text-slate-700">{fmtNum(r.motorcycles)}</td>
                    <td className="py-2 text-right tabular-nums text-slate-700">{fmtNum(r.trucks)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </Card>


    </div>
  );
}
