// Plain Thai names for the page and tab ids that the visitor stats report (telemetry `view`, e.g. "yolo:live").
// Kept apart from VisitorsPage.jsx so the labels can be tested without the page's module-load side effects.
import { PAGE_TITLES } from './navPages.js';

const PAGE_LABEL = {
  ...PAGE_TITLES, analytics: 'สถิติเมือง (หน้าเก่า)', 'bma-count': 'นับรถทุกกล้อง กทม.', helmet: 'คนไม่สวมหมวกกันน็อก', wrongway: 'รถขับย้อนศร',
};
// Tab ids of the pages (CameraAiPage, SafetyPage, WaterPage, DashboardPage, ...). An id not listed here shows only its page name.
const SUB_LABEL = {
  overview: 'รถติดตอนนี้', trend: 'แนวโน้ม', flood: 'น้ำท่วม', roads: 'ถนนน้ำท่วม', incidents: 'อุบัติเหตุและรถเสีย', 'bma-reports': 'ข่าวจากศูนย์ กทม.',
  safety: 'ความปลอดภัย', traffic: 'จราจร', density: 'ความหนาแน่น', accidents: 'อุบัติเหตุ', riskbkk: 'จุดเสี่ยง กทม.', visitors: 'ผู้เข้าใช้งาน',
  'road-risk': 'ถนนแต่ละสาย', situation: 'น้ำในเขื่อนทั่วประเทศ', north: 'น้ำเหนือ', watch: 'น้ำท่วมใน กทม.', shelter: 'จุดพักพิง', reports: 'เรื่องที่คนแจ้ง',
  agent: 'AI สรุปสถานการณ์', analysis: 'AI คาดการณ์รายโซน',
  live: 'AI นับรถสด', search: 'ค้นหากล้อง', bma: 'กล้อง กทม.', helmet: 'หมวกกันน็อก', wrongway: 'ขับย้อนศร',
  provinces: 'คาดการณ์น้ำท่วม', summary: 'สรุปสถานการณ์', parking: 'จุดจอดรถหนีน้ำ', events: 'ปิดถนน งานใหญ่',
};

// Base name, then " › " and the tab name when that tab has a label and is not the same words as the base
export function pageLabel(view) {
  const [base, sub] = view.split(':');
  const name = PAGE_LABEL[base] || base;
  const subName = sub && SUB_LABEL[sub];
  return subName && subName !== name ? `${name} › ${subName}` : name;
}
