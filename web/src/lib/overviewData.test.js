import { describe, expect, test } from 'vitest';
import { sumVehicleHistory, bmaHourlyLines, incidentRows, sortRows, toCsv, thinLabels } from './overviewData.js';

describe('sumVehicleHistory', () => {
  test('sums two cameras per key in keys order', () => {
    const out = sumVehicleHistory({
      bucket: 'hour',
      keys: ['2026-11-21T08:00', '2026-11-21T09:00'],
      cameras: [
        { series: { '2026-11-21T08:00': { cars: 10, motorcycles: 4, trucks: 1, total: 15 }, '2026-11-21T09:00': { cars: 3, motorcycles: 2, trucks: 0, total: 5 } } },
        { series: { '2026-11-21T08:00': { cars: 5, motorcycles: 6, trucks: 0, total: 11 } } },
      ],
    });
    expect(out).toEqual([
      { key: '2026-11-21T08:00', label: '08 น.', cars: 15, motorcycles: 10 },
      { key: '2026-11-21T09:00', label: '09 น.', cars: 3, motorcycles: 2 },
    ]);
  });

  test('keys with no camera data come back as zeros', () => {
    const out = sumVehicleHistory({ bucket: 'hour', keys: ['2026-11-21T10:00'], cameras: [] });
    expect(out).toEqual([{ key: '2026-11-21T10:00', label: '10 น.', cars: 0, motorcycles: 0 }]);
  });

  test('accepts a space between date and hour in hour keys', () => {
    const out = sumVehicleHistory({ bucket: 'hour', keys: ['2026-11-21 08:00'], cameras: [] });
    expect(out[0].label).toBe('08 น.');
  });

  test('day keys get a D/M label without leading zeros', () => {
    const out = sumVehicleHistory({
      bucket: 'day',
      keys: ['2026-11-05', '2026-11-21'],
      cameras: [{ series: { '2026-11-05': { cars: 7, motorcycles: 1, trucks: 0, total: 8 } } }],
    });
    expect(out.map((r) => r.label)).toEqual(['5/11', '21/11']);
    expect(out[0]).toMatchObject({ cars: 7, motorcycles: 1 });
  });

  test('missing or empty input gives an empty array', () => {
    expect(sumVehicleHistory(null)).toEqual([]);
    expect(sumVehicleHistory(undefined)).toEqual([]);
    expect(sumVehicleHistory({})).toEqual([]);
    expect(sumVehicleHistory({ bucket: 'hour', keys: [], cameras: [] })).toEqual([]);
  });
});

describe('bmaHourlyLines', () => {
  test('divides by camera count and rounds to one decimal per camera', () => {
    const out = bmaHourlyLines([{ hour: '2026-11-21T08:00', cars: 7, motorcycles: 10, cam_count: 3 }]);
    expect(out[0].cars).toBe(2.3);
    expect(out[0].motorcycles).toBe(3.3);
  });

  test('cam_count of zero is treated as one', () => {
    const out = bmaHourlyLines([{ hour: '2026-11-21T08:00', cars: 6, motorcycles: 2, cam_count: 0 }]);
    expect(out[0]).toMatchObject({ cars: 6, motorcycles: 2 });
  });

  test('t is epoch seconds of the hour read as local time', () => {
    const out = bmaHourlyLines([{ hour: '2026-11-21T08:00', cars: 1, motorcycles: 1, cam_count: 1 }]);
    expect(out[0].t).toBe(new Date(2026, 10, 21, 8, 0).getTime() / 1000);
    expect(out[0].label).toBe('08 น.');
  });

  test('skips rows without an hour', () => {
    const out = bmaHourlyLines([
      { cars: 1, motorcycles: 1, cam_count: 1 },
      { hour: '2026-11-21T09:00', cars: 2, motorcycles: 2, cam_count: 1 },
    ]);
    expect(out.map((r) => r.label)).toEqual(['09 น.']);
  });

  test('missing input gives an empty array', () => {
    expect(bmaHourlyLines(undefined)).toEqual([]);
    expect(bmaHourlyLines([])).toEqual([]);
  });
});

