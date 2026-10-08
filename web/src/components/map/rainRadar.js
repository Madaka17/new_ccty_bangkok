// RainViewer rain radar on the traffic map: the newest radar frame every minute, drawn under the traffic lines.
import { useEffect, useState } from 'react';

export function useRainRadar(mapRef, isActive) {
  const [showRainRadar, setShowRainRadar] = useState(false);

  const [radarOpacity, setRadarOpacity] = useState(0.65);
  const [radarTileUrl, setRadarTileUrl] = useState(null);
  const [radarTime, setRadarTime] = useState(null);

  // Fetch RainViewer radar timestamp & tile url
  useEffect(() => {
    if (!isActive) return;
    let alive = true;
    const fetchRadar = () => {
      fetch('https://api.rainviewer.com/public/weather-maps.json')
        .then((res) => {
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          return res.json();
        })
        .then((data) => {
          if (!alive || !data?.host || !data?.radar?.past?.length) return;
          const latest = data.radar.past[data.radar.past.length - 1];
          // Color 2: smooth radar colors
          const url = `${data.host}${latest.path}/256/{z}/{x}/{y}/2/1_1.png`;
          setRadarTileUrl(url);
          const d = new Date(latest.time * 1000);
          setRadarTime(d.toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' }));
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

  // Sync Rain Radar tile layer to MapLibre with maxzoom: 7 (prevents Zoom Level Not Supported)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !radarTileUrl) return;

    const applyRadar = () => {
      const sourceId = 'rain-radar-source';
      const layerId = 'rain-radar-layer';

      const existingSource = map.getSource(sourceId);
      if (existingSource) {
        if (existingSource.setTiles) {
          existingSource.setTiles([radarTileUrl]);
        }
      } else {
        try {
          map.addSource(sourceId, {
            type: 'raster',
            tiles: [radarTileUrl],
            tileSize: 256,
            maxzoom: 7, // CRITICAL: RainViewer free tiles are z<=7. MapLibre scales up smoothly for z>7 without error boxes!
            attribution: '© RainViewer',
          });
        } catch (e) {
          console.warn('[map] addSource error:', e);
        }
      }

      if (!map.getLayer(layerId)) {
        const beforeLayer = map.getLayer('traffic-forward') ? 'traffic-forward' : undefined;
        try {
          map.addLayer(
            {
              id: layerId,
              type: 'raster',
              source: sourceId,
              paint: {
                'raster-opacity': radarOpacity,
                'raster-fade-duration': 300,
              },
            },
            beforeLayer
          );
        } catch (e) {
          console.warn('[map] addLayer error:', e);
        }
      }

      if (map.getLayer(layerId)) {
        map.setLayoutProperty(layerId, 'visibility', showRainRadar ? 'visible' : 'none');
        map.setPaintProperty(layerId, 'raster-opacity', radarOpacity);
      }
    };

    if (map.isStyleLoaded()) {
      applyRadar();
    } else {
      map.once('load', applyRadar);
    }
  }, [radarTileUrl, showRainRadar, radarOpacity]);
  return { showRainRadar, setShowRainRadar, radarOpacity, setRadarOpacity, radarTime };
}
