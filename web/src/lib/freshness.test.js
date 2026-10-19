import { describe, expect, test } from 'vitest';
import { freshness, FRESH_LIMIT } from './freshness.js';

const NOW = 1_800_000_000;

describe('freshness', () => {
  test('says how old the data is', () => {
    expect(freshness(NOW - 20, 900, NOW)).toEqual({ text: 'เมื่อสักครู่', stale: false });
    expect(freshness(NOW - 5 * 60, 900, NOW)).toEqual({ text: '5 นาทีก่อน', stale: false });
    expect(freshness(NOW - 2 * 3600, FRESH_LIMIT.air, NOW)).toEqual({ text: '2 ชม.ก่อน', stale: false });
  });

  test('past its source limit it is old', () => {
    expect(freshness(NOW - 20 * 60, FRESH_LIMIT.traffic, NOW).stale).toBe(true);
  });

  test('no time: nothing to say', () => {
    expect(freshness(null, 900, NOW)).toBe(null);
  });
});
