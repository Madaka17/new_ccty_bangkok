// The AI earthquake brief tab. A classic script (not a module): every js/ file shares one global scope and index.html loads them in order.

/* ============================= AI EARTHQUAKE BRIEF ============================= */
// Written server-side (server/quake_brief.py) from the live catalogs. The AI's text and the feeds' place
// names are escaped before they go into the page.
function escHtml(s){
  return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function briefCoords(e){
  return `${Math.abs(e.lat).toFixed(2)}°${e.lat>=0?'N':'S'} ${Math.abs(e.lng).toFixed(2)}°${e.lng>=0?'E':'W'}`;
}
function briefTectonics(e, ready){
  if(!ready) return '<span style="color:var(--ink-muted);">กำลังโหลดข้อมูลแนวรอยต่อ</span>';
  const parts = [];
  if(e.plate) parts.push(`${e.plate.subduction?'เขตมุดตัว ':'แนวรอยต่อ '}${escHtml(e.plate.name)} (ห่าง ${e.plate.dist_km} กม.)`);
  if(e.fault) parts.push(`รอยเลื่อน ${escHtml(e.fault.name)}${e.fault.slip_type?' · '+escHtml(e.fault.slip_type):''} (ห่าง ${e.fault.dist_km} กม.)`);
  return parts.join('<br>') || '<span style="color:var(--ink-muted);">ไม่อยู่ใกล้แนวรอยต่อหรือรอยเลื่อนที่ทราบ</span>';
}
function briefEventRow(e, withImpact, ready){
  const src = e.url ? `<a href="${escHtml(e.url)}" target="_blank" rel="noopener" style="color:var(--accent-strong);">${escHtml(e.source)}</a>` : escHtml(e.source);
  return `<tr>
    <td class="tabular">${escHtml(e.time)}</td>
    <td class="tabular strong">M${e.magnitude.toFixed(1)}</td>
    <td class="tabular">${e.depth_km!=null ? e.depth_km+' กม.' : '—'}</td>
    <td style="white-space:normal;min-width:200px;">${escHtml(e.place)}<div class="tabular" style="font-size:14px;color:var(--ink-muted);">${briefCoords(e)}</div></td>
    <td style="white-space:normal;min-width:220px;font-size:15px;">${briefTectonics(e, ready)}</td>
    ${withImpact ? `<td class="tabular">${e.dist_bkk_km.toLocaleString()} กม.</td>
    <td>${e.max_mmi_th>=2 ? `MMI ${mmiRomanJs(e.max_mmi_th)} · ${escHtml(e.max_mmi_th_where)}` : '<span style="color:var(--ink-muted);">ไม่รู้สึก</span>'}</td>` : ''}
    <td>${src}</td>
  </tr>`;
}

async function renderBrief(){
  const b = await api('/api/world/brief');
  const el = document.getElementById('view-brief');
  const title = '<h2>AI วิเคราะห์แผ่นดินไหวล่าสุด</h2>';
  if(!b.ready){
    el.innerHTML = `<div class="view-head">${title}<p class="desc">กำลังรวบรวมข้อมูลจาก USGS · EMSC · GEOFON · TMD และเขียนบทวิเคราะห์ เปิดแท็บนี้อีกครั้งในอีกสักครู่</p></div>`;
    return;
  }
  const f = b.facts, lv = f.level, bkk = f.bangkok;
  const [bg, fg] = levelPillStyle(lv.lv);
  const writer = b.source === 'template' ? 'สรุปอัตโนมัติจากข้อมูล (ไม่ได้ใช้ AI)' : `เขียนโดย AI (${escHtml(b.source)})`;
  const updated = new Date(b.updated_at * 1000).toLocaleString('th-TH', {dateStyle:'medium', timeStyle:'short'});
  const none = cols => `<tr><td colspan="${cols}" style="color:var(--ink-muted);">ไม่มีรายงาน</td></tr>`;
  const provinceRows = f.provinces.map((p, i) => {
    const [pbg, pfg] = levelPillStyle(p.level);
    return `<tr>
      <td class="tabular">${i+1}</td>
      <td class="strong">${escHtml(p.province)}${p.soft_clay ? ' <span class="badge neutral">ดินอ่อน</span>' : ''}</td>
      <td>${escHtml(p.region)}</td>
      <td><span class="badge" style="background:${pbg};color:${pfg};">MMI ${p.roman} · ระดับ ${p.level}</span></td>
      <td style="white-space:normal;min-width:200px;font-size:15px;">${escHtml(p.event)} (ห่าง ${p.dist_km.toLocaleString()} กม.)</td>
    </tr>`;
  }).join('');
  const maxRisk = Math.max(1, ...f.standing_hazard.map(r => r.score));
  const riskBars = f.standing_hazard.slice(0, 8).map(r => `
    <div style="display:flex;align-items:center;gap:10px;">
      <span style="width:120px;font-size:15.5px;color:var(--ink-secondary);">${escHtml(r.region)}</span>
      <div style="flex:1;background:var(--surface-2);border-radius:6px;height:12px;"><div style="width:${r.score/maxRisk*100}%;height:100%;background:var(--status-warn);border-radius:6px;"></div></div>
      <span class="tabular" style="width:32px;text-align:right;font-size:15px;">${r.score}</span>
    </div>`).join('');

  el.innerHTML = `
    <div class="view-head">${title}
      <p class="desc">สรุปจากฟีดจริง USGS · EMSC · GEOFON · TMD ย้อนหลัง ${f.window_days} วัน: แผ่นดินไหวขนาด 4.5 ขึ้นไปทั่วโลก และเหตุการณ์ใกล้ไทย · ${writer} · อัปเดต ${updated}</p>
    </div>
    <div class="callout" style="border-color:${fg};background:${bg};flex-direction:column;gap:4px;">
      <div style="font-size:15px;font-weight:600;color:${fg};">ผลกระทบสูงสุดต่อไทย: ระดับ ${lv.lv} · ${escHtml(lv.name)} (MMI ${lv.roman})</div>
      <div style="color:var(--ink-primary);font-weight:600;">${escHtml(b.headline)}</div>
    </div>
    <div class="grid grid-4">
      <div class="stat-tile"><span class="label">M4.5+ ทั่วโลก (${f.window_days} วัน)</span><span class="value tabular">${f.world.count}<small>ครั้ง</small></span></div>
      <div class="stat-tile"><span class="label">M6+ ทั่วโลก</span><span class="value tabular">${f.world.count_m6}<small>ครั้ง</small></span></div>
      <div class="stat-tile"><span class="label">ใกล้ประเทศไทย</span><span class="value tabular">${f.near_count}<small>ครั้ง</small></span></div>
      <div class="stat-tile"><span class="label">กรุงเทพฯ (คาดการณ์)</span><span class="value" style="font-size:25px;">${bkk && bkk.mmi >= 2 ? 'MMI '+bkk.roman : 'ไม่รู้สึก'}</span></div>
    </div>
    <div class="grid grid-12">
      <div class="panel col-7">
        <div class="panel-head"><h3>ภาพรวมทั่วโลกและภูมิภาค</h3><span class="hint">ขนาดใหญ่ที่สุด ${f.world.top.length} เหตุการณ์</span></div>
        <p class="brief-text">${escHtml(b.world)}</p>
        <div class="scroll-x"><table class="data-table">
          <thead><tr><th>เวลา (ไทย)</th><th>ขนาด</th><th>ลึก</th><th>ศูนย์กลาง</th><th>แนวรอยต่อ / รอยเลื่อน</th><th>แหล่ง</th></tr></thead>
          <tbody>${f.world.top.map(e => briefEventRow(e, false, f.tectonics_ready)).join('') || none(6)}</tbody>
        </table></div>
      </div>
      <div class="panel col-5">
        <div class="panel-head"><h3>ความเสี่ยงต่ออาคาร</h3><span class="badge" style="background:${bg};color:${fg};">ระดับ ${lv.lv} · ${escHtml(lv.name)}</span></div>
        <p class="brief-text">${escHtml(b.buildings)}</p>
        <h3 style="font-size:17px;">ควรทำอย่างไร</h3>
        <ul class="brief-list">${b.advice.map(a => `<li>${escHtml(a)}</li>`).join('')}</ul>
      </div>
      <div class="panel col-12">
        <div class="panel-head"><h3>แผ่นดินไหวใกล้ประเทศไทย</h3><span class="hint">เรียงตามแรงสั่นที่คาดว่าถึงไทย · แสดง ${f.near.length} จาก ${f.near_count} เหตุการณ์</span></div>
        <div class="scroll-x"><table class="data-table">
          <thead><tr><th>เวลา (ไทย)</th><th>ขนาด</th><th>ลึก</th><th>ศูนย์กลาง</th><th>แนวรอยต่อ / รอยเลื่อน</th><th>ห่าง กทม.</th><th>แรงสั่นสูงสุดในไทย</th><th>แหล่ง</th></tr></thead>
          <tbody>${f.near.map(e => briefEventRow(e, true, f.tectonics_ready)).join('') || none(8)}</tbody>
        </table></div>
      </div>
      <div class="panel col-7">
        <div class="panel-head"><h3>จังหวัดที่ได้รับผลกระทบมากที่สุด</h3><span class="hint">MMI คาดการณ์ตามระยะทาง · ดินอ่อน +${f.amplify_mmi}</span></div>
        <p class="brief-text">${escHtml(b.thailand)}</p>
        ${provinceRows ? `<div class="scroll-x"><table class="data-table">
          <thead><tr><th>#</th><th>จังหวัด</th><th>ภาค</th><th>แรงสั่นที่คาด</th><th>จากเหตุการณ์</th></tr></thead>
          <tbody>${provinceRows}</tbody>
        </table></div>` : `<p class="panel-sub" style="margin-top:0;">ไม่มีจังหวัดใดคาดว่ารู้สึกแรงสั่น (MMI ต่ำกว่า II)${bkk ? ` · กรุงเทพฯ คาด MMI ${bkk.mmi.toFixed(1)}` : ''}</p>`}
      </div>
      <div class="panel col-5">
        <div class="panel-head"><h3>ความเสี่ยงประจำพื้นที่</h3><span class="hint">จากรอยเลื่อนมีพลังในประเทศ · เต็ม 100</span></div>
        <div style="display:flex;flex-direction:column;gap:8px;">${riskBars}</div>
        <p class="panel-sub" style="margin-top:0;">รอยเลื่อนมีพลัง: ${f.thai_faults.map(x => `${escHtml(x.name)} (${escHtml(x.province)})`).join(' · ')}</p>
        <p class="panel-sub" style="margin-top:0;">ผลระยะไกล: ${f.soft_clay.map(escHtml).join(' ')} อยู่บนชั้นดินเหนียวอ่อน ซึ่งขยายแรงสั่นจากแผ่นดินไหวใหญ่ที่อยู่ไกล (คิดเพิ่ม +${f.amplify_mmi} MMI)</p>
      </div>
    </div>
    <p class="footnote">บทวิเคราะห์นี้เขียนอัตโนมัติจากข้อมูลแผ่นดินไหวสาธารณะ ค่า MMI เป็นค่าประมาณจากแบบจำลองตามระยะทาง ไม่ใช่ค่าที่วัดได้จริง และไม่ใช่ประกาศเตือนภัยทางการ ให้ยึดประกาศจากกรมอุตุนิยมวิทยาและ ปภ. เป็นหลัก · แนวรอยต่อแผ่นเปลือกโลก: Bird (2003) PB2002 · รอยเลื่อน: GEM Global Active Faults</p>`;
}

