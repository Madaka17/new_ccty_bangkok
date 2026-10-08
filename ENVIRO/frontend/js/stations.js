// View 3: monitoring stations and nodes. A classic script (not a module): every js/ file shares one global scope and index.html loads them in order.

/* ============================= VIEW 3: MONITORING STATIONS ============================= *
 * Entirely driven by real hardware nodes (see server/routes/nodes.py +
 * firmware/prototype_node) -- no simulated-network content on this page any
 * more. With (currently) a single physical prototype connected, the
 * list/map below will just show that one row -- built to scale to more
 * without changes once more real nodes exist. */

let selectedNodeId = null;
let lastNodesList = []; // most recent /api/nodes fetch -- lets the edit-open/cancel handlers redraw the table instantly from cache instead of a network round-trip, and without disturbing an unrelated in-progress edit elsewhere in the list
let nodesMap = null, nodesMapLayer = null;

// "จัดการอุปกรณ์" (device management) mode -- while on, clicking the node
// map pins the currently-selected node's location instead of just panning.
// Neither real nor simulated nodes report their own GPS yet, so this is
// how a node's shown position gets set/corrected (see
// routes/nodes.py set_node_location) until real GPS hardware exists.
let deviceManagementMode = false;

function toggleDeviceManagementMode(){
  deviceManagementMode = !deviceManagementMode;
  const btn = document.getElementById('deviceMgmtToggle');
  const banner = document.getElementById('deviceMgmtBanner');
  const mapEl = document.getElementById('nodesMapEl');
  if(btn){
    btn.style.background = deviceManagementMode ? 'var(--accent-strong)' : '';
    btn.style.color = deviceManagementMode ? '#fff' : '';
    btn.style.borderColor = deviceManagementMode ? 'var(--accent-strong)' : '';
  }
  if(mapEl) mapEl.style.cursor = deviceManagementMode ? 'crosshair' : '';
  if(banner){
    banner.hidden = !deviceManagementMode;
    if(deviceManagementMode){
      const n = selectedNodeId ? selectedNodeId : null;
      banner.textContent = n
        ? `โหมดจัดการอุปกรณ์: คลิกบนแผนที่เพื่อปักตำแหน่งใหม่ให้ "${n}" (เลือกแถวอื่นในตารางเพื่อเปลี่ยนโหนดที่จะปัก)`
        : `โหมดจัดการอุปกรณ์: เลือกโหนดจากตารางด้านซ้ายก่อน แล้วคลิกบนแผนที่เพื่อปักตำแหน่ง`;
    }
  }
}

async function saveNodeLocation(nodeId, lat, lng){
  try{
    await api(`/api/nodes/${nodeId}/location`, {method:'PATCH', body: JSON.stringify({lat, lng})});
    showToast('บันทึกตำแหน่งโหนดแล้ว', `${nodeId} → (${lat.toFixed(5)}, ${lng.toFixed(5)})`);
    await refreshStationsData();
  }catch(e){
    showToast('บันทึกตำแหน่งไม่สำเร็จ', e.message, false);
  }
}

// Auto-scaled y-domain waveform SVG (unlike waveSvg's fixed [-1.3,1.3], tuned
// for the simulated station's synthetic amplitude convention) -- real
// accelerometer values sit close to zero at rest (~0.01g) and only swing
// wide during an actual event, so the domain is computed from the data
// itself each draw, with a floor so idle noise doesn't get visually
// exaggerated into looking like constant shaking.
function realWaveSvg(values, color, h, label, domain){
  h = h || 90;
  const W = 600;
  const d = pathFromSeries(values && values.length ? values : [0,0], W, h-4, domain);
  return `
  <svg class="chart" viewBox="0 0 ${W} ${h+16}" preserveAspectRatio="none" style="width:100%;height:${h+16}px;display:block;">
    <line class="grid-line" x1="0" y1="${h/2}" x2="${W}" y2="${h/2}" stroke-width="1"/>
    <path d="${d}" fill="none" stroke="${color}" stroke-width="1.6" stroke-linejoin="round" transform="translate(0,2)"/>
    <text x="4" y="${h+13}" font-size="9">${label}</text>
    <text x="${W-4}" y="${h+13}" font-size="9" text-anchor="end">±${domain[1].toFixed(3)}g</text>
  </svg>`;
}

