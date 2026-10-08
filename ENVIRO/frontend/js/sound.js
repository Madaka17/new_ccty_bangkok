// Alert sounds (Web Audio). A classic script (not a module): every js/ file shares one global scope and index.html loads them in order.

/* ============================= ALERT SOUND (Web Audio, synthesized to match the siren spec on each level) ============================= */
let audioCtx = null;
let soundEnabled = localStorage.getItem('enviro_sound') !== 'off';

function ensureAudioCtx(){
  if(!audioCtx){
    try{ audioCtx = new (window.AudioContext || window.webkitAudioContext)(); }catch(e){ return null; }
  }
  if(audioCtx.state === 'suspended') audioCtx.resume().catch(()=>{});
  return audioCtx;
}
// Browsers block audio until a user gesture; the login click (or any first
// click after auto-login) unlocks the context so later WS-triggered alerts
// can actually play.
document.addEventListener('click', ()=>ensureAudioCtx(), {once:true});

function beep(ctx, freq, startTime, duration, gainPeak){
  const osc = ctx.createOscillator(), gain = ctx.createGain();
  osc.type = 'sine';
  osc.frequency.setValueAtTime(freq, startTime);
  gain.gain.setValueAtTime(0.0001, startTime);
  gain.gain.linearRampToValueAtTime(gainPeak, startTime + 0.02);
  gain.gain.linearRampToValueAtTime(0.0001, startTime + duration);
  osc.connect(gain); gain.connect(ctx.destination);
  osc.start(startTime); osc.stop(startTime + duration + 0.03);
}

// Real browser text-to-speech (Web Speech API) for the voice prompts the
// level-4/6 siren specs call for -- not a recorded audio file, genuinely
// synthesized speech, same spirit as the Web-Audio-synthesized beeps below.
function speak(text){
  if(!soundEnabled || !window.speechSynthesis) return;
  try{
    // A known Chrome/WebKit SpeechSynthesis quirk: an utterance can get stuck
    // mid-queue (speechSynthesis.speaking stays true, no 'start'/'end' event
    // ever fires) and silently blocks every utterance queued behind it --
    // which, for a repeating alert like the Level 6 siren, means NONE of the
    // voice prompts are ever heard again after the first bad one, even though
    // speak() keeps getting called correctly. Cancelling first guarantees
    // this call is never stuck behind an earlier stuck/unfinished utterance.
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = 'th-TH'; utter.rate = 1.0; utter.pitch = 1.0;
    window.speechSynthesis.speak(utter);
  }catch(e){}
}

let criticalAlertTimer = null;
// Set only when the user actually dismissed the Level 6 alarm (ack button or
// muting) -- distinguishes "stopped on purpose" from "criticalAlertTimer
// died some other way" so the visibilitychange handler below knows whether
// resuming it is welcome or would defeat a deliberate mute/acknowledge.
let criticalUserStopped = false;
function stopCriticalAlertRepeat(){
  if(criticalAlertTimer){ clearInterval(criticalAlertTimer); criticalAlertTimer = null; }
  criticalUserStopped = true;
  if(window.speechSynthesis) window.speechSynthesis.cancel();
  const ack = document.getElementById('criticalAckBar');
  if(ack) ack.hidden = true;
}
// Life-safety hardening: browsers throttle/suspend timers (rAF *and*, given
// enough backgrounded time, setInterval too) while a tab is hidden -- a phone
// screen lock or an app switch during the exact seconds a Level 6 wave
// arrives. If the tab comes back to the foreground, a Level 6 event is still
// the live situation, and the user never actually acknowledged or muted it,
// resume the alarm immediately instead of leaving it silently dead.
document.addEventListener('visibilitychange', ()=>{
  if(document.visibilityState !== 'visible') return;
  if(criticalUserStopped || criticalAlertTimer) return;
  const ev = situationData && situationData.event;
  const youLevel = ev ? getEvForGuidance(ev) : null; // pin-based -- see updateTopbar/checkPinCrossing
  if(youLevel && youLevel.level === 6) playArrivalSound(6);
});

