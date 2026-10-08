// The Leaflet map of Thailand: base layers, faults, quakes, stations, the viewer's pin. A classic script (not a module): every js/ file shares one global scope and index.html loads them in order.

/* ============================= REAL THAILAND MAP (Leaflet, real lat/lng, switchable basemap) =============================
   Basemap choices are both genuinely free and ToS-compliant with no API key:
   - OpenStreetMap street tiles (dark-filtered via CSS to match the theme)
   - Esri World Imagery satellite tiles (shown true-color, not filtered)
   NOTE: real Google Maps satellite tiles are NOT wired in here -- Google's tile
   endpoints require a billed Maps Platform API key to use per their Terms of
   Service; hot-linking the undocumented bare tile URLs without one is a ToS
   violation. Esri World Imagery is the closest free, legitimate equivalent. */
let leafletMap = null, mapLayer = null, worldQuakeLayer = null, worldFaultLayer = null, nodesSituationLayer = null, layersControl = null;
let worldLayersLoaded = false;

// Deliberately no blue anywhere in this ramp -- blue is reserved for our own
// simulated sensor stations, so a real earthquake marker is never visually
// confusable with one of ours.
const MAG_COLOR_STOPS = [
  {max:3.0, color:'#8a94a6'}, {max:4.0, color:'#e0c341'}, {max:5.0, color:'#fab219'},
  {max:6.0, color:'#ec835a'}, {max:99, color:'#d03b3b'},
];
function magColor(mag){
  const m = mag==null ? 0 : mag;
  return (MAG_COLOR_STOPS.find(s=>m<s.max) || MAG_COLOR_STOPS[MAG_COLOR_STOPS.length-1]).color;
}
function magRadius(mag){ return 3.5 + Math.max(0, (mag||2.5) - 2.0) * 2.2; }

function ensureMap(){
  if(leafletMap && document.body.contains(leafletMap.getContainer())) return leafletMap;
  const savedView = window.__mapView;
  leafletMap = L.map('mapEl', {zoomControl:true, attributionControl:true})
    .setView(savedView ? savedView.center : [13.7, 101.0], savedView ? savedView.zoom : 5.3);
  leafletMap.on('moveend', ()=>{ window.__mapView = {center: leafletMap.getCenter(), zoom: leafletMap.getZoom()}; });

  const streetLayer = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19, className: 'osm-dark-tiles',
  });
  const satelliteLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
    attribution: 'Imagery &copy; <a href="https://www.esri.com/">Esri</a>, Maxar, Earthstar Geographics',
    maxZoom: 19,
  });
  const baseLayers = {'แผนที่ถนน (OpenStreetMap)': streetLayer, 'ภาพถ่ายดาวเทียม (Esri)': satelliteLayer};
  (window.__mapBase === 'satellite' ? satelliteLayer : streetLayer).addTo(leafletMap);
  leafletMap.on('baselayerchange', (e)=>{ window.__mapBase = e.name.includes('ดาวเทียม') ? 'satellite' : 'street'; });

  mapLayer = L.layerGroup().addTo(leafletMap);
  worldFaultLayer = L.layerGroup(); // added to map lazily once data & the user's toggle allow it
  worldQuakeLayer = L.layerGroup();
  nodesSituationLayer = L.layerGroup();
  const overlays = {
    'รอยเลื่อนทั่วโลก (GEM GAF-DB)': worldFaultLayer,
    'แผ่นดินไหวจริงทั่วโลก + ภูมิภาค (USGS/EMSC/GEOFON/TMD)': worldQuakeLayer,
    'โหนดตรวจวัด ENVIRO': nodesSituationLayer,
  };
  worldFaultLayer.addTo(leafletMap);
  worldQuakeLayer.addTo(leafletMap);
  nodesSituationLayer.addTo(leafletMap);
  layersControl = L.control.layers(baseLayers, overlays, {position:'topright', collapsed:true}).addTo(leafletMap);

  // The map is often created in the same tick that its container goes from
  // `display:none` to visible (e.g. right after login) -- Leaflet then caches
  // a stale zero-size layout and throws `_leaflet_pos` errors on the first
  // interaction. A deferred invalidateSize() forces it to re-measure once the
  // browser has actually laid the now-visible container out.
  setTimeout(()=>{ if(leafletMap) leafletMap.invalidateSize(); }, 0);

  loadWorldLayers();
  return leafletMap;
}

