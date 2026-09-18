// Mobile bottom navigation: the four most used pages plus "เมนู" for the rest.
// Desktop keeps the sidebar (hidden lg:block in App.jsx); this bar is lg:hidden.
import NavIcon from './NavIcons.jsx';
import { FOCUS } from './dashboard/ui.jsx';

const ITEMS = [
  { id: 'dashboard', label: 'แดชบอร์ด' },
  { id: 'cameras', label: 'กล้อง' },
  { id: 'yolo', label: 'AI สด' },
  { id: 'map', label: 'แผนที่' },
];

export default function BottomNav({ page, onNavigate, onMenu }) {
  const inBar = ITEMS.some((i) => i.id === page);
  return (
    <nav
      aria-label="เมนูหลัก"
      className="lg:hidden fixed bottom-0 inset-x-0 z-40 bg-white border-t border-slate-200 pb-[env(safe-area-inset-bottom)]"
    >
      <ul className="grid grid-cols-5">
        {ITEMS.map((it) => {
          const on = page === it.id;
          return (
            <li key={it.id}>
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
        })}
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
