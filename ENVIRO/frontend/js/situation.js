// View 1, the situation page: guidance, wave ripples, the event panel, city table, now cards. A classic script (not a module): every js/ file shares one global scope and index.html loads them in order.

/* ============================================================================
   LOCATION-AWARE GUIDANCE + EVACUATION-VS-SHELTER ASSESSMENT
   Superseded the old generic "หมอบ ป้อง เกาะ อย่าวิ่ง" 4-card panel (removed
   per explicit request -- see git history if that generic, location-blind
   version is ever needed again) -- this panel now carries both the
   canonical per-level alert message (SAFETY_URGENCY, above) and the
   location-specific advice in one place, instead of two separate,
   inconsistent-sounding panels.
   Source spec: "ความรุนแรงที่คาด ณ ตำแหน่งผู้ใช้.docx" -- three parts:
   (1) advice that actually differs by where the viewer is, not one generic
       message for everyone; (2) a time-safety formula deciding whether
       there's genuinely enough time to reach open ground vs. shelter in
       place; (3) hazard "override" conditions (fire, stuck in an elevator,
       etc.) that supersede the normal level-based advice immediately.
   The doc is explicit that the time formula and its constants are "an
   engineering safety proposal for a prototype system, not an official
   government standard" -- kept that way here; the constants are disclosed
   in the UI, not silently baked in.
   ============================================================================ */
const LOCATION_TYPES = [
  {key:'house1', label:'บ้านชั้นเดียว / อยู่ชั้นล่าง', defaultWalkSec:20},
  {key:'house2', label:'บ้านหลายชั้น (อยู่ชั้นบน)', defaultWalkSec:60},
  {key:'highrise', label:'อาคารสูง / คอนโด', defaultWalkSec:240},
  {key:'school', label:'โรงเรียน', defaultWalkSec:60},
  {key:'hospital', label:'โรงพยาบาล', defaultWalkSec:90},
  {key:'mall_office', label:'ห้างสรรพสินค้า / สำนักงาน', defaultWalkSec:90},
  {key:'factory', label:'โรงงาน', defaultWalkSec:60},
  {key:'outdoor', label:'กลางแจ้ง', defaultWalkSec:10},
  {key:'driving', label:'กำลังขับรถ', defaultWalkSec:0},
  {key:'coastal', label:'ชายฝั่ง', defaultWalkSec:30},
];

// Per level (1-6) x per location -- verbatim/lightly-adapted from the spec
// doc's per-location breakdown. Levels 1-2 combine "โรงเรียน/โรงพยาบาล" and
// don't cover "โรงงาน" in the source -- filled in below at those two levels
// with a plainly-consistent low-severity equivalent (awareness only, same
// tone as the other level-1/2 entries) since the location picker needs to
// stay the same 10 options at every level.
const LOCATION_GUIDANCE_BY_LEVEL = {
  1: {
    house1:'ใช้ชีวิตตามปกติ ตรวจสอบว่าเส้นทางและจุดกำบังไม่มีสิ่งกีดขวาง',
    house2:'ใช้ชีวิตตามปกติ ตรวจสอบว่าเส้นทางและจุดกำบังไม่มีสิ่งกีดขวาง',
    highrise:'ไม่ต้องอพยพ ระบุตำแหน่งโต๊ะและบันไดหนีไฟไว้ล่วงหน้า',
    school:'แสดงสถานะให้เจ้าหน้าที่ทราบ ยังไม่ต้องประกาศฉุกเฉิน',
    hospital:'แสดงสถานะให้เจ้าหน้าที่ทราบ ยังไม่ต้องประกาศฉุกเฉิน',
    mall_office:'แจ้งฝ่ายอาคารเพื่อติดตามสถานการณ์',
    factory:'ดำเนินงานได้ตามปกติ ตรวจสอบเครื่องจักรว่าไม่มีความผิดปกติ',
    outdoor:'ดำเนินกิจกรรมได้ตามปกติ',
    driving:'ไม่ต้องหยุดรถ ติดตามข้อมูลโดยไม่ใช้โทรศัพท์ขณะขับ',
    coastal:'ยังไม่ต้องอพยพ เว้นแต่มีประกาศสึนามิแยกต่างหาก',
  },
  2: {
    house1:'หยุดงานบนบันไดหรือที่สูง อยู่ห่างตู้และกระจก เตรียมจุดกำบัง',
    house2:'หยุดงานบนบันไดหรือที่สูง อยู่ห่างตู้และกระจก เตรียมจุดกำบัง',
    highrise:'อยู่ในชั้นปัจจุบัน ห่างหน้าต่างและผนังภายนอก ไม่ต้องลงจากอาคาร',
    school:'ครูแจ้งนักเรียนให้อยู่ในความสงบและเตรียมเข้ากำบังใต้โต๊ะ',
    hospital:'ล็อกล้อเตียงหรืออุปกรณ์ ตรวจความพร้อมของผู้ป่วยที่เคลื่อนย้ายลำบาก',
    mall_office:'หยุดใช้บันไดเลื่อนชั่วคราวเมื่อจำเป็น เตรียมประกาศภายใน',
    factory:'ดำเนินงานต่อได้ระมัดระวังขึ้น สังเกตกระบวนการที่มีความร้อนหรือแรงดันสูง',
    outdoor:'สังเกตอาคาร กำแพง ป้ายและสายไฟรอบตัว',
    driving:'ขับต่อด้วยความระมัดระวัง ไม่จอดกะทันหัน',
    coastal:'ติดตามประกาศสึนามิ แต่ไม่ตื่นตระหนก',
  },
  3: {
    house1:'หากเวลาปลอดภัยมากกว่า 180 วินาทีและมีพื้นที่โล่งที่สำรวจแล้ว อาจเคลื่อนออกตามแผน มิฉะนั้นให้เข้ากำบังในบ้าน',
    house2:'ผู้ที่อยู่ชั้นบนควรอยู่ชั้นเดิม ไม่รีบลงบันได เลือกโต๊ะที่แข็งแรง',
    highrise:'ไม่ลงจากอาคาร ไม่ใช้ลิฟต์ ไปยังจุดกำบังภายในชั้นเดียวกัน',
    school:'นักเรียนเข้าประจำโต๊ะ ครูตรวจนักเรียนและเตรียมคำสั่งหมอบ–กำบัง–ยึดจับ',
    hospital:'ล็อกเตียง ปกป้องศีรษะผู้ป่วย หยุดหัตถการที่หยุดได้อย่างปลอดภัย',
    mall_office:'ไม่วิ่งไปทางออก อยู่ห่างกระจก ชั้นสินค้าและโคมไฟ',
    factory:'หยุดเครื่องจักรและกระบวนการเสี่ยงด้วยระบบที่ออกแบบไว้',
    outdoor:'ไปยังพื้นที่โล่ง ห่างอาคาร กำแพง ต้นไม้และเสาไฟ',
    driving:'ลดความเร็วอย่างนุ่มนวล หาตำแหน่งจอดที่ห่างสะพานและสายไฟ',
    coastal:'เตรียมเส้นทางขึ้นที่สูง แต่ปฏิบัติตามประกาศสึนามิหรือสัญญาณธรรมชาติ',
  },
  4: {
    house1:'อยู่ภายใน หมอบใต้โต๊ะแข็งแรง ยึดโต๊ะ และป้องกันศีรษะกับลำคอ',
    house2:'อยู่ภายใน หมอบใต้โต๊ะแข็งแรง ยึดโต๊ะ และป้องกันศีรษะกับลำคอ',
    highrise:'อยู่ในชั้นปัจจุบัน ห่างกระจกและผนังภายนอก ห้ามใช้ลิฟต์หรือเริ่มลงบันได',
    school:'ครูสั่งหมอบ–กำบัง–ยึดจับทันที ไม่พานักเรียนวิ่งออกจากห้อง',
    hospital:'ผู้ป่วยอยู่บนเตียงให้ป้องกันศีรษะ ล็อกล้อ และอยู่ห่างกระจก',
    mall_office:'ไม่กรูไปทางออก เข้ากำบังใต้โต๊ะหรือเคาน์เตอร์ที่แข็งแรง',
    factory:'ระบบอัตโนมัติหยุดเครื่องจักร ปิดวาล์วหรือแหล่งความร้อน แล้วพนักงานเข้ากำบัง',
    outdoor:'อยู่ภายนอก ไปพื้นที่โล่งและหมอบต่ำ',
    driving:'จอดอย่างปลอดภัย ดึงเบรกมือ และอยู่ในรถ',
    coastal:'ป้องกันตัวระหว่างสั่นก่อน หลังหยุดสั่นจึงประเมินการอพยพสึนามิ',
  },
  5: {
    house1:'หมอบ–กำบัง–ยึดจับ ห้ามวิ่งออก หลังหยุดสั่นให้ออกจากบ้านที่เสียหาย',
    house2:'หมอบ–กำบัง–ยึดจับ ห้ามวิ่งออก หลังหยุดสั่นให้ออกจากบ้านที่เสียหาย',
    highrise:'อยู่ในจุดกำบัง ห้ามใช้ลิฟต์ หลังหยุดสั่นให้รอประกาศและใช้บันไดเมื่ออาคารเสียหาย',
    school:'ป้องกันนักเรียนอยู่กับที่ หลังหยุดสั่นจึงอพยพเป็นแถวตามแผน',
    hospital:'ปกป้องผู้ป่วยก่อน เคลื่อนย้ายหลังหยุดสั่นตามลำดับความเร่งด่วน',
    mall_office:'อยู่ห่างกระจกและพื้นที่โถง หลังหยุดสั่นให้ปฏิบัติตามเจ้าหน้าที่',
    factory:'อยู่ห่างถังสารเคมี เตาและเครื่องจักร หลังหยุดสั่นให้ใช้แผนสารอันตราย',
    outdoor:'หมอบต่ำในพื้นที่โล่ง ระวังกำแพง อาคารและสายไฟล้ม',
    driving:'อยู่ในรถ หลีกเลี่ยงสะพาน อุโมงค์ ทางยกระดับและลาดเขา',
    coastal:'หลังหยุดสั่นให้อพยพขึ้นที่สูงหรือเข้าแผ่นดินทันทีเมื่อแรงสั่นรุนแรงหรือยาวนาน',
  },
  6: {
    house1:'ป้องกันตนจนหยุดสั่น ออกจากบ้านที่เสียหาย ระวังไฟ ก๊าซ สายไฟและอาฟเตอร์ช็อก',
    house2:'ป้องกันตนจนหยุดสั่น ออกจากบ้านที่เสียหาย ระวังไฟ ก๊าซ สายไฟและอาฟเตอร์ช็อก',
    highrise:'อยู่ในจุดกำบัง ไม่ใช้ลิฟต์ หลังหยุดสั่นประเมินไฟ ควันและโครงสร้างก่อนใช้บันได',
    school:'ครูคุ้มครองนักเรียนและตรวจจำนวนคน อพยพหลังหยุดสั่นเมื่อเส้นทางปลอดภัย',
    hospital:'ใช้แผนภัยพิบัติภายใน คัดแยกผู้บาดเจ็บ และไม่เคลื่อนย้ายผู้ป่วยโดยไม่มีเส้นทางปลอดภัย',
    mall_office:'ปฏิบัติตามเจ้าหน้าที่ ไม่ย้อนกลับไปเอาทรัพย์สิน',
    factory:'ใช้แผนฉุกเฉินสารเคมี ไฟไหม้และโครงสร้าง ห้ามเข้าพื้นที่รั่วไหล',
    outdoor:'อยู่ในพื้นที่โล่ง ห่างอาคาร สะพาน เสาไฟ ลาดเขาและรอยแยก',
    driving:'จอดรถ หลีกเลี่ยงสะพานและสายไฟ หลังเหตุการณ์อย่าขับผ่านถนนเสียหาย',
    coastal:'เมื่อหยุดสั่นให้อพยพขึ้นที่สูงทันที ไม่รอประกาศ และไม่กลับจนกว่าจะมีคำสั่งปลอดภัย',
  },
};

