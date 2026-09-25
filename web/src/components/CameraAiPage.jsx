import { PageHeader } from './dashboard/primitives.jsx';
import ViewSwitch from './ViewSwitch.jsx';
import YoloPage from './YoloPage.jsx';
import BmaCountPage from './BmaCountPage.jsx';
import HelmetPage from './HelmetPage.jsx';
import WrongWayPage from './WrongWayPage.jsx';

const TABS = [
  { id: 'live', label: 'AI ตรวจจับรถสด', hint: 'กล้องเดียว · YOLO11x', icon: 'yolo' },
  { id: 'bma', label: 'นับรถจากกล้อง กทม.', hint: 'ทุกกล้อง · สถิติย้อนหลัง', icon: 'bma-count' },
  { id: 'helmet', label: 'Helmet Check', hint: 'ตรวจหมวกกันน็อก · กล้อง กทม.', icon: 'helmet' },
  { id: 'wrongway', label: 'Wrong-Way Check', hint: 'ตรวจรถย้อนศร · กล้อง กทม.', icon: 'wrongway' },
];

// Live YOLO view of one camera, the city-wide BMA snapshot counts and the helmet / wrong-way
// patrols, one page with four tabs. Only the open tab is mounted, so the live stream stops while
// another tab is shown.
export default function CameraAiPage({ tab, onTab, cameras, favorites, camid, incidents, onPickCamera, onToast, onAsk }) {
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title="Camera AI & Analysis" description="ดูรถจากกล้องสดด้วย AI สถิตินับรถจากกล้อง กทม. ทุกตัว และตรวจหมวกกันน็อก/รถย้อนศร" />
      <ViewSwitch tabs={TABS} value={tab} onChange={onTab} label="มุมมองกล้อง" />
      {tab === 'live' && <YoloPage active cameras={cameras} favorites={favorites} camid={camid} incidents={incidents} onPickCamera={onPickCamera} onToast={onToast} onAsk={onAsk} />}
      {tab === 'bma' && <BmaCountPage isActive onToast={onToast} />}
      {tab === 'helmet' && <HelmetPage isActive onToast={onToast} />}
      {tab === 'wrongway' && <WrongWayPage isActive onToast={onToast} />}
    </div>
  );
}
