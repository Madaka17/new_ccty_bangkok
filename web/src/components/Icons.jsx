// Soft, rounded illustrated icons. All share a 24x24 viewBox.
const base = { fill: 'none', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' };

export function FlowerIcon({ className = 'w-5 h-5' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <g fill="#d7ccef">
        <circle cx="12" cy="6.5" r="3.2" />
        <circle cx="17.5" cy="12" r="3.2" />
        <circle cx="12" cy="17.5" r="3.2" />
        <circle cx="6.5" cy="12" r="3.2" />
      </g>
      <circle cx="12" cy="12" r="2.6" fill="#edc55c" />
    </svg>
  );
}

export function HeartIcon({ filled = false, className = 'w-5 h-5' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <path
        d="M12 20.5s-7.5-4.6-7.5-10A4.3 4.3 0 0 1 12 8a4.3 4.3 0 0 1 7.5 2.5c0 5.4-7.5 10-7.5 10Z"
        fill={filled ? '#f5a88c' : 'rgba(250,205,188,0.35)'}
        stroke={filled ? '#e07a57' : '#f5a88c'}
        {...base}
      />
    </svg>
  );
}

export function CarIcon({ className = 'w-6 h-6' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <path d="M4 13.5 5.6 8.8A2 2 0 0 1 7.5 7.5h9a2 2 0 0 1 1.9 1.3L20 13.5v4a1 1 0 0 1-1 1h-1.5a1 1 0 0 1-1-1V17h-9v.5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-4Z" fill="#e3eedd" stroke="#6e9463" {...base} />
      <circle cx="8" cy="14" r="1.2" fill="#6e9463" />
      <circle cx="16" cy="14" r="1.2" fill="#6e9463" />
      <path d="M6.5 11h11" stroke="#9dbf92" {...base} />
    </svg>
  );
}

export function BikeIcon({ className = 'w-6 h-6' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <circle cx="6" cy="16" r="3.2" fill="#ebe5f7" stroke="#8a72c4" {...base} />
      <circle cx="18" cy="16" r="3.2" fill="#ebe5f7" stroke="#8a72c4" {...base} />
      <path d="M6 16 9.5 9.5H13l3.5 6.5M13 9.5l1.5-2.5H17" stroke="#8a72c4" {...base} />
      <path d="M9.5 9.5 12.5 16" stroke="#b5a3de" {...base} />
    </svg>
  );
}

export function TruckIcon({ className = 'w-6 h-6' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <path d="M3 8a1.5 1.5 0 0 1 1.5-1.5H14V16H3V8Z" fill="#fde6dd" stroke="#e07a57" {...base} />
      <path d="M14 10h3.2a1.5 1.5 0 0 1 1.2.6l2.3 3a1.5 1.5 0 0 1 .3.9V16H14v-6Z" fill="#facdbc" stroke="#e07a57" {...base} />
      <circle cx="7" cy="17" r="1.8" fill="#fff" stroke="#e07a57" {...base} />
      <circle cx="17.5" cy="17" r="1.8" fill="#fff" stroke="#e07a57" {...base} />
    </svg>
  );
}

export function BellIcon({ className = 'w-5 h-5' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <path d="M7 16V11a5 5 0 0 1 10 0v5l1.5 1.5H5.5L7 16Z" fill="#fbefd3" stroke="#c9a03a" {...base} />
      <path d="M10 19.5a2 2 0 0 0 4 0" stroke="#c9a03a" {...base} />
    </svg>
  );
}

export function SparkleIcon({ className = 'w-5 h-5' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <path d="M12 3.5c.6 4.2 2.3 5.9 6.5 6.5-4.2.6-5.9 2.3-6.5 6.5-.6-4.2-2.3-5.9-6.5-6.5 4.2-.6 5.9-2.3 6.5-6.5Z" fill="#f6dfa7" stroke="#c9a03a" {...base} />
      <path d="M18.5 15c.3 1.8 1 2.5 2.5 2.7-1.5.3-2.2 1-2.5 2.8-.3-1.8-1-2.5-2.5-2.8 1.5-.2 2.2-.9 2.5-2.7Z" fill="#fde6dd" stroke="#e07a57" strokeWidth="1.4" strokeLinejoin="round" />
    </svg>
  );
}

export function CameraIcon({ className = 'w-5 h-5' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <path d="M4 9.5A2.5 2.5 0 0 1 6.5 7H8l1.2-1.8h5.6L16 7h1.5A2.5 2.5 0 0 1 20 9.5v7a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 16.5v-7Z" fill="#ebe5f7" stroke="#8a72c4" {...base} />
      <circle cx="12" cy="13" r="3.2" fill="#fff" stroke="#8a72c4" {...base} />
    </svg>
  );
}

export function MapPinIcon({ className = 'w-5 h-5' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <path d="M12 21s-6-5.6-6-10.5a6 6 0 1 1 12 0C18 15.4 12 21 12 21Z" fill="#e3eedd" stroke="#6e9463" {...base} />
      <circle cx="12" cy="10.5" r="2.2" fill="#fff" stroke="#6e9463" {...base} />
    </svg>
  );
}

export function StarIcon({ className = 'w-4 h-4' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <path d="m12 3.8 2.5 5.2 5.7.7-4.2 3.9 1.1 5.6L12 16.5l-5.1 2.7 1.1-5.6-4.2-3.9 5.7-.7L12 3.8Z" fill="#f6dfa7" stroke="#c9a03a" {...base} />
    </svg>
  );
}

export function SettingsIcon({ className = 'w-5 h-5' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <circle cx="12" cy="12" r="3" fill="#fff" stroke="#6b6572" {...base} />
      <path d="M12 4.5v2M12 17.5v2M4.5 12h2M17.5 12h2M6.7 6.7l1.4 1.4M15.9 15.9l1.4 1.4M6.7 17.3l1.4-1.4M15.9 8.1l1.4-1.4" stroke="#9a94a1" {...base} />
    </svg>
  );
}

export function CloseIcon({ className = 'w-5 h-5' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <path d="m7 7 10 10M17 7 7 17" stroke="currentColor" {...base} />
    </svg>
  );
}

export function CheckIcon({ className = 'w-4 h-4' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <path d="m6 12.5 3.8 3.8L18 8" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
    </svg>
  );
}

export function RefreshIcon({ className = 'w-4 h-4' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <path d="M19 12a7 7 0 1 1-2-4.9M19 5v3.5h-3.5" stroke="currentColor" {...base} />
    </svg>
  );
}

export function ExpandIcon({ className = 'w-4 h-4' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <path d="M9 4.5H4.5V9M15 4.5h4.5V9M9 19.5H4.5V15M15 19.5h4.5V15" stroke="currentColor" {...base} />
    </svg>
  );
}

export function LocateIcon({ className = 'w-4 h-4' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <circle cx="12" cy="12" r="5" fill="#ebe5f7" stroke="#8a72c4" {...base} />
      <circle cx="12" cy="12" r="1.6" fill="#8a72c4" />
      <path d="M12 3v3M12 18v3M3 12h3M18 12h3" stroke="#8a72c4" {...base} />
    </svg>
  );
}

// Illustration for offline feed
export function OfflineIllustration({ className = 'w-40 h-28' }) {
  return (
    <svg viewBox="0 0 200 140" className={className} aria-hidden="true">
      <ellipse cx="100" cy="122" rx="70" ry="9" fill="#efeae4" />
      <path d="M40 56a20 20 0 0 1 38-8 16 16 0 0 1 30 4 18 18 0 0 1 32 14H40a12 12 0 0 1 0-10Z" fill="#fff" stroke="#d7ccef" strokeWidth="2.5" />
      <rect x="62" y="70" width="76" height="46" rx="14" fill="#ebe5f7" stroke="#b5a3de" strokeWidth="2.5" />
      <circle cx="100" cy="93" r="13" fill="#fff" stroke="#b5a3de" strokeWidth="2.5" />
      <path d="M94 93c1.5-3 3.5-3 5-3s3.5 0 5 3" stroke="#8a72c4" strokeWidth="2.5" strokeLinecap="round" fill="none" />
      <rect x="120" y="60" width="26" height="14" rx="7" fill="#f6dfa7" stroke="#c9a03a" strokeWidth="2" />
      <text x="133" y="70.5" textAnchor="middle" fontSize="9" fill="#a07e2b" fontFamily="Poppins, sans-serif">zzz</text>
      <circle cx="152" cy="40" r="6" fill="#facdbc" />
      <circle cx="46" cy="90" r="4" fill="#c8debf" />
    </svg>
  );
}
