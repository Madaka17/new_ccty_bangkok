import { useEffect, useState, useCallback } from 'react';

const FAV_KEY = 'bkk_cctv_favs';
const ACTIVE_KEY = 'bkk_cctv_active_slots';
const NAME_KEY = 'bkk_cctv_user_name';
const DEFAULT_NAME = 'เพื่อนบ้าน';

function readJSON(key, fallback) {
  try {
    const v = localStorage.getItem(key);
    return v ? JSON.parse(v) : fallback;
  } catch {
    return fallback;
  }
}

function writeJSON(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {}
}

export function useFavorites() {
  const [favs, setFavs] = useState(() => new Set(readJSON(FAV_KEY, [])));
  useEffect(() => writeJSON(FAV_KEY, Array.from(favs)), [favs]);
  const toggle = useCallback((id) => {
    setFavs((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);
  return [favs, toggle];
}

export function useActiveCameras() {
  const [list, setList] = useState(() => readJSON(ACTIVE_KEY, []));
  useEffect(() => writeJSON(ACTIVE_KEY, list), [list]);
  const toggle = useCallback((id) => {
    setList((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id].slice(-9)));
  }, []);
  const remove = useCallback((id) => setList((prev) => prev.filter((x) => x !== id)), []);
  const clear = useCallback(() => setList([]), []);
  // Add several cameras at once (no toggling), keeping the newest 9
  const addMany = useCallback((ids) => {
    setList((prev) => [...prev.filter((x) => !ids.includes(x)), ...ids].slice(-9));
  }, []);
  return { active: list, toggle, remove, clear, addMany };
}

export function useUserName() {
  const [name, setName] = useState(() => {
    try {
      return localStorage.getItem(NAME_KEY) || DEFAULT_NAME;
    } catch {
      return DEFAULT_NAME;
    }
  });
  const save = useCallback((n) => {
    const v = (n || '').trim() || DEFAULT_NAME;
    setName(v);
    try {
      localStorage.setItem(NAME_KEY, v);
    } catch {}
  }, []);
  return [name, save];
}

export function greetingByHour(d = new Date()) {
  const h = d.getHours();
  if (h < 12) return 'สวัสดีตอนเช้า';
  if (h < 17) return 'สวัสดีตอนบ่าย';
  return 'สวัสดีตอนเย็น';
}

export function distanceKm(a, b) {
  const R = 6371;
  const dLat = ((b.lat - a.lat) * Math.PI) / 180;
  const dLon = ((b.lng - a.lng) * Math.PI) / 180;
  const s =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((a.lat * Math.PI) / 180) * Math.cos((b.lat * Math.PI) / 180) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(s));
}

// Province is a label, not a status: one neutral tone for every province
const NEUTRAL_TONE = 'bg-slate-100 text-slate-600 border border-slate-200';
export const PROVINCE_TONE = {
  กรุงเทพมหานคร: NEUTRAL_TONE,
  นนทบุรี: NEUTRAL_TONE,
  นครปฐม: NEUTRAL_TONE,
  สมุทรปราการ: NEUTRAL_TONE,
  ปทุมธานี: NEUTRAL_TONE,
};

// Traffic level of a camera (from the AI count / survey), shown as a pill on camera cards and video slots
export const CAM_LEVEL = {
  free: { text: 'ถนนโล่ง', cls: 'bg-emerald-50 text-emerald-700 border border-emerald-200', dot: '#059669' },
  moderate: { text: 'รถปานกลาง', cls: 'bg-amber-50 text-amber-700 border border-amber-200', dot: '#d97706' },
  heavy: { text: 'รถติดขัด', cls: 'bg-red-50 text-red-700 border border-red-200', dot: '#dc2626' },
};

export function camStatusText(st) {
  if (!st?.ts) return null;
  const m = Math.round((Date.now() / 1000 - st.ts) / 60);
  const ago = m < 1 ? 'เมื่อสักครู่' : m < 60 ? `${m} นาทีก่อน` : `${Math.round(m / 60)} ชม.ก่อน`;
  return `${st.source === 'count' ? 'นับต่อเนื่อง' : 'AI สุ่มดู'} · รถผ่าน ${st.rate_per_min} คัน/นาที · ในภาพ ${Math.round(st.visible)} คัน · ${ago}`;
}
