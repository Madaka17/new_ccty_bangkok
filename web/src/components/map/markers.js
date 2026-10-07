// Marker colours, shapes and the small text helpers of the traffic map's pins and popups.
// Pin color
export const PIN = '#2563eb';
export const PIN_COLOR = {
  กรุงเทพมหานคร: '#2563eb',
  นนทบุรี: '#0891b2',
  นครปฐม: '#059669',
  สมุทรปราการ: '#7c3aed',
  ปทุมธานี: '#d97706',
  ชลบุรี: '#ea580c',
  ฉะเชิงเทรา: '#4f46e5',
};
// Water layer. Two different measurements share it, so they get two different marker shapes:
//  * road sensors (BMA drainage, Bangkok only) - centimetres of water ON the road, a depth badge
//  * river / canal gauges (ThaiWater, whole metro area) - % of bank capacity, a round dot
export const FLOOD_STYLE = {
  flood: { color: '#dc2626', ring: 'rgba(220,38,38,.28)', label: 'น้ำท่วม' },
  slight: { color: '#f59e0b', ring: 'rgba(245,158,11,.28)', label: 'น้ำท่วมเล็กน้อย' },
  normal: { color: '#0ea5e9', ring: 'rgba(14,165,233,.18)', label: 'ปกติ' },
  offline: { color: '#94a3b8', ring: 'rgba(148,163,184,.18)', label: 'เครื่องวัดขัดข้อง' },
};
export const GAUGE_STYLE = {
  overflow: { color: '#dc2626', label: 'ล้นตลิ่ง' },
  high: { color: '#f59e0b', label: 'น้ำมาก' },
  normal: { color: '#0284c7', label: 'ปกติ' },
  low: { color: '#94a3b8', label: 'น้ำน้อย' },
};
// AI flood watch on the BMA cameras (flood_cam_service.py): a camera pill, the colour is what the AI saw
export const CAM_FLOOD_STYLE = {
  severe: { color: '#7f1d1d', label: 'น้ำท่วมหนัก' },
  flooded: { color: '#dc2626', label: 'น้ำท่วมถนน' },
  puddle: { color: '#f59e0b', label: 'น้ำขังเล็กน้อย' },
  none: { color: '#16a34a', label: 'ไม่มีน้ำท่วม' },
  unclear: { color: '#94a3b8', label: 'มองไม่ชัด' },
};
export const CAM_WET = ['severe', 'flooded', 'puddle'];
// Flood reports sent by the public from the Water Forecast map (user_reports.py)
export const USER_REPORT_COLOR = '#0891b2';
// Citizen flood reports (Traffy Fondue): a speech-bubble pin, hotter the fresher the report
export const REPORT_COLOR = '#7c3aed';
export const REPORT_FRESH_S = 3600;
// Flooded highways from the Department of Highways (HDMS): a road-sign pin, faded once the ticket is closed
export const HDMS_COLOR = '#be185d';
export const KIND_TH = { accident: 'อุบัติเหตุ', breakdown: 'รถเสีย' };
export const CLOSURE_COLOR = { closed: '#b91c1c', diversion: '#ea580c' };
export const closureTh = (c) => (c.kind === 'diversion' ? 'ปิดบางช่วง / เบี่ยงจราจร' : c.reason === 'flood' ? 'ถนนปิด (น้ำท่วม ผ่านไม่ได้)' : 'ถนนปิด');
export const sourceTh = (i) => (i.source === 'camera' ? 'กล้อง AI เห็น' : i.source === 'bma' ? 'ศูนย์จราจร กทม.' : 'ข่าวจราจร');
// "เขตวัฒนา กรุงเทพฯ" / "อ.เสนา จ.พระนครศรีอยุธยา", from the province and district the server found
export const placeTh = (i) => {
  if (!i.province) return '';
  const bkk = i.province === 'กรุงเทพมหานคร';
  return `${i.amphoe ? `${bkk ? 'เขต' : 'อ.'}${i.amphoe} ` : ''}${bkk ? 'กรุงเทพฯ' : `จ.${i.province}`}`;
};
export const TH_MON = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.'];
// Longdo 'YYYY-MM-DD HH:MM:SS' -> "4 ต.ค. 09:30 น."
export const feedTimeTh = (t) => {
  const d = t ? new Date(t.replace(' ', 'T')) : null;
  if (!d || Number.isNaN(d.getTime())) return '';
  return `${d.getDate()} ${TH_MON[d.getMonth()]} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')} น.`;
};
export const THAILAND = [[97.3, 5.6], [105.7, 20.5]];
export const NATION_FLOOD_COLOR = { road: '#0284c7', river: '#1e3a8a' };
// Flooded road: a sky-blue drop-shaped pin with waves; river over the bank: a navy square
export function nationFloodEl(f) {
  const el = document.createElement('button');
  el.type = 'button';
  el.className = 'cursor-pointer';
  el.setAttribute('aria-label', f.kind === 'river' ? 'แม่น้ำล้นตลิ่ง' : 'ถนนน้ำท่วม');
  const color = NATION_FLOOD_COLOR[f.kind];
  const shape = f.kind === 'river' ? 'border-radius:5px' : 'border-radius:999px 999px 999px 3px';
  el.style.cssText = `width:22px;height:22px;${shape};background:${color};border:2px solid #fff;box-shadow:0 1px 4px rgba(15,23,42,.35);color:#fff;font:700 13px/1 var(--font-sans);display:flex;align-items:center;justify-content:center;padding:0`;
  el.textContent = '≈';
  return el;
}
export const METRO_PROVINCES = ['กรุงเทพมหานคร', 'นนทบุรี', 'ปทุมธานี', 'สมุทรปราการ', 'นครปฐม', 'สมุทรสาคร'];
export const agoTh = (ts) => {
  const m = Math.round((Date.now() / 1000 - ts) / 60);
  return m < 1 ? 'เมื่อสักครู่' : m < 60 ? `${m} นาทีก่อน` : `${Math.round(m / 60)} ชม.ก่อน`;
};
export const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
// Closed road: a no-entry sign; diversion: an orange square with an arrow
export function closureEl(c) {
  const el = document.createElement('button');
  el.type = 'button';
  el.className = 'cursor-pointer';
  el.setAttribute('aria-label', closureTh(c));
  const color = CLOSURE_COLOR[c.kind];
  if (c.kind === 'diversion') {
    el.style.cssText = `width:24px;height:24px;border-radius:6px;background:${color};border:2px solid #fff;box-shadow:0 1px 4px rgba(15,23,42,.35);color:#fff;font:700 14px/1 var(--font-sans);display:flex;align-items:center;justify-content:center;padding:0`;
    el.textContent = '↪';
  } else {
    el.style.cssText = `width:26px;height:26px;border-radius:999px;background:${color};border:2px solid #fff;box-shadow:0 0 0 4px ${color}33,0 1px 4px rgba(15,23,42,.35);display:flex;align-items:center;justify-content:center;padding:0`;
    const bar = document.createElement('span');
    bar.style.cssText = 'display:block;width:13px;height:4px;border-radius:2px;background:#fff';
    el.appendChild(bar);
  }
  return el;
}
// Pulsing warning marker for an incident
export function incidentEl(kind) {
  const el = document.createElement('button');
  el.type = 'button';
  el.className = 'cursor-pointer incident-pin';
  el.setAttribute('aria-label', KIND_TH[kind] || 'เหตุบนถนน');
  const color = kind === 'breakdown' ? '#d97706' : '#dc2626';
  el.style.cssText = `width:30px;height:30px;border-radius:999px;background:${color};border:3px solid #fff;box-shadow:0 0 0 6px ${color}33,0 2px 8px rgba(15,23,42,.3);color:#fff;font-weight:700;font-size:16px;line-height:1;display:flex;align-items:center;justify-content:center;animation:incident-pulse 1.6s ease-out infinite`;
  el.textContent = '!';
  return el;
}
export function pinEl(color, active, floodRisk) {
  const el = document.createElement('button');
  el.type = 'button';
  el.className = 'cursor-pointer';
  if (floodRisk) {
    const borderCol = floodRisk.isOverflow ? '#ef4444' : '#f59e0b';
    const shadow = floodRisk.isOverflow
      ? '0 0 0 4px rgba(239,68,68,0.4), 0 2px 6px rgba(0,0,0,0.3)'
      : '0 0 0 3px rgba(245,158,11,0.4), 0 2px 6px rgba(0,0,0,0.3)';
    el.style.cssText = `width:22px;height:22px;border-radius:999px;background:${color};border:3px solid ${borderCol};box-shadow:${shadow};position:relative;${active ? 'outline:3px solid #0f172a;outline-offset:1px;' : ''}`;
    const badge = document.createElement('span');
    badge.textContent = '🌊';
    badge.style.cssText = 'position:absolute;top:-10px;right:-9px;font-size:11px;line-height:1;pointer-events:none;filter:drop-shadow(0 1px 1px rgba(0,0,0,0.4));';
    el.appendChild(badge);
  } else {
    el.style.cssText = `width:20px;height:20px;border-radius:999px;background:${color};border:3px solid #fff;box-shadow:0 1px 4px rgba(15,23,42,.3);${active ? 'outline:3px solid #0f172a;outline-offset:1px;' : ''}`;
  }
  return el;
}
