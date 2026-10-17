// Road-closure and big-event calendar: Thai labels, Bangkok-time ranges and the map hand-off.
// Times in items are epoch seconds (or null); Bangkok is UTC+7 with no daylight saving.

const KIND_LABEL = {
  closure: 'ปิดถนน',
  diversion: 'เบี่ยงจราจร',
  event: 'งานใหญ่',
  run: 'งานวิ่ง',
  concert: 'คอนเสิร์ต',
  ceremony: 'พิธี / ขบวน',
};

const SOURCE_LABEL = {
  team: 'ทีมงาน BKK StreetSmart',
  longdo: 'Longdo Traffic',
  bma: 'ศูนย์จราจร กทม.',
  bma_bulletin: 'ประกาศศูนย์จราจร กทม.',
};

const TH_MON = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.'];
const BKK_OFFSET_S = 7 * 3600;

export const kindLabel = (kind) => KIND_LABEL[kind] || 'ประกาศ';
export const sourceLabel = (source) => SOURCE_LABEL[source] || 'ประกาศ';

// Bangkok wall clock of an epoch-seconds value, read through UTC so the browser's own zone does not matter
function bkkParts(epoch) {
  const d = new Date((epoch + BKK_OFFSET_S) * 1000);
  return {
    day: d.getUTCDate(),
    month: d.getUTCMonth(),
    dayKey: Math.floor((epoch + BKK_OFFSET_S) / 86400),
    hh: String(d.getUTCHours()).padStart(2, '0'),
    mm: String(d.getUTCMinutes()).padStart(2, '0'),
  };
}

const dayText = (p) => `${p.day} ${TH_MON[p.month]}`;

// A Thai short time range: "18 ต.ค. 06:00 – 12:00", "18 ต.ค. – 20 ต.ค.", "จนกว่าจะประกาศ"
export function timeRange(start, end) {
  if (start == null && end == null) return 'ไม่ระบุเวลา';
  if (end == null) return 'จนกว่าจะประกาศ';
  const e = bkkParts(end);
  if (start == null) return `ถึง ${dayText(e)} ${e.hh}:${e.mm}`;
  const s = bkkParts(start);
  if (s.dayKey === e.dayKey) return `${dayText(s)} ${s.hh}:${s.mm} – ${e.hh}:${e.mm}`;
  return `${dayText(s)} – ${dayText(e)}`;
}

// A datetime-local value ("2026-10-18T06:00") read as Bangkok time, as epoch seconds; null when it is not a date
export function bangkokInputToEpoch(value) {
  if (!value) return null;
  const ms = Date.parse(`${value}:00+07:00`);
  return Number.isNaN(ms) ? null : Math.floor(ms / 1000);
}

// Calendar items with coordinates from the four buckets, each item once (by id)
export function mapItemsWithCoords(calendar) {
  if (!calendar) return [];
  const seen = new Set();
  const out = [];
  for (const bucket of ['ongoing', 'today', 'tomorrow', 'week']) {
    for (const item of calendar[bucket] || []) {
      if (item.lat == null || item.lng == null || seen.has(item.id)) continue;
      seen.add(item.id);
      out.push(item);
    }
  }
  return out;
}

// Map layer hand-off: the dashboard asks for a layer, and the map page turns it on when it mounts.
// Storage can throw (private window), so every access is guarded.
const MAP_LAYER_KEY = 'bkk-map-layer-request';

export function requestMapLayer(layer) {
  try {
    sessionStorage.setItem(MAP_LAYER_KEY, layer);
  } catch {}
}

export function readMapLayerRequest() {
  try {
    return sessionStorage.getItem(MAP_LAYER_KEY) || '';
  } catch {
    return '';
  }
}

export function clearMapLayerRequest() {
  try {
    sessionStorage.removeItem(MAP_LAYER_KEY);
  } catch {}
}
