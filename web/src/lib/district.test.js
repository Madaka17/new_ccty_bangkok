import { afterEach, describe, expect, test, vi } from 'vitest';
import { readMyDistrict, writeMyDistrict, deepestFirst, visibleCameras, CAMERA_SHOWN } from './district.js';

afterEach(() => vi.unstubAllGlobals());

function fakeStorage(initial = {}) {
  const data = { ...initial };
  return {
    data,
    getItem: (k) => (k in data ? data[k] : null),
    setItem: (k, v) => { data[k] = String(v); },
  };
}

const throwing = {
  getItem: () => { throw new Error('denied'); },
  setItem: () => { throw new Error('denied'); },
};

describe('readMyDistrict / writeMyDistrict', () => {
  test('saves and reads back one of the 50 districts under my-district', () => {
    const s = fakeStorage();
    vi.stubGlobal('localStorage', s);
    writeMyDistrict('ดินแดง');
    expect(s.data['my-district']).toBe('ดินแดง');
    expect(readMyDistrict()).toBe('ดินแดง');
  });

  test('nothing saved gives null', () => {
    vi.stubGlobal('localStorage', fakeStorage());
    expect(readMyDistrict()).toBeNull();
  });

  test('a stored name that is not a Bangkok district gives null', () => {
    vi.stubGlobal('localStorage', fakeStorage({ 'my-district': 'เมืองนนท์' }));
    expect(readMyDistrict()).toBeNull();
  });

  test('a throwing storage never throws: read gives null, write is silent', () => {
    vi.stubGlobal('localStorage', throwing);
    expect(() => writeMyDistrict('ดินแดง')).not.toThrow();
    expect(readMyDistrict()).toBeNull();
  });

  test('missing localStorage (no global) is safe', () => {
    vi.stubGlobal('localStorage', undefined);
    expect(() => writeMyDistrict('ดินแดง')).not.toThrow();
    expect(readMyDistrict()).toBeNull();
  });
});

describe('deepestFirst', () => {
  test('sorts flood points by depth, deepest first, without mutating the input', () => {
    const pts = [{ where: 'a', level_cm: 10 }, { where: 'b', level_cm: 42 }, { where: 'c', level_cm: null }];
    const out = deepestFirst(pts);
    expect(out.map((p) => p.where)).toEqual(['b', 'a', 'c']);
    expect(pts[0].where).toBe('a');
  });
});

describe('visibleCameras', () => {
  const cams = Array.from({ length: 15 }, (_, i) => ({ camid: String(i) }));

  test('shows at most 12 until asked for all', () => {
    expect(CAMERA_SHOWN).toBe(12);
    expect(visibleCameras(cams, false)).toHaveLength(12);
    expect(visibleCameras(cams, true)).toHaveLength(15);
  });

  test('a short list is shown whole', () => {
    expect(visibleCameras(cams.slice(0, 3), false)).toHaveLength(3);
  });
});
