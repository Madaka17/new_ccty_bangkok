// Where the browser says we are, and how far off that may be.
// A phone answers from GPS within metres. A computer without GPS or Wi-Fi (on a LAN cable) only has its IP
// address, and that can be kilometres off, so every caller shows the accuracy circle and says how far off.

export const ROUGH_M = 200;   // worse than this: say so and let the person move the pin themselves

// GeoJSON polygon of a circle `meters` around lng/lat (64 points, good enough on a city map)
export function circlePolygon(lng, lat, meters) {
  const pts = [];
  const dLat = meters / 111320;
  const dLng = meters / (111320 * Math.cos((lat * Math.PI) / 180));
  for (let i = 0; i <= 64; i++) {
    const a = (i / 64) * 2 * Math.PI;
    pts.push([lng + dLng * Math.cos(a), lat + dLat * Math.sin(a)]);
  }
  return { type: 'Feature', geometry: { type: 'Polygon', coordinates: [pts] }, properties: {} };
}

export function accuracyText(m) {
  return m >= 1000 ? `~${(m / 1000).toFixed(m >= 10000 ? 0 : 1)} กม.` : `~${Math.round(m)} ม.`;
}

// The warning to show for a rough fix, or '' when it is good
export function roughWarning(m) {
  if (m == null || m <= ROUGH_M) return '';
  return `ตำแหน่งคลาดเคลื่อนได้ ${accuracyText(m)} (อุปกรณ์นี้ไม่มี GPS จึงใช้ตำแหน่งจากเครือข่าย)`;
}

// Draw (or move) the accuracy circle on a maplibre map, in its own source/layers
export function showAccuracy(map, lng, lat, meters, color = '#8a72c4') {
  const data = { type: 'FeatureCollection', features: [circlePolygon(lng, lat, meters)] };
  const src = map.getSource('me-accuracy');
  if (src) {
    src.setData(data);
    return;
  }
  map.addSource('me-accuracy', { type: 'geojson', data });
  map.addLayer({ id: 'me-accuracy-fill', type: 'fill', source: 'me-accuracy', paint: { 'fill-color': color, 'fill-opacity': 0.12 } });
  map.addLayer({ id: 'me-accuracy-line', type: 'line', source: 'me-accuracy', paint: { 'line-color': color, 'line-width': 1.5, 'line-opacity': 0.6 } });
}

// Frame the fix: close in for a precise one, the whole circle for a rough one
export function frameFix(map, lng, lat, meters, zoom = 16) {
  if (meters > ROUGH_M) {
    const c = circlePolygon(lng, lat, meters).geometry.coordinates[0];
    const lngs = c.map((p) => p[0]);
    const lats = c.map((p) => p[1]);
    map.fitBounds([[Math.min(...lngs), Math.min(...lats)], [Math.max(...lngs), Math.max(...lats)]], { padding: 40, maxZoom: zoom, duration: 800 });
  } else {
    map.easeTo({ center: [lng, lat], zoom, duration: 800 });
  }
}
