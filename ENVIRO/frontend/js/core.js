// Icons, the API client and login, chart helpers. A classic script (not a module): every js/ file shares one global scope and index.html loads them in order.

/* ============================= ICONS ============================= */
const ICONS = {
  map:'<path d="M9 4 3 6.5v13L9 17l6 2.5 6-2.5v-13L15 6.5 9 4Z"/><path d="M9 4v13"/><path d="M15 6.5V19.5"/>',
  bell:'<path d="M6 9a6 6 0 1 1 12 0c0 4 1.5 5.5 2 6.5H4c.5-1 2-2.5 2-6.5Z"/><path d="M10 19.5a2 2 0 0 0 4 0"/>',
  sensor:'<circle cx="12" cy="12" r="2.2"/><path d="M8.2 8.2a5.4 5.4 0 0 0 0 7.6"/><path d="M15.8 8.2a5.4 5.4 0 0 1 0 7.6"/><path d="M5.3 5.3a9.8 9.8 0 0 0 0 13.4"/><path d="M18.7 5.3a9.8 9.8 0 0 1 0 13.4"/>',
  wave:'<path d="M2 12h3l2-7 3 14 3-11 2 4h7" fill="none"/>',
  layers:'<path d="M12 3 3 8l9 5 9-5-9-5Z"/><path d="M3 13l9 5 9-5"/><path d="M3 17.5l9 5 9-5"/>',
  shield:'<path d="M12 3 5 5.5v6c0 5 3 8 7 9.5 4-1.5 7-4.5 7-9.5v-6L12 3Z"/><path d="m9 12 2 2 4-4"/>',
  check:'<path d="m5 12 4.5 4.5L19 7"/>',
  warnTri:'<path d="M12 4 2 20h20L12 4Z"/><path d="M12 10.5v4.2"/><path d="M12 17.6h.01"/>',
  chevronDown:'<path d="M6 9l6 6 6-6"/>',
  grip:'<path d="M12 3v18"/><path d="M5 8h14"/><path d="M5 16h14"/>',
  noEntry:'<circle cx="12" cy="12" r="9"/><path d="M6.5 6.5 17.5 17.5"/>',
  clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7.5v5l3.2 1.9"/>',
  info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5"/><path d="M12 7.6h.01"/>',
  pin:'<path d="M12 21s7-7.6 7-12.4A7 7 0 0 0 5 8.6C5 13.4 12 21 12 21Z"/><circle cx="12" cy="8.6" r="2.4"/>',
  refresh:'<path d="M4 12a8 8 0 0 1 13.66-5.66L20 8.5"/><path d="M20 4v4.5h-4.5"/><path d="M20 12a8 8 0 0 1-13.66 5.66L4 15.5"/><path d="M4 20v-4.5h4.5"/>',
  target:'<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="2.4"/><path d="M12 2.5v3"/><path d="M12 18.5v3"/><path d="M2.5 12h3"/><path d="M18.5 12h3"/>',
  flame:'<path d="M12 2s5 5 5 10a5 5 0 0 1-10 0c0-2 1-3 1-3s.5 2 2 2c1 0 1-1.5 0-3-1.5-2-1-4 2-6Z"/>',
  elevator:'<rect x="5" y="3" width="14" height="18" rx="1.5"/><path d="M10 8l2-2 2 2"/><path d="M10 14l2 2 2-2"/>',
  globe:'<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3Z"/>',
};
function icon(name, cls=''){return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" class="${cls}">${ICONS[name]}</svg>`;}

/* ============================= AUTH + API ============================= */
// Path this page is served under: '' at http://localhost:5050/, '/enviro' on the public site, where
// Tailscale Funnel mounts ENVIRO at /enviro next to BKK StreetSmart. Every API and WebSocket URL starts with it.
const BASE = location.pathname.replace(/\/(index\.html)?$/, '');
let AUTH = JSON.parse(localStorage.getItem('enviro_auth') || 'null');
// Without a login the dashboard opens read-only as this guest (the server treats a request with no
// token the same way); "เข้าสู่ระบบ" in the rail opens the login form for staff.
const GUEST = {username:'guest', role:'guest', display_name:'ผู้เยี่ยมชม'};

function saveAuth(a){ AUTH = a; localStorage.setItem('enviro_auth', JSON.stringify(a)); }
function clearAuth(){ AUTH = null; localStorage.removeItem('enviro_auth'); }

async function api(path, opts={}){
  const headers = Object.assign({'Content-Type':'application/json'}, opts.headers||{});
  if(AUTH && AUTH.token) headers['Authorization'] = 'Bearer ' + AUTH.token;
  const res = await fetch(BASE + path, Object.assign({}, opts, {headers}));
  if(res.status === 401){ clearAuth(); location.reload(); throw new Error('unauthorized'); }   // stale token: start over as guest
  if(!res.ok){ const body = await res.json().catch(()=>({})); throw new Error(body.message || body.error || res.statusText); }
  return res.status === 204 ? null : res.json();
}

function showLogin(){
  document.getElementById('loginMask').hidden = false;
  document.getElementById('app').hidden = true;
}
function showApp(){
  document.getElementById('loginMask').hidden = true;
  document.getElementById('app').hidden = false;
  document.getElementById('railUser').innerHTML = `<b>${AUTH.display_name}</b>${AUTH.role}`;
  document.getElementById('logoutBtn').textContent = AUTH.token ? 'ออกจากระบบ' : 'เข้าสู่ระบบ';
  applyRolePermissions();
}

document.getElementById('loginCancel').addEventListener('click', ()=>{
  document.getElementById('loginMask').hidden = true;
  document.getElementById('app').hidden = false;
});

document.getElementById('loginForm').addEventListener('submit', async (e)=>{
  e.preventDefault();
  const username = document.getElementById('loginUser').value.trim();
  const password = document.getElementById('loginPass').value;
  const errEl = document.getElementById('loginError');
  errEl.textContent = '';
  try{
    const res = await fetch(BASE + '/api/auth/login', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({username,password})});
    const body = await res.json();
    if(!res.ok){ errEl.textContent = body.message || 'เข้าสู่ระบบไม่สำเร็จ'; return; }
    saveAuth(body);
    location.reload();   // the guest dashboard is already running: reload it with the staff account
  }catch(err){ errEl.textContent = 'เชื่อมต่อเซิร์ฟเวอร์ไม่ได้'; }
});

