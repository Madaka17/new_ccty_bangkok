import { useMemo, useState } from 'react';
import { Card, SectionHeader, Badge, Segmented, Skeleton, EmptyState, Truncate } from '../dashboard/ui.jsx';
import { StatTile, StatusBanner } from '../dashboard/primitives.jsx';
import { fmtNum, fmtTime } from '../dashboard/format.js';

const PERIODS = [
  ['day', 'รายวัน'],
  ['week', 'รายสัปดาห์'],
  ['month', 'รายเดือน'],
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

  return (
    <div className="flex flex-col gap-4">
      {cycle && (
        <StatusBanner tone="blue" label={`รอบนับทุก ${cycle.cycle_minutes} นาที`}>
          เริ่มรอบ {fmtTime(cycle.cycle_started)} น. · รีเซ็ตถัดไป <b>{fmtTime(cycle.next_reset)} น.</b> (<CountdownText ts={cycle.next_reset} />) · สะสมรอบนี้ <b>{fmtNum(cycle.cycle?.total)}</b> คัน จาก {cycle.cycle?.scans || 0} รอบสแกน · บันทึกแล้ว {cycle.cycles_archived} รอบ
          {cycle.last_error && <span className="text-red-700"> · บันทึกล่าสุดล้มเหลว: {cycle.last_error}</span>}
        </StatusBanner>
      )}

      <Card className="p-5">
        <SectionHeader
          title={data?.title || 'เปรียบเทียบปริมาณจราจร'}
          description="ตัวเลข = รถที่เห็นในภาพสแนปช็อต รวมทุกรอบสแกนในช่วงนั้น ใช้เทียบความหนาแน่นช่วงต่อช่วง"
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
                  <b className="text-slate-900 dark:text-slate-100">{shown.label}</b> · {fmtNum(shown.total)} คัน · รถยนต์ {fmtNum(shown.cars)} · มอเตอร์ไซค์ {fmtNum(shown.motorcycles)} · บรรทุก {fmtNum(shown.trucks)} · {shown.cycles} รอบ
                </>
              ) : (
                'ยังไม่มีรอบที่บันทึก'
              )}
            </p>

            {/* View Mode & Filter Controls */}
            <div className="flex items-center gap-2 flex-wrap">
              <div className="inline-flex rounded-lg border border-cream-200 dark:border-slate-700 bg-cream-50 dark:bg-slate-800 p-0.5 text-xs">
                <button
                  type="button"
                  onClick={() => setChartMode('grouped')}
                  className={`cursor-pointer px-2.5 py-1 rounded-md font-medium transition-colors ${
                    chartMode === 'grouped'
                      ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 shadow-xs'
                      : 'text-slate-600 dark:text-slate-400 hover:text-slate-900'
                  }`}
                >
                  แยกแท่งรายประเภท
                </button>
                <button
                  type="button"
                  onClick={() => setChartMode('stacked')}
                  className={`cursor-pointer px-2.5 py-1 rounded-md font-medium transition-colors ${
                    chartMode === 'stacked'
                      ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 shadow-xs'
                      : 'text-slate-600 dark:text-slate-400 hover:text-slate-900'
                  }`}
                >
                  ซ้อนทับ (ยอดรวม)
                </button>
              </div>

              {/* Filter chips */}
              <div className="flex items-center gap-1 text-xs">
                <button
                  type="button"
                  onClick={() => setFilterType('all')}
                  className={`cursor-pointer px-2 py-1 rounded-md font-medium transition-colors ${
                    filterType === 'all'
                      ? 'bg-slate-800 text-white dark:bg-slate-200 dark:text-slate-900'
                      : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:text-slate-900'
                  }`}
                >
                  ทั้งหมด
                </button>
                <button
                  type="button"
                  onClick={() => setFilterType('cars')}
                  className={`cursor-pointer inline-flex items-center gap-1 px-2 py-1 rounded-md font-medium transition-colors ${
                    filterType === 'cars'
                      ? 'bg-blue-600 text-white'
                      : 'bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 hover:bg-blue-100'
                  }`}
                >
                  <span className="w-2 h-2 rounded-full bg-blue-500" /> รถยนต์
                </button>
                <button
                  type="button"
                  onClick={() => setFilterType('motorcycles')}
                  className={`cursor-pointer inline-flex items-center gap-1 px-2 py-1 rounded-md font-medium transition-colors ${
                    filterType === 'motorcycles'
                      ? 'bg-amber-500 text-white'
                      : 'bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 hover:bg-amber-100'
                  }`}
                >
                  <span className="w-2 h-2 rounded-full bg-amber-500" /> มอไซ
                </button>
                <button
                  type="button"
                  onClick={() => setFilterType('trucks')}
                  className={`cursor-pointer inline-flex items-center gap-1 px-2 py-1 rounded-md font-medium transition-colors ${
                    filterType === 'trucks'
                      ? 'bg-slate-600 text-white'
                      : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200'
                  }`}
                >
                  <span className="w-2 h-2 rounded-full bg-slate-500" /> บรรทุก
                </button>
              </div>
            </div>
          </div>

          {loading ? (
            <Skeleton className="mt-3 h-56 w-full" />
          ) : !chart.length ? (
            <div className="mt-3">
              <EmptyState title="ยังไม่มีข้อมูลเปรียบเทียบ" description="ระบบจะบันทึกรอบแรกเมื่อถึงเวลารีเซ็ตรอบถัดไป" />
            </div>
          ) : chartMode === 'grouped' ? (
            /* GROUPED BARS: 3 separate bars side by side per date */
            <div className="mt-4 pt-2 pb-1 border-b border-slate-200 dark:border-slate-800" onMouseLeave={() => setHover(null)}>
              <div className="flex items-end justify-around gap-2 sm:gap-6 min-h-[220px]">
                {chart.map((c) => {
                  const isCur = c.period_key === data.current_key;
                  const cTot = c.total || 1;
                  const carsH = Math.max(4, Math.round(((c.cars || 0) / max) * 155));
                  const motosH = Math.max(4, Math.round(((c.motorcycles || 0) / max) * 155));
                  const trucksH = Math.max(4, Math.round(((c.trucks || 0) / max) * 155));

                  const showCars = filterType === 'all' || filterType === 'cars';
                  const showMotos = filterType === 'all' || filterType === 'motorcycles';
                  const showTrucks = filterType === 'all' || filterType === 'trucks';

                  return (
                    <div
                      key={c.period_key}
                      onMouseEnter={() => setHover(c)}
                      className={`flex-1 flex flex-col items-center p-2 sm:p-3 rounded-xl transition-all ${
                        isCur
                          ? 'bg-blue-50/50 dark:bg-blue-950/20 ring-1 ring-blue-500/40'
                          : 'hover:bg-slate-50 dark:hover:bg-slate-800/40'
                      }`}
                    >
                      {/* Top Total Header */}
                      <div className="text-center mb-3">
                        <span className="text-xs font-semibold text-slate-800 dark:text-slate-200">
                          {c.label} {isCur && <span className="text-[11px] text-blue-600 dark:text-blue-400">({data.curr_label})</span>}
                        </span>
                        <span className="text-[11px] text-slate-500 block font-medium">
                          รวม {fmtNum(c.total)} คัน
                        </span>
                      </div>

                      {/* Side-by-side grouped bars */}
                      <div className="w-full flex items-end justify-center gap-1.5 sm:gap-3 h-44">
                        {/* 1. Cars */}
                        {showCars && (
                          <div className="flex-1 max-w-[52px] h-full flex flex-col justify-end items-center group">
                            <span className="text-[10px] font-bold text-blue-600 dark:text-blue-400 mb-1 tabular-nums whitespace-nowrap">
                              {fmtCompact(c.cars)}
                            </span>
                            <div
                              style={{ height: `${carsH}px` }}
                              className="w-full rounded-t-md bg-blue-600 dark:bg-blue-500 transition-all group-hover:brightness-110 shadow-xs"
                              title={`${c.label} รถยนต์: ${fmtNum(c.cars)} คัน (${Math.round((c.cars / cTot) * 100)}%)`}
                            />
                            <span className="text-[10px] text-slate-500 mt-1.5 leading-none">รถยนต์</span>
                            <span className="text-[9px] text-blue-600 dark:text-blue-400 font-medium leading-none mt-0.5">
                              {Math.round((c.cars / cTot) * 100)}%
                            </span>
                          </div>
                        )}

                        {/* 2. Motorcycles */}
                        {showMotos && (
                          <div className="flex-1 max-w-[52px] h-full flex flex-col justify-end items-center group">
                            <span className="text-[10px] font-bold text-amber-600 dark:text-amber-400 mb-1 tabular-nums whitespace-nowrap">
                              {fmtCompact(c.motorcycles)}
                            </span>
                            <div
                              style={{ height: `${motosH}px` }}
                              className="w-full rounded-t-md bg-amber-500 dark:bg-amber-400 transition-all group-hover:brightness-110 shadow-xs"
                              title={`${c.label} มอเตอร์ไซค์: ${fmtNum(c.motorcycles)} คัน (${Math.round((c.motorcycles / cTot) * 100)}%)`}
                            />
                            <span className="text-[10px] text-slate-500 mt-1.5 leading-none">มอไซ</span>
                            <span className="text-[9px] text-amber-600 dark:text-amber-400 font-medium leading-none mt-0.5">
                              {Math.round((c.motorcycles / cTot) * 100)}%
                            </span>
                          </div>
                        )}

                        {/* 3. Trucks */}
                        {showTrucks && (
                          <div className="flex-1 max-w-[52px] h-full flex flex-col justify-end items-center group">
                            <span className="text-[10px] font-bold text-slate-600 dark:text-slate-300 mb-1 tabular-nums whitespace-nowrap">
                              {fmtCompact(c.trucks)}
                            </span>
                            <div
                              style={{ height: `${trucksH}px` }}
                              className="w-full rounded-t-md bg-slate-500 dark:bg-slate-400 transition-all group-hover:brightness-110 shadow-xs"
                              title={`${c.label} บรรทุก/บัส: ${fmtNum(c.trucks)} คัน (${Math.round((c.trucks / cTot) * 100)}%)`}
                            />
                            <span className="text-[10px] text-slate-500 mt-1.5 leading-none">บรรทุก</span>
                            <span className="text-[9px] text-slate-600 dark:text-slate-400 font-medium leading-none mt-0.5">
                              {Math.round((c.trucks / cTot) * 100)}%
                            </span>
                          </div>
                        )}
                      </div>
                    </div>
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
                  ตารางเปรียบเทียบสัดส่วนและจำนวนรถแยกรายประเภท:
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
                      <th className="py-2.5 px-3 text-right font-medium text-slate-500">รอบสแกน</th>
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
