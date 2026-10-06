import ThemeToggle from './ThemeToggle.jsx';

// Left navigation, grouped by what the page is for. `hint` is the one-liner shown as the
// tooltip; the label is also the page's title in its header and the mobile top bar.
export const NAV_GROUPS = [
  {
    label: 'ภาพรวม',
    items: [
      { id: 'dashboard', label: 'ภาพรวมจราจร', hint: 'รถติดตรงไหน มีเหตุอะไรบนถนน และควรเลี่ยงทางไหน' },
      { id: 'map', label: 'แผนที่จราจร', hint: 'แผนที่รถติด กล้อง น้ำท่วม และจุดอันตราย' },
    ],
  },
  {
    label: 'กล้อง',
    items: [
      { id: 'yolo', label: 'กล้อง AI', hint: 'AI นับรถจากกล้อง ค้นหากล้อง และตรวจคนไม่สวมหมวกกันน็อกหรือขับย้อนศร' },
      { id: 'cameras', label: 'ดูกล้องสด', hint: 'เลือกกล้องมาดูภาพสดพร้อมกันได้ 9 กล้อง' },
    ],
  },
  {
    label: 'เฝ้าระวังเมือง',
    items: [
      { id: 'water', label: 'น้ำท่วม', hint: 'ระดับน้ำ น้ำเหนือ ถนนที่น้ำท่วม จุดพักพิง และ AI สรุปสถานการณ์' },
      { id: 'safety', label: 'อุบัติเหตุ', hint: 'จุดที่เกิดอุบัติเหตุบ่อย และจุดเสี่ยงในกรุงเทพฯ' },
      { id: 'alerts', label: 'แจ้งเตือน', hint: 'ประกาศเตือนภัย และตั้งให้เว็บเตือนเมื่อมีเหตุ' },
      { id: 'enviro', label: 'แผ่นดินไหว', hint: 'เฝ้าระวังและเตือนภัยแผ่นดินไหว' },
    ],
  },
  {
    label: 'เครื่องมือ',
    items: [
      { id: 'ai', label: 'ถาม AI', hint: 'ถาม AI เรื่องรถติด น้ำท่วม หรือเรื่องทั่วไป' },
      { id: 'report', label: 'แจ้งน้ำท่วม', hint: 'แจ้งน้ำท่วมกับ BKK StreetSmart แนบรูป รายละเอียด และปักหมุดตำแหน่ง' },
      { id: 'visitors', label: 'สถิติผู้ใช้', hint: 'มีคนใช้เว็บกี่คน และดูหน้าไหนมากที่สุด' },
    ],
  },
];

export const PAGE_TITLES = Object.fromEntries(NAV_GROUPS.flatMap((g) => g.items).map((i) => [i.id, i.label]));

// Menu drawn as a river: one wavy teal stream runs down the left (.river-rail in index.css), every page is a
// pier on it, and each group is a quiet heading beside a small buoy. The page you are on is the orange pier
// with "อยู่ที่นี่". Pills sit to the right of the stream so hover and the current page never cut the river.
// Colours come from the river tokens in index.css, so it follows light / dark.
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
            <div key={group.label} className="relative pt-3">
              {/* the river, running on to the next group's buoy */}
              <span aria-hidden="true" className={`river-rail absolute left-[13px] top-6 w-2 ${last ? 'bottom-5' : '-bottom-6'}`} />
              <p className="relative flex items-center gap-2.5 min-h-8">
                <span className="w-[34px] shrink-0 grid place-items-center" aria-hidden="true">
                  <span className="w-2.5 h-2.5 rounded-full bg-[var(--c-primary)] ring-4 ring-[var(--c-surface)]" />
                </span>
                <span className="font-display text-[13px] font-semibold tracking-wide text-[var(--c-muted)]">{group.label}</span>
              </p>
              <ul className="flex flex-col gap-0.5 pt-0.5">
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
                        className="group relative cursor-pointer w-full text-left min-h-11 flex items-center text-[15px] rounded-full"
                      >
                        <span className="w-[34px] shrink-0 grid place-items-center" aria-hidden="true">
                          {on ? (
                            <span className="w-4 h-4 rounded-full bg-[var(--c-here)] border-[3px] border-[var(--c-surface)] ring-4 ring-[var(--c-here-tint)]" />
                          ) : (
                            <span className="w-3 h-3 rounded-full bg-[var(--c-surface)] border-2 border-[var(--c-wave)] transition-colors duration-150 group-hover:border-[var(--c-primary)]" />
                          )}
                        </span>
                        <span
                          className={`ml-1 flex-1 min-w-0 min-h-10 px-3 rounded-full flex items-center gap-2 transition-colors duration-150 ${
                            on ? 'bg-[var(--c-here-tint)] font-bold' : 'font-medium group-hover:bg-[var(--c-raised)]'
                          }`}
                        >
                          <span className="truncate flex-1">{item.label}</span>
                          {on && <span className="shrink-0 text-xs font-semibold text-[var(--c-here-text)]">อยู่ที่นี่</span>}
                          {!on && badge && (
                            <span className="shrink-0 text-[11px] px-2 py-0.5 rounded-full tabular-nums bg-[var(--c-primary-tint)] text-[var(--c-primary)]">{badge}</span>
                          )}
                        </span>
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
