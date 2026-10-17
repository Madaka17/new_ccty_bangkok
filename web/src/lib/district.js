// "เขตของฉัน": the one district a visitor saved, and small helpers for its page.
// Backend: /api/district/{name} (backend/traffic/district_view.py). The district list is bkkDistricts.js.
import { BKK_DISTRICTS } from './bkkDistricts.js';

export const MY_DISTRICT_KEY = 'my-district';
export const CAMERA_SHOWN = 12;

const KNOWN = new Set(BKK_DISTRICTS);

// The saved district, or null when none is saved, the saved name is not one of the 50, or storage is blocked
export function readMyDistrict() {
  try {
    const name = globalThis.localStorage?.getItem(MY_DISTRICT_KEY);
    return name && KNOWN.has(name) ? name : null;
  } catch {
    return null;
  }
}

// Saves the district; a blocked storage (private window, disabled site data) is ignored
export function writeMyDistrict(name) {
  try {
    globalThis.localStorage?.setItem(MY_DISTRICT_KEY, name);
  } catch {}
}

// Flood points, deepest water first (a copy; the input is not changed). Points with no depth go last.
export function deepestFirst(points) {
  return [...(points || [])].sort((a, b) => (b.level_cm ?? -Infinity) - (a.level_cm ?? -Infinity));
}

// The camera thumbnails to draw: the first 12, or all when the visitor asked for all
export function visibleCameras(cams, showAll) {
  const list = cams || [];
  return showAll ? list : list.slice(0, CAMERA_SHOWN);
}