// Hazard override conditions -- any one active supersedes the normal
// level+location advice immediately, regardless of alert level.
const OVERRIDE_CONDITIONS = [
  {key:'fire', icon:'flame', label:'ไฟไหม้ / ควัน / ก๊าซรั่ว', text:'ออกจากพื้นที่ด้วยเส้นทางปลอดภัย ห้ามใช้ลิฟต์'},
  {key:'elevator', icon:'elevator', label:'ติดอยู่ในลิฟต์', text:'กดชั้นใกล้ที่สุด ออกจากลิฟต์แล้วหาที่กำบัง'},
  {key:'structural', icon:'warnTri', label:'อาคารมีเสียงโครงสร้างผิดปกติ', text:'หลังหยุดสั่นให้ออกจากอาคารทันที'},
  {key:'early_shake', icon:'noEntry', label:'เริ่มรู้สึกสั่นแล้ว (ก่อน ETA)', text:'ยกเลิกการเคลื่อนย้ายทันที หมอบ–กำบัง–ยึดจับเดี๋ยวนี้'},
  {key:'tsunami', icon:'wave', label:'มีสัญญาณ/ประกาศสึนามิ', text:'หลังหยุดสั่นให้อพยพขึ้นที่สูงหรือเข้าแผ่นดินทันที'},
  {key:'official', icon:'shield', label:'มีคำสั่งจากเจ้าหน้าที่', text:'ปฏิบัติตามคำสั่งทางการ เหนือคำแนะนำอัตโนมัติของระบบนี้'},
];

// Session state -- location choice persists across reloads (it describes
// the person, not a specific event); overrides are situational and reset
// each session on purpose.
let userLocationType = localStorage.getItem('enviro_loc_type') || 'house1';
let activeOverrides = new Set();

// `ev` is the pin-recomputed object (see getEvForGuidance) or null; `rawEv`
// is the actual event (or null) -- needed to tell "no event" apart from
// "there's an event but no location set", which must show a distinct
// "severity unknown" banner instead of either the idle text or a level.
function renderLocationGuidance(ev, rawEv){
  const panel = document.getElementById('locationGuidancePanel');
  if(!panel) return;
  const locationUnknown = !!rawEv && !ev;
  // lv (1-6) picks which level's location-advice text to show even with no
  // event, so "ฉันอยู่ที่" always previews something sensible -- but the
  // banner itself must not claim "ตรวจพบเหตุการณ์แผ่นดินไหว" (an event was
  // detected) when none actually was, so it looks up SAFETY_URGENCY by the
  // real level (0 = idle) separately from lv.
  const lv = ev ? Math.max(1, Math.min(6, ev.level)) : 1;
  const locOptions = LOCATION_TYPES.map(l=>
    `<option value="${l.key}"${l.key===userLocationType?' selected':''}>${l.label}</option>`).join('');

  const activeOverride = OVERRIDE_CONDITIONS.find(o => activeOverrides.has(o.key));
  const overrideBanner = activeOverride ? `
    <div class="override-banner">
      <div class="ob-label">${icon('warnTri')} เงื่อนไขเร่งด่วนแทนที่คำแนะนำปกติ — ${activeOverride.label}</div>
      <div class="ob-text">${activeOverride.text}</div>
    </div>` : '';

  const urgency = locationUnknown
    ? {fg: 'var(--status-info)', bg: 'var(--status-info-soft)', text: 'มีเหตุการณ์แผ่นดินไหวที่ระบบกำลังตรวจสอบอยู่ แต่ยังไม่ทราบตำแหน่งของคุณ — กดปุ่ม "ตำแหน่งที่ตั้ง" บนแผนที่ (GPS หรือกรอกพิกัดเอง) เพื่อดูคำแนะนำเฉพาะตำแหน่งจริง'}
    : SAFETY_URGENCY[ev ? lv : 0];
  const themed = ev && lv >= 3;
  const advice = LOCATION_GUIDANCE_BY_LEVEL[lv]?.[userLocationType] || LOCATION_GUIDANCE_BY_LEVEL[1][userLocationType];
  const locLabel = (LOCATION_TYPES.find(l=>l.key===userLocationType)||{}).label || '';

  panel.innerHTML = `
    <div class="panel-head"><h3>คำแนะนำตามสถานที่ของคุณ</h3><span class="hint">ปรับตามระดับ + สถานที่ที่คุณอยู่ตอนนี้</span></div>
    <div class="callout" style="border-color:${urgency.fg};background:${urgency.bg};margin-bottom:2px;"><div style="color:${urgency.fg};font-weight:600;">${urgency.text}</div></div>
    <div class="loc-select-row">
      <label for="userLocationSelect">${icon('pin')} ฉันอยู่ที่:</label>
      <select class="field" id="userLocationSelect" style="width:auto;">${locOptions}</select>
    </div>
    <div class="loc-advice-card${themed?' themed':''}" style="${themed?`--card-fg:${urgency.fg};--loc-bg:${urgency.bg};`:''}">
      ${icon('warnTri')}
      <div>
        <div class="loc-title">ระดับ ${lv} · ${locLabel}</div>
        <div class="loc-text">${advice}</div>
      </div>
    </div>
    ${overrideBanner}
    <div class="override-row">
      ${OVERRIDE_CONDITIONS.map(o=>`
        <button type="button" class="override-btn${activeOverrides.has(o.key)?' active':''}" data-override="${o.key}">
          ${icon(o.icon)}<span>${o.label}</span>
        </button>`).join('')}
    </div>`;
}

// Great-circle distance in km -- used below to know exactly when the animated
// S-wave circle's radius has grown enough to cover the user's pin, in sync
// with the rendered frame rather than a coarser once-a-second server poll.
function haversineKm(lat1, lng1, lat2, lng2){
  const R = 6371, toRad = d => d * Math.PI / 180;
  const dLat = toRad(lat2 - lat1), dLng = toRad(lng2 - lng1);
  const a = Math.sin(dLat/2)**2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng/2)**2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
}

// The single source of truth for "where is the user" -- a custom pin the
// user set via the ตำแหน่งที่ตั้ง popover. Every P/S-wave-to-"your position"
// calculation (the map pin/ripple crossing, the countdown callout, the
// "คุณอยู่ที่นี่" table badge, the impact/level panels) must derive from this
// exact same point.
// Returns null when the viewer hasn't actually set their own position --
// per explicit request, "your position" must come ONLY from a real source
// (GPS, or manually entered lat/lng), never silently substitute the fixed
// reference station (BKK-201, Bangkok) as if it were a real answer. Every
// caller (map pin, impact panel, wave countdown, level/location guidance)
// must treat null as "location not set" and say so, not quietly show
// Bangkok's numbers as if they were the viewer's own.
function resolveYouLocation(data){
  const customLoc = getUserCustomLocation();
  return customLoc
    ? {lat: customLoc.lat, lng: customLoc.lng, id: 'custom', region: 'ตำแหน่งที่คุณตั้งไว้เอง', custom: true}
    : null;
}

// The "ความรุนแรงที่คาด ณ ตำแหน่งคุณ" panel (impact ring + MMI + the ระดับ N
// guidance banner + location-based advice) has to describe the MMI/level at
// the viewer's ACTUAL pin -- but the server's predicted_mmi/level are (by
// design, see REFERENCE_STATION in server/simulator.py) computed at the
// single fixed reference station shared by every viewer, so those numbers
// were silently wrong whenever a viewer set a custom pin elsewhere (e.g. a
// pin near the epicenter showing the same low level Bangkok would see, far
// away). This recomputes MMI/level LOCALLY for the resolved "you" point,
// as an exact client-side port of server/simulator.py's own
// pga_at_distance()+pga_to_mmi()+_level_for_mmi() -- same formulas, same
// constants, evaluated at an arbitrary point instead of only the reference
// station. The server's own broadcast alert (siren, topbar pill, WS toast)
// intentionally stays anchored to the shared reference station -- one real
// alert must mean one shared severity for the dispatch/siren pipeline, only
// this personalized display panel should differ per viewer.
let LEVEL_BANDS = null, levelBandsPromise = null;
async function getLevelBands(){
  if(LEVEL_BANDS) return LEVEL_BANDS;
  if(!levelBandsPromise) levelBandsPromise = api('/api/levels').then(rows=>{
    LEVEL_BANDS = rows.slice().sort((a,b)=>a.lv-b.lv);
    return LEVEL_BANDS;
  }).catch(()=>null);
  return levelBandsPromise;
}

const MMI_ROMAN_JS = ['I','II','III','IV','V','VI','VII','VIII','IX','X','XI','XII'];
function mmiRomanJs(mmi){ return MMI_ROMAN_JS[Math.max(0, Math.min(11, Math.floor(mmi) - 1))]; }

// Exact port of pga_at_distance()+pga_to_mmi() from server/simulator.py --
// same synthetic magnitude-scaling/attenuation shape, same real, cited
// Wald et al. (1999) PGA->MMI conversion already used server-side.
function predictMmiJs(magnitude, distKm, depthKm){
  const MMI_PGA_SCALE = 40.0;
  const hypoKm = Math.sqrt(distKm * distKm + depthKm * depthKm);
  const atten = 1 / (1 + hypoKm / 55);
  const ampMult = Math.pow(10, (magnitude - 4.8) / 2.0);
  const pgaGal = MMI_PGA_SCALE * atten * ampMult;
  if(pgaGal <= 0) return 1.0;
  const low = 2.20 * Math.log10(pgaGal) + 1.00;
  const high = 3.66 * Math.log10(pgaGal) - 1.66;
  const mmi = low <= 4.22 ? low : high;
  return Math.max(1.0, Math.min(12.0, mmi));
}

// Exact port of _level_for_mmi()'s SQL: highest lv whose [mmi_min, mmi_max)
// band contains mmi, an open-ended top band (mmi_max IS NULL) included.
function levelForMmiJs(mmi, bands){
  for(let i = bands.length - 1; i >= 0; i--){
    const b = bands[i];
    if(mmi >= b.mmi_min && (b.mmi_max == null || mmi < b.mmi_max)) return b;
  }
  return bands[0];
}

// Returns a level/MMI object for the resolved "you" point, or null if the
// level bands haven't loaded yet or "you" can't be resolved -- callers must
// fall back to the server's own (reference-station) ev.level/predicted_mmi
// in that case, exactly as they did before this existed.
function computeYouLevelForEvent(ev){
  if(!ev || !LEVEL_BANDS || !situationData) return null;
  const you = resolveYouLocation(situationData);
  if(!you) return null;
  const distKm = haversineKm(ev.lat, ev.lng, you.lat, you.lng);
  const mag = ev.magnitude_estimate ?? ev.magnitude;
  const mmi = predictMmiJs(mag, distKm, ev.depth);
  const row = levelForMmiJs(mmi, LEVEL_BANDS);
  return {
    level: row.lv, level_name: row.name, message: row.message,
    channels: row.channels, siren: row.siren, color: row.color,
    predicted_mmi: mmi, predicted_mmi_roman: mmiRomanJs(mmi), dist_km: distKm,
  };
}

// Merges computeYouLevelForEvent()'s result onto `ev`, or null if no real
// location is set / it can't be computed yet -- the shape every level/
// location-guidance renderer expects as their first argument. Shared so the
// override-button and location-type-select handlers (which re-render
// #locationGuidancePanel outside of paintSituation's own render pass) build
// the exact same object paintSituation does, instead of duplicating this.
function getEvForGuidance(ev){
  const youLevel = computeYouLevelForEvent(ev);
  return youLevel ? {...ev, ...youLevel} : null;
}

