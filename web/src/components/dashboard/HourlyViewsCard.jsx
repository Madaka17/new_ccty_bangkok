import { useMemo, useState } from 'react';
import { Card } from './ui.jsx';
import { fmtNum, fmtDay, pad2 } from './format.js';

const hourLabel = (h) => `${pad2(h)}:00`;

// Today's page views per hour. The running hour is highlighted and later hours are left empty,
// so the chart fills in as the day goes on.
export default function HourlyViewsCard({
  hours = [],
  currentHour = null,
  peakHours = [],
  dauSeries = [],
}) {
  const peakSet = useMemo(() => new Set(peakHours.map((p) => p.hour)), [peakHours]);
  const maxVal = useMemo(() => Math.max(1, ...hours), [hours]);

  const [hover, setHover] = useState(null);
  const shownHour = hover ?? currentHour;
  const shownViews = shownHour !== null ? hours[shownHour] || 0 : 0;

  const today = dauSeries[dauSeries.length - 1] || null;

  return (
    <Card className="p-4 sm:p-5 flex flex-col gap-5">
      <div>
        <h2 className="text-base font-semibold text-ink-900">ยอดเปิดดูวันนี้ รายชั่วโมง</h2>
        <p className="text-xs text-ink-500 mt-0.5">แท่งสีเขียว = ชั่วโมงปัจจุบัน อัปเดตสด</p>
      </div>

      <div>
        {/* Readout for the hovered / current hour. Fixed height so the chart never jumps. */}
        <div className="flex items-baseline gap-2 h-6 text-sm">
          {shownHour !== null && (
            <>
              <span className="text-ink-600 tabular-nums">{hourLabel(shownHour)}–{pad2(shownHour)}:59 น.</span>
              <span className="font-semibold text-ink-900 tabular-nums">{fmtNum(shownViews)} ครั้ง</span>
              {shownHour === currentHour && <span className="text-xs text-emerald-600 dark:text-emerald-400">ตอนนี้</span>}
              {peakSet.has(shownHour) && <span className="text-xs text-blue-600 dark:text-blue-400">ช่วงคนใช้มาก</span>}
            </>
          )}
        </div>

        <div className="relative mt-3 pl-9">
          {[1, 0.5, 0].map((f) => (
            <div key={f} className="absolute left-9 right-0 border-t border-dashed border-cream-300 dark:border-slate-700 pointer-events-none" style={{ top: `${100 - f * 88}%` }}>
              <span className="absolute -left-9 -top-2 w-8 text-right text-[11px] text-ink-500 tabular-nums">{fmtNum(Math.round(maxVal * f))}</span>
            </div>
          ))}

          <div className="flex items-end gap-1 sm:gap-1.5 h-40" onMouseLeave={() => setHover(null)}>
            {hours.map((val, hour) => {
              const isNow = hour === currentHour;
              const isHover = hover === hour;
              const pct = Math.max(2, (val / maxVal) * 88);
              const cls = isNow
                ? 'bg-emerald-500 dark:bg-emerald-400 animate-pulse'
                : val === 0
                  ? 'bg-cream-200 dark:bg-slate-800'
                  : isHover ? 'bg-blue-500 dark:bg-blue-300' : 'bg-blue-600/70 dark:bg-blue-400/70';
              return (
                <div
                  key={hour}
                  className="relative flex-1 h-full flex items-end cursor-pointer min-w-0"
                  onMouseEnter={() => setHover(hour)}
                  onClick={() => setHover(hour)}
                  title={`${hourLabel(hour)} · ${fmtNum(val)} ครั้ง`}
                >
                  <div style={{ height: `${pct}%` }} className={`w-full rounded-t-md transition-[height,background-color] duration-500 ${cls}`} />
                  {val > 0 && (
                    <span
                      style={{ bottom: `calc(${pct}% + 3px)` }}
                      className={`absolute inset-x-0 text-center text-[10px] leading-none tabular-nums ${isNow ? 'text-emerald-600 dark:text-emerald-300 font-semibold' : 'text-ink-500'} ${isHover || isNow ? '' : 'hidden sm:block'}`}
                    >
                      {fmtNum(val)}
                    </span>
                  )}
                </div>
              );
            })}
          </div>

          <div className="flex gap-1 sm:gap-1.5 mt-1.5 border-t border-cream-300 dark:border-slate-700 pt-1">
            {hours.map((_, hour) => (
              <div key={hour} className="flex-1 text-center text-[11px] text-ink-600 tabular-nums min-w-0">
                {hour % 3 === 0 ? `${pad2(hour)}` : <span className="text-cream-300 dark:text-slate-700">·</span>}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Daily users, oldest to newest */}
      {dauSeries.length > 1 && (
        <div className="pt-4 border-t border-cream-200 dark:border-slate-800">
          <span className="block text-sm font-medium text-ink-900 mb-2">ผู้ใช้รายวัน (คน)</span>
          <div className="flex gap-1.5 flex-wrap">
            {dauSeries.map((s) => (
              <div
                key={s.day}
                className={`px-2.5 py-1.5 rounded-lg border text-center min-w-14 ${s === today ? 'bg-blue-50 border-blue-200 dark:bg-blue-500/10 dark:border-blue-500/30' : 'bg-cream-50 dark:bg-slate-800/60 border-cream-200 dark:border-slate-800'}`}
              >
                <span className="block text-[11px] text-ink-500">{s === today ? 'วันนี้' : fmtDay(s.day)}</span>
                <span className="block text-sm font-medium text-ink-900 tabular-nums">{fmtNum(s.users)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}
