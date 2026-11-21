import { useState } from 'react';
import ThemeToggle from './ThemeToggle.jsx';
import NavIcon from './NavIcons.jsx';
import { WeatherBadge, WeatherFxToggle, skyClass } from './fx/WeatherFx.jsx';
import { NAV_GROUPS, PAGE_TITLES, PAGE_HINTS } from '../lib/navPages.js';

export { NAV_GROUPS, PAGE_TITLES, PAGE_HINTS };

const CLOSED_KEY = 'nav-groups-closed';

// Labels of the groups the viewer collapsed. Storage can be blocked or hold bad JSON; then nothing is collapsed.
export function readClosedGroups() {
  try {
    const v = JSON.parse(localStorage.getItem(CLOSED_KEY) || '[]');
    return Array.isArray(v) ? v.filter((x) => typeof x === 'string') : [];
  } catch {
    return [];
  }
}

function writeClosedGroups(list) {
  try { localStorage.setItem(CLOSED_KEY, JSON.stringify(list)); } catch {}
}

// Dashboard-style menu: a brand header, collapsible groups with a sky-blue filled row for the current page,
// count pills, and a footer with the report button and the dark-mode switch. Colours come from the --c-* tokens.
function LogoMark() {
  // Small skyline mark, matches the icon stroke style used in the menu.
  return (
    <svg viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="w-6 h-6 text-[var(--c-on-primary)]" aria-hidden="true">
      <path d="M3 27h26" />
      <path d="M6 27V13l4-3 4 3v14" />
      <path d="M14 27V8l5-4 5 4v19" />
      <path d="M24 27V16l3 2v9" />
      <path d="M9 17h1M9 21h1M17 11h1M17 15h1M17 19h1M17 23h1" />
    </svg>
  );
}

const PILL = 'num text-[11px] min-w-5 h-5 px-1.5 rounded-full grid place-items-center';

export default function Sidebar({ page, onNavigate, aiActive, liveCount = 0, alertCount = 0, onReport, onClose, weatherPref, onWeatherPref, weatherScene, weatherBlocked }) {
  const [closed, setClosed] = useState(readClosedGroups);

  const toggleGroup = (label) => {
    const next = closed.includes(label) ? closed.filter((l) => l !== label) : [...closed, label];
    setClosed(next);
    writeClosedGroups(next);
  };

  return (
    <div className="h-full flex flex-col bg-[var(--c-surface)] text-[var(--c-ink)] border-r border-[var(--c-border)]">
      <div className={`h-20 px-4 flex items-center gap-3 ${skyClass(weatherScene)}`}>
        <span className="w-9 h-9 rounded-xl bg-[var(--c-primary-fill)] grid place-items-center shrink-0 shadow-[var(--c-glow)]">
          <LogoMark />
        </span>
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
        {NAV_GROUPS.map((group, gi) => {
          const holdsPage = group.items.some((item) => item.id === page);
          const open = holdsPage || !closed.includes(group.label);
          const listId = `nav-group-${gi}`;
          const badges = {
            ai: aiActive ? { text: 'พร้อม', tone: 'grey' } : null,
            cameras: liveCount ? { text: `${liveCount}`, tone: 'grey' } : null,
            alerts: alertCount > 0 ? { text: `${alertCount}`, tone: 'alert' } : null,
          };
          return (
            <div key={group.label} className={gi ? 'mt-5' : ''}>
              <button
                type="button"
                onClick={() => toggleGroup(group.label)}
                disabled={holdsPage}
                aria-expanded={open}
                aria-controls={listId}
                className="cursor-pointer w-full min-h-11 px-3 flex items-center gap-2 text-left panel-label disabled:cursor-default"
              >
                <span className="flex-1">{group.label}</span>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={`w-4 h-4 shrink-0 transition-transform duration-150 motion-reduce:transition-none ${open ? 'rotate-90' : ''}`} aria-hidden="true">
                  <path d="M9 6l6 6-6 6" />
                </svg>
              </button>
              <div className={gi ? 'ml-5 pl-2 border-l border-[var(--c-border)]' : ''}>
                <ul id={listId} hidden={!open} className="flex flex-col gap-0.5">
                  {group.items.map((item) => {
                    const on = page === item.id;
                    const badge = badges[item.id];
                    const pillClass = on
                      ? 'bg-white/25 text-[var(--c-on-primary)]'
                      : badge?.tone === 'alert'
                        ? 'bg-[var(--c-series-b)] text-white'
                        : 'bg-[var(--c-raised)] text-[var(--c-ink)]';
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
                          className={`group cursor-pointer w-full min-h-11 px-3 rounded-xl flex items-center gap-3 text-left text-[15px] transition-colors duration-150 ${
                            on
                              ? 'bg-[var(--c-primary-fill)] text-[var(--c-on-primary)] font-semibold shadow-[var(--c-glow)]'
                              : 'text-[var(--c-muted)] font-medium hover:bg-[var(--c-raised)] hover:text-[var(--c-ink)]'
                          }`}
                        >
                          <NavIcon name={item.id} className="w-5 h-5 shrink-0" />
                          <span className="truncate flex-1">{item.label}</span>
                          {badge && <span className={`${PILL} shrink-0 ${pillClass}`}>{badge.text}</span>}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            </div>
          );
        })}
      </nav>

      <div className="px-3 py-3 border-t border-[var(--c-border)] flex flex-col items-stretch gap-1">
        {onReport && (
          <button
            type="button"
            aria-label="แจ้งน้ำท่วม"
            onClick={() => {
              onReport();
              onClose?.();
            }}
            className="cursor-pointer w-full min-h-11 px-2 rounded-xl flex items-center gap-3 text-left hover:bg-[var(--c-raised)] transition-colors duration-150"
          >
            <span className="w-10 h-10 rounded-full bg-[var(--c-primary-fill)] text-[var(--c-on-primary)] shadow-[var(--c-glow)] grid place-items-center shrink-0" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" className="w-5 h-5" aria-hidden="true">
                <path d="M12 5v14M5 12h14" />
              </svg>
            </span>
            <span className="font-medium text-[15px]">แจ้งน้ำท่วม</span>
          </button>
        )}
        {weatherScene && <WeatherBadge scene={weatherScene} />}
        <ThemeToggle variant="switch" />
        {onWeatherPref && <WeatherFxToggle withLabel pref={weatherPref} blocked={weatherBlocked} onChange={onWeatherPref} className="justify-start" />}
      </div>
    </div>
  );
}