/* ---- seismic-wave ripple animation: expanding P/S wave-front circles, timed to the real Vp/Vs used for the arrival countdown ---- */
let rippleAnimId = null, rippleCircles = null, rippleEventId = null, rippleFallbackTimer = null;
// Set once a ripple has naturally expired (swept past its own felt radius),
// distinct from rippleEventId being cleared for other reasons -- without
// this, a later periodic repaint of the SAME still-active event would see
// rippleEventId no longer matching and restart the ripple from scratch, only
// for the very first frame (elapsed time already huge) to immediately
// exceed the felt radius again and stop it -- and see stopRipple()'s note
// below for why that restart-then-instantly-stop cycle was also silently
// resurrecting the countdown callout every ~400ms after it should have
// stayed hidden.
let rippleExpiredEventId = null;
let ripplePinDistKm = null, rippleSeenNotArrived = false, rippleArrivalFired = false;
function stopRipple(){
  if(rippleAnimId) cancelAnimationFrame(rippleAnimId);
  rippleAnimId = null;
  if(rippleFallbackTimer) clearInterval(rippleFallbackTimer);
  rippleFallbackTimer = null;
  if(rippleCircles){ rippleCircles.forEach(c=>{ try{ leafletMap.removeLayer(c); }catch(e){} }); }
  rippleCircles = null;
  rippleEventId = null;
  ripplePinDistKm = null; rippleSeenNotArrived = false; rippleArrivalFired = false;
  // The countdown callout is only allowed to be visible while a wave circle
  // is actually being drawn (see revealWaveCountdownIfVisible) -- once the
  // ripple stops (event cleared, or the wave has swept past its own felt
  // radius and removed itself), there is no circle left on the map at all,
  // so the callout must go back to hidden too instead of staying visible
  // forever after the one time it was revealed.
  const waveCountdownEl = document.querySelector('.wave-countdown-callout');
  if(waveCountdownEl) waveCountdownEl.hidden = true;
}
// `pinLat`/`pinLng` -- the "ตำแหน่งของคุณ" map pin (see paintMap's `you`) --
// are optional; when given, the arrival sound (see playArrivalSound) fires
// at the exact rendered frame where the solid red S-wave circle's edge first
// reaches/covers that pin, so the sound change is tied to what's actually
// visible on the map rather than to the once-a-second countdown tick. Only
// fires on a genuine not-yet-covered -> covered transition observed *during
// this animation* (rippleSeenNotArrived), so reopening/refreshing the page
// well after a real quake's wave has already passed never plays it.
// Approximate "felt radius" for the P/S ripple rings: the distance at which
// shaking fades below MMI ~II (barely perceptible), so a small event's rings
// fade out close to the epicenter and a large one's reach much farther --
// instead of every event sharing the same fixed 3000km ceiling regardless of
// magnitude. This is the algebraic inverse of this same app's own server-side
// attenuation model (server/simulator.py pga_at_distance/pga_to_mmi/
// MMI_PGA_SCALE/magnitude_amp_multiplier) solved for distance instead of PGA
// -- same illustrative physics, not a real GMPE, kept consistent with the
// numbers already driving the rest of this app's MMI predictions.
function feltRadiusKm(magnitude, depthKm){
  const MMI_PGA_SCALE = 40.0;
  const mag = magnitude || 5.0, depth = depthKm || 10.0;
  const ampMult = Math.pow(10, (mag - 4.8) / 2.0);
  const targetMmi = 2.0; // below this, treated as "not felt"
  const targetPga = targetMmi <= 4.22 ? Math.pow(10, (targetMmi - 1.00) / 2.20) : Math.pow(10, (targetMmi + 1.66) / 3.66);
  const atten = targetPga / (MMI_PGA_SCALE * ampMult);
  if(atten <= 0 || atten >= 1) return 3000; // fallback: same ceiling as before
  const hypoKm = 55 * (1 / atten - 1);
  const distKm = Math.sqrt(Math.max(0, hypoKm * hypoKm - depth * depth));
  return Math.min(3000, Math.max(50, distKm));
}

function startRipple(ev, vpKmS, vsKmS, pinLat, pinLng){
  if(rippleEventId === ev.id) return; // already animating this event
  if(rippleExpiredEventId === ev.id) return; // already swept past its felt radius -- don't resurrect it
  stopRipple();
  rippleEventId = ev.id;
  ripplePinDistKm = (pinLat != null && pinLng != null) ? haversineKm(ev.lat, ev.lng, pinLat, pinLng) : null;
  rippleSeenNotArrived = false; rippleArrivalFired = false;
  const center = [ev.lat, ev.lng];
  const startMs = new Date(ev.ts).getTime();
  const pWave = L.circle(center, {radius:1, color:'#63a4ee', weight:1.5, fillOpacity:0, opacity:.55, dashArray:'1 6', interactive:false});
  const sWave = L.circle(center, {radius:1, color:'#d03b3b', weight:2, fillColor:'#d03b3b', fillOpacity:.05, opacity:.75, interactive:false});
  pWave.addTo(leafletMap); sWave.addTo(leafletMap);
  rippleCircles = [pWave, sWave];
  const MAX_RADIUS_M = feltRadiusKm(ev.magnitude_estimate ?? ev.magnitude, ev.depth) * 1000; // magnitude/depth-scaled: stop once both fronts have swept past this event's plausible felt radius
  // Shared by both the rAF-driven frame() below (precise, but only runs while
  // this tab is visible and compositing -- browsers throttle/suspend
  // requestAnimationFrame in a backgrounded tab or a locked screen) and the
  // setInterval fallback beneath it (coarser, but keeps running regardless of
  // tab visibility). Life-safety: a user is at least as likely to have
  // switched apps or locked their phone the moment a Level 6 wave arrives as
  // to be staring at the map, so the sound trigger must not depend on the
  // page being visible. Both call this with the identical arrived/not-arrived
  // state, so whichever notices the crossing first fires it -- the
  // rippleArrivalFired guard makes a double-fire from both paths harmless.
  function checkPinCrossing(sR){
    if(ripplePinDistKm == null) return;
    const sKm = sR / 1000;
    if(sKm < ripplePinDistKm){
      rippleSeenNotArrived = true;
    } else if(rippleSeenNotArrived && !rippleArrivalFired){
      rippleArrivalFired = true;
      // Read the level fresh from live state rather than the closure's `ev`
      // snapshot -- the confidence/magnitude estimate (and so the level)
      // can still upgrade in the seconds/minutes the wave spends travelling
      // to the pin, and the arrival sound must reflect the current level.
      const liveEv = (situationData && situationData.event && situationData.event.id === ev.id) ? situationData.event : ev;
      // Pin-based level (see getEvForGuidance) -- the whole point of this
      // callback is "the wave just reached YOUR pin", so the sound it plays
      // must reflect the severity AT that pin, not the reference station.
      const youLevel = getEvForGuidance(liveEv);
      if(youLevel) playArrivalSound(youLevel.level);
    }
  }
  // The countdown callout (.wave-countdown-callout) starts `hidden` in its
  // template every repaint -- this is the ONLY place that reveals it, and
  // only once the P-wave circle has grown past a genuinely visible radius,
  // not merely the instant startRipple()/frame() first runs (radius could
  // still be ~0m then, i.e. no circle a human could actually see yet). Runs
  // every animation frame so it also re-reveals within one frame after a
  // periodic repaint resets the element back to hidden, with no dependence
  // on rippleEventId (which flags "the ripple exists in code", not "a
  // visible circle is on screen" -- the distinction this exists to fix).
  const RIPPLE_VISIBLE_RADIUS_M = 2000; // ~2km: small but a real, renderable circle
  function revealWaveCountdownIfVisible(pR){
    if(pR < RIPPLE_VISIBLE_RADIUS_M) return;
    const el = document.querySelector('.wave-countdown-callout');
    if(el && el.hidden) el.hidden = false;
  }
  function frame(){
    const elapsedSec = Math.max(0, (Date.now() - startMs) / 1000);
    const pR = elapsedSec * vpKmS * 1000, sR = elapsedSec * vsKmS * 1000;
    pWave.setRadius(pR);
    sWave.setRadius(sR);
    const fade = Math.max(0, 1 - sR / MAX_RADIUS_M);
    pWave.setStyle({opacity: .55 * fade});
    sWave.setStyle({opacity: .75 * fade, fillOpacity: .05 * fade});
    checkPinCrossing(sR);
    // Check expiry BEFORE revealing -- a repaint can call startRipple() for
    // an event whose elapsed time already exceeds MAX_RADIUS_M on this very
    // first frame (e.g. a slow/high-speed-multiplier scenario the viewer
    // comes back to later), and that must go straight to expired/hidden
    // rather than flash the countdown callout visible for one frame first.
    if(sR > MAX_RADIUS_M){ rippleExpiredEventId = ev.id; stopRipple(); return; }
    revealWaveCountdownIfVisible(pR);
    rippleAnimId = requestAnimationFrame(frame);
  }
  frame();
  // Guard: frame() above may have already expired and called stopRipple()
  // synchronously (see the comment on rippleExpiredEventId) -- in that case
  // rippleCircles is back to null and this must NOT set up a fallback timer
  // for a ripple that no longer exists. Before this guard existed, such a
  // timer kept running forever, calling revealWaveCountdownIfVisible() every
  // 400ms with an elapsed time that only ever grows -- silently un-hiding
  // the countdown callout again and again even though no wave circle was
  // actually on the map any more.
  if(rippleCircles){
    rippleFallbackTimer = setInterval(()=>{
      const elapsedSec = Math.max(0, (Date.now() - startMs) / 1000);
      checkPinCrossing(elapsedSec * vsKmS * 1000);
      if(elapsedSec * vsKmS * 1000 > MAX_RADIUS_M){ rippleExpiredEventId = ev.id; stopRipple(); return; }
      revealWaveCountdownIfVisible(elapsedSec * vpKmS * 1000);
    }, 400);
  }
}

function epicenterIcon(){
  return L.divIcon({
    className:'', html:`<div class="quake-pulse" style="width:14px;height:14px;border:2px solid #fff;"></div>`,
    iconSize:[14,14], iconAnchor:[7,7],
  });
}

// "There is an active event right now" -- fires for the exact same
// active_event a real detection produces, and (per explicit request) for a
// "จำลองแผ่นดินไหว" demo trigger too, since both populate the identical
// server-side active_event and this card has no way (or need) to tell them
// apart. Distinct from #realQuakeTicker, which is specifically the latest
// REAL event from the external USGS/EMSC/GEOFON/TMD feeds.
function paintActiveEventCard(ev){
  const card = document.getElementById('activeEventCard');
  if(!card) return;
  // A genuine simulated event takes over this card -- clear any real-quake
  // "ดูคลื่นแผ่นดินไหว" view state first so its timer/marker doesn't keep
  // running stale underneath the real thing (see viewRealQuakeWave below).
  // A GENUINE simulated event (a different object than the real-quake-view's
  // own synthetic ev, which also calls this function to render itself into
  // the same card) takes over this card -- clear any real-quake-view
  // timer/marker so it doesn't keep running stale underneath the real thing.
  if(ev && ev !== realQuakeViewEv) clearRealQuakeViewState();
  if(!ev){
    // A real-quake view owns this card right now -- the periodic "no
    // simulated event" repaint (paintMap() calling this with null every
    // refresh in real-data-only mode) must not clobber it.
    if(realQuakeViewEv) return;
    card.hidden = true; card.innerHTML = ''; return;
  }
  card.hidden = false;
  const d = new Date(ev.ts);
  const dateStr = d.toLocaleDateString('th-TH', {day:'numeric', month:'short', year:'numeric'});
  const timeStr = d.toLocaleTimeString('th-TH', {hour:'2-digit', minute:'2-digit'}) + ' น.';
  const shortPlace = (ev.place || 'ไม่ทราบตำแหน่ง').split('—')[0].trim();
  card.innerHTML = `
    <div class="aec-head">
      <div class="aec-title">${icon('warnTri')}<span>กำลังเกิดเหตุการณ์ขณะนี้</span></div>
      <button type="button" class="aec-refresh" id="aecRefreshBtn" title="เลื่อนแผนที่ไปยังศูนย์กลางเหตุการณ์">${icon('refresh')}</button>
    </div>
    <div class="aec-row">${icon('clock')}<span>${dateStr} · ${timeStr}</span></div>
    <div class="aec-row">${icon('info')}<span>ขนาด <b>M${ev.magnitude}</b> · ลึก <b>${ev.depth}</b> กม.</span></div>
    <div class="aec-row">${icon('pin')}<span>${shortPlace}</span></div>
    <div class="aec-row">${icon('target')}<span>พิกัด (${Number(ev.lat).toFixed(3)}, ${Number(ev.lng).toFixed(3)})</span></div>`;
  const btn = document.getElementById('aecRefreshBtn');
  if(btn) btn.addEventListener('click', ()=>{ if(leafletMap) leafletMap.setView([ev.lat, ev.lng], 7); });
}

// ---- "ดูคลื่นแผ่นดินไหว" -- view a REAL quake from the world feed (map,
// "0. สถานการณ์ปัจจุบัน" mode) using the exact same wave-ripple/countdown
// visualization the simulated demo pipeline uses, referenced against the
// viewer's own Pin -- entirely client-side (no server/simulator state is
// touched; this never creates a real ENVIRO "event", just a client-side
// visualization of a real one). Real quakes are never sped up.
const VP_KM_S_REAL = 6.5, VS_KM_S_REAL = 3.8; // matches server/simulator.py's real-world constants
let realQuakeViewEv = null, realQuakeViewTimer = null, realQuakeEpicenterMarker = null, realQuakeStaticCircle = null;

