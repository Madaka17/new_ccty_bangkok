// Navigation, the simulate button and start-up. A classic script (not a module): every js/ file shares one global scope and index.html loads them in order.

/* ============================= NAV / BOOT ============================= */
const VIEWS = [
  {id:'situation', label:'หน้าสถานการณ์', icon:'map', render:renderSituation},
  {id:'brief',     label:'AI วิเคราะห์แผ่นดินไหว', icon:'globe', render:renderBrief},
  {id:'warning',   label:'เตือนล่วงหน้า',   icon:'bell', render:renderWarning},
  {id:'stations',  label:'สถานีตรวจวัด',   icon:'sensor', render:renderStations},
  {id:'analysis',  label:'วิเคราะห์ข้อมูล', icon:'wave', render:renderAnalysis},
  {id:'compare',   label:'เปรียบเทียบแหล่งข้อมูล', icon:'layers', render:renderCompare},
  {id:'admin',     label:'ผู้ดูแลระบบ',     icon:'shield', render:renderAdmin},
];

function switchView(id){
  VIEWS.forEach(v=>{ document.getElementById('view-'+v.id).hidden = v.id!==id; });
  document.querySelectorAll('.nav-item').forEach(b=>b.classList.toggle('active', b.dataset.view===id));
  document.getElementById('topTitle').textContent = VIEWS.find(v=>v.id===id).label;
  document.querySelector('.content').scrollTop = 0;
  const meta = VIEWS.find(v=>v.id===id);
  Promise.resolve(meta.render()).catch(err=>{
    if(err.message !== 'unauthorized') showToast('โหลดข้อมูลไม่สำเร็จ', err.message, false);
  });
}

// The topbar quick-demo button picks between two fixed scenarios
// (#topSimulateScenario) instead of a random one -- deliberately, so the
// point is to see how the real 6-level/Predicted-MMI pipeline classifies and
// times a *specific known* event, not a random Thai fault. Both scenarios'
// exact epicenter/depth/magnitude are defined server-side
// (HISTORICAL_MYANMAR_2025 / HISTORICAL_ANDAMAN_MEGATHRUST in
// server/routes/admin.py) so repeated clicks can't drift -- these constants
// only carry display text for the toast. Wave speed is chosen via
// #topSimulateSpeed: real speed for a genuine physical countdown, or
// accelerated to watch the ripple reach the reference location without
// waiting minutes.
// This is entirely independent of the real live-earthquake feeds on the
// world map (USGS/EMSC/GEOFON/TMD, server/world_quakes.py) -- those keep
// polling and displaying real current seismicity regardless of this button.
const SIMULATE_SCENARIOS = {
  myanmar_2025: {
    toastTitle: 'จำลองแผ่นดินไหวเมียนมา 28 มี.ค. 2568',
    label: 'รอยเลื่อนสะกาย (Sagaing Fault) เมียนมา',
  },
  andaman_l6: {
    toastTitle: 'จำลองแผ่นดินไหวอันดามัน (ทดสอบระดับ 6)',
    label: 'แนวมุดตัวสุมาตรา-อันดามัน (6.255467, 95.412450)',
  },
  mae_lao_2014: {
    toastTitle: 'จำลองแผ่นดินไหวแม่ลาว 5 พ.ค. 2557',
    label: 'ต.ดงมะดะ อ.แม่ลาว จ.เชียงราย (กรมทรัพยากรธรณี)',
  },
};

