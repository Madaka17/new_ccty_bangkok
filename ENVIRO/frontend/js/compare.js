// View 5: source comparison and quake history. A classic script (not a module): every js/ file shares one global scope and index.html loads them in order.

/* ============================= VIEW 5: SOURCE COMPARISON ============================= */
function historySourceBadge(source){
  const colors = {USGS:'var(--series-usgs)', EMSC:'var(--series-emsc)', GEOFON:'var(--series-geofon)', TMD:'var(--series-tmd)'};
  return `<span class="legend-item"><span class="legend-swatch" style="background:${colors[source]||'#888'};"></span>${source}</span>`;
}

const HISTORY_MONTH_NAMES = ['','ม.ค.','ก.พ.','มี.ค.','เม.ย.','พ.ค.','มิ.ย.','ก.ค.','ส.ค.','ก.ย.','ต.ค.','พ.ย.','ธ.ค.'];
let historyPage = 1;
let historyFilterOptions = null; // cached {years, months_by_year, regions} -- doesn't change often, no need to refetch every table load

// Populates ปี/เดือน/สถานที่ with only the values that actually have data
// behind them (see /api/compare/history/filters) -- เดือน narrows to the
// months that exist within whichever ปี is currently selected.
async function loadHistoryFilterOptions(){
  const yearSel = document.getElementById('historyYearFilter');
  const monthSel = document.getElementById('historyMonthFilter');
  const regionSel = document.getElementById('historyRegionFilter');
  if(!yearSel || !monthSel || !regionSel) return;
  try{
    if(!historyFilterOptions) historyFilterOptions = await api('/api/compare/history/filters');
  }catch(e){ return; }
  const keepYear = yearSel.value, keepRegion = regionSel.value;
  // Merge in the years a backfill can actually reach (see
  // world_quakes.BACKFILL_MAX_YEARS_BACK) even if none of them have local
  // data yet -- otherwise a year with nothing cached could never be picked
  // at all, and "ดึงข้อมูลย้อนหลัง" would have no year to fetch for.
  const nowYear = new Date().getFullYear();
  const backfillYears = [nowYear, nowYear-1, nowYear-2, nowYear-3];
  const allYears = Array.from(new Set([...historyFilterOptions.years, ...backfillYears])).sort((a,b)=>b-a);
  yearSel.innerHTML = `<option value="">ทุกปี</option>` +
    allYears.map(y=>`<option value="${y}">${y + 543}${historyFilterOptions.years.includes(y)?'':' (ยังไม่มีข้อมูล)'}</option>`).join(''); // พ.ศ. for a Thai-facing dropdown
  yearSel.value = keepYear;
  regionSel.innerHTML = `<option value="">ทุกสถานที่</option>` +
    historyFilterOptions.regions.map(r=>`<option value="${r.replace(/"/g,'&quot;')}">${r}</option>`).join('');
  regionSel.value = keepRegion;
  renderHistoryMonthOptions();
}
function renderHistoryMonthOptions(){
  const yearSel = document.getElementById('historyYearFilter');
  const monthSel = document.getElementById('historyMonthFilter');
  if(!yearSel || !monthSel || !historyFilterOptions) return;
  const keepMonth = monthSel.value;
  // No year picked yet, OR a year picked that has no LOCAL data yet (a
  // backfill-only year -- see ยังไม่มีข้อมูล in loadHistoryFilterOptions) --
  // either way there's no real "which months have data" answer yet, so
  // offer all 12 rather than an empty dropdown with nothing to narrow by.
  const months = (yearSel.value && historyFilterOptions.months_by_year[yearSel.value])
    ? historyFilterOptions.months_by_year[yearSel.value]
    : Array.from({length:12}, (_,i)=>i+1);
  monthSel.innerHTML = `<option value="">ทุกเดือน</option>` +
    months.map(m=>`<option value="${m}">${HISTORY_MONTH_NAMES[m]}</option>`).join('');
  monthSel.value = months.includes(Number(keepMonth)) ? keepMonth : '';
}

