import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchWeatherNow } from './api.js';
import { forcedScene, weatherScene, fxAllowed, readPref, writePref } from './weatherFx.js';

const POLL_MS = 10 * 60 * 1000;
const REDUCED_QUERY = '(prefers-reduced-motion: reduce)';

// The viewer's spot, only when the browser already granted location. Never prompts.
async function grantedSpot() {
  try {
    const perm = await navigator.permissions?.query({ name: 'geolocation' });
    if (perm?.state !== 'granted' || !navigator.geolocation) return null;
  } catch {
    return null;
  }
  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ lat: Number(p.coords.latitude.toFixed(2)), lng: Number(p.coords.longitude.toFixed(2)) }),
      () => resolve(null),
      { timeout: 8000, maximumAge: 600000 },
    );
  });
}

// Weather background state for the page: the scene to draw, whether effects may run, and the on/off choice.
// Keeps the last good weather reading when a fetch fails (no badge flicker, no retry loop).
export default function useWeatherScene() {
  const [pref, setPrefState] = useState(() => readPref());
  const [now, setNow] = useState(null);
  const [reducedMotion, setReducedMotion] = useState(() =>
    typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia(REDUCED_QUERY).matches,
  );
  const [battery, setBattery] = useState(null);
  const saveData = typeof navigator !== 'undefined' && !!navigator.connection?.saveData;

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return undefined;
    const mq = window.matchMedia(REDUCED_QUERY);
    const onChange = (e) => setReducedMotion(e.matches);
    mq.addEventListener?.('change', onChange);
    return () => mq.removeEventListener?.('change', onChange);
  }, []);

  useEffect(() => {
    let alive = true;
    let bat = null;
    const update = () => alive && setBattery({ level: bat.level, charging: bat.charging });
    navigator.getBattery?.().then((b) => {
      if (!alive) return;
      bat = b;
      update();
      b.addEventListener('levelchange', update);
      b.addEventListener('chargingchange', update);
    }).catch(() => {});
    return () => {
      alive = false;
      bat?.removeEventListener('levelchange', update);
      bat?.removeEventListener('chargingchange', update);
    };
  }, []);

  useEffect(() => {
    let alive = true;
    let spot = null;
    const load = () => {
      fetchWeatherNow(spot?.lat, spot?.lng)
        .then((d) => { if (alive && d) setNow(d); })
        .catch(() => {});
    };
    load();   // Bangkok centre first; the viewer's own spot replaces it when location is already granted
    grantedSpot().then((p) => { if (alive && p) { spot = p; load(); } });
    const id = setInterval(load, POLL_MS);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  const setPref = useCallback((value) => {
    writePref(value);
    setPrefState(value === 'off' ? 'off' : 'on');
  }, []);

  const scene = useMemo(() => forcedScene(window.location.search) ?? weatherScene(now), [now]);
  const allowed = fxAllowed({ pref, reducedMotion, saveData, battery });

  return { scene, allowed, pref, setPref };
}