// Thai "how long ago" string for the explanation shown when a real quake's
// wave has already fully swept past its felt radius by the time someone
// clicks "ดูคลื่นแผ่นดินไหว" -- almost always true for anything more than a
// few minutes old, which is most of what the world-quake feed shows (a list
// of past events, not a live one), so this needs to read naturally for
// minutes/hours/days, not just seconds.
function fmtElapsedThai(sec){
  sec = Math.max(0, Math.round(sec));
  if(sec < 60) return `${sec} วินาที`;
  const min = Math.floor(sec/60);
  if(min < 60) return `${min} นาที`;
  const hr = Math.floor(min/60);
  if(hr < 24) return `${hr} ชั่วโมง ${min%60} นาที`;
  const day = Math.floor(hr/24);
  return `${day} วัน ${hr%24} ชั่วโมง`;
}

function clearRealQuakeViewState(){
  if(realQuakeViewTimer){ clearInterval(realQuakeViewTimer); realQuakeViewTimer = null; }
  realQuakeViewEv = null;
  if(realQuakeEpicenterMarker && mapLayer){ try{ mapLayer.removeLayer(realQuakeEpicenterMarker); }catch(e){} realQuakeEpicenterMarker = null; }
  if(realQuakeStaticCircle && mapLayer){ try{ mapLayer.removeLayer(realQuakeStaticCircle); }catch(e){} realQuakeStaticCircle = null; }
}
function stopRealQuakeView(){
  clearRealQuakeViewState();
  stopRipple();
  paintActiveEventCard(null);
}

// Draws (or redraws, after a periodic paintMap() repaint wiped mapLayer) the
// epicenter marker plus, depending on whether the wave has already swept
// past its own felt radius by *now*: a static dashed "this is as far as it
// reached" circle (already expired -- see the alreadyExpired comment in
// viewRealQuakeWave), or a resumed live P/S ripple (still within its felt
// radius). startRipple() is safe to call repeatedly for the same ev.id --
// it no-ops if already animating (rippleEventId match) or already expired
// (rippleExpiredEventId match), and otherwise picks up from the true
// elapsed wall-clock time, so calling it again after paintMap()'s
// stopRipple() resumes the animation in place rather than restarting it.
function paintRealQuakeOverlay(ev, you){
  if(!leafletMap || !mapLayer) return null;
  realQuakeEpicenterMarker = L.marker([ev.lat, ev.lng], {icon: epicenterIcon()})
    .bindPopup(`<b>เหตุการณ์จริง</b><br>M${ev.magnitude!=null?ev.magnitude.toFixed(1):'?'} ลึก ${ev.depth} กม.<br>${ev.place}`)
    .addTo(mapLayer);
  const originMs = new Date(ev.ts).getTime();
  const elapsedNowSec = Math.max(0, (Date.now() - originMs) / 1000);
  const feltKm = feltRadiusKm(ev.magnitude_estimate ?? ev.magnitude, ev.depth);
  const alreadyExpired = elapsedNowSec * VS_KM_S_REAL > feltKm;
  if(alreadyExpired){
    realQuakeStaticCircle = L.circle([ev.lat, ev.lng], {
      radius: feltKm * 1000, color:'#d03b3b', weight:1.5, dashArray:'4 6',
      fillColor:'#d03b3b', fillOpacity:.04, opacity:.5, interactive:false,
    }).addTo(mapLayer);
  } else if(you){
    startRipple(ev, VP_KM_S_REAL, VS_KM_S_REAL, you.lat, you.lng);
  }
  return {alreadyExpired, feltKm, elapsedNowSec};
}

function viewRealQuakeWave(lat, lng, magnitude, depthKm, timeMs, place){
  if(!isRealDataOnlyMode()){
    showToast('ใช้ได้เฉพาะโหมด "0. สถานการณ์ปัจจุบัน"', 'สลับ dropdown สถานการณ์ด้านบนกลับไปที่ "0. สถานการณ์ปัจจุบัน" ก่อน', false);
    return;
  }
  const you = situationData ? resolveYouLocation(situationData) : null;
  if(!you){
    showToast('ยังไม่ได้ตั้งค่าตำแหน่ง', 'กรุณากดปุ่ม "ตำแหน่งที่ตั้ง" ตั้งค่าตำแหน่งของคุณก่อน เพื่อดูว่าคลื่นจะมาถึงคุณเมื่อไหร่', false);
    return;
  }
  if(leafletMap) leafletMap.closePopup();
  clearRealQuakeViewState();
  const ev = {
    id: 'real-view-' + timeMs, ts: new Date(timeMs).toISOString(),
    lat, lng, magnitude, magnitude_estimate: magnitude, depth: depthKm != null ? depthKm : 10,
    place: place || 'ไม่ทราบตำแหน่ง',
  };
  realQuakeViewEv = ev;
  ensureMap();

  // A real quake pulled from the world feed is, by definition, something
  // that already happened -- often minutes, hours, or days ago, not "right
  // now". If its S-wave has already swept past this event's own felt radius
  // (see feltRadiusKm) before the button was even clicked, an animated
  // ripple has nothing left to show: startRipple()'s very first frame would
  // compute a radius already past MAX_RADIUS_M and self-expire before
  // rendering a single visible circle -- correct physics, but silent and
  // confusing (looks like the feature is just broken). paintRealQuakeOverlay
  // detects that case up front and shows a static "how far this one
  // reached" circle plus (below) an explicit explanation, instead of either
  // a blank map or a silently-dropped ripple.
  const {alreadyExpired, feltKm, elapsedNowSec} = paintRealQuakeOverlay(ev, you);
  autoFitMapToEvent(ev, you);
  paintActiveEventCard(ev);
  if(alreadyExpired){
    showToast(
      'เหตุการณ์นี้ผ่านไปแล้ว ไม่มีคลื่นเคลื่อนที่ให้แสดง',
      `เกิดขึ้นเมื่อ ${fmtElapsedThai(elapsedNowSec)} ที่แล้ว — แรงสั่นสะเทือนแผ่ไปถึงระยะประมาณ ${Math.round(feltKm)} กม. แล้วสงบลงทั้งหมด (เส้นประบนแผนที่ = ขอบเขตที่เคยรู้สึกได้)`,
      false,
    );
  } else {
    showToast('กำลังแสดงคลื่นแผ่นดินไหวจริงบนแผนที่', `M${magnitude!=null?magnitude.toFixed(1):'?'} ${ev.place} — อ้างอิงตำแหน่งของคุณ`);
  }

  const startMs = new Date(ev.ts).getTime();
  const tick = ()=>{
    const you2 = situationData ? resolveYouLocation(situationData) : null;
    if(!you2){ stopRealQuakeView(); return; }
    const distKm = haversineKm(lat, lng, you2.lat, you2.lng);
    const elapsedSec = Math.max(0, (Date.now() - startMs) / 1000);
    const sRemain = Math.max(0, distKm / VS_KM_S_REAL - elapsedSec);
    const sArrived = sRemain <= 0;
    // Recomputed every tick (not just once at click-time) -- feltKm doesn't
    // change, but a quake that was still "live" when the button was clicked
    // naturally crosses into "already past its felt radius" while being
    // watched, and the countdown row must reflect that transition too.
    const stillWithinFeltRadius = elapsedSec * VS_KM_S_REAL <= feltKm;
    const card = document.getElementById('activeEventCard');
    if(!card || card.hidden) return;
    let row = document.getElementById('realQuakeCountdownRow');
    if(!row){
      row = document.createElement('div');
      row.className = 'aec-row'; row.id = 'realQuakeCountdownRow';
      card.appendChild(row);
      const closeBtn = document.createElement('button');
      closeBtn.type = 'button'; closeBtn.className = 'btn';
      closeBtn.style.cssText = 'margin-top:8px;padding:6px 12px;font-size:14px;width:100%;';
      closeBtn.textContent = 'ปิดการแสดงคลื่น';
      closeBtn.addEventListener('click', stopRealQuakeView);
      card.appendChild(closeBtn);
    }
    if(!stillWithinFeltRadius){
      row.innerHTML = `${icon('info')}<span>เหตุการณ์นี้ผ่านไปแล้ว <b>${fmtElapsedThai(elapsedSec)}</b> ที่แล้ว — คลื่นสงบลงทั่วบริเวณที่เคยรู้สึกได้ (~${Math.round(feltKm)} กม.) ก่อนถึงตำแหน่งคุณแล้ว จึงไม่มีคลื่นเคลื่อนที่ให้แสดง</span>`;
    } else {
      row.innerHTML = `${icon('warnTri')}<span>คลื่น S ถึงตำแหน่งคุณโดยประมาณใน <b class="tabular">${sArrived?'มาถึงแล้ว':fmtTime(sRemain)}</b> น.:ว.</span>`;
    }
  };
  tick();
  realQuakeViewTimer = setInterval(tick, 1000);
}

// Lets a viewer set their own real position (device GPS, or typed lat/lng)
// so the "📍 ตำแหน่งของคุณ" map pin -- and everything client-side keyed off
// it (auto-fit-to-event, the S-wave arrival sound trigger) -- reflects where
// they actually are, instead of always the fixed reference station used for
// the server's own official MMI/level calculation. Deliberately scoped to
// the map/client side only: the server's predicted-MMI/alert-level/siren
// pipeline still runs off the fixed reference station (BKK-201) regardless --
// rewiring that too is a materially bigger backend change, not implied by
// "add a button here".
function getUserCustomLocation(){
  try{
    const raw = localStorage.getItem('enviro_user_location');
    if(!raw) return null;
    const v = JSON.parse(raw);
    if(typeof v?.lat === 'number' && typeof v?.lng === 'number') return v;
  }catch(e){}
  return null;
}
function setUserCustomLocation(lat, lng){
  localStorage.setItem('enviro_user_location', JSON.stringify({lat, lng}));
  renderUserLocationUI();
  if(situationData) paintMap(situationData);
}
function clearUserCustomLocation(){
  localStorage.removeItem('enviro_user_location');
  renderUserLocationUI();
  if(situationData) paintMap(situationData);
}
function renderUserLocationUI(){
  const btn = document.getElementById('userLocationBtn');
  const status = document.getElementById('userLocationStatus');
  const clearBtn = document.getElementById('clearLocBtn');
  const loc = getUserCustomLocation();
  if(btn) btn.classList.toggle('set', !!loc);
  if(status){
    status.className = 'loc-popover-status' + (loc ? ' set' : '');
    status.textContent = loc
      ? `กำลังใช้ตำแหน่งที่คุณตั้งไว้: (${loc.lat.toFixed(5)}, ${loc.lng.toFixed(5)})`
      : `ยังไม่ได้ตั้งค่า — ระบบจะยังไม่แสดงความรุนแรงเฉพาะตำแหน่งของคุณจนกว่าจะใช้ GPS หรือกรอกพิกัดเอง`;
  }
  if(clearBtn) clearBtn.hidden = !loc;
}
function wireUserLocationControls(){
  const btn = document.getElementById('userLocationBtn');
  const pop = document.getElementById('userLocationPopover');
  if(!btn || !pop) return;
  btn.addEventListener('click', e=>{ e.stopPropagation(); pop.hidden = !pop.hidden; });
  document.addEventListener('click', e=>{
    if(!pop.hidden && !pop.contains(e.target) && e.target !== btn) pop.hidden = true;
  });
  document.getElementById('useGpsBtn').addEventListener('click', ()=>{
    if(!navigator.geolocation){ showToast('ไม่รองรับ GPS', 'เบราว์เซอร์นี้ไม่รองรับการขอตำแหน่งจากอุปกรณ์', false); return; }
    const gpsBtn = document.getElementById('useGpsBtn');
    gpsBtn.disabled = true; const original = gpsBtn.innerHTML; gpsBtn.innerHTML = 'กำลังขอตำแหน่ง...';
    navigator.geolocation.getCurrentPosition(
      pos=>{
        // Only fills the lat/lng fields -- doesn't apply/close on its own,
        // so the viewer can see and, if needed, tweak what GPS returned
        // before committing to it via the same "ใช้พิกัดนี้" button typed
        // coordinates use.
        document.getElementById('manualLat').value = pos.coords.latitude;
        document.getElementById('manualLng').value = pos.coords.longitude;
        gpsBtn.disabled = false; gpsBtn.innerHTML = original;
        showToast('ดึงพิกัดจาก GPS สำเร็จ', `(${pos.coords.latitude.toFixed(5)}, ${pos.coords.longitude.toFixed(5)}) — กด "ใช้พิกัดนี้" เพื่อยืนยัน`);
      },
      err=>{
        gpsBtn.disabled = false; gpsBtn.innerHTML = original;
        showToast('ขอตำแหน่งไม่สำเร็จ', err.message || 'กรุณาอนุญาตการเข้าถึงตำแหน่งของเบราว์เซอร์', false);
      },
      {enableHighAccuracy:true, timeout:10000},
    );
  });
  document.getElementById('saveManualLocBtn').addEventListener('click', async ()=>{
    const lat = Number(document.getElementById('manualLat').value);
    const lng = Number(document.getElementById('manualLng').value);
    if(!Number.isFinite(lat) || lat < -90 || lat > 90 || !Number.isFinite(lng) || lng < -180 || lng > 180){
      showToast('พิกัดไม่ถูกต้อง', 'ละติจูดต้องอยู่ระหว่าง -90 ถึง 90 และลองจิจูดระหว่าง -180 ถึง 180', false);
      return;
    }
    setUserCustomLocation(lat, lng);
    document.getElementById('userLocationPopover').hidden = true;
    showToast('ใช้พิกัดนี้แล้ว', `หมุดย้ายไปที่ (${lat.toFixed(5)}, ${lng.toFixed(5)})`);
    // Re-paint immediately -- otherwise the map pin, the S/P countdown, and
    // the ripple's arrival-sound trigger point would all keep showing the
    // OLD position until the next periodic refresh, exactly the kind of
    // pin/countdown mismatch this whole fix is about.
    if(situationData) await paintSituation();
    // Per explicit request: the map must always re-center on a freshly
    // entered coordinate, at a wide-ish zoom -- otherwise (e.g. with no
    // active event, so autoFitMapToEvent never runs) the view just stays
    // wherever it happened to be panned before, with the new pin possibly
    // off-screen entirely. Called AFTER the repaint so it's the last word
    // on where the map ends up, even if an active event's own auto-fit also
    // just ran.
    if(leafletMap) leafletMap.setView([lat, lng], 8);
  });
  document.getElementById('clearLocBtn').addEventListener('click', ()=>{
    clearUserCustomLocation();
    document.getElementById('userLocationPopover').hidden = true;
    if(situationData) paintSituation();
  });
  renderUserLocationUI();
}

