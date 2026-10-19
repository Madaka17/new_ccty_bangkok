// Traffy flood reports, kept to the ones that say the water is there now (the server's report_kind:
// backend/water/flood_feeds.py). Aid requests for a past flood ("เยียวยา", the ทางรัฐ app), "it floods when it
// rains", what a flood left behind and drain or road complaints are left out of every list, pin and count, and
// their number rides along as `left_out` so a page can say so. An older server without kinds keeps everything.
export function waterNow(reports) {
  if (!reports) return reports;
  const all = reports.items || [];
  const items = all.filter((i) => !i.kind || i.kind === 'water');
  return { ...reports, items, total: items.length, left_out: all.length - items.length };
}

// One line for a page under its report list, or null when nothing was left out
export function leftOutNote(reports) {
  const n = reports?.left_out || 0;
  return n ? `ไม่นับอีก ${n} เรื่องที่ไม่ใช่น้ำท่วมตอนนี้ เช่น ขอเงินเยียวยา ท่อตัน ถนนชำรุด` : null;
}
