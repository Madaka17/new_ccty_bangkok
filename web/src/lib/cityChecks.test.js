import { describe, expect, test } from 'vitest';
import { incidentCheck, waterCheck, waterReportCount, INCIDENTS_RED } from './cityChecks.js';

const gauge = (province, level) => ({ province, level });
const zone = (name, watch, storm_at = null) => ({ name, watch, storm_at });
const noFlood = { counts: { flood: 0, slight: 0 } };

describe('waterCheck', () => {
  test('river overflow outside Bangkok does not make Bangkok yellow, but is named', () => {
    const w = { river: [gauge('นครปฐม', 'overflow'), gauge('สมุทรปราการ', 'overflow'), gauge('กรุงเทพมหานคร', 'high')], weather: [] };
    const c = waterCheck(w, noFlood);
    expect(c.tone).toBe('green');
    expect(c.status).toBe('กทม. ปกติ · ปริมณฑลน้ำล้นตลิ่ง 2 จุด');
  });

  test('Bangkok overflow counts', () => {
    const c = waterCheck({ river: [gauge('กรุงเทพมหานคร', 'overflow')], weather: [] }, noFlood);
    expect(c).toMatchObject({ tone: 'yellow', status: 'น้ำล้นตลิ่ง 1 จุด' });
  });

  test('an orange rain watch is a watch, with the storm time', () => {
    const w = { river: [], weather: [zone('กทม. เหนือ', 'yellow'), zone('กทม. ชั้นใน', 'orange', 'พรุ่งนี้ 14:00')] };
    expect(waterCheck(w, noFlood)).toMatchObject({ tone: 'yellow', status: 'ฝนฟ้าคะนอง พรุ่งนี้ 14:00' });
  });

  test("Bangkok's own rain zones decide over the provinces around", () => {
    const w = { river: [], weather: [{ id: 'samut_prakan', name: 'สมุทรปราการ', watch: 'orange', storm_at: 'พรุ่งนี้ 13:00' },
      { id: 'bkk_inner', name: 'กทม. ชั้นใน', watch: 'orange', storm_at: 'พรุ่งนี้ 14:00' }] };
    expect(waterCheck(w, noFlood).status).toBe('ฝนฟ้าคะนอง พรุ่งนี้ 14:00');
  });

  test('flooded roads come first and are red', () => {
    const c = waterCheck({ river: [], weather: [zone('a', 'orange', 'x')] }, { counts: { flood: 2, slight: 1 } });
    expect(c).toMatchObject({ tone: 'red', status: 'ถนนน้ำท่วม 3 จุด', flooding: 3 });
  });

  test('heavy rain counts only at Bangkok stations', () => {
    const w = { river: [], weather: [], ntw: { rain: [{ province: 'นครปฐม', level: 'heavy' }, { province: 'กรุงเทพมหานคร', level: 'extreme' }] } };
    expect(waterCheck(w, noFlood)).toMatchObject({ tone: 'yellow', status: 'ฝนหนัก 1 จุด' });
  });

  test('nothing loaded yet', () => {
    expect(waterCheck(null, null)).toMatchObject({ tone: 'neutral', known: false });
  });
});

describe('incidentCheck', () => {
  const ev = (kind, title) => ({ kind, title });
  test('accidents and breakdowns are counted apart', () => {
    const c = incidentCheck({ camera: [], longdo: [ev('accident', 'อุบัติเหตุ ก'), ev('accident', 'อุบัติเหตุ ข'), ev('breakdown', 'รถเสีย ค')] });
    expect(c).toMatchObject({ tone: 'yellow', status: 'อุบัติเหตุ 2 · รถเสีย 1', total: 3 });
  });

  test('a "คืบหน้า" item about a listed incident is not counted twice', () => {
    const c = incidentCheck({ longdo: [ev('breakdown', 'รถเสีย ถนนบรมราชชนนี'), ev('breakdown', 'คืบหน้ารถเสีย ถนนบรมราชชนนี')] });
    expect(c.total).toBe(1);
  });

  test(`red only from ${INCIDENTS_RED} incidents`, () => {
    const many = (n) => ({ longdo: Array.from({ length: n }, (_, i) => ev('accident', `อุบัติเหตุ ${i}`)) });
    expect(incidentCheck(many(INCIDENTS_RED - 1)).tone).toBe('yellow');
    expect(incidentCheck(many(INCIDENTS_RED)).tone).toBe('red');
    expect(incidentCheck({ longdo: [] })).toMatchObject({ tone: 'green', status: 'ไม่มีเหตุ' });
  });
});

describe('waterReportCount', () => {
  test('uses the server count of reports that say the water is there now', () => {
    expect(waterReportCount({ updated_at: 1, water_now: 15, items: new Array(45) })).toBe(15);
  });
  test('an older server: every report without a kind counts', () => {
    expect(waterReportCount({ updated_at: 1, items: [{}, { kind: 'aid' }, { kind: 'water' }] })).toBe(2);
  });
  test('no answer from Traffy yet: no count, never a wrong "none"', () => {
    expect(waterReportCount({})).toBe(null);
  });
});