// Automatically frames the map so both the epicenter AND the user's own
// reference pin are visible together the moment a NEW event starts -- so a
// viewer immediately sees where it happened relative to themselves, without
// hunting for the epicenter marker or manually panning/zooming. Guarded to
// fire once per distinct event id, not on every 15s/WS repaint of the SAME
// still-active event -- otherwise it would keep yanking back any manual pan
// or zoom the viewer had just made while reading the map.
let lastAutoFitEventId = null;
function autoFitMapToEvent(ev, you){
  if(!ev || !you || !leafletMap || lastAutoFitEventId === ev.id) return;
  lastAutoFitEventId = ev.id;
  const bounds = L.latLngBounds([[ev.lat, ev.lng], [you.lat, you.lng]]);
  leafletMap.fitBounds(bounds, {padding: [70, 70], maxZoom: 8});
}

function paintMap(data){
  ensureMap();
  mapLayer.clearLayers();
  paintActiveEventCard(data.event);

  data.faults.forEach(f=>{
    L.polyline([[f.lat1,f.lng1],[f.lat2,f.lng2]], {color:'#ec835a', weight:2.5, dashArray:'2 6', opacity:.85})
      .bindPopup(`<b>${f.name}</b><br>${f.region} · แนวรอยเลื่อนมีพลังของไทย (เส้นทางเป็นการประมาณเชิงพื้นที่)`)
      .addTo(mapLayer);
  });

  data.stations.forEach(s=>{
    // ออนไลน์ = เขียว, ออฟไลน์ = ฟ้า -- เดียวกับโหนดตรวจวัดจริง/จำลองใน
    // paintNodesMap/refreshSituationNodes ด้านล่าง ให้ทั้งแอปใช้อนุสัญญาสี
    // เดียวกันสำหรับ "สถานี ENVIRO" ทุกประเภท (ดู legend ใน situationShell())
    const c = s.status==='online' ? '#5fe05f' : '#63a4ee';
    L.circleMarker([s.lat,s.lng], {
      radius:6, color:c, weight:1.5, fillColor:c, fillOpacity:.9,
    }).bindPopup(`<b>${s.id}</b><br>${s.region} · ${s.status==='online'?'ออนไลน์':'ออฟไลน์'} (สถานีจำลองของ ENVIRO)`).addTo(mapLayer);
  });

  const ev = data.event;
  const you = resolveYouLocation(data);
  if(ev){
    L.marker([ev.lat, ev.lng], {icon: epicenterIcon()})
      .bindPopup(`<b>${ev.id}</b><br>ศูนย์กลาง M${ev.magnitude} ลึก ${ev.depth} กม.<br>${ev.place}<br><span style="color:#8a94a6;">เหตุการณ์จำลองของ ENVIRO</span>`)
      .addTo(mapLayer);
    startRipple(ev, data.vp_km_s, data.vs_km_s, you ? you.lat : null, you ? you.lng : null);
    autoFitMapToEvent(ev, you);
  } else {
    stopRipple();
    if(data.pending_quake){
      const q = data.pending_quake;
      L.circleMarker([q.lat,q.lng], {radius:8, color:'#fab219', weight:2, fillColor:'#fab219', fillOpacity:.35, dashArray:'3 3'})
        .bindPopup(`<b>จุดเฝ้าระวังปัจจุบัน</b><br>${q.place}<br>${q.fault}`)
        .addTo(mapLayer);
    }
  }

  if(you){
    // Same pin-position MMI/level recompute the impact panel uses (see
    // computeYouLevelForEvent) -- the map pin's own color now matches what
    // the panel says about that exact point, instead of always being a
    // plain black dot regardless of how severe it is right there.
    const youLevel = ev ? computeYouLevelForEvent(ev) : null;
    const pinColor = youLevel ? levelPillStyle(youLevel.level)[1] : null;
    const levelLine = youLevel
      ? `<br><b style="color:${pinColor};">MMI ${youLevel.predicted_mmi_roman} · ระดับแจ้งเตือน ${youLevel.level} (${youLevel.level_name})</b>`
      : '';
    L.marker([you.lat, you.lng], {icon: youPinIcon(pinColor), zIndexOffset: 1000})
      .bindPopup(`<b>ตำแหน่งของคุณ</b><br>${you.region}${levelLine}`)
      .addTo(mapLayer);
  }

  // `mapLayer.clearLayers()` above wipes EVERY marker/circle added to it,
  // including a "ดูคลื่นแผ่นดินไหว" real-quake overlay's epicenter marker and
  // (once expired) its static felt-radius circle -- and the `else` branch
  // above calls stopRipple() outright whenever there's no active *simulated*
  // event, which kills a real-quake-view's still-running P/S ripple too. Both
  // would otherwise silently vanish off the map on every ~15s situation poll
  // (see situationRefreshTimer) while the countdown card kept ticking along
  // untouched, looking exactly like "the wave just isn't shown" even for a
  // fresh, still-animating real quake. Restore/resume it here, every repaint,
  // whenever a real-quake view is active and no simulated event has taken
  // over (paintActiveEventCard(data.event) above already cleared
  // realQuakeViewEv in that case).
  if(realQuakeViewEv && !ev){
    paintRealQuakeOverlay(realQuakeViewEv, you);
  }
}

let situationTimer = null, situationRefreshTimer = null, situationData = null;

// "จำลองแผ่นดินไหว" toggle state -- red+blinking while a (simulated or real)
// event is active, grey+static otherwise. "ตำแหน่งที่ตั้ง" is deliberately
// NOT gated on this: per explicit request it must stay clickable/settable
// at all times, independent of whether a simulation is running.
let simulateActive = false;
// Set true the instant a trigger POST succeeds, independent of whether the
// server has actually *declared* an event yet -- schedule -> detection has
// a real few-second STA/LTA delay (see Simulator.trigger_manual_quake), and
// the button must go red the moment the user starts it, not only once
// active_event finally appears. Only stopSimulatedQuake() clears this.
let manualSimulateStarted = false;
// All 3 must be set before "จำลองแผ่นดินไหว" can start a NEW simulation --
// per explicit request, nothing should be simulated/shown until the viewer
// has (1) set their own ตำแหน่งที่ตั้ง, (2) picked an actual scenario
// (not "0. สถานการณ์ปัจจุบัน", which means "no simulation" by design), and
// (3) picked a speed. Does not gate STOPPING an already-running simulation.
function simulateGateOk(){
  const scenario = document.getElementById('topSimulateScenario')?.value;
  const speed = document.getElementById('topSimulateSpeed')?.value;
  return !!getUserCustomLocation() && !!scenario && scenario !== 'current_real' && !!speed;
}

function describeMissingSimulateConditions(){
  const missing = [];
  if(!getUserCustomLocation()) missing.push('1) ตำแหน่งที่ตั้ง');
  const scenario = document.getElementById('topSimulateScenario')?.value;
  if(!scenario || scenario === 'current_real') missing.push('2) สถานการณ์จำลอง');
  if(!document.getElementById('topSimulateSpeed')?.value) missing.push('3) ความเร่ง');
  return missing;
}

function syncSimulateButtonUI(active){
  simulateActive = active;
  const btn = document.getElementById('topSimulateBtn');
  if(btn){
    btn.classList.toggle('sim-active', active);
    btn.classList.toggle('sim-idle', !active);
    // Starting requires the gate; stopping an already-running simulation
    // must always stay possible regardless of the gate's current state.
    btn.disabled = !active && !simulateGateOk();
  }
  // ตำแหน่งที่ตั้ง is intentionally NOT gated on simulateActive -- per
  // explicit request, the viewer must be able to set/change their position
  // at any time, whether or not a simulation is currently running.
}

function handleSimulateBtnClick(){
  if(simulateActive){ stopSimulatedQuake(); return; }
  // The button is `disabled` (so a real click can't normally reach here)
  // whenever the gate fails -- this is just defense in depth against a
  // programmatic .click(), with a message saying exactly what's missing.
  if(!simulateGateOk()){
    showToast('ยังเริ่มจำลองไม่ได้', `กรุณาตั้งค่าให้ครบก่อน: ${describeMissingSimulateConditions().join(', ')}`, false);
    return;
  }
  triggerRandomQuake();
}

async function stopSimulatedQuake(){
  const btn = document.getElementById('topSimulateBtn');
  if(btn) btn.disabled = true;
  try{
    await api('/api/admin/clear-event', {method: 'POST'});
    manualSimulateStarted = false;
    // Snap everything back to "0. สถานการณ์ปัจจุบัน" immediately, not just
    // the button color -- per explicit request, stopping must look and
    // behave exactly like the idle option was selected from the start,
    // not leave the old scenario chosen with a now-stale map/panel behind.
    const scenarioSel = document.getElementById('topSimulateScenario');
    if(scenarioSel) scenarioSel.value = 'current_real';
    updateTopbar();
    if(!document.getElementById('view-situation').hidden) await loadSituation();
    syncSimulateButtonUI(false);
    showToast('หยุดการจำลองแล้ว', 'เครือข่ายกลับสู่โหมดเฝ้าระวังตามปกติ');
  }catch(e){
    showToast('หยุดการจำลองไม่สำเร็จ', e.message, false);
    syncSimulateButtonUI(simulateActive); // stop failed -- restore whatever the real current state actually is
  }
}

/* "แผ่นดินไหวตอนนี้": real quakes near Thailand, which provinces would feel them, the tsunami screen and what to
   do -- in place of the AI-analysis panel while no simulated event is shown. Built from /api/world/brief (the AI
   brief tab's facts, last 7 days) and /api/world/tsunami, read again every 5 minutes; the 15-second situation
   repaint reuses the last HTML. */
let nowCardsHtml = '<div class="panel-sub">กำลังโหลดแผ่นดินไหวล่าสุด…</div>';
let nowCardsHint = '', nowCardsAt = 0, nowCardsBusy = false;
const NOW_CARDS_MS = 5 * 60000;

function nowQuakeTime(e){
  return e.time_ms ? new Date(e.time_ms).toLocaleString('th-TH', {day:'numeric', month:'short', hour:'2-digit', minute:'2-digit'}) : (e.time || '');
}

