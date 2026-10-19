// Three of the home page's six checks, as pure functions of the API answers, so their scope and thresholds are
// tested (lib/cityChecks.test.js). Each returns { tone, status } plus the counts the summary needs.
// tone: green = fine, yellow = watch, red = act, neutral = no data yet.

export const BANGKOK = 'กรุงเทพมหานคร';
// Accidents and breakdowns Longdo / the camera AI list for the whole city at once; Bangkok always has a few
export const INCIDENTS_RED = 8;

const WATCH_RANK = { green: 0, yellow: 1, orange: 2, red: 3 };

// Rain and water in Bangkok. Flooded roads come from the BMA drainage sensors (`flood`, ~250 stations); ThaiWater
// relays only about 107 of them, so it is the fallback. River gauges and rain stations cover Bangkok and the
// provinces around it: only Bangkok's own count toward the tone, the rest are named as ปริมณฑล.
// The rain-watch zones (green / yellow / orange / red, the worst one leads) also carry tomorrow's storm.
export function waterCheck(water, flood) {
  const roads = water?.flood_roads;
  const flooding = flood
    ? (flood.counts?.flood || 0) + (flood.counts?.slight || 0)
    : (roads?.flooding || 0) + (roads?.slight || 0);
  if (!water && !flooding) return { tone: 'neutral', status: 'กำลังโหลด', flooding, known: false };

  const river = water?.river || [];
  const bkkOverflow = river.filter((r) => r.province === BANGKOK && r.level === 'overflow').length;
  const nearOverflow = river.filter((r) => r.province !== BANGKOK && r.level === 'overflow').length;
  const heavyRain = (water?.ntw?.rain || []).filter((r) => r.province === BANGKOK && (r.level === 'heavy' || r.level === 'extreme')).length;
  // Bangkok's own zones (ids bkk_*) decide; the provinces around only when no Bangkok zone came
  const all = water?.weather || [];
  const own = all.filter((z) => String(z.id || '').startsWith('bkk'));
  const zones = own.length ? own : all;
  const worst = zones.reduce((w, z) => ((WATCH_RANK[z.watch] ?? 0) > (WATCH_RANK[w?.watch] ?? -1) ? z : w), null);
  const watch = worst?.watch || 'green';

  let tone = 'green';
  let status = 'ปกติ';
  if (flooding > 0) {
    tone = 'red';
    status = `ถนนน้ำท่วม ${flooding} จุด`;
  } else if (watch === 'red') {
    tone = 'red';
    status = `เตือนภัย ${worst.name}`;
  } else if (bkkOverflow > 0) {
    tone = 'yellow';
    status = `น้ำล้นตลิ่ง ${bkkOverflow} จุด`;
  } else if (heavyRain > 0) {
    tone = 'yellow';
    status = `ฝนหนัก ${heavyRain} จุด`;
  } else if (watch === 'orange' || watch === 'yellow') {
    tone = 'yellow';
    status = worst.storm_at ? `ฝนฟ้าคะนอง ${worst.storm_at}` : `เฝ้าระวังฝน ${worst.name}`;
  } else if (nearOverflow > 0) {
    status = `กทม. ปกติ · ปริมณฑลน้ำล้นตลิ่ง ${nearOverflow} จุด`;
  }
  return { tone, status, flooding, bkkOverflow, nearOverflow, heavyRain, watch, known: true };
}

// Accidents and breakdowns, counted apart. A Longdo "คืบหน้า…" item is news about an incident already listed and
// is not counted twice.
export function incidentCheck(incidents) {
  if (!incidents) return { tone: 'neutral', status: 'กำลังโหลด', total: 0, known: false };
  const all = [...(incidents.camera || []), ...(incidents.longdo || [])];
  const titles = new Set(all.map((i) => i.title));
  const seen = all.filter((i) => !(/^คืบหน้า\s*/.test(i.title || '') && titles.has((i.title || '').replace(/^คืบหน้า\s*/, ''))));
  const accidents = seen.filter((i) => i.kind !== 'breakdown').length;
  const breakdowns = seen.length - accidents;
  const total = seen.length;
  const tone = total === 0 ? 'green' : total >= INCIDENTS_RED ? 'red' : 'yellow';
  const status = total === 0
    ? 'ไม่มีเหตุ'
    : [accidents ? `อุบัติเหตุ ${accidents}` : null, breakdowns ? `รถเสีย ${breakdowns}` : null].filter(Boolean).join(' · ');
  return { tone, status, total, accidents, breakdowns, known: true };
}

// People on Traffy who say the water is there now (the server's report_kind). Aid requests for a past flood,
// "it floods when it rains" and drain or road complaints are not counted. An older server without `water_now`
// counts every report.
export function waterReportCount(traffy) {
  if (!traffy?.updated_at) return null;
  if (traffy.water_now != null) return traffy.water_now;
  return (traffy.items || []).filter((i) => !i.kind || i.kind === 'water').length;
}
