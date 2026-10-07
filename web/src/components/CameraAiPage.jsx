import { useEffect } from 'react';
import { PageHeader, SubPage } from './dashboard/primitives.jsx';
import { trackView } from '../lib/telemetry.js';
import { PAGE_TITLES } from './Sidebar.jsx';
import ViewSwitch from './ViewSwitch.jsx';
import YoloPage from './YoloPage.jsx';
import BmaCountPage from './BmaCountPage.jsx';
import HelmetPage from './HelmetPage.jsx';
import WrongWayPage from './WrongWayPage.jsx';
import CameraSearchPage from './CameraSearchPage.jsx';

const TABS = [
  { id: 'live', label: 'AI นับรถสด', hint: 'เลือกกล้อง 1 ตัว แล้วดู AI นับรถจากภาพสด', icon: 'yolo' },
  { id: 'search', label: 'ค้นหากล้อง', hint: 'ค้นหากล้องจากชื่อแยก ถนน หรือเขต', icon: 'search' },
  { id: 'bma', label: 'นับรถทุกกล้อง กทม.', hint: 'จำนวนรถจากกล้อง กทม. ทุกตัว และย้อนหลัง', icon: 'bma-count' },
  { id: 'helmet', label: 'คนไม่สวมหมวกกันน็อก', hint: 'AI หาคนขี่มอเตอร์ไซค์ที่ไม่สวมหมวกจากกล้อง กทม.', icon: 'helmet' },
  { id: 'wrongway', label: 'รถขับย้อนศร', hint: 'AI หารถที่ขับสวนทางจากกล้อง กทม.', icon: 'wrongway' },
];

// Live YOLO view of one camera, a search over every camera, the city-wide BMA snapshot counts and the
// helmet / wrong-way patrols, one page with five tabs. Only the open tab is mounted, so the live stream stops while
// another tab is shown.
export default function CameraAiPage({ tab, onTab, cameras, favorites, camid, incidents, onPickCamera, onToast, onAsk }) {
  useEffect(() => trackView(`yolo:${tab}`), [tab]);   // which of the five tabs people use
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={PAGE_TITLES.yolo} description="ให้ AI ช่วยดูกล้อง: นับรถ ค้นหากล้อง และหาคนไม่สวมหมวกกันน็อกหรือขับย้อนศร" />
      <ViewSwitch tabs={TABS} value={tab} onChange={onTab} label="มุมมองกล้อง" />
      <SubPage>
        {tab === 'live' && <YoloPage active cameras={cameras} favorites={favorites} camid={camid} incidents={incidents} onPickCamera={onPickCamera} onToast={onToast} onAsk={onAsk} />}
        {tab === 'search' && (
          <CameraSearchPage
            isActive
            cameras={cameras}
            favorites={favorites}
            onWatchLive={(id) => {
              onPickCamera(id);
              onTab('live');
            }}
          />
        )}
        {tab === 'bma' && <BmaCountPage isActive onToast={onToast} />}
        {tab === 'helmet' && <HelmetPage isActive onToast={onToast} />}
        {tab === 'wrongway' && <WrongWayPage isActive onToast={onToast} />}
      </SubPage>
    </div>
  );
}
