import { useState } from 'react';

// Collapsible block of layers in the map side panel; the header says how many of its layers are on,
// so a closed group still shows what is drawn on the map.
export function LayerGroup({ title, hint, on = 0, defaultOpen = false, children }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-lg border border-cream-200 bg-white shrink-0">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="cursor-pointer w-full flex items-center gap-2 px-3 py-2.5 text-left rounded-lg hover:bg-slate-50 transition-colors duration-150"
      >
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-semibold text-ink-900">{title}</span>
          {hint && <span className="block text-[11px] text-slate-500 truncate" title={hint}>{hint}</span>}
        </span>
        {on > 0 && <span className="shrink-0 rounded-md bg-blue-50 text-blue-700 px-1.5 text-[11px] font-medium tabular-nums">เปิด {on}</span>}
        <svg viewBox="0 0 20 20" fill="currentColor" className={`w-4 h-4 shrink-0 text-slate-500 transition-transform duration-150 ${open ? 'rotate-180' : ''}`} aria-hidden="true">
          <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.06l3.71-3.83a.75.75 0 111.08 1.04l-4.25 4.39a.75.75 0 01-1.08 0L5.21 8.27a.75.75 0 01.02-1.06z" clipRule="evenodd" />
        </svg>
      </button>
      {open && (
        <div className="px-3 pb-3 pt-3 border-t border-cream-200 flex flex-col divide-y divide-slate-100 [&>*]:py-3 [&>*:first-child]:pt-0 [&>*:last-child]:pb-0">
          {children}
        </div>
      )}
    </div>
  );
}
