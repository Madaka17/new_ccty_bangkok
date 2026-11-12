// Left navigation, grouped by what the page is for. `hint` is the one-liner shown as the
// tooltip; the label is also the page's title in its header and the mobile top bar.
export const NAV_GROUPS = [
  {
    label: 'ตอนนี้',
    items: [
      { id: 'dashboard', label: 'ภาพรวม', hint: 'รถติดตรงไหน มีเหตุอะไรบนถนน และควรเลี่ยงทางไหน' },
      { id: 'map', label: 'แผนที่', hint: 'แผนที่รถติด กล้อง น้ำท่วม และจุดอันตราย' },
    ],
  },
  {
    label: 'เตือนภัย',
    items: [
      { id: 'alerts', label: 'ประกาศเตือน', hint: 'ประกาศเตือนภัย และตั้งให้เว็บเตือนเมื่อมีเหตุ' },
      { id: 'water', label: 'น้ำท่วม', hint: 'ระดับน้ำ น้ำเหนือ ถนนที่น้ำท่วม จุดพักพิง และ AI สรุปสถานการณ์' },
      { id: 'enviro', label: 'แผ่นดินไหว', hint: 'เฝ้าระวังและเตือนภัยแผ่นดินไหว' },
      { id: 'safety', label: 'จุดเสี่ยงอุบัติเหตุ', hint: 'จุดที่เกิดอุบัติเหตุบ่อย และจุดเสี่ยงในกรุงเทพฯ' },
    ],
  },
  {
    label: 'กล้อง',
    items: [
      { id: 'cameras', label: 'ดูกล้องสด', hint: 'เลือกกล้องมาดูภาพสดพร้อมกันได้ 9 กล้อง' },
      { id: 'yolo', label: 'กล้อง AI', hint: 'AI นับรถจากกล้อง ค้นหากล้อง และตรวจคนไม่สวมหมวกกันน็อกหรือขับย้อนศร' },
    ],
  },
  {
    label: 'แจ้งและช่วยเหลือ',
    items: [
      { id: 'report', label: 'แจ้งน้ำท่วม', hint: 'แจ้งน้ำท่วมกับ BKK StreetSmart แนบรูป รายละเอียด และปักหมุดตำแหน่ง' },
      { id: 'ai', label: 'ถาม AI', hint: 'ถาม AI เรื่องรถติด น้ำท่วม หรือเรื่องทั่วไป' },
    ],
  },
  {
    label: 'เกี่ยวกับ',
    items: [
      { id: 'visitors', label: 'สถิติผู้ใช้', hint: 'มีคนใช้เว็บกี่คน และดูหน้าไหนมากที่สุด' },
    ],
  },
];

// Pages reached from the home screen (PM2.5 tile, "เขตของฉัน" button) stay out of the menu but keep their titles
export const PAGE_TITLES = {
  ...Object.fromEntries(NAV_GROUPS.flatMap((g) => g.items).map((i) => [i.id, i.label])),
  air: 'ฝุ่น PM2.5',
  district: 'เขตของฉัน',
};

// One-liners per page for tooltips and page search
export const PAGE_HINTS = {
  ...Object.fromEntries(NAV_GROUPS.flatMap((g) => g.items).map((i) => [i.id, i.hint])),
  air: 'ค่าฝุ่น PM2.5 ตอนนี้',
  district: 'ข่าวสารเขตที่คุณเลือก',
};
