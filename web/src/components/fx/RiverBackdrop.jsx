// The page's sky and river, behind everything: three soft lights (canal teal, evening orange, river cyan) drifting slowly
// across the top, and the river's current flowing along the bottom of the screen. Decoration only: fixed,
// behind the content (z-index -1), never takes a tap, and stands still for "reduce motion" (index.css).
export default function RiverBackdrop() {
  return (
    <div className="river-backdrop" aria-hidden="true">
      <span className="river-glow river-glow-a" />
      <span className="river-glow river-glow-b" />
      <span className="river-glow river-glow-c" />
      <svg className="river-current" viewBox="0 0 1200 120" preserveAspectRatio="none">
        {/* two copies side by side: the band slides one copy's width and loops without a seam */}
        <g className="river-current-far">
          <path d="M0 70 C150 40 300 100 450 70 S750 40 900 70 S1050 100 1200 70 V120 H0Z" />
          <path transform="translate(1200 0)" d="M0 70 C150 40 300 100 450 70 S750 40 900 70 S1050 100 1200 70 V120 H0Z" />
        </g>
        <g className="river-current-near">
          <path d="M0 90 C200 70 400 110 600 90 S1000 70 1200 90 V120 H0Z" />
          <path transform="translate(1200 0)" d="M0 90 C200 70 400 110 600 90 S1000 70 1200 90 V120 H0Z" />
        </g>
      </svg>
    </div>
  );
}
