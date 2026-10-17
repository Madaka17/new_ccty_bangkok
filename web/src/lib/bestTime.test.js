import { describe, expect, test } from 'vitest';
import { todayDayType, hourRange, LEVEL_TH } from './bestTime.js';

describe('todayDayType', () => {
  test('Saturday in Bangkok time is weekend', () => {
    expect(todayDayType(new Date('2026-10-17T09:00:00+07:00'))).toBe('weekend');
  });
  test('Monday in Bangkok time is workday', () => {
    expect(todayDayType(new Date('2026-10-19T09:00:00+07:00'))).toBe('workday');
  });
  test('uses Bangkok day even when UTC is still the day before', () => {
    // Sunday 00:30 Bangkok = Saturday 17:30 UTC
    expect(todayDayType(new Date('2026-10-18T00:30:00+07:00'))).toBe('weekend');
    // Monday 06:00 Bangkok = Sunday 23:00 UTC
    expect(todayDayType(new Date('2026-10-19T06:00:00+07:00'))).toBe('workday');
  });
});

describe('hourRange', () => {
  test('formats an en-dash range with two-digit hours', () => {
    expect(hourRange({ from: 9, to: 10 })).toBe('09:00–10:00');
    expect(hourRange({ from: 6, to: 7 })).toBe('06:00–07:00');
    expect(hourRange({ from: 21, to: 22 })).toBe('21:00–22:00');
  });
});

describe('LEVEL_TH', () => {
  test('has the three Thai level names', () => {
    expect(LEVEL_TH).toEqual({ free: 'คล่องตัว', moderate: 'ชะลอตัว', heavy: 'ติดขัด' });
  });
});
