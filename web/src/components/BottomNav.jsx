// Mobile bottom navigation: the four most used pages, "แจ้งน้ำท่วม" raised in the middle, and "เพิ่มเติม" for the rest.
// Desktop keeps the sidebar (hidden lg:block in App.jsx); this bar is lg:hidden.
import NavIcon from './NavIcons.jsx';
import { FOCUS } from './dashboard/ui.jsx';

const ITEMS = [
  { id: 'dashboard', label: 'แดชบอร์ด' },
  { id: 'map', label: 'แผนที่' },
  { id: 'yolo', label: 'กล้อง AI' },
  { id: 'cameras', label: 'กล้องสด' },
];

function NavButton({ it, page, onNavigate }) {
  const on = page === it.id;
  return (
    <li>
      <button
        type="button"
        onClick={() => onNavigate(it.id)}
        aria-current={on ? 'page' : undefined}
        className={`cursor-pointer w-full h-14 flex flex-col items-center justify-center gap-0.5 text-[11px] font-medium transition-colors duration-150 ${FOCUS} ${
          on ? 'text-blue-700' : 'text-slate-500 hover:text-slate-900'
        }`}
      >
        <span className={`rounded-full px-3 py-0.5 transition-colors duration-150 ${on ? 'bg-blue-50' : ''}`}>
          <NavIcon name={it.id} className="w-5 h-5" />
        </span>
        {it.label}
      </button>
    </li>
  );
}

export default function BottomNav({ page, onNavigate, onMenu, onReport }) {
  const inBar = page === 'report' || ITEMS.some((i) => i.id === page);
  return (
    <nav
      aria-label="เมนูหลัก"
      className="lg:hidden fixed bottom-0 inset-x-0 z-40 bg-white border-t border-slate-200 pb-[env(safe-area-inset-bottom)]"
    >
      <ul className="grid grid-cols-6">
        {ITEMS.slice(0, 2).map((it) => <NavButton key={it.id} it={it} page={page} onNavigate={onNavigate} />)}
        <li>
          <button
            type="button"
            onClick={onReport}
            aria-current={page === 'report' ? 'page' : undefined}
            className={`cursor-pointer w-full h-14 flex flex-col items-center justify-end pb-1 gap-0.5 text-[11px] font-semibold text-cyan-700 ${FOCUS}`}
          >
            <span className={`-mt-5 w-12 h-12 rounded-full text-white grid place-items-center shadow-md ring-4 ring-white ${page === 'report' ? 'bg-cyan-800' : 'bg-cyan-600'}`}>
              <NavIcon name="report" className="w-6 h-6" />
            </span>
            แจ้งน้ำท่วม
          </button>
        </li>
        {ITEMS.slice(2).map((it) => <NavButton key={it.id} it={it} page={page} onNavigate={onNavigate} />)}
        <li>
          <button
            type="button"
            onClick={onMenu}
            aria-haspopup="dialog"
            className={`cursor-pointer w-full h-14 flex flex-col items-center justify-center gap-0.5 text-[11px] font-medium transition-colors duration-150 ${FOCUS} ${
              !inBar ? 'text-blue-700' : 'text-slate-500 hover:text-slate-900'
            }`}
          >
            <span className={`rounded-full px-3 py-0.5 ${!inBar ? 'bg-blue-50' : ''}`}>
              <NavIcon name="menu" className="w-5 h-5" />
            </span>
            เพิ่มเติม
          </button>
        </li>
      </ul>
    </nav>
  );
}
