import ThemeToggle from './ThemeToggle.jsx';

// Left navigation, grouped by what the page is for. `hint` is the one-liner shown as the
// tooltip; the label is also the page's title in its header and the mobile top bar.
// `line` is the group's colour on the menu's rail map (--line-* in index.css).
export const NAV_GROUPS = [
  {
    label: 'ภาพรวม',
    line: 'var(--line-1)',
    items: [
      { id: 'dashboard', label: 'ภาพรวมจราจร', hint: 'รถติดตรงไหน มีเหตุอะไรบนถนน และควรเลี่ยงทางไหน' },
      { id: 'map', label: 'แผนที่จราจร', hint: 'แผนที่รถติด กล้อง น้ำท่วม และจุดอันตราย' },
    ],
  },
  {
    label: 'กล้อง',
    line: 'var(--line-2)',
    items: [
      { id: 'yolo', label: 'กล้อง AI', hint: 'AI นับรถจากกล้อง ค้นหากล้อง และตรวจคนไม่สวมหมวกกันน็อกหรือขับย้อนศร' },
      { id: 'cameras', label: 'ดูกล้องสด', hint: 'เลือกกล้องมาดูภาพสดพร้อมกันได้ 9 กล้อง' },
    ],
  },
  {
    label: 'เฝ้าระวังเมือง',
    line: 'var(--line-3)',
    items: [
      { id: 'water', label: 'น้ำท่วม', hint: 'ระดับน้ำ น้ำเหนือ ถนนที่น้ำท่วม จุดพักพิง และ AI สรุปสถานการณ์' },
      { id: 'safety', label: 'อุบัติเหตุ', hint: 'จุดที่เกิดอุบัติเหตุบ่อย และจุดเสี่ยงในกรุงเทพฯ' },
      { id: 'alerts', label: 'แจ้งเตือน', hint: 'ประกาศเตือนภัย และตั้งให้เว็บเตือนเมื่อมีเหตุ' },
      { id: 'enviro', label: 'แผ่นดินไหว', hint: 'เฝ้าระวังและเตือนภัยแผ่นดินไหว' },
    ],
  },
  {
    label: 'เครื่องมือ',
    line: 'var(--line-4)',
    items: [
      { id: 'ai', label: 'ถาม AI', hint: 'ถาม AI เรื่องรถติด น้ำท่วม หรือเรื่องทั่วไป' },
      { id: 'report', label: 'แจ้งน้ำท่วม', hint: 'แจ้งน้ำท่วมถึงเขต ผ่าน Traffy Fondue และดูเรื่องที่คนแจ้งใน 6 ชม.' },
      { id: 'visitors', label: 'สถิติผู้ใช้', hint: 'มีคนใช้เว็บกี่คน และดูหน้าไหนมากที่สุด' },
    ],
  },
];

export const PAGE_TITLES = Object.fromEntries(NAV_GROUPS.flatMap((g) => g.items).map((i) => [i.id, i.label]));

// Menu drawn as a rail map: each group is a line in its own colour with its name on a sign, every page is a
// station on it, and the lines meet at square interchanges. The page you are on is the big orange station
// with "อยู่ที่นี่". Colours come from the city tokens in index.css, so it follows light / dark.
function LogoMark() {
  // Small skyline mark, matches the icon stroke style used in the menu.
  return (
    <svg viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="w-9 h-9 text-[var(--c-line)]" aria-hidden="true">
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
    ai: aiActive ? 'พร้อม' : null,
    cameras: liveCount ? `${liveCount}` : null,
  };
  return (
    <div className="h-full flex flex-col bg-[var(--c-surface)] text-[var(--c-ink)] border-r border-[var(--c-border)]">
      <div className="px-4 pt-5 pb-3 flex items-center gap-3">
        <LogoMark />
        <div className="min-w-0 flex-1">
          <p className="font-display text-[17px] font-bold tracking-tight leading-tight">BKK StreetSmart</p>
          <p className="text-xs text-[var(--c-muted)] leading-tight">จราจรและน้ำท่วม</p>
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label="ปิดเมนู"
            className="cursor-pointer shrink-0 w-11 h-11 rounded-md grid place-items-center hover:bg-[var(--c-raised)]"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" className="w-5 h-5" aria-hidden="true">
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        )}
      </div>

      <nav aria-label="หน้าหลัก" className="flex-1 overflow-y-auto px-3 pb-4 scroll-soft">
        {NAV_GROUPS.map((group, gi) => {
          const last = gi === NAV_GROUPS.length - 1;
          return (
            <div key={group.label} className="relative pt-3" style={{ '--g': group.line }}>
              {/* this group's line, running on to the next group's interchange */}
              <span aria-hidden="true" className={`absolute left-[15px] top-6 w-1 bg-[var(--g)] ${last ? 'bottom-5' : '-bottom-6'}`} />
              <p className="relative flex items-center gap-2.5 min-h-8">
                <span className="w-[34px] shrink-0 grid place-items-center" aria-hidden="true">
                  <span className="w-4 h-4 rounded-[3px] bg-[var(--g)] ring-3 ring-[var(--c-surface)]" />
                </span>
                <span className="font-display rounded-[3px] bg-[var(--g)] px-2 py-0.5 text-sm font-bold text-[var(--c-surface)]">{group.label}</span>
              </p>
              <ul className="flex flex-col pt-0.5">
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
                        className={`relative cursor-pointer w-full text-left min-h-11 pr-3 rounded-r-md flex items-center gap-2.5 text-[15px] transition-colors duration-150 ${
                          on ? 'bg-[var(--c-here-tint)] font-bold' : 'font-medium text-[var(--c-ink)] hover:bg-[var(--c-raised)]'
                        }`}
                      >
                        <span className="w-[34px] shrink-0 grid place-items-center" aria-hidden="true">
                          {on ? (
                            <span className="w-5 h-5 rounded-full bg-[var(--c-here)] border-4 border-[var(--c-surface)] ring-3 ring-[var(--c-here)]" />
                          ) : (
                            <span className="w-3.5 h-3.5 rounded-full bg-[var(--c-surface)] border-3 border-[var(--g)]" />
                          )}
                        </span>
                        <span className="truncate flex-1">{item.label}</span>
                        {on && <span className="shrink-0 text-xs font-semibold text-[var(--c-here-text)]">อยู่ที่นี่</span>}
                        {!on && badge && (
                          <span className="shrink-0 text-[11px] px-1.5 py-0.5 rounded-[3px] tabular-nums bg-[var(--c-raised)] text-[var(--c-muted)]">{badge}</span>
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </nav>

      <div className="px-3 py-3 border-t border-[var(--c-border)]">
        <ThemeToggle withLabel />
      </div>
    </div>
  );
}