async function loadWorldLayers(){
  if(worldLayersLoaded) return;
  worldLayersLoaded = true;
  try{
    const faultsData = await api('/api/world/faults');
    if(faultsData.ready){
      const renderer = L.canvas();
      faultsData.faults.forEach(f=>{
        if(f.points.length < 2) return;
        L.polyline(f.points, {renderer, color:'#9085e9', weight:1, opacity:.55})
          .bindPopup(`<b>${f.name || 'ไม่ระบุชื่อ (Unnamed)'}</b>${f.slip_type? '<br>ประเภท: '+f.slip_type:''}<br><span style="color:#8a94a6;">GEM GAF-DB</span>`)
          .addTo(worldFaultLayer);
      });
      const hint = document.getElementById('worldFaultHint');
      if(hint) hint.textContent = `${faultsData.count.toLocaleString()} รอยเลื่อน · ${faultsData.source}`;
    } else {
      setTimeout(()=>{ worldLayersLoaded=false; loadWorldLayers(); }, 4000);
      worldLayersLoaded = true;
    }
  }catch(e){ worldLayersLoaded = false; }

  await refreshWorldQuakes();
  clearInterval(window.__worldQuakePoll);
  window.__worldQuakePoll = setInterval(refreshWorldQuakes, 60000);

  refreshWorldQuakeHistoryStats();
  clearInterval(window.__worldQuakeHistoryPoll);
  window.__worldQuakeHistoryPoll = setInterval(refreshWorldQuakeHistoryStats, 300000);

  refreshSituationNodes();
  clearInterval(window.__situationNodesPoll);
  window.__situationNodesPoll = setInterval(refreshSituationNodes, 15000);
}

// Node markers on the main สถานการณ์ map (toggleable overlay -- see
// ensureMap's `overlays`) -- the same nodes shown on the สถานีตรวจวัด page,
// so a viewer can see where they are relative to an active event without
// switching pages.
let situationNodesAutoFitted = false;

async function refreshSituationNodes(){
  if(!nodesSituationLayer) return;
  let list;
  try{ list = await api('/api/nodes'); }catch(e){ return; }
  nodesSituationLayer.clearLayers();
  const pts = [];
  // jitterCoincidentNodes (defined near paintNodesMap below -- hoisted, so
  // fine to call from here) keeps this map's dots matching the same nodes
  // the สถานีตรวจวัด page's own map and table show, even when 2+ nodes
  // share exact coordinates and would otherwise hide one another.
  jitterCoincidentNodes(list).forEach(n=>{
    pts.push([n.renderLat, n.renderLng]);
    const color = n.online ? '#5fe05f' : '#63a4ee'; // เขียว=ออนไลน์, ฟ้า=ออฟไลน์ -- อนุสัญญาสีเดียวกับ "สถานี ENVIRO" ใน situationShell()'s legend
    const marker = L.circleMarker([n.renderLat, n.renderLng], {
      radius: 6, color, weight: 2, fillColor: color, fillOpacity: .8,
    }).bindPopup(
      `<b>${n.name || n.node_id}</b><br>`+
      `${n.node_id} · ${n.online ? 'ออนไลน์' : 'ออฟไลน์'}`+
      (n.battery_pct != null ? ` · แบต ${n.battery_pct}%` : '')
    );
    // Same permanent รหัสโหนด label as the สถานีตรวจวัด page's own map
    // (paintNodesMap) -- keeps a node's identity on this map unambiguous
    // too, not just its click-popup, for consistency between both pages.
    marker.bindTooltip(n.node_id, {permanent: true, direction: 'top', offset: [0, -6], className: 'node-map-label'});
    marker.addTo(nodesSituationLayer);
  });
  // Matches แผนที่โหนด's own zoom/fit behaviour (paintNodesMap) on this map
  // too, so a viewer isn't left looking at all of Southeast Asia to find a
  // cluster of dots that page already shows nicely framed -- but only ONCE
  // (first time nodes load), and only if no active event has already
  // claimed the view (see autoFitMapToEvent/lastAutoFitEventId): an event's
  // own fit always wins, and this must not keep yanking the view back to
  // node bounds on every ~15s poll once someone has panned/zoomed away.
  if(!situationNodesAutoFitted && lastAutoFitEventId === null && leafletMap && pts.length){
    situationNodesAutoFitted = true;
    if(pts.length === 1) leafletMap.setView(pts[0], 9);
    else leafletMap.fitBounds(L.latLngBounds(pts), {padding:[70,70], maxZoom:9});
  }
}

let lastTopQuakeId = null;

