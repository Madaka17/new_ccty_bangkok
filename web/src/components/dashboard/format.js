// Shared formatting helpers and status tokens for the dashboard.
// Status colours carry data meaning (traffic level); every other surface stays neutral slate.

export const STATUS = {
  green: { hex: '#059669', text: 'text-emerald-700', bg: 'bg-emerald-50', border: 'border-emerald-200', bar: 'bg-emerald-600' },
  yellow: { hex: '#d97706', text: 'text-amber-700', bg: 'bg-amber-50', border: 'border-amber-200', bar: 'bg-amber-500' },
  red: { hex: '#dc2626', text: 'text-red-700', bg: 'bg-red-50', border: 'border-red-200', bar: 'bg-red-600' },
  neutral: { hex: '#64748b', text: 'text-slate-600', bg: 'bg-slate-100', border: 'border-slate-200', bar: 'bg-slate-400' },
};

// Longdo road level text (Thai) -> status key
export const ROAD_LEVEL = { โล่ง: 'green', ปานกลาง: 'yellow', ติดขัด: 'red' };
// Camera AI level -> status key + label
export const AI_LEVEL = {
  free: { key: 'green', label: 'โล่ง' },
  moderate: { key: 'yellow', label: 'ปานกลาง' },
  heavy: { key: 'red', label: 'ติดขัด' },
};

export function flowLevel(flow) {
  if (flow == null) return { key: 'neutral', label: 'รอข้อมูล', hint: 'กำลังประมวลผลเส้นทางจราจร' };
  if (flow >= 75) return { key: 'green', label: 'คล่องตัว', hint: 'การจราจรไหลลื่น เดินทางได้ตามปกติ' };
  if (flow >= 45) return { key: 'yellow', label: 'ปานกลาง', hint: 'มีจุดชะลอตัวบางช่วง เผื่อเวลาเดินทาง' };
  return { key: 'red', label: 'หนาแน่น', hint: 'รถสะสมหลายจุด ตรวจสอบเส้นทางเลี่ยงก่อนออกเดินทาง' };
}

const THAI_MONTHS = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.'];
export const pad2 = (v) => String(v).padStart(2, '0');

export const fmtTime = (ts) => (ts ? `${pad2(new Date(ts * 1000).getHours())}:${pad2(new Date(ts * 1000).getMinutes())}` : '--:--');

export const fmtDay = (key) => {
  const d = new Date(key);
  return `${d.getDate()} ${THAI_MONTHS[d.getMonth()]}`;
};

export const fmtDateTime = (ts) => {
  if (!ts) return '';
  const d = new Date(ts * 1000);
  return `${d.getDate()} ${THAI_MONTHS[d.getMonth()]} ${fmtTime(ts)} น.`;
};

export function agoText(ts) {
  if (!ts) return 'ยังไม่ได้วัด';
  const m = Math.round((Date.now() / 1000 - ts) / 60);
  if (m < 1) return 'เมื่อสักครู่';
  if (m < 60) return `${m} นาทีก่อน`;
  const h = Math.floor(m / 60);
  return h < 24 ? `${h} ชม. ${m % 60 > 0 ? `${m % 60} นาที` : ''}ก่อน`.replace('  ', ' ') : `${Math.round(h / 24)} วันก่อน`;
}

export function fmtDuration(sec) {
  if (sec == null) return '';
  const m = Math.round(sec / 60);
  if (m < 1) return `${Math.round(sec)} วินาที`;
  if (m < 60) return `${m} นาที`;
  return `${Math.floor(m / 60)} ชม. ${m % 60} นาที`;
}

export const fmtNum = (n) => (n == null ? '–' : Number(n).toLocaleString('th-TH'));
