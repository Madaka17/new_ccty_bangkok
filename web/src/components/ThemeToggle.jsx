import { useTheme } from '../lib/theme.js';

// Light / dark switch: a sun in dark mode (go light), a moon in light mode (go dark)
export default function ThemeToggle({ withLabel = false, className = '' }) {
  const [theme, toggle] = useTheme();
  const toDark = theme !== 'dark';
  const label = toDark ? 'โหมดมืด' : 'โหมดสว่าง';
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={`เปลี่ยนเป็น${label}`}
      title={`เปลี่ยนเป็น${label}`}
      className={`cursor-pointer inline-flex items-center justify-center gap-2 min-h-11 min-w-11 rounded-md text-[var(--c-ink)] hover:bg-[var(--c-raised)] transition-colors duration-150 ${withLabel ? 'px-3 text-sm font-medium' : ''} ${className}`}
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5 shrink-0" aria-hidden="true">
        {toDark ? (
          <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" />
        ) : (
          <>
            <circle cx="12" cy="12" r="4" />
            <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
          </>
        )}
      </svg>
      {withLabel && label}
    </button>
  );
}