// Real, on-demand fetch from USGS/EMSC/GEOFON's live APIs (see
// /api/compare/history/backfill + world_quakes.run_historical_backfill) for
// whichever ปี(+เดือน) is currently selected -- per explicit request, so a
// year/month outside the background poller's own short live window can
// still be populated with real data instead of showing empty forever.
async function runHistoryBackfill(){
  const yearSel = document.getElementById('historyYearFilter');
  const monthSel = document.getElementById('historyMonthFilter');
  const btn = document.getElementById('historyBackfillBtn');
  const year = yearSel ? yearSel.value : '';
  if(!year){
    showToast('เลือกปีก่อน', 'กรุณาเลือก "ปี" ที่ต้องการดึงข้อมูลย้อนหลังจาก API จริงก่อน', false);
    return;
  }
  const month = monthSel ? monthSel.value : '';
  const originalHtml = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `${icon('warnTri')} กำลังดึงข้อมูล…`;
  try{
    const body = {year: Number(year)};
    if(month) body.month = Number(month);
    const res = await api('/api/compare/history/backfill', {method:'POST', body: JSON.stringify(body)});
    const bySrc = Object.entries(res.by_source||{})
      .map(([s,r])=> r.error ? `${s} ผิดพลาด (${r.error})` : `${s} ${r.fetched.toLocaleString()} เหตุการณ์`)
      .join(' · ');
    showToast('ดึงข้อมูลย้อนหลังเสร็จแล้ว', `รวม ${res.total_fetched.toLocaleString()} เหตุการณ์ (${bySrc})`, true);
    historyFilterOptions = null; // stale now that new years/regions may exist -- force a refetch
    await loadHistoryFilterOptions();
    yearSel.value = year;
    if(month) monthSel.value = month;
    historyPage = 1;
    await loadQuakeHistoryTable();
  }catch(e){
    showToast('ดึงข้อมูลย้อนหลังไม่สำเร็จ', e.message, false);
  }finally{
    btn.disabled = false;
    btn.innerHTML = originalHtml;
  }
}

async function loadQuakeHistoryTable(){
  const sourceSel = document.getElementById('historySourceFilter');
  const yearSel = document.getElementById('historyYearFilter');
  const monthSel = document.getElementById('historyMonthFilter');
  const regionSel = document.getElementById('historyRegionFilter');
  const searchInput = document.getElementById('historyPlaceSearch');
  const source = sourceSel ? sourceSel.value : '';
  const year = yearSel ? yearSel.value : '';
  const month = monthSel ? monthSel.value : '';
  const region = regionSel ? regionSel.value : '';
  const q = searchInput ? searchInput.value.trim() : '';
  const tbody = document.querySelector('#quakeHistoryTable tbody');
  const summary = document.getElementById('quakeHistorySummary');
  const pager = document.getElementById('quakeHistoryPager');
  const qs = new URLSearchParams({page: String(historyPage), page_size: '50'});
  if(source) qs.set('source', source);
  if(year) qs.set('year', year);
  if(month) qs.set('month', month);
  if(region) qs.set('region', region);
  if(q) qs.set('q', q);
  try{
    const hist = await api(`/api/compare/history?${qs.toString()}`);
    if(summary){
      const bySrc = Object.entries(hist.by_source||{}).map(([s,c])=>`${s} ${c.toLocaleString()}`).join(' · ');
      const since = hist.tracking_since ? new Date(hist.tracking_since).toLocaleString('th-TH') : '—';
      const filtered = (source||year||month||region||q) ? ` · ตรงตัวกรอง <b class="tabular">${hist.total.toLocaleString()}</b> เหตุการณ์` : '';
      summary.innerHTML = `สะสมทั้งหมด <b class="tabular">${Object.values(hist.by_source||{}).reduce((a,b)=>a+b,0).toLocaleString()}</b> เหตุการณ์ (${bySrc || 'ยังไม่มีข้อมูล'}) · เริ่มบันทึกตั้งแต่ ${since}${filtered}`+
        (hist.history_error? ` · <span style="color:var(--status-warn);">บันทึกข้อมูลขัดข้อง: ${hist.history_error}</span>` : '');
    }
    if(tbody){
      tbody.innerHTML = (hist.events||[]).map(e=>`
        <tr>
          <td class="tabular" style="color:var(--ink-muted);">${e.time_ms? new Date(e.time_ms).toLocaleString('th-TH') : '—'}</td>
          <td>${historySourceBadge(e.source)}</td>
          <td class="tabular strong">${e.magnitude!=null? e.magnitude.toFixed(1) : '—'}</td>
          <td class="tabular">${e.depth_km!=null? Math.round(e.depth_km)+' กม.' : '—'}</td>
          <td style="white-space:normal;">${e.place || 'ไม่ทราบตำแหน่ง'}${e.regional? ' <span class="badge info" style="font-size:12.5px;">ภูมิภาค</span>' : ''}</td>
          <td>${e.url? `<a href="${e.url}" target="_blank" rel="noopener" style="color:var(--accent-strong);">ดูรายละเอียด</a>` : '—'}</td>
        </tr>`).join('') || `<tr><td colspan="6" style="text-align:center;color:var(--ink-muted);">ไม่พบเหตุการณ์ตรงตัวกรองที่เลือก</td></tr>`;
    }
    if(pager){
      historyPage = hist.page;
      pager.innerHTML = hist.total > 0 ? `
        <span class="hint">หน้า ${hist.page} จาก ${hist.total_pages} (${hist.total.toLocaleString()} เหตุการณ์)</span>
        <button type="button" class="btn" id="historyPrevBtn" style="padding:6px 12px;font-size:14.5px;" ${hist.page<=1?'disabled':''}>ก่อนหน้า</button>
        <button type="button" class="btn" id="historyNextBtn" style="padding:6px 12px;font-size:14.5px;" ${hist.page>=hist.total_pages?'disabled':''}>ถัดไป</button>
      ` : '';
      document.getElementById('historyPrevBtn')?.addEventListener('click', ()=>{ historyPage = Math.max(1, historyPage-1); loadQuakeHistoryTable(); });
      document.getElementById('historyNextBtn')?.addEventListener('click', ()=>{ historyPage = historyPage+1; loadQuakeHistoryTable(); });
    }
  }catch(e){
    if(summary) summary.textContent = 'โหลดฐานข้อมูลประวัติไม่สำเร็จ: ' + e.message;
  }
}

