import { useMemo } from 'react';
import { badgeText, dropCount } from '../../lib/weatherFx.js';

// Weather background behind the content (same layer approach as RiverBackdrop). Decoration only: fixed,
// z-index -1, pointer-events none, aria-hidden. Particles are made once per scene (useMemo), and the
// animations only move transform and opacity (index.css, "weather background").
const isNarrow = () => typeof window !== 'undefined' && window.matchMedia?.('(max-width: 639px)').matches;

const rand = (a, b) => a + Math.random() * (b - a);

function makeDrops(intensity, narrow, windy) {
  const n = dropCount(intensity, narrow);
  const slant = windy ? 25 : 12;
  return Array.from({ length: n }, (_, i) => ({
    key: i,
    x: rand(-5, 105),
    len: rand(14, 28),
    angle: slant,
    delay: rand(0, 1.1),
    dur: intensity === 'heavy' ? rand(0.5, 0.8) : rand(0.7, 1.1),
    opacity: rand(0.6, 1),
  }));
}

function makeGusts(narrow) {
  const n = narrow ? 8 : 16;
  return Array.from({ length: n }, (_, i) => ({
    key: i,
    top: rand(4, 96),
    width: rand(80, 160),
    dur: rand(1.5, 3),
    delay: -rand(0, 3),
    opacity: rand(0.5, 1),
  }));
}

function Rain({ intensity, windy, narrow }) {
  const drops = useMemo(() => makeDrops(intensity, narrow, windy), [intensity, windy, narrow]);
  return (
    <>
      <div className="wfx-sky" data-i={intensity} />
      {drops.map((d) => (
        <span key={d.key} className="wfx-drop" style={{ left: `${d.x}%`, transform: `rotate(${d.angle}deg)` }}>
          <i
            className="wfx-streak"
            style={{
              height: `${d.len}px`,
              opacity: d.opacity,
              animationDelay: `${d.delay}s`,
              animationDuration: `${d.dur}s`,
            }}
          />
        </span>
      ))}
    </>
  );
}

function Gusts({ narrow }) {
  const gusts = useMemo(() => makeGusts(narrow), [narrow]);
  return gusts.map((g) => (
    <i
      key={g.key}
      className="wfx-gust"
      style={{ top: `${g.top}%`, width: `${g.width}px`, opacity: g.opacity, animationDuration: `${g.dur}s`, animationDelay: `${g.delay}s` }}
    />
  ));
}

export default function WeatherFx({ scene, allowed }) {
  const narrow = useMemo(() => isNarrow(), []);
  if (!allowed || !scene) return null;
  const { kind, intensity, cool, windy } = scene;
  const raining = kind === 'rain' || kind === 'storm';

  return (
    <div className="wfx-layer" aria-hidden="true" data-kind={kind}>
      {raining && <Rain intensity={intensity} windy={windy} narrow={narrow} />}
      {kind === 'storm' && <span className="wfx-flash" />}
      {kind === 'cloudy' && (
        <>
          <span className="wfx-veil" />
          <span className="wfx-cloud wfx-cloud-a" />
          <span className="wfx-cloud wfx-cloud-b" />
          <span className="wfx-cloud wfx-cloud-c" />
        </>
      )}
      {kind === 'sunny' && (
        <>
          <span className="wfx-sun" />
          <span className="wfx-rays">
            <span className="wfx-ray" style={{ transform: 'rotate(-30deg)' }} />
            <span className="wfx-ray" style={{ transform: 'rotate(0deg)' }} />
            <span className="wfx-ray" style={{ transform: 'rotate(28deg)' }} />
          </span>
        </>
      )}
      {cool && (
        <>
          <span className="wfx-cool" />
          <span className="wfx-mist" />
        </>
      )}
      {windy && <Gusts narrow={narrow} />}
    </div>
  );
}

const ICON = {
  storm: <path d="M13 2L4 14h7l-1 8 9-12h-7l1-8z" />,
  rain: <path d="M12 3c3 4 5 7 5 10a5 5 0 0 1-10 0c0-3 2-6 5-10z" />,
  wind: <path d="M3 8h11a3 3 0 1 0-3-3M3 12h15a3 3 0 1 1-3 3M3 16h7" />,
  cool: <path d="M14 14.76V5a2 2 0 0 0-4 0v9.76a4 4 0 1 0 4 0z" />,
};

// Small status pill: icon always, text from sm up (the text is the aria-label on phones). Shows even when effects are off.
export function WeatherBadge({ scene }) {
  const text = scene ? badgeText(scene) : '';
  if (!text) return null;
  const icon = scene.kind === 'storm' ? 'storm' : scene.kind === 'rain' ? 'rain' : scene.windy ? 'wind' : 'cool';
  return (
    <span
      role="status"
      aria-label={text}
      className="shrink-0 inline-flex items-center gap-1.5 h-8 px-2 sm:px-2.5 rounded-full text-xs font-medium bg-[var(--c-primary-tint)] text-[var(--c-primary)]"
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4 shrink-0" aria-hidden="true">
        {ICON[icon]}
      </svg>
      <span className="hidden sm:inline whitespace-nowrap">{text}</span>
    </span>
  );
}

// On / off for the weather background. Same button style as ThemeToggle.
export function WeatherFxToggle({ pref, onChange, withLabel = false, className = '' }) {
  const on = pref !== 'off';
  const label = on ? 'ปิดเอฟเฟกต์อากาศ' : 'เปิดเอฟเฟกต์อากาศ';
  return (
    <button
      type="button"
      onClick={() => onChange(on ? 'off' : 'on')}
      aria-pressed={on}
      aria-label={label}
      title={label}
      className={`cursor-pointer inline-flex items-center justify-center gap-2 min-h-11 min-w-11 rounded-md text-[var(--c-ink)] hover:bg-[var(--c-raised)] transition-colors duration-150 ${withLabel ? 'px-3 text-sm font-medium' : ''} ${className}`}
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5 shrink-0" aria-hidden="true">
        <path d="M7 18a4.5 4.5 0 0 1-.6-8.96 6 6 0 0 1 11.7 1.5A4 4 0 0 1 17 18H7z" />
        {!on && <path d="M3 3l18 18" />}
      </svg>
      {withLabel && label}
    </button>
  );
}
