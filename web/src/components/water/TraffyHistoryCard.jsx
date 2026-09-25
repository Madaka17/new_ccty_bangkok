// Traffy flood reports compared day to day and week to week (/api/traffy/history, traffy_history.py
// archives every report so the counts outlive the feed's 6 h window). Current period in blue, the
// previous one in gray, both named in the legend; every bar has a hover tooltip.
import { useCallback, useEffect, useState } from 'react';
import { fetchTraffyHistory } from '../../lib/api.js';
import { Card, Badge, SectionHeader, Skeleton, EmptyState, Segmented } from '../dashboard/ui.jsx';
import { StatTile } from '../dashboard/primitives.jsx';
import { fmtNum, fmtDateTime } from '../dashboard/format.js';

const POLL_MS = 300000;
const NOW = 'bg-blue-600';
const PREV = 'bg-slate-400/70';
const shortDate = (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString('th-TH', { day: 'numeric', month: 'short' });

function Legend({ now, prev }) {
  return (
    <div className="flex flex-wrap gap-3 text-xs text-slate-600">
      <span className="flex items-center gap-1.5"><span className={`w-2.5 h-2.5 rounded-sm ${NOW}`} aria-hidden="true" />{now}</span>
      <span className="flex items-center gap-1.5"><span className={`w-2.5 h-2.5 rounded-sm ${PREV}`} aria-hidden="true" />{prev}</span>
    </div>
  );
}

// Two bars per slot (current, previous), shared baseline and scale
function PairBars({ labels, now, prev, nowName, prevName, label, cut }) {
  const max = Math.max(1, ...now, ...prev);
  return (
    <div role="img" aria-label={label}>
      <div className="flex items-end gap-1 h-32">
        {labels.map((l, i) => (
          <div key={l} className="flex-1 min-w-0 h-full flex items-end justify-center gap-[2px]" title={`${l} · ${nowName} ${fmtNum(now[i])} · ${prevName} ${fmtNum(prev[i])}`}>
            <span className={`w-1/2 max-w-3 rounded-t ${cut != null && i > cut ? 'bg-transparent' : NOW}`} style={{ height: `${(now[i] / max) * 100}%` }} />
            <span className={`w-1/2 max-w-3 rounded-t ${PREV}`} style={{ height: `${(prev[i] / max) * 100}%` }} />
          </div>
        ))}
      </div>
      <div className="flex gap-1 mt-1 text-[10px] text-slate-500 tabular-nums">
        {labels.map((l, i) => <span key={l} className="flex-1 text-center">{labels.length > 12 && i % 3 ? '' : l}</span>)}
      </div>
    </div>
  );
}

// One bar per period, newest last (in blue)
function SeriesBars({ rows, labelOf, label }) {
  const max = Math.max(1, ...rows.map((r) => r.n));
  return (
    <div role="img" aria-label={label}>
      <div className="flex items-end gap-1 h-24">
        {rows.map((r, i) => (
          <div key={i} className="flex-1 h-full flex items-end" title={`${labelOf(r)} · ${fmtNum(r.n)} เรื่อง`}>
            <span className={`w-full rounded-t ${i === rows.length - 1 ? NOW : PREV}`} style={{ height: `${Math.max(r.n ? 3 : 0, (r.n / max) * 100)}%` }} />
          </div>
        ))}
      </div>
      <div className="flex gap-1 mt-1 text-[10px] text-slate-500 tabular-nums">
        {rows.map((r, i) => <span key={i} className="flex-1 text-center truncate">{i % 2 === rows.length % 2 ? '' : labelOf(r)}</span>)}
      </div>
    </div>
  );
}

function change(pct) {
  if (pct == null) return { text: 'ยังไม่มีข้อมูลช่วงก่อนหน้า', tone: 'blue' };
  if (pct === 0) return { text: 'เท่าเดิม', tone: 'blue' };
  return { text: `${pct > 0 ? '▲' : '▼'} ${Math.abs(pct)}%`, tone: pct > 0 ? 'red' : 'green' };
}

export default function TraffyHistoryCard({ isActive }) {
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);
  const [view, setView] = useState('day');

  const load = useCallback(() => fetchTraffyHistory().then((d) => { setData(d); setFailed(false); }).catch(() => setFailed(true)), []);
  useEffect(() => {
    if (!isActive) return;
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [isActive, load]);

  const header = (
    <SectionHeader
      id="traffy-history"
      title="เทียบเรื่องแจ้งน้ำท่วม วันต่อวัน / รายสัปดาห์"
      description={`Traffy Fondue · เทียบกับช่วงเวลาเดียวกันของวันหรือสัปดาห์ก่อน${data?.since ? ` · เริ่มเก็บข้อมูล ${fmtDateTime(data.since)}` : ''}`}
      action={<Segmented label="มุมมอง" value={view} onChange={setView} options={[['day', 'วันต่อวัน'], ['week', 'รายสัปดาห์']]} />}
    />
  );
  if (!data) {
    return <Card className="p-5">{header}{failed ? <EmptyState title="โหลดสถิติไม่สำเร็จ" /> : <Skeleton className="h-40 mt-3" />}</Card>;
  }

  const d = data.day;
  const w = data.week;
  const dc = change(d.change_pct);
  const wc = change(w.change_pct);
  const hours = [...Array(24)].map((_, h) => `${String(h).padStart(2, '0')}`);

  return (
    <Card className="p-5">
      {header}
      {view === 'day' ? (
        <div className="mt-3 flex flex-col gap-4">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <StatTile label="วันนี้" value={`${fmtNum(d.today)} เรื่อง`} sub={`ถึง ${String(data.now_hour).padStart(2, '0')}:59 น.`} tone="blue" />
            <StatTile label="เมื่อวานเวลาเดียวกัน" value={`${fmtNum(d.yesterday_same_time)} เรื่อง`} sub={`ทั้งวัน ${fmtNum(d.yesterday_total)} เรื่อง`} />
            <StatTile label="เปลี่ยนแปลง" value={dc.text} sub="วันนี้เทียบเมื่อวาน" tone={dc.tone} />
            <StatTile label="น้ำหัวเข่าขึ้นไป" value={`${fmtNum(d.today_deep)} เรื่อง`} sub={`เมื่อวานเวลาเดียวกัน ${fmtNum(d.yesterday_deep)}`} tone={d.today_deep > d.yesterday_deep ? 'red' : 'green'} />
          </div>
          <div>
            <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
              <p className="text-xs font-semibold text-slate-700">รายชั่วโมง</p>
              <Legend now="วันนี้" prev="เมื่อวาน" />
            </div>
            <PairBars labels={hours} now={d.hours_today} prev={d.hours_yesterday} nowName="วันนี้" prevName="เมื่อวาน" label="เรื่องแจ้งน้ำท่วมรายชั่วโมง วันนี้เทียบเมื่อวาน" cut={data.now_hour} />
          </div>
          <div>
            <p className="text-xs font-semibold text-slate-700 mb-2">รายวัน {d.days.length} วันล่าสุด</p>
            <SeriesBars rows={d.days} labelOf={(r) => shortDate(r.date)} label="เรื่องแจ้งน้ำท่วมรายวัน" />
          </div>
          {data.districts.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-slate-700 mb-1">รายเขต วันนี้เทียบเมื่อวานเวลาเดียวกัน</p>
              <table className="w-full text-[13px] text-slate-700">
                <thead>
                  <tr className="text-left text-xs text-slate-500 border-b border-slate-200">
                    <th className="py-1 font-medium">เขต</th>
                    <th className="py-1 font-medium text-right">วันนี้</th>
                    <th className="py-1 font-medium text-right">เมื่อวาน</th>
                    <th className="py-1 font-medium text-right">เปลี่ยนแปลง</th>
                  </tr>
                </thead>
                <tbody>
                  {data.districts.map((r) => {
                    const diff = r.today - r.yesterday_same_time;
                    return (
                      <tr key={r.district} className="border-b border-slate-100 last:border-0">
                        <td className="py-1">{r.district}</td>
                        <td className="py-1 text-right tabular-nums">{fmtNum(r.today)}</td>
                        <td className="py-1 text-right tabular-nums">{fmtNum(r.yesterday_same_time)}</td>
                        <td className="py-1 text-right tabular-nums">
                          {diff === 0 ? '–' : <Badge tone={diff > 0 ? 'red' : 'green'}>{diff > 0 ? '+' : ''}{diff}</Badge>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : (
        <div className="mt-3 flex flex-col gap-4">
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
            <StatTile label="สัปดาห์นี้" value={`${fmtNum(w.this_week)} เรื่อง`} sub="ตั้งแต่วันจันทร์" tone="blue" />
            <StatTile label="สัปดาห์ก่อนช่วงเดียวกัน" value={`${fmtNum(w.last_week_same_time)} เรื่อง`} sub={`ทั้งสัปดาห์ ${fmtNum(w.last_week_total)} เรื่อง`} />
            <StatTile label="เปลี่ยนแปลง" value={wc.text} sub="สัปดาห์นี้เทียบสัปดาห์ก่อน" tone={wc.tone} />
          </div>
          <div>
            <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
              <p className="text-xs font-semibold text-slate-700">รายวันในสัปดาห์</p>
              <Legend now="สัปดาห์นี้" prev="สัปดาห์ก่อน" />
            </div>
            <PairBars labels={w.weekday_labels} now={w.this_week_by_day} prev={w.last_week_by_day} nowName="สัปดาห์นี้" prevName="สัปดาห์ก่อน" label="เรื่องแจ้งน้ำท่วมรายวันในสัปดาห์ สัปดาห์นี้เทียบสัปดาห์ก่อน" cut={data.weekday} />
          </div>
          <div>
            <p className="text-xs font-semibold text-slate-700 mb-2">รายสัปดาห์ {w.weeks.length} สัปดาห์ล่าสุด</p>
            <SeriesBars rows={w.weeks} labelOf={(r) => `${shortDate(r.week_start)}`} label="เรื่องแจ้งน้ำท่วมรายสัปดาห์" />
          </div>
        </div>
      )}
      {data.since && data.generated_at - data.since < 2 * 86400 && (
        <p className="text-xs text-amber-700 mt-3">เพิ่งเริ่มเก็บข้อมูล ตัวเลขช่วงก่อนหน้าจะครบเมื่อเก็บได้ครบวันหรือสัปดาห์</p>
      )}
    </Card>
  );
}
