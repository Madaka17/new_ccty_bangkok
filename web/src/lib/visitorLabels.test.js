import { describe, it, expect } from 'vitest';
import { pageLabel } from './visitorLabels.js';

describe('pageLabel (visitor view ids)', () => {
  it('turns a camera AI tab id into Thai, never the raw id', () => {
    expect(pageLabel('yolo:live')).toBe('กล้อง AI › AI นับรถสด');
    expect(pageLabel('yolo:helmet')).toBe('กล้อง AI › หมวกกันน็อก');
  });

  it('uses the Thai labels for the overview and water tabs', () => {
    expect(pageLabel('dashboard:overview')).toBe('ภาพรวม › รถติดตอนนี้');
    expect(pageLabel('water:situation')).toBe('น้ำท่วม › น้ำในเขื่อนทั่วประเทศ');
    expect(pageLabel('water:watch')).toBe('น้ำท่วม › น้ำท่วมใน กทม.');
  });

  it('shows only the base label when the sub id is unknown', () => {
    expect(pageLabel('yolo:unknownthing')).toBe('กล้อง AI');
  });
});