// A sustained tone (attack - flat sustain - release) rather than beep()'s
// short linear triangle -- what a real "ปี๊บยาว" (long beep) needs so it
// reads as one continuous alarm tone instead of a quick blip stretched out.
// `freqEnd` (optional) lets levels 5-6 bend the pitch downward through the
// tone for a more siren-like, urgent character.
function longBeep(ctx, freqStart, startTime, duration, gainPeak, freqEnd){
  const osc = ctx.createOscillator(), gain = ctx.createGain();
  osc.type = 'sine';
  osc.frequency.setValueAtTime(freqStart, startTime);
  if(freqEnd != null) osc.frequency.linearRampToValueAtTime(freqEnd, startTime + duration);
  gain.gain.setValueAtTime(0.0001, startTime);
  gain.gain.linearRampToValueAtTime(gainPeak, startTime + 0.05);
  gain.gain.setValueAtTime(gainPeak, startTime + Math.max(0.05, duration - 0.08));
  gain.gain.linearRampToValueAtTime(0.0001, startTime + duration);
  osc.connect(gain); gain.connect(ctx.destination);
  osc.start(startTime); osc.stop(startTime + duration + 0.05);
}

// A continuous rising/falling wail -- the "ウーウー" cadence of Japan's real
// disaster-warning speakers (防災行政無線) and the J-Alert siren, sweeping
// smoothly between a low and high pitch rather than beeping/blipping. This
// is an original tone built in that same wailing-siren idiom, not a
// recording or reproduction of any broadcaster's specific copyrighted
// alert chime. Used only for the Level 6 arrival signal below.
function jpWailSiren(ctx, startTime, duration, gainPeak){
  const osc = ctx.createOscillator(), gain = ctx.createGain();
  osc.type = 'triangle'; // some edge/harmonics so it cuts through, short of a harsh buzzer
  const freqLow = 500, freqHigh = 1100, halfCycle = 0.65; // ~1.3s per up-down sweep
  const endTime = startTime + duration;
  osc.frequency.setValueAtTime(freqLow, startTime);
  let t = startTime, up = true;
  while(t < endTime){
    const next = Math.min(t + halfCycle, endTime);
    osc.frequency.linearRampToValueAtTime(up ? freqHigh : freqLow, next);
    t = next; up = !up;
  }
  gain.gain.setValueAtTime(0.0001, startTime);
  gain.gain.linearRampToValueAtTime(gainPeak, startTime + 0.12);
  gain.gain.setValueAtTime(gainPeak, Math.max(startTime + 0.12, endTime - 0.12));
  gain.gain.linearRampToValueAtTime(0.0001, endTime);
  osc.connect(gain); gain.connect(ctx.destination);
  osc.start(startTime); osc.stop(endTime + 0.05);
}

// Plays once the S-wave ripple genuinely reaches the reference location's
// map pin (see startRipple/haversineKm above) -- a distinct signal from playAlertSound(), which
// fires when the event is first *detected/classified* (possibly minutes
// before the wave physically arrives anywhere near the viewer). This is
// "it's happening at your position right now", so it's deliberately a
// single sustained "ปี๊บยาว" per level rather than the multi-beep detection
// pattern, escalating in length/urgency, with Level 6 continuing --
// reusing the same criticalAckBar/criticalAlertTimer UI as a declare-time
// Level 6 alert would.
//
// IMPORTANT (life-safety): Level 6 deliberately has NO auto-stop-by-timer.
// server/simulator.py's SHAKE_DURATION_S (9s) is a fixed synthetic waveform
// envelope used only to shape the detection signal fed to STA/LTA -- it is
// identical for every magnitude and bears no relationship to how long real
// strong shaking from a major earthquake actually lasts (which can run from
// tens of seconds to several minutes). Auto-stopping the siren off that
// constant would risk silencing "หมอบ กำบัง ยึดจับ" while real shaking is
// still happening. The canonical Level 6 spec (server/db.py LEVELS row 6)
// says the siren repeats "จนผู้ใช้กดยืนยันรับทราบ" -- until the user
// acknowledges -- with no time limit, matching playAlertSound(6) below.
// Only a genuine user tap on the ack button (stopCriticalAlertRepeat) or a
// real re-classification to a lower level stops it.
function playArrivalSound(level){
  if(!soundEnabled || level <= 1) return;
  const ctx = ensureAudioCtx();
  if(!ctx) return;
  const now = ctx.currentTime + 0.05;
  if(level === 2){
    longBeep(ctx, 700, now, 0.6, 0.22);
  } else if(level === 3){
    longBeep(ctx, 650, now, 1.0, 0.26);
  } else if(level === 4){
    longBeep(ctx, 600, now, 1.4, 0.28);
    speak('แรงสั่นสะเทือนมาถึงตำแหน่งของคุณแล้ว');
  } else if(level === 5){
    longBeep(ctx, 580, now, 2.0, 0.32, 460);
    speak('แรงสั่นสะเทือนรุนแรงมาถึงตำแหน่งของคุณแล้ว');
  } else if(level === 6){
    // Arrival is the more urgent, life-critical moment -- always switch to
    // this exact cycle right when the pin is covered, even if a declare-time
    // Level 6 alert (playAlertSound, below) is already looping its own
    // pattern, so what's unambiguously heard at that instant is the wail +
    // command voice, not a continuation of the earlier detection sound.
    if(criticalAlertTimer) clearInterval(criticalAlertTimer);
    criticalUserStopped = false; // a live Level 6 alarm starting always supersedes an earlier dismissal
    const cycle = ()=>{
      // Re-check on every tick, not just when the cycle starts -- soundEnabled
      // can flip to false anytime while this setInterval keeps running, and
      // muting must silence it on the very next tick, not just block new cycles.
      if(!soundEnabled) return;
      const c2 = ensureAudioCtx(); if(!c2) return;
      jpWailSiren(c2, c2.currentTime + 0.05, 2.6, 0.34);
      speak('แผ่นดินไหวรุนแรง หมอบ กำบัง ยึดจับ ทันที'); // starts together with the wail, not after it
    };
    cycle();
    criticalAlertTimer = setInterval(cycle, 3000);
    const ack = document.getElementById('criticalAckBar');
    if(ack) ack.hidden = false;
  }
}

