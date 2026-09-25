// Friendly robot face for the floating "ask AI" button: round head with an antenna, blinking eyes,
// pink cheeks and a smile. Fixed colours on purpose, it always sits on the blue button.
export default function BotFace({ className = 'w-10 h-10' }) {
  return (
    <svg viewBox="0 0 48 48" className={className} aria-hidden="true">
      {/* antenna */}
      <line x1="24" y1="5" x2="24" y2="11" stroke="#ffffff" strokeWidth="2" strokeLinecap="round" />
      <circle cx="24" cy="5" r="2.6" fill="#fcd34d" className="bot-bulb" />
      {/* ears */}
      <rect x="4" y="21" width="4.5" height="10" rx="2.2" fill="#bfdbfe" />
      <rect x="39.5" y="21" width="4.5" height="10" rx="2.2" fill="#bfdbfe" />
      {/* head */}
      <rect x="8" y="11" width="32" height="29" rx="11" fill="#ffffff" />
      {/* face screen */}
      <rect x="12" y="16" width="24" height="18" rx="8" fill="#1e3a8a" />
      {/* eyes */}
      <g className="bot-eyes">
        <ellipse cx="19" cy="24" rx="2.6" ry="3" fill="#7dd3fc" />
        <ellipse cx="29" cy="24" rx="2.6" ry="3" fill="#7dd3fc" />
        <circle cx="19.9" cy="22.9" r="0.9" fill="#ffffff" />
        <circle cx="29.9" cy="22.9" r="0.9" fill="#ffffff" />
      </g>
      {/* cheeks */}
      <circle cx="15" cy="29.5" r="1.8" fill="#f9a8d4" opacity="0.85" />
      <circle cx="33" cy="29.5" r="1.8" fill="#f9a8d4" opacity="0.85" />
      {/* smile */}
      <path d="M20.5 29 q3.5 3.2 7 0" fill="none" stroke="#7dd3fc" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}
