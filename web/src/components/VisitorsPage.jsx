// Visitors: who is on the site now, today's users and views, busiest pages and hours (/api/visitors,
// polled every 5 s while open). Was a tab of City Analytics; now its own page in the menu.
import { useEffect, useState } from 'react';
import { fetchVisitorStats } from '../lib/api.js';
import { Card, Badge, SectionHeader, Skeleton, EmptyState, ErrorState } from './dashboard/ui.jsx';
import { PageHeader, StatTile, ShareBar } from './dashboard/primitives.jsx';
import { fmtNum } from './dashboard/format.js';
import HourlyViewsCard from './dashboard/HourlyViewsCard.jsx';

const TOPIC_LABEL = { traffic: 'Traffic', flood: 'Flood', road_status: 'Road Status', accidents: 'Accidents' };
const TOPIC_COLOR = { traffic: 'bg-blue-600', flood: 'bg-cyan-500', road_status: 'bg-amber-500', accidents: 'bg-red-600' };
const VISITOR_POLL_MS = 5000;
const PAGE_LABEL = {
  dashboard: 'Traffic Dashboard', analytics: 'City Analytics', cameras: 'กล้อง CCTV', map: 'Traffic Map',
  water: 'น้ำท่วม', yolo: 'Camera AI', 'bma-count': 'นับรถกล้อง กทม.', helmet: 'Helmet Check',
  wrongway: 'Wrong-Way Check', ai: 'AI ผู้ช่วย', safety: 'Accidents & Risk', visitors: 'Visitors', alerts: 'Alerts',
};
const SUB_LABEL = {
  overview: 'ภาพรวม', trend: 'แนวโน้ม', flood: 'น้ำท่วม', roads: 'ถนน', incidents: 'เหตุการณ์', 'bma-reports': 'รายงาน กทม.',
  safety: 'ความปลอดภัย', traffic: 'จราจร', density: 'ความหนาแน่น', accidents: 'อุบัติเหตุ', riskbkk: 'จุดเสี่ยง กทม.', visitors: 'ผู้เข้าใช้งาน',
};
const hh = (h) => `${String(h).padStart(2, '0')}:00`;
function pageLabel(view) {
  const [base, sub] = view.split(':');
  const name = PAGE_LABEL[base] || base;
  return sub ? `${name} › ${SUB_LABEL[sub] || sub}` : name;
}

// Ranked list with a proportional bar behind each row, so the biggest page reads at a glance
function RankList({ rows, unit, empty }) {
  if (!rows.length) return <p className="text-sm text-slate-500 mt-2">{empty}</p>;
  const max = Math.max(1, ...rows.map((r) => r.n));
  return (
    <ul className="mt-2 flex flex-col gap-1">
      {rows.map((r) => (
        <li key={r.key} className="relative rounded-md px-2 py-1.5 text-sm flex items-center overflow-hidden">
          <span className="absolute inset-y-0 left-0 bg-blue-500/10 dark:bg-blue-400/15 rounded-md" style={{ width: `${(r.n / max) * 100}%` }} aria-hidden="true" />
          <span className="relative text-slate-900 truncate">{r.label}</span>
          <span className="relative ml-auto pl-3 text-xs tabular-nums text-slate-600 whitespace-nowrap">{fmtNum(r.n)} {unit}</span>
        </li>
      ))}
    </ul>
  );
}

