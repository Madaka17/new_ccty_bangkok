// The traffic map's MapLibre style: OpenStreetMap base tiles, Longdo traffic lines, rail, buildings and POIs.
// Traffic line widths follow Longdo's own style (r_char = road class, 1 = biggest)
export const CLASS = ['to-number', ['coalesce', ['get', 'r_char'], 4]];
export const LINE_WIDTH = ['interpolate', ['linear'], ['zoom'], 9, 1.5, 12, ['case', ['<=', CLASS, 2], 4, ['<=', CLASS, 5], 2.5, 1.5], 14, ['case', ['<=', CLASS, 2], 7, ['<=', CLASS, 5], 4, 2.5]];
export const OFFSET = (dir) => ['interpolate', ['linear'], ['zoom'], 9, 1.5 * dir, 13, 3 * dir];
export function mapStyle() {
  const origin = window.location.origin;
  return {
    version: 8,
    sources: {
      base: { type: 'raster', tiles: [`${origin}/api/tiles/base/{z}/{x}/{y}.png`], tileSize: 256, maxzoom: 19, attribution: '© OpenStreetMap contributors' },
      traffic: { type: 'vector', tiles: [`${origin}/api/traffic/tile/{z}/{x}/{y}.pbf`], minzoom: 5, maxzoom: 12, attribution: 'Traffic © Longdo' },
      // OpenFreeMap (OpenMapTiles schema) only for the 3D building footprints + heights
      omt: { type: 'vector', url: 'https://tiles.openfreemap.org/planet', attribution: '© OpenFreeMap' },
      // BTS / MRT / ARL / SRT Red lines + stations, a static snapshot of OSM route relations
      rail: { type: 'geojson', data: `${origin}/rail_bkk.geojson`, attribution: 'Rail © OpenStreetMap' },
    },
    layers: [
      { id: 'base', type: 'raster', source: 'base', paint: { 'raster-saturation': -0.45, 'raster-brightness-min': 0.05, 'raster-contrast': -0.08 } },
      // Flat building footprints for the "รายละเอียดสิ่งปลูกสร้าง" toggle
      {
        id: 'buildings-2d',
        type: 'fill',
        source: 'omt',
        'source-layer': 'building',
        minzoom: 14,
        layout: { visibility: 'none' },
        paint: {
          'fill-color': ['interpolate', ['linear'], ['coalesce', ['get', 'render_height'], 8], 0, '#dbe4ee', 40, '#b6c4d6', 120, '#8fa3bd', 250, '#6b82a3'],
          'fill-opacity': 0.55,
          'fill-outline-color': '#64748b',
        },
      },
      {
        id: 'traffic-forward',
        type: 'line',
        source: 'traffic',
        'source-layer': 'traffic',
        filter: ['!=', ['get', 'fillcolor'], ''],
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-opacity': 0.9, 'line-color': ['concat', '#', ['get', 'fillcolor']], 'line-width': LINE_WIDTH, 'line-offset': OFFSET(-1) },
      },
      {
        id: 'traffic-reverse',
        type: 'line',
        source: 'traffic',
        'source-layer': 'traffic',
        filter: ['!=', ['get', 'fillcolor_r'], ''],
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-opacity': 0.9, 'line-color': ['concat', '#', ['get', 'fillcolor_r']], 'line-width': LINE_WIDTH, 'line-offset': OFFSET(1) },
      },
      // Rail: a white casing under each coloured line so it reads apart from the traffic colours
      { id: 'rail-casing', type: 'line', source: 'rail', filter: ['==', ['get', 'kind'], 'line'], layout: { visibility: 'none', 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#ffffff', 'line-width': ['interpolate', ['linear'], ['zoom'], 9, 4, 14, 8] } },
      { id: 'rail-line', type: 'line', source: 'rail', filter: ['==', ['get', 'kind'], 'line'], layout: { visibility: 'none', 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': ['get', 'colour'], 'line-width': ['interpolate', ['linear'], ['zoom'], 9, 2, 14, 4.5] } },
      {
        id: 'rail-station',
        type: 'circle',
        source: 'rail',
        filter: ['==', ['get', 'kind'], 'station'],
        layout: { visibility: 'none' },
        paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 2.5, 14, 6], 'circle-color': '#ffffff', 'circle-stroke-color': ['get', 'colour'], 'circle-stroke-width': ['interpolate', ['linear'], ['zoom'], 10, 1.5, 14, 3] },
      },
      // 3D buildings (OpenFreeMap heights) from zoom 15, drawn over the flat buildings baked into the base
      // raster; the map tilts itself when zoomed in (auto-tilt effect). Overlay layers (risk layers,
      // heatmaps) are inserted below it.
      {
        id: 'buildings-3d',
        type: 'fill-extrusion',
        source: 'omt',
        'source-layer': 'building',
        minzoom: 15,
        filter: ['!', ['coalesce', ['get', 'hide_3d'], false]],
        paint: {
          'fill-extrusion-color': ['interpolate', ['linear'], ['coalesce', ['get', 'render_height'], 8], 0, '#cbd5e1', 40, '#94a3b8', 120, '#64748b', 250, '#334155'],
          'fill-extrusion-height': ['interpolate', ['linear'], ['zoom'], 15, 0, 15.6, ['coalesce', ['get', 'render_height'], 8]],
          'fill-extrusion-base': ['interpolate', ['linear'], ['zoom'], 15, 0, 15.6, ['coalesce', ['get', 'render_min_height'], 0]],
          'fill-extrusion-opacity': 0.85,
        },
      },
      // Invisible points so the OpenFreeMap POIs (hospitals, schools, malls, temples ...) are loaded
      // and queryable; their Thai names are drawn as DOM markers (the style has no glyphs for text)
      { id: 'poi-pts', type: 'circle', source: 'omt', 'source-layer': 'poi', minzoom: 14, paint: { 'circle-radius': 1, 'circle-opacity': 0 } },
    ],
  };
}
