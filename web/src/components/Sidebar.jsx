import { Segmented, FOCUS } from './dashboard/ui.jsx';
import NavIcon from './NavIcons.jsx';

// Left navigation. Groups are plain text on purpose: the page names carry the meaning.
export const NAV_GROUPS = [
  {
    title: 'ภาพรวม',
    items: [
      { id: 'dashboard', label: 'แดชบอร์ดจราจร' },
      { id: 'analytics', label: 'สรุปข้อมูลเมือง' },
    ],
  },
  {
    title: 'กล้อง',
    items: [
      { id: 'cameras', label: 'กล้องของฉัน' },
      { id: 'bma-count', label: 'นับรถจากกล้อง กทม.' },
      { id: 'yolo', label: 'AI ตรวจจับรถสด' },
    ],
  },
  {
    title: 'แผนที่และน้ำ',
    items: [
      { id: 'map', label: 'แผนที่จราจร' },
      { id: 'water', label: 'คาดการณ์น้ำ' },
    ],
  },
  { title: 'ผู้ช่วย', items: [{ id: 'ai', label: 'ถาม AI เรื่องเส้นทาง' }] },
];

export const PAGE_TITLES = Object.fromEntries(NAV_GROUPS.flatMap((g) => g.items.map((i) => [i.id, i.label])));

const THEMES = [
  ['light', 'สว่าง'],
  ['dark', 'มืด'],
  ['system', 'ตามเครื่อง'],
];

export default function Sidebar({ page, onNavigate, liveCount, totalCount, aiActive, theme, onTheme, onClose }) {
  return (
    <div className="h-full flex flex-col bg-white border-r border-slate-200">
      <div className="px-5 pt-5 pb-4 border-b border-slate-200">
        <p className="text-lg font-semibold text-slate-900 tracking-tight">BKK StreetSmart</p>
        <p className="text-xs text-slate-600">Your Street Smart Guide</p>
      </div>

      <nav aria-label="หน้าหลัก" className="flex-1 overflow-y-auto px-3 py-3">
        {NAV_GROUPS.map((g) => (
          <div key={g.title} className="mb-3">
            <p className="px-2 pb-1 text-[11px] font-medium uppercase tracking-wide text-slate-500">{g.title}</p>
            <ul className="flex flex-col gap-0.5">
              {g.items.map((item) => {
                const on = page === item.id;
                return (
                  <li key={item.id}>
                    <button
                      type="button"
                      onClick={() => {
                        onNavigate(item.id);
                        onClose?.();
                      }}
                      aria-current={on ? 'page' : undefined}
                      className={`cursor-pointer w-full text-left rounded-lg px-3 py-2 text-sm flex items-center gap-2.5 transition-colors duration-150 ${FOCUS} ${
                        on ? 'bg-blue-50 text-blue-800 font-medium' : 'text-slate-700 hover:bg-slate-100 hover:text-slate-900'
                      }`}
                    >
                      <NavIcon name={item.id} className={`w-[18px] h-[18px] shrink-0 ${on ? 'text-blue-700' : 'text-slate-400'}`} />
                      {item.label}
                      {item.id === 'ai' && aiActive && <span className="ml-2 text-xs text-blue-700">ทำงานอยู่</span>}
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className="px-5 py-4 border-t border-slate-200 flex flex-col gap-3">
        <p className="text-xs text-slate-600">
          <span className="live-dot inline-block w-1.5 h-1.5 rounded-full bg-emerald-600 mr-1.5 align-middle" aria-hidden="true" />
          {liveCount > 0 ? `เปิดกล้องอยู่ ${liveCount} ตัว` : `กล้องพร้อมใช้ ${totalCount} ตัว`}
        </p>
        <div>
          <p className="text-[11px] text-slate-500 mb-1">ธีม</p>
          <Segmented label="ธีม" value={theme} onChange={onTheme} options={THEMES} />
        </div>
      </div>
    </div>
  );
}