async function refreshWorldQuakes(){
  let quakeData;
  const rangeSel = document.getElementById('worldQuakeRange');
  const days = rangeSel ? rangeSel.value : 90;
  try{ quakeData = await api(`/api/world/earthquakes?days=${days}`); }
  catch(e){ return; }

  if(worldQuakeLayer) worldQuakeLayer.clearLayers();
  const quakes = quakeData.quakes || [];
  const SOURCE_STYLE = {
    TMD: {dashArray: null, weight: 2.5},          // TMD = Thailand's own network, drawn with a bolder ring
    USGS: {dashArray: null, weight: 1.5},
    EMSC: {dashArray: '2 2', weight: 1.5},
    GEOFON: {dashArray: '5 3', weight: 1.5},
  };
  quakes.forEach(q=>{
    const c = magColor(q.magnitude);
    const style = SOURCE_STYLE[q.source] || {dashArray: null, weight: 1.5};
    L.circleMarker([q.lat,q.lng], {
      radius: magRadius(q.magnitude), color: c, weight: style.weight, fillColor: c, fillOpacity:.5,
      dashArray: style.dashArray, className: q.is_recent ? 'quake-marker-recent' : '',
    }).bindPopup(
      `<b>M${q.magnitude!=null?q.magnitude.toFixed(1):'?'} — ${q.place||'ไม่ทราบตำแหน่ง'}</b>`+
      (q.is_recent? ` <span style="color:var(--status-critical);font-weight:600;">● กำลัง active / เพิ่งเกิด</span>` : '')+
      `<br>แหล่งข้อมูล: ${q.source}${q.source==='TMD'?' (กรมอุตุนิยมวิทยา — เครือข่ายในประเทศไทย)':q.regional?' (ภูมิภาคเอเชียตะวันออกเฉียงใต้)':' (เหตุการณ์สำคัญทั่วโลก)'}<br>`+
      `ความลึก ${q.depth_km!=null? Math.round(q.depth_km)+' กม.':'—'} · ${q.time_ms? new Date(q.time_ms).toLocaleString('th-TH'):'—'}`+
      (q.url? `<br><a href="${q.url}" target="_blank" rel="noopener" style="color:#63a4ee;">ดูรายละเอียด</a>` : '')+
      // Only makes sense with a real origin time to count travel-time from --
      // a handful of real feed rows come through with time_ms missing.
      (q.time_ms!=null? `<br><button type="button" class="btn" style="margin-top:6px;padding:5px 10px;font-size:13.5px;width:100%;" `+
        `onclick="viewRealQuakeWave(${q.lat},${q.lng},${q.magnitude!=null?q.magnitude:'null'},${q.depth_km!=null?q.depth_km:'null'},${q.time_ms},${JSON.stringify(q.place||'ไม่ทราบตำแหน่ง').replace(/"/g,'&quot;')})">`+
        `${icon('warnTri')} ดูคลื่นแผ่นดินไหว</button>` : '')
    ).addTo(worldQuakeLayer);
  });

  const hint = document.getElementById('worldQuakeHint');
  if(hint){
    const regionalCount = quakes.filter(q=>q.regional).length;
    const tmdCount = quakes.filter(q=>q.source==='TMD').length;
    const recentCount = quakes.filter(q=>q.is_recent).length;
    const rangeLabel = quakeData.days === 'realtime' ? 'Realtime' : ({90:'90 วัน',7:'7 วัน',1:'24 ชม.'}[quakeData.days] || `${quakeData.days} วัน`);
    hint.textContent = `${quakeData.count} เหตุการณ์จริงย้อนหลัง ${rangeLabel} (${regionalCount} ในภูมิภาคเอเชียตะวันออกเฉียงใต้ · ${tmdCount} จาก TMD ในประเทศไทย)`+
      `${recentCount? ` · ${recentCount} จุดกำลัง active/เพิ่งเกิด (กระพริบ)` : ''} · ${quakeData.connected?'เชื่อมต่อจริง':'ขาดการเชื่อมต่อบางส่วน'}`;
  }

  // Top-right ticker -- tied directly to the #worldQuakeRange condition
  // selected above the map: literally "the single most recent real event
  // within whatever window the user is currently browsing" (90d/7d/24h),
  // not a separately-prioritized "what's happening right now" indicator.
  // Picking the range dropdown re-fetches `quakes` already filtered to that
  // window (server-side, via ?days=), so sorting by time_ms and taking the
  // first entry is exactly "the latest occurrence under that time condition"
  // -- no extra prioritization (recency-flag, regional, magnitude fallback)
  // that could otherwise surface an event other than the truly-latest one.
  const ticker = document.getElementById('realQuakeTicker');
  if(!ticker) return;
  const rangeLabel = quakeData.days === 'realtime' ? 'สถานการณ์ปัจจุบัน (Realtime)' : ({90:'90 วันที่ผ่านมา',7:'7 วันที่ผ่านมา',1:'24 ชั่วโมงที่ผ่านมา'}[quakeData.days] || `${quakeData.days} วันที่ผ่านมา`);
  const nearest = quakes.filter(q=>q.time_ms!=null).sort((a,b)=>b.time_ms-a.time_ms)[0];
  if(!nearest){ ticker.hidden = true; return; }

  const moved = lastTopQuakeId && lastTopQuakeId !== nearest.id;
  lastTopQuakeId = nearest.id;
  const ago = nearest.time_ms ? Math.max(0, Math.round((Date.now()-nearest.time_ms)/60000)) : null;
  ticker.hidden = false;
  ticker.innerHTML = `
    <div class="tk-label">${nearest.is_recent? '🔴 ' : '🌍 '}แผ่นดินไหวจริงล่าสุด (${rangeLabel})</div>
    <div class="tk-mag" style="color:${magColor(nearest.magnitude)};">M${nearest.magnitude!=null?nearest.magnitude.toFixed(1):'?'}</div>
    <div class="tk-place">${nearest.place || 'ไม่ทราบตำแหน่ง'}</div>
    <div class="tk-meta">${nearest.source}${ago!=null? ' · '+(ago<60? ago+' นาทีที่แล้ว' : Math.round(ago/60)+' ชม.ที่แล้ว') : ''}</div>`;
  if(moved){ ticker.classList.remove('flash'); void ticker.offsetWidth; ticker.classList.add('flash'); }
}

