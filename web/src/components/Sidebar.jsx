import ThemeToggle from './ThemeToggle.jsx';
import NavIcon from './NavIcons.jsx';
import { WeatherBadge, WeatherFxToggle, skyClass } from './fx/WeatherFx.jsx';
import { NAV_GROUPS, PAGE_TITLES, PAGE_HINTS } from '../lib/navPages.js';

export { NAV_GROUPS, PAGE_TITLES, PAGE_HINTS };

// Console menu: a graphite rail split from the page by a 1px seam. Each group is a small quiet label; each page is
// a row with its icon. The page you are on sits on the one raised step, its icon and label in the action colour.
// Colours come from the tokens in index.css, so it follows light / dark.
function LogoMark() {
  // Small skyline mark, matches the icon stroke style used in the menu.
  return (
    <svg viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="w-8 h-8 text-[var(--c-primary)]" aria-hidden="true">
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
                      className={`group cursor-pointer w-full min-h-11 px-3 rounded-lg flex items-center gap-3 text-left text-[15px] transition-colors duration-150 ${
                        on
                          ? 'bg-[var(--c-primary-fill)] text-[var(--c-on-primary)] font-semibold shadow-[var(--c-glow)]'
                          : 'text-[var(--c-muted)] font-medium hover:bg-[var(--c-raised)] hover:text-[var(--c-ink)]'
                      }`}
                    >
                      <NavIcon name={item.id} className="w-5 h-5 shrink-0" />
                      <span className="truncate flex-1">{item.label}</span>
                      {badge && (
                        <span className={`num shrink-0 text-[11px] px-1.5 rounded-full border ${on ? 'border-current text-[var(--c-on-primary)]' : 'border-[var(--c-border)] text-[var(--c-ink)]'}`}>{badge}</span>
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
