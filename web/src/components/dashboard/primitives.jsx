// Page-level building blocks shared by every page (header, KPI tile, status banner, tabs, modal, share bar).
// Same visual language as ui.jsx: white cards, slate text, blue-600 for the one accent.
import { createContext, useContext, useEffect } from 'react';
import { Card, Badge, Skeleton, Truncate, FOCUS } from './ui.jsx';

const Nested = createContext(false);

// Wraps a page shown as a tab of another page: its PageHeader becomes a section heading (h2)
// under the parent's h1 instead of a second page title.
export function SubPage({ children }) {
  return <Nested.Provider value>{children}</Nested.Provider>;
}

// One title, one line of context, actions on the right
export function PageHeader({ title, description, actions, children }) {
  const nested = useContext(Nested);
  const H = nested ? 'h2' : 'h1';
  return (
    <header className={`flex flex-wrap items-end justify-between gap-3 ${nested ? '' : 'pt-1'}`}>
      <div className="min-w-0">
        <H className={`${nested ? 'text-[17px] leading-6' : 'text-xl leading-7'} font-semibold text-slate-900`}>{title}</H>
        {description && <p className="text-[13px] text-slate-600 mt-0.5 leading-5">{description}</p>}
        {children}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

// KPI tile: label, big number, one-line note, optional badge
export function StatTile({ label, value, sub, badge, loading, tone }) {
  const valueTone = { red: 'text-red-700', yellow: 'text-amber-700', green: 'text-emerald-700', blue: 'text-blue-700' }[tone] || 'text-slate-900';
  return (
    <Card as="div" className="p-4">
      <div className="min-w-0">
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs text-slate-600 truncate">{label}</p>
          {badge}
        </div>
        {loading ? <Skeleton className="h-7 w-20 mt-1" /> : <p className={`text-2xl font-semibold leading-8 tabular-nums ${valueTone}`}>{value}</p>}
        {sub && <Truncate text={sub} className="text-xs text-slate-500 mt-0.5" />}
      </div>
    </Card>
  );
}

// One-sentence status banner. tone: green | yellow | red | blue | neutral
export function StatusBanner({ tone = 'blue', label, children, action }) {
  const cls = {
    red: 'border-red-200 bg-red-50 text-red-900',
    yellow: 'border-amber-200 bg-amber-50 text-amber-900',
    green: 'border-emerald-200 bg-emerald-50 text-emerald-900',
    blue: 'border-blue-200 bg-blue-50 text-blue-900',
    neutral: 'border-slate-200 bg-slate-50 text-slate-800',
  }[tone];
  return (
    <div role="status" className={`rounded-xl border px-4 py-3 flex flex-wrap items-center gap-3 ${cls}`}>
      {label && (
        <Badge tone={tone} dot>
          {label}
        </Badge>
      )}
      <p className="text-sm flex-1 min-w-[200px] leading-5">{children}</p>
      {action}
    </div>
  );
}

// Section switcher; `tabs` is [{id, label, badge?}]
export function Tabs({ tabs, value, onChange, label }) {
  return (
    <div role="tablist" aria-label={label} className="flex items-center gap-1 border-b border-slate-200 overflow-x-auto overflow-y-hidden scroll-soft">
      {tabs.map((t) => {
        const on = value === t.id;
        return (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={on}
            onClick={() => onChange(t.id)}
            className={`cursor-pointer inline-flex items-center gap-1.5 whitespace-nowrap px-3 h-10 -mb-px text-sm font-medium border-b-2 transition-colors duration-150 ${FOCUS} ${
              on ? 'border-blue-600 text-blue-700' : 'border-transparent text-slate-600 hover:text-slate-900'
            }`}
          >
            {t.label}
            {t.badge != null && <span className="ml-0.5 rounded-md bg-slate-100 px-1.5 text-xs text-slate-600">{t.badge}</span>}
          </button>
        );
      })}
    </div>
  );
}

// Centered modal; closes on backdrop click or Escape
export function Modal({ open, onClose, title, subtitle, children, footer, wide = false }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e) => e.key === 'Escape' && onClose?.();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === 'string' ? title : undefined}
        onClick={(e) => e.stopPropagation()}
        className={`bg-white rounded-xl border border-slate-200 w-full ${wide ? 'max-w-4xl' : 'max-w-2xl'} overflow-hidden`}
      >
        <div className="px-4 py-3 border-b border-slate-200 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-[15px] font-semibold text-slate-900 leading-6 truncate">{title}</h2>
            {subtitle && <p className="text-xs text-slate-600 mt-0.5">{subtitle}</p>}
          </div>
          <button
            type="button"
            onClick={onClose}
            className={`cursor-pointer h-8 px-2.5 rounded-lg text-xs text-slate-600 hover:bg-slate-100 hover:text-slate-900 flex items-center justify-center ${FOCUS}`}
          >
            ปิด
          </button>
        </div>
        {children}
        {footer && <div className="px-4 py-3 border-t border-slate-200 bg-slate-50 flex flex-wrap items-center justify-between gap-3">{footer}</div>}
      </div>
    </div>
  );
}

// Stacked share bar with legend. parts: [{label, value, color}] where color is a bg-* class
export function ShareBar({ parts, unit = '' }) {
  const total = parts.reduce((a, p) => a + (p.value || 0), 0) || 1;
  return (
    <div>
      <div className="h-2.5 w-full rounded-full bg-slate-100 overflow-hidden flex" role="img" aria-label={parts.map((p) => `${p.label} ${p.value}`).join(', ')}>
        {parts.map((p) => (
          <div key={p.label} className={`h-full ${p.color}`} style={{ width: `${((p.value || 0) / total) * 100}%` }} />
        ))}
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-600">
        {parts.map((p) => (
          <li key={p.label} className="inline-flex items-center gap-1.5 whitespace-nowrap">
            <span className={`w-2.5 h-2.5 rounded-sm shrink-0 ${p.color}`} aria-hidden="true" />
            {p.label}
            <span className="tabular-nums font-medium text-slate-900">
              {Number(p.value || 0).toLocaleString('th-TH')}
              {unit}
            </span>
            <span className="tabular-nums text-slate-500">({Math.round(((p.value || 0) / total) * 100)}%)</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