// Proof that real earthquake events are actually accumulating permanently in
// SQLite (world_quake_history), not just displayed off the 5-minute live
// cache and discarded -- this is the groundwork the user asked for so a
// future Edge AI feature has real historical data to analyze/forecast from,
// not just whatever the last poll happened to return.
async function refreshWorldQuakeHistoryStats(){
  const el = document.getElementById('worldQuakeHistoryHint');
  if(!el) return;
  try{
    const stats = await api('/api/world/earthquakes/history-stats');
    const since = stats.collecting_since ? new Date(stats.collecting_since).toLocaleString('th-TH') : '–';
    const bySource = (stats.by_source||[]).map(s=>`${s.source} ${s.count.toLocaleString()}`).join(' · ');
    el.textContent = `บันทึกถาวรลง SQLite แล้ว ${stats.total_stored.toLocaleString()} เหตุการณ์ (${bySource}) — เริ่มสะสมตั้งแต่ ${since} เพื่อใช้วิเคราะห์แนวโน้มด้วย Edge AI ในอนาคต`;
  }catch(e){ el.textContent = 'ยังไม่มีข้อมูลสะสม'; }
}

// `dotColor` ties the pin's own center dot to the severity level AT that
// exact pin (see computeYouLevelForEvent in paintMap below) -- the pin
// itself, not just the side panel, now shows at a glance whether where you
// are is currently calm (grey/no color, no event) or under an active alert
// and how bad (green -> red, the same scale levelPillStyle uses everywhere
// else). The white teardrop shape and black outline stay constant so the
// pin is still readable against any basemap/zoom.
function youPinIcon(dotColor){
  const dot = dotColor || '#0a0d12';
  return L.divIcon({
    className: 'you-pin', html: `<svg width="22" height="30" viewBox="0 0 22 30" xmlns="http://www.w3.org/2000/svg">
      <path d="M11 0C4.9 0 0 4.9 0 11c0 8.3 11 19 11 19s11-10.7 11-19C22 4.9 17.1 0 11 0Z" fill="#fff" stroke="#0a0d12" stroke-width="1"/>
      <circle cx="11" cy="11" r="4" fill="${dot}"/>
    </svg>`,
    iconSize:[22,30], iconAnchor:[11,30],
  });
}
const IMPACT_LABELS = {1:'น้อยมาก', 2:'เล็กน้อย', 3:'ปานกลาง', 4:'รุนแรง', 5:'รุนแรงมาก', 6:'วิกฤต'};

/* ---- Level-specific guidance: rendered both on the normal 15s data refresh
   AND immediately (synchronously, no network round-trip) the instant a WS
   alert/alert-upgrade message arrives, so the recommendation text changes
   together with the alert sound instead of lagging behind it. ---- */
