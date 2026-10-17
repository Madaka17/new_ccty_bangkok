// Weather scene and permission helpers for the weather background. Pure: no React, no DOM.

const PREF_KEY = 'weather-fx';
const STORM_TEXT = 'ฝนฟ้าคะนอง';
const RAIN_TEXT = 'ฝนกำลังตก';
const WINDY_TEXT = 'ลมแรง';
const COOL_TEXT = 'อากาศเย็น';
const COOL_MAX_C = 22;
const WINDY_MIN_MS = 8;
const LOW_BATTERY = 0.2;
const DROPS = { light: 40, moderate: 80, heavy: 140 };
const KINDS = ['heavyrain', 'rain', 'storm', 'sunny', 'cloudy', 'clear'];

// Default storage without touching an undeclared global (Node has no localStorage).
const webStorage = () => {
  try {
    return localStorage;
  } catch {
    return undefined;
  }
};

export function weatherScene(now) {
  const s = String(now?.symbol ?? '').toLowerCase();
  const r = now?.rain_1h ?? null;
  const cool = now?.temp != null && now.temp <= COOL_MAX_C;
  const windy = now?.wind_speed != null && now.wind_speed >= WINDY_MIN_MS;
  const flags = { cool, windy };

  if (s.includes('thunder')) {
    return { kind: 'storm', intensity: s.includes('heavy') || r >= 4 ? 'heavy' : 'moderate', ...flags };
  }
  if (s.includes('rain') || (r != null && r >= 0.5)) {
    let intensity = 'moderate';
    if (s.includes('heavy') || r >= 4) intensity = 'heavy';
    else if (s.includes('light') || (r != null && r < 1)) intensity = 'light';
    return { kind: 'rain', intensity, ...flags };
  }
  if (s.startsWith('cloudy') || s.startsWith('fog')) return { kind: 'cloudy', intensity: null, ...flags };
  if (s.startsWith('clearsky_day') || s.startsWith('fair_day') || s.startsWith('partlycloudy_day')) {
    return { kind: 'sunny', intensity: null, ...flags };
  }
  return { kind: 'clear', intensity: null, ...flags };
}

// Preview override from ?fx=a,b,c. The first kind token sets the scene; cool and windy add flags.
export function forcedScene(search) {
  const raw = new URLSearchParams(search || '').get('fx');
  if (!raw) return null;
  const tokens = raw.split(',').map((t) => t.trim().toLowerCase());
  const known = tokens.filter((t) => KINDS.includes(t) || t === 'cool' || t === 'windy');
  if (!known.length) return null;
  const scene = { kind: 'clear', intensity: null, cool: false, windy: false };
  const kind = known.find((t) => KINDS.includes(t));
  if (kind === 'heavyrain') Object.assign(scene, { kind: 'rain', intensity: 'heavy' });
  else if (kind === 'rain') Object.assign(scene, { kind: 'rain', intensity: 'moderate' });
  else if (kind === 'storm') Object.assign(scene, { kind: 'storm', intensity: 'moderate' });
  else if (kind) scene.kind = kind;
  scene.cool = known.includes('cool');
  scene.windy = known.includes('windy');
  return scene;
}

export function fxAllowed({ pref, reducedMotion, saveData, battery } = {}) {
  if (pref === 'off' || reducedMotion || saveData) return false;
  if (battery && battery.level < LOW_BATTERY && !battery.charging) return false;
  return true;
}

export function readPref(storage = webStorage()) {
  try {
    return storage.getItem(PREF_KEY) === 'off' ? 'off' : 'on';
  } catch {
    return 'on';
  }
}

export function writePref(value, storage = webStorage()) {
  try {
    storage.setItem(PREF_KEY, value === 'off' ? 'off' : 'on');
  } catch {
    // storage blocked: the choice simply does not persist
  }
}

export function badgeText(scene) {
  if (scene.kind === 'storm') return STORM_TEXT;
  if (scene.kind === 'rain') return RAIN_TEXT;
  if (scene.windy) return WINDY_TEXT;
  if (scene.cool) return COOL_TEXT;
  return '';
}

export function dropCount(intensity, narrow) {
  const n = DROPS[intensity] ?? 0;
  return narrow ? Math.floor(n / 2) : n;
}
