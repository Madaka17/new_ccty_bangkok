import { forwardRef } from 'react';
// Small neutral building blocks shared across the dashboard.
// One accent (blue-600) for interactive elements; slate for everything else.

export const FOCUS = 'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 focus-visible:ring-offset-2';

export const Card = forwardRef(function Card({ as: Tag = 'section', className = '', children, ...rest }, ref) {
  return (
    <Tag ref={ref} className={`rounded-xl border border-slate-200 bg-white ${className}`} {...rest}>
      {children}
    </Tag>
  );
});

export function SectionHeader({ id, title, description, action, className = '' }) {
  return (
    <div className={`flex flex-wrap items-start justify-between gap-3 ${className}`}>
      <div className="min-w-0">
        <h3 id={id} className="text-[15px] font-semibold text-slate-900 leading-6">
          {title}
        </h3>
        {description && <p className="text-[13px] text-slate-600 mt-0.5 leading-5">{description}</p>}
      </div>
      {action && <div className="shrink-0 max-w-full">{action}</div>}
    </div>
  );
}

const BADGE_TONE = {
  neutral: 'bg-slate-100 text-slate-700 border-slate-200',
  green: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  yellow: 'bg-amber-50 text-amber-700 border-amber-200',
  red: 'bg-red-50 text-red-700 border-red-200',
  blue: 'bg-blue-50 text-blue-700 border-blue-200',
};

export function Badge({ tone = 'neutral', dot = false, className = '', children }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-medium leading-5 whitespace-nowrap ${BADGE_TONE[tone]} ${className}`}
    >
      {dot && <span className="w-1.5 h-1.5 rounded-full bg-current" aria-hidden="true" />}
      {children}
    </span>
  );
}

const BTN_VARIANT = {
  primary: 'bg-blue-600 text-white border-blue-600 hover:bg-blue-700 hover:border-blue-700',
  secondary: 'bg-white text-slate-800 border-slate-300 hover:bg-slate-50',
  ghost: 'bg-transparent text-slate-700 border-transparent hover:bg-slate-100',
  danger: 'bg-red-600 text-white border-red-600 hover:bg-red-700',
};
const BTN_SIZE = { sm: 'h-8 px-3 text-xs', md: 'h-10 px-4 text-sm' };

export function Button({ variant = 'secondary', size = 'md', loading = false, disabled, className = '', children, ...rest }) {
  const off = disabled || loading;
  return (
    <button
      type="button"
      disabled={off}
      aria-busy={loading || undefined}
      className={`inline-flex items-center justify-center gap-2 rounded-lg border font-medium transition-colors duration-150 ${FOCUS} ${BTN_VARIANT[variant]} ${BTN_SIZE[size]} ${off ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer'} ${className}`}
      {...rest}
    >
      {loading && <Spinner className="w-3.5 h-3.5" />}
      {children}
    </button>
  );
}

export function Spinner({ className = 'w-4 h-4' }) {
  return (
    <svg className={`animate-spin ${className}`} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="3" className="opacity-25" />
      <path d="M21 12a9 9 0 0 1-9 9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

// Tab-like control; `options` is [[value, label], ...]
export function Segmented({ options, value, onChange, label }) {
  return (
    <div role="tablist" aria-label={label} className="inline-flex max-w-full overflow-x-auto rounded-lg border border-slate-200 bg-slate-100 p-0.5">
      {options.map(([k, text]) => {
        const on = value === k;
        return (
          <button
            key={k}
            type="button"
            role="tab"
            aria-selected={on}
            onClick={() => onChange(k)}
            className={`cursor-pointer shrink-0 whitespace-nowrap rounded-md px-3 h-7 text-xs font-medium transition-colors duration-150 ${FOCUS} ${
              on ? 'bg-white text-slate-900 border border-slate-200' : 'text-slate-600 hover:text-slate-900 border border-transparent'
            }`}
          >
            {text}
          </button>
        );
      })}
    </div>
  );
}

export function Skeleton({ className = '' }) {
  return <div className={`animate-pulse rounded-md bg-slate-100 ${className}`} aria-hidden="true" />;
}

export function EmptyState({ title, description, action }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 px-4 py-8 text-center">
      <p className="text-sm font-medium text-slate-700">{title}</p>
      {description && <p className="text-[13px] text-slate-500 mt-1">{description}</p>}
      {action && <div className="mt-3 flex justify-center">{action}</div>}
    </div>
  );
}

export function ErrorState({ message = 'โหลดข้อมูลไม่สำเร็จ', onRetry, retrying = false }) {
  return (
    <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 flex flex-wrap items-center justify-between gap-3">
      <p className="text-sm text-red-800">{message}</p>
      {onRetry && (
        <Button size="sm" onClick={onRetry} loading={retrying}>
          ลองใหม่
        </Button>
      )}
    </div>
  );
}

// Truncated single line that reveals the full text on hover / focus via the native tooltip
export function Truncate({ text, className = '' }) {
  return (
    <span className={`block truncate ${className}`} title={text}>
      {text}
    </span>
  );
}
