import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fetchWaterSummary } from '../lib/api.js';
import { trackView } from '../lib/telemetry.js';
import { Badge, Button, ErrorState } from './dashboard/ui.jsx';
import { PageHeader, StatTile, StatusBanner } from './dashboard/primitives.jsx';
import { fmtDateTime } from './dashboard/format.js';
import { PAGE_TITLES } from './Sidebar.jsx';
import ForecastChart from './water/ForecastChart.jsx';
import WaterMap from './water/WaterMap.jsx';
import ViewSwitch from './ViewSwitch.jsx';
import FloodAgentCard from './dashboard/FloodAgentCard.jsx';
import FloodAnalysisGuide from './water/FloodAnalysisGuide.jsx';
import FloodWatchSection from './water/FloodWatchSection.jsx';
import CitizenReportsSection from './water/CitizenReportsSection.jsx';
import ShelterSection from './water/ShelterSection.jsx';
import FloodRoadsCard from './water/FloodRoadsCard.jsx';
import FloodPointsMap from './water/FloodPointsMap.jsx';
import NorthFlowSection from './water/NorthFlowSection.jsx';
import { RiverStations, CanalCard, NtwRainCard } from './water/WaterLists.jsx';

const POLL_MS = 60000;
const TABS = [
  { id: 'situation', label: 'ระดับน้ำตอนนี้', hint: 'น้ำในแม่น้ำและคลอง น้ำทะเลหนุน ถนนน้ำท่วม และฝน', icon: 'water' },
  { id: 'north', label: 'น้ำเหนือ → ภาคกลาง', hint: 'น้ำจากภาคเหนือไหลลงมาถึงกรุงเทพฯ เมื่อไร และมากแค่ไหน', icon: 'water' },
  { id: 'roads', label: 'ถนนน้ำท่วม', hint: 'แผนที่ถนนที่น้ำท่วมตอนนี้ จากกล้อง เครื่องวัด และกรมทางหลวง', icon: 'map' },
  { id: 'watch', label: 'เขตเสี่ยงน้ำท่วม', hint: 'เขตไหนต้องระวัง และคาดการณ์ 1-6 ชม. ข้างหน้า', icon: 'alerts' },
  { id: 'shelter', label: 'จุดพักพิงใกล้ฉัน', hint: 'จุดพักพิงชั่วคราวของ กทม. ใกล้คุณ พร้อมเบอร์โทรและเส้นทาง', icon: 'map' },
  { id: 'reports', label: 'เรื่องที่คนแจ้ง', hint: 'เรื่องน้ำท่วมที่คนแจ้งผ่าน Traffy Fondue และข่าวจราจร', icon: 'visitors' },
  { id: 'agent', label: 'AI สรุปสถานการณ์', hint: 'AI สรุปว่าตอนนี้น่าห่วงแค่ไหน เขตไหนต้องระวัง ถนนไหนควรเลี่ยง', icon: 'analytics' },
  { id: 'analysis', label: 'AI คาดการณ์รายโซน', hint: 'AI คาดการณ์น้ำท่วมแต่ละโซน และคำแนะนำสำหรับประชาชน', icon: 'ai' },
];
const DEFAULT_STATION = '1132'; // สะพานนวลฉวี: nearest official 7-day forecast to Bangkok