async function triggerRandomQuake(){
  const btn = document.getElementById('topSimulateBtn');
  const speedSel = document.getElementById('topSimulateSpeed');
  const scenarioSel = document.getElementById('topSimulateScenario');
  const speed = speedSel ? Number(speedSel.value) : 1;
  const scenarioKey = scenarioSel ? scenarioSel.value : 'myanmar_2025';

  if(scenarioKey === 'current_real'){
    // "สถานการณ์ปัจจุบัน" -- per explicit request, this option must NOT
    // simulate anything: it never calls /api/admin/simulate-quake, so no
    // synthetic event is injected into the detection pipeline. It only
    // switches the world map to the Realtime window and reports honestly
    // whatever the real external feeds (USGS/EMSC/GEOFON/TMD) currently
    // show -- including saying plainly when nothing real is active, rather
    // than implying a result. This does NOT drive the main AI Analysis
    // panel/siren (that pipeline only ever reflects ENVIRO's own simulated
    // detections) -- it's a real-data check on the map layer specifically.
    btn.disabled = true;
    const originalHtml = btn.innerHTML;
    btn.innerHTML = `${icon('warnTri')} กำลังตรวจสอบ...`;
    try{
      const rangeSel = document.getElementById('worldQuakeRange');
      if(rangeSel) rangeSel.value = 'realtime';
      if(!document.getElementById('view-situation').hidden) await refreshWorldQuakes();
      const data = await api('/api/world/earthquakes?days=realtime');
      const active = (data.quakes || []).filter(q => q.is_recent);
      if(active.length){
        const top = active.slice().sort((a,b) => (b.magnitude||0) - (a.magnitude||0))[0];
        showToast('สถานการณ์ปัจจุบัน (ข้อมูลจริงทั้งหมด)',
          `พบเหตุการณ์จริงที่ยัง active อยู่ ${active.length} จุด — ใหญ่ที่สุด M${top.magnitude!=null?top.magnitude.toFixed(1):'?'} ${top.place||'ไม่ทราบตำแหน่ง'} (${top.source}) · จากฟีดสาธารณะจริง ไม่มีการจำลองเหตุการณ์ใดๆ`);
      } else {
        showToast('สถานการณ์ปัจจุบัน (ข้อมูลจริงทั้งหมด)',
          `ไม่มีแผ่นดินไหวจริงที่กำลัง active อยู่ในขณะนี้ (ภายใน ${data.recent_minutes} นาทีล่าสุด จากฟีดจริง USGS/EMSC/GEOFON/TMD) — ระบบไม่ได้จำลองเหตุการณ์ใดๆ`);
      }
    }catch(e){
      showToast('ตรวจสอบสถานการณ์จริงไม่สำเร็จ', e.message, false);
    }finally{
      btn.disabled = false;
      btn.innerHTML = originalHtml;
    }
    return;
  }

  const scenario = SIMULATE_SCENARIOS[scenarioKey] || SIMULATE_SCENARIOS.myanmar_2025;
  btn.disabled = true;
  const originalHtml = btn.innerHTML;
  btn.innerHTML = `${icon('warnTri')} กำลังจำลอง...`;
  try{
    const res = await api('/api/admin/simulate-quake', {method:'POST', body: JSON.stringify({
      historical_event: scenarioKey, speed_multiplier: speed,
    })});
    const speedNote = speed > 1 ? `เร่งเวลา ${speed}x` : 'ความเร็วคลื่นจริง (ไม่เร่งเวลา)';
    // For the Andaman scenario specifically: at the real ~1,000km distance no
    // realistic magnitude reaches Level 6 at the reference location (see
    // server/routes/admin.py: ANDAMAN_L6_MAGNITUDE_CAP). Per explicit request,
    // this scenario deliberately solves for a magnitude beyond any earthquake
    // ever recorded so Level 6 (and its continuous siren) can be tested on
    // demand -- disclose that plainly rather than imply it's a realistic case.
    const honestNote = scenarioKey === 'andaman_l6'
      ? ' · ขนาดถูกปรับเกินจริงโดยตั้งใจเพื่อให้ถึงระดับ 6 เสมอ สำหรับทดสอบระบบแจ้งเตือนต่อเนื่อง (ไม่ใช่คาดการณ์ตามความเป็นจริง)'
      : '';
    showToast(scenario.toastTitle,
      `M${res.magnitude} ${scenario.label} — ${speedNote} · ETA ถึงสถานีใกล้ที่สุดประมาณ ${res.eta_s}s${honestNote}`);
    // Go red/blinking immediately -- don't wait for STA/LTA to actually
    // declare active_event a few seconds from now (see
    // Simulator.trigger_manual_quake's start_s delay); the button represents
    // "a simulation is running", which starts the instant this POST succeeds.
    manualSimulateStarted = true;
    syncSimulateButtonUI(true);
    if(!document.getElementById('view-situation').hidden) loadSituation();
  }catch(e){
    showToast('จำลองไม่สำเร็จ', e.message, false);
  }finally{
    btn.disabled = false;
    btn.innerHTML = originalHtml;
  }
}

let booted = false;
function boot(){
  if(booted) return;
  booted = true;
  const navEl = document.getElementById('nav');
  navEl.innerHTML = VIEWS.map((v,i)=>`
    <button class="nav-item${i===0?' active':''}" data-view="${v.id}">
      ${icon(v.icon)}<span class="nav-label">${v.label}</span><span class="nav-idx">0${i+1}</span>
    </button>`).join('');
  navEl.addEventListener('click', e=>{
    const b = e.target.closest('.nav-item');
    if(!b) return;
    switchView(b.dataset.view);
  });
  // topSimulateBtn/topSimulateScenario/topSimulateSpeed now live inside
  // situationShell() (moved out of the always-present topbar since they only
  // ever do anything on the situation view) -- they don't exist in the DOM
  // yet at boot time, so their wiring happens in paintSituation()'s
  // "build shell once" block instead, alongside wireUserLocationControls().
  document.getElementById('criticalAckBtn').addEventListener('click', stopCriticalAlertRepeat);
  paintSoundToggle();
  document.getElementById('soundToggleBtn').addEventListener('click', ()=>{
    soundEnabled = !soundEnabled;
    localStorage.setItem('enviro_sound', soundEnabled ? 'on' : 'off');
    paintSoundToggle();
    if(soundEnabled){
      ensureAudioCtx(); playAlertSound(3); // quick confirmation beep
    } else {
      // Muting must stop everything immediately, including a Level 6 siren
      // already looping via setInterval -- soundEnabled is only checked when
      // a cycle *starts*, not on every tick, so without this the wail/beep
      // and voice would keep firing every 3-5s regardless of the toggle.
      stopCriticalAlertRepeat();
    }
  });
  switchView('situation');
  refreshStationCount();
  setInterval(refreshStationCount, 30000);
  connectWs();

  function tickClock(){ document.getElementById('clock').textContent = new Date().toLocaleTimeString('th-TH',{hour:'2-digit',minute:'2-digit',second:'2-digit'}); }
  tickClock();
  setInterval(tickClock, 1000);
}

// Embedded, the rail is a row of tabs: its login and connection status go to the end of the topbar
if(document.documentElement.classList.contains('embed')) document.querySelector('.topbar').append(document.querySelector('.rail-foot'));
if(!(AUTH && AUTH.token)) AUTH = GUEST;
// Embedded, visitors get a lighter page without the staff-only tab and controls (the .embed.guest rules)
if(!AUTH.token) document.documentElement.classList.add('guest');
showApp();
boot();
