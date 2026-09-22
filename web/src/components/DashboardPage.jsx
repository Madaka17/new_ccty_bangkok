import { useCallback, useEffect, useState } from 'react';
import { fetchTrafficSummary, fetchBmaAnalytics, fetchAnalytics, fetchOnlineCount, fetchFloodStatus } from '../lib/api.js';
import { trackView } from '../lib/telemetry.js';
import { Button, Badge } from './dashboard/ui.jsx';
import { PageHeader, Tabs } from './dashboard/primitives.jsx';
import { fmtDateTime, fmtNum } from './dashboard/format.js';
import FlowOverview from './dashboard/FlowOverview.jsx';
import IncidentPanel from './dashboard/IncidentPanel.jsx';
import DensityPanel from './dashboard/DensityPanel.jsx';
import TrafficGuidanceCard from './dashboard/TrafficGuidanceCard.jsx';
import CityStatusStrip from './dashboard/CityStatusStrip.jsx';
import FloodPanel from './dashboard/FloodPanel.jsx';
import RoadRiskPanel from './dashboard/RoadRiskPanel.jsx';
import BMAEventFeed from './water/BMAEventFeed.jsx';

const POLL_MS = 60000;
// Dashboard sections; each tab groups one topic
const SECTIONS = [
  { id: 'overview', label: 'ภาพรวมจราจร' },
  { id: 'flood', label: 'น้ำท่วมขังถนน' },
  { id: 'road-risk', label: 'วิเคราะห์รายถนน' },
  { id: 'incidents', label: 'เหตุการณ์สด' },
  { id: 'bma-reports', label: 'รายงานสดจากศูนย์' },
];


