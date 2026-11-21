import { useTheme } from '../lib/theme.js';

const MOON = <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" />;
const SUN = (
  <>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
  </>
);

// Light / dark switch: a sun in dark mode (go light), a moon in light mode (go dark).
// variant "switch": a full-width row for the sidebar footer, with a moon, the label and an on/off track.
export default function ThemeToggle({ withLabel = false, className = '', variant }) {
  const [theme, toggle] = useTheme();
  const dark = theme === 'dark';
  const toDark = theme !== 'dark';
  const label = toDark ? 'โหมดมืด' : 'โหมดสว่าง';

  if (variant === 'switch') {
    return (
      <button
        type="button"
        role="switch"
        aria-checked={dark}
        onClick={toggle}
        title={`เปลี่ยนเป็น${label}`}
        className={`cursor-pointer w-full min-h-11 px-2 rounded-xl flex items-center gap-3 text-left text-[15px] font-medium text-[var(--c-ink)] hover:bg-[var(--c-raised)] transition-colors duration-150 ${className}`}
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5 shrink-0 text-[var(--c-muted)]" aria-hidden="true">
          {MOON}
        </svg>
        <span className="flex-1">โหมดมืด</span>
        <span aria-hidden="true" className={`relative shrink-0 w-10 h-[22px] rounded-full transition-colors duration-150 ${dark ? 'bg-[var(--c-primary-fill)]' : 'bg-[var(--c-border-strong)]'}`}>
          <span className={`absolute top-0.5 left-0.5 w-[18px] h-[18px] rounded-full bg-white shadow-sm transition-transform duration-150 ${dark ? 'translate-x-[18px]' : ''}`} />
        </span>
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={`เปลี่ยนเป็น${label}`}
      title={`เปลี่ยนเป็น${label}`}
      className={`cursor-pointer inline-flex items-center justify-center gap-2 min-h-11 min-w-11 rounded-md text-[var(--c-ink)] hover:bg-[var(--c-raised)] transition-colors duration-150 ${withLabel ? 'px-3 text-sm font-medium' : ''} ${className}`}
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5 shrink-0" aria-hidden="true">
        {toDark ? MOON : SUN}
      </svg>
      {withLabel && label}
    </button>
  );
}