// Overall outlook line derived from the pieces we have (kept deliberately simple and explainable)
function outlook(s) {
  if (!s) return null;
  const over = s.river_counts?.overflow || 0;
  const high = s.river_counts?.high || 0;
  const roads = (s.flood_roads?.flooding || 0) + (s.flood_roads?.slight || 0);
  const rain = s.rain_warnings?.some((r) => r.kind === 'forecast');
  const tide = Math.max(0, ...(s.tide || []).map((t) => t.max ?? 0));
  if (over >= 3 || roads >= 5) return { tone: 'red', label: 'เสี่ยงสูง', text: `น้ำล้นตลิ่ง ${over} จุด${roads ? ` และถนนน้ำท่วม ${roads} จุด` : ''} คนที่อยู่ริมน้ำหรือที่ลุ่มควรเตรียมรับมือ` };
  if (over >= 1 || high >= 8 || rain || tide >= 1.2) return { tone: 'yellow', label: 'เฝ้าระวัง', text: `${over ? `น้ำล้นตลิ่ง ${over} จุด · ` : ''}ใกล้ล้นตลิ่ง ${high} จุด${rain ? ' · อาจมีฝนหนักใน 24 ชม.' : ''}${tide >= 1.2 ? ' · น้ำทะเลหนุนสูง' : ''} บ้านริมแม่น้ำเจ้าพระยาที่อยู่นอกคันกั้นน้ำควรระวังช่วงน้ำขึ้น` };
  return { tone: 'green', label: 'ปกติ', text: 'น้ำในแม่น้ำและคลองส่วนใหญ่ยังต่ำกว่าตลิ่ง ไม่มีเตือนฝนหนัก' };
}