export default function DashboardPage({ isActive, liveCount, cameras = [], incidents, onAsk, onOpenRoad, onNavigate, onOpenAI, onToast }) {
  const source = 'bma';
  const [section, setSection] = useState('overview');
  const [summary, setSummary] = useState(null);
  const [bma, setBma] = useState(null);
  const [density, setDensity] = useState(null);
  const [onlineCount, setOnlineCount] = useState(null);
  const [summaryError, setSummaryError] = useState(false);
  // Road-flood sensor counts (BMA drainage): badge on the tab + the city status strip
  const [flood, setFlood] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(() => {
    setRefreshing(true);
    const a = fetchTrafficSummary(25)
      .then((s) => {
        setSummary(s);
        setSummaryError(false);
      })
      .catch(() => setSummaryError(true));
    const b = fetchBmaAnalytics().then((d) => setBma(d)).catch(() => {});
    const c = fetchAnalytics().then((d) => {
      setDensity(d.density);
      if (d.visitors?.online != null) setOnlineCount(d.visitors.online);
    }).catch(() => {});
    const d = fetchOnlineCount().then((n) => setOnlineCount(n)).catch(() => {});
    const e = fetchFloodStatus().then((f) => setFlood(f)).catch(() => {});
    return Promise.allSettled([a, b, c, d, e]).finally(() => setRefreshing(false));
  }, []);

  useEffect(() => {
    if (!isActive) return;
    load();
    const id = setInterval(load, POLL_MS);
    const idOnline = setInterval(() => {
      fetchOnlineCount().then(setOnlineCount).catch(() => {});
    }, 60000);
    return () => {
      clearInterval(id);
      clearInterval(idOnline);
    };
  }, [isActive, load]);

  const ready = summary?.ready ? summary : null;

  // BMA unified summary
  const cg = bma?.summary?.congestion;
  const bmaSummary = bma?.summary
    ? {
        ready: true,
        online: true,
        is_bma: true,
        updated_at: bma.scan_status?.last_scan_time
          ? Math.floor(new Date(bma.scan_status.last_scan_time.replace(' ', 'T')).getTime() / 1000)
          : Math.floor(Date.now() / 1000),
        flow_index: Math.max(1, Math.round((cg?.free_pct || 0) + 0.5 * (cg?.moderate_pct || 0))),
        green_pct: Math.round(cg?.free_pct || 0),
        yellow_pct: Math.round(cg?.moderate_pct || 0),
        red_pct: Math.round(cg?.heavy_pct || 0),
        camera_count: bma.summary.online_cameras || 0,
        total_cameras: bma.summary.total_cameras || 0,
        total_vehicles: bma.summary.total_vehicles || 0,
        avg_per_camera: bma.summary.avg_per_camera || 0,
        free_count: cg?.free_count || 0,
        moderate_count: cg?.moderate_count || 0,
        heavy_count: cg?.heavy_count || 0,
        cars: bma.summary.cars || 0,
        cars_pct: bma.summary.cars_pct || 0,
        motorcycles: bma.summary.motorcycles || 0,
        motorcycles_pct: bma.summary.motorcycles_pct || 0,
        trucks: bma.summary.trucks || 0,
        trucks_pct: bma.summary.trucks_pct || 0,
        congested: (bma.top_congested || []).slice(0, 8).map((c) => ({
          name: `${c.road || c.title} (${c.district || 'กทม.'})`,
          level: 'หนาแน่น',
          is_bma: true,
          total: c.total,
          cars: c.cars,
          motorcycles: c.motorcycles,
          trucks: c.trucks,
          green_pct: 0,
          yellow_pct: 10,
          red_pct: 90,
          flow: 10,
        })),
        free_flow: (bma.top_free || []).slice(0, 8).map((c) => ({
          name: `${c.road || c.title} (${c.district || 'กทม.'})`,
          level: c.total > 4 ? 'ปานกลาง' : 'คล่องตัว',
          is_bma: true,
          total: c.total,
          cars: c.cars,
          motorcycles: c.motorcycles,
          trucks: c.trucks,
          green_pct: c.total > 4 ? 40 : 100,
          yellow_pct: c.total > 4 ? 60 : 0,
          red_pct: 0,
          flow: c.total > 4 ? 60 : 95,
        })),
        // Hourly totals across all cameras -> a 1-100 "flow" score (fewer queued vehicles = freer)
        history: (bma.hourly_trends || []).map((h, i) => ({
          t: h.hour ? Math.floor(new Date(h.hour).getTime() / 1000) : Math.floor(Date.now() / 1000) - ((bma.hourly_trends.length - 1 - i) * 3600),
          flow: Math.max(1, Math.min(100, Math.round(100 - ((h.total ?? h.vehicles ?? 0) / Math.max(1, h.cam_count || 574)) * 8))),
          red_pct: 85,
          hourly: true,
        })),
      }
    : null;

  const activeSummary = source === 'bma' ? (bmaSummary || ready) : (ready || bmaSummary);
  const incidentCount = (incidents?.camera?.length || 0) + (incidents?.longdo?.length || 0);
  const floodCount = (flood?.counts?.flood || 0) + (flood?.counts?.slight || 0);

  return (
    <div className="flex flex-col gap-4 max-w-6xl mx-auto w-full">
      <PageHeader
        title={source === 'bma' ? 'แดชบอร์ดสภาพจราจร' : 'แดชบอร์ดสภาพจราจร Longdo'}
        description={
          activeSummary
            ? `ข้อมูลล่าสุด ${fmtDateTime(activeSummary.updated_at)}`
            : 'กำลังโหลดข้อมูล...'
        }
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" onClick={load} loading={refreshing}>
              รีเฟรช
            </Button>
            <div
              className="inline-flex items-center gap-2 h-8 px-3 rounded-lg border border-cream-200 bg-white text-xs shadow-xs"
              title="ผู้ใช้ออนไลน์ตอนนี้ (heartbeat ภายใน 90 วินาที)"
            >
              <span className="flex items-center gap-1.5 font-medium text-ink-900">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                </span>
                ผู้ใช้ออนไลน์
              </span>
              <span className="font-semibold text-emerald-600 dark:text-emerald-400 text-sm tabular-nums">
                {onlineCount != null ? fmtNum(onlineCount) : '–'}
              </span>
              <span className="text-[11px] text-ink-600">คน</span>
              <Badge tone="green" dot>Real-time</Badge>
            </div>
          </div>
        }
      />

      {summaryError && activeSummary && !activeSummary.is_bma && (
        <p role="status" className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          รีเฟรชล่าสุดไม่สำเร็จ แสดงข้อมูลเมื่อ {fmtDateTime(activeSummary.updated_at)}
        </p>
      )}


      <CityStatusStrip summary={activeSummary} incidents={incidents} flood={flood} onNavigate={onNavigate} isActive={isActive} />

      <Tabs
        label="หมวดข้อมูลแดชบอร์ด"
        value={section}
        onChange={(id) => {
          setSection(id);
          trackView(`dashboard:${id}`);
        }}
        tabs={SECTIONS.map((t) => (t.id === 'incidents' ? { ...t, badge: incidentCount || undefined }
          : t.id === 'flood' ? { ...t, badge: floodCount || undefined } : t))}
      />

      {section === 'overview' && (
        <>
          <FlowOverview summary={activeSummary} error={summaryError} onRetry={load} retrying={refreshing} />
          <DensityPanel d={density} onOpenRoad={onOpenRoad} showShare={false} />
          <TrafficGuidanceCard onOpenRoad={onOpenRoad} onAsk={onAsk} />
        </>
      )}
      {section === 'flood' && <FloodPanel isActive={isActive && section === 'flood'} onNavigate={onNavigate} />}
      {section === 'road-risk' && <RoadRiskPanel isActive={isActive && section === 'road-risk'} onOpenRoad={onOpenRoad} />}
      {section === 'incidents' && <IncidentPanel incidents={incidents} onOpenAI={onOpenAI} onNavigate={onNavigate} />}
      {section === 'bma-reports' && <BMAEventFeed isActive={isActive && section === 'bma-reports'} onToast={onToast} />}
    </div>
  );
}

