import { useState, useEffect, useCallback } from 'react';
import { Card, Badge, Skeleton, ErrorState } from './ui.jsx';
import { fetchTrafficGuidance } from '../../lib/api.js';

const POLL_MS = 60000;
const MAX_HOTSPOTS = 3;
const MAX_ALTS = 3;

const FLOW_BAR = { red: 'bg-red-500', yellow: 'bg-amber-500', green: 'bg-emerald-500', neutral: 'bg-slate-300' };

// Flow score 0-100 as a short bar + number. Same width on every card so the row lines up.
function FlowMeter({ flow, tone }) {
  return (
    <div className="flex items-center gap-2 min-w-0">
      <div className="h-1.5 w-16 rounded-full bg-cream-200 dark:bg-slate-700 overflow-hidden shrink-0">
        <div className={`h-full rounded-full ${FLOW_BAR[tone] || FLOW_BAR.neutral}`} style={{ width: `${flow ?? 0}%` }} />
      </div>
      <span className="text-sm text-ink-900 tabular-nums font-medium">{flow ?? '–'}<span className="text-ink-500 font-normal">/100</span></span>
    </div>
  );
}

// คำแนะนำการระบายรถ: ทุกอย่างในการ์ดนี้มาจาก /api/traffic/guidance ซึ่งสร้างใหม่ทุกนาที
// จากเส้นสีแผนที่ Longdo + จำนวนรถจากกล้อง กทม. + เหตุการณ์ (ไม่มีข้อความคงที่)
// ทุกการ์ดมีบล็อกเท่ากัน 5 ส่วน (หัว / ตัวเลข / จุดสะสม / ทางเลี่ยง / วิธีระบาย) ความสูงล็อกไว้ให้ตรงกันทั้งกริด
export default function TrafficGuidanceCard() {
  const [filter, setFilter] = useState('all');
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    return fetchTrafficGuidance()
      .then((d) => {
        setData(d);
        setError(false);
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  const items = data?.items || [];
  const isBusy = (c) => c.status === 'congested' || c.status === 'moderate' || c.status === 'incident';
  const countCongested = items.filter(isBusy).length;
  const countFree = items.filter((c) => c.status === 'free').length;
  const countIncidents = items.filter((c) => c.status === 'incident').length;

  const filtered = items.filter((c) => {
    if (filter === 'congested') return isBusy(c);
    if (filter === 'free') return c.status === 'free';
    if (filter === 'incidents') return c.status === 'incident';
    return true;
  });

  const chip = (key, label, activeCls) => (
    <button
      type="button"
      onClick={() => setFilter(key)}
      className={`cursor-pointer px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
        filter === key ? activeCls : 'bg-cream-100 text-ink-600 hover:text-ink-900'
      }`}
    >
      {label}
    </button>
  );

  return (
    <Card className="p-4 sm:p-5 flex flex-col gap-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-ink-900 leading-7">คำแนะนำการระบายรถ</h2>
          <p className="text-xs text-ink-500">จากเส้นจราจรสด + กล้อง กทม. อัปเดตทุก 1 นาที</p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5 self-start sm:self-auto">
          {chip('all', `ทั้งหมด ${items.length}`, 'bg-ink-900 text-white dark:bg-slate-100 dark:text-slate-900')}
          {chip('congested', `ต้องเร่งระบาย ${countCongested}`, 'bg-red-600 text-white')}
          {chip('free', `คล่องตัว ${countFree}`, 'bg-emerald-600 text-white')}
          {countIncidents > 0 && chip('incidents', `มีเหตุ ${countIncidents}`, 'bg-amber-600 text-white')}
        </div>
      </div>

      {error && !data ? (
        <ErrorState message="โหลดคำแนะนำไม่สำเร็จ" onRetry={load} retrying={loading} />
      ) : !data ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {[1, 2, 3, 4, 5, 6].map((n) => (
            <Skeleton key={n} className="h-80" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3 auto-rows-fr">
          {filtered.map((c) => {
            const hotspots = c.hotspots.slice(0, MAX_HOTSPOTS);
            const alts = (c.alternatives || []).slice(0, MAX_ALTS);
            const incident = c.incidents?.[0];
            return (
              <div
                key={c.id}
                className="rounded-xl border border-cream-200 bg-cream-100/40 p-4 flex flex-col gap-3 h-full hover:border-slate-300 dark:hover:border-slate-600 transition-colors"
              >
                {/* 1. Name + status. Two-line name box so short and long names take the same height. */}
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <h3 className="text-[15px] font-semibold text-ink-900 leading-snug line-clamp-2 min-h-[2.5rem]" title={c.name}>{c.name}</h3>
                    <span className="block text-xs text-ink-500 truncate" title={c.zone}>{c.zone}</span>
                  </div>
                  <Badge tone={c.tone} dot={c.status === 'incident' || c.status === 'congested'} className="shrink-0">
                    {c.status_label}
                  </Badge>
                </div>

                {/* 2. Numbers */}
                <div className="flex items-center justify-between gap-3 py-2 border-y border-cream-200">
                  <FlowMeter flow={c.flow} tone={c.tone} />
                  <span className="text-sm text-ink-600 tabular-nums shrink-0">
                    เส้นแดง <span className="font-medium text-ink-900">{c.red_km ?? 0}</span> กม.
                  </span>
                </div>

                {/* 3. Hotspots: fixed 3 rows */}
                <div>
                  <span className="block text-xs font-medium text-ink-500 mb-1">จุดสะสมตอนนี้</span>
                  <ul className="flex flex-col gap-1 min-h-[4.5rem]">
                    {hotspots.length ? (
                      hotspots.map((s, i) => (
                        <li key={i} className="flex items-center gap-2 text-sm leading-5">
                          <span className="w-1.5 h-1.5 rounded-full bg-red-500 shrink-0" />
                          <span className="text-ink-900 truncate min-w-0 flex-1" title={s.label}>{s.label}</span>
                          <span className="text-xs text-ink-500 tabular-nums shrink-0">
                            {s.km} กม.{s.camera?.total != null ? ` · ${s.camera.total} คัน` : ''}
                          </span>
                        </li>
                      ))
                    ) : (
                      <li className="text-sm text-ink-500 leading-5">ไม่มีเส้นแดงสะสม</li>
                    )}
                  </ul>
                </div>

                {/* 4. Alternatives as chips with live flow. Green = recommended. */}
                <div>
                  <span className="block text-xs font-medium text-ink-500 mb-1">ทางเลี่ยง (ระบายได้/100)</span>
                  <div className="flex flex-wrap gap-1.5 min-h-[3.75rem] content-start">
                    {alts.length ? (
                      alts.map((a) => (
                        <span
                          key={a.name}
                          title={a.name}
                          className={`inline-flex items-center gap-1.5 max-w-full rounded-md border px-2 py-0.5 text-xs leading-5 ${
                            a.recommended
                              ? 'bg-emerald-50 border-emerald-200 text-emerald-800 dark:bg-emerald-950/40 dark:border-emerald-900 dark:text-emerald-300'
                              : 'bg-cream-100 border-cream-200 text-ink-600'
                          }`}
                        >
                          <span className="truncate">{a.name}</span>
                          <span className="tabular-nums font-medium shrink-0">{a.flow}</span>
                        </span>
                      ))
                    ) : (
                      <span className="text-sm text-ink-500">ยังไม่มีข้อมูลทางเลี่ยง</span>
                    )}
                  </div>
                </div>

                {/* 5. Advice: incident (if any) replaces the signal line; both clamp so cards stay even */}
                <div className="rounded-lg bg-white dark:bg-slate-900 border border-cream-200 p-3 text-sm flex flex-col gap-1.5">
                  <p className="text-ink-900 line-clamp-3 min-h-[3.75rem]" title={c.action}>
                    <span className="font-semibold text-blue-600 dark:text-blue-400">ระบาย: </span>{c.action}
                  </p>
                  {incident ? (
                    <p className="text-[13px] text-red-700 dark:text-red-300 line-clamp-2 min-h-[2.5rem] pt-1.5 border-t border-cream-200" title={incident.title}>
                      <span className="font-semibold">เหตุสด: </span>{incident.title}
                    </p>
                  ) : (
                    <p className="text-[13px] text-ink-600 line-clamp-2 min-h-[2.5rem] pt-1.5 border-t border-cream-200" title={c.signal}>
                      <span className="font-semibold">สัญญาณไฟ: </span>{c.signal}
                    </p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}
