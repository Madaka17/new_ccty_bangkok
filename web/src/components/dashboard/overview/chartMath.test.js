import { describe, expect, test } from 'vitest';
import { niceMax, linePath } from './chartMath.js';

describe('niceMax', () => {
  test('gives a whole-number top divisible by 4 so four gridlines land on whole numbers', () => {
    expect(niceMax(0)).toBe(4);
    expect(niceMax(3)).toBe(4);
    expect(niceMax(10)).toBe(12);
    expect(niceMax(12)).toBe(12);
    expect(niceMax(13)).toBe(16);
  });

  test('never returns NaN for missing input', () => {
    expect(niceMax(undefined)).toBe(4);
    expect(niceMax(NaN)).toBe(4);
  });
});

describe('linePath', () => {
  test('empty input gives an empty path', () => {
    expect(linePath([])).toBe('');
  });

  test('one point is a move, more points are smooth cubic segments through every point', () => {
    expect(linePath([{ x: 0, y: 0 }])).toBe('M0,0');
    const d = linePath([{ x: 0, y: 0 }, { x: 10, y: 10 }, { x: 20, y: 0 }]);
    expect(d.startsWith('M0,0')).toBe(true);
    expect(d.match(/C/g)).toHaveLength(2);
    expect(d).toContain('10,10');
    expect(d).toContain('20,0');
  });
});
