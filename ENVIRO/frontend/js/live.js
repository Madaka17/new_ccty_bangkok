// WebSocket live feed and the top bar. A classic script (not a module): every js/ file shares one global scope and index.html loads them in order.

/* ============================= WEBSOCKET LIVE FEED ============================= */
let LATEST_SNAPSHOT = null, lastTickAt = 0;
let ws = null, wsRetryMs = 1000;

function connectWs(){
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}${BASE}/ws`);
  ws.onopen = ()=>{
    wsRetryMs = 1000;
    document.getElementById('netDot').className = 'dot good';
    document.getElementById('netText').textContent = 'เครือข่ายออนไลน์';
    document.getElementById('connBanner').classList.remove('show');
  };
  ws.onclose = ()=>{
    document.getElementById('netDot').className = 'dot bad';
    document.getElementById('netText').textContent = 'ขาดการเชื่อมต่อ';
    document.getElementById('connBanner').classList.add('show');
    setTimeout(connectWs, wsRetryMs);
    wsRetryMs = Math.min(15000, wsRetryMs * 1.6);
  };
  ws.onerror = ()=>{ ws.close(); };
  ws.onmessage = (ev)=>{
    let msg; try{ msg = JSON.parse(ev.data); }catch(e){ return; }
    if(msg.type === 'tick'){
      LATEST_SNAPSHOT = msg.data;
      lastTickAt = Date.now();
      updateTopbar();
    } else if(msg.type === 'alert' || msg.type === 'alert-upgrade'){
      const e = msg.event;
      const isNew = msg.type === 'alert';
      // "สถานการณ์ปัจจุบัน" mode means real-data-only -- this whole message
      // is ENVIRO's own simulated pipeline (background noise or a demo),
      // so no toast, siren, or guidance update should fire for it here.
      // loadSituation()/renderWarning() still run below so the (suppressed)
      // views correctly stay on "no event" rather than going stale.
      if(!isRealDataOnlyMode()){
        // Per explicit request, the toast/siren/topbar/critical banner all
        // now reflect the severity AT THE VIEWER'S OWN PIN, not the fixed
        // reference station -- e.level below is deliberately the pin-based
        // recompute (see getEvForGuidance), not the raw WS payload's level.
        const youLevel = getEvForGuidance(e);
        if(youLevel){
          showToast(
            isNew ? `ตรวจพบเหตุการณ์ระดับ ${youLevel.level}` : `ยกระดับเป็นระดับ ${youLevel.level}`,
            `${youLevel.level_name} — ประเมิน M${e.magnitude_estimate} · ความเชื่อมั่น${e.confidence_label} (${e.stations_triggered} สถานี)`,
          );
          // Only replay the alert sound (and, at level 6, re-arm the "repeat
          // until acknowledged" loop) on a genuinely new alert or an actual
          // level change -- a routine confidence-tier bump (more stations
          // corroborating the same severity) should update the badge text
          // without re-sounding the siren or re-showing a dismissed level-6 bar.
          if(isNew || msg.level_changed) playAlertSound(youLevel.level);
        } else {
          // No pin set -- we genuinely don't know the severity AT the
          // viewer's own position, so no siren (would be guessing at a
          // level), just a soft heads-up naming what's missing.
          showToast('ตรวจพบเหตุการณ์แผ่นดินไหว', 'ยังไม่ทราบระดับความรุนแรงที่ตำแหน่งของคุณ — ยังไม่ได้ตั้งค่า "ตำแหน่งที่ตั้ง"', false);
        }
        // Update the guidance text in this same tick, from the WS payload
        // directly -- no waiting on loadSituation()'s network round-trip, so
        // the recommendation changes exactly together with the sound.
        if(!document.getElementById('view-situation').hidden && document.getElementById('levelGuidancePanel')){
          renderLevelGuidance(youLevel, e);
        }
      }
      if(!document.getElementById('view-situation').hidden) loadSituation();
      if(!document.getElementById('view-warning').hidden) renderWarning();
    } else if(msg.type === 'test-alert'){
      showToast('มีการทดสอบแจ้งเตือน', `ระดับ ${msg.level} โดย ${msg.by} (แซนด์บ็อกซ์)`);
    } else if(msg.type === 'quake-scheduled'){
      // Deliberately does NOT set manualSimulateStarted here (and so does not
      // flip this tab into showing the simulated pipeline) -- this message
      // also fires for the simulator's own ambient background STA/LTA
      // scheduling, with no admin action involved at all, and per explicit
      // request nothing may become visible on THIS tab without ITS OWN
      // "จำลองแผ่นดินไหว" press. topSimulateBtn's own trigger already sets
      // manualSimulateStarted synchronously for the tab that actually
      // pressed it, which is the only case that should un-mask anything.
      if(!document.getElementById('view-situation').hidden) loadSituation();
    } else if(msg.type === 'event-cleared'){
      // The demo was stopped -- possibly from a different tab/session --
      // sync this client's toggle button back to idle either way.
      manualSimulateStarted = false;
      syncSimulateButtonUI(false);
      if(!document.getElementById('view-situation').hidden) loadSituation();
    } else if(msg.type === 'node-telemetry'){
      // A node (real, or one of the 7 simulated ones in node_simulator.py --
      // which tick every ~2s each) just uploaded a fresh reading. Refetch
      // the whole list rather than patching just this one node's DOM, since
      // it's cheap at this node count and keeps every field in sync with
      // the server's own computation of them -- but throttled, since 7
      // simulated nodes broadcasting independently would otherwise refetch
      // several times a second while these pages are open.
      if(!document.getElementById('view-stations').hidden) throttledRefreshStationsData();
      if(!document.getElementById('view-situation').hidden) throttledRefreshSituationNodes();
    }
  };
}

function updateTopbar(){
  if(!LATEST_SNAPSHOT) return;
  const ev = isRealDataOnlyMode() ? null : LATEST_SNAPSHOT.active_event;
  const pill = document.getElementById('levelPill');
  // Per explicit request: the topbar pill is no longer the fixed
  // reference-station level -- it's the same pin-based recompute the rest
  // of the app already uses (see getEvForGuidance/computeYouLevelForEvent).
  const youLevel = ev ? getEvForGuidance(ev) : null;
  if(ev && youLevel){
    const [bg,fg] = levelPillStyle(youLevel.level);
    pill.style.background = bg; pill.style.color = fg;
    pill.textContent = `ระดับเตือนภัย ${youLevel.level} · ${youLevel.level_name}`;
  } else if(ev && !youLevel){
    pill.style.background = 'var(--status-info-soft)'; pill.style.color = 'var(--status-info)';
    pill.textContent = 'ยังไม่ได้ตั้งค่าตำแหน่ง';
  } else {
    pill.style.background = 'var(--surface-2)'; pill.style.color = 'var(--ink-muted)';
    pill.textContent = 'กำลังเฝ้าระวัง';
  }
}

