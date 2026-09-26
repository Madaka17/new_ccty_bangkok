import { useCallback, useEffect, useState } from 'react';
import { fetchBmaCameras, fetchBmaAnalytics, fetchBmaScanStatus, triggerBmaScan, fetchBmaComparison, fetchBmaDriveDStatus, fetchBmaCycle } from '../lib/api.js';
import { Badge, Button } from './dashboard/ui.jsx';
import { PageHeader, Tabs, StatusBanner } from './dashboard/primitives.jsx';
import { fmtTime } from './dashboard/format.js';
import BmaOverview from './bma/BmaOverview.jsx';
import BmaComparison from './bma/BmaComparison.jsx';
import BmaCameraGrid from './bma/BmaCameraGrid.jsx';

const POLL_MS = 60000;
const TABS = [
  { id: 'overview', label: 'ภาพรวมตอนนี้' },
  { id: 'compare', label: 'เทียบวัน / สัปดาห์ / เดือน' },
  { id: 'cameras', label: 'กล้องทุกตัว' },
];
// Counts vehicles in every BMA traffic camera snapshot (574 cameras, one scan every ~4 min),
// keeps hourly cycles on disk as CSV and compares periods. Three views, one data load.
export default function BmaCountPage({ isActive, onToast }) {
  const [tab, setTab] = useState('overview');
  const [cameras, setCameras] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [scan, setScan] = useState(null);
  const [cycle, setCycle] = useState(null);
  const [period, setPeriod] = useState('day');
  const [comparison, setComparison] = useState(null);
  const [files, setFiles] = useState(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [filters, setFilters] = useState({ query: '', district: 'all', level: 'all', sort: 'total_desc' });

  const load = useCallback(async () => {
    try {
      const [cams, anal, st, cyc] = await Promise.all([fetchBmaCameras(), fetchBmaAnalytics(), fetchBmaScanStatus(), fetchBmaCycle().catch(() => null)]);
      setCameras(cams.items || []);
      setAnalytics(anal);
      setScan(st);
      if (cyc) setCycle(cyc);
    } catch {
      /* keep last data; the header shows when it was last updated */
    } finally {
      setLoading(false);
    }
  }, []);

  const loadComparison = useCallback(async (p) => {
    try {
      const [c, f] = await Promise.all([fetchBmaComparison(p), fetchBmaDriveDStatus()]);
      setComparison(c);
      setFiles(f);
    } catch {
      /* same: keep the last good comparison */
    }
  }, []);

  useEffect(() => {
    if (!isActive) return;
    load();
    loadComparison(period);
    const id = setInterval(() => {
      load();
      if (tab === 'compare') loadComparison(period);
    }, POLL_MS);
    return () => clearInterval(id);
  }, [isActive, load, loadComparison, period, tab]);

  const startScan = async () => {
    setStarting(true);
    try {
      await triggerBmaScan();
      onToast?.('เริ่มสแกนกล้องทั้งหมดแล้ว ใช้เวลาประมาณ 1-2 นาที');
      const poll = setInterval(async () => {
        try {
          const st = await fetchBmaScanStatus();
          setScan(st);
          if (!st.is_scanning) {
            clearInterval(poll);
            setStarting(false);
            load();
          }
        } catch {
          clearInterval(poll);
          setStarting(false);
        }
      }, 2000);
    } catch {
      onToast?.('เริ่มสแกนไม่สำเร็จ');
      setStarting(false);
    }
  };

  const scanning = starting || !!scan?.is_scanning;
  const online = analytics?.summary?.online_cameras ?? cameras.filter((c) => c.status === 'online').length;

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="นับรถจากกล้อง กทม."
        description={
          scan?.last_scan_time
            ? `กล้อง ${cameras.length} ตัว สแกนล่าสุด ${scan.last_scan_time.slice(11, 16)} น. · รอบต่อไปอัตโนมัติทุก 4 นาที · ยอดสะสมรีเซ็ตทุก ${cycle?.cycle_minutes || 60} นาที (ครั้งถัดไป ${cycle ? `${fmtTime(cycle.next_reset)} น.` : '–'})`
            : 'กำลังรอรอบสแกนแรก'
        }
        actions={
          <>
            {online > 0 && (
              <Badge tone="green" dot>
                ออนไลน์ {online} กล้อง
              </Badge>
            )}
            <Button size="sm" variant="primary" onClick={startScan} loading={scanning}>
              {scanning ? `กำลังสแกน ${scan?.current_index || 0}/${scan?.total_cameras || cameras.length}` : 'สแกนตอนนี้'}
            </Button>
            <a href="/api/bma/export/csv" download className="inline-flex items-center h-8 px-3 rounded-lg border border-slate-300 bg-white text-xs font-medium text-slate-800 hover:bg-slate-50">
              ดาวน์โหลด CSV
            </a>
          </>
        }
      />

      {scan?.last_scan_time && !scanning && online === 0 && cameras.length > 0 && (
        <StatusBanner tone="yellow" label="ต้นทางไม่ส่งภาพ">
          เซิร์ฟเวอร์กล้อง กทม. (cpudapp.bangkok.go.th) ตอบกลับเป็นภาพว่างทุกกล้องในรอบสแกนล่าสุด {scan.last_scan_time.slice(11, 16)} น.
          ตัวนับจึงเป็น 0 ชั่วคราว ระบบยังสแกนซ้ำทุก 4 นาทีและจะกลับมาเองเมื่อต้นทางส่งภาพ · ดูข้อมูลย้อนหลังได้ที่แท็บ "เทียบวัน / สัปดาห์ / เดือน"
        </StatusBanner>
      )}

      <Tabs tabs={TABS} value={tab} onChange={setTab} label="มุมมอง" />

      {tab === 'overview' && (
        <BmaOverview
          analytics={analytics}
          cameras={cameras}
          loading={loading}
          onOpenCamera={(cam) => {
            setFilters({ query: cam.camera_code || cam.title, district: 'all', level: 'all', sort: 'total_desc' });
            setTab('cameras');
          }}
          onFilterDistrict={(d) => {
            setFilters({ query: '', district: d, level: 'all', sort: 'total_desc' });
            setTab('cameras');
          }}
          onFilterRoad={(r) => {
            setFilters({ query: r, district: 'all', level: 'all', sort: 'total_desc' });
            setTab('cameras');
          }}
        />
      )}
      {tab === 'compare' && (
        <BmaComparison
          data={comparison}
          period={period}
          onPeriod={(p) => {
            setPeriod(p);
            loadComparison(p);
          }}
          cycle={cycle}
          files={files}
          loading={!comparison}
        />
      )}
      {tab === 'cameras' && <BmaCameraGrid cameras={cameras} loading={loading} filters={filters} onFilters={setFilters} />}
    </div>
  );
}
