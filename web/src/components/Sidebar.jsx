import ThemeToggle from './ThemeToggle.jsx';
import NavIcon from './NavIcons.jsx';
import { WeatherBadge, WeatherFxToggle, skyClass } from './fx/WeatherFx.jsx';

// Left navigation, grouped by what the page is for. `hint` is the one-liner shown as the
// tooltip; the label is also the page's title in its header and the mobile top bar.
export const NAV_GROUPS = [
  {
    label: 'ตอนนี้',
    items: [
      { id: 'dashboard', label: 'ภาพรวม', hint: 'รถติดตรงไหน มีเหตุอะไรบนถนน และควรเลี่ยงทางไหน' },
      { id: 'map', label: 'แผนที่', hint: 'แผนที่รถติด กล้อง น้ำท่วม และจุดอันตราย' },
    ],
  },
  {
    label: 'เตือนภัย',
    items: [
      { id: 'alerts', label: 'ประกาศเตือน', hint: 'ประกาศเตือนภัย และตั้งให้เว็บเตือนเมื่อมีเหตุ' },
      { id: 'water', label: 'น้ำท่วม', hint: 'ระดับน้ำ น้ำเหนือ ถนนที่น้ำท่วม จุดพักพิง และ AI สรุปสถานการณ์' },
      { id: 'enviro', label: 'แผ่นดินไหว', hint: 'เฝ้าระวังและเตือนภัยแผ่นดินไหว' },
      { id: 'safety', label: 'จุดเสี่ยงอุบัติเหตุ', hint: 'จุดที่เกิดอุบัติเหตุบ่อย และจุดเสี่ยงในกรุงเทพฯ' },
    ],
  },
  {
    label: 'กล้อง',
    items: [
      { id: 'cameras', label: 'ดูกล้องสด', hint: 'เลือกกล้องมาดูภาพสดพร้อมกันได้ 9 กล้อง' },
      { id: 'yolo', label: 'กล้อง AI', hint: 'AI นับรถจากกล้อง ค้นหากล้อง และตรวจคนไม่สวมหมวกกันน็อกหรือขับย้อนศร' },
    ],
  },
  {
    label: 'แจ้งและช่วยเหลือ',
    items: [
      { id: 'report', label: 'แจ้งน้ำท่วม', hint: 'แจ้งน้ำท่วมกับ BKK StreetSmart แนบรูป รายละเอียด และปักหมุดตำแหน่ง' },
      { id: 'ai', label: 'ถาม AI', hint: 'ถาม AI เรื่องรถติด น้ำท่วม หรือเรื่องทั่วไป' },
    ],
  },
  {
    label: 'เกี่ยวกับ',
    items: [
      { id: 'visitors', label: 'สถิติผู้ใช้', hint: 'มีคนใช้เว็บกี่คน และดูหน้าไหนมากที่สุด' },
    ],
  },
];

// Pages reached from the home screen (PM2.5 tile, "เขตของฉัน" button) stay out of the menu but keep their titles
export const PAGE_TITLES = {
  ...Object.fromEntries(NAV_GROUPS.flatMap((g) => g.items).map((i) => [i.id, i.label])),
  air: 'ฝุ่น PM2.5',
  district: 'เขตของฉัน',
};

// Console menu: a graphite rail split from the page by a 1px seam. Each group is a small quiet label; each page is
// a row with its icon. The page you are on sits on the one raised step, its icon and label in the action colour.
// Colours come from the tokens in index.css, so it follows light / dark.
function LogoMark() {
  // Small skyline mark, matches the icon stroke style used in the menu.
  return (
    <svg viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="w-8 h-8 text-[var(--c-ink)]" aria-hidden="true">
      <path d="M3 27h26" />
      <path d="M6 27V13l4-3 4 3v14" />
      <path d="M14 27V8l5-4 5 4v19" />
      <path d="M24 27V16l3 2v9" />
      <path d="M9 17h1M9 21h1M17 11h1M17 15h1M17 19h1M17 23h1" />
    </svg>
  );
}

export default function Sidebar({ page, onNavigate, aiActive, liveCount = 0, onClose, weatherPref, onWeatherPref, weatherScene, weatherBlocked }) {
  const badges = {
    ai: aiActive ? 'พร้อม' : null,
    cameras: liveCount ? `${liveCount}` : null,
  };
  return (
    <div className="h-full flex flex-col bg-[var(--c-surface)] text-[var(--c-ink)] border-r border-[var(--c-border)]">
      <div className={`h-16 px-4 flex items-center gap-3 border-b border-[var(--c-border)] ${skyClass(weatherScene)}`}>
        <LogoMark />
        <div className="min-w-0 flex-1">
          <p className="text-base font-bold leading-tight">BKK StreetSmart</p>
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

      <nav aria-label="หน้าหลัก" className="flex-1 overflow-y-auto px-3 py-3 scroll-soft">
        {NAV_GROUPS.map((group, gi) => (
          <div key={group.label} className={gi ? 'mt-5' : ''}>
            <p className="panel-label px-3 pb-1.5">{group.label}</p>
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
                      className={`group cursor-pointer w-full min-h-11 px-3 rounded-md flex items-center gap-3 text-left text-[15px] transition-colors duration-150 ${
                        on ? 'bg-[var(--c-raised)] text-[var(--c-ink)] font-semibold' : 'text-[var(--c-muted)] font-medium hover:bg-[var(--c-raised)] hover:text-[var(--c-ink)]'
                      }`}
                    >
                      <NavIcon name={item.id} className={`w-5 h-5 shrink-0 ${on ? 'text-[var(--c-primary)]' : ''}`} />
                      <span className="truncate flex-1">{item.label}</span>
                      {badge && (
                        <span className="num shrink-0 text-[11px] px-1.5 rounded-full border border-[var(--c-border)] text-[var(--c-ink)]">{badge}</span>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className="px-3 py-3 border-t border-[var(--c-border)] flex flex-col items-start gap-1">
        {weatherScene && <WeatherBadge scene={weatherScene} />}
        <ThemeToggle withLabel />
        {onWeatherPref && <WeatherFxToggle withLabel pref={weatherPref} blocked={weatherBlocked} onChange={onWeatherPref} className="justify-start" />}
      </div>
    </div>
  );
}
