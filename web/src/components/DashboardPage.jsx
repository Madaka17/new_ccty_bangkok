import { useCallback, useEffect, useState } from 'react';
import { CameraIcon, MapPinIcon, SparkleIcon, RefreshIcon } from './Icons.jsx';
import { fetchAIStats, fetchTrafficSummary } from '../lib/api.js';
import { Button } from './dashboard/ui.jsx';
import { fmtDateTime } from './dashboard/format.js';
import FlowOverview from './dashboard/FlowOverview.jsx';
import KpiTiles from './dashboard/KpiTiles.jsx';
import IncidentPanel from './dashboard/IncidentPanel.jsx';
import RoadLists from './dashboard/RoadLists.jsx';
import TrendChart from './dashboard/TrendChart.jsx';
import VehicleCounts from './dashboard/VehicleCounts.jsx';

const POLL_MS = 30000;

export default function DashboardPage({ isActive, liveCount, cameras = [], incidents, onAsk, onOpenRoad, onNavigate, onOpenAI }) {
  const [summary, setSummary] = useState(null);
  const [summaryError, setSummaryError] = useState(false);
  const [ai, setAi] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(() => {
    setRefreshing(true);
    const a = fetchTrafficSummary(5)
      .then((s) => {
        setSummary(s);
        setSummaryError(false);
      })
      .catch(() => setSummaryError(true));
    const b = fetchAIStats().then(setAi).catch(() => setAi(null));
    return Promise.allSettled([a, b]).finally(() => setRefreshing(false));
  }, []);

  useEffect(() => {
    if (!isActive) return;
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [isActive, load]);

  // The server answers {ready:false} until its first Longdo pass finishes; treat that as still loading
  const ready = summary?.ready ? summary : null;

  return (
    <div className="flex flex-col gap-4 max-w-6xl mx-auto w-full">
      {/* Page header */}
      <header className="flex flex-wrap items-end justify-between gap-3 pt-1">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 leading-7">แดชบอร์ดการจราจร</h1>
          <p className="text-[13px] text-slate-600 mt-0.5">
            {ready ? `ข้อมูลล่าสุด ${fmtDateTime(ready.updated_at)} · รีเฟรชอัตโนมัติทุก 30 วินาที` : 'กำลังโหลดข้อมูล'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" onClick={load} loading={refreshing} aria-label="รีเฟรชข้อมูล">
            {!refreshing && <RefreshIcon className="w-3.5 h-3.5" />}
            รีเฟรช
          </Button>
          <Button size="sm" variant="primary" onClick={() => onAsk('')}>
            <SparkleIcon className="w-3.5 h-3.5" />
            ถาม AI
          </Button>
        </div>
      </header>

      {summaryError && ready && (
        <p role="status" className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          รีเฟรชล่าสุดไม่สำเร็จ แสดงข้อมูลเมื่อ {fmtDateTime(ready.updated_at)}
        </p>
      )}

      <KpiTiles summary={ready} ai={ai} liveCount={liveCount} />

      <FlowOverview summary={ready} error={summaryError} onRetry={load} retrying={refreshing} />

      <IncidentPanel incidents={incidents} onOpenAI={onOpenAI} onNavigate={onNavigate} />

      <RoadLists summary={ready} onOpenRoad={onOpenRoad} />

      <TrendChart history={ready?.history} />

      <VehicleCounts cameras={cameras} />

      <nav aria-label="ทางลัด" className="flex flex-wrap items-center justify-center gap-2 py-2">
        <Button onClick={() => onNavigate('map')}>
          <MapPinIcon className="w-4 h-4" />
          แผนที่จราจรสด
        </Button>
        <Button onClick={() => onNavigate('cameras')}>
          <CameraIcon className="w-4 h-4" />
          กล้อง CCTV ทั้งหมด
        </Button>
      </nav>
    </div>
  );
}
