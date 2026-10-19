// How old one source's data is, for the small time under each home check. `limit` is how old the data may get
// before it counts as old for that source (each polls at its own pace); old data is said, never hidden.
// ts and limit in seconds.
export const FRESH_LIMIT = {
  traffic: 900,     // map colours every minute
  incident: 900,    // Longdo every minute
  water: 3600,      // gauges every 10-15 min, the summary every few minutes
  report: 1800,     // Traffy every 5 min
  weather: 3600,    // MET Norway every 10 min
  air: 7200,        // stations report once an hour
};

export function freshness(ts, limit, now = Date.now() / 1000) {
  if (!ts) return null;
  const s = Math.max(0, now - ts);
  const m = Math.round(s / 60);
  const text = m < 1 ? 'เมื่อสักครู่' : m < 60 ? `${m} นาทีก่อน` : `${Math.round(m / 60)} ชม.ก่อน`;
  return { text, stale: s > limit };
}
