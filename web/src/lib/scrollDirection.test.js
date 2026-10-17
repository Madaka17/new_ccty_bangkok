import { describe, expect, test } from 'vitest';
import { nextVisibility } from './scrollDirection.js';

const at = (y, lastY, now, lastMoveAt, prev) => nextVisibility(prev, { y, lastY, now, lastMoveAt });

describe('nextVisibility', () => {
  test('shows at the top of the page', () => {
    expect(at(40, 300, 1000, 900, false)).toBe(true);
  });

  test('hides after moving down by 20 px', () => {
    expect(at(320, 300, 1000, 900, true)).toBe(false);
  });

  test('keeps the previous state for a 4 px move down', () => {
    expect(at(304, 300, 1000, 900, true)).toBe(true);
    expect(at(304, 300, 1000, 900, false)).toBe(false);
  });

  test('shows after moving up by 10 px', () => {
    expect(at(290, 300, 1000, 900, false)).toBe(true);
  });

  test('shows again after 1.3 s idle', () => {
    expect(at(500, 500, 2300, 1000, false)).toBe(true);
  });
});
