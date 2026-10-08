// Collapsible block of layers in the map side panel; the header says how many of its layers are on,
// so a closed group still shows what is drawn on the map.
// One line about a NASA EONET event: wind (storms report knots), distance to Thailand and which way it moves
export const TREND_TH = { closer: 'กำลังเข้าใกล้ไทย', away: 'กำลังออกห่างจากไทย', steady: 'ระยะห่างจากไทยพอ ๆ เดิม' };
export function nasaEventLine(e) {
  const wind = e.unit === 'kts' && e.magnitude ? `ลม ${Math.round(e.magnitude * 1.852)} กม./ชม. · ` : '';
  const where = e.km_to_thailand ? `ห่างไทย ${e.km_to_thailand.toLocaleString()} กม.` : 'อยู่ในประเทศไทย';
  return `${wind}${where}${TREND_TH[e.trend] ? ` · ${TREND_TH[e.trend]}` : ''}`;
}
