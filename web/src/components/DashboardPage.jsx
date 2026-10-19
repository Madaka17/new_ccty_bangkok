import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchTrafficSummary, fetchTrafficAreas, fetchBmaAnalytics, fetchAnalytics, fetchOnlineCount, fetchFloodStatus } from '../lib/api.js';
import { bmaCountsLive, pickTrafficSummary } from '../lib/trafficSummary.js';
import { readMyDistrict } from '../lib/district.js';
import { bmaSiteDown } from './bma/BmaSiteNotice.jsx';
import { trackView } from '../lib/telemetry.js';
import { Button } from './dashboard/ui.jsx';
import { PageHeader, Tabs } from './dashboard/primitives.jsx';
import { fmtDateTime, fmtNum } from './dashboard/format.js';
import { PAGE_TITLES } from './Sidebar.jsx';
import FlowOverview from './dashboard/FlowOverview.jsx';
import IncidentPanel from './dashboard/IncidentPanel.jsx';
import EventsPanel from './dashboard/EventsPanel.jsx';
import DensityPanel from './dashboard/DensityPanel.jsx';
import TrafficGuidanceCard from './dashboard/TrafficGuidanceCard.jsx';
import BestTimeCard from './dashboard/BestTimeCard.jsx';
import CityStatusStrip from './dashboard/CityStatusStrip.jsx';
import RoadRiskPanel from './dashboard/RoadRiskPanel.jsx';
import NewsCard from './dashboard/NewsCard.jsx';
import AvoidRoadsCard from './dashboard/AvoidRoadsCard.jsx';
import BMAEventFeed from './water/BMAEventFeed.jsx';
import EmergencyButton from './EmergencyButton.jsx';

const POLL_MS = 60000;
const MORE_KEY = 'home-details-open';
// Dashboard sections; each tab groups one topic
const SECTIONS = [
  { id: 'overview', label: 'รถติดตอนนี้' },
  { id: 'road-risk', label: 'ถนนแต่ละสาย' },
  { id: 'incidents', label: 'อุบัติเหตุและรถเสีย' },
  { id: 'events', label: 'ปิดถนน งานใหญ่' },
  { id: 'bma-reports', label: 'ข่าวจากศูนย์ กทม.' },
];


