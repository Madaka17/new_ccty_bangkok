// PM2.5 helpers for the air page. Breakpoints mirror the PCD bands; labels and colours mirror
// backend/water/air_service.py LEVELS, so the page never invents a colour.
const BANGKOK = 'กรุงเทพมหานคร';

const LEVELS = {
  very_good: { label: 'ดีมาก', color: '#3BA0FF' },
  good: { label: 'ดี', color: '#4CC74A' },
  moderate: { label: 'ปานกลาง', color: '#FFD400' },
  unhealthy: { label: 'เริ่มมีผลต่อสุขภาพ', color: '#FF8C00' },
  very_unhealthy: { label: 'มีผลต่อสุขภาพ', color: '#E3272C' },
};

const ADVICE = {
  very_good: 'อากาศดี ทำกิจกรรมนอกบ้านได้ตามปกติ',
  good: 'อากาศดี ทำกิจกรรมนอกบ้านได้ตามปกติ',
  moderate: 'ทำกิจกรรมนอกบ้านได้ เด็ก ผู้สูงอายุ และคนที่แพ้ง่ายควรสังเกตอาการ',
  unhealthy: 'ควรใส่หน้ากาก N95 เมื่ออยู่นอกบ้าน และลดเวลาอยู่กลางแจ้ง',
  very_unhealthy: 'ควรอยู่ในอาคาร ปิดหน้าต่าง ถ้าต้องออกนอกบ้านให้ใส่หน้ากาก N95',
};

// PM2.5 in µg/m³ -> { level, label, color }
export function band(pm25) {
  const level = pm25 <= 15 ? 'very_good' : pm25 <= 25 ? 'good' : pm25 <= 37.5 ? 'moderate' : pm25 <= 75 ? 'unhealthy' : 'very_unhealthy';
  return { level, ...LEVELS[level] };
}

const validPm = (v) => typeof v === 'number' && Number.isFinite(v);

// Mean PM2.5 over the Bangkok stations only (other provinces are ignored); null when there is none
export function bkkAverage(items) {
  const vals = (items || []).filter((s) => s?.province === BANGKOK && validPm(s.pm25)).map((s) => s.pm25);
  if (!vals.length) return null;
  const pm25 = Math.round((vals.reduce((a, b) => a + b, 0) / vals.length) * 10) / 10;
  return { pm25, ...band(pm25) };
}

// Bangkok districts by mean PM2.5, highest first. `district` is the word after the last เขต;
// areas without เขต are skipped.
export function districtRanking(items) {
  const groups = new Map();
  for (const s of items || []) {
    if (s?.province !== BANGKOK || !validPm(s.pm25) || !s.area) continue;
    const found = [...s.area.matchAll(/เขต\s*([฀-๿]+)/g)].pop();
    if (!found) continue;
    const district = found[1];
    const g = groups.get(district) || { sum: 0, points: 0 };
    g.sum += s.pm25;
    g.points += 1;
    groups.set(district, g);
  }
  return [...groups.entries()]
    .map(([district, g]) => {
      const pm25 = Math.round((g.sum / g.points) * 10) / 10;
      return { district, pm25, points: g.points, ...band(pm25) };
    })
    .sort((a, b) => b.pm25 - a.pm25 || a.district.localeCompare(b.district, 'th'));
}

// What to do outside today, by level. Unknown level -> ''
export function airAdvice(level) {
  return ADVICE[level] ?? '';
}