function ensureNodesMap(){
  const el = document.getElementById('nodesMapEl');
  if(!el) return null;
  if(nodesMap && document.body.contains(nodesMap.getContainer())) return nodesMap;
  nodesMap = L.map('nodesMapEl', {zoomControl:true, attributionControl:false}).setView([13.7,101.0], 5.3);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution:'&copy; OpenStreetMap contributors', maxZoom:19, className:'osm-dark-tiles',
  }).addTo(nodesMap);
  nodesMapLayer = L.layerGroup().addTo(nodesMap);
  // Bound once per map instance -- reads deviceManagementMode/selectedNodeId
  // live on every click rather than capturing them at bind time, so toggling
  // the mode or picking a different row doesn't need this re-bound.
  nodesMap.on('click', (e)=>{
    if(!deviceManagementMode) return;
    if(!selectedNodeId){
      showToast('ยังไม่ได้เลือกโหนด', 'เลือกโหนดจากตารางด้านซ้ายก่อนคลิกปักตำแหน่ง', false);
      return;
    }
    saveNodeLocation(selectedNodeId, e.latlng.lat, e.latlng.lng);
  });
  return nodesMap;
}

// When 2+ nodes share (near-)identical coordinates -- e.g. a real node
// still at its un-pinned default location, seeded at the same city as a
// simulated one -- their markers draw exactly on top of each other.
// Whichever one Leaflet paints last visually hides the rest underneath it,
// so the map can show only ONE status color/label at a spot where the
// table lists several nodes, some online and some not (this is exactly
// the "map doesn't match the table" symptom). Spreads coincident nodes in
// a small circle around their shared point purely for where the marker is
// DRAWN -- the node's own lat/lng (used for click-to-pin edit, distance
// calcs, the table, etc.) is completely untouched.
function jitterCoincidentNodes(list){
  const groups = new Map();
  list.forEach(n=>{
    if(n.lat == null || n.lng == null) return;
    const key = n.lat.toFixed(3) + ',' + n.lng.toFixed(3);
    if(!groups.has(key)) groups.set(key, []);
    groups.get(key).push(n);
  });
  const out = [];
  groups.forEach(group=>{
    if(group.length === 1){
      out.push(Object.assign({renderLat: group[0].lat, renderLng: group[0].lng}, group[0]));
      return;
    }
    // ~4km spread -- close enough to still read as "the same place" at a
    // normal zoom, far enough apart that every marker renders visibly.
    const R = 0.035;
    group.forEach((n, i)=>{
      const angle = (2 * Math.PI * i) / group.length;
      out.push(Object.assign({renderLat: n.lat + R * Math.cos(angle), renderLng: n.lng + R * Math.sin(angle)}, n));
    });
  });
  return out;
}

function paintNodesMap(list){
  const map = ensureNodesMap();
  if(!map || !nodesMapLayer) return;
  nodesMapLayer.clearLayers();
  const pts = [];
  jitterCoincidentNodes(list).forEach(n=>{
    pts.push([n.renderLat, n.renderLng]);
    const color = n.online ? '#5fe05f' : '#63a4ee'; // เขียว=ออนไลน์, ฟ้า=ออฟไลน์ -- อนุสัญญาสีเดียวกับ "สถานี ENVIRO" ใน situationShell()'s legend
    const marker = L.circleMarker([n.renderLat, n.renderLng], {
      radius: n.node_id === selectedNodeId ? 9 : 7, color, weight: n.node_id === selectedNodeId ? 3 : 2,
      fillColor: color, fillOpacity: .85,
    }).bindPopup(`<b>${n.name || n.node_id}</b><br>${n.node_id} · ${n.online ? 'ออนไลน์' : 'ออฟไลน์'}`);
    // Permanent label (not just the click-popup) so a marker's identity on
    // the map is unambiguous against "รหัสโหนด" in the table next to it,
    // even before clicking -- two nodes sited close together (e.g. both
    // near Bangkok) would otherwise be indistinguishable dots.
    marker.bindTooltip(n.node_id, {permanent: true, direction: 'top', offset: [0, -6], className: 'node-map-label'});
    marker.on('click', ()=> selectNode(n.node_id));
    marker.addTo(nodesMapLayer);
  });
  if(pts.length === 1) map.setView(pts[0], 9);
  else if(pts.length > 1) map.fitBounds(L.latLngBounds(pts), {padding:[40,40], maxZoom:9});
}

// Dropdown next to "ค่าที่ตรวจวัดล่าสุด" -- lets someone switch which
// node's metrics/waveform/classification panels are shown without
// scrolling back up to the table, reusing the exact same selectNode() the
// table-row click and map-marker click already call.
function nodeSelectHtml(nodeId){
  const options = (lastNodesList.length ? lastNodesList : [{node_id: nodeId, name: nodeId}])
    .map(n=>`<option value="${n.node_id}" ${n.node_id===nodeId?'selected':''}>${n.node_id} — ${n.name||n.node_id}</option>`)
    .join('');
  return `<select class="field" style="width:auto;max-width:220px;padding:5px 8px;font-size:13.5px;" onchange="selectNode(this.value)">${options}</select>`;
}

