// Helpers for the "ออกกี่โมงดี" card. Backend: /api/bma/best_time (hourly per-road car-count profiles).

export const LEVEL_TH = { free: 'คล่องตัว', moderate: 'ชะลอตัว', heavy: 'ติดขัด' };

const pad2 = (n) => String(n).padStart(2, '0');

// Bangkok is UTC+7 with no DST, so read the weekday from the shifted UTC clock, not the viewer's zone.
export function todayDayType(date = new Date()) {
  const bkk = new Date(date.getTime() + 7 * 3600 * 1000);
  const dow = bkk.getUTCDay();
  return dow === 0 || dow === 6 ? 'weekend' : 'workday';
}

// { from: 9, to: 10 } -> '09:00–10:00'
export function hourRange({ from, to }) {
  return `${pad2(from)}:00–${pad2(to)}:00`;
}
