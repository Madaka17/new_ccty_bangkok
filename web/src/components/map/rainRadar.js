// RainViewer rain radar on the traffic map: the last 2 hours of radar frames (plus the short forecast when
// RainViewer sends one), one raster layer per frame under the traffic lines. Only the shown frame has opacity,
// so stepping through time never flickers: every frame's tiles are already loaded.
import { useEffect, useMemo, useRef, useState } from 'react';
import { fetchJson } from '../../lib/api.js';

const ID_PREFIX = 'rain-radar-';
const STEP_MS = 600;     // time on each frame while playing
const HOLD_MS = 1500;    // pause on the newest frame before looping
const timeOf = (t) => new Date(t * 1000).toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' });

// Run fn once the style has its layers (traffic-forward is the anchor the radar sits under). A map whose
// tiles are still loading is not "style loaded", and 'load' fired long ago, so wait on 'styledata' instead.
// Returns the cleanup; the latest effect run always cancels the earlier wait, so the newest state wins.
function whenReady(map, fn) {
  const ready = () => {
    try {
      return !!map.getLayer('traffic-forward');
    } catch {
      return false;
    }
  };
  const run = () => {
    if (ready()) fn();
    else map.once('styledata', run);
  };
  run();
  return () => {
    try {
      map.off('styledata', run);
    } catch {
      /* map already removed */
    }
  };
}

// Make the map hold exactly these frames, with only the shown one visible at `opacity`
function syncFrames(map, frames, index, show, opacity) {
  const want = new Set(frames.map((f) => f.id));
  // Frames no longer listed go away: layer before its source
  (map.getStyle()?.layers || []).forEach((l) => {
    if (l.id.startsWith(ID_PREFIX) && !want.has(l.id)) {
      map.removeLayer(l.id);
      if (map.getSource(l.id)) map.removeSource(l.id);
    }
  });
  frames.forEach((f, i) => {
    if (!map.getSource(f.id)) {
      // maxzoom 7: RainViewer free tiles stop at z7; MapLibre scales them up past that without error tiles
      map.addSource(f.id, { type: 'raster', tiles: [f.url], tileSize: 256, maxzoom: 7, attribution: '© RainViewer' });
    }
    if (!map.getLayer(f.id)) {
      map.addLayer({ id: f.id, type: 'raster', source: f.id, paint: { 'raster-opacity': 0, 'raster-fade-duration': 0 } }, 'traffic-forward');
    }
    const o = show && i === index ? opacity : 0;
    if (map.getPaintProperty(f.id, 'raster-opacity') !== o) map.setPaintProperty(f.id, 'raster-opacity', o);
    const v = show ? 'visible' : 'none';
    if (map.getLayoutProperty(f.id, 'visibility') !== v) map.setLayoutProperty(f.id, 'visibility', v);
  });
}

export function useRainRadar(mapRef, isActive) {
  const [showRainRadar, setShowRainRadar] = useState(true);
  const [radarOpacity, setRadarOpacity] = useState(0.65);
  const [frames, setFrames] = useState([]);       // [{ id, time, url, forecast }], oldest first
  const [radarIndex, setRadarIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const idsRef = useRef({ next: 0, byPath: {} }); // a path keeps its layer id across refreshes
  const framesRef = useRef([]);
  const indexRef = useRef(0);
  framesRef.current = frames;
  indexRef.current = radarIndex;

  // Fetch RainViewer frames every minute
  useEffect(() => {
    if (!isActive) return;
    let alive = true;
    const fetchRadar = () => {
      fetchJson('https://api.rainviewer.com/public/weather-maps.json', 'rain_radar')
        .then((data) => {
          if (!alive || !data?.host || !data?.radar?.past?.length) return;
          const ids = idsRef.current;
          const make = (f, forecast) => {
            if (!(f.path in ids.byPath)) ids.byPath[f.path] = ids.next++;
            // Color 2: smooth radar colors
            return { id: `${ID_PREFIX}${ids.byPath[f.path]}`, time: f.time, url: `${data.host}${f.path}/256/{z}/{x}/{y}/2/1_1.png`, forecast };
          };
          const next = [...data.radar.past.map((f) => make(f, false)), ...(data.radar.nowcast || []).map((f) => make(f, true))];
          const old = framesRef.current;
          // Same frames as before: change nothing
          if (next.length === old.length && next.every((f, i) => f.id === old[i].id)) return;
          const pastOf = (list) => list.filter((f) => !f.forecast).length - 1;
          const shown = old[indexRef.current];
          const wasNow = !shown || indexRef.current === pastOf(old);
          // Following "now" keeps following it; a hand-picked time stays on that frame while it is listed
          let idx = wasNow ? -1 : next.findIndex((f) => f.id === shown.id);
          if (idx < 0) idx = pastOf(next);
          setFrames(next);
          setRadarIndex(idx);
        })
        .catch((err) => console.warn('[RainViewer]', err));
    };
    fetchRadar();
    const interval = setInterval(fetchRadar, 60000);
    return () => {
      alive = false;
      clearInterval(interval);
    };
  }, [isActive]);

  // Put the frames on the map. Re-runs when the map is re-created (isActive) and on every state change;
  // whenReady waits for the style, and the latest run cancels the earlier wait, so no update is lost.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !frames.length) return;
    return whenReady(map, () => {
      try {
        syncFrames(map, frames, radarIndex, showRainRadar, radarOpacity);
      } catch (e) {
        console.warn('[map] rain radar error:', e);
      }
    });
  }, [isActive, frames, radarIndex, showRainRadar, radarOpacity]);

  // Playback: step every 600 ms, hold 1.5 s on the newest frame, loop. Never starts by itself.
  useEffect(() => {
    if (!playing) return;
    if (!isActive || !showRainRadar || frames.length < 2) {
      setPlaying(false);
      return;
    }
    const last = frames.length - 1;
    const t = setTimeout(() => setRadarIndex((i) => (i >= last ? 0 : i + 1)), radarIndex >= last ? HOLD_MS : STEP_MS);
    return () => clearTimeout(t);
  }, [playing, isActive, showRainRadar, frames, radarIndex]);

  const radarPlaying = playing;
  const setRadarPlaying = (v) => {
    const on = typeof v === 'function' ? v(playing) : v;
    // Play from the oldest frame when it is pressed on the newest one
    if (on && frames.length && radarIndex >= frames.length - 1) setRadarIndex(0);
    setPlaying(!!on);
  };

  const shown = frames[radarIndex];
  const pastCount = useMemo(() => frames.filter((f) => !f.forecast).length, [frames]);
  return {
    showRainRadar,
    setShowRainRadar,
    radarOpacity,
    setRadarOpacity,
    radarTime: shown ? timeOf(shown.time) : null,
    radarFrames: frames.length,
    radarIndex,
    setRadarIndex,
    radarPlaying,
    setRadarPlaying,
    radarIsForecast: !!shown?.forecast,
    radarIsNow: !!shown && !shown.forecast && radarIndex === pastCount - 1,
  };
}
