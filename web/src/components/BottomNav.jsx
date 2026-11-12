// Mobile bottom navigation: the three most used pages, "แจ้งน้ำท่วม" in the middle on the one filled square, and
// "เพิ่มเติม" for the rest. Desktop keeps the sidebar (hidden lg:block in App.jsx); this bar is lg:hidden. Console
// look like the sidebar: a 1px seam along the top edge, the page you are on marked by a 2px rule in the action
// colour on that seam.
import NavIcon from './NavIcons.jsx';
import { FOCUS } from './dashboard/ui.jsx';

const ITEMS = [
  { id: 'dashboard', label: 'ภาพรวม' },
  { id: 'map', label: 'แผนที่' },
  { id: 'alerts', label: 'ประกาศเตือน' },
];

function NavButton({ it, page, onNavigate }) {
  const on = page === it.id;
  return (
    <li>
      <button
        type="button"
        onClick={() => onNavigate(it.id)}
        aria-current={on ? 'page' : undefined}
        className={`relative cursor-pointer w-full h-15 flex flex-col items-center justify-center gap-0.5 text-xs whitespace-nowrap transition-colors duration-150 ${FOCUS} ${
          on ? 'text-[var(--c-primary)] font-semibold' : 'text-[var(--c-muted)] font-medium hover:text-[var(--c-ink)]'
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
  return <span aria-hidden="true" className="absolute top-0 inset-x-3 h-0.5 rounded-full bg-[var(--c-primary)]" />;
}

export default function BottomNav({ page, onNavigate, onMenu, onReport }) {
  const inBar = page === 'report' || ITEMS.some((i) => i.id === page);
  return (
    <nav
      aria-label="เมนูหลัก"
      className="lg:hidden fixed bottom-0 inset-x-0 z-40 bg-[var(--c-surface)] border-t border-[var(--c-border)] pb-[env(safe-area-inset-bottom)]"
    >
      <ul className="grid grid-cols-5">
        {ITEMS.slice(0, 2).map((it) => <NavButton key={it.id} it={it} page={page} onNavigate={onNavigate} />)}
        <li>
          <button
            type="button"
            onClick={onReport}
            aria-current={page === 'report' ? 'page' : undefined}
            className={`relative cursor-pointer w-full h-15 flex flex-col items-center justify-center gap-0.5 text-xs whitespace-nowrap font-semibold text-[var(--c-ink)] ${FOCUS}`}
          >
            {page === 'report' && <Station />}
            <span className="w-9 h-7 rounded-md bg-[var(--c-primary-fill)] text-[var(--c-on-primary)] grid place-items-center">
              <NavIcon name="report" className="w-5 h-5" />
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
            className={`relative cursor-pointer w-full h-15 flex flex-col items-center justify-center gap-0.5 text-xs whitespace-nowrap transition-colors duration-150 ${FOCUS} ${
              !inBar ? 'text-[var(--c-primary)] font-semibold' : 'text-[var(--c-muted)] font-medium hover:text-[var(--c-ink)]'
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