// Mirrors the `siren` text already written per level in server/db.py LEVELS --
// this makes those descriptions (single beep / triple beep / alternating
// 660-1200Hz siren, plus voice prompts) into real audio instead of just
// label text.
function playAlertSound(level){
  if(!soundEnabled || level <= 1) return;
  if(level !== 6) stopCriticalAlertRepeat(); // a new, lower-severity alert supersedes any lingering level-6 repeat
  const ctx = ensureAudioCtx();
  if(!ctx) return;
  const now = ctx.currentTime + 0.05;
  if(level === 2){
    beep(ctx, 880, now, 0.18, 0.20);
  } else if(level === 3){
    [0, 0.28].forEach(o => beep(ctx, 660, now + o, 0.18, 0.22));
  } else if(level === 4){
    for(let i=0;i<6;i++) beep(ctx, i%2===0 ? 660 : 1200, now + i*0.28, 0.24, 0.24);
    speak('เตรียมหมอบ กำบัง ยึดจับ');
  } else if(level === 5){
    for(let i=0;i<10;i++) beep(ctx, i%2===0 ? 660 : 1200, now + i*0.2, 0.17, 0.28);
  } else if(level === 6){
    // "ไซเรนสลับเสียงพูดต่อเนื่อง จนผู้ใช้กดยืนยันรับทราบ" -- repeats the
    // siren+voice cycle until the user acknowledges via the banner button
    // (stopCriticalAlertRepeat), instead of firing once like lower levels.
    const cycle = ()=>{
      if(!soundEnabled) return; // re-checked every tick -- see the arrival-cycle comment above
      const c2 = ensureAudioCtx(); if(!c2) return;
      const t = c2.currentTime + 0.05;
      for(let i=0;i<10;i++) beep(c2, i%2===0 ? 660 : 1200, t + i*0.2, 0.17, 0.3);
      speak('เหตุการณ์แผ่นดินไหววิกฤต หมอบ กำบัง ยึดจับทันที');
    };
    cycle();
    if(criticalAlertTimer) clearInterval(criticalAlertTimer);
    criticalUserStopped = false; // a live Level 6 alarm starting always supersedes an earlier dismissal
    criticalAlertTimer = setInterval(cycle, 5000);
    const ack = document.getElementById('criticalAckBar');
    if(ack) ack.hidden = false;
  }
}

function paintSoundToggle(){
  const btn = document.getElementById('soundToggleBtn');
  btn.innerHTML = soundEnabled
    ? `${icon('bell')} <span class="tabular">เสียงแจ้งเตือน: เปิด</span>`
    : `${icon('bell')} <span class="tabular" style="color:var(--ink-faint);">เสียงแจ้งเตือน: ปิด</span>`;
}

async function refreshStationCount(){
  try{
    const regions = await api('/api/stations/regions');
    const total = regions.reduce((s,r)=>s+r.total,0);
    const online = regions.reduce((s,r)=>s+r.online,0);
    document.getElementById('topStations').textContent = `${online.toLocaleString()}/${total.toLocaleString()}`;
  }catch(e){}
}

