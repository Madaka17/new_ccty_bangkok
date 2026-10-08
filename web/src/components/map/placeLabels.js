// "อาคารและสถานที่" on the traffic map: flat building footprints, POI name labels from the vector tiles in view
// and click-for-info on any building.
import { useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import { POI_MAX, POI_MIN_ZOOM, POI_TIER_MAX, poiKindOf, poiTierOf } from './places.js';
import { esc } from './markers.js';

export function usePlaceLabels(mapRef) {
  // Building details: flat footprints in 2D, POI name labels (DOM markers) and click-for-info on any building
  const [showPlaces, setShowPlaces] = useState(false);

  const showPlacesRef = useRef(false);
  const poiMarkersRef = useRef([]);

  // Building details toggle: 2D footprints + POI labels + click info. Labels are rebuilt on every
  // moveend from the vector tiles in view (rank = OpenMapTiles importance, lower is bigger).
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    showPlacesRef.current = showPlaces;
    const clearPois = () => {
      for (const m of poiMarkersRef.current) m.remove();
      poiMarkersRef.current = [];
    };
    let lastSig = '';
    const drawPois = () => {
      if (!showPlacesRef.current || map.getZoom() < POI_MIN_ZOOM || !map.getLayer('poi-pts')) {
        clearPois();
        lastSig = '';
        return;
      }
      const raw = map.queryRenderedFeatures({ layers: ['poi-pts'] });
      // same POIs in the same place as last time (tiles unchanged): keep the markers as they are
      const c = map.getCenter();
      const sig = `${raw.length}|${map.getZoom().toFixed(2)}|${c.lng.toFixed(5)},${c.lat.toFixed(5)}`;
      if (sig === lastSig) return;
      lastSig = sig;
      clearPois();
      const seen = new Set();
      const feats = raw
        .map((f) => ({ p: f.properties, c: f.geometry?.coordinates }))
        .filter((f) => f.c && f.p.name && poiKindOf(f.p))
        .map((f) => ({ ...f, tier: poiTierOf(f.p) }))
        .sort((a, b) => a.tier - b.tier || (a.p.rank ?? 99) - (b.p.rank ?? 99));
      const perTier = [0, 0, 0];
      const placed = [];   // screen positions of labels already drawn: skip one that would overlap
      for (const f of feats) {
        if (poiMarkersRef.current.length >= POI_MAX) break;
        if (perTier[f.tier] >= POI_TIER_MAX[f.tier]) continue;
        const key = `${f.p.name}|${Math.round(f.c[0] * 2000)}|${Math.round(f.c[1] * 2000)}`;
        if (seen.has(key)) continue;
        seen.add(key);
        const pt = map.project(f.c);
        if (placed.some((q) => Math.abs(q.x - pt.x) < 110 && Math.abs(q.y - pt.y) < 22)) continue;
        placed.push(pt);
        perTier[f.tier] += 1;
        const [icon, kindTh, color] = poiKindOf(f.p);
        const nameEn = f.p['name:en'] || f.p.name_en;
        const el = document.createElement('button');
        el.type = 'button';
        el.className = 'poi-label';
        el.style.cssText = `display:flex;align-items:center;gap:3px;max-width:170px;padding:2px 6px 2px 4px;border-radius:999px;background:rgba(255,255,255,.92);border:1.5px solid ${color};color:#0f172a;font:500 11px/1.2 var(--font-sans);box-shadow:0 1px 3px rgba(15,23,42,.25);cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis`;
        el.innerHTML = `<span style="font-size:12px">${icon}</span><span style="overflow:hidden;text-overflow:ellipsis">${esc(f.p.name)}</span>`;
        el.title = `${kindTh}: ${f.p.name}`;
        const popup = new maplibregl.Popup({ offset: 12, closeButton: true, maxWidth: '260px' }).setHTML(
          `<div style="font-size:13px;line-height:1.4"><b>${esc(f.p.name)}</b>${nameEn ? `<br><span style="color:#64748b">${esc(nameEn)}</span>` : ''}` +
            `<br><span style="color:${color};font-weight:600">${icon} ${kindTh}</span>${f.p.subclass && f.p.subclass !== f.p.class ? ` <span style="color:#64748b">· ${esc(f.p.subclass)}</span>` : ''}` +
            '<br><span style="color:#94a3b8;font-size:11px">ข้อมูล OpenStreetMap / OpenFreeMap</span></div>'
        );
        poiMarkersRef.current.push(new maplibregl.Marker({ element: el, anchor: 'bottom', offset: [0, -4] }).setLngLat(f.c).setPopup(popup).addTo(map));
      }
    };
    const onBuildingClick = (e) => {
      if (!showPlacesRef.current) return;
      const layers = ['buildings-3d', 'buildings-2d'].filter((id) => map.getLayer(id));
      const hit = map.queryRenderedFeatures(e.point, { layers })[0];
      if (!hit) return;
      const h = Number(hit.properties.render_height ?? 0);
      const base = Number(hit.properties.render_min_height ?? 0);
      const floors = h > 0 ? Math.max(1, Math.round(h / 3.2)) : null;
      // the nearest named POI inside ~40 px is very likely this building's name
      const near = map.queryRenderedFeatures([[e.point.x - 40, e.point.y - 40], [e.point.x + 40, e.point.y + 40]], { layers: ['poi-pts'] })
        .filter((f) => f.properties.name && poiKindOf(f.properties))
        .sort((a, b) => poiTierOf(a.properties) - poiTierOf(b.properties) || (a.properties.rank ?? 99) - (b.properties.rank ?? 99))[0];
      const kind = near && poiKindOf(near.properties);
      new maplibregl.Popup({ offset: 6, closeButton: true, maxWidth: '260px' })
        .setLngLat(e.lngLat)
        .setHTML(
          `<div style="font-size:13px;line-height:1.45"><b>${near ? esc(near.properties.name) : 'อาคาร'}</b>` +
            (kind ? `<br><span style="color:${kind[2]};font-weight:600">${kind[0]} ${kind[1]}</span>` : '') +
            (h > 0 ? `<br>สูงประมาณ <b>${Math.round(h)} ม.</b> (~${floors} ชั้น)${base > 0 ? ` · ยกจากพื้น ${Math.round(base)} ม.` : ''}` : '<br><span style="color:#64748b">ไม่มีข้อมูลความสูง</span>') +
            '<br><span style="color:#94a3b8;font-size:11px">ข้อมูล OpenStreetMap</span></div>'
        )
        .addTo(map);
    };
    const apply = () => {
      if (map.getLayer('buildings-2d')) map.setLayoutProperty('buildings-2d', 'visibility', showPlaces ? 'visible' : 'none');
      if (showPlaces && map.getZoom() < POI_MIN_ZOOM) map.easeTo({ zoom: POI_MIN_ZOOM, duration: 700 });
      drawPois();
    };
    // idle fires each time the map finishes rendering (also when late tiles come in); moveend covers pans
    const onIdle = () => drawPois();
    // getLayer = the style JSON is applied (isStyleLoaded() is false whenever tiles are still loading)
    if (map.getLayer('poi-pts')) apply();
    else map.once('styledata', apply);
    map.on('idle', onIdle);
    map.on('moveend', onIdle);
    map.on('click', onBuildingClick);
    return () => {
      map.off('idle', onIdle);
      map.off('moveend', onIdle);
      map.off('click', onBuildingClick);
      clearPois();
    };
  }, [showPlaces]);
  return { showPlaces, setShowPlaces };
}