document.getElementById('logoutBtn').addEventListener('click', async ()=>{
  if(!AUTH.token){ showLogin(); return; }
  try{ await api('/api/auth/logout', {method:'POST'}); }catch(e){}
  clearAuth();
  location.reload();
});

function applyRolePermissions(){
  const canWrite = AUTH && (AUTH.role === 'admin' || AUTH.role === 'operator');
  document.querySelectorAll('[data-requires-write]').forEach(el=>{
    // Preserve whatever informative tooltip the element already has (set once,
    // in `data-title`) instead of clobbering it -- only swap in the read-only
    // notice when the user actually lacks write access.
    if(el.dataset.title === undefined) el.dataset.title = el.title;
    el.disabled = !canWrite;
    el.title = canWrite ? el.dataset.title : 'สิทธิ์ของคุณเป็นแบบอ่านอย่างเดียว';
  });
  document.querySelectorAll('[data-requires-admin]').forEach(el=>{
    el.disabled = !(AUTH && AUTH.role === 'admin');
  });
}

/* ============================= CHART HELPERS ============================= */
function pathFromSeries(values, w, h, domain){
  if(!values || !values.length) return '';
  const [lo,hi] = domain || [Math.min(...values), Math.max(...values)];
  const range = (hi-lo)||1;
  const step = w/(Math.max(1,values.length-1));
  return values.map((v,i)=>{
    const x=i*step, y = h - ((v-lo)/range)*h;
    return `${i===0?'M':'L'}${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(' ');
}
// Like pathFromSeries, but a `null` entry breaks the line instead of plotting
// through it as 0 -- for sparse per-source series where most indices have no
// reading at all (see the accuracy-series chart on the Compare page).
function sparsePathFromSeries(values, w, h, domain){
  if(!values || !values.length) return '';
  const [lo,hi] = domain;
  const range = (hi-lo)||1;
  const step = w/(Math.max(1,values.length-1));
  let d = '', drawing = false;
  values.forEach((v,i)=>{
    if(v == null){ drawing = false; return; }
    const x=i*step, y = h - ((v-lo)/range)*h;
    d += (drawing?'L':'M') + x.toFixed(2) + ',' + y.toFixed(2) + ' ';
    drawing = true;
  });
  return d.trim();
}
function waveSvg(values, color, h, label, rightLabel){
  h = h || 90;
  const W = 600;
  const d = pathFromSeries(values, W, h-4, [-1.3,1.3]);
  return `
  <svg class="chart" viewBox="0 0 ${W} ${h+16}" preserveAspectRatio="none" style="width:100%;height:${h+16}px;display:block;">
    <line class="grid-line" x1="0" y1="${h/2}" x2="${W}" y2="${h/2}" stroke-width="1"/>
    <path d="${d}" fill="none" stroke="${color}" stroke-width="1.6" stroke-linejoin="round" transform="translate(0,2)"/>
    <text x="4" y="${h+13}" font-size="9">${label}</text>
    <text x="${W-4}" y="${h+13}" font-size="9" text-anchor="end">${rightLabel||''}</text>
  </svg>`;
}
function hexLerp(a,b,t){
  const pa=[1,3,5].map(i=>parseInt(a.substr(i,2),16));
  const pb=[1,3,5].map(i=>parseInt(b.substr(i,2),16));
  const c=pa.map((v,i)=>Math.round(v+(pb[i]-v)*t));
  return '#'+c.map(v=>v.toString(16).padStart(2,'0')).join('');
}
function seqColor(t){ return hexLerp('#141b26','#63a4ee', Math.max(0,Math.min(1,t))); }
function fmtTime(sec){
  if(sec===null || sec===undefined) return '—';
  sec = Math.max(0, Math.round(sec));
  const m = Math.floor(sec/60), s = sec%60;
  return `${m}:${String(s).padStart(2,'0')}`;
}

const tipEl = document.getElementById('tip');
document.addEventListener('mousemove', e=>{
  if(!tipEl.classList.contains('show')) return;
  tipEl.style.left = Math.min(window.innerWidth-250, e.clientX+14)+'px';
  tipEl.style.top = Math.max(8, e.clientY-38)+'px';
});
document.addEventListener('mouseover', e=>{
  const t = e.target.closest('[data-tip]');
  if(!t) return;
  tipEl.innerHTML = t.getAttribute('data-tip');
  tipEl.classList.add('show');
});
document.addEventListener('mouseout', e=>{
  if(e.target.closest('[data-tip]')) tipEl.classList.remove('show');
});
// Delegated (not re-bound per render) since #mmiExplainToggle lives inside
// eventDetailPanel's innerHTML, which gets fully replaced on every situation
// refresh -- a directly-attached listener would be destroyed each time.
document.addEventListener('click', e=>{
  const btn = e.target.closest('#mmiExplainToggle');
  if(!btn) return;
  const body = btn.parentElement.querySelector('.mmi-explain-body');
  if(body) body.hidden = !body.hidden;
});
// Map legend show/hide -- the button only shows when embedded (.embed .legend-toggle)
document.addEventListener('click', e=>{
  const btn = e.target.closest('#mapLegendToggle');
  if(btn) btn.parentElement.classList.toggle('legend-open');
});
// Location guidance / evacuation-assessment interactions -- also delegated,
// since #locationGuidancePanel's innerHTML is fully rebuilt on every render
// (see renderLocationGuidance).
document.addEventListener('click', e=>{
  const ob = e.target.closest('.override-btn');
  if(ob){
    const key = ob.dataset.override;
    if(activeOverrides.has(key)) activeOverrides.delete(key); else activeOverrides.add(key);
    if(situationData) renderLocationGuidance(getEvForGuidance(situationData.event), situationData.event);
  }
});
document.addEventListener('change', e=>{
  if(e.target.id === 'userLocationSelect'){
    userLocationType = e.target.value;
    localStorage.setItem('enviro_loc_type', userLocationType);
    if(situationData) renderLocationGuidance(getEvForGuidance(situationData.event), situationData.event);
  }
});
function showToast(title, sub, ok=true){
  const t = document.getElementById('toast');
  t.innerHTML = `${icon(ok?'check':'warnTri')}<div><div class="tt">${title}</div><div class="ts">${sub}</div></div>`;
  t.querySelector('svg').style.color = ok ? 'var(--status-good)' : 'var(--status-critical)';
  t.classList.add('show');
  clearTimeout(window.__toastTimer);
  window.__toastTimer = setTimeout(()=>t.classList.remove('show'), 4500);
}

const LEVEL_BADGE = {1:'good',2:'info',3:'watch',4:'warn',5:'critical',6:'extreme'};
function levelPillStyle(lv){
  const map = {1:['var(--status-good-soft)','#5fe05f'],2:['var(--status-info-soft)','var(--status-info)'],
    3:['var(--status-watch-soft)','var(--status-watch)'],4:['var(--status-warn-soft)','var(--status-warn)'],
    5:['var(--status-critical-soft)','#ff8f8f'],6:['var(--status-extreme-soft)','#ffb8b8']};
  return map[lv] || ['var(--surface-2)','var(--ink-muted)'];
}

