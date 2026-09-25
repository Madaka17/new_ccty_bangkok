// สรุปข้อมูลเมือง: five analytics sections from /api/analytics/summary
// (traffic overview, flood watch + 1-6 h outlook, black spots, visitors) with JSON/CSV export.
import { useCallback, useEffect, useState } from 'react';
import { fetchAnalytics, fetchVisitorStats } from '../lib/api.js';
import { trackView } from '../lib/telemetry.js';
import { Button, Card, Badge, SectionHeader, Skeleton, EmptyState, ErrorState } from './dashboard/ui.jsx';
import { PageHeader, StatTile, StatusBanner, Tabs, ShareBar } from './dashboard/primitives.jsx';
import { fmtDateTime, fmtNum, ROAD_LEVEL, STATUS } from './dashboard/format.js';
import FloodPredictionCard from './dashboard/FloodPredictionCard.jsx';
import HourlyViewsCard from './dashboard/HourlyViewsCard.jsx';
import RiskAnalysisCard from './dashboard/RiskAnalysisCard.jsx';

const POLL_MS = 60000;
const SECTIONS = [
  { id: 'traffic', label: 'ภาพรวมการจราจร' },
  { id: 'flood', label: 'เฝ้าระวังน้ำท่วม' },
  { id: 'accidents', label: 'อุบัติเหตุและมาตรการ' },
  { id: 'riskbkk', label: 'จุดเสี่ยง กทม. (AI)' },
  { id: 'visitors', label: 'ผู้เข้าใช้งาน' },
];
const RISK_TONE = { สูง: 'red', ปานกลาง: 'yellow', ต่ำ: 'green' };
const WATCH_TONE = { red: 'red', orange: 'yellow', yellow: 'yellow', green: 'green' };
const PRIORITY_TONE = { เร่งด่วน: 'red', สูง: 'yellow', ปานกลาง: 'neutral', เฝ้าระวัง: 'yellow' };
const TOPIC_LABEL = { traffic: 'Traffic', flood: 'Flood', road_status: 'Road Status', accidents: 'Accidents' };
const TOPIC_COLOR = { traffic: 'bg-blue-600', flood: 'bg-cyan-500', road_status: 'bg-amber-500', accidents: 'bg-red-600' };

function cciTone(cci) {
  if (cci == null) return 'neutral';
  return cci >= 40 ? 'red' : cci >= 20 ? 'yellow' : 'green';
}


