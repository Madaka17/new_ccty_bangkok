import { describe, expect, test } from 'vitest';
import { badgeText, dropCount, forcedScene, fxAllowed, readPref, weatherScene, writePref } from './weatherFx.js';

const throwing = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); } };
const fakeStorage = (value) => ({ getItem: () => value, setItem() {} });

describe('weatherScene', () => {
  test('rain intensity from symbol and amount', () => {
    expect(weatherScene({ symbol: 'lightrain', rain_1h: 0.3 })).toMatchObject({ kind: 'rain', intensity: 'light' });
    expect(weatherScene({ symbol: 'heavyrainshowers_day' })).toMatchObject({ kind: 'rain', intensity: 'heavy' });
    expect(weatherScene({ symbol: 'rain', rain_1h: 2 })).toMatchObject({ kind: 'rain', intensity: 'moderate' });
    expect(weatherScene({ symbol: 'cloudy', rain_1h: 5 })).toMatchObject({ kind: 'rain', intensity: 'heavy' });
  });

  test('thunder is storm', () => {
    expect(weatherScene({ symbol: 'rainandthunder' })).toMatchObject({ kind: 'storm', intensity: 'moderate' });
    expect(weatherScene({ symbol: 'heavyrainandthunder' })).toMatchObject({ kind: 'storm', intensity: 'heavy' });
  });

  test('cloudy, sunny and clear kinds have no intensity', () => {
    expect(weatherScene({ symbol: 'fog' })).toMatchObject({ kind: 'cloudy', intensity: null });
    expect(weatherScene({ symbol: 'clearsky_day', temp: 34 })).toMatchObject({ kind: 'sunny', intensity: null, cool: false });
    expect(weatherScene({ symbol: 'fair_day', temp: 22.5, wind_speed: 7.9 }))
      .toMatchObject({ kind: 'sunny', cool: false, windy: false });
    expect(weatherScene({ symbol: 'clearsky_night', temp: 21, wind_speed: 9 }))
      .toMatchObject({ kind: 'clear', cool: true, windy: true });
  });

  test('missing values give clear with both flags false', () => {
    expect(weatherScene(null)).toEqual({ kind: 'clear', intensity: null, cool: false, windy: false });
    expect(weatherScene({ symbol: null })).toEqual({ kind: 'clear', intensity: null, cool: false, windy: false });
  });
});

describe('forcedScene', () => {
  test('reads the ?fx= comma list', () => {
    expect(forcedScene('?fx=storm')).toMatchObject({ kind: 'storm', intensity: 'moderate' });
    expect(forcedScene('?fx=heavyrain')).toMatchObject({ kind: 'rain', intensity: 'heavy' });
    expect(forcedScene('?fx=rain')).toMatchObject({ kind: 'rain', intensity: 'moderate' });
    expect(forcedScene('?fx=sunny,windy')).toMatchObject({ kind: 'sunny', intensity: null, windy: true, cool: false });
    expect(forcedScene('?fx=clear,cool')).toMatchObject({ kind: 'clear', cool: true, windy: false });
  });

  test('returns null when nothing is recognised', () => {
    expect(forcedScene('?x=1')).toBeNull();
    expect(forcedScene('?fx=bogus')).toBeNull();
  });
});

describe('fxAllowed', () => {
  const base = { pref: 'on', reducedMotion: false, saveData: false, battery: null };

  test('true for the defaults', () => {
    expect(fxAllowed(base)).toBe(true);
  });

  test('false when any one condition holds', () => {
    expect(fxAllowed({ ...base, pref: 'off' })).toBe(false);
    expect(fxAllowed({ ...base, reducedMotion: true })).toBe(false);
    expect(fxAllowed({ ...base, saveData: true })).toBe(false);
    expect(fxAllowed({ ...base, battery: { level: 0.1, charging: false } })).toBe(false);
  });

  test('low battery while charging is allowed', () => {
    expect(fxAllowed({ ...base, battery: { level: 0.1, charging: true } })).toBe(true);
  });
});

describe('readPref and writePref', () => {
  test('readPref gives on when storage throws', () => {
    expect(readPref(throwing)).toBe('on');
  });

  test('readPref returns the stored off', () => {
    expect(readPref(fakeStorage('off'))).toBe('off');
  });

  test('writePref does not throw when storage throws', () => {
    expect(() => writePref('off', throwing)).not.toThrow();
  });
});

describe('badgeText', () => {
  const scene = (kind, flags = {}) => ({ kind, intensity: null, cool: false, windy: false, ...flags });

  test('storm beats windy', () => {
    expect(badgeText(scene('storm', { windy: true }))).toBe('ฝนฟ้าคะนอง');
  });

  test('rain beats cool', () => {
    expect(badgeText(scene('rain', { cool: true }))).toBe('ฝนกำลังตก');
  });

  test('windy beats cool', () => {
    expect(badgeText(scene('sunny', { windy: true, cool: true }))).toBe('ลมแรง');
    expect(badgeText(scene('clear', { cool: true }))).toBe('อากาศเย็น');
  });

  test('sunny alone gives empty text', () => {
    expect(badgeText(scene('sunny'))).toBe('');
  });
});

describe('dropCount', () => {
  test('per intensity, halved when narrow', () => {
    expect(dropCount('light', false)).toBe(40);
    expect(dropCount('moderate', false)).toBe(80);
    expect(dropCount('heavy', false)).toBe(140);
    expect(dropCount('heavy', true)).toBe(70);
    expect(dropCount('light', true)).toBe(20);
  });

  test('zero for null', () => {
    expect(dropCount(null, false)).toBe(0);
  });
});