function nodeListRowHtml(n){
  const dotColor = n.online ? 'var(--status-good)' : (n.vibration_active ? 'var(--status-critical)' : 'var(--status-watch)');
  const dotSoft = n.online ? 'var(--status-good-soft)' : (n.vibration_active ? 'var(--status-critical-soft)' : 'var(--status-watch-soft)');
  const lastSeenText = n.last_seen ? fmtElapsedThai((Date.now() - new Date(n.last_seen).getTime())/1000) : '—';
  const selected = n.node_id === selectedNodeId;
  return `
    <tr class="node-row${selected?' selected':''}" data-node-id="${n.node_id}" style="cursor:pointer;${selected?'background:var(--surface-2);':''}">
      <td><span class="dot" style="background:${dotColor};box-shadow:0 0 0 3px ${dotSoft};"></span></td>
      <td class="strong tabular">${n.node_id}</td>
      <td>${n.name || '—'}</td>
      <td>${n.region || '—'}</td>
      <td class="tabular">${n.battery_pct != null ? n.battery_pct + '%' : '—'}</td>
      <td class="tabular">${lastSeenText}</td>
      <td>${n.online ? `<span class="badge good"><span class="dot" style="background:currentColor;"></span>ออนไลน์</span>` : `<span class="badge info"><span class="dot" style="background:currentColor;"></span>ออฟไลน์</span>`}</td>
      <td><button type="button" class="btn node-edit-btn" data-requires-write data-node-id="${n.node_id}" style="padding:4px 10px;font-size:13px;">${icon('target')} จัดการ</button></td>
    </tr>`;
}

// The inline row editor -- opened by the "จัดการ" column's button -- lets
// someone type รหัสโหนด (rename)/ชื่อ/ภูมิภาค/Lat/Lng/สถานะ directly, as a
// precise alternative to click-to-pin on the map
// (toggleDeviceManagementMode below). All save through the same general
// PATCH /api/nodes/<id> endpoint (routes/nodes.py edit_node).
let editingNodeId = null;

