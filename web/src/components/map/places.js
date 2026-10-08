// Place labels on the traffic map (the "อาคารและสถานที่" layer): which OpenMapTiles POIs get a label, and in what order.
// OpenMapTiles poi classes worth a label, with an icon and a Thai name
export const POI_KIND = {
  hospital: ['🏥', 'โรงพยาบาล', '#dc2626'], clinic: ['🏥', 'คลินิก', '#dc2626'], doctors: ['🏥', 'คลินิก', '#dc2626'], pharmacy: ['💊', 'ร้านขายยา', '#dc2626'],
  school: ['🏫', 'โรงเรียน', '#2563eb'], college: ['🏫', 'วิทยาลัย', '#2563eb'], university: ['🎓', 'มหาวิทยาลัย', '#2563eb'], kindergarten: ['🏫', 'อนุบาล', '#2563eb'],
  shop: ['🛍️', 'ร้านค้า', '#7c3aed'], grocery: ['🛒', 'ซูเปอร์มาร์เก็ต', '#7c3aed'], mall: ['🏬', 'ห้างสรรพสินค้า', '#7c3aed'], department_store: ['🏬', 'ห้างสรรพสินค้า', '#7c3aed'],
  town_hall: ['🏛️', 'หน่วยงานราชการ', '#b45309'], townhall: ['🏛️', 'หน่วยงานราชการ', '#b45309'], police: ['🚓', 'สถานีตำรวจ', '#b45309'], fire_station: ['🚒', 'สถานีดับเพลิง', '#b45309'], post: ['📮', 'ไปรษณีย์', '#b45309'], bank: ['🏦', 'ธนาคาร', '#b45309'], embassy: ['🏛️', 'สถานทูต', '#b45309'],
  place_of_worship: ['🛕', 'ศาสนสถาน', '#d97706'],
  railway: ['🚉', 'สถานีรถไฟ', '#059669'], bus: ['🚌', 'ป้ายรถเมล์', '#059669'], ferry_terminal: ['⛴️', 'ท่าเรือ', '#059669'], airport: ['✈️', 'สนามบิน', '#059669'], aerodrome: ['✈️', 'สนามบิน', '#059669'],
  lodging: ['🏨', 'โรงแรม', '#0891b2'], hotel: ['🏨', 'โรงแรม', '#0891b2'],
  park: ['🌳', 'สวนสาธารณะ', '#16a34a'], stadium: ['🏟️', 'สนามกีฬา', '#16a34a'], sports_centre: ['🏟️', 'ศูนย์กีฬา', '#16a34a'], golf: ['⛳', 'สนามกอล์ฟ', '#16a34a'],
  museum: ['🏛️', 'พิพิธภัณฑ์', '#9333ea'], attraction: ['📍', 'สถานที่ท่องเที่ยว', '#9333ea'], monument: ['🗿', 'อนุสาวรีย์', '#9333ea'], theatre: ['🎭', 'โรงละคร', '#9333ea'], cinema: ['🎬', 'โรงภาพยนตร์', '#9333ea'],
  parking: ['🅿️', 'ที่จอดรถ', '#475569'], fuel: ['⛽', 'ปั๊มน้ำมัน', '#475569'], charging_station: ['🔌', 'จุดชาร์จ EV', '#475569'],
  market: ['🧺', 'ตลาด', '#ea580c'],
};
export const POI_MAX = 70;
export const POI_MIN_ZOOM = 15;
// Label priority: public buildings first, then services, shops last (and capped) so a mall's
// tenants do not crowd out the hospital next door
export const POI_TIER = (cls) => (['shop', 'grocery', 'clothing_store', 'department_store', 'lodging', 'hotel', 'parking', 'fuel', 'charging_station', 'bank', 'pharmacy', 'clinic', 'doctors'].includes(cls) ? 2
  : ['mall', 'market', 'park', 'museum', 'attraction', 'monument', 'theatre', 'cinema', 'stadium', 'sports_centre', 'golf', 'post', 'embassy'].includes(cls) ? 1 : 0);
export const POI_TIER_MAX = [POI_MAX, 30, 15];
export const poiKindOf = (p) => POI_KIND[p.class] || POI_KIND[p.subclass];
export const poiTierOf = (p) => POI_TIER(POI_KIND[p.class] ? p.class : p.subclass);
