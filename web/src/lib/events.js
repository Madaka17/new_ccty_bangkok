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

export const PARTIAL_NOTE = 'ข้อมูลบางส่วนยังไม่มา รายการอาจไม่ครบ';
export const UNKNOWN_EMPTY = 'ยังไม่มีข้อมูลครบ';
export const NONE_LISTED = 'ไม่มีรายการ';

// True when the calendar says some feed is not ok (sources_ok value false). A missing map counts as ok.
export const anySourceNotOk = (sourcesOk) => Object.values(sourcesOk || {}).some((v) => v === false);

// The text for an empty section: while a feed is not ok, "none" would be a lie, so say the data is missing.
export const emptySectionText = (sourcesOk) => (anySourceNotOk(sourcesOk) ? UNKNOWN_EMPTY : NONE_LISTED);
export const sourceLabel = (source) => SOURCE_LABEL[source] || 'ประกาศ';

// Bangkok wall clock of an epoch-seconds value, read through UTC so the browser's own zone does not matter
function bkkParts(epoch) {
  const d = new Date((epoch + BKK_OFFSET_S) * 1000);
  return {
    day: d.getUTCDate(),
    month: d.getUTCMonth(),
    year: d.getUTCFullYear(),
    dayKey: Math.floor((epoch + BKK_OFFSET_S) / 86400),
    hh: String(d.getUTCHours()).padStart(2, '0'),
    mm: String(d.getUTCMinutes()).padStart(2, '0'),
  };
}

// "18 ต.ค."; a date outside the current Bangkok year gets the Buddhist-era short year: "18 ม.ค. 70"
const dayText = (p, nowYear) => {
  const base = `${p.day} ${TH_MON[p.month]}`;
  return p.year === nowYear ? base : `${base} ${String((p.year + 543) % 100).padStart(2, '0')}`;
};

// A Thai short time range: "18 ต.ค. 06:00 – 12:00", "18 ต.ค. – 20 ต.ค.", "จนกว่าจะประกาศ".
// now (epoch seconds) decides the current year, so a date in another year shows its year.
export function timeRange(start, end, now = Date.now() / 1000) {
  if (start == null && end == null) return 'ไม่ระบุเวลา';
  if (end == null) return 'จนกว่าจะประกาศ';
  const nowYear = bkkParts(now).year;
  const e = bkkParts(end);
  if (start == null) return `ถึง ${dayText(e, nowYear)} ${e.hh}:${e.mm}`;
  const s = bkkParts(start);
  if (s.dayKey === e.dayKey) return `${dayText(s, nowYear)} ${s.hh}:${s.mm} – ${e.hh}:${e.mm}`;
  return `${dayText(s, nowYear)} – ${dayText(e, nowYear)}`;
}

// Longdo closures and diversions are already drawn by the closures layer (ถนนปิด), so the calendar skips them
export function isDuplicateOfClosure(item) {
  return item.source === 'longdo' && ['closed', 'closure', 'diversion'].includes(item.kind);
}

// A datetime-local value ("2026-10-18T06:00") read as Bangkok time, as epoch seconds; null when it is not a date
export function bangkokInputToEpoch(value) {
  if (!value) return null;
  const ms = Date.parse(`${value}:00+07:00`);
  return Number.isNaN(ms) ? null : Math.floor(ms / 1000);
}

// Calendar items with coordinates from the four buckets, each item once (by id)
export function mapItemsWithCoords(calendar, { skipClosures = false } = {}) {
  if (!calendar) return [];
  const seen = new Set();
  const out = [];
  for (const bucket of ['ongoing', 'today', 'tomorrow', 'week']) {
    for (const item of calendar[bucket] || []) {
      if (item.lat == null || item.lng == null || seen.has(item.id)) continue;
      if (skipClosures && isDuplicateOfClosure(item)) continue;
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