function nodeEditRowHtml(n){
  const esc = (s)=> String(s==null?'':s).replace(/"/g,'&quot;');
  return `
    <tr class="node-edit-row" data-node-id="${n.node_id}">
      <td></td>
      <td colspan="7">
        <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end;padding:10px 0;">
          <label style="display:flex;flex-direction:column;gap:4px;font-size:13px;color:var(--ink-muted);">รหัสโหนด
            <input type="text" class="field node-edit-id" value="${esc(n.node_id)}" style="width:120px;padding:6px 8px;font-size:14px;">
          </label>
          <label style="display:flex;flex-direction:column;gap:4px;font-size:13px;color:var(--ink-muted);">ชื่อ
            <input type="text" class="field node-edit-name" value="${esc(n.name)}" style="width:170px;padding:6px 8px;font-size:14px;">
          </label>
          <label style="display:flex;flex-direction:column;gap:4px;font-size:13px;color:var(--ink-muted);">ภูมิภาค
            <input type="text" class="field node-edit-region" value="${esc(n.region)}" style="width:130px;padding:6px 8px;font-size:14px;">
          </label>
          <label style="display:flex;flex-direction:column;gap:4px;font-size:13px;color:var(--ink-muted);">Lat
            <input type="number" step="0.00001" class="field node-edit-lat" value="${esc(n.lat)}" style="width:110px;padding:6px 8px;font-size:14px;">
          </label>
          <label style="display:flex;flex-direction:column;gap:4px;font-size:13px;color:var(--ink-muted);">Lng
            <input type="number" step="0.00001" class="field node-edit-lng" value="${esc(n.lng)}" style="width:110px;padding:6px 8px;font-size:14px;">
          </label>
          <label style="display:flex;flex-direction:column;gap:4px;font-size:13px;color:var(--ink-muted);">สถานะ
            <select class="field node-edit-status" style="width:150px;padding:6px 8px;font-size:14px;">
              <option value="0" ${!n.paused?'selected':''}>ออนไลน์ (ตามข้อมูลจริง)</option>
              <option value="1" ${n.paused?'selected':''}>บังคับให้ออฟไลน์ (ทดสอบ)</option>
            </select>
          </label>
          <button type="button" class="btn primary node-edit-save" data-node-id="${n.node_id}" style="padding:6px 14px;font-size:14px;">บันทึก</button>
          <button type="button" class="btn node-edit-cancel" style="padding:6px 14px;font-size:14px;">ยกเลิก</button>
        </div>
        ${!n.is_simulated ? `<p class="panel-sub" style="margin:4px 0 0;font-size:13px;">⚠ อุปกรณ์จริง: เปลี่ยนรหัสโหนดต้องแก้ NODE_ID ในเฟิร์มแวร์ให้ตรงกันด้วย มิฉะนั้นจะอัปโหลดข้อมูลไม่ได้อีก</p>` : ''}
      </td>
    </tr>`;
}

// Shared by renderStations()'s initial paint and refreshStationsData()'s
// poll patch -- keeps the open edit row (if any) across a refresh instead
// of it vanishing every ~4s while someone is mid-edit (values are re-filled
// from the freshly-fetched node each time, so an in-progress *unsaved* edit
// can get reset by a poll -- an acceptable tradeoff against the editor
// disappearing entirely, and short enough of a window in practice).
function nodeListRowsHtml(list){
  return list.map(n=>{
    let html = nodeListRowHtml(n);
    if(n.node_id === editingNodeId) html += nodeEditRowHtml(n);
    return html;
  }).join('');
}

async function saveNodeEdit(nodeId, row){
  const newId = row.querySelector('.node-edit-id').value.trim();
  const name = row.querySelector('.node-edit-name').value.trim();
  const region = row.querySelector('.node-edit-region').value.trim();
  const lat = parseFloat(row.querySelector('.node-edit-lat').value);
  const lng = parseFloat(row.querySelector('.node-edit-lng').value);
  const paused = row.querySelector('.node-edit-status').value === '1';
  if(!newId || !name){
    showToast('บันทึกไม่สำเร็จ', 'ต้องระบุรหัสโหนดและชื่อ', false);
    return;
  }
  if(!isFinite(lat) || !isFinite(lng)){
    showToast('บันทึกไม่สำเร็จ', 'ต้องระบุ Lat/Lng เป็นตัวเลข', false);
    return;
  }
  try{
    const body = {name, region, lat, lng, paused};
    if(newId !== nodeId) body.new_node_id = newId;
    const updated = await api(`/api/nodes/${nodeId}`, {method:'PATCH', body: JSON.stringify(body)});
    showToast('บันทึกข้อมูลโหนดแล้ว', updated.rename_warning || `${newId} → ${name} · ${region || '(ไม่ระบุภูมิภาค)'} (${lat.toFixed(5)}, ${lng.toFixed(5)})`);
    editingNodeId = null;
    if(selectedNodeId === nodeId) selectedNodeId = newId;
    await refreshStationsData();
  }catch(e){
    showToast('บันทึกไม่สำเร็จ', e.message, false);
  }
}

function renderStationsStatTiles(list){
  const total = list.length;
  const online = list.filter(n=>n.online).length;
  const withBattery = list.filter(n=>n.battery_pct != null);
  const avgBattery = withBattery.length ? Math.round(withBattery.reduce((s,n)=>s+n.battery_pct,0)/withBattery.length) : null;
  const seenTimes = list.filter(n=>n.last_seen).map(n=>(Date.now()-new Date(n.last_seen).getTime())/1000);
  const freshest = seenTimes.length ? Math.min(...seenTimes) : null;
  const vibrating = list.filter(n=>n.vibration_active).length;
  return `
    <div class="stat-tile"><span class="label">โหนดออนไลน์</span><span class="value tabular" style="color:var(--status-good);">${online}<small>/ ${total}</small></span></div>
    <div class="stat-tile"><span class="label">แบตเตอรี่เฉลี่ย</span><span class="value tabular">${avgBattery!=null?avgBattery:'—'}<small>%</small></span></div>
    <div class="stat-tile"><span class="label">ข้อมูลสดสุดเมื่อ</span><span class="value tabular">${freshest!=null?Math.round(freshest):'—'}<small>วินาทีที่แล้ว</small></span></div>
    <div class="stat-tile"><span class="label">กำลังตรวจพบแรงสั่น</span><span class="value tabular" style="color:${vibrating?'var(--status-critical)':'inherit'};">${vibrating}<small>/ ${total} โหนด</small></span></div>`;
}

async function renderStations(){
  deviceManagementMode = false; // fresh DOM each time this renders -- start from a clean, predictable state
  editingNodeId = null;
  const [spec, list] = await Promise.all([
    api('/api/nodes/device-spec'), api('/api/nodes').catch(()=>[]),
  ]);
  lastNodesList = list;
  if(!selectedNodeId || !list.find(n=>n.node_id===selectedNodeId)){
    selectedNodeId = list.length ? list[0].node_id : null;
  }

  document.getElementById('view-stations').innerHTML = `
    <div class="view-head">
      <h2>สถานีตรวจวัด</h2>
      <p class="desc">เครือข่ายโหนดตรวจวัด ENVIRO ครอบคลุม เชียงใหม่ พิษณุโลก ตาก กรุงเทพฯ (มจพ.) ขอนแก่น ชลบุรี และสงขลา — ทุกโหนดผ่านการวิเคราะห์สัญญาณจริงชุดเดียวกันทั้งหมด (STA/LTA, FFT, การจำแนกด้วย Edge AI)</p>
    </div>
    <div class="grid grid-12">
      <div class="panel col-7">
        <div class="panel-head"><h3>${spec.name} <span class="hint">${spec.version}</span></h3><span class="badge good">อุปกรณ์จริง</span></div>
        <div class="device-card">
          <div class="device-visual">${icon('sensor')}</div>
          <div class="spec-grid">
            <div class="spec-row"><span class="k">เซนเซอร์</span><span class="v">${spec.sensor}</span></div>
            <div class="spec-row"><span class="k">หน่วยประมวลผล</span><span class="v">${spec.compute}</span></div>
            <div class="spec-row"><span class="k">การเชื่อมต่อ</span><span class="v">${spec.connectivity}</span></div>
            <div class="spec-row"><span class="k">การติดตั้ง</span><span class="v">${spec.install}</span></div>
            <div class="spec-row"><span class="k">การสอบเทียบ</span><span class="v">${spec.calibration}</span></div>
            <div class="spec-row"><span class="k">อัตราสุ่มสัญญาณ</span><span class="v">${spec.sample_rate}</span></div>
          </div>
        </div>
      </div>
      <div class="panel col-5" id="statTilesPanel">
        <div class="panel-head"><h3>ภาพรวมเครือข่ายโหนด</h3></div>
        <div class="grid grid-2" style="gap:10px;">${renderStationsStatTiles(list)}</div>
      </div>
    </div>
    <div class="grid grid-12" style="margin-top:14px;">
      <div class="panel col-7">
        <div class="panel-head"><h3>รายการโหนด</h3><span class="hint">คลิกแถวเพื่อดูรายละเอียด</span></div>
        <div class="scroll-x">
          <table class="data-table">
            <thead><tr><th></th><th>รหัสโหนด</th><th>ชื่อ</th><th>สถานีที่ตั้ง</th><th>แบตเตอรี่</th><th>อัปเดตล่าสุด</th><th>สถานะ</th><th>จัดการ</th></tr></thead>
            <tbody id="nodeListBody">${list.length ? nodeListRowsHtml(list) : `<tr><td colspan="8" class="panel-sub">ยังไม่มีโหนดฮาร์ดแวร์จริงลงทะเบียนในระบบ</td></tr>`}</tbody>
          </table>
        </div>
      </div>
      <div class="panel col-5">
        <div class="panel-head">
          <h3>แผนที่โหนด</h3>
          <button type="button" class="btn" id="deviceMgmtToggle" data-requires-write title="เข้าสู่โหมดจัดการอุปกรณ์เพื่อปักตำแหน่งโหนดบนแผนที่" style="padding:5px 12px;font-size:13.5px;">${icon('target')} จัดการอุปกรณ์</button>
        </div>
        <div id="deviceMgmtBanner" hidden style="font-size:14px;color:var(--status-info);background:var(--status-info-soft);border-radius:var(--radius-m);padding:8px 12px;margin-bottom:8px;"></div>
        <div id="nodesMapEl" style="height:260px;border-radius:var(--radius-l);overflow:hidden;"></div>
      </div>
    </div>
    <div class="grid grid-12" style="margin-top:14px;">
      <div class="panel col-4" id="nodeMetricsPanel"></div>
      <div class="panel col-4" id="nodeWavePanel"></div>
      <div class="panel col-4" id="nodeClassPanel"></div>
    </div>`;

  document.getElementById('nodeListBody').addEventListener('click', (e)=>{
    const editBtn = e.target.closest('.node-edit-btn');
    if(editBtn){
      // Redraws from the cached list, not a fresh fetch+refreshStationsData()
      // -- that function now deliberately skips rebuilding this table body
      // whenever editingNodeId is set (see its own comment), so it can't be
      // the one to draw the editor's very first frame.
      editingNodeId = editBtn.dataset.nodeId;
      const bodyEl = document.getElementById('nodeListBody');
      if(bodyEl && lastNodesList.length) bodyEl.innerHTML = nodeListRowsHtml(lastNodesList);
      applyRolePermissions();
      return;
    }
    const cancelBtn = e.target.closest('.node-edit-cancel');
    if(cancelBtn){
      editingNodeId = null;
      const bodyEl = document.getElementById('nodeListBody');
      if(bodyEl && lastNodesList.length) bodyEl.innerHTML = nodeListRowsHtml(lastNodesList);
      applyRolePermissions();
      return;
    }
    const saveBtn = e.target.closest('.node-edit-save');
    if(saveBtn){
      saveNodeEdit(saveBtn.dataset.nodeId, saveBtn.closest('tr'));
      return;
    }
    const row = e.target.closest('.node-row');
    if(row) selectNode(row.dataset.nodeId);
  });
  document.getElementById('deviceMgmtToggle').addEventListener('click', toggleDeviceManagementMode);

  paintNodesMap(list);
  await selectNode(selectedNodeId, list);
  applyRolePermissions(); // data-requires-write on #deviceMgmtToggle above is only in the DOM from this render onward

  clearInterval(window.__stationsPoll);
  window.__stationsPoll = setInterval(()=> refreshStationsData(), 4000);
}

// Throttled wrappers for the 'node-telemetry' WS push (see ws.onmessage) --
// 7 simulated nodes (node_simulator.py) each broadcast independently every
// ~2s, so an unthrottled refresh-per-message would refetch several times a
// second while these pages are open. The 4s/15s poll timers below already
// provide a steady baseline; this just lets a genuine fresh reading show up
// sooner than that, without thrashing.
let __stationsRefreshThrottle = null;
function throttledRefreshStationsData(){
  if(__stationsRefreshThrottle) return;
  __stationsRefreshThrottle = setTimeout(()=>{ __stationsRefreshThrottle = null; }, 1500);
  refreshStationsData();
}
let __situationNodesRefreshThrottle = null;
function throttledRefreshSituationNodes(){
  if(__situationNodesRefreshThrottle) return;
  __situationNodesRefreshThrottle = setTimeout(()=>{ __situationNodesRefreshThrottle = null; }, 3000);
  refreshSituationNodes();
}

// Lightweight refresh -- re-fetches the node list (stat tiles/table/map)
// and the selected node's waveform/analysis, patching existing DOM instead
// of rebuilding the whole view. Used by both the poll timer and the
// 'node-telemetry' WS push (see ws.onmessage).
async function refreshStationsData(){
  if(document.getElementById('view-stations').hidden) return;
  let list;
  try{ list = await api('/api/nodes'); }catch(e){ return; }
  lastNodesList = list;
  const statEl = document.getElementById('statTilesPanel');
  if(statEl) statEl.querySelector('.grid').innerHTML = renderStationsStatTiles(list);
  // While a row's inline editor is open, leave the table body and map
  // alone -- 7 simulated nodes (node_simulator.py) broadcast independently
  // every ~2s, so an unthrottled table rebuild here would blow away
  // whatever someone is mid-typing into the edit row well before they can
  // click "บันทึก". Everything resumes refreshing the instant the editor
  // closes (saved or cancelled -- see saveNodeEdit / the cancel handler).
  if(!editingNodeId){
    const bodyEl = document.getElementById('nodeListBody');
    if(bodyEl) bodyEl.innerHTML = list.length ? nodeListRowsHtml(list) : `<tr><td colspan="8" class="panel-sub">ยังไม่มีโหนดฮาร์ดแวร์จริงลงทะเบียนในระบบ</td></tr>`;
    paintNodesMap(list);
  }
  if(!selectedNodeId || !list.find(n=>n.node_id===selectedNodeId)){
    selectedNodeId = list.length ? list[0].node_id : null;
  }
  await selectNode(selectedNodeId, list, {skipListRefresh:true}); // table/map already handled above (or intentionally frozen while editing)
  applyRolePermissions(); // re-applies data-requires-write to the freshly re-rendered "จัดการ"/edit-form buttons above
}

async function selectNode(nodeId, list, opts){
  selectedNodeId = nodeId;
  const mgmtBanner = document.getElementById('deviceMgmtBanner');
  if(deviceManagementMode && mgmtBanner){
    mgmtBanner.textContent = nodeId
      ? `โหมดจัดการอุปกรณ์: คลิกบนแผนที่เพื่อปักตำแหน่งใหม่ให้ "${nodeId}" (เลือกแถวอื่นในตารางเพื่อเปลี่ยนโหนดที่จะปัก)`
      : `โหมดจัดการอุปกรณ์: เลือกโหนดจากตารางด้านซ้ายก่อน แล้วคลิกบนแผนที่เพื่อปักตำแหน่ง`;
  }
  if(!nodeId){
    ['nodeMetricsPanel','nodeWavePanel','nodeClassPanel'].forEach(id=>{
      const el = document.getElementById(id);
      if(el) el.innerHTML = `<p class="panel-sub">ยังไม่มีโหนดที่เลือก</p>`;
    });
    return;
  }
  if(!(opts && opts.skipListRefresh)){
    document.querySelectorAll('#nodeListBody .node-row').forEach(tr=>{
      const sel = tr.dataset.nodeId === nodeId;
      tr.classList.toggle('selected', sel);
      tr.style.background = sel ? 'var(--surface-2)' : '';
    });
    if(list) paintNodesMap(list);
  }

  let n = list ? list.find(x=>x.node_id===nodeId) : null;
  let wf;
  try{
    [n, wf] = await Promise.all([n ? Promise.resolve(n) : api(`/api/nodes/${nodeId}`), api(`/api/nodes/${nodeId}/waveform`)]);
  }catch(e){ return; }

  const metricsEl = document.getElementById('nodeMetricsPanel');
  if(metricsEl){
    const vibBadge = n.vibration_active
      ? `<span class="badge critical"><span class="dot" style="background:currentColor;"></span>ตรวจพบแรงสั่น</span>`
      : `<span class="badge good"><span class="dot" style="background:currentColor;"></span>ปกติ</span>`;
    metricsEl.innerHTML = `
      <div class="panel-head"><h3>ค่าที่ตรวจวัดล่าสุด</h3>${nodeSelectHtml(nodeId)}</div>
      <div class="grid grid-3" style="gap:8px;">
        <div class="stat-tile"><span class="label">Accel X</span><span class="value tabular" style="font-size:22px;">${n.accel_x!=null?n.accel_x.toFixed(4):'—'}<small>g</small></span></div>
        <div class="stat-tile"><span class="label">Accel Y</span><span class="value tabular" style="font-size:22px;">${n.accel_y!=null?n.accel_y.toFixed(4):'—'}<small>g</small></span></div>
        <div class="stat-tile"><span class="label">Accel Z</span><span class="value tabular" style="font-size:22px;">${n.accel_z!=null?n.accel_z.toFixed(4):'—'}<small>g</small></span></div>
      </div>
      <div class="spec-grid" style="margin-top:10px;">
        <div class="spec-row"><span class="k">แบตเตอรี่</span><span class="v tabular">${n.battery_pct!=null?n.battery_pct+'%':'—'}${n.battery_v!=null?' · '+n.battery_v.toFixed(2)+'V':''}</span></div>
        <div class="spec-row"><span class="k">อุณหภูมิ / ความดันอากาศ</span><span class="v tabular">${n.temperature_c!=null?n.temperature_c.toFixed(1)+'°C':'—'} / ${n.pressure_hpa!=null?n.pressure_hpa.toFixed(1)+' hPa':'—'}</span></div>
        <div class="spec-row"><span class="k">PGA (ค่าพีคล่าสุด)</span><span class="v tabular">${wf.pga_g.toFixed(4)} g</span></div>
        <div class="spec-row"><span class="k">STA / LTA</span><span class="v tabular">${wf.stalta.toFixed(2)}</span></div>
        <div class="spec-row"><span class="k">ความถี่เด่น</span><span class="v tabular">${wf.dominant_hz>0?wf.dominant_hz.toFixed(2)+' Hz':'—'}</span></div>
        <div class="spec-row"><span class="k">มุมเอียง (Roll / Pitch)</span><span class="v tabular">${n.roll_deg!=null?n.roll_deg.toFixed(1)+'°':'—'} / ${n.pitch_deg!=null?n.pitch_deg.toFixed(1)+'°':'—'}</span></div>
        <div class="spec-row"><span class="k">สถานะแรงสั่น</span><span class="v">${vibBadge}</span></div>
        <div class="spec-row"><span class="k">เซนเซอร์บนบอร์ด</span><span class="v">BMP280 ${n.bmp_ok?'✓':'✗'} · IMU ${n.imu_ok?'✓':'✗'}</span></div>
      </div>`;
  }

  const waveEl = document.getElementById('nodeWavePanel');
  if(waveEl){
    if(wf.seconds_available > 0){
      const allVals = [...wf.axes.x, ...wf.axes.y, ...wf.axes.z];
      const m = Math.max(0.02, ...allVals.map(Math.abs)) * 1.15;
      const domain = [-m, m];
      const rateHint = wf.low_res
        ? `${wf.seconds_available.toFixed(0)}s · ~1 ตัวอย่าง/วิ (ยังไม่มี raw 20Hz)`
        : `${wf.seconds_available.toFixed(0)}s / ${wf.window_sec}s`;
      waveEl.innerHTML = `
        <div class="panel-head"><h3>คลื่นสัญญาณสด (X/Y/Z)</h3><span class="hint">${rateHint}</span></div>
        ${wf.low_res ? `<p class="panel-sub">แสดงจากค่า ACCEL X/Y/Z ล่าสุดของแต่ละรอบอัปโหลด (~1 ครั้ง/วิ) เป็นข้อมูลจริงแต่ความละเอียดต่ำ — STA/LTA (แผงซ้าย) ยังคำนวณได้จริงที่อัตรานี้ แต่การจำแนกด้วย Edge AI (แผงขวา) ต้องใช้ raw waveform 20Hz เท่านั้น ต้องอัปเดตเฟิร์มแวร์ให้ส่งฟิลด์ "wave" ก่อน (ดู firmware/prototype_node)</p>` : ''}
        ${realWaveSvg(wf.axes.x,'var(--series-enviro)',60,'X',domain)}
        ${realWaveSvg(wf.axes.y,'var(--series-usgs)',60,'Y',domain)}
        ${realWaveSvg(wf.axes.z,'var(--series-gistda)',60,'Z',domain)}`;
    } else {
      waveEl.innerHTML = `
        <div class="panel-head"><h3>คลื่นสัญญาณสด (X/Y/Z)</h3></div>
        <p class="panel-sub">ยังไม่มีข้อมูลจากโหนดนี้เลย — รอสักครู่หลังอัปโหลดครั้งแรก</p>`;
    }
  }

  const classEl = document.getElementById('nodeClassPanel');
  if(classEl){
    classEl.innerHTML = wf.low_res ? `
      <div class="panel-head"><h3>การจำแนกด้วย Edge AI</h3></div>
      <p class="panel-sub">การแยก <b>แผ่นดินไหว/ยานพาหนะ/เครื่องจักร/เสียงรบกวน</b> ใช้ "ความถี่การสั่น" เป็นตัวชี้ขาดหลัก (เครื่องจักรสั่นถี่สม่ำเสมอสูง, รถวิ่งผ่านสั่นถี่ปานกลาง, แผ่นดินไหวสั่นความถี่กว้างปนกัน) ซึ่งต้องสุ่มตัวอย่างอย่างน้อย ~20 ครั้ง/วินาทีถึงจะ "จับจังหวะ" ได้ — เหมือนถ่ายวิดีโอพัดลมหมุนด้วยกล้อง 1 เฟรม/วินาที จะเห็นแค่ว่าพัดลมหมุนหรือไม่หมุน แต่บอกไม่ได้ว่าหมุนเร็วแค่ไหน ตอนนี้โหนดนี้ส่งแค่ 1 ค่า/วินาที (เห็นว่า "มีการสั่น" ได้ แต่บอกไม่ได้ว่าสั่นแบบไหน) ต้องอัปเดตเฟิร์มแวร์ให้ส่งฟิลด์ "wave" (20Hz) ก่อนจึงจะจำแนกได้จริง</p>
      <div style="display:flex;flex-direction:column;gap:12px;">${renderClassBars(wf.classification_bars)}</div>
      <div class="spec-row" style="margin-top:10px;"><span class="k">ความครบถ้วนของข้อมูล</span><span class="v tabular">0% (ต้องใช้ raw waveform)</span></div>` : `
      <div class="panel-head"><h3>การจำแนกด้วย Edge AI</h3></div>
      <p class="panel-sub">คำนวณจริงจากบัฟเฟอร์คลื่นของโหนดนี้เอง (STA/LTA + ความแหลมของสเปกตรัม FFT) — ยังไม่มีสถานีข้างเคียงให้ยืนยันด้วยความสอดคล้องของเครือข่าย จนกว่าจะมีโหนดจริงมากกว่า 1 ตัวในบริเวณใกล้เคียง</p>
      <div style="display:flex;flex-direction:column;gap:12px;">${renderClassBars(wf.classification_bars)}</div>
      <div class="spec-row" style="margin-top:10px;"><span class="k">ความครบถ้วนของข้อมูล</span><span class="v tabular">${wf.classification_confidence_pct.toFixed(0)}%</span></div>`;
  }
}
