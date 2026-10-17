import { useEffect, useId, useState } from 'react';
import { Card, SectionHeader, Segmented, Skeleton, ErrorState } from './ui.jsx';
import { fetchBestTime } from '../../lib/api.js';
import { todayDayType, hourRange, LEVEL_TH } from '../../lib/bestTime.js';

// ออกกี่โมงดี: the hour with the fewest cars (free-flowing) and the busiest hour on a road, from the hourly
// car-count profile of the BMA cameras. The bars use the tone classes so light and dark themes share one palette.
const LEVEL_TONE = { free: 'tone-green', moderate: 'tone-yellow', heavy: 'tone-red' };
const DAY_OPTIONS = [['workday', 'วันทำงาน'], ['weekend', 'เสาร์-อาทิตย์']];
const MAX_BAR_PX = 112; // bar area height; the tallest bar fills it

// Current hour in Bangkok (UTC+7)
const bkkHour = (date = new Date()) => (date.getUTCHours() + 7) % 24;

export default function BestTimeCard({ isActive }) {
  const [road, setRoad] = useState('');
  const [day, setDay] = useState(() => todayDayType());
  const [data, setData] = useState(null);
  // The road list is kept apart from `data` so the select keeps its options and value while loading or after an error
  const [roads, setRoads] = useState([]);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(false);
  const [retryTick, setRetryTick] = useState(0);
  const selectId = useId();

  // No polling: the profile changes hourly. Refetch on each picker change, and when the page becomes active.
  // Each request clears the previous bars, so stale bars never sit under a changed picker.
  useEffect(() => {
    if (!isActive) return undefined;
    let live = true;
    setLoading(true);
    setData(null);
    setError(false);
    fetchBestTime(road, day)
      .then((d) => {
        if (!live) return;
        setData(d);
        if (d.roads?.length) setRoads(d.roads);
      })
      .catch(() => live && setError(true))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [road, day, isActive, retryTick]);

  const hours = data?.hours || [];
  const values = hours.map((h) => h.avg).filter((v) => typeof v === 'number');
  const max = values.length ? Math.max(...values) : 0;
  const now = bkkHour();
  const best = data?.best;
  const worst = data?.worst;

  return (
    <Card className="p-4 sm:p-5 flex flex-col gap-4" aria-labelledby={`${selectId}-title`}>
      <SectionHeader
        id={`${selectId}-title`}
        title="ออกกี่โมงดี"
        description={data ? `ช่วงที่รถน้อยและรถมาก จากกล้อง กทม. ${data.days_of_data} วัน` : 'ช่วงที่รถน้อยและรถมาก จากกล้อง กทม.'}
      />

      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor={selectId} className="sr-only">เลือกถนน</label>
        <select
          id={selectId}
          value={road}
          onChange={(e) => setRoad(e.target.value)}
          style={{ backgroundColor: 'var(--c-surface)', color: 'var(--c-ink)', borderColor: 'var(--c-border)' }}
          className="min-w-0 max-w-full flex-1 h-9 rounded-lg border px-2 text-sm"
        >
          <option value="">ทั้งกรุงเทพฯ</option>
          {roads.map((r) => (
            <option key={r.road} value={r.road}>{`${r.road} (${r.cameras} กล้อง)`}</option>
          ))}
        </select>
        <Segmented label="เลือกวัน" options={DAY_OPTIONS} value={day} onChange={setDay} />
      </div>

      {error ? (
        <ErrorState message="โหลดข้อมูลไม่สำเร็จ" onRetry={() => setRetryTick((n) => n + 1)} retrying={loading} />
      ) : !data ? (
        <Skeleton className="h-40" />
      ) : (
        <>
          <div className="flex items-end gap-[2px]" style={{ height: MAX_BAR_PX }}>
            {hours.map((h) => {
              const isNow = h.h === now;
              const label = `${String(h.h).padStart(2, '0')}:00 ${LEVEL_TH[h.level] || 'ไม่มีข้อมูล'}`;
              return (
                <div key={h.h} className="flex-1 min-w-0 h-full flex flex-col justify-end items-center">
                  {typeof h.avg === 'number' ? (
                    <div
                      role="img"
                      aria-label={label}
                      title={label}
                      className={`${LEVEL_TONE[h.level] || 'tone-neutral'} w-full max-w-[24px] rounded-t-[4px] bg-[var(--t-band)] ${
                        isNow ? 'outline outline-2 outline-offset-2 outline-slate-900 dark:outline-slate-100' : ''
                      }`}
                      style={{ height: `${Math.max(4, (h.avg / (max || 1)) * MAX_BAR_PX)}px` }}
                    />
                  ) : (
                    <div
                      role="img"
                      aria-label={label}
                      title={label}
                      className={`w-full max-w-[24px] h-2 rounded-t-[4px] border border-dashed border-slate-400 opacity-60 ${
                        isNow ? 'outline outline-2 outline-offset-2 outline-slate-900 dark:outline-slate-100' : ''
                      }`}
                    />
                  )}
                </div>
              );
            })}
          </div>
          <div className="flex gap-[2px] -mt-2">
            {hours.map((h) => (
              <span
                key={h.h}
                className={`flex-1 min-w-0 text-center text-[10px] leading-4 tabular-nums text-slate-600 ${h.h % 2 ? 'invisible sm:visible' : ''}`}
              >
                {String(h.h).padStart(2, '0')}
              </span>
            ))}
          </div>

          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
            {Object.entries(LEVEL_TH).map(([level, text]) => (
              <span key={level} className={`${LEVEL_TONE[level]} inline-flex items-center gap-1.5`}>
                <span className="w-2.5 h-2.5 rounded-sm bg-[var(--t-band)]" aria-hidden="true" />
                {text}
              </span>
            ))}
          </div>

          {best ? (
            <div className="flex flex-col gap-1 text-sm text-slate-900">
              <p>รถน้อยที่สุด <span className="font-semibold tabular-nums">{hourRange(best)}</span></p>
              {worst && <p>ควรเลี่ยง <span className="font-semibold tabular-nums">{hourRange(worst)}</span></p>}
            </div>
          ) : (
            <p className="text-sm text-slate-600">ข้อมูลยังไม่พอ ลองเลือกถนนอื่นหรือทั้งกรุงเทพฯ</p>
          )}
        </>
      )}
    </Card>
  );
}