// ---------------------------------------------------------------- 1. traffic
function TrafficSection({ d, onOpenRoad }) {
  if (!d?.ready) return <EmptyState title="รอข้อมูลเส้นจราจร" description="ระบบกำลังสร้างดัชนีถนนจาก Longdo Traffic (ครั้งแรกใช้เวลาหลายนาที)" />;
  const tone = cciTone(d.congestion_index);
  return (
    <div className="flex flex-col gap-4">
      <StatusBanner tone={tone} label={d.congestion_level}>
        ดัชนีความติดขัดภาพรวมเมือง (City Congestion Index) {d.congestion_index}/100 · โครงข่าย {fmtNum(Math.round(d.total_km))} กม. {fmtNum(d.road_count)} สาย · รายงานเหตุ 6 ชม. {d.reports_6h} รายการ
      </StatusBanner>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatTile label="City Congestion Index" value={`${d.congestion_index} / 100`} sub="แดง 100% + เหลือง 50% ของระยะทาง" tone={tone} badge={<Badge tone={tone} dot>{d.congestion_level}</Badge>} />
        <StatTile label="ดัชนีการระบายรถ" value={`${d.flow_index} / 100`} sub="ยิ่งสูงยิ่งคล่องตัว" tone="blue" />
        <StatTile label={`ถนนสายหลัก (≥ ${d.major_threshold_km} กม.)`} value={`${d.major.red_pct}% ติด`} sub={`${fmtNum(d.major.roads)} สาย · ติด ${d.major.red_km} จาก ${fmtNum(d.major.km)} กม.`} tone={d.major.red_pct >= 30 ? 'red' : d.major.red_pct >= 15 ? 'yellow' : 'green'} />
        <StatTile label={`ถนนสายรอง (< ${d.major_threshold_km} กม.)`} value={`${d.secondary.red_pct}% ติด`} sub={`${fmtNum(d.secondary.roads)} สาย · ติดขัด ${d.secondary.congested} สาย`} tone={d.secondary.red_pct >= 30 ? 'red' : d.secondary.red_pct >= 15 ? 'yellow' : 'green'} />
      </div>
      <Card className="p-5">
        <SectionHeader id="top5" title="5 ถนนที่มีการจราจรติดขัดสะสมสูงสุด" description="เรียงตามระยะทางที่เป็นสีแดง พร้อมสาเหตุจากรายงาน กทม. / Longdo / กล้อง AI ใน 6 ชั่วโมง" />
        <ol className="mt-3 divide-y divide-slate-100">
          {d.top5.map((r, i) => (
            <li key={r.name} className="py-3 flex gap-3">
              <span className="w-6 text-center text-sm font-semibold text-slate-500 tabular-nums shrink-0">{i + 1}</span>
              <div className="flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <button type="button" onClick={() => onOpenRoad?.(r.name)} className="cursor-pointer text-sm font-medium text-slate-900 hover:text-blue-700 truncate" title="เปิดกล้องบนถนนนี้">
                    {r.name}
                  </button>
                  <Badge tone={ROAD_LEVEL[r.level] || 'neutral'}>{r.level}</Badge>
                  <Badge tone="neutral">{r.major ? 'สายหลัก' : 'สายรอง'}</Badge>
                </div>
                <p className="text-xs text-slate-600 mt-1 tabular-nums">
                  ติดสะสม <span className="font-medium text-slate-900">{r.red_km}</span> จาก {r.length_km} กม. · ระบาย {r.flow}/100
                </p>
                <p className={`text-xs mt-1 ${r.causes.length ? 'text-red-700' : 'text-slate-500'}`}>สาเหตุ: {r.cause_text}</p>
              </div>
            </li>
          ))}
        </ol>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------- 2. flood
function FloodSection({ d }) {
  if (!d?.ready) return <EmptyState title="ไม่มีข้อมูลระดับน้ำ" description="ThaiWater ไม่ตอบสนอง ลองใหม่ภายหลัง" />;
  const worst = d.prediction[0];
  const sc = d.station_counts;
  return (
    <div className="flex flex-col gap-4">
      {worst && (
        <StatusBanner tone={RISK_TONE[worst.peak_level]} label={`เสี่ยง${worst.peak_level}`}>
          คาดการณ์ 1–6 ชม.: {worst.zone} เสี่ยงสูงสุด {worst.peak_score}/100 ที่ชั่วโมงที่ {worst.peak_h} · ฝนคาดการณ์ 6 ชม. {worst.rain_6h} มม. (โอกาส {worst.prob_6h}%)
        </StatusBanner>
      )}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatTile label="สถานีแม่น้ำล้นตลิ่ง" value={fmtNum(sc.river?.overflow || 0)} sub={`ใกล้วิกฤต ${sc.river?.high || 0} · ปกติ ${sc.river?.normal || 0}`} tone={sc.river?.overflow ? 'red' : sc.river?.high ? 'yellow' : 'green'} />
        <StatTile label="คลองระบายน้ำเต็ม" value={fmtNum(sc.canal?.overflow || 0)} sub={`ห่างตลิ่ง ≤ 20 ซม. อีก ${sc.canal?.high || 0} จาก ${sc.canal_total || 0} จุดวัด`} tone={sc.canal?.overflow ? 'red' : sc.canal?.high ? 'yellow' : 'green'} />
        <StatTile label="ถนนน้ำท่วม (≥ 10 ซม.)" value={fmtNum(d.flood_roads.flooding || 0)} sub={`น้ำขังเล็กน้อย ${d.flood_roads.slight || 0} จุด`} tone={d.flood_roads.flooding ? 'red' : d.flood_roads.slight ? 'yellow' : 'green'} />
        <StatTile label="เขตเฝ้าระวังเร่งด่วน" value={fmtNum(d.urgent_districts.filter((u) => u.priority === 'เร่งด่วน').length)} sub={`เฝ้าระวังรวม ${d.urgent_districts.length} เขต`} tone={d.urgent_districts.some((u) => u.priority === 'เร่งด่วน') ? 'red' : 'green'} />
      </div>

      <FloodPredictionCard prediction={d.prediction} modelNote={d.model_note} />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card className="p-5">
          <SectionHeader id="urgent" title="จุดเฝ้าระวังเร่งด่วนรายเขต" description="สถานีล้นตลิ่ง / ใกล้วิกฤต และถนนที่มีน้ำท่วมขังในเขต" />
          {d.urgent_districts.length === 0 ? (
            <p className="text-sm text-slate-600 mt-3">ไม่มีเขตที่ระดับน้ำเกินเกณฑ์ในขณะนี้</p>
          ) : (
            <ul className="mt-3 divide-y divide-slate-100">
              {d.urgent_districts.map((u) => (
                <li key={u.district} className="py-2.5">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-slate-900">{u.district}</span>
                    <Badge tone={PRIORITY_TONE[u.priority]} dot>{u.priority}</Badge>
                    <span className="ml-auto text-xs text-slate-500 tabular-nums">ล้น {u.overflow} · สูง {u.high} · ถนนท่วม {u.flood_roads}</span>
                  </div>
                  <p className="text-xs text-slate-600 mt-1">{u.items.join(' · ')}</p>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card className="p-5">
          <SectionHeader id="stations" title="สถานีที่ระดับน้ำเทียบจุดวิกฤต" description="แม่น้ำ: ระยะห่างจากตลิ่ง · คลอง: % ความจุ" />
          {d.alert_stations.length === 0 ? (
            <p className="text-sm text-slate-600 mt-3">ทุกสถานีอยู่ในเกณฑ์ปกติ</p>
          ) : (
            <ul className="mt-3 divide-y divide-slate-100 max-h-80 overflow-y-auto scroll-soft">
              {d.alert_stations.map((s) => (
                <li key={`${s.kind}-${s.name}`} className="py-2 flex items-center gap-2 text-sm">
                  <Badge tone={s.level === 'overflow' ? 'red' : 'yellow'}>{s.level === 'overflow' ? 'ล้น' : 'ใกล้วิกฤต'}</Badge>
                  <span className="text-slate-900 truncate">{s.name}</span>
                  <span className="text-xs text-slate-500 truncate">{s.district}</span>
                  <span className="ml-auto text-xs text-slate-600 tabular-nums whitespace-nowrap">
                    {s.kind === 'river' ? (s.diff_bank != null ? `ต่ำกว่าตลิ่ง ${s.diff_bank} ม.` : `${s.msl ?? '–'} ม.รทก.`) : (s.diff_bank != null ? (s.diff_bank > 0 ? `ต่ำกว่าตลิ่ง ${s.diff_bank} ม.` : `เกินตลิ่ง ${Math.abs(s.diff_bank)} ม.`) : `${s.storage_pct ?? '–'}%`)}
                    {s.trend != null && <span className={s.trend > 0 ? 'text-red-700' : 'text-emerald-700'}> {s.trend > 0 ? '▲' : '▼'}{Math.abs(s.trend)}</span>}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- hourly bars chart
function Bars({ values, labelOf, highlight }) {
  if (!values?.length) return null;
  const max = Math.max(1, ...values);
  return (
    <div>
      <div className="flex items-end gap-[3px] h-28" role="img" aria-label="ผู้เสียชีวิตรายชั่วโมง">
        {values.map((v, i) => {
          const isHigh = highlight?.has(i);
          const pct = Math.max(4, (v / max) * 100);
          return (
            <div key={i} className="flex-1 flex flex-col justify-end items-center group relative" title={`${String(i).padStart(2, '0')}:00 · ${v} คน`}>
              <span className="opacity-0 group-hover:opacity-100 transition-opacity absolute -top-6 text-[10px] font-semibold tabular-nums text-slate-700 bg-white px-1 rounded shadow-xs border border-slate-200 pointer-events-none z-10 whitespace-nowrap">
                {v} คน
              </span>
              <div
                className={`w-full rounded-sm transition-all duration-200 ${
                  isHigh ? 'bg-red-600 shadow-xs' : i < 6 || i >= 22 ? 'bg-slate-400' : 'bg-slate-200 hover:bg-slate-300'
                }`}
                style={{ height: `${pct}%` }}
              />
            </div>
          );
        })}
      </div>
      <div className="mt-2 flex justify-between text-[11px] text-slate-500 tabular-nums">
        <span>00:00</span>
        <span>06:00</span>
        <span>12:00</span>
        <span>18:00</span>
        <span>23:00</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- 4. accidents
function AccidentSection({ d }) {
  if (!d?.ready) return <EmptyState title="ไม่มีข้อมูล Thai RSC" description="ยังดึงสถิติอุบัติเหตุไม่ได้" />;
  const hours = d.dead_by_hour?.length === 24 ? d.dead_by_hour : null;
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatTile label="เสียชีวิตวันนี้" value={fmtNum(d.today?.dead)} sub={`บาดเจ็บ ${fmtNum(d.today?.injured)} ราย`} tone={d.today?.dead ? 'red' : 'green'} />
        <StatTile label={`เสียชีวิตสะสมปี ${d.year_be || ''}`} value={fmtNum(d.ytd?.dead)} sub={`บาดเจ็บ ${fmtNum(d.ytd?.injured)} ราย`} tone="red" />
        <StatTile label="จุดเกิดเหตุกระจุกตัว" value={fmtNum(d.black_spots.length)} sub={`จากพิกัดอุบัติเหตุ ${fmtNum(d.points_total)} จุด`} tone="yellow" />
        <StatTile label="เขตเสี่ยงสูงสุด" value={d.districts[0]?.name || '–'} sub={d.districts[0] ? `เสียชีวิต ${d.districts[0].dead} · บาดเจ็บ ${d.districts[0].injured}` : ''} />
      </div>
      {d.citywide_measures.length > 0 && (
        <StatusBanner tone="yellow" label="มาตรการทั่วเมือง">
          {d.citywide_measures.join(' · ')}
        </StatusBanner>
      )}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-4">
        <Card className="p-5">
          <SectionHeader id="black-spots" title="Black Spots และแนวทางลดอุบัติเหตุเฉพาะพื้นที่" description="จัดกลุ่มพิกัดอุบัติเหตุในรัศมี ~275 ม. · คะแนน = เคส + 3×บาดเจ็บ + 10×เสียชีวิต · มาตรการเลือกตามประเภทถนน" />
          <ol className="mt-3 divide-y divide-slate-100">
            {d.black_spots.map((b, i) => (
              <li key={`${b.lat}-${b.lon}`} className="py-3 flex gap-3">
                <span className="w-6 text-center text-sm font-semibold text-slate-500 tabular-nums shrink-0">{i + 1}</span>
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-slate-900 truncate" title={b.place}>{b.place}</span>
                    <Badge tone={PRIORITY_TONE[b.priority]} dot>{b.priority}</Badge>
                    <Badge tone="neutral">{b.road_type}</Badge>
                  </div>
                  <p className="text-xs text-slate-600 mt-1 tabular-nums">
                    เขต{b.district} · {fmtNum(b.cases)} เคส · เสียชีวิต <span className="font-medium text-red-700">{b.dead}</span> · บาดเจ็บ {fmtNum(b.injured)} · ปี {b.years.join('/')}
                  </p>
                  <ul className="mt-1.5 flex flex-col gap-0.5">
                    {b.measures.map((m) => (
                      <li key={m} className="text-xs text-slate-700 flex gap-1.5">
                        <span className="text-blue-600 shrink-0">•</span>
                        <span>{m}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </li>
            ))}
          </ol>
          <p className="text-[11px] text-slate-500 mt-3">{d.injury_note} · แหล่งข้อมูล {d.source || 'Thai RSC'}</p>
        </Card>
        <div className="flex flex-col gap-4">
          <Card className="p-5">
            <SectionHeader id="by-district" title="รายเขต" description="เรียงตามผู้เสียชีวิตสะสมปีนี้" />
            <ul className="mt-3 divide-y divide-slate-100">
              {d.districts.map((x) => (
                <li key={x.name} className="py-1.5 flex items-center text-sm">
                  <span className="text-slate-900">{x.name}</span>
                  <span className="ml-auto text-xs tabular-nums text-slate-600">
                    <span className="font-medium text-red-700">{x.dead}</span> ตาย · {fmtNum(x.injured)} เจ็บ
                  </span>
                </li>
              ))}
            </ul>
          </Card>
          {hours && (
            <Card className="p-5">
              <SectionHeader id="by-hour" title="ผู้เสียชีวิตรายชั่วโมง" description="สะสมปีนี้ ทั้งกรุงเทพฯ" />
              <div className="mt-3">
                <Bars values={hours} labelOf={(i) => `${i}`} highlight={new Set(hours.map((v, i) => [v, i]).sort((a, b) => b[0] - a[0]).slice(0, 3).map((x) => x[1]))} />
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- 5. visitors
const VISITOR_POLL_MS = 5000;
const PAGE_LABEL = {
  dashboard: 'Traffic Dashboard', analytics: 'City Analytics', cameras: 'กล้อง CCTV', map: 'Traffic Map',
  water: 'น้ำท่วม', yolo: 'Camera AI', 'bma-count': 'นับรถกล้อง กทม.', helmet: 'Helmet Check',
  wrongway: 'Wrong-Way Check', ai: 'AI ผู้ช่วย',
};
const SUB_LABEL = {
  overview: 'ภาพรวม', trend: 'แนวโน้ม', flood: 'น้ำท่วม', roads: 'ถนน', incidents: 'เหตุการณ์', 'bma-reports': 'รายงาน กทม.',
  safety: 'ความปลอดภัย', traffic: 'จราจร', density: 'ความหนาแน่น', accidents: 'อุบัติเหตุ', visitors: 'ผู้เข้าใช้งาน',
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

function VisitorSection({ d: initial, isActive }) {
  const [d, setD] = useState(initial);
  const [lastOk, setLastOk] = useState(Date.now());
  const [stale, setStale] = useState(false);

  useEffect(() => {
    if (!isActive) return;
    let alive = true;
    const tick = () => {
      if (document.visibilityState !== 'visible') return;
      fetchVisitorStats()
        .then((x) => {
          if (!alive) return;
          setD(x);
          setLastOk(Date.now());
          setStale(false);
        })
        .catch(() => alive && setStale(true));
    };
    tick();
    const id = setInterval(tick, VISITOR_POLL_MS);
    document.addEventListener('visibilitychange', tick);
    return () => {
      alive = false;
      clearInterval(id);
      document.removeEventListener('visibilitychange', tick);
    };
  }, [isActive]);

  if (!d?.ready) return <EmptyState title="ไม่มีข้อมูลผู้เข้าชม" />;
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

// ---------------------------------------------------------------- page
export default function AnalyticsPage({ isActive, onOpenRoad }) {
  const [section, setSection] = useState('traffic');
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback((refresh = false) => {
    setRefreshing(true);
    return fetchAnalytics(refresh)
      .then((d) => {
        setData(d);
        setError(false);
      })
      .catch(() => setError(true))
      .finally(() => setRefreshing(false));
  }, []);

  useEffect(() => {
    if (!isActive) return;
    load();
    const id = setInterval(() => load(), POLL_MS);
    return () => clearInterval(id);
  }, [isActive, load]);

  const pick = (id) => {
    setSection(id);
    trackView(`analytics:${id}`);
  };

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="สรุปข้อมูลเมือง"
        description={`จราจร · น้ำท่วม · ความหนาแน่น · อุบัติเหตุ · ผู้เข้าใช้งาน${data ? ` · อัปเดต ${fmtDateTime(data.generated_at)}` : ''}`}
        actions={
          <Button size="sm" loading={refreshing} onClick={() => load(true)}>
            รีเฟรช
          </Button>
        }
      />
      <Tabs label="หมวดสรุปข้อมูล" value={section} onChange={pick} tabs={SECTIONS} />
      {error && !data ? (
        <ErrorState onRetry={() => load(true)} retrying={refreshing} />
      ) : !data ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {[0, 1, 2, 3].map((i) => (
            <Card key={i} as="div" className="p-4"><Skeleton className="h-7 w-24" /><Skeleton className="h-3 w-32 mt-2" /></Card>
          ))}
        </div>
      ) : (
        <>
          {section === 'traffic' && <TrafficSection d={data.traffic} onOpenRoad={onOpenRoad} />}
          {section === 'flood' && <FloodSection d={data.flood} />}
          {section === 'accidents' && <AccidentSection d={data.accidents} />}
          {section === 'visitors' && <VisitorSection d={data.visitors} isActive={isActive} />}
          {section === 'riskbkk' && <RiskAnalysisCard isActive={isActive} />}
        </>
      )}
    </div>
  );
}
