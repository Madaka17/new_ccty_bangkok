import { useEffect, useState } from 'react';

// Small pieces shared by the overview cards: empty block, series legend, hover tooltip, chart width.

// Width in CSS px of the element behind ref, kept current with a ResizeObserver. 640 until it is measured.
export function useChartWidth(ref) {
  const [width, setWidth] = useState(640);
  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const apply = (w) => {
      if (w > 0) setWidth(Math.round(w));
    };
    apply(el.clientWidth);
    if (typeof ResizeObserver === 'undefined') return undefined;
    const ro = new ResizeObserver((entries) => apply(entries[0]?.contentRect?.width ?? 0));
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref]);
  return width;
}

export function EmptyBlock({ text, className = 'h-56' }) {
  return (
    <div className={`flex items-center justify-center rounded-xl border border-dashed border-[var(--c-border-strong)] px-4 text-center text-sm text-[var(--c-muted)] ${className}`}>
      {text}
    </div>
  );
}

export function SeriesLegend({ items }) {
  return (
    <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-[var(--c-muted)]">
      {items.map((it) => (
        <li key={it.label} className="flex items-center gap-1.5">
          <span aria-hidden="true" className="h-2.5 w-2.5 rounded-full" style={{ background: it.token }} />
          {it.label}
        </li>
      ))}
    </ul>
  );
}

// Floating card over a chart. xPct places it horizontally (0-100 of the chart width) and keeps it inside the card.
export function ChartTip({ xPct, children }) {
  const transform = xPct > 80 ? 'translateX(-100%)' : xPct < 20 ? 'none' : 'translateX(-50%)';
  return (
    <div
      className="pointer-events-none absolute top-2 z-10 min-w-36 rounded-xl border border-[var(--c-border)] bg-[var(--c-surface)] px-3 py-2 text-xs text-[var(--c-ink)] shadow-[var(--c-card-shadow)]"
      style={{ left: `${xPct}%`, transform }}
    >
      {children}
    </div>
  );
}

export function TipRow({ token, label, value }) {
  return (
    <p className="mt-1 flex items-center gap-2">
      <span aria-hidden="true" className="h-2 w-2 rounded-full" style={{ background: token }} />
      <span className="text-[var(--c-muted)]">{label}</span>
      <span className="num ml-auto font-semibold">{value}</span>
    </p>
  );
}
