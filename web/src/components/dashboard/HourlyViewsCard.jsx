import { useMemo, useState } from 'react';
import { Card, Badge } from './ui.jsx';
import { fmtNum } from './format.js';

function formatDayLabel(dayStr) {
  if (!dayStr) return '';
  const parts = dayStr.split('-');
  if (parts.length === 3) {
    const months = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.'];
    const m = parseInt(parts[1], 10) - 1;
    const d = parseInt(parts[2], 10);
    return `${d} ${months[m] || ''}`;
  }
  return dayStr;
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

  // Default active hour is the top peak hour if exists, or null
  const topPeak = peakHours[0] || null;
  const [activeHour, setActiveHour] = useState(null);

  const currentDisplayHour = activeHour !== null ? activeHour : topPeak ? topPeak.hour : null;
  const currentDisplayViews = currentDisplayHour !== null ? (hours[currentDisplayHour] || 0) : 0;
  const isCurrentPeak = currentDisplayHour !== null && peakSet.has(currentDisplayHour);

  return (
    <Card className="p-4 sm:p-5 flex flex-col gap-4">
      {/* 1. Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 pb-3 border-b border-cream-200 dark:border-slate-800">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-base font-semibold text-ink-900 leading-6">
              เพจวิวรายชั่วโมง (24 ชม.)
            </h2>
            {topPeak && topPeak.views > 0 && (
              <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 dark:bg-blue-950/60 dark:text-blue-300 border border-blue-200 dark:border-blue-800/60">
                <span>🔥</span> พีคสุด {String(topPeak.hour).padStart(2, '0')}:00 น.
              </span>
            )}
          </div>
          <p className="text-xs text-ink-600 mt-1">
            สถิติการเข้าดูสะสม {peakWindowDays} วันล่าสุด จำแนกตามช่วงเวลาตลอด 24 ชม.
          </p>
        </div>

        {/* Total views badge */}
        <div className="text-left sm:text-right shrink-0">
          <span className="text-[11px] text-ink-500 block">ยอดเข้าดูสะสม</span>
          <span className="text-sm font-bold text-ink-900 tabular-nums">
            {fmtNum(totalViews)} <span className="text-xs font-normal text-ink-500">ครั้ง</span>
          </span>
        </div>
      </div>

      {/* 2. Selected Hour Insight Banner */}
      <div className="flex items-center justify-between p-2.5 rounded-xl bg-cream-50 dark:bg-slate-800/50 border border-cream-200 dark:border-slate-800 text-xs">
        <div className="flex items-center gap-2">
          <span className="text-base">🕒</span>
          <div>
            <span className="text-ink-600">ช่วงเวลา: </span>
            <span className="font-semibold text-ink-900">
              {currentDisplayHour !== null
                ? `${String(currentDisplayHour).padStart(2, '0')}:00 – ${String(currentDisplayHour).padStart(2, '0')}:59 น.`
                : 'ชี้ที่แท่งเพื่อดูรายละเอียด'}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-ink-600">จำนวน:</span>
          <span className="font-bold text-blue-600 dark:text-blue-400 text-sm tabular-nums">
            {fmtNum(currentDisplayViews)} เพจวิว
          </span>
          {isCurrentPeak && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-100 text-blue-800 dark:bg-blue-900/60 dark:text-blue-200 font-medium">
              Peak Hour
            </span>
          )}
        </div>
      </div>

      {/* 3. Bar Chart Container */}
      <div className="flex flex-col gap-1.5">
        {/* Y-axis guide label */}
        <div className="flex justify-between items-center text-[10px] text-ink-400 px-1">
          <span>สูงสุด {fmtNum(maxVal)} วิว</span>
          <span>แตะหรือชี้ที่แท่งเพื่อดูจำนวน</span>
        </div>

        {/* Chart Area */}
        <div className="relative h-36 flex items-end gap-[3px] sm:gap-1 pt-6 pb-1 px-1 border-b border-cream-300 dark:border-slate-700">
          {/* Background guide lines */}
          <div className="absolute inset-x-0 top-6 border-b border-dashed border-cream-200 dark:border-slate-800 pointer-events-none" />
          <div className="absolute inset-x-0 top-1/2 border-b border-dashed border-cream-200 dark:border-slate-800 pointer-events-none" />

          {hours.map((val, hour) => {
            const isPeak = peakSet.has(hour);
            const isSelected = currentDisplayHour === hour;
            const isTop = topPeak && topPeak.hour === hour && val > 0;
            const heightPercent = maxVal > 0 ? (val / maxVal) * 100 : 0;
            const heightPx = Math.max(3, Math.round((heightPercent / 100) * 105));

            return (
              <div
                key={hour}
                className="flex-1 h-full flex flex-col justify-end items-center relative group cursor-pointer"
                onMouseEnter={() => setActiveHour(hour)}
                onMouseLeave={() => setActiveHour(null)}
                onClick={() => setActiveHour(hour)}
              >
                {/* Floating indicator above the top peak bar */}
                {isTop && (
                  <div className="absolute -top-5 left-1/2 -translate-x-1/2 flex flex-col items-center pointer-events-none">
                    <span className="text-[10px] font-bold text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-slate-800 px-1 rounded shadow-2xs leading-none whitespace-nowrap">
                      {fmtNum(val)}
                    </span>
                    <span className="text-[8px] text-blue-500 leading-none">▼</span>
                  </div>
                )}

                {/* The Bar */}
                <div
                  style={{ height: `${heightPx}px` }}
                  className={`w-full rounded-t-sm transition-all duration-150 ${
                    val === 0
                      ? 'bg-cream-200 dark:bg-slate-800'
                      : isTop
                      ? isSelected
                        ? 'bg-blue-600 dark:bg-blue-400 shadow-md ring-2 ring-blue-400/40'
                        : 'bg-blue-600 dark:bg-blue-500'
                      : isPeak
                      ? isSelected
                        ? 'bg-indigo-600 dark:bg-indigo-400 ring-2 ring-indigo-400/40'
                        : 'bg-indigo-500 dark:bg-indigo-500/80'
                      : isSelected
                      ? 'bg-sky-500 dark:bg-sky-400 ring-2 ring-sky-400/40'
                      : 'bg-sky-400/75 hover:bg-sky-500 dark:bg-sky-600/60 dark:hover:bg-sky-500'
                  }`}
                />
              </div>
            );
          })}
        </div>

        {/* X-axis Labels */}
        <div className="flex justify-between items-center text-[10px] text-ink-500 px-1 pt-1 tabular-nums">
          <span>00:00</span>
          <span>03:00</span>
          <span>06:00</span>
          <span>09:00</span>
          <span>12:00</span>
          <span>15:00</span>
          <span>18:00</span>
          <span>21:00</span>
          <span>23:00</span>
        </div>
      </div>



      {/* 5. Daily Active Users (DAU History) */}
      {dauSeries && dauSeries.length > 1 && (
        <div className="pt-2 border-t border-cream-200 dark:border-slate-800">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] font-medium text-ink-600">
              ผู้ใช้งานรายวันย้อนหลัง (DAU Series):
            </span>
            <span className="text-[10px] text-ink-400">หน่วย: คน/วัน</span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-7 gap-1.5">
            {dauSeries.map((s, idx) => {
              const isLatest = idx === dauSeries.length - 1;
              return (
                <div
                  key={s.day}
                  className={`p-2 rounded-lg border text-center ${
                    isLatest
                      ? 'bg-blue-50/60 dark:bg-blue-950/40 border-blue-200 dark:border-blue-800/60'
                      : 'bg-cream-50/70 dark:bg-slate-800/40 border-cream-200 dark:border-slate-800'
                  }`}
                >
                  <span className="text-[10px] text-ink-500 block">
                    {isLatest ? 'วันนี้' : formatDayLabel(s.day)}
                  </span>
                  <span className="text-xs font-bold text-ink-900 block mt-0.5 tabular-nums">
                    {fmtNum(s.users)} <span className="text-[10px] font-normal text-ink-500">คน</span>
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </Card>
  );
}
