import { describe, expect, test } from 'vitest';
import { kindLabel, sourceLabel, timeRange, bangkokInputToEpoch, mapItemsWithCoords } from './events.js';

// epoch seconds of a Bangkok wall-clock time (UTC+7)
const bkk = (s) => Math.floor(Date.parse(`${s}+07:00`) / 1000);

describe('kindLabel', () => {
  test('names each kind in plain Thai', () => {
    expect(kindLabel('closure')).toBe('ปิดถนน');
    expect(kindLabel('diversion')).toBe('เบี่ยงจราจร');
    expect(kindLabel('event')).toBe('งานใหญ่');
    expect(kindLabel('run')).toBe('งานวิ่ง');
    expect(kindLabel('concert')).toBe('คอนเสิร์ต');
    expect(kindLabel('ceremony')).toBe('พิธี / ขบวน');
  });
  test('an unknown kind is an announcement', () => {
    expect(kindLabel('roadwork')).toBe('ประกาศ');
    expect(kindLabel(undefined)).toBe('ประกาศ');
  });
});

describe('sourceLabel', () => {
  test('names each source', () => {
    expect(sourceLabel('team')).toBe('ทีมงาน BKK StreetSmart');
    expect(sourceLabel('longdo')).toBe('Longdo Traffic');
    expect(sourceLabel('bma')).toBe('ศูนย์จราจร กทม.');
    expect(sourceLabel('bma_bulletin')).toBe('ประกาศศูนย์จราจร กทม.');
  });
});

describe('timeRange', () => {
  test('same day shows both times', () => {
    expect(timeRange(bkk('2026-10-18T06:00:00'), bkk('2026-10-18T12:00:00'))).toBe('18 ต.ค. 06:00 – 12:00');
  });
  test('across days shows the two dates', () => {
    expect(timeRange(bkk('2026-10-18T06:00:00'), bkk('2026-10-20T22:00:00'))).toBe('18 ต.ค. – 20 ต.ค.');
  });
  test('no end says until announced', () => {
    expect(timeRange(bkk('2026-10-18T06:00:00'), null)).toBe('จนกว่าจะประกาศ');
  });
  test('formats in Bangkok time whatever the browser zone is', () => {
    // 23:30 on 17 Oct in Bangkok is 16:30 UTC on 17 Oct
    expect(timeRange(bkk('2026-10-17T23:30:00'), bkk('2026-10-18T01:00:00'))).toBe('17 ต.ค. – 18 ต.ค.');
  });
  test('no start shows only the end', () => {
    expect(timeRange(null, bkk('2026-10-18T12:00:00'))).toBe('ถึง 18 ต.ค. 12:00');
  });
  test('neither time gives a plain note', () => {
    expect(timeRange(null, null)).toBe('ไม่ระบุเวลา');
  });
});

describe('bangkokInputToEpoch', () => {
  test('reads a datetime-local value as Bangkok time', () => {
    expect(bangkokInputToEpoch('2026-10-18T06:00')).toBe(bkk('2026-10-18T06:00:00'));
  });
  test('empty or broken input gives null', () => {
    expect(bangkokInputToEpoch('')).toBeNull();
    expect(bangkokInputToEpoch('not a date')).toBeNull();
  });
});

describe('mapItemsWithCoords', () => {
  test('keeps items with coordinates once each, across the four sections', () => {
    const a = { id: 'a', lat: 13.7, lng: 100.5 };
    const b = { id: 'b', lat: null, lng: null };
    const c = { id: 'c', lat: 13.8, lng: 100.6 };
    const out = mapItemsWithCoords({ ongoing: [a, b], today: [a], tomorrow: [c], week: [] });
    expect(out.map((i) => i.id)).toEqual(['a', 'c']);
  });
  test('no data gives an empty list', () => {
    expect(mapItemsWithCoords(null)).toEqual([]);
  });
});