function VisitorSection({ isActive }) {
  const [d, setD] = useState(null);
  const [lastOk, setLastOk] = useState(Date.now());
  const [stale, setStale] = useState(false);

  useEffect(() => {
    if (!isActive) return;
    let alive = true;
    const tick = (first = false) => {
      if (!first && document.visibilityState !== 'visible') return;   // first load always, then only while shown
      fetchVisitorStats()
        .then((x) => {
          if (!alive) return;
          setD(x);
          setLastOk(Date.now());
          setStale(false);
        })
        .catch(() => alive && setStale(true));
    };
    tick(true);
    const id = setInterval(() => tick(), VISITOR_POLL_MS);
    const onShow = () => tick();
    document.addEventListener('visibilitychange', onShow);
    return () => {
      alive = false;
      clearInterval(id);
      document.removeEventListener('visibilitychange', onShow);
    };
  }, [isActive]);

  if (!d) {
    return stale
      ? <ErrorState message="โหลดข้อมูลผู้เข้าใช้งานไม่สำเร็จ" />
      : (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {[0, 1, 2, 3].map((i) => (
            <Card key={i} as="div" className="p-4"><Skeleton className="h-7 w-24" /><Skeleton className="h-3 w-32 mt-2" /></Card>
          ))}
        </div>
      );
  }
  if (!d.ready) return <EmptyState title="ไม่มีข้อมูลผู้เข้าชม" />;
  const prev = d.dau_yesterday_same_time ?? d.dau_yesterday;
  const delta = d.dau - prev;
  const thisHour = d.hours_today?.[d.current_hour] ?? 0;
  const onlineRows = [...(d.online_by_view || [])].sort((a, b) => b.users - a.users).map((v) => ({ key: v.view, label: pageLabel(v.view), n: v.users }));
  const viewRows = d.by_view.slice(0, 6).map((v) => ({ key: v.view, label: pageLabel(v.view), n: v.views }));

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2 text-xs text-slate-600" role="status">
        <span className="relative flex w-2.5 h-2.5">
          {!stale && <span className="absolute inset-0 rounded-full bg-emerald-500 animate-ping opacity-60" />}
          <span className={`relative w-2.5 h-2.5 rounded-full ${stale ? 'bg-red-500' : 'bg-emerald-500'}`} />
        </span>
        {stale ? 'ขาดการเชื่อมต่อ กำลังลองใหม่' : `อัปเดตสดทุก ${VISITOR_POLL_MS / 1000} วินาที`}
        <span className="text-slate-500 tabular-nums">· ล่าสุด {new Date(lastOk).toLocaleTimeString('th-TH')}</span>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatTile label="กำลังใช้งานอยู่ตอนนี้" value={`${fmtNum(d.online)} คน`} sub="เปิดเว็บอยู่ใน 90 วินาทีล่าสุด" tone="green" badge={<Badge tone="green" dot>Live</Badge>} />
        <StatTile label="ผู้ใช้วันนี้" value={`${fmtNum(d.dau)} คน`} sub={`เมื่อวานเวลาเดียวกัน ${fmtNum(prev)} (${delta >= 0 ? '+' : ''}${fmtNum(delta)})`} tone="blue" />
        <StatTile label="ยอดเปิดดูวันนี้" value={`${fmtNum(d.views_today)} ครั้ง`} sub={`ชั่วโมงนี้ ${fmtNum(thisHour)} ครั้ง`} />
        <StatTile label="ช่วงคนใช้มากสุด" value={d.peak_hours[0] ? hh(d.peak_hours[0].hour) : '–'} sub={d.peak_hours.length ? `สถิติ ${d.peak_window_days} วันล่าสุด` : 'ยังไม่มีข้อมูล'} tone="yellow" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="flex flex-col gap-4">
          <Card className="p-5">
            <SectionHeader id="online-now" title="ตอนนี้กำลังดูหน้าไหน" description="ผู้ใช้ที่ออนไลน์อยู่ แยกตามหน้าที่เปิด" />
            <RankList rows={onlineRows} unit="คน" empty="ยังไม่มีผู้ใช้ออนไลน์" />
          </Card>
          <Card className="p-5">
            <SectionHeader id="topic-share" title="หน้ายอดนิยมวันนี้" description="นับทุกครั้งที่เปิดหน้าหรือเปลี่ยนแท็บ" />
            {d.views_today ? (
              <div className="mt-3">
                <ShareBar parts={d.by_topic.filter((t) => t.views).map((t) => ({ label: TOPIC_LABEL[t.topic], value: t.views, color: TOPIC_COLOR[t.topic] }))} />
              </div>
            ) : null}
            <RankList rows={viewRows} unit="ครั้ง" empty="ยังไม่มีการเปิดดูวันนี้" />
          </Card>
        </div>
        <HourlyViewsCard
          hours={d.hours_today || d.hours}
          currentHour={d.current_hour}
          peakHours={d.peak_hours}
          dauSeries={d.dau_series}
        />
      </div>
    </div>
  );
}

export default function VisitorsPage({ isActive }) {
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title="Visitors" description="ผู้เข้าใช้งานเว็บ: ออนไลน์ตอนนี้ ผู้ใช้และยอดเปิดดูวันนี้ หน้ายอดนิยม และช่วงเวลาที่คนใช้มากสุด" />
      <VisitorSection isActive={isActive} />
    </div>
  );
}