export default function WaterPage({ isActive, onToast, onNavigate, onAsk, onOpenRoad }) {
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [stationId, setStationId] = useState(DEFAULT_STATION);
  const [tab, setTab] = useState('situation');
  const pickTab = (id) => {
    setTab(id);
    trackView(`water:${id}`);
  };
  const chartRef = useRef(null);
  // Picking a station from a list further down the page: switch and bring the chart into view
  const pickStation = useCallback((id) => {
    setStationId(String(id));
    chartRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, []);

  const load = useCallback(() => {
    setRefreshing(true);
    return fetchWaterSummary()
      .then((s) => {
        setSummary(s);
        setError(false);
      })
      .catch(() => setError(true))
      .finally(() => setRefreshing(false));
  }, []);

  useEffect(() => {
    if (!isActive) return;
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [isActive, load]);

  // Chart station list: upstream official stations first, then every metro station
  const stations = useMemo(() => {
    if (!summary) return [];
    const up = (summary.official_stations || []).filter((s) => !summary.river.some((r) => r.id === s.id)).map((s) => ({ ...s, district: '', official_forecast: true }));
    return [...up, ...summary.river];
  }, [summary]);

  useEffect(() => {
    if (stations.length && !stations.some((s) => s.id === stationId)) setStationId(stations[0].id);
  }, [stations, stationId]);

  const loading = !summary;
  const o = outlook(summary);
  const tideMax = summary?.tide?.length ? summary.tide.reduce((a, b) => ((b.max ?? -9) > (a.max ?? -9) ? b : a)) : null;
  const roads = summary?.flood_roads;

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={PAGE_TITLES.water}
        description={`น้ำท่วมและระดับน้ำ กรุงเทพฯ และปริมณฑล · ${summary ? `อัปเดต ${fmtDateTime(summary.updated_at)}` : 'กำลังโหลด'}`}
        actions={
          <>
            {summary?.stale && <Badge tone="yellow">ข้อมูลยังไม่อัปเดต</Badge>}
            <Button size="sm" onClick={load} loading={refreshing}>
              รีเฟรช
            </Button>
          </>
        }
      />

      <ViewSwitch tabs={TABS} value={tab} onChange={pickTab} label="หัวข้อน้ำท่วม" />

      {tab === 'roads' && (
        <>
          <FloodPointsMap isActive={isActive} onReport={() => onNavigate('report')} />
          <FloodRoadsCard isActive={isActive} onOpenRoad={onOpenRoad} />
        </>
      )}

      {tab === 'north' && <NorthFlowSection isActive={isActive} onOpenRoad={onOpenRoad} />}

      {tab === 'watch' && <FloodWatchSection isActive={isActive} />}

      {tab === 'reports' && <CitizenReportsSection isActive={isActive} />}

      {tab === 'shelter' && <ShelterSection isActive={isActive} />}

      {tab === 'agent' && <FloodAgentCard isActive={isActive} onOpenRoad={onOpenRoad} />}

      {tab === 'analysis' && <FloodAnalysisGuide isActive={isActive} onNavigate={onNavigate} onAsk={onAsk} />}

      {tab === 'situation' && (
        <>
          {error && !summary && <ErrorState message="โหลดข้อมูลระดับน้ำไม่สำเร็จ" onRetry={load} retrying={refreshing} />}
          {summary?.api_key?.rejected && (
            <p role="status" className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
              แหล่งข้อมูลระดับน้ำขัดข้อง ระบบกำลังต่อใหม่เอง ข้อมูลบางส่วนอาจยังไม่อัปเดต
            </p>
          )}
          {error && summary && (
            <p role="status" className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
              อัปเดตล่าสุดไม่สำเร็จ แสดงข้อมูลเมื่อ {fmtDateTime(summary.updated_at)}
            </p>
          )}

          {o && (
            <StatusBanner tone={o.tone} label={o.label}>
              {o.text}
            </StatusBanner>
          )}

          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <StatTile
              label="จุดวัดน้ำที่ล้นตลิ่ง"
              value={summary ? `${summary.river_counts.overflow} / ${summary.river.length}` : '–'}
              sub={summary ? `ใกล้ล้นอีก ${summary.river_counts.high} จุด` : ''}
              badge={summary?.river_counts.overflow ? <Badge tone="red" dot>ล้น</Badge> : null}
              loading={loading}
            />
            <StatTile
              label="น้ำทะเลหนุนสูงสุดวันนี้"
              value={tideMax?.max != null ? `${tideMax.max.toFixed(2)} ม.` : '–'}
              sub={tideMax ? `${tideMax.name} เวลา ${tideMax.max_time} น.` : ''}
              badge={tideMax?.max >= 1.2 ? <Badge tone="yellow">หนุนสูง</Badge> : null}
              loading={loading}
            />
            <StatTile
              label="ถนน กทม. ที่น้ำท่วม"
              value={roads ? `${roads.flooding + roads.slight} จุด` : '–'}
              sub={roads ? `จากเครื่องวัดบนถนน ${roads.flooding + roads.slight + roads.normal} จุด` : ''}
              badge={roads?.flooding ? <Badge tone="red" dot>ท่วม</Badge> : null}
              loading={loading}
            />
            <StatTile
              label="คลอง กทม. ที่น้ำสูง"
              value={summary ? `${summary.canal_counts.overflow + summary.canal_counts.high} / ${summary.canal_total}` : '–'}
              sub={summary ? `ล้นตลิ่ง ${summary.canal_counts.overflow} · ใกล้ล้น ${summary.canal_counts.high}` : ''}
              badge={summary?.canal_counts.overflow ? <Badge tone="red" dot>ล้น</Badge> : null}
              loading={loading}
            />
          </div>

          <WaterMap isActive={isActive} onPickStation={pickStation} />

          {stations.length > 0 && <ForecastChart stations={stations} stationId={stationId} onPickStation={setStationId} anchorRef={chartRef} />}

          <RiverStations rows={summary?.river} selectedId={stationId} onSelect={pickStation} loading={loading} />

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <CanalCard canals={summary?.canals} counts={summary?.canal_counts} total={summary?.canal_total} roads={roads} loading={loading} />
            <NtwRainCard ntw={summary?.ntw} loading={loading} />
          </div>

          <p className="text-xs text-slate-500 leading-5 px-1">
            ข้อมูลจากคลังข้อมูลน้ำแห่งชาติ สถาบันสารสนเทศทรัพยากรน้ำ (สสน.) และสำนักการระบายน้ำ กทม. · การคาดการณ์ใช้ประกอบการตัดสินใจเบื้องต้นเท่านั้น
          </p>
        </>
      )}
    </div>
  );
}
