// เฝ้าระวังน้ำท่วม: river / canal stations against their banks, flooded roads, the 1-6 h zone outlook,
// urgent districts and the AI reading of the Traffy flood reports (flood part of /api/analytics/summary).
// Was a tab of City Analytics; now a tab of the Water Forecast page.
import { useCallback, useEffect, useState } from 'react';
import { fetchAnalytics } from '../../lib/api.js';
import { Card, Badge, SectionHeader, Skeleton, EmptyState, ErrorState } from '../dashboard/ui.jsx';
import { StatTile, StatusBanner } from '../dashboard/primitives.jsx';
import { fmtNum } from '../dashboard/format.js';
import FloodPredictionCard from '../dashboard/FloodPredictionCard.jsx';
import TraffyAnalysisCard from '../dashboard/TraffyAnalysisCard.jsx';

const POLL_MS = 60000;
const RISK_TONE = { สูง: 'red', ปานกลาง: 'yellow', ต่ำ: 'green' };
const PRIORITY_TONE = { เร่งด่วน: 'red', สูง: 'yellow', ปานกลาง: 'neutral', เฝ้าระวัง: 'yellow' };

function FloodSection({ d, isActive }) {
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

      <TraffyAnalysisCard isActive={isActive} />

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

export default function FloodWatchSection({ isActive }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback((refresh = false) => {
    setRefreshing(true);
    return fetchAnalytics(refresh)
      .then((d) => { setData(d); setError(false); })
      .catch(() => setError(true))
      .finally(() => setRefreshing(false));
  }, []);

  useEffect(() => {
    if (!isActive) return;
    load();
    const id = setInterval(() => load(), POLL_MS);
    return () => clearInterval(id);
  }, [isActive, load]);

  if (error && !data) return <ErrorState onRetry={() => load(true)} retrying={refreshing} />;
  if (!data) {
    return (
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[0, 1, 2, 3].map((i) => (
          <Card key={i} as="div" className="p-4"><Skeleton className="h-7 w-24" /><Skeleton className="h-3 w-32 mt-2" /></Card>
        ))}
      </div>
    );
  }
  return <FloodSection d={data.flood} isActive={isActive} />;
}