// The map shows the last 7 days, then centres on the quake
async function focusRealQuake(lat, lng){
  const rangeSel = document.getElementById('worldQuakeRange');
  if(rangeSel && rangeSel.value === 'realtime'){ rangeSel.value = '7'; await refreshWorldQuakes(); }
  if(leafletMap) leafletMap.setView([lat, lng], 6);
}

function nowCardsMarkup(brief, tsunami){
  const f = (brief && brief.ready && brief.facts) || null;
  const days = f ? f.window_days : 7;
  // 1. Latest real quakes near Thailand
  const near = f ? f.near.slice().sort((a, b) => (b.time_ms || 0) - (a.time_ms || 0)).slice(0, 5) : [];
  const quakes = !f ? '<p>ยังโหลดข้อมูลแผ่นดินไหวไม่ได้ ลองใหม่อีกครั้งภายหลัง</p>'
    : !near.length ? `<p>${days} วันที่ผ่านมา ไม่มีแผ่นดินไหวใกล้ประเทศไทย</p>`
    : near.map(e => `<button type="button" class="now-quake" onclick="focusRealQuake(${Number(e.lat)},${Number(e.lng)})">
        <span class="now-mag tabular" style="background:${magColor(e.magnitude)};">M${Number(e.magnitude).toFixed(1)}</span>
        <span><b>${escHtml(e.place)}</b>
          <small>${escHtml(nowQuakeTime(e))} · ห่างไทย ${Number(e.dist_th_km).toLocaleString()} กม. (ใกล้${escHtml(e.nearest_province)})</small>
          <small>${!e.felt_in_th ? 'คนไทยไม่รู้สึก'
            : e.max_mmi_th >= 3 ? `คนที่${escHtml(e.max_mmi_th_where || '')}รู้สึกได้`
            : `บางคนที่${escHtml(e.max_mmi_th_where || '')}อาจรู้สึกได้เล็กน้อย`}</small></span>
      </button>`).join('');
  // 2. Which provinces would feel them
  const groups = new Map();
  (f ? f.provinces : []).forEach(p => {
    if(!groups.has(p.felt_th)) groups.set(p.felt_th, []);
    groups.get(p.felt_th).push(p.province);
  });
  const felt = !f ? '' : !groups.size ? `<p>${days} วันที่ผ่านมา ไม่มีแผ่นดินไหวที่คนในไทยน่าจะรู้สึกได้</p>`
    : [...groups].map(([text, names]) => `<p><b>${names.map(escHtml).join(' ')}</b><small>${escHtml(text)}</small></p>`).join('')
      + `<small>จากแผ่นดินไหว ${escHtml(f.provinces[0].event)} · ประเมินจากขนาดและระยะทาง ไม่ใช่รายงานจากคนในพื้นที่</small>`;
  // 3. Tsunami
  let tsu = '';
  if(tsunami){
    const links = tsunami.official.map(o => `<a href="${o.url}" target="_blank" rel="noopener">${escHtml(o.name)}</a>`).join(' · ');
    tsu = tsunami.status === 'watch'
      ? `<div class="now-card watch"><h4>${icon('warnTri')} สึนามิ: เฝ้าระวัง</h4>
          ${tsunami.events.map(q => `<p>มีแผ่นดินไหว M${Number(q.magnitude).toFixed(1)} ใต้${escHtml(q.sea)} (${escHtml(q.place || '')}) เมื่อ ${escHtml(nowQuakeTime(q))}</p>`).join('')}
          <p>คนที่อยู่ริมทะเลให้ติดตามประกาศทางการ ถ้ารู้สึกแผ่นดินไหวแรง หรือเห็นน้ำทะเลลดลงผิดปกติ ให้ขึ้นที่สูงทันที ไม่ต้องรอประกาศ</p>
          <small>ระบบประเมินเองจากขนาดและตำแหน่ง ไม่ใช่ประกาศเตือนภัยทางการ · ${links}</small></div>`
      : `<div class="now-card good"><h4>${icon('check')} สึนามิ: ไม่มีสัญญาณ</h4>
          <p>${tsunami.window_hours} ชั่วโมงที่ผ่านมา ไม่มีแผ่นดินไหวใหญ่ใต้ทะเลรอบไทยที่อาจทำให้เกิดสึนามิ</p>
          <small>ระบบประเมินเองจากแผ่นดินไหว M${tsunami.min_magnitude} ขึ้นไป ไม่ใช่ประกาศทางการ · ${links}</small></div>`;
  }
  return `<div class="now-card"><h4>แผ่นดินไหวล่าสุดใกล้ไทย</h4>${quakes}<small>แตะเพื่อดูบนแผนที่ · ${days} วันที่ผ่านมา</small></div>
    ${f ? `<div class="now-card"><h4>ไทยรู้สึกไหม</h4>${felt}</div>` : ''}
    ${tsu}`;
}

// 4. What to do: outside #nowCards, and drawn open again after each repaint if the viewer opened it
let nowGuideOpen = false;
function nowGuideHtml(){
  return `<div class="now-card"><details${nowGuideOpen ? ' open' : ''} ontoggle="nowGuideOpen = this.open">
      <summary>ทำอย่างไรเมื่อเกิดแผ่นดินไหว</summary>
      <b>เตรียมไว้ก่อน</b>
      <ul><li>ยึดตู้ ชั้นวางของสูง และของหนักไว้กับผนัง</li><li>รู้ไว้ว่าในบ้านและที่ทำงาน ตรงไหนหลบได้ เช่น ใต้โต๊ะที่แข็งแรง</li>
        <li>เตรียมไฟฉาย น้ำดื่ม ยาประจำตัว และเบอร์โทรฉุกเฉินไว้ในที่หยิบง่าย</li></ul>
      <b>ระหว่างสั่น</b>
      <ul><li>หมอบลง หาที่กำบัง แล้วจับไว้ให้มั่น จนกว่าจะหยุดสั่น</li><li>อยู่ห่างกระจก หน้าต่าง และของที่อาจตกใส่</li>
        <li>อย่าใช้ลิฟต์ อย่าวิ่งออกจากอาคารขณะยังสั่น</li><li>ถ้าอยู่นอกอาคาร ไปที่โล่ง ห่างตึก เสาไฟ และป้ายโฆษณา</li></ul>
      <b>หลังหยุดสั่น</b>
      <ul><li>ระวังแผ่นดินไหวตามมา (อาฟเตอร์ช็อก)</li><li>ถ้าได้กลิ่นแก๊ส อย่าจุดไฟหรือเปิดสวิตช์ไฟ ให้ปิดวาล์วแล้วออกจากอาคาร</li>
        <li>ถ้าอาคารร้าว ให้ออกทางบันได แล้วรอข้างนอก</li><li>ถ้าอยู่ริมทะเลและสั่นแรง ให้ขึ้นที่สูงทันที</li></ul>
      <small>เบอร์ฉุกเฉิน: ปภ. 1784 · ตำรวจ 191 · เจ็บป่วยฉุกเฉิน 1669</small>
    </details></div>`;
}

async function refreshNowCards(){
  if(nowCardsBusy || Date.now() - nowCardsAt < NOW_CARDS_MS) return;
  nowCardsBusy = true;
  try{
    const [brief, tsunami] = await Promise.all([
      api('/api/world/brief').catch(() => null),
      api('/api/world/tsunami').catch(() => null),   // an older server has no tsunami screen: the card is left out
    ]);
    nowCardsHtml = nowCardsMarkup(brief, tsunami);
    nowCardsAt = brief && brief.ready ? Date.now() : 0;   // not ready yet: ask again on the next repaint
    const el = document.getElementById('nowCards');
    if(el) el.innerHTML = nowCardsHtml;
    if(brief && brief.updated_at) nowCardsHint = 'อัปเดต ' + new Date(brief.updated_at * 1000).toLocaleTimeString('th-TH', {hour:'2-digit', minute:'2-digit'});
    const hint = document.getElementById('nowCardsHint');
    if(hint) hint.textContent = nowCardsHint;
  }finally{
    nowCardsBusy = false;
  }
}

async function loadSituation(){
  situationData = await api('/api/situation');
  await paintSituation();
}

