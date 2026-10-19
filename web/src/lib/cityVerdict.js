// The home page's answer to "ตอนนี้ออกไปได้ไหม", made from the six checks by rules (no AI).
// Three answers plus "not known yet":
//   green   ออกได้            nothing to watch
//   yellow  ออกได้ แต่ระวัง     something to watch; the trip still works
//   red     รอก่อนถ้าไม่รีบ      the trip itself is hit: heavy traffic city-wide, or many flooded roads
//   neutral the data is not all in yet, and nothing to watch is known so far
// Only traffic and flooded roads can make the answer red. A check may still show red on its own row (many
// incidents), but it does not stop a trip by itself, so it only makes the answer yellow. A danger already known is
// shown at once, even while other checks are still loading.

export const FLOOD_ROADS_SEVERE = 10;   // flooded roads (BMA sensors, flood + slight) from which the answer is red

export const VERDICT_LABEL = {
  green: 'ออกได้',
  yellow: 'ออกได้ แต่ระวัง',
  red: 'รอก่อนถ้าไม่รีบ',
};

// items: the six checks [{ q, say, tone, known }]; trafficTone: the traffic check's tone; flooding: flooded roads
// now; avoid: up to two jammed road names
export function cityVerdict({ items, trafficTone, flooding = 0, avoid = [] }) {
  const care = [...items.filter((i) => i.known && i.tone === 'red'), ...items.filter((i) => i.known && i.tone === 'yellow')];   // red first
  const calm = items.filter((i) => i.known && !care.includes(i));
  const pending = items.filter((i) => !i.known);
  const avoidText = avoid.length ? avoid.slice(0, 2).join(' กับ') : null;
  const floodLine = `ถนนน้ำท่วม ${flooding} จุด ดูเส้นทางก่อนออก`;

  let tone;
  let headline;
  if (flooding >= FLOOD_ROADS_SEVERE || trafficTone === 'red') {
    tone = 'red';
    headline = flooding >= FLOOD_ROADS_SEVERE
      ? floodLine
      : avoidText ? `รถติดหนักหลายสาย เลี่ยง${avoidText}` : 'รถติดหนักหลายสาย';
  } else if (care.length) {
    tone = 'yellow';
    headline = flooding > 0
      ? floodLine
      : trafficTone === 'yellow'
        ? (avoidText ? `รถชะลอตัว เผื่อเวลา และเลี่ยง${avoidText}` : 'รถชะลอตัว เผื่อเวลาเดินทาง')
        : trafficTone === 'green' ? `รถคล่องตัว แต่มี ${care.length} เรื่องต้องระวัง` : `มี ${care.length} เรื่องต้องระวัง`;
  } else if (pending.length) {
    return {
      tone: 'neutral',
      label: calm.length ? 'ข้อมูลยังไม่ครบ' : 'กำลังโหลด',
      headline: 'กำลังรวมข้อมูลของเมือง ยังสรุปไม่ได้',
      detail: `ยังไม่มีข้อมูล: ${pending.map((i) => i.q).join(', ')}`,
      care, calm, pending,
    };
  } else {
    tone = 'green';
    headline = 'ทุกเรื่องปกติ เดินทางได้ตามปกติ';
  }

  const detail = [
    ...care.map((i) => i.say),
    ...(care.length && calm.length && !pending.length ? ['เรื่องอื่นปกติ'] : []),
    ...(pending.length ? [`ยังไม่มีข้อมูล: ${pending.map((i) => i.q).join(', ')}`] : []),
  ].join(' · ');
  return { tone, label: VERDICT_LABEL[tone], headline, detail, care, calm, pending };
}