// Line chart: real magnitude per source (USGS/EMSC/GEOFON/TMD, sparse -- each
// real event was reported by exactly one source) alongside a simulated
// "ENVIRO Sensor Network" reading for every event (see
// routes/compare.py:_simulated_enviro_estimate), so the gap between the
// dashed ENVIRO line and whichever real source has a point at that index is
// a rough visual read on estimation accuracy.
const ACCURACY_SOURCES = [
  {key:'USGS', color:'var(--series-usgs)'},
  {key:'EMSC', color:'var(--series-emsc)'},
  {key:'GEOFON', color:'var(--series-geofon)'},
  {key:'TMD', color:'var(--series-tmd)'},
];
async function loadAccuracyChart(){
  const panel = document.getElementById('accuracyChartBody');
  if(!panel) return;
  try{
    const data = await api('/api/compare/accuracy-series?limit=30');
    const events = data.events || [];
    if(!events.length){
      panel.innerHTML = `<p class="panel-sub" style="text-align:center;color:var(--ink-muted);">ยังไม่มีข้อมูลเพียงพอสำหรับสร้างกราฟ — ระบบจะเริ่มแสดงเมื่อสะสมเหตุการณ์จริงได้มากขึ้น</p>`;
      return;
    }
    const allMags = events.flatMap(e=>[e.magnitude, e.enviro_estimate]).filter(v=>v!=null);
    const lo = Math.floor(Math.min(...allMags) - 0.3), hi = Math.ceil(Math.max(...allMags) + 0.3);
    const W = 900, H = 260, padL = 30, padR = 8, padT = 8, padB = 22;
    const plotW = W - padL - padR, plotH = H - padT - padB;
    const n = events.length;
    const xOf = i => (i/(Math.max(1,n-1))) * plotW;
    const yOf = v => plotH - ((v-lo)/((hi-lo)||1))*plotH;

    const yTicks = [];
    for(let m=Math.ceil(lo); m<=hi; m++) yTicks.push(m);
    const gridLines = yTicks.map(m=>
      `<line x1="0" y1="${yOf(m).toFixed(1)}" x2="${plotW}" y2="${yOf(m).toFixed(1)}" stroke="var(--border)" stroke-width="1" opacity="0.5"/>`+
      `<text x="-8" y="${(yOf(m)+3).toFixed(1)}" font-size="9" text-anchor="end" fill="var(--ink-muted)">M${m}</text>`
    ).join('');

    const realSeries = ACCURACY_SOURCES.map(s=>{
      const values = events.map(e => e.source === s.key ? e.magnitude : null);
      const d = sparsePathFromSeries(values, plotW, plotH, [lo,hi]);
      const pts = events.map((e,i)=> e.source !== s.key ? '' : `<circle class="hoverable" data-tip="<div class='tt'>${s.key} · ${new Date(e.time_ms).toLocaleDateString('th-TH')}</div><div class='ts'>M${e.magnitude.toFixed(1)} — ${(e.place||'ไม่ทราบตำแหน่ง').replace(/"/g,'&quot;')}</div>" cx="${xOf(i).toFixed(1)}" cy="${yOf(e.magnitude).toFixed(1)}" r="3.4" fill="${s.color}"/>`).join('');
      return (d? `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="1.6" opacity="0.9"/>` : '') + pts;
    }).join('');

    const enviroValues = events.map(e=>e.enviro_estimate);
    const enviroPath = sparsePathFromSeries(enviroValues, plotW, plotH, [lo,hi]);
    const enviroPts = events.map((e,i)=>
      `<circle class="hoverable" data-tip="<div class='tt'>ENVIRO Sensor Network (จำลอง)</div><div class='ts'>ประเมิน M${e.enviro_estimate.toFixed(1)} · จริงจาก ${e.source} M${e.magnitude.toFixed(1)} (คลาดเคลื่อน ${Math.abs(e.enviro_estimate-e.magnitude).toFixed(2)})</div>" cx="${xOf(i).toFixed(1)}" cy="${yOf(e.enviro_estimate).toFixed(1)}" r="2.6" fill="var(--series-enviro)"/>`
    ).join('');

    const legend = ACCURACY_SOURCES.map(s=>`<div class="legend-item"><span class="legend-swatch" style="background:${s.color};"></span>${s.key}</div>`).join('') +
      `<div class="legend-item"><span class="legend-swatch" style="background:var(--series-enviro);"></span>ENVIRO Sensor Network (จำลอง)</div>`;

    panel.innerHTML = `
      <div class="legend" style="margin-bottom:10px;">${legend}</div>
      <div class="scroll-x">
        <svg class="chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="width:100%;height:${H}px;min-width:640px;">
          <g transform="translate(${padL},${padT})">
            ${gridLines}
            ${realSeries}
            <path d="${enviroPath}" fill="none" stroke="var(--series-enviro)" stroke-width="2" stroke-dasharray="4 3"/>
            ${enviroPts}
          </g>
        </svg>
      </div>
      <p class="panel-sub" style="margin-top:8px;">${events.length} เหตุการณ์ล่าสุด (เรียงตามเวลาเกิดเหตุ) · ${data.note}</p>`;
  }catch(e){
    panel.innerHTML = `<p class="panel-sub" style="color:var(--status-warn);">โหลดกราฟไม่สำเร็จ: ${e.message}</p>`;
  }
}

