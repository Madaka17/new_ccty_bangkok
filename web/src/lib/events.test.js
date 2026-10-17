import { describe, expect, test } from 'vitest';
import {
  kindLabel, sourceLabel, timeRange, bangkokInputToEpoch, mapItemsWithCoords, isDuplicateOfClosure,
  anySourceNotOk, emptySectionText, PARTIAL_NOTE, UNKNOWN_EMPTY, NONE_LISTED,
} from './events.js';

// epoch seconds of a Bangkok wall-clock time (UTC+7)
const bkk = (s) => Math.floor(Date.parse(`${s}+07:00`) / 1000);

describe('sources_ok', () => {
  test('all feeds ok: no partial flag, an empty section says none listed', () => {
    const ok = { closures: true, bma: true, bulletins: true };
    expect(anySourceNotOk(ok)).toBe(false);
    expect(emptySectionText(ok)).toBe(NONE_LISTED);
  });
  test('one feed not ok: partial flag, an empty section says the data is missing', () => {
    const down = { closures: false, bma: true, bulletins: true };
    expect(anySourceNotOk(down)).toBe(true);
    expect(emptySectionText(down)).toBe(UNKNOWN_EMPTY);
    expect(PARTIAL_NOTE).toBe('ข้อมูลบางส่วนยังไม่มา รายการอาจไม่ครบ');
  });
  test('a missing sources_ok map (older server) counts as ok', () => {
    expect(anySourceNotOk(undefined)).toBe(false);
    expect(emptySectionText(null)).toBe(NONE_LISTED);
  });
});

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
  const NOW = bkk('2026-10-18T09:00:00');
  const tr = (a, b) => timeRange(a, b, NOW);
  test('same day shows both times', () => {
    expect(tr(bkk('2026-10-18T06:00:00'), bkk('2026-10-18T12:00:00'))).toBe('18 ต.ค. 06:00 – 12:00');
  });
  test('across days shows the two dates', () => {
    expect(tr(bkk('2026-10-18T06:00:00'), bkk('2026-10-20T22:00:00'))).toBe('18 ต.ค. – 20 ต.ค.');
  });
  test('no end says until announced', () => {
    expect(tr(bkk('2026-10-18T06:00:00'), null)).toBe('จนกว่าจะประกาศ');
  });
  test('formats in Bangkok time whatever the browser zone is', () => {
    // 23:30 on 17 Oct in Bangkok is 16:30 UTC on 17 Oct
    expect(tr(bkk('2026-10-17T23:30:00'), bkk('2026-10-18T01:00:00'))).toBe('17 ต.ค. – 18 ต.ค.');
  });
  test('no start shows only the end', () => {
    expect(tr(null, bkk('2026-10-18T12:00:00'))).toBe('ถึง 18 ต.ค. 12:00');
  });
  test('neither time gives a plain note', () => {
    expect(tr(null, null)).toBe('ไม่ระบุเวลา');
  });
});

describe('timeRange year', () => {
  const now = bkk('2026-10-18T09:00:00');
  test('same year as now: no year', () => {
    expect(timeRange(bkk('2026-01-18T06:00:00'), bkk('2026-01-18T12:00:00'), now)).toBe('18 ม.ค. 06:00 – 12:00');
  });
  test('another year: Buddhist-era short year', () => {
    // 2027 + 543 = 2570, last two digits 70
    expect(timeRange(bkk('2027-01-18T06:00:00'), bkk('2027-01-18T12:00:00'), now)).toBe('18 ม.ค. 70 06:00 – 12:00');
    expect(timeRange(bkk('2025-12-30T00:00:00'), bkk('2026-01-02T00:00:00'), now)).toBe('30 ธ.ค. 68 – 2 ม.ค.');
  });
});

describe('isDuplicateOfClosure', () => {
  test('a Longdo closure or diversion is covered by the closures layer', () => {
    expect(isDuplicateOfClosure({ source: 'longdo', kind: 'closed' })).toBe(true);
    expect(isDuplicateOfClosure({ source: 'longdo', kind: 'diversion' })).toBe(true);
  });
  test('team, BMA and other kinds are not covered', () => {
    expect(isDuplicateOfClosure({ source: 'team', kind: 'closure' })).toBe(false);
    expect(isDuplicateOfClosure({ source: 'bma', kind: 'roadwork' })).toBe(false);
    expect(isDuplicateOfClosure({ source: 'longdo', kind: 'event' })).toBe(false);
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
