import { useEffect, useId, useRef } from 'react';
import { motion } from 'framer-motion';
import { FOCUS } from './dashboard/ui.jsx';
import NavIcon from './NavIcons.jsx';

// Segmented switch between the views of one page (Camera AI, Water, Accidents & Risk): each view is a card,
// the open one lifts out of the tray. tabs: [{ id, label, icon, hint? }]; the hint is the tooltip only.
// Lists of 5+ tabs run as one horizontally scrollable row below sm (phones), the grid from sm up.
export default function ViewSwitch({ tabs, value, onChange, label }) {
  const pill = useId();   // the lifted card slides to the tab picked
  const tray = useRef(null);
  const long = tabs.length >= 5;
  const cols = { 2: 'grid-cols-2', 3: 'grid-cols-1 md:grid-cols-3', 4: 'grid-cols-2 xl:grid-cols-4', 7: 'grid-cols-2 md:grid-cols-4', 8: 'grid-cols-2 md:grid-cols-4' }[tabs.length]
    || 'grid-cols-2 md:grid-cols-3 xl:grid-cols-5';
  const layout = long ? 'flex overflow-x-auto snap-x snap-mandatory scroll-soft sm:grid sm:overflow-visible' : `grid ${cols}`;

  // On phones, keep the selected tab in view of the scrolling row.
  useEffect(() => {
    if (!long || !tray.current || !window.matchMedia?.('(max-width: 639px)').matches) return;
    const el = tray.current.querySelector('[aria-selected="true"]');
    if (!el?.scrollIntoView) return;
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    el.scrollIntoView({ inline: 'nearest', block: 'nearest', behavior: reduce ? 'auto' : 'smooth' });
  }, [value, long]);

  const tablist = (
    <div ref={tray} role="tablist" aria-label={label} className={`seg-tray ${layout} gap-1.5 p-1.5 rounded-2xl w-full ${tabs.length > 2 ? '' : 'sm:w-fit sm:min-w-[520px]'}`}>
      {tabs.map((t) => {
        const on = value === t.id;
        return (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={on}
            title={t.hint}
            onClick={() => onChange(t.id)}
            className={`seg-slide relative cursor-pointer flex items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors duration-200 ${FOCUS} ${on ? '' : 'seg-off'} ${long ? 'shrink-0 snap-start max-sm:min-h-11 max-sm:gap-2' : ''}`}
          >
            {on && <motion.span layoutId={pill} className="seg-pill" transition={{ type: 'spring', stiffness: 380, damping: 34 }} />}
            <span className={`relative shrink-0 grid place-items-center w-9 h-9 rounded-lg transition-colors duration-200 ${on ? 'bg-[var(--c-on-primary)]/15 text-[var(--c-on-primary)]' : 'seg-icon'}`}>
              <NavIcon name={t.icon} className="w-5 h-5" />
            </span>
            <span className="relative min-w-0">
              <span className={`block text-sm font-semibold leading-snug ${long ? 'whitespace-nowrap sm:whitespace-normal sm:line-clamp-2' : 'line-clamp-2'}`}>{t.label}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
  if (!long) return tablist;
  // Phones: a fade on the right edge says the row keeps going past the screen.
  return (
    <div className="relative w-full">
      {tablist}
      <div data-fade="end" aria-hidden="true" className="pointer-events-none absolute inset-y-0 right-0 w-8 rounded-r-2xl bg-gradient-to-r from-transparent to-[var(--c-ground)] sm:hidden" />
    </div>
  );
}
