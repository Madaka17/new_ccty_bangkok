// Mobile bottom navigation: the four most used pages, "แจ้งน้ำท่วม" raised in the middle, and "เพิ่มเติม" for the rest.
// Desktop keeps the sidebar (hidden lg:block in App.jsx); this bar is lg:hidden. Same rail look as the sidebar:
// a line along the top edge, the page you are on marked by an orange station sitting on it.
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
        className={`relative cursor-pointer w-full h-15 flex flex-col items-center justify-center gap-0.5 text-xs transition-colors duration-150 ${FOCUS} ${
          on ? 'text-[var(--c-ink)] font-bold' : 'text-[var(--c-muted)] font-medium hover:text-[var(--c-ink)]'
        }`}
      >
        {on && <Station />}
        <NavIcon name={it.id} className="w-6 h-6" />
        {it.label}
      </button>
    </li>
  );
}

function Station() {
  return <span aria-hidden="true" className="absolute -top-[7px] left-1/2 -ml-2 w-4 h-4 rounded-full bg-[var(--c-here)] border-3 border-[var(--c-surface)] ring-2 ring-[var(--c-here)]" />;
}

export default function BottomNav({ page, onNavigate, onMenu, onReport }) {
  const inBar = page === 'report' || ITEMS.some((i) => i.id === page);
  return (
    <nav
      aria-label="เมนูหลัก"
      className="lg:hidden fixed bottom-0 inset-x-0 z-40 bg-[var(--c-surface)] pb-[env(safe-area-inset-bottom)]"
    >
      <span aria-hidden="true" className="absolute inset-x-0 top-0 h-1 bg-[var(--c-line)]" />
      <ul className="grid grid-cols-6">
        {ITEMS.slice(0, 2).map((it) => <NavButton key={it.id} it={it} page={page} onNavigate={onNavigate} />)}
        <li>
          <button
            type="button"
            onClick={onReport}
            aria-current={page === 'report' ? 'page' : undefined}
            className={`cursor-pointer w-full h-15 flex flex-col items-center justify-end pb-1 gap-0.5 text-[11px] whitespace-nowrap font-bold text-cyan-700 dark:text-cyan-300 ${FOCUS}`}
          >
            <span className={`-mt-5 w-12 h-12 rounded-full text-white grid place-items-center shadow-md ring-4 ring-[var(--c-surface)] ${page === 'report' ? 'bg-cyan-800' : 'bg-cyan-700'}`}>
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
            className={`relative cursor-pointer w-full h-15 flex flex-col items-center justify-center gap-0.5 text-xs transition-colors duration-150 ${FOCUS} ${
              !inBar ? 'text-[var(--c-ink)] font-bold' : 'text-[var(--c-muted)] font-medium hover:text-[var(--c-ink)]'
            }`}
          >
            {!inBar && <Station />}
            <NavIcon name="menu" className="w-6 h-6" />
            เพิ่มเติม
          </button>
        </li>
      </ul>
    </nav>
  );
}
