import { useState, useEffect, useCallback } from 'react';
import { Card, Badge, Button, Skeleton, ErrorState } from './ui.jsx';
import { fetchTrafficGuidance, fetchAreaGuidance } from '../../lib/api.js';

const POLL_MS = 60000;
const BANGKOK = '10';
const MAX_HOTSPOTS = 3;
const MAX_ALTS = 3;
const FIRST_CARDS = 6; // cards shown before "ดูทั้งหมด"; the rest open on demand so the overview stays short

// ถนนสายหลัก: ติดตรงไหน เลี่ยงทางไหน ทุกอย่างในการ์ดนี้มาจาก /api/traffic/guidance ซึ่งสร้างใหม่ทุกนาที
// จากเส้นสีแผนที่ Longdo + จำนวนรถจากกล้อง กทม. + เหตุการณ์ (ไม่มีข้อความคงที่)
// ทุกการ์ดมีบล็อกเท่ากัน 5 ส่วน (หัว / ระยะที่ติด / จุดที่ติด / ทางเลี่ยง / คำแนะนำ) ความสูงล็อกไว้ให้ตรงกันทั้งกริด
// เลือกจังหวัด/อำเภอในการ์ด "รถติดแค่ไหนตอนนี้": การ์ดเป็นถนนในพื้นที่นั้นแทน (/api/traffic/guidance/area)
// ยกเว้นเลือกกรุงเทพฯ ทั้งจังหวัด ซึ่งใช้ 12 เส้นทางหลักเดิม
export default function TrafficGuidanceCard({ province = '', amphoe = '' }) {
  const [filter, setFilter] = useState('all');
  const [showAll, setShowAll] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(false);
  const [slow, setSlow] = useState(false);
  const byArea = !!province && !(province === BANGKOK && !amphoe);

  // `current()` is false once another area was picked, so a late answer for the old one is dropped
  const load = useCallback((current = () => true) => {
    setLoading(true);
    return (byArea ? fetchAreaGuidance(province, amphoe) : fetchTrafficGuidance())
      .then((d) => {
        if (!current()) return;
        setData(d);
        setError(false);
      })
      .catch(() => current() && setError(true))
      .finally(() => current() && setLoading(false));
  }, [byArea, province, amphoe]);

  useEffect(() => {
    // A new area: drop the old cards (skeleton) first
    let live = true;
    setData(null);
    setError(false);
    setFilter('all');
    setShowAll(false);
    setSlow(false);
    const run = () => load(() => live);
    run();
    const id = setInterval(run, POLL_MS);
    const slowId = setTimeout(() => live && setSlow(true), 4000);   // an area's first answer can take a minute
    return () => {
      live = false;
      clearInterval(id);
      clearTimeout(slowId);
    };
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
  const visible = showAll ? filtered : filtered.slice(0, FIRST_CARDS);

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
          <h2 className="text-[15px] font-semibold text-ink-900 leading-6">
            ถนนสายหลัก{byArea && data?.area ? ` ${data.area}` : ''}: ติดตรงไหน เลี่ยงทางไหน
          </h2>
          <p className="text-[13px] text-slate-600 mt-0.5 leading-5">
            {byArea ? 'ถนนในพื้นที่ที่เลือก เรียงจากที่ติดมากสุด · อัปเดตทุก 5 นาที' : 'อัปเดตทุก 1 นาที'}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5 self-start sm:self-auto">
          {chip('all', `ทั้งหมด ${items.length}`, 'bg-ink-900 text-white dark:bg-slate-100 dark:text-slate-900')}
          {chip('congested', `รถติด ${countCongested}`, 'bg-red-600 text-white')}
          {chip('free', `คล่องตัว ${countFree}`, 'bg-emerald-600 text-white')}
          {countIncidents > 0 && chip('incidents', `มีเหตุ ${countIncidents}`, 'bg-amber-600 text-white')}
        </div>
      </div>

      {error && !data ? (
        <ErrorState message="โหลดข้อมูลถนนไม่สำเร็จ" onRetry={() => load()} retrying={loading} />
      ) : !data ? (
        <div className="flex flex-col gap-2">
          {byArea && slow && (
            <p role="status" className="text-sm text-ink-600">กำลังเตรียมข้อมูลถนนของพื้นที่นี้ ครั้งแรกอาจใช้เวลาถึง 1 นาที</p>
          )}
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {[1, 2, 3, 4, 5, 6].map((n) => (
              <Skeleton key={n} className="h-80" />
            ))}
          </div>
        </div>
      ) : !items.length ? (
        <p className="text-sm text-ink-500">พื้นที่นี้มีถนนสายหลักบนแผนที่จราจรน้อยเกินไป ยังสรุปไม่ได้</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3 auto-rows-fr">
          {visible.map((c) => {
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
                    {/* "คล่องตัว" above "รถติดรวม 6.9 กม." read as a contradiction */}
                    {c.status === 'free' && c.red_km >= 1 ? 'ส่วนใหญ่คล่อง' : c.status_label}
                  </Badge>
                </div>

                {/* 2. How long the jams add up to */}
                <p className="py-2 border-y border-cream-200 text-sm text-ink-600 tabular-nums">
                  {c.red_km ? (
                    <>
                      รถติดรวม <span className="font-medium text-ink-900">{c.red_km}</span> กม.
                    </>
                  ) : (
                    'ไม่มีช่วงที่รถติด'
                  )}
                </p>

                {/* 3. Hotspots: fixed 3 rows */}
                <div>
                  <span className="block text-xs font-medium text-ink-500 mb-1">จุดที่รถติดตอนนี้</span>
                  <ul className="flex flex-col gap-1 min-h-[4.5rem]">
                    {hotspots.length ? (
                      hotspots.map((s, i) => (
                        <li key={i} className="flex items-center gap-2 text-sm leading-5">
                          <span className="w-1.5 h-1.5 rounded-full bg-red-500 shrink-0" />
                          <span className="text-ink-900 truncate min-w-0 flex-1" title={s.label}>{s.label}</span>
                          <span className="text-xs text-ink-500 tabular-nums shrink-0">ติดยาว {s.km} กม.</span>
                        </li>
                      ))
                    ) : (
                      <li className="text-sm text-ink-500 leading-5">ไม่มีจุดที่รถติด</li>
                    )}
                  </ul>
                </div>

                {/* 4. Alternatives as chips. Green = the traffic on it moves well (recommended). */}
                <div>
                  <span className="block text-xs font-medium text-ink-500 mb-1">ทางเลี่ยง (สีเขียว = รถคล่อง)</span>
                  <div className="flex flex-wrap gap-1.5 min-h-[3.75rem] content-start">
                    {alts.length ? (
                      alts.map((a) => (
                        <span
                          key={a.name}
                          title={`${a.name}: ${a.recommended ? 'รถคล่อง' : 'รถชะลอตัว'}`}
                          className={`inline-flex items-center gap-1.5 max-w-full rounded-md border px-2 py-0.5 text-xs leading-5 ${
                            a.recommended
                              ? 'bg-emerald-50 border-emerald-200 text-emerald-800 dark:bg-emerald-950/40 dark:border-emerald-900 dark:text-emerald-300'
                              : 'bg-cream-100 border-cream-200 text-ink-600'
                          }`}
                        >
                          <span className="truncate">{a.name}</span>
                        </span>
                      ))
                    ) : (
                      <span className="text-sm text-ink-500">ยังไม่มีข้อมูลทางเลี่ยง</span>
                    )}
                  </div>
                </div>

                {/* 5. Advice for drivers; an incident (if any) replaces the line for traffic officers; both clamp so cards stay even */}
                <div className="rounded-lg bg-white dark:bg-slate-900 border border-cream-200 p-3 text-sm flex flex-col gap-1.5">
                  <p className="text-ink-900 line-clamp-3 min-h-[3.75rem]" title={c.action}>
                    <span className="font-semibold text-blue-600 dark:text-blue-400">แนะนำ: </span>{c.action}
                  </p>
                  {incident ? (
                    <p className="text-[13px] text-red-700 dark:text-red-300 line-clamp-2 min-h-[2.5rem] pt-1.5 border-t border-cream-200" title={incident.title}>
                      <span className="font-semibold">เหตุตอนนี้: </span>{incident.title}
                    </p>
                  ) : (
                    <p className="text-[13px] text-ink-600 line-clamp-2 min-h-[2.5rem] pt-1.5 border-t border-cream-200" title={c.signal}>
                      <span className="font-semibold">สำหรับเจ้าหน้าที่: </span>{c.signal}
                    </p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
      {data && filtered.length > FIRST_CARDS && (
        <div className="flex justify-center">
          <Button size="sm" onClick={() => setShowAll((v) => !v)} aria-expanded={showAll}>
            {showAll ? 'แสดงน้อยลง' : `ดูทั้งหมด ${filtered.length} เส้นทาง`}
          </Button>
        </div>
      )}
    </Card>
  );
}
