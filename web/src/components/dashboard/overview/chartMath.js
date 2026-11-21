// Pure geometry for the overview charts: no DOM, no React.

// Top of a y axis: at least 4 and a multiple of 4, so four equal gridlines land on whole numbers.
export function niceMax(value) {
  const n = Number(value);
  if (!Number.isFinite(n) || n <= 0) return 4;
  return Math.max(4, Math.ceil(n / 4) * 4);
}

// Smooth path (Catmull-Rom as cubic Beziers) that passes through every point.
export function linePath(pts) {
  if (!pts.length) return '';
  let d = `M${pts[0].x},${pts[0].y}`;
  if (pts.length === 1) return d;
  for (let i = 0; i < pts.length - 1; i += 1) {
    const p0 = pts[i - 1] || pts[i];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[i + 2] || p2;
    const c1x = p1.x + (p2.x - p0.x) / 6;
    const c1y = p1.y + (p2.y - p0.y) / 6;
    const c2x = p2.x - (p3.x - p1.x) / 6;
    const c2y = p2.y - (p3.y - p1.y) / 6;
    d += ` C${c1x},${c1y} ${c2x},${c2y} ${p2.x},${p2.y}`;
  }
  return d;
}
