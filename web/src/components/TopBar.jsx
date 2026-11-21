import { useEffect, useMemo, useRef, useState } from 'react';
import ThemeToggle from './ThemeToggle.jsx';
import NavIcon from './NavIcons.jsx';
import { WeatherBadge } from './fx/WeatherFx.jsx';
import { ALL_PAGES, searchPages } from '../lib/pageSearch.js';

// Skyline mark, the same as the sidebar logo
function SkylineMark() {
  return (
    <svg viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5" aria-hidden="true">
      <path d="M3 27h26" />
      <path d="M6 27V13l4-3 4 3v14" />
      <path d="M14 27V8l5-4 5 4v19" />
      <path d="M24 27V16l3 2v9" />
      <path d="M9 17h1M9 21h1M17 11h1M17 15h1M17 19h1M17 23h1" />
    </svg>
  );
}

// Desktop top bar: page search, live cameras link, weather, bell, theme and the "my district" chip
export default function TopBar({ onNavigate, liveCount = 0, weatherScene, alertCount = 0, district = null }) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const inputRef = useRef(null);
  const blurTimer = useRef(null);
  useEffect(() => () => clearTimeout(blurTimer.current), []);
  const results = useMemo(() => searchPages(query, ALL_PAGES), [query]);
  const showList = open && query.trim() !== '';
  const activeId = showList && results[active] ? `page-search-opt-${results[active].id}` : undefined;

  const go = (id) => {
    onNavigate(id);
    setQuery('');
    setOpen(false);
    setActive(0);
    inputRef.current?.blur();
  };

  const onKeyDown = (e) => {
    if (e.key === 'ArrowDown' && results.length) {
      e.preventDefault();
      setOpen(true);
      setActive((i) => (i + 1) % results.length);
    } else if (e.key === 'ArrowUp' && results.length) {
      e.preventDefault();
      setOpen(true);
      setActive((i) => (i - 1 + results.length) % results.length);
    } else if (e.key === 'Enter') {
      const hit = results[active] || results[0];
      if (showList && hit) { e.preventDefault(); go(hit.id); }
    } else if (e.key === 'Escape') {
      setQuery('');
      setOpen(false);
      setActive(0);
    }
  };

  return (
    <div className="hidden lg:flex sticky top-0 z-30 h-16 items-center gap-4 px-6 bg-[var(--c-ground)] dark:border-b dark:border-[var(--c-border)]">
      <div className="relative max-w-md flex-1">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5 absolute left-3 top-1/2 -translate-y-1/2 text-[var(--c-muted)] pointer-events-none" aria-hidden="true">
          <circle cx="11" cy="11" r="7" />
          <path d="M20 20l-3.5-3.5" />
        </svg>
        <input
          ref={inputRef}
          type="search"
          role="combobox"
          aria-expanded={showList}
          aria-controls={showList ? 'page-search-list' : undefined}
          aria-activedescendant={activeId}
          aria-autocomplete="list"
          aria-label="ค้นหาหน้า"
          placeholder="ค้นหาหน้า"
          value={query}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); setActive(0); }}
          onFocus={() => setOpen(true)}
          onBlur={() => { clearTimeout(blurTimer.current); blurTimer.current = setTimeout(() => setOpen(false), 120); }}
          onKeyDown={onKeyDown}
          className="w-full min-h-11 pl-10 pr-3 rounded-xl bg-[var(--c-raised)] border border-transparent text-[var(--c-ink)] placeholder:text-[var(--c-muted)] text-sm"
        />
        {showList && (
          <ul id="page-search-list" role="listbox" aria-label="หน้าที่พบ" className="absolute left-0 right-0 top-full mt-1 rounded-lg border border-[var(--c-border)] bg-[var(--c-surface)] shadow-lg overflow-hidden">
            {results.length === 0 ? (
              <li role="presentation" className="px-3 py-3 text-sm text-[var(--c-muted)]">ไม่พบหน้านี้</li>
            ) : results.map((p, i) => (
              <li
                key={p.id}
                id={`page-search-opt-${p.id}`}
                role="option"
                aria-selected={i === active}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => go(p.id)}
                onMouseEnter={() => setActive(i)}
                className={`cursor-pointer px-3 py-2 min-h-11 flex flex-col justify-center ${i === active ? 'bg-[var(--c-primary-tint)]' : ''}`}
              >
                <span className="text-sm font-bold text-[var(--c-ink)]">{p.label}</span>
                {p.hint && <span className="text-xs text-[var(--c-muted)] truncate">{p.hint}</span>}
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="flex items-center gap-2 shrink-0 ml-auto">
        {liveCount > 0 && (
          <button type="button" onClick={() => onNavigate('cameras')} className="cursor-pointer min-h-11 px-2 text-sm text-[var(--c-muted)] hover:text-[var(--c-ink)]">
            ดูสด {liveCount} กล้อง
          </button>
        )}
        <WeatherBadge scene={weatherScene} />
        <button
          type="button"
          onClick={() => onNavigate('alerts')}
          aria-label="ประกาศเตือน"
          title="ประกาศเตือน"
          className="cursor-pointer relative shrink-0 w-11 h-11 rounded-xl grid place-items-center text-[var(--c-ink)] hover:bg-[var(--c-raised)]"
        >
          <NavIcon name="alerts" className="w-5 h-5" />
          {alertCount > 0 && (
            <span aria-hidden="true" className="absolute top-2.5 right-2.5 w-2 h-2 rounded-full bg-[var(--act-ring)] ring-2 ring-[var(--c-ground)]" />
          )}
        </button>
        <ThemeToggle />
        <button
          type="button"
          onClick={() => onNavigate('district')}
          className="cursor-pointer shrink-0 min-h-11 pl-1.5 pr-3 rounded-xl hover:bg-[var(--c-raised)] flex items-center gap-2.5"
        >
          <span aria-hidden="true" className="w-9 h-9 rounded-full grid place-items-center shrink-0 bg-[var(--c-primary-tint)] text-[var(--c-primary)] text-sm font-bold">
            {district ? district.charAt(0) : <SkylineMark />}
          </span>
          <span className="min-w-0 text-left">
            <span className="block text-sm font-semibold text-[var(--c-ink)] truncate max-w-[10rem]">{district || 'เลือกเขตของฉัน'}</span>
            <span className="block text-xs text-[var(--c-muted)]">เขตของฉัน</span>
          </span>
        </button>
      </div>
    </div>
  );
}