// `ev` here is already the pin-recomputed object (see getEvForGuidance) or
// null; `rawEv` is the actual event (or null), used only to tell "no event
// at all" apart from "there's an event but no location is set yet" --
// those need different messages, not the same idle "monitoring normally"
// text for both.
function renderLevelGuidance(ev, rawEv){
  const panel = document.getElementById('levelGuidancePanel');
  if(!panel) return;
  if(!rawEv){
    panel.innerHTML = `<div class="callout">${icon('check')}<div>ไม่มีคำแนะนำเร่งด่วนในขณะนี้ — เครือข่ายกำลังเฝ้าระวังตามปกติ</div></div>`;
    return;
  }
  if(!ev){
    panel.innerHTML = `<div class="callout" style="border-color:var(--status-info);background:var(--status-info-soft);">
      ${icon('pin')}
      <div>
        <div style="font-weight:600;margin-bottom:3px;">ยังไม่ได้ตั้งค่าตำแหน่งของคุณ</div>
        <div style="color:var(--ink-primary);">มีเหตุการณ์แผ่นดินไหวที่ระบบกำลังตรวจสอบอยู่ แต่ยังไม่ทราบตำแหน่งของคุณ จึงยังบอกระดับความรุนแรงเฉพาะจุดไม่ได้ — กดปุ่ม "ตำแหน่งที่ตั้ง" บนแผนที่แล้วใช้ GPS หรือกรอกพิกัดเอง</div>
      </div>
    </div>`;
    return;
  }
  const [bg, fg] = levelPillStyle(ev.level);
  panel.innerHTML = `
    <div class="callout" style="border-color:${fg};background:${bg};">
      ${icon('warnTri')}
      <div>
        <div style="font-weight:600;color:${fg};margin-bottom:3px;">ระดับ ${ev.level} — ${ev.level_name}</div>
        <div style="color:var(--ink-primary);">${ev.message}</div>
      </div>
    </div>`;
}

// text (levels 1-6) is the exact "ข้อความแจ้งเตือน" per level from the
// reference spec doc (ความรุนแรงที่คาด ณ ตำแหน่งผู้ใช้.docx) -- word for
// word, not a paraphrase, so this banner always shows the authoritative
// per-level information the doc defines. Level 0 (before any detection)
// isn't covered by the doc, so it keeps its own idle-state text.
const SAFETY_URGENCY = {
  0: {bg:'var(--surface-2)', fg:'var(--ink-muted)', text:'โหมดเฝ้าระวังปกติ — ไม่ต้องดำเนินการเพิ่มเติม แต่ควรทราบตำแหน่งที่กำบังใกล้ตัวไว้เสมอ'},
  1: {bg:'var(--status-good-soft)', fg:'#5fe05f', text:'ตรวจพบเหตุการณ์แผ่นดินไหว แต่ไม่คาดว่าจะมีผลกระทบ ณ ตำแหน่งของคุณ ระบบกำลังติดตามและตรวจสอบข้อมูล'},
  2: {bg:'var(--status-info-soft)', fg:'var(--status-info)', text:'คุณอาจรู้สึกแรงสั่นสะเทือนเล็กน้อย อยู่ห่างจากกระจก ชั้นวาง และสิ่งของที่อาจตก พร้อมติดตามการอัปเดต'},
  3: {bg:'var(--status-watch-soft)', fg:'var(--status-watch)', text:'คาดว่าจะรู้สึกแรงสั่นชัดเจน หยุดกิจกรรมเสี่ยงและไปยังจุดกำบังที่ใกล้ที่สุด เตรียมหมอบ–กำบัง–ยึดจับ'},
  4: {bg:'var(--status-warn-soft)', fg:'var(--status-warn)', text:'แรงสั่นอาจก่อความเสียหาย หมอบ–กำบัง–ยึดจับทันที อย่าวิ่งออกจากอาคารและห้ามใช้ลิฟต์'},
  5: {bg:'var(--status-critical-soft)', fg:'#ff8f8f', text:'คาดว่าแรงสั่นรุนแรงมาก ป้องกันศีรษะและลำคอทันที อยู่ในจุดกำบังจนหยุดสั่น และเตรียมรับอาฟเตอร์ช็อก'},
  6: {bg:'var(--status-extreme-soft)', fg:'#ffb8b8', text:'ภาวะวิกฤต รักษาชีวิตเป็นอันดับแรก หมอบ–กำบัง–ยึดจับ ห้ามเคลื่อนย้ายจนแรงสั่นหยุด หลังจากนั้นออกจากอาคารที่เสียหายและปฏิบัติตามคำสั่งทางการ'},
};
