import NavIcon from './NavIcons.jsx';

// Left navigation: one flat list on a navy panel (no group headers), like a classic
// analytics console. Order = how often each page is opened.
export const NAV_ITEMS = [
  { id: 'dashboard', label: 'แดชบอร์ดจราจร' },
  { id: 'analytics', label: 'สรุปข้อมูลเมือง' },
  { id: 'map', label: 'แผนที่จราจร' },
  { id: 'cameras', label: 'กล้องของฉัน' },
  { id: 'bma-count', label: 'นับรถจากกล้อง กทม.' },
  { id: 'yolo', label: 'AI ตรวจจับรถสด' },
  { id: 'water', label: 'คาดการณ์น้ำ' },
  { id: 'ai', label: 'ถาม AI เรื่องเส้นทาง' },
];

export const PAGE_TITLES = Object.fromEntries(NAV_ITEMS.map((i) => [i.id, i.label]));

const THEMES = [
  ['light', 'สว่าง'],
  ['dark', 'มืด'],
  ['system', 'ตามเครื่อง'],
];

// Sidebar colours are fixed hex values on purpose: the .dark remaps in index.css
// (bg-white, text-slate-*) must not touch this panel — it is always navy.
const NAVY = 'bg-[#0f1f3d]';
const FOCUS_NAVY = 'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#9ec1ec] focus-visible:ring-offset-2 focus-visible:ring-offset-[#0f1f3d]';

function LogoMark() {
  // Small skyline mark, matches the icon stroke style used in the menu.
  return (
    <svg viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="w-9 h-9 text-[#cfe0f5]" aria-hidden="true">
      <path d="M3 27h26" />
      <path d="M6 27V13l4-3 4 3v14" />
      <path d="M14 27V8l5-4 5 4v19" />
      <path d="M24 27V16l3 2v9" />
      <path d="M9 17h1M9 21h1M17 11h1M17 15h1M17 19h1M17 23h1" />
    </svg>
  );
}

export default function Sidebar({ page, onNavigate, liveCount, totalCount, aiActive, theme, onTheme, onClose }) {
  return (
    <div className={`h-full flex flex-col ${NAVY} text-[#e6edf7]`}>
      <div className="px-4 pt-5 pb-4 flex items-center gap-3">
        <LogoMark />
        <div className="min-w-0">
          <p className="text-[15px] font-semibold text-white tracking-tight leading-tight">BKK StreetSmart</p>
          <p className="text-[10.5px] text-[#9fb2cc] leading-tight">Bangkok Traffic Analytics</p>
        </div>
      </div>

      <nav aria-label="หน้าหลัก" className="flex-1 overflow-y-auto px-3 py-2">
        <ul className="flex flex-col gap-1">
          {NAV_ITEMS.map((item) => {
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
                  className={`cursor-pointer w-full text-left rounded-md px-3 py-2 text-[13px] flex items-center gap-3 transition-colors duration-150 ${FOCUS_NAVY} ${
                    on ? 'bg-[#dbe6f5] text-[#0f1f3d] font-medium' : 'text-[#d3ddeb] hover:bg-white/8 hover:text-white'
                  }`}
                >
                  <NavIcon name={item.id} className={`w-4 h-4 shrink-0 ${on ? 'text-[#0f1f3d]' : 'text-[#9fb2cc]'}`} />
                  <span className="truncate">{item.label}</span>
                  {item.id === 'ai' && aiActive && (
                    <span className={`ml-auto text-[10px] px-1.5 py-0.5 rounded ${on ? 'bg-[#0f1f3d]/10 text-[#0f1f3d]' : 'bg-white/10 text-[#cfe0f5]'}`}>ทำงาน</span>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="px-4 py-4 border-t border-white/10 flex flex-col gap-3">
        <p className="text-[11.5px] text-[#b7c6dc]">
          <span className="live-dot inline-block w-1.5 h-1.5 rounded-full bg-emerald-400 mr-1.5 align-middle" aria-hidden="true" />
          {liveCount > 0 ? `เปิดกล้องอยู่ ${liveCount} ตัว` : `กล้องพร้อมใช้ ${totalCount} ตัว`}
        </p>
        <div>
          <p className="text-[10.5px] text-[#9fb2cc] mb-1">ธีม</p>
          <div role="tablist" aria-label="ธีม" className="inline-flex rounded-md bg-white/8 p-0.5">
            {THEMES.map(([k, text]) => {
              const on = theme === k;
              return (
                <button
                  key={k}
                  type="button"
                  role="tab"
                  aria-selected={on}
                  onClick={() => onTheme(k)}
                  className={`cursor-pointer rounded px-2.5 h-6 text-[11px] font-medium transition-colors duration-150 ${FOCUS_NAVY} ${
                    on ? 'bg-[#dbe6f5] text-[#0f1f3d]' : 'text-[#b7c6dc] hover:text-white'
                  }`}
                >
                  {text}
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
