import { describe, expect, test } from 'vitest';
import { cityVerdict, FLOOD_ROADS_SEVERE } from './cityVerdict.js';

const check = (q, tone, known = true) => ({ q, say: `${q} ${tone}`, tone, known });
const allFine = () => [check('รถติดไหม', 'green'), check('อุบัติเหตุ', 'green'), check('ฝนและน้ำ', 'green'),
  check('คนแจ้งน้ำท่วม', 'green'), check('อากาศ', 'green'), check('ฝุ่น', 'green')];

describe('cityVerdict', () => {
  test('every check fine: go', () => {
    const v = cityVerdict({ items: allFine(), trafficTone: 'green' });
    expect(v.tone).toBe('green');
    expect(v.label).toBe('ออกได้');
    expect(v.headline).toBe('ทุกเรื่องปกติ เดินทางได้ตามปกติ');
  });

  test('a red row that does not stop a trip (many flood reports) only makes it yellow', () => {
    const items = allFine();
    items[3] = check('คนแจ้งน้ำท่วม', 'red');
    const v = cityVerdict({ items, trafficTone: 'green' });
    expect(v.tone).toBe('yellow');
    expect(v.label).toBe('ออกได้ แต่ระวัง');
    expect(v.headline).toBe('รถคล่องตัว แต่มี 1 เรื่องต้องระวัง');
  });

  test('heavy traffic city-wide: wait if you can, naming the roads to avoid', () => {
    const items = allFine();
    items[0] = check('รถติดไหม', 'red');
    const v = cityVerdict({ items, trafficTone: 'red', avoid: ['พระราม 4', 'สุขุมวิท', 'ลาดพร้าว'] });
    expect(v.tone).toBe('red');
    expect(v.label).toBe('รอก่อนถ้าไม่รีบ');
    expect(v.headline).toBe('รถติดหนักหลายสาย เลี่ยงพระราม 4 กับสุขุมวิท');
  });

  test('many flooded roads: red; a few: yellow, both name the count', () => {
    const items = allFine();
    items[2] = check('ฝนและน้ำ', 'red');
    expect(cityVerdict({ items, trafficTone: 'green', flooding: FLOOD_ROADS_SEVERE }).tone).toBe('red');
    const few = cityVerdict({ items, trafficTone: 'green', flooding: 3 });
    expect(few.tone).toBe('yellow');
    expect(few.headline).toBe('ถนนน้ำท่วม 3 จุด ดูเส้นทางก่อนออก');
  });

  test('missing data is never shown as fine', () => {
    const items = allFine();
    items[5] = check('ฝุ่น', 'neutral', false);
    const v = cityVerdict({ items, trafficTone: 'green' });
    expect(v.tone).toBe('neutral');
    expect(v.label).toBe('ข้อมูลยังไม่ครบ');
    expect(v.detail).toBe('ยังไม่มีข้อมูล: ฝุ่น');
  });

  test('a danger already known shows at once, even while other checks load', () => {
    const items = allFine();
    items[1] = check('อุบัติเหตุ', 'yellow');
    items[5] = check('ฝุ่น', 'neutral', false);
    const v = cityVerdict({ items, trafficTone: 'green' });
    expect(v.tone).toBe('yellow');
    expect(v.detail).toBe('อุบัติเหตุ yellow · ยังไม่มีข้อมูล: ฝุ่น');
  });

  test('nothing loaded yet', () => {
    const items = allFine().map((i) => ({ ...i, tone: 'neutral', known: false }));
    expect(cityVerdict({ items, trafficTone: 'neutral' }).label).toBe('กำลังโหลด');
  });
});