function situationShell(){
  return `
    <div class="view-head">
      <h2>หน้าสถานการณ์แผ่นดินไหวปัจจุบัน</h2>
    </div>
    <div class="grid grid-12">
      <div class="col-8" style="align-self:start;display:flex;flex-direction:column;gap:14px;">
      <div class="panel">
        <div class="panel-head"><h3>แผนที่สถานการณ์</h3><span class="hint" id="mapUpdatedHint">–</span></div>
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap;">
          <label for="worldQuakeRange" style="font-size:15.5px;color:var(--ink-muted);">ตำแหน่งจุดแผ่นดินไหว</label>
          <select class="field" id="worldQuakeRange" style="width:auto;padding:5px 10px;font-size:15.5px;">
            <option value="realtime">สถานการณ์ปัจจุบัน (Realtime)</option>
            <option value="90">90 วันที่ผ่านมา</option>
            <option value="7" selected>7 วันที่ผ่านมา</option>
            <option value="1">24 ชั่วโมงที่ผ่านมา (รอบวัน)</option>
          </select>
        </div>
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap;">
          <div style="position:relative;">
            <button type="button" class="loc-set-btn" id="userLocationBtn">${icon('pin')}<span>ตำแหน่งที่ตั้ง</span>${icon('chevronDown', 'loc-set-chevron')}</button>
            <div class="loc-popover" id="userLocationPopover" hidden>
              <div class="loc-popover-title">ตั้งตำแหน่งของคุณบนแผนที่</div>
              <button type="button" class="btn" id="useGpsBtn">${icon('target')} ใช้ตำแหน่งจาก GPS อุปกรณ์</button>
              <div class="loc-popover-divider">หรือกรอกพิกัดเอง</div>
              <div class="loc-popover-manual">
                <input type="number" id="manualLat" placeholder="ละติจูด เช่น 13.815158" step="0.000001">
                <input type="number" id="manualLng" placeholder="ลองจิจูด เช่น 100.523556" step="0.000001">
                <button type="button" class="btn" id="saveManualLocBtn">ใช้พิกัดนี้</button>
              </div>
              <div class="loc-popover-status" id="userLocationStatus"></div>
              <button type="button" class="loc-popover-clear" id="clearLocBtn" hidden>ล้างค่า กลับไปใช้ตำแหน่งอ้างอิงเดิม</button>
            </div>
          </div>
          <select class="topbar-chip" id="topSimulateScenario" style="cursor:pointer;"
            title="เลือกสถานการณ์จำลอง">
            <option value="current_real" selected>0. สถานการณ์ปัจจุบัน</option>
            <option value="myanmar_2025">1. M8.2 เมียนมา 28 มี.ค. 2568</option>
            <option value="andaman_l6">2. อันดามัน (6.255467, 95.412450) ทดสอบระดับ 6</option>
            <option value="mae_lao_2014">3. M6.3 แม่ลาว จ.เชียงราย 5 พ.ค. 2557</option>
          </select>
          <select class="topbar-chip" id="topSimulateSpeed" style="cursor:pointer;"
            title="ความเร็วคลื่น — เลือกความเร็วจริงเพื่อดูเวลานับถอยหลังตามจริง หรือเร่งเวลาเพื่อทดสอบระบบเร็วขึ้น">
            <option value="1" selected>ความเร็วจริง</option>
            <option value="2">เร่ง 2x</option>
            <option value="4">เร่ง 4x</option>
            <option value="8">เร่ง 8x</option>
            <option value="12">เร่ง 12x</option>
            <option value="20">เร่ง 20x</option>
            <option value="50">เร่ง 50x</option>
            <option value="80">เร่ง 80x</option>
            <option value="100">เร่ง 100x</option>
          </select>
          <button class="btn sim-idle" id="topSimulateBtn" data-requires-write disabled
            title="จำลองแผ่นดินไหวตามสถานการณ์ที่เลือกด้านซ้าย ผ่านไปป์ไลน์ตรวจจับจริงทั้งหมด — สถานการณ์ที่ 1 คือเหตุการณ์จริง M8.2 เมียนมา 28 มี.ค. 2568 (ตัวเลขที่รายงานกันทั่วไปคือ M7.7-7.9) ที่รอยเลื่อนสะกาย ส่วนสถานการณ์ที่ 2 คือจุดในทะเลอันดามันที่แก้สมการหาขนาดที่ให้ระดับ 6 ที่ตำแหน่งอ้างอิง — แต่ที่ระยะทางจริง ~1,000 กม. แม้ขนาดใหญ่ที่สุดเท่าที่เคยบันทึกได้ (M9.5) ก็ยังไปถึงเพียงระดับ 5 เท่านั้น ระบบจะแสดงระดับจริงตามฟิสิกส์ ไม่ปลอมระดับ 6">${icon('warnTri')} <span id="topSimulateBtnLabel">จำลองแผ่นดินไหว</span></button>
        </div>
        <div class="map-wrap">
          <div id="mapEl"></div>
          <div id="activeEventCard" class="active-event-card" hidden></div>
          <div id="realQuakeTicker" class="quake-ticker" hidden></div>
          <button type="button" class="legend-toggle" id="mapLegendToggle">คำอธิบายสัญลักษณ์</button>
          <div class="map-legend-bar" id="mapLegend">
            <div class="legend-item"><span class="legend-swatch" style="background:var(--status-critical);border-radius:50%;"></span>ศูนย์กลางแผ่นดินไหว (จำลอง)</div>
            <div class="legend-item"><span class="legend-swatch ring dashed" style="border-color:#63a4ee;"></span>คลื่น P (เดินทางมาถึงอันดับแรก)</div>
            <div class="legend-item"><span class="legend-swatch ring" style="border-color:#d03b3b;"></span>คลื่น S (แรงทำลายล้างสูงกว่ามาก)</div>
            <div class="legend-item"><span class="legend-swatch" style="background:#5fe05f;border-radius:50%;"></span>สถานี ENVIRO (ออนไลน์)</div>
            <div class="legend-item"><span class="legend-swatch" style="background:#63a4ee;border-radius:50%;"></span>สถานี ENVIRO (ออฟไลน์)</div>
            <div class="legend-item"><span class="legend-swatch line" style="background:var(--status-warn);"></span>รอยเลื่อนไทย (ตำแหน่งจริง)</div>
            <div class="legend-item"><span class="legend-swatch line" style="background:#9085e9;"></span>รอยเลื่อนทั่วโลก (ข้อมูลจริง)</div>
            <div class="legend-item"><span class="legend-swatch" style="background:#ec835a;border-radius:50%;"></span>แผ่นดินไหวจริงทั่วโลก/ภูมิภาค (USGS·EMSC·GEOFON·TMD — ขนาดวงกลม = ความรุนแรง, TMD ขอบหนา)</div>
            <div class="legend-item"><span class="legend-swatch quake-marker-recent" style="background:#ec835a;border-radius:50%;"></span>กำลัง active / เพิ่งเกิด (กระพริบ)</div>
            <div class="legend-item"><svg width="11" height="15" viewBox="0 0 22 30" xmlns="http://www.w3.org/2000/svg" style="flex:none;"><path d="M11 0C4.9 0 0 4.9 0 11c0 8.3 11 19 11 19s11-10.7 11-19C22 4.9 17.1 0 11 0Z" fill="#fff" stroke="#0a0d12" stroke-width="1.5"/><circle cx="11" cy="11" r="4" fill="var(--status-watch)"/></svg>ตำแหน่งของคุณ (สีจุดกลางเปลี่ยนตามระดับความรุนแรง ณ จุดนั้น)</div>
          </div>
        </div>
        <p class="panel-sub" hidden>พื้นแผนที่จาก OpenStreetMap/Esri จริง 100% (สลับภาพถ่ายดาวเทียมได้) · <span id="worldFaultHint">กำลังโหลดรอยเลื่อนทั่วโลก…</span> · <span id="worldQuakeHint">กำลังโหลดแผ่นดินไหวทั่วโลก…</span></p>
        <p class="panel-sub" id="worldQuakeHistoryHint" hidden>–</p>
      </div>
      <div class="panel" id="locationGuidancePanel"></div>
      </div>
      <div class="panel col-4" id="eventDetailPanel"></div>
      <div class="panel col-12">
        <div class="panel-head"><h3>เวลาที่คลื่นมาถึงและผลกระทบตามเมือง</h3><span class="hint" id="citiesHint">–</span></div>
        <div class="scroll-x">
          <table class="data-table">
            <thead><tr><th>เมือง</th><th>ระยะห่างจากศูนย์กลาง</th><th>คลื่น P มาถึงใน</th><th>คลื่น S มาถึงใน</th><th>ความรุนแรงที่คาดการณ์ (MMI)</th></tr></thead>
            <tbody id="citiesTbody"></tbody>
          </table>
        </div>
      </div>
      <div class="grid grid-4 col-12" id="systemStatusRow"></div>
    </div>`;
}

// "สถานการณ์ปัจจุบัน" (current_real) means real-data-only by explicit
// design -- ENVIRO's own active_event pipeline (organic background noise
// the simulator generates on its own, or a manually triggered demo
// scenario) is never real external data, so surfacing it while this mode
// is selected would misleadingly look like a genuine quake is happening.
// Used to suppress that pipeline's display everywhere it appears (this
// panel, the topbar level pill, WS-triggered sound/toasts) without
// touching situationData or the backend/simulator itself.
function isRealDataOnlyMode(){
  // Whether to show ENVIRO's own simulated pipeline is governed SOLELY by
  // whether THIS browser tab has actually pressed "จำลองแผ่นดินไหว" and not
  // yet stopped it (manualSimulateStarted) -- per explicit request, merely
  // picking a scenario in the dropdown (arming it) must have zero visible
  // effect until the button itself is pressed. This deliberately does NOT
  // look at data.event/!!ev or any WS push: the events table is shared
  // across every server process pointed at the same data/enviro.db, and the
  // simulator's own background STA/LTA loop can independently declare a
  // low-level ambient "detection" with no admin action at all -- either one
  // could otherwise leak a real-looking simulation through on a fresh page
  // load or a mere dropdown change, which is exactly the bug this fixes.
  // Defaults to true (masked) before any button press, matching the
  // required "home page is always สถานการณ์ปัจจุบัน" behavior.
  return !manualSimulateStarted;
}

