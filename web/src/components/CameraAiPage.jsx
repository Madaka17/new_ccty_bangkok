import { PageHeader } from './dashboard/primitives.jsx';
import { FOCUS } from './dashboard/ui.jsx';
import NavIcon from './NavIcons.jsx';
import YoloPage from './YoloPage.jsx';
import BmaCountPage from './BmaCountPage.jsx';

const TABS = [
  { id: 'live', label: 'AI ตรวจจับรถสด', hint: 'กล้องเดียว · YOLO11x', icon: 'yolo' },
  { id: 'bma', label: 'นับรถจากกล้อง กทม.', hint: 'ทุกกล้อง · สถิติย้อนหลัง', icon: 'bma-count' },
];

// Segmented switch: each view is a card, the open one lifts out of the tray
function ViewSwitch({ value, onChange }) {
  return (
    <div role="tablist" aria-label="มุมมองกล้อง" className="seg-tray grid grid-cols-2 gap-1.5 p-1.5 rounded-2xl w-full sm:w-fit sm:min-w-[520px]">
      {TABS.map((t) => {
        const on = value === t.id;
        return (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={on}
            onClick={() => onChange(t.id)}
            className={`cursor-pointer flex items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-all duration-200 ${FOCUS} ${on ? 'seg-on' : 'seg-off'}`}
          >
            <span className={`shrink-0 grid place-items-center w-9 h-9 rounded-lg transition-colors duration-200 ${on ? 'bg-blue-600 text-white' : 'seg-icon'}`}>
              <NavIcon name={t.icon} className="w-5 h-5" />
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-semibold truncate">{t.label}</span>
              <span className="seg-hint block text-[11.5px] truncate">{t.hint}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}

// Live YOLO view of one camera and the city-wide BMA snapshot counts, one page with two tabs.
// Only the open tab is mounted, so the live stream stops while the counts tab is shown.
export default function CameraAiPage({ tab, onTab, cameras, favorites, camid, incidents, onPickCamera, onToast, onAsk }) {
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title="Camera AI & Analysis" description="ดูรถจากกล้องสดด้วย AI และสถิตินับรถจากกล้อง กทม. ทุกตัว" />
      <ViewSwitch value={tab} onChange={onTab} />
      {tab === 'live' && <YoloPage active cameras={cameras} favorites={favorites} camid={camid} incidents={incidents} onPickCamera={onPickCamera} onToast={onToast} onAsk={onAsk} />}
      {tab === 'bma' && <BmaCountPage isActive onToast={onToast} />}
    </div>
  );
}
