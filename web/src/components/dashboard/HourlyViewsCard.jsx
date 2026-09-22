import { useMemo, useState } from 'react';
import { Card } from './ui.jsx';
import { fmtNum, fmtDay, pad2 } from './format.js';

const hourLabel = (h) => `${pad2(h)}:00`;

// One number with a small caption. Used for the KPI row under the header.
function Stat({ label, value, unit, hint }) {
  return (
    <div className="min-w-0">
      <span className="block text-xs text-ink-500">{label}</span>
      <span className="block text-lg font-semibold text-ink-900 tabular-nums leading-tight">
        {value}
        {unit && <span className="ml-1 text-xs font-normal text-ink-500">{unit}</span>}
      </span>
      {hint && <span className="block text-xs text-ink-500 truncate">{hint}</span>}
    </div>
  );
}

export default function HourlyViewsCard({
  hours = [],
  peakHours = [],
  peakWindowDays = 7,
  dauSeries = [],
}) {
  const peakSet = useMemo(() => new Set(peakHours.map((p) => p.hour)), [peakHours]);
  const maxVal = useMemo(() => Math.max(1, ...hours), [hours]);
  const totalViews = useMemo(() => hours.reduce((a, b) => a + b, 0), [hours]);
  const activeHours = useMemo(() => hours.filter((v) => v > 0).length, [hours]);
  const avgPerHour = activeHours ? Math.round(totalViews / activeHours) : 0;

  const topPeak = peakHours[0] || null;
  const [hover, setHover] = useState(null);
  const shownHour = hover ?? (topPeak ? topPeak.hour : null);
  const shownViews = shownHour !== null ? hours[shownHour] || 0 : 0;

  const today = dauSeries[dauSeries.length - 1] || null;
  const yesterday = dauSeries[dauSeries.length - 2] || null;
  const dauDelta = today && yesterday ? today.users - yesterday.users : null;

  return (
    <Card className="p-4 sm:p-5 flex flex-col gap-5">
      {/* Header */}
      <div>
        <h2 className="text-base font-semibold text-ink-900">เพจวิวรายชั่วโมง</h2>
        <p className="text-xs text-ink-500 mt-0.5">รวม {peakWindowDays} วันล่าสุด แยกตามชั่วโมงของวัน</p>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-3 gap-3">
        <Stat label="ยอดเข้าดูรวม" value={fmtNum(totalViews)} unit="ครั้ง" />
        <Stat
          label="ชั่วโมงที่ดูมากสุด"
          value={topPeak ? hourLabel(topPeak.hour) : '–'}
          hint={topPeak ? `${fmtNum(topPeak.views)} ครั้ง` : 'ยังไม่มีข้อมูล'}
        />
        <Stat label="เฉลี่ยต่อชั่วโมง" value={fmtNum(avgPerHour)} unit="ครั้ง" />
      </div>

      {/* Chart */}
      <div>
        {/* Readout for the hovered / peak hour. Fixed height so the chart never jumps. */}
        <div className="flex items-baseline gap-2 h-6 text-sm">
          {shownHour !== null ? (
            <>
              <span className="text-ink-600 tabular-nums">{hourLabel(shownHour)}–{pad2(shownHour)}:59 น.</span>
              <span className="font-semibold text-ink-900 tabular-nums">{fmtNum(shownViews)} ครั้ง</span>
              {peakSet.has(shownHour) && <span className="text-xs text-blue-600 dark:text-blue-400">ชั่วโมงพีค</span>}
            </>
          ) : (
            <span className="text-ink-500">ชี้ที่แท่งเพื่อดูจำนวน</span>
          )}
        </div>

        <div className="relative mt-3 pl-9">
          {/* Y axis: 3 guide lines with their values, so a bar can be read without hovering */}
          {[1, 0.5, 0].map((f) => (
            <div key={f} className="absolute left-9 right-0 border-t border-dashed border-cream-300 dark:border-slate-700 pointer-events-none" style={{ top: `${100 - f * 88}%` }}>
              <span className="absolute -left-9 -top-2 w-8 text-right text-[11px] text-ink-500 tabular-nums">{fmtNum(Math.round(maxVal * f))}</span>
            </div>
          ))}

          <div className="flex items-end gap-1 sm:gap-1.5 h-40" onMouseLeave={() => setHover(null)}>
            {hours.map((val, hour) => {
              const isPeak = peakSet.has(hour);
              const isHover = hover === hour;
              const pct = Math.max(2, (val / maxVal) * 88);
              const cls = val === 0
                ? 'bg-cream-200 dark:bg-slate-800'
                : isPeak
                  ? (isHover ? 'bg-blue-500 dark:bg-blue-300' : 'bg-blue-600 dark:bg-blue-400')
                  : (isHover ? 'bg-slate-500 dark:bg-slate-300' : 'bg-slate-400 dark:bg-slate-500');
              return (
                <div
                  key={hour}
                  className="relative flex-1 h-full flex items-end cursor-pointer min-w-0"
                  onMouseEnter={() => setHover(hour)}
                  onClick={() => setHover(hour)}
                  title={`${hourLabel(hour)} · ${fmtNum(val)} ครั้ง`}
                >
                  <div style={{ height: `${pct}%` }} className={`w-full rounded-t-md transition-colors duration-150 ${cls}`} />
                  {/* Value above every bar (desktop); on phones only the hovered / peak bar */}
                  {val > 0 && (
                    <span
                      style={{ bottom: `calc(${pct}% + 3px)` }}
                      className={`absolute inset-x-0 text-center text-[10px] leading-none tabular-nums ${isPeak ? 'text-blue-600 dark:text-blue-300 font-semibold' : 'text-ink-500'} ${isHover || isPeak ? '' : 'hidden sm:block'}`}
                    >
                      {fmtNum(val)}
                    </span>
                  )}
                </div>
              );
            })}
          </div>

          {/* X axis: label under every 3rd bar, small tick under the others */}
          <div className="flex gap-1 sm:gap-1.5 mt-1.5 border-t border-cream-300 dark:border-slate-700 pt-1">
            {hours.map((_, hour) => (
              <div key={hour} className="flex-1 text-center text-[11px] text-ink-600 tabular-nums min-w-0">
                {hour % 3 === 0 ? `${pad2(hour)}` : <span className="text-cream-300 dark:text-slate-700">·</span>}
              </div>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-4 mt-2 text-xs text-ink-500">
          <span className="inline-flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-sm bg-blue-600 dark:bg-blue-400" /> ชั่วโมงพีค</span>
          <span className="inline-flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-sm bg-slate-400 dark:bg-slate-500" /> ชั่วโมงอื่น</span>
          <span className="ml-auto">แกนนอน = ชั่วโมงของวัน (00-23 น.)</span>
        </div>
      </div>

      {/* Daily active users */}
      {dauSeries.length > 0 && (
        <div className="pt-4 border-t border-cream-200 dark:border-slate-800">
          <div className="flex items-baseline justify-between mb-2">
            <span className="text-sm font-medium text-ink-900">ผู้ใช้งานรายวัน</span>
            <span className="text-xs text-ink-500">คน/วัน</span>
          </div>
          <div className="flex items-end gap-4 flex-wrap">
            <div>
              <span className="block text-xs text-ink-500">วันนี้</span>
              <span className="text-2xl font-semibold text-ink-900 tabular-nums leading-tight">
                {fmtNum(today?.users || 0)}
                <span className="ml-1 text-xs font-normal text-ink-500">คน</span>
              </span>
              {dauDelta !== null && (
                <span className={`block text-xs tabular-nums ${dauDelta > 0 ? 'text-emerald-600 dark:text-emerald-400' : dauDelta < 0 ? 'text-red-600 dark:text-red-400' : 'text-ink-500'}`}>
                  {dauDelta > 0 ? '+' : ''}{fmtNum(dauDelta)} จากเมื่อวาน
                </span>
              )}
            </div>
            {dauSeries.length > 1 && (
              <div className="flex gap-1.5 flex-wrap">
                {dauSeries.slice(0, -1).map((s) => (
                  <div key={s.day} className="px-2.5 py-1.5 rounded-lg bg-cream-50 dark:bg-slate-800/60 border border-cream-200 dark:border-slate-800 text-center min-w-14">
                    <span className="block text-[11px] text-ink-500">{fmtDay(s.day)}</span>
                    <span className="block text-sm font-medium text-ink-900 tabular-nums">{fmtNum(s.users)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}
