import { describe, expect, test } from 'vitest';
import { airAdvice, bkkAverage, band, districtRanking } from './air.js';

const bkk = (area, pm25) => ({ province: 'กรุงเทพมหานคร', area, pm25 });

describe('band', () => {
  test('maps PCD breakpoints to the air_service levels', () => {
    expect(band(15).level).toBe('very_good');
    expect(band(15.1).level).toBe('good');
    expect(band(25).level).toBe('good');
    expect(band(37.5).level).toBe('moderate');
    expect(band(75).level).toBe('unhealthy');
    expect(band(75.1).level).toBe('very_unhealthy');
    expect(band(75.1)).toEqual({ level: 'very_unhealthy', label: 'มีผลต่อสุขภาพ', color: '#E3272C' });
  });
});

describe('bkkAverage', () => {
  test('ignores other provinces', () => {
    const items = [bkk('เขตปทุมวัน', 20), bkk('เขตบางบอน', 30), { province: 'สมุทรสาคร', area: 'เมืองสมุทรสาคร', pm25: 88 }];
    const avg = bkkAverage(items);
    expect(avg.pm25).toBe(25);
    expect(avg.level).toBe('good');
  });

  test('returns null when there are no Bangkok items', () => {
    expect(bkkAverage([])).toBeNull();
  });
});

describe('districtRanking', () => {
  test('groups by district, drops the เขต prefix, sorts by mean descending', () => {
    const rows = districtRanking([bkk('เขตปทุมวัน', 10), bkk('เขตปทุมวัน', 30), bkk('เขตบางบอน', 40)]);
    expect(rows.map((r) => ({ district: r.district, pm25: r.pm25, points: r.points }))).toEqual([
      { district: 'บางบอน', pm25: 40, points: 1 },
      { district: 'ปทุมวัน', pm25: 20, points: 2 },
    ]);
  });

  test('takes the district after the last เขต and skips areas without one', () => {
    const rows = districtRanking([
      bkk('ริมถนนดินแดง เขตดินแดง', 20),
      bkk('เขตดินแดง (สถานีวัด)', 40),
      bkk('(เขตดินแดง)', 30),
      bkk('แขวงหิรัญรูจี เขตธนบุรี', 30),
      bkk('ถนนสุขุมวิท', 99),
    ]);
    expect(rows.map((r) => ({ district: r.district, pm25: r.pm25, points: r.points }))).toEqual([
      { district: 'ดินแดง', pm25: 30, points: 3 },
      { district: 'ธนบุรี', pm25: 30, points: 1 },
    ]);
  });
});

describe('airAdvice', () => {
  test('gives the exact copy for unhealthy', () => {
    expect(airAdvice('unhealthy')).toBe('ควรใส่หน้ากาก N95 เมื่ออยู่นอกบ้าน และลดเวลาอยู่กลางแจ้ง');
  });

  test('gives an empty string for an unknown level', () => {
    expect(airAdvice('x')).toBe('');
  });
});