describe('incidentRows', () => {
  test('merges camera and longdo rows, camera time from ts', () => {
    const out = incidentRows({
      camera: [{ id: 'c1', title: 'รถชนที่สี่แยก', kind: 'accident', image: 'a.jpg', ts: 1000 }],
      longdo: [{ id: 'l1', title: 'รถเสียบนสะพาน', kind: 'breakdown', start: '2026-11-21 08:30:00' }],
    });
    expect(out).toHaveLength(2);
    const cam = out.find((r) => r.id === 'c1');
    expect(cam).toEqual({ id: 'c1', title: 'รถชนที่สี่แยก', kind: 'accident', source: 'camera', image: 'a.jpg', at: 1000 });
    const lon = out.find((r) => r.id === 'l1');
    expect(lon.source).toBe('longdo');
    expect(lon.at).toBe(new Date(2026, 10, 21, 8, 30, 0).getTime() / 1000);
  });

  test('kind defaults to accident, id falls back to source and index, missing time is null', () => {
    const out = incidentRows({ camera: [{ title: 'x' }], longdo: [] });
    expect(out[0]).toMatchObject({ id: 'camera-0', kind: 'accident', at: null, image: null });
  });

  test('missing input gives an empty array', () => {
    expect(incidentRows(undefined)).toEqual([]);
    expect(incidentRows({})).toEqual([]);
  });

  test('sorted newest first, rows without time last', () => {
    const out = incidentRows({
      camera: [{ id: 'old', ts: 100 }, { id: 'none' }, { id: 'new', ts: 300 }],
      longdo: [{ id: 'mid', start: '2026-11-21 08:30:00' }],
    });
    const ids = out.map((r) => r.id);
    expect(ids[ids.length - 1]).toBe('none');
    const times = out.filter((r) => r.at != null).map((r) => r.at);
    expect(times).toEqual([...times].sort((a, b) => b - a));
    expect(ids[0]).toBe('mid');
  });
});

describe('sortRows', () => {
  const rows = [{ n: 2 }, { n: null }, { n: 1 }, { n: 3 }];

  test('ascending sort with nulls last', () => {
    expect(sortRows(rows, 'n', 'asc').map((r) => r.n)).toEqual([1, 2, 3, null]);
  });

  test('descending sort still puts nulls last', () => {
    expect(sortRows(rows, 'n', 'desc').map((r) => r.n)).toEqual([3, 2, 1, null]);
  });

  test('returns a new array and leaves the input untouched', () => {
    const copy = rows.map((r) => ({ ...r }));
    const out = sortRows(rows, 'n', 'asc');
    expect(out).not.toBe(rows);
    expect(rows).toEqual(copy);
  });
});

describe('toCsv', () => {
  const columns = [
    { key: 'name', label: 'ชื่อ' },
    { key: 'n', label: 'จำนวน' },
  ];

  test('starts with a BOM, header row, CRLF line ends', () => {
    const csv = toCsv([{ name: 'a', n: 1 }, { name: 'b', n: 2 }], columns);
    expect(csv).toBe('﻿ชื่อ,จำนวน\r\na,1\r\nb,2');
  });

  test('quotes values with commas, quotes and newlines', () => {
    const csv = toCsv([{ name: 'a, "b"', n: 'x\ny' }], columns);
    expect(csv).toBe('﻿ชื่อ,จำนวน\r\n"a, ""b""","x\ny"');
  });

  test('null and undefined become empty cells', () => {
    const csv = toCsv([{ name: null, n: undefined }], columns);
    expect(csv).toBe('﻿ชื่อ,จำนวน\r\n,');
  });

  test('no rows gives only the BOM and header', () => {
    expect(toCsv([], columns)).toBe('﻿ชื่อ,จำนวน');
  });
});

describe('thinLabels', () => {
  test('step is one up to twelve labels', () => {
    expect(thinLabels(0)).toBe(1);
    expect(thinLabels(5)).toBe(1);
    expect(thinLabels(12)).toBe(1);
  });

  test('step grows as ceil(n / max)', () => {
    expect(thinLabels(13)).toBe(2);
    expect(thinLabels(24)).toBe(2);
    expect(thinLabels(30)).toBe(3);
  });

  test('custom max is respected', () => {
    expect(thinLabels(10, 5)).toBe(2);
  });
});