export default function DashboardPage({ isActive, liveCount, cameras = [], incidents, onAsk, onAskText, onOpenRoad, onNavigate, onOpenAI, onToast }) {
  // The summary comes from the Longdo road colours; the BMA camera count only stands in until Longdo has data
  const source = 'longdo';
  const [myDistrict] = useState(readMyDistrict);
  const [section, setSection] = useState('overview');
  const [summary, setSummary] = useState(null);
  const [bma, setBma] = useState(null);
  const [areas, setAreas] = useState(null);
  const [roadArea, setRoadArea] = useState(null);   // province / district picked in FlowOverview, for the road cards
  const [density, setDensity] = useState(null);
  const [onlineCount, setOnlineCount] = useState(null);
  const [summaryError, setSummaryError] = useState(false);
  // Road-flood sensor counts (BMA drainage), for the flooded-road figure on the city status strip
  const [flood, setFlood] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  // wide screens show the news card beside the roads at once; phones only once the details are open
  const [isWide, setIsWide] = useState(() => window.matchMedia?.('(min-width: 1024px)').matches ?? true);
  useEffect(() => {
    const mq = window.matchMedia?.('(min-width: 1024px)');
    if (!mq) return;
    const on = (e) => setIsWide(e.matches);
    mq.addEventListener?.('change', on);
    return () => mq.removeEventListener?.('change', on);
  }, []);

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
    const f = fetchTrafficAreas().then(setAreas).catch(() => {});
    return Promise.allSettled([a, b, c, d, e, f]).finally(() => setRefreshing(false));
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
  const site = bma?.scan_status?.source;
  const siteDown = bmaSiteDown(site);
  const countsLive = bmaCountsLive(bma?.scan_status);
  const bmaSummary = bma?.summary
    ? {
        ready: true,
        online: !siteDown && countsLive,
        is_bma: true,
        site,
        // site down: the time of the last picture, not the last (empty) scan
        updated_at: siteDown && site.last_frame_at
          ? site.last_frame_at
          : bma.scan_status?.last_scan_time
            ? Math.floor(new Date(bma.scan_status.last_scan_time.replace(' ', 'T')).getTime() / 1000)
            : Math.floor(Date.now() / 1000),
        flow_index: (siteDown || !countsLive) ? null : Math.min(100, Math.max(1, Math.round((cg?.free_pct || 0) + 0.5 * (cg?.moderate_pct || 0)))),
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

  const activeSummary = pickTrafficSummary(source, bmaSummary, ready);
  // Bangkok's one traffic score: every road with a colour on the map (traffic/areas), the same figure the traffic
  // panel shows for Bangkok. The main-roads summary is used for the roads to avoid and the trend.
  const bkkFlow = areas?.ready ? areas.provinces?.find((p) => p.code === '10')?.flow ?? null : null;
  const incidentCount = (incidents?.camera?.length || 0) + (incidents?.longdo?.length || 0);
  // The most jammed roads, by name only, for the summary sentence ("เลี่ยง ... กับ ...")
  const avoid = activeSummary?.flow_index != null && activeSummary.flow_index < 75
    ? [...new Set((bma?.top_congested || []).map((c) => c.road).filter(Boolean))].slice(0, 2)
    : [];
  // The details (news on phones, the five traffic tabs everywhere) stay folded so home is the answer and the
  // checks; the viewer's last choice is remembered on this device
  const [more, setMore] = useState(() => {
    try { return localStorage.getItem(MORE_KEY) === '1'; } catch { return false; }
  });
  const toggleMore = () => setMore((v) => {
    try { localStorage.setItem(MORE_KEY, v ? '0' : '1'); } catch {}
    return !v;
  });
  // the open tab counts once it is on screen, the first one included
  useEffect(() => { if (more) trackView(`dashboard:${section}`); }, [section, more]);
  const pickSection = setSection;
  // The accident answer on the summary opens the accident tab and brings its list into view with the focus on it.
  // Only after that tap: switching tabs or loading the page never scrolls.
  const incidentsRef = useRef(null);
  const [jump, setJump] = useState(false);
  const openIncidents = () => {
    setMore(true);
    pickSection('incidents');
    setJump(true);
  };
  useEffect(() => {
    if (!jump || section !== 'incidents') return;
    setJump(false);
    const el = incidentsRef.current;
    if (!el) return;
    el.focus({ preventScroll: true });
    const calm = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    el.scrollIntoView({ behavior: calm ? 'auto' : 'smooth', block: 'start' });
  }, [jump, section]);

  return (
    <div className="flex flex-col gap-4">
      {/* wide screens: the page header; phones: the top bar already names the page, so only the time and my
          district sit above the answer. The page refreshes itself every minute. */}
      <div className="hidden md:block">
        <PageHeader
          title={PAGE_TITLES.dashboard}
          description={activeSummary ? `ข้อมูลล่าสุด ${fmtDateTime(activeSummary.updated_at)}` : 'กำลังโหลดข้อมูล...'}
          actions={
            <div className="flex flex-wrap items-center gap-2">
              <DistrictButton district={myDistrict} onNavigate={onNavigate} className="h-9" />
              <Button size="sm" onClick={load} loading={refreshing} className="h-9">
                รีเฟรช
              </Button>
              <span className="inline-flex items-center gap-2 h-9 px-3 rounded-md border border-[var(--c-border)] text-xs text-[var(--c-muted)]" title="จำนวนคนที่เปิดเว็บอยู่ตอนนี้">
                <span aria-hidden="true" className="live-dot w-2 h-2 rounded-full bg-[var(--ok-ring)]" />
                คนดูอยู่ตอนนี้
                <span className="num text-sm font-semibold text-[var(--c-ink)]">{onlineCount != null ? fmtNum(onlineCount) : '–'}</span>
              </span>
            </div>
          }
        />
      </div>
      <div className="md:hidden flex items-center justify-between gap-3">
        <h1 className="sr-only">{PAGE_TITLES.dashboard}</h1>
        <p className="text-xs text-[var(--c-muted)]">{activeSummary ? `ข้อมูลล่าสุด ${fmtDateTime(activeSummary.updated_at)}` : 'กำลังโหลดข้อมูล...'}</p>
        <DistrictButton district={myDistrict} onNavigate={onNavigate} className="min-h-11" />
      </div>

      {summaryError && activeSummary && !activeSummary.is_bma && (
        <p role="status" className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          รีเฟรชล่าสุดไม่สำเร็จ แสดงข้อมูลเมื่อ {fmtDateTime(activeSummary.updated_at)}
        </p>
      )}


      <CityStatusStrip
        summary={activeSummary}
        bkkFlow={bkkFlow}
        trafficAt={bkkFlow != null ? areas?.updated_at : activeSummary?.updated_at}
        incidents={incidents}
        flood={flood}
        avoid={avoid}
        onNavigate={onNavigate}
        onIncidents={openIncidents}
        onAskText={onAskText}
        isActive={isActive}
        emergency={<EmergencyButton inline />}
      />

      {/* roads to avoid on the left, the country's flood and accident news beside them on wide screens. There the two
          cards are one height: the roads card sets it and the news list scrolls inside the news card. On phones the
          news waits in the details. */}
      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] gap-4">
        <AvoidRoadsCard summary={summary} onNavigate={onNavigate} />
        <div className={`relative min-w-0 lg:min-h-[28rem] ${more ? '' : 'hidden lg:block'}`}>
          <NewsCard isActive={isActive && (more || isWide)} />
        </div>
      </div>

      <button
        type="button"
        onClick={toggleMore}
        aria-expanded={more}
        aria-controls="home-details"
        className="cursor-pointer w-full min-h-14 px-4 py-2.5 rounded-lg border border-[var(--c-border)] bg-[var(--c-surface)] flex items-center gap-3 text-left hover:bg-[var(--c-raised)] transition-colors duration-150"
      >
        <span className="flex-1 min-w-0">
          <span className="block text-base font-semibold">{more ? 'ซ่อนรายละเอียด' : 'ดูรายละเอียดเพิ่ม'}</span>
          <span className="block text-sm text-[var(--c-muted)]">
            <span className="lg:hidden">ข่าว · </span>ออกกี่โมงดี · ถนนแต่ละสาย · อุบัติเหตุ{incidentCount ? ` ${incidentCount} จุด` : ''} · ปิดถนน · ข่าวจากศูนย์ กทม.
          </span>
        </span>
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={`w-4 h-4 shrink-0 text-[var(--c-muted)] transition-transform duration-200 ${more ? 'rotate-180' : ''}`} aria-hidden="true">
          <path d="M4 6l4 4 4-4" />
        </svg>
      </button>

      {more && (
        <div id="home-details" className="panel-open flex flex-col gap-4">
        <Tabs
          label="หมวดข้อมูลจราจร"
          value={section}
          onChange={pickSection}
          tabs={SECTIONS.map((t) => (t.id === 'incidents' ? { ...t, badge: incidentCount || undefined } : t))}
        />

        {section === 'overview' && (
          <>
            <BestTimeCard isActive={isActive} />
            <FlowOverview summary={activeSummary} areas={areas} error={summaryError} onRetry={load} retrying={refreshing} onArea={setRoadArea} />
            <TrafficGuidanceCard province={roadArea?.province} amphoe={roadArea?.amphoe} />
          </>
        )}
        {/* The road-colour shares (Longdo lines) sit with the per-road views: on the overview they read as a second,
            different traffic score next to the one above */}
        {section === 'road-risk' && (
          <>
            <DensityPanel d={density} onOpenRoad={onOpenRoad} showShare={false} />
            <RoadRiskPanel isActive={isActive && section === 'road-risk'} onOpenRoad={onOpenRoad} />
          </>
        )}
        {section === 'incidents' && (
          <div ref={incidentsRef} tabIndex={-1} aria-label="รายการอุบัติเหตุและรถเสีย" className="scroll-mt-20 outline-none">
            <IncidentPanel incidents={incidents} onOpenAI={onOpenAI} onNavigate={onNavigate} />
          </div>
        )}
        {section === 'events' && <EventsPanel isActive={isActive && section === 'events'} onNavigate={onNavigate} />}
        {section === 'bma-reports' && <BMAEventFeed isActive={isActive && section === 'bma-reports'} onToast={onToast} />}
        </div>
      )}
    </div>
  );
}

// My district, in the "yours" colour: the one thing on home that belongs to the viewer
function DistrictButton({ district, onNavigate, className = '' }) {
  return (
    <button
      type="button"
      onClick={() => onNavigate?.('district')}
      className={`cursor-pointer shrink-0 inline-flex items-center gap-1.5 px-3 rounded-md border border-[var(--c-border)] bg-[var(--c-yours-tint)] text-sm font-semibold text-[var(--c-yours)] hover:border-[var(--c-yours)] transition-colors duration-150 ${className}`}
    >
      {district ? `เขตของฉัน: ${district}` : 'เลือกเขตของฉัน'}
      <span aria-hidden="true">›</span>
    </button>
  );
}
