import { describe, it, expect } from 'vitest';
import { searchPages, ALL_PAGES } from './pageSearch.js';

const pages = [
  { id: 'water', label: 'น้ำท่วม', hint: 'ระดับน้ำ' },
  { id: 'yolo', label: 'กล้อง AI', hint: 'ตรวจคนไม่สวมหมวกกันน็อก' },
  { id: 'cameras', label: 'ดูกล้องสด', hint: 'ภาพสด' },
];

describe('searchPages', () => {
  it('empty or blank query returns nothing', () => {
    expect(searchPages('', pages)).toEqual([]);
    expect(searchPages('   ', pages)).toEqual([]);
  });
  it('matches label', () => {
    expect(searchPages('น้ำ', pages).map((p) => p.id)).toEqual(['water']);
  });
  it('matches hint only', () => {
    expect(searchPages('หมวกกันน็อก', pages).map((p) => p.id)).toEqual(['yolo']);
  });
  it('label matches rank before hint matches', () => {
    const r = searchPages('สด', [{ id: 'a', label: 'x', hint: 'สด' }, { id: 'b', label: 'สด', hint: '' }]);
    expect(r.map((p) => p.id)).toEqual(['b', 'a']);
  });
  it('is case-insensitive for latin text', () => {
    expect(searchPages('ai', pages).map((p) => p.id)).toEqual(['yolo']);
  });
  it('respects limit', () => {
    expect(searchPages('ก', pages, 1)).toHaveLength(1);
  });
  it('ALL_PAGES includes home-only pages air and district', () => {
    const ids = ALL_PAGES.map((p) => p.id);
    expect(ids).toContain('air');
    expect(ids).toContain('district');
  });
});
