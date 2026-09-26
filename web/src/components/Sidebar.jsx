import NavIcon from './NavIcons.jsx';

// Left navigation on a navy panel, grouped by what the page is for. `hint` is the Thai one-liner
// shown as the tooltip; the label is also the page's title in its header and the mobile top bar.
export const NAV_GROUPS = [
  {
    label: 'Overview',
    items: [
      { id: 'dashboard', label: 'Traffic Dashboard', hint: 'ภาพรวมจราจร เหตุการณ์สด และคำแนะนำการระบายรถ' },
      { id: 'map', label: 'Traffic Map', hint: 'แผนที่เส้นจราจรสด กล้อง น้ำท่วม และจุดเสี่ยง' },
    ],
  },
  {
    label: 'Cameras & AI',
    items: [
      { id: 'yolo', label: 'Camera AI & Analysis', hint: 'AI ตรวจจับรถสด นับรถกล้อง กทม. ตรวจหมวกกันน็อกและรถย้อนศร' },
      { id: 'cameras', label: 'My Cameras', hint: 'เลือกกล้อง CCTV มาดูภาพสดพร้อมกันได้ 9 กล้อง' },
    ],
  },
  {
    label: 'City Watch',
    items: [
      { id: 'water', label: 'Water Forecast', hint: 'ระดับน้ำ เฝ้าระวังน้ำท่วม การแจ้งน้ำท่วม และ AI คาดการณ์' },
      { id: 'safety', label: 'Accidents & Risk', hint: 'อุบัติเหตุ มาตรการรายจุด และจุดเสี่ยง กทม.' },
      { id: 'alerts', label: 'Alerts', hint: 'ตั้งค่าการแจ้งเตือนและประกาศเตือนภัย' },
    ],
  },
  {
    label: 'Tools',
    items: [
      { id: 'ai', label: 'Ask AI', hint: 'ถาม AI เรื่องจราจร น้ำท่วม หรือเรื่องทั่วไป' },
      { id: 'visitors', label: 'Visitors', hint: 'สถิติผู้เข้าใช้งานเว็บ' },
    ],
  },
];

export const PAGE_TITLES = Object.fromEntries(NAV_GROUPS.flatMap((g) => g.items).map((i) => [i.id, i.label]));

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

export default function Sidebar({ page, onNavigate, aiActive, liveCount = 0, onClose }) {
  const badges = {
    ai: aiActive ? 'ทำงาน' : null,
    cameras: liveCount ? `${liveCount}` : null,
  };
  return (
    <div className={`h-full flex flex-col ${NAVY} text-[#e6edf7]`}>
      <div className="px-4 pt-5 pb-3 flex items-center gap-3">
        <LogoMark />
        <div className="min-w-0 flex-1">
          <p className="text-[15px] font-semibold text-white tracking-tight leading-tight">BKK StreetSmart</p>
          <p className="text-[10.5px] text-[#9fb2cc] leading-tight">Bangkok Traffic Analytics</p>
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label="ปิดเมนู"
            className={`cursor-pointer shrink-0 w-9 h-9 rounded-md grid place-items-center text-[#cfe0f5] hover:bg-white/10 ${FOCUS_NAVY}`}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" className="w-5 h-5" aria-hidden="true">
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        )}
      </div>

      <nav aria-label="หน้าหลัก" className="flex-1 overflow-y-auto px-3 pb-4">
        {NAV_GROUPS.map((group) => (
          <div key={group.label} className="mt-3 first:mt-1">
            <p className="px-3 pb-1 text-[10.5px] font-medium uppercase tracking-wider text-[#7f95b3]">{group.label}</p>
            <ul className="flex flex-col gap-0.5">
              {group.items.map((item) => {
                const on = page === item.id;
                const badge = badges[item.id];
                return (
                  <li key={item.id}>
                    <button
                      type="button"
                      title={item.hint}
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
                      {badge && (
                        <span className={`ml-auto shrink-0 text-[10px] px-1.5 py-0.5 rounded tabular-nums ${on ? 'bg-[#0f1f3d]/10 text-[#0f1f3d]' : 'bg-white/10 text-[#cfe0f5]'}`}>{badge}</span>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>
    </div>
  );
}