async function renderCompare(){
  const [cmp, fc] = await Promise.all([api('/api/compare'), api('/api/compare/forecast')]);

  const rows = cmp.sources.map(s=>{
    const latencyLabel = s.latency_sec==null ? '—' : (s.latency_sec>=60? (s.latency_sec/60).toFixed(0)+' นาที' : Math.round(s.latency_sec)+' วิ');
    const connBadge = s.simulated===false ? `<span class="badge ${s.connected?'good':'critical'}" style="margin-left:6px;">${s.connected?'เชื่อมต่อจริง':'ขาดการเชื่อมต่อ'}</span>` : '';
    return `<tr>
      <td><span class="legend-item"><span class="legend-swatch" style="background:${s.color_var};"></span><span class="strong">${s.name}</span>${connBadge}</span></td>
      <td class="tabular strong">${s.magnitude!=null? s.magnitude.toFixed(1) : '—'}</td>
      <td class="tabular">${s.depth!=null? s.depth+' กม.' : '—'}</td>
      <td class="tabular">${latencyLabel}</td>
      <td class="tabular">${s.confidence!=null? s.confidence+'%' : '—'}</td>
      <td class="tabular">${s.loc_err_km!=null? '±'+s.loc_err_km+' กม.' : '—'}</td>
      <td style="white-space:normal;color:var(--ink-muted);font-size:15px;">${s.note||''}${s.url?` · <a href="${s.url}" target="_blank" rel="noopener" style="color:var(--accent-strong);">ดูรายละเอียด ${s.name}</a>`:''}</td>
    </tr>`;
  }).join('');

  const enviro = cmp.sources.find(s=>s.name==='ENVIRO');
  const latencies = cmp.sources.filter(s=>s.latency_sec!=null);
  const maxLatency = Math.max(...latencies.map(s=>s.latency_sec), 1);
  const latBars = latencies.map(s=>`
    <div style="display:flex;align-items:center;gap:10px;">
      <span style="width:64px;font-size:15.5px;color:var(--ink-secondary);">${s.name}</span>
      <div style="flex:1;background:var(--surface-2);border-radius:6px;height:14px;">
        <div class="hoverable" data-tip="<div class='tt'>${s.name}</div><div class='ts'>หน่วงเวลา ${s.latency_sec} วินาที</div>" style="width:${Math.max(3,(s.latency_sec/maxLatency)*100)}%;height:100%;background:${s.color_var};border-radius:6px;"></div>
      </div>
      <span class="tabular" style="width:56px;text-align:right;font-size:15px;color:var(--ink-secondary);">${s.latency_sec>=60? (s.latency_sec/60).toFixed(0)+'m' : Math.round(s.latency_sec)+'s'}</span>
    </div>`).join('');
  const confs = cmp.sources.filter(s=>s.confidence!=null);
  const confBars = confs.map(s=>`
    <div style="display:flex;align-items:center;gap:10px;">
      <span style="width:64px;font-size:15.5px;color:var(--ink-secondary);">${s.name}</span>
      <div style="flex:1;background:var(--surface-2);border-radius:6px;height:14px;">
        <div class="hoverable" data-tip="<div class='tt'>${s.name}</div><div class='ts'>ความเชื่อมั่น ${s.confidence}%</div>" style="width:${s.confidence}%;height:100%;background:${s.color_var};border-radius:6px;"></div>
      </div>
      <span class="tabular" style="width:36px;text-align:right;font-size:15px;color:var(--ink-secondary);">${s.confidence}%</span>
    </div>`).join('');

  const fw=560, fh=120, fmax=45;
  const fcharts = fc.series.map(r=>{
    const d = pathFromSeries(r.data, fw, fh-24, [0,fmax]);
    const areaD = d + ` L${fw},${fh-24} L0,${fh-24} Z`;
    const pts = r.data.map((v,i)=>{
      const x=(i/(r.data.length-1))*fw;
      const y=(fh-24) - (v/fmax)*(fh-24);
      return `<circle class="hoverable" data-tip="<div class='tt'>${fc.days[i]}</div><div class='ts'>โอกาส ${v}%</div>" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3.2" fill="${r.color}"/>`;
    }).join('');
    const dayLabels = fc.days.map((dLabel,i)=>`<text x="${(i/(fc.days.length-1))*fw}" y="${fh-6}" font-size="9" text-anchor="middle">${dLabel}</text>`).join('');
    return `<div style="display:flex;flex-direction:column;gap:6px;">
      <div class="legend-item"><span class="legend-swatch" style="background:${r.color};"></span>${r.region}</div>
      <svg class="chart" viewBox="0 0 ${fw} ${fh}" preserveAspectRatio="none" style="width:100%;height:${fh}px;">
        <path d="${areaD}" fill="${r.color}" opacity=".12"/>
        <path d="${d}" fill="none" stroke="${r.color}" stroke-width="1.8"/>
        ${pts}${dayLabels}
      </svg>
    </div>`;
  }).join('');

  document.getElementById('view-compare').innerHTML = `
    <div class="view-head">
      <h2>เปรียบเทียบแหล่งข้อมูล</h2>
      <p class="desc">เปรียบเทียบผลตรวจจับจาก ENVIRO, กรมอุตุนิยมวิทยา (TMD), USGS, EMSC, GEOFON, GISTDA และ NASA — แถว USGS/EMSC/GEOFON เชื่อมต่อฟีดสาธารณะจริงแบบเรียลไทม์ (สามแหล่งอิสระหลักที่ใช้อ้างอิงความถูกต้องของ Edge AI) ส่วน TMD/GISTDA/NASA ยังเป็นข้อมูลอ้างอิงประกอบการสาธิตจนกว่าจะมีข้อตกลงเชื่อมต่อ API กับหน่วยงาน</p>
    </div>
    <div class="grid grid-4">
      <div class="stat-tile"><span class="label">เหตุการณ์ล่าสุด</span><span class="value" style="font-size:21px;">${cmp.event_id || 'ยังไม่มีเหตุการณ์'}</span></div>
      <div class="stat-tile"><span class="label">แหล่งที่แจ้งเตือนเร็วที่สุด</span><span class="value" style="font-size:25px;color:var(--series-enviro);">ENVIRO</span></div>
      <div class="stat-tile"><span class="label">ความหน่วงของ ENVIRO</span><span class="value tabular">${enviro? enviro.latency_sec : '—'}<small>วินาที</small></span></div>
      <div class="stat-tile"><span class="label">สถานะฟีดจริง (USGS·EMSC·GEOFON)</span><span class="value" style="font-size:18.5px;color:${cmp.sources.filter(s=>s.simulated===false).every(s=>s.connected)?'var(--status-good)':'var(--status-warn)'};">${cmp.sources.filter(s=>s.simulated===false&&s.connected).length}/${cmp.sources.filter(s=>s.simulated===false).length} เชื่อมต่ออยู่</span></div>
    </div>
    <div class="panel">
      <div class="panel-head"><h3>ตารางเปรียบเทียบ${cmp.event_id? ' · เหตุการณ์ '+cmp.event_id : ''}</h3></div>
      <div class="scroll-x">
        <table class="data-table">
          <thead><tr><th>แหล่งข้อมูล</th><th>ขนาด (Mw)</th><th>ความลึก</th><th>เวลาแจ้งเตือน</th><th>ความเชื่อมั่น</th><th>คลาดเคลื่อนตำแหน่ง</th><th>หมายเหตุ</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>
    <div class="grid grid-2">
      <div class="panel">
        <div class="panel-head"><h3>เวลาแจ้งเตือน (Latency)</h3></div>
        <div style="display:flex;flex-direction:column;gap:11px;">${latBars}</div>
      </div>
      <div class="panel">
        <div class="panel-head"><h3>ความเชื่อมั่น (Confidence)</h3></div>
        <div style="display:flex;flex-direction:column;gap:11px;">${confBars}</div>
      </div>
    </div>
    <div class="panel">
      <div class="panel-head">
        <h3>ฐานข้อมูลประวัติแผ่นดินไหวจริง</h3>
      </div>
      <p class="panel-sub">ทุกเหตุการณ์จริงที่ระบบเคยพบจากทุกฟีด จะถูกบันทึกลงฐานข้อมูลถาวรตั้งแต่ระบบเริ่มทำงาน (ไม่หายไปเมื่อรีสตาร์ท และไม่ถูกจำกัดตามช่วงเวลาย้อนหลังของแต่ละ API เหมือนแผนที่) — เป็นวัตถุดิบสำหรับ Edge AI นำไปวิเคราะห์แนวโน้มและพัฒนาการพยากรณ์ในอนาคต ปัจจุบันเป็นการเก็บข้อมูลดิบเท่านั้น ยังไม่มีการวิเคราะห์หรือพยากรณ์อัตโนมัติจากข้อมูลชุดนี้</p>
      <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:10px;">
        <select class="field" id="historySourceFilter" style="width:auto;padding:5px 10px;font-size:15.5px;">
          <option value="">ทุกแหล่งข้อมูล</option>
          <option value="USGS">USGS</option>
          <option value="EMSC">EMSC</option>
          <option value="GEOFON">GEOFON</option>
          <option value="TMD">TMD</option>
        </select>
        <select class="field" id="historyYearFilter" style="width:auto;padding:5px 10px;font-size:15.5px;">
          <option value="">ทุกปี</option>
        </select>
        <select class="field" id="historyMonthFilter" style="width:auto;padding:5px 10px;font-size:15.5px;">
          <option value="">ทุกเดือน</option>
        </select>
        <select class="field" id="historyRegionFilter" style="width:auto;padding:5px 10px;font-size:15.5px;max-width:220px;">
          <option value="">ทุกสถานที่</option>
        </select>
        <input type="text" class="field" id="historyPlaceSearch" placeholder="พิมพ์ค้นหาสถานที่/คำค้น…" style="width:180px;padding:5px 10px;font-size:15.5px;">
        <button type="button" class="btn" id="historyFilterClearBtn" style="padding:6px 12px;font-size:14.5px;">ล้างตัวกรอง</button>
        <button type="button" class="btn" id="historyBackfillBtn" style="padding:6px 12px;font-size:14.5px;border-color:var(--accent-strong);color:var(--accent-strong);"
          title="ดึงเหตุการณ์จริงจาก USGS/EMSC/GEOFON สำหรับปีที่เลือก (หรือปี+เดือน) มาเก็บลงฐานข้อมูล — ย้อนหลังได้สูงสุด 3 ปี">${icon('layers')} ดึงข้อมูลย้อนหลัง (API จริง)</button>
      </div>
      <div id="quakeHistorySummary" class="hint" style="margin-bottom:10px;">กำลังโหลด…</div>
      <div class="scroll-x">
        <table class="data-table" id="quakeHistoryTable">
          <thead><tr><th>เวลาเกิดเหตุ</th><th>แหล่งข้อมูล</th><th>ขนาด</th><th>ความลึก</th><th>ตำแหน่ง</th><th></th></tr></thead>
          <tbody><tr><td colspan="6" style="text-align:center;color:var(--ink-muted);">กำลังโหลด…</td></tr></tbody>
        </table>
      </div>
      <div id="quakeHistoryPager" style="display:flex;gap:10px;align-items:center;justify-content:flex-end;margin-top:10px;"></div>
    </div>
    <div class="panel">
      <div class="panel-head"><h3>ความแม่นยำของขนาดแผ่นดินไหว — เทียบรายแหล่งข้อมูล (Accuracy)</h3></div>
      <p class="panel-sub">ขนาด (Mw) ของเหตุการณ์จริงล่าสุดที่แต่ละแหล่งข้อมูล (USGS/EMSC/GEOFON/TMD) รายงาน เทียบกับค่าประมาณของ "ENVIRO Sensor Network" — สถานีเซนเซอร์ที่จำลองขึ้นเพื่อการเปรียบเทียบนี้โดยเฉพาะ (เครือข่าย ENVIRO จริงยังไม่เคยตรวจวัดเหตุการณ์ทั่วโลกเหล่านี้โดยตรง มีแต่ทดสอบกับสถานการณ์จำลองในไทย)</p>
      <div id="accuracyChartBody"><p class="panel-sub" style="text-align:center;color:var(--ink-muted);">กำลังโหลด…</p></div>
    </div>
    <div class="panel">
      <div class="panel-head"><h3>พยากรณ์เชิงสถิติ 7 วันข้างหน้า (AI Forecast)</h3></div>
      <div class="callout">${icon('warnTri')}<div><b>ข้อจำกัดสำคัญ:</b> ${fc.disclaimer}</div></div>
      <div class="grid grid-3">${fcharts}</div>
    </div>`;

  // Any filter change starts back at page 1 -- otherwise "หน้า 4" could
  // silently persist into a filtered result set with only 1 page, showing
  // the "ไม่พบเหตุการณ์" empty state for no real reason.
  const resetPageAndReload = ()=>{ historyPage = 1; loadQuakeHistoryTable(); };
  document.getElementById('historySourceFilter').addEventListener('change', resetPageAndReload);
  document.getElementById('historyYearFilter').addEventListener('change', ()=>{ renderHistoryMonthOptions(); resetPageAndReload(); });
  document.getElementById('historyMonthFilter').addEventListener('change', resetPageAndReload);
  document.getElementById('historyRegionFilter').addEventListener('change', resetPageAndReload);
  // Debounced -- searches as you type (พิมพ์ค้นหา) without hammering the API
  // on every keystroke; Enter fires immediately without waiting it out.
  let historySearchDebounce = null;
  document.getElementById('historyPlaceSearch').addEventListener('input', ()=>{
    clearTimeout(historySearchDebounce);
    historySearchDebounce = setTimeout(resetPageAndReload, 400);
  });
  document.getElementById('historyPlaceSearch').addEventListener('keydown', e=>{
    if(e.key === 'Enter'){ clearTimeout(historySearchDebounce); resetPageAndReload(); }
  });
  document.getElementById('historyFilterClearBtn').addEventListener('click', ()=>{
    ['historySourceFilter','historyYearFilter','historyMonthFilter','historyRegionFilter'].forEach(id=>{
      document.getElementById(id).value = '';
    });
    document.getElementById('historyPlaceSearch').value = '';
    renderHistoryMonthOptions();
    resetPageAndReload();
  });
  document.getElementById('historyBackfillBtn').addEventListener('click', runHistoryBackfill);
  loadHistoryFilterOptions().then(loadQuakeHistoryTable);
  loadAccuracyChart();
}

