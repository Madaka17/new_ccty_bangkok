// Building shadows for the map's shade view (like Shade Walk): where the sun is at a given time, and the
// ground each building shades. Sun position follows the SunCalc formulas (Vladimir Agafonkin, BSD);
// a shadow is the convex hull of the footprint and the footprint moved away from the sun by
// height / tan(altitude), which is exact for convex buildings and close enough for the rest.

const RAD = Math.PI / 180;
const DAY_MS = 86400000;
const J1970 = 2440588;
const J2000 = 2451545;
const OBLIQUITY = RAD * 23.4397;
const M_PER_DEG = 111320;
const MAX_SHADOW_M = 400; // a low sun throws shadows across whole blocks; cap them

/** Sun altitude and azimuth (degrees; azimuth clockwise from north) at `date` for lat/lng. */
export function sunPosition(date, lat, lng) {
  const d = date.valueOf() / DAY_MS - 0.5 + J1970 - J2000;
  const M = RAD * (357.5291 + 0.98560028 * d);
  const C = RAD * (1.9148 * Math.sin(M) + 0.02 * Math.sin(2 * M) + 0.0003 * Math.sin(3 * M));
  const L = M + C + RAD * 102.9372 + Math.PI;
  const dec = Math.asin(Math.sin(L) * Math.sin(OBLIQUITY));
  const ra = Math.atan2(Math.sin(L) * Math.cos(OBLIQUITY), Math.cos(L));
  const H = RAD * (280.16 + 360.9856235 * d) + RAD * lng - ra;
  const phi = RAD * lat;
  const altitude = Math.asin(Math.sin(phi) * Math.sin(dec) + Math.cos(phi) * Math.cos(dec) * Math.cos(H));
  const azSouth = Math.atan2(Math.sin(H), Math.cos(H) * Math.sin(phi) - Math.tan(dec) * Math.cos(phi));
  return { altitude: altitude / RAD, azimuth: ((azSouth / RAD + 180) % 360 + 360) % 360 };
}

// Andrew's monotone chain; points are [x, y]
function hull(pts) {
  const p = pts.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  if (p.length < 3) return p;
  const cross = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lower = [];
  for (const q of p) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], q) <= 0) lower.pop();
    lower.push(q);
  }
  const upper = [];
  for (let i = p.length - 1; i >= 0; i--) {
    const q = p[i];
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], q) <= 0) upper.pop();
    upper.push(q);
  }
  return lower.slice(0, -1).concat(upper.slice(0, -1));
}

/**
 * Shadow polygons for building features (GeoJSON Polygon / MultiPolygon with render_height /
 * render_min_height, as in the OpenMapTiles building layer). Returns a FeatureCollection, empty when
 * the sun is down.
 */
export function buildingShadows(features, sun) {
  const out = [];
  if (!sun || sun.altitude <= 0.5) return { type: 'FeatureCollection', features: out };
  const tanAlt = Math.tan(sun.altitude * RAD);
  const az = sun.azimuth * RAD;
  // unit vector pointing away from the sun, in metres east / north
  const ux = -Math.sin(az);
  const uy = -Math.cos(az);
  for (const f of features) {
    const g = f.geometry;
    if (!g) continue;
    const h = Number(f.properties?.render_height ?? 8);
    const base = Number(f.properties?.render_min_height ?? 0);
    if (!(h > 0) || base > 0) continue; // a raised part (skybridge, overhang) is left out
    const len = Math.min(MAX_SHADOW_M, h / tanAlt);
    const rings = g.type === 'Polygon' ? [g.coordinates[0]] : g.type === 'MultiPolygon' ? g.coordinates.map((p) => p[0]) : [];
    for (const ring of rings) {
      if (!ring || ring.length < 3) continue;
      const lat = ring[0][1];
      const dLng = (ux * len) / (M_PER_DEG * Math.cos(lat * RAD));
      const dLat = (uy * len) / M_PER_DEG;
      const pts = [];
      for (const [x, y] of ring) {
        pts.push([x, y], [x + dLng, y + dLat]);
      }
      const h2 = hull(pts);
      if (h2.length >= 3) {
        out.push({ type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [[...h2, h2[0]]] } });
      }
    }
  }
  return { type: 'FeatureCollection', features: out };
}
