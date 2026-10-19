import { describe, expect, test } from 'vitest';
import { leftOutNote, waterNow } from './floodReports.js';

describe('waterNow', () => {
  test('keeps only the reports that say the water is there now', () => {
    const r = waterNow({ updated_at: 1, total: 4, items: [{ id: 1, kind: 'water' }, { id: 2, kind: 'aid' }, { id: 3, kind: 'recurring' }, { id: 4 }] });
    expect(r.items.map((i) => i.id)).toEqual([1, 4]);
    expect(r).toMatchObject({ total: 2, left_out: 2, updated_at: 1 });
    expect(leftOutNote(r)).toBe('ไม่นับอีก 2 เรื่องที่ไม่ใช่น้ำท่วมตอนนี้ เช่น ขอเงินเยียวยา ท่อตัน ถนนชำรุด');
  });

  test('nothing left out: no note; no answer yet: unchanged', () => {
    expect(leftOutNote(waterNow({ items: [{ kind: 'water' }] }))).toBe(null);
    expect(waterNow(null)).toBe(null);
  });
});