async function paintSituation(){
  let data = situationData;
  if(isRealDataOnlyMode() && data.event){
    data = {
      ...data, event: null,
      cities: data.cities.map(c => ({
        ...c, mmi_label: 'ไม่มีเหตุการณ์ปัจจุบัน',
        p_remaining_sec: null, s_remaining_sec: null, p_arrived: false, s_arrived: false,
      })),
    };
  }
  const ev = data.event;
  await getLevelBands();
  // Same "you" point the map pin/ripple/arrival-sound already use (see
  // resolveYouLocation) -- returns null when the viewer hasn't set a real
  // position (GPS or manual coordinates). locationSet gates every "at your
  // position" display below: per explicit request, none of them may fall
  // back to the server's own fixed-reference-station numbers and present
  // them as if they were the viewer's own.
  const you = resolveYouLocation(data);
  const locationSet = !!you;
  // Recompute MMI/level at the viewer's actual pin (see
  // computeYouLevelForEvent) -- only attempted when a real location is set;
  // evForGuidance stays null otherwise, and every renderer below must show
  // an explicit "set your location" prompt in that case, not silently
  // substitute ev's own (reference-station) level/MMI.
  const evForGuidance = locationSet ? getEvForGuidance(ev) : null;

  // The wave-arrival origin is the event when one exists, else the same
  // pending-quake placeholder the server used to compute data.cities[].dist_km,
  // so youDistKm stays comparable to those.
  const waveOrigin = ev ? {lat: ev.lat, lng: ev.lng} : (data.pending_quake ? {lat: data.pending_quake.lat, lng: data.pending_quake.lng} : null);
  const youDistKm = (you && waveOrigin) ? haversineKm(waveOrigin.lat, waveOrigin.lng, you.lat, you.lng) : null;
  function computeYouWave(){
    if(!ev || youDistKm == null) return {p_remaining_sec: null, s_remaining_sec: null, p_arrived: false, s_arrived: false};
    const elapsedSec = Math.max(0, (Date.now() - new Date(ev.ts).getTime()) / 1000);
    const p_remaining_sec = Math.max(0, youDistKm / data.vp_km_s - elapsedSec);
    const s_remaining_sec = Math.max(0, youDistKm / data.vs_km_s - elapsedSec);
    return {p_remaining_sec, s_remaining_sec, p_arrived: p_remaining_sec <= 0, s_arrived: s_remaining_sec <= 0};
  }
  const youWave = computeYouWave();
  // A table row counts as "you are here" only if its server-computed dist_km
  // (measured from the same waveOrigin) matches youDistKm -- reusing dist_km
  // instead of needing each city's lat/lng client-side.
  const youCityBadge = c => (youDistKm != null && Math.abs(c.dist_km - youDistKm) < 1)
    ? ' <span class="badge info">คุณอยู่ที่นี่</span>' : '';

  // Build the shell once. Rebuilding it on every 15s refresh would tear down
  // and recreate the Leaflet map (losing the ~2MB world-faults layer + user's
  // pan/zoom) -- so only the pieces that actually change get patched below.
  if(!document.getElementById('mapEl')){
    document.getElementById('view-situation').innerHTML = situationShell();
    document.getElementById('worldQuakeRange').addEventListener('change', refreshWorldQuakes);
    wireUserLocationControls();
    // Named + de-duplicated: this "build shell once" block has, in
    // practice, run more than once per page load (view-situation's DOM gets
    // rebuilt on some navigation paths even though #mapEl re-appearing is
    // meant to prevent that) -- with a bare anonymous listener that silently
    // bound a second, third, ... copy each time, so ONE click on the toggle
    // fired stopSimulatedQuake()/triggerRandomQuake() (and its POST) once
    // per accumulated copy instead of once. removeEventListener here is a
    // no-op the very first time and a real deduplication every time after.
    document.getElementById('topSimulateBtn').removeEventListener('click', handleSimulateBtnClick);
    document.getElementById('topSimulateBtn').addEventListener('click', handleSimulateBtnClick);
    // Re-render immediately on toggling in/out of "สถานการณ์ปัจจุบัน" --
    // otherwise the suppressed/restored event display would lag behind by up
    // to one periodic tick, which reads as the dropdown not having done
    // anything yet.
    document.getElementById('topSimulateScenario').addEventListener('change', ()=>{
      updateTopbar();
      if(!document.getElementById('view-situation').hidden) paintSituation();
    });
    // Speed doesn't affect anything else on repaint, but the simulate
    // button's enabled/disabled state (see simulateGateOk) depends on it
    // having a real selection too, so re-sync just that on change.
    document.getElementById('topSimulateSpeed').addEventListener('change', ()=>{
      syncSimulateButtonUI(simulateActive);
    });
    // topSimulateBtn carries data-requires-write, same as the admin view's
    // write-gated buttons -- but it didn't exist yet when showApp() first
    // called this at login (it's created here, lazily), so it needs its own
    // pass now to actually get disabled for a read-only role.
    applyRolePermissions();
  }

  document.getElementById('mapUpdatedHint').textContent =
    ev ? 'อัปเดตล่าสุด ' + new Date(ev.ts).toLocaleString('th-TH') : 'ยังไม่พบเหตุการณ์ — ระบบกำลังเฝ้าระวัง';
  document.getElementById('citiesHint').textContent =
    `คำนวณจาก Vp ≈ ${data.vp_km_s} กม./วิ, Vs ≈ ${data.vs_km_s} กม./วิ (ค่าประมาณเปลือกโลก${data.speed_multiplier>1?' × เร่งเวลา '+data.speed_multiplier+'x เพื่อการสาธิต':''}) — คำนวณฝั่งเซิร์ฟเวอร์`;

  // renderLevelGuidance(ev) is called below, right after eventDetailPanel's
  // innerHTML is (re)written -- #levelGuidancePanel now lives nested inside
  // it (moved there per request, replacing the old always-visible MMI
  // explanation paragraph, which is now a collapsible button instead), so
  // calling it any earlier would find nothing yet on the very first render.

  // Arrival sound is triggered by startRipple() the instant the animated red
  // S-wave circle's radius covers the map pin (see haversineKm/ripplePinDistKm
  // above) -- frame-accurate to what's on screen, not this countdown text.
  renderLocationGuidance(evForGuidance, ev);
  const impactLv = (ev && evForGuidance) ? evForGuidance.level : 0;
  const [ringBg, ringFg] = (ev && evForGuidance) ? levelPillStyle(impactLv)
    : (ev ? ['var(--status-info-soft)', 'var(--status-info)'] : ['var(--surface-2)', 'var(--ink-muted)']);
  const tsunamiBanner = ev && ev.tsunami_risk ? `
    <div class="callout extreme" style="margin-top:2px;">
      ${icon('warnTri')}
      <div><b>⚠ เฝ้าระวังสึนามิ (เบื้องต้น)</b> — ศูนย์กลางอยู่ในทะเลตื้นบริเวณอันดามัน และมีขนาดใหญ่พอที่จะก่อคลื่นสึนามิได้ หากอยู่ในพื้นที่ชายฝั่ง ให้อพยพขึ้นที่สูงหรือเข้าแผ่นดินทันทีหลังแรงสั่นหยุด อย่ารอประกาศเพิ่มเติม (นี่เป็นการประเมินอย่างง่ายของระบบ ไม่ใช่ประกาศเตือนภัยทางการ — ให้ยึดตามประกาศจาก ปภ./กรมอุตุนิยมวิทยาเป็นหลัก)</div>
    </div>` : '';

  document.getElementById('eventDetailPanel').innerHTML = `
    ${ev ? `<div class="panel-head"><h3>วิเคราะห์ผลกระทบด้วย Edge AI</h3><span class="badge info">AI Analysis</span></div>`
         : `<div class="panel-head"><h3>แผ่นดินไหวตอนนี้</h3><span class="hint" id="nowCardsHint">${nowCardsHint}</span></div>`}
    ${ev && data.speed_multiplier > 1 ? `<div class="badge warn" style="align-self:flex-start;">${icon('warnTri')} โหมดสาธิตเร่งเวลา ${data.speed_multiplier}x (ไม่ใช่ความเร็วคลื่นจริง)</div>` : ''}
    ${ev ? `
    ${tsunamiBanner}
    <div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap;">
      <div class="impact-ring" style="--ring-bg:${ringBg};--ring-fg:${ringFg};">${evForGuidance ? impactLv : '?'}</div>
      <div>
        <div style="font-size:13.5px;color:var(--ink-muted);text-transform:uppercase;letter-spacing:.04em;">ความรุนแรงที่คาด ณ ตำแหน่งคุณ</div>
        ${evForGuidance ? `
        <div style="font-size:22px;font-weight:600;color:${ringFg};">MMI ${evForGuidance.predicted_mmi_roman} · ระดับแจ้งเตือน ${evForGuidance.level}</div>
        <div style="font-size:15px;color:var(--ink-secondary);">${IMPACT_LABELS[impactLv]}</div>
        ` : `
        <div style="font-size:16px;font-weight:600;color:${ringFg};">ยังไม่ได้ตั้งค่าตำแหน่งของคุณ</div>
        <div style="font-size:14px;color:var(--ink-secondary);">กดปุ่ม "ตำแหน่งที่ตั้ง" บนแผนที่ (GPS หรือกรอกพิกัดเอง) เพื่อดูความรุนแรงที่ตำแหน่งจริงของคุณ</div>
        `}
      </div>
      <div style="margin-left:auto;text-align:right;">
        <div style="font-size:13.5px;color:var(--ink-muted);text-transform:uppercase;letter-spacing:.04em;">ขนาดเหตุการณ์ (Mw)</div>
        <div class="tabular" style="font-size:25px;font-weight:700;font-family:var(--font-display);">M${ev.magnitude_estimate ?? ev.magnitude}</div>
        <span class="badge ${ev.confidence_tier>=4?'good':ev.confidence_tier>=3?'watch':'neutral'}">ความเชื่อมั่น AI ${ev.confidence_label} · ยืนยันแล้ว ${ev.stations_triggered} สถานี</span>
        ${ev.external_match ? `<div style="margin-top:6px;"><span class="badge good" title="${ev.external_match.place || ''}${ev.external_match.magnitude!=null?' · M'+ev.external_match.magnitude:''}">${icon('check')} ยืนยันจาก ${ev.external_match.source} (~${ev.external_match.dist_km} กม.)</span></div>` : ''}
      </div>
    </div>
    <div id="levelGuidancePanel" style="margin-top:2px;"></div>
    ${locationSet ? `
    <div class="callout wave-countdown-callout ${youWave.p_arrived ? 'wave-p-passed' : 'wave-p-coming'}" style="margin-top:2px;" hidden>
      ${icon('warnTri')}
      <div>คลื่น S จะมาถึงตำแหน่งของคุณโดยประมาณใน <b class="tabular" id="userCountdown">${youWave.s_arrived ? 'มาถึงแล้ว' : fmtTime(youWave.s_remaining_sec)}</b> นาที:วินาที</div>
    </div>
    ` : `
    <div class="callout" style="margin-top:2px;border-color:var(--status-info);background:var(--status-info-soft);">
      ${icon('pin')}
      <div>ยังไม่ทราบเวลาที่คลื่นจะมาถึงตำแหน่งของคุณ เพราะยังไม่ได้ตั้งค่าตำแหน่ง — กดปุ่ม "ตำแหน่งที่ตั้ง" บนแผนที่เพื่อดู</div>
    </div>
    `}
    <table class="data-table kv-stack">
      <tr><td>รหัสเหตุการณ์</td><td class="strong tabular">${ev.id}</td></tr>
      <tr><td>ตำแหน่งศูนย์กลาง</td><td class="strong">${ev.place}</td></tr>
      <tr><td>ความลึก</td><td class="strong tabular">${ev.depth} กม.</td></tr>
      <tr><td>ความรุนแรงที่ศูนย์กลาง (MMI)</td><td class="strong tabular">${ev.mmi_epicenter}</td></tr>
      <tr><td>PGA ที่สถานีใกล้ที่สุด</td><td class="strong tabular">${ev.pga_gal} Gal</td></tr>
    </table>
    <div class="mmi-explain">
      <button type="button" class="mmi-explain-btn" id="mmiExplainToggle">${icon('info')}<span>ทำไมความรุนแรงถึงต่างกันในแต่ละพื้นที่?</span></button>
      <p class="panel-sub mmi-explain-body" hidden>ระดับจัดตาม<b>ความรุนแรงที่คาดการณ์ ณ ตำแหน่งอ้างอิง (Predicted MMI)</b> ไม่ใช่ขนาดแผ่นดินไหว (Magnitude) โดยตรง — เหตุการณ์เดียวกันให้ความรุนแรงต่างกันในแต่ละพื้นที่ตามระยะทาง ความลึก และสภาพพื้นที่ (อ้างอิงแนวทาง USGS: Magnitude vs. Intensity) ส่วนจำนวนสถานียืนยันร่วมมีผลต่อ "ความเชื่อมั่น" เท่านั้น ทั้งขนาดและ MMI คำนวณจริงฝั่งเซิร์ฟเวอร์จากระยะทางจริงถึงศูนย์กลาง ไม่ใช่ค่าคงที่</p>
    </div>
    ` : `<div class="now-cards"><div id="nowCards" class="now-cards">${nowCardsHtml}</div>${nowGuideHtml()}</div>`}`;
  renderLevelGuidance(evForGuidance, ev);
  if(!ev) refreshNowCards();

  const regionsForStatus = await api('/api/stations/regions').catch(()=>[]);
  const totalSt = regionsForStatus.reduce((s,r)=>s+r.total,0) || 1;
  const onlineSt = regionsForStatus.reduce((s,r)=>s+r.online,0);
  const detectorAlive = lastTickAt && (Date.now() - lastTickAt < 3000);
  const respMs = lastTickAt ? Math.max(0, Date.now() - lastTickAt) : null;
  document.getElementById('systemStatusRow').innerHTML = `
    <div class="stat-tile"><span class="label">ระบบตรวจจับ</span><span class="value" style="font-size:23px;color:${detectorAlive?'var(--status-good)':'var(--status-critical)'};">${detectorAlive?'ปกติ':'ตรวจสอบ'}</span></div>
    <div class="stat-tile"><span class="label">เซนเซอร์ออนไลน์</span><span class="value tabular" style="font-size:23px;">${onlineSt.toLocaleString()}<small>/${totalSt.toLocaleString()}</small></span></div>
    <div class="stat-tile"><span class="label">เครือข่ายเสถียร</span><span class="value tabular" style="font-size:23px;">${((onlineSt/totalSt)*100).toFixed(1)}<small>%</small></span></div>
    <div class="stat-tile"><span class="label">เวลาตอบสนองล่าสุด</span><span class="value tabular" style="font-size:23px;">${respMs!=null? respMs : '–'}<small>ms</small></span></div>`;

  document.getElementById('citiesTbody').innerHTML = data.cities.map(c=>`<tr>
      <td class="strong">${c.name}${youCityBadge(c)}</td>
      <td class="tabular">${c.dist_km.toLocaleString()} กม.</td>
      <td class="tabular" data-p-city="${c.name}">${c.p_arrived? 'มาถึงแล้ว': fmtTime(c.p_remaining_sec)}</td>
      <td class="tabular" data-s-city="${c.name}">${c.s_arrived? 'มาถึงแล้ว': fmtTime(c.s_remaining_sec)}</td>
      <td>${c.mmi_label}</td>
    </tr>`).join('');

  paintMap(data);
  syncSimulateButtonUI(manualSimulateStarted || !!ev);

  // The countdown callout starts out `hidden` in the template above -- it is
  // revealed only by startRipple()'s own animation-frame loop
  // (revealWaveCountdownIfVisible), once the P-wave circle has actually
  // grown to a visible radius on the map, not merely the instant
  // startRipple() is called (radius could still be ~0m then). See
  // startRipple() above for why this can't just be checked once here.

  clearInterval(situationTimer);
  if(ev){
    // Recompute p/s_remaining_sec fresh from real elapsed wall-clock time
    // every tick (mirroring startRipple()'s own method exactly) instead of
    // decrementing by 1 per 1000ms tick -- a naive decrement drifts from the
    // visual P/S wave-front circles under any timer imprecision (background
    // tab throttling, a busy event loop), especially at high
    // speed_multiplier, which is exactly the "countdown says minutes left
    // but the red S-wave circle already covers the pin" bug this fixes.
    const startMs = new Date(ev.ts).getTime();
    const vpEff = data.vp_km_s, vsEff = data.vs_km_s;
    const uEl = document.getElementById('userCountdown');
    const waveCalloutEl = uEl ? uEl.closest('.callout') : null;
    situationTimer = setInterval(()=>{
      const elapsedSec = Math.max(0, (Date.now() - startMs) / 1000);
      data.cities.forEach(c=>{
        c.p_remaining_sec = Math.max(0, c.dist_km / vpEff - elapsedSec);
        c.s_remaining_sec = Math.max(0, c.dist_km / vsEff - elapsedSec);
        c.p_arrived = c.p_remaining_sec <= 0;
        c.s_arrived = c.s_remaining_sec <= 0;
        const pEl = document.querySelector(`[data-p-city="${c.name}"]`);
        const sEl = document.querySelector(`[data-s-city="${c.name}"]`);
        if(pEl) pEl.textContent = c.p_arrived ? 'มาถึงแล้ว' : fmtTime(c.p_remaining_sec);
        if(sEl) sEl.textContent = c.s_arrived ? 'มาถึงแล้ว' : fmtTime(c.s_remaining_sec);
      });
      // The countdown callout tracks the actual pin (youDistKm, captured
      // above from resolveYouLocation) -- not a fixed city row -- so it
      // reaches "มาถึงแล้ว" at the exact moment the real distance from the
      // origin to THAT pin has been covered, wherever the pin is. Blue
      // blink while P is still inbound to the pin, red blink once P has
      // passed it (see .wave-p-coming/.wave-p-passed).
      if(uEl && youDistKm != null){
        const pRemain = Math.max(0, youDistKm / vpEff - elapsedSec);
        const sRemain = Math.max(0, youDistKm / vsEff - elapsedSec);
        const pArrived = pRemain <= 0, sArrived = sRemain <= 0;
        uEl.textContent = sArrived ? 'มาถึงแล้ว' : fmtTime(sRemain);
        if(waveCalloutEl){
          waveCalloutEl.classList.toggle('wave-p-passed', pArrived);
          waveCalloutEl.classList.toggle('wave-p-coming', !pArrived);
        }
      }
    }, 1000);
  }
}

async function renderSituation(){
  await loadSituation();
  clearInterval(situationRefreshTimer);
  situationRefreshTimer = setInterval(loadSituation, 15000);
}

