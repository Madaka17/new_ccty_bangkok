import { describe, expect, test } from 'vitest';
import { cityVerdict, FLOOD_ROADS_SEVERE } from './cityVerdict.js';

const NOW = 1_800_000_000;   // fixed "now" in unix seconds
// id, at and limit are optional: the old tests have no data time, so none of their checks is ever old
const check = (q, tone, known = true, { id, at, limit } = {}) => ({ q, say: `${q} ${tone}`, tone, known, id, at, limit });
const aged = (secondsOld, limit) => ({ at: NOW - secondsOld, limit });
const allFine = () => [check('รถติดไหม', 'green', true, { id: 'traffic' }), check('อุบัติเหตุ', 'green', true, { id: 'incident' }),
  check('ฝนและน้ำ', 'green', true, { id: 'water' }), check('คนแจ้งน้ำท่วม', 'green', true, { id: 'report' }),
  check('อากาศ', 'green', true, { id: 'weather' }), check('ฝุ่น', 'green', true, { id: 'air' })];

describe('cityVerdict', () => {
  test('every check fine: go', () => {
    const v = cityVerdict({ items: allFine(), trafficTone: 'green' });
    expect(v.tone).toBe('green');
    expect(v.label).toBe('ออกได้');
    expect(v.headline).toBe('ทุกเรื่องปกติ เดินทางได้ตามปกติ');
    expect(v.old).toEqual([]);
  });

  test('a red row that does not stop a trip (many flood reports) only makes it yellow', () => {
    const items = allFine();
    items[3] = check('คนแจ้งน้ำท่วม', 'red', true, { id: 'report' });
    const v = cityVerdict({ items, trafficTone: 'green' });
    expect(v.tone).toBe('yellow');
    expect(v.label).toBe('ออกได้ แต่ระวัง');
    expect(v.headline).toBe('รถคล่องตัว แต่มี 1 เรื่องต้องระวัง');
  });

  test('heavy traffic city-wide: wait if you can, naming the roads to avoid', () => {
    const items = allFine();
    items[0] = check('รถติดไหม', 'red', true, { id: 'traffic' });
    const v = cityVerdict({ items, trafficTone: 'red', avoid: ['พระราม 4', 'สุขุมวิท', 'ลาดพร้าว'] });
    expect(v.tone).toBe('red');
    expect(v.label).toBe('รอก่อนถ้าไม่รีบ');
    expect(v.headline).toBe('รถติดหนักหลายสาย เลี่ยงพระราม 4 กับสุขุมวิท');
  });

  test('many flooded roads: red; a few: yellow, both name the count', () => {
    const items = allFine();
    items[2] = check('ฝนและน้ำ', 'red', true, { id: 'water' });
    expect(cityVerdict({ items, trafficTone: 'green', flooding: FLOOD_ROADS_SEVERE }).tone).toBe('red');
    const few = cityVerdict({ items, trafficTone: 'green', flooding: 3 });
    expect(few.tone).toBe('yellow');
    expect(few.headline).toBe('ถนนน้ำท่วม 3 จุด ดูเส้นทางก่อนออก');
  });

  test('missing data is never shown as fine', () => {
    const items = allFine();
    items[5] = check('ฝุ่น', 'neutral', false, { id: 'air' });
    const v = cityVerdict({ items, trafficTone: 'green' });
    expect(v.tone).toBe('neutral');
    expect(v.label).toBe('ข้อมูลยังไม่ครบ');
    expect(v.detail).toBe('ยังไม่มีข้อมูล: ฝุ่น');
  });

  test('a danger already known shows at once, even while other checks load', () => {
    const items = allFine();
    items[1] = check('อุบัติเหตุ', 'yellow', true, { id: 'incident' });
    items[5] = check('ฝุ่น', 'neutral', false, { id: 'air' });
    const v = cityVerdict({ items, trafficTone: 'green' });
    expect(v.tone).toBe('yellow');
    expect(v.detail).toBe('อุบัติเหตุ yellow · ยังไม่มีข้อมูล: ฝุ่น');
  });

  test('nothing loaded yet', () => {
    const items = allFine().map((i) => ({ ...i, tone: 'neutral', known: false }));
    expect(cityVerdict({ items, trafficTone: 'neutral' }).label).toBe('กำลังโหลด');
  });

  test('old traffic data: no ออกได้, says the data may be old and names the check', () => {
    const items = allFine();
    items[0] = check('รถติดไหม', 'green', true, { id: 'traffic', ...aged(2000, 900) });
    const v = cityVerdict({ items, trafficTone: 'green', now: NOW });
    expect(v.tone).toBe('neutral');
    expect(v.label).toBe('ข้อมูลอาจไม่ล่าสุด');
    expect(v.headline).toBe('ตรวจเองก่อนออก ข้อมูลบางเรื่องไม่ได้อัปเดต');
    expect(v.detail).toContain('ข้อมูลเก่า: รถติดไหม');
    expect(v.detail).toContain('33 นาทีก่อน');
    expect(v.old.map((i) => i.q)).toEqual(['รถติดไหม']);
  });

  test('old air data does not change the answer', () => {
    const items = allFine();
    items[5] = check('ฝุ่น', 'green', true, { id: 'air', ...aged(99999, 7200) });
    const v = cityVerdict({ items, trafficTone: 'green', now: NOW });
    expect(v.tone).toBe('green');
    expect(v.label).toBe('ออกได้');
    expect(v.old).toEqual([]);
  });

  test('a known red danger on old traffic data still shows red', () => {
    const items = allFine();
    items[0] = check('รถติดไหม', 'red', true, { id: 'traffic', ...aged(2000, 900) });
    const v = cityVerdict({ items, trafficTone: 'red', now: NOW });
    expect(v.tone).toBe('red');
    expect(v.label).toBe('รอก่อนถ้าไม่รีบ');
  });

  test('flood reports yellow with old water data: neutral, and the care item is still said', () => {
    const items = allFine();
    items[2] = check('ฝนและน้ำ', 'green', true, { id: 'water', ...aged(5000, 3600) });
    items[3] = check('คนแจ้งน้ำท่วม', 'yellow', true, { id: 'report', ...aged(60, 1800) });
    const v = cityVerdict({ items, trafficTone: 'green', now: NOW });
    expect(v.tone).toBe('neutral');
    expect(v.label).toBe('ข้อมูลอาจไม่ล่าสุด');
    expect(v.detail).toContain('คนแจ้งน้ำท่วม yellow');
    expect(v.detail).toContain('ข้อมูลเก่า: ฝนและน้ำ');
  });

  test('old flood reports alone do not change the answer (their row says the update failed)', () => {
    const items = allFine();
    items[3] = check('คนแจ้งน้ำท่วม', 'green', true, { id: 'report', ...aged(99999, 1800) });
    const v = cityVerdict({ items, trafficTone: 'green', now: NOW });
    expect(v.tone).toBe('green');
  });

  test('old and still-loading checks are both said', () => {
    const items = allFine();
    items[0] = check('รถติดไหม', 'green', true, { id: 'traffic', ...aged(2000, 900) });
    items[5] = check('ฝุ่น', 'neutral', false);
    const v = cityVerdict({ items, trafficTone: 'green', now: NOW });
    expect(v.tone).toBe('neutral');
    expect(v.detail).toContain('ยังไม่มีข้อมูล: ฝุ่น');
  });

  test('fresh data stays green', () => {
    const items = allFine();
    items[0] = check('รถติดไหม', 'green', true, { id: 'traffic', ...aged(60, 900) });
    const v = cityVerdict({ items, trafficTone: 'green', now: NOW });
    expect(v.tone).toBe('green');
    expect(v.label).toBe('ออกได้');
  });
});
