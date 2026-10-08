// View 6: admin. A classic script (not a module): every js/ file shares one global scope and index.html loads them in order.

/* ============================= VIEW 6: ADMIN ============================= */
const STATUS_LABEL = {good:{cls:'good',text:'ปกติ'}, watch:{cls:'watch',text:'เสื่อมประสิทธิภาพ'}, critical:{cls:'critical',text:'ขัดข้อง'}};

function renderAuditRows(rows){
  return rows.map(a=>`<tr><td class="tabular" style="color:var(--ink-muted);">${new Date(a.ts).toLocaleString('th-TH')}</td><td class="strong tabular">${a.username}</td><td>${a.action}</td></tr>`).join('');
}

async function refreshAuditLog(){
  const rows = await api('/api/admin/audit-log?limit=8');
  const el = document.querySelector('#auditTable tbody');
  if(el) el.innerHTML = renderAuditRows(rows);
}

async function renderAdmin(){
  const [services, roles, audit, backup, levels, epi, tg] = await Promise.all([
    api('/api/admin/services'), api('/api/admin/roles'), api('/api/admin/audit-log?limit=8'),
    api('/api/admin/backup'), api('/api/levels'), api('/api/admin/epicenter-options'),
    api('/api/admin/telegram').catch(()=>({bot_token_masked:'',has_token:false,chat_id:'',enabled:false})),
  ]);

  const svcRows = services.map(s=>{
    const st = STATUS_LABEL[s.status] || STATUS_LABEL.good;
    return `<div class="panel" style="padding:14px 16px;flex-direction:row;align-items:center;gap:14px;">
      <span class="badge ${st.cls}"><span class="dot" style="background:currentColor;"></span>${st.text}</span>
      <div style="flex:1;min-width:0;">
        <div style="font-weight:500;font-size:17px;">${s.name}</div>
        <div style="font-size:14px;color:var(--ink-muted);">${s.note?s.note+' · ':''}ตรวจล่าสุด ${s.checked_at} · ทำงานต่อเนื่อง ${s.process_uptime}</div>
      </div>
      <span class="tabular" style="font-size:16px;color:var(--ink-secondary);">Uptime ${s.uptime_pct}%</span>
    </div>`;
  }).join('');

  const roleRows = roles.map(r=>`<tr><td class="strong">${r.role}</td><td class="tabular">${r.users_count}</td><td style="white-space:normal;">${r.permissions}</td></tr>`).join('');
  const levelOptions = levels.map(l=>`<option value="${l.lv}">ระดับ ${l.lv} — ${l.name}</option>`).join('');
  const regionOptions = ['ภาคเหนือตอนบน','ภาคตะวันตก','ภาคใต้ฝั่งอันดามัน','ทั่วประเทศ (สาธิต)'].map(r=>`<option>${r}</option>`).join('');

  document.getElementById('view-admin').innerHTML = `
    <div class="view-head">
      <h2>ผู้ดูแลระบบ</h2>
      <p class="desc">สถานะระบบส่วนกลาง (API/Gateway), สิทธิ์ผู้ใช้, บันทึกการตรวจสอบ, การสำรองข้อมูล (สำรองจริงลงดิสก์) และการทดสอบส่งแจ้งเตือนแบบปลอดภัย · เข้าสู่ระบบในนาม <b>${AUTH.display_name}</b> (${AUTH.role})</p>
    </div>
    <div class="grid grid-12">
      <div class="col-7" style="display:flex;flex-direction:column;gap:10px;">
        <div class="panel-head" style="padding:0 2px;"><h3>สถานะระบบ (API · Gateway · Calibration · AI Model)</h3></div>
        ${svcRows}
      </div>
      <div class="col-5" style="display:flex;flex-direction:column;gap:14px;">
        <div class="panel">
          <div class="panel-head"><h3>การสำรองข้อมูล (Backup)</h3><span class="badge good"><span class="dot" style="background:currentColor;"></span>${backup?'สำเร็จ':'ยังไม่เคยสำรอง'}</span></div>
          <table class="data-table">
            <tr><td>สำรองล่าสุด</td><td class="strong" id="backupTs">${backup? new Date(backup.ts).toLocaleString('th-TH') : '—'}</td></tr>
            <tr><td>ขนาดไฟล์</td><td class="strong tabular" id="backupSize">${backup? (backup.size_bytes/1024).toFixed(0)+' KB' : '—'}</td></tr>
            <tr><td>ที่อยู่ไฟล์</td><td class="strong tabular" style="font-size:14px;" id="backupPath">${backup? backup.path.split('/').pop() : '—'}</td></tr>
            <tr><td>นโยบายเก็บรักษา</td><td class="strong">รายวัน 30 ชุด / รายเดือน 12 ชุด</td></tr>
          </table>
          <button class="btn primary" id="runBackupBtn" data-requires-admin style="align-self:flex-start;">สำรองข้อมูลตอนนี้</button>
        </div>
        <div class="panel">
          <div class="panel-head"><h3>สิทธิ์ผู้ใช้งาน</h3></div>
          <div class="scroll-x">
            <table class="data-table"><thead><tr><th>บทบาท</th><th>ผู้ใช้</th><th>สิทธิ์</th></tr></thead><tbody>${roleRows}</tbody></table>
          </div>
        </div>
      </div>
      <div class="panel col-7">
        <div class="panel-head"><h3>บันทึกการตรวจสอบ (Audit Log)</h3><span class="hint">ล่าสุด 8 รายการ</span></div>
        <div class="scroll-x">
          <table class="data-table" id="auditTable"><thead><tr><th>เวลา</th><th>ผู้ใช้</th><th>เหตุการณ์</th></tr></thead><tbody>${renderAuditRows(audit)}</tbody></table>
        </div>
      </div>
      <div class="panel col-5">
        <div class="panel-head"><h3>ทดสอบส่งการแจ้งเตือน (Safe Test Alert)</h3><span class="badge info">โหมดแซนด์บ็อกซ์</span></div>
        <p class="panel-sub">การทดสอบนี้จะไม่ส่งสัญญาณจริงไปยังประชาชนหรือช่องทางภายนอกใด ๆ ใช้สำหรับตรวจสอบการทำงานภายในเท่านั้น</p>
        <div class="field-row">
          <label>ระดับที่ทดสอบ<select class="field" id="testLevel">${levelOptions}</select></label>
          <label>พื้นที่ทดสอบ<select class="field" id="testRegion">${regionOptions}</select></label>
        </div>
        <button class="btn primary" id="testAlertBtn" data-requires-write style="align-self:flex-start;">${icon('bell')} ส่งการแจ้งเตือนทดสอบ</button>
      </div>
      <div class="panel col-12">
        <div class="panel-head"><h3>จำลองแผ่นดินไหว (Simulate Earthquake)</h3><span class="badge warn">ผ่านไปป์ไลน์ตรวจจับจริง</span></div>
        <p class="panel-sub">ต่างจากการทดสอบแจ้งเตือนด้านบน — ปุ่มนี้จะฉีดคลื่นสัญญาณจำลองเข้าสถานีจริง แล้วให้อัลกอริทึม STA/LTA, การประเมิน PGA และ Multi-node corroboration ทำงานสด ๆ เหมือนเหตุการณ์จริง (ใช้เวลาสองสามวินาทีถึงราวหนึ่งนาทีกว่าจะเห็นการแจ้งเตือน ขึ้นกับระยะทางคลื่นเดินทาง) <b>ระดับที่ประกาศขึ้นกับความรุนแรงที่คาดการณ์ ณ ตำแหน่งอ้างอิง (กรุงเทพฯ)</b> ซึ่งลดลงตามระยะทางจริงจากรอยเลื่อนที่เลือก — แผ่นดินไหวขนาดใหญ่บนรอยเลื่อนที่อยู่ไกลจึงอาจให้ระดับต่ำกว่าที่คาดหากยังไม่ถึงกรุงเทพฯ มากนัก (นี่คือประเด็นที่ต้องการสื่อ: ขนาดกับความรุนแรงเป็นคนละเรื่องกัน)</p>
        <div class="field-row">
          <label>ศูนย์กลาง (เลือกจากรอยเลื่อน)<select class="field" id="quakeEpicenter">${epi.epicenters.map(e=>`<option value="${e.key}">${e.label}</option>`).join('')}</select></label>
          <label>ขนาด (Magnitude)<select class="field" id="quakeMagnitude">${epi.magnitudes.map(m=>`<option value="${m}" ${m===4.8?'selected':''}>M${m}${m===7.7?' (เทียบเท่าเหตุการณ์เมียนมา มี.ค. 2568)':''}</option>`).join('')}</select></label>
          <label>โหมดเวลา<select class="field" id="quakeSpeed">
            <option value="1">ความเร็วคลื่นจริง (Vp/Vs จริง)</option>
            <option value="12">เร่งเวลา 12x (ความเชื่อมั่นไล่ถึงยืนยันแล้วใน ~1 นาที)</option>
          </select></label>
        </div>
        <button class="btn primary" id="simulateQuakeBtn" data-requires-write style="align-self:flex-start;background:var(--status-critical);border-color:var(--status-critical);">${icon('warnTri')} จำลองแผ่นดินไหว</button>
      </div>
      <div class="panel col-12">
        <div class="panel-head"><h3>การแจ้งเตือนผ่าน Telegram</h3><span class="badge ${tg.enabled && tg.has_token ? 'good' : 'neutral'}" id="telegramStatusBadge">${tg.enabled && tg.has_token ? 'เปิดใช้งาน' : (tg.has_token ? 'ตั้งค่าไว้แต่ปิดใช้งาน' : 'ยังไม่ได้ตั้งค่า')}</span></div>
        <p class="panel-sub">เมื่อระบบตรวจพบเหตุการณ์ใหม่หรือยกระดับการแจ้งเตือน จะส่งข้อความจริงไปยัง Telegram ผ่าน Bot API ของคุณเอง — สร้างบอทได้ฟรีโดยแชทกับ <b>@BotFather</b> ใน Telegram พิมพ์ <code class="kbd">/newbot</code> เพื่อรับ Bot Token จากนั้นแชทกับบอทของคุณ 1 ครั้งแล้วเปิด <code class="kbd">https://api.telegram.org/bot&lt;TOKEN&gt;/getUpdates</code> เพื่อหา Chat ID ของคุณ</p>
        <div class="field-row">
          <label style="flex:1;min-width:220px;">Bot Token<input class="field" id="tgToken" style="width:100%;" value="${tg.bot_token_masked||''}" placeholder="วาง Token จาก @BotFather"></label>
          <label style="flex:1;min-width:160px;">Chat ID<input class="field" id="tgChatId" style="width:100%;" value="${tg.chat_id||''}" placeholder="เช่น 123456789"></label>
          <label style="justify-content:flex-end;"><span>&nbsp;</span><span style="display:flex;align-items:center;gap:6px;font-size:17px;color:var(--ink-primary);"><input type="checkbox" id="tgEnabled" ${tg.enabled?'checked':''}> เปิดใช้งาน</span></label>
        </div>
        <div class="field-row">
          <button class="btn primary" id="tgSaveBtn" data-requires-admin>บันทึกการตั้งค่า</button>
          <button class="btn" id="tgTestBtn" data-requires-admin>${icon('bell')} ส่งข้อความทดสอบ</button>
        </div>
      </div>
    </div>`;

  document.getElementById('testAlertBtn').addEventListener('click', async ()=>{
    const level = document.getElementById('testLevel').value;
    const region = document.getElementById('testRegion').value;
    try{
      const res = await api('/api/admin/test-alert', {method:'POST', body: JSON.stringify({level: Number(level), region})});
      await refreshAuditLog();
      showToast('ทดสอบสำเร็จ', res.message);
    }catch(e){ showToast('ทำรายการไม่สำเร็จ', e.message, false); }
  });

  document.getElementById('runBackupBtn').addEventListener('click', async ()=>{
    try{
      const res = await api('/api/admin/backup/run', {method:'POST'});
      document.getElementById('backupTs').textContent = new Date(res.ts).toLocaleString('th-TH');
      document.getElementById('backupSize').textContent = (res.size_bytes/1024).toFixed(0)+' KB';
      document.getElementById('backupPath').textContent = res.path.split('/').pop();
      await refreshAuditLog();
      showToast('สำรองข้อมูลสำเร็จ', `บันทึกไฟล์จริงขนาด ${(res.size_bytes/1024).toFixed(0)} KB ลงดิสก์แล้ว`);
    }catch(e){ showToast('สำรองข้อมูลไม่สำเร็จ', e.message, false); }
  });

  document.getElementById('simulateQuakeBtn').addEventListener('click', async ()=>{
    const epicenter_key = document.getElementById('quakeEpicenter').value;
    const magnitude = Number(document.getElementById('quakeMagnitude').value);
    const speed_multiplier = Number(document.getElementById('quakeSpeed').value);
    try{
      const res = await api('/api/admin/simulate-quake', {method:'POST', body: JSON.stringify({epicenter_key, magnitude, speed_multiplier})});
      await refreshAuditLog();
      showToast('เริ่มจำลองแผ่นดินไหวแล้ว', `คลื่นจะไปถึงสถานีแรกในราว ${res.eta_s} วินาที${speed_multiplier>1?' (เร่งเวลา '+speed_multiplier+'x)':''} ระบบจะตรวจจับและแจ้งเตือนอัตโนมัติ`);
    }catch(e){ showToast('จำลองไม่สำเร็จ', e.message, false); }
  });

  document.getElementById('tgSaveBtn').addEventListener('click', async ()=>{
    const bot_token = document.getElementById('tgToken').value.trim();
    const chat_id = document.getElementById('tgChatId').value.trim();
    const enabled = document.getElementById('tgEnabled').checked;
    try{
      await api('/api/admin/telegram', {method:'POST', body: JSON.stringify({bot_token, chat_id, enabled})});
      const fresh = await api('/api/admin/telegram');
      document.getElementById('tgToken').value = fresh.bot_token_masked || '';
      const badge = document.getElementById('telegramStatusBadge');
      badge.textContent = fresh.enabled && fresh.has_token ? 'เปิดใช้งาน' : (fresh.has_token ? 'ตั้งค่าไว้แต่ปิดใช้งาน' : 'ยังไม่ได้ตั้งค่า');
      badge.className = 'badge ' + (fresh.enabled && fresh.has_token ? 'good' : 'neutral');
      await refreshAuditLog();
      showToast('บันทึกการตั้งค่า Telegram แล้ว', enabled ? 'เปิดใช้งานการแจ้งเตือนผ่าน Telegram แล้ว' : 'บันทึกไว้แต่ยังไม่ได้เปิดใช้งาน');
    }catch(e){ showToast('บันทึกไม่สำเร็จ', e.message, false); }
  });

  document.getElementById('tgTestBtn').addEventListener('click', async ()=>{
    const btn = document.getElementById('tgTestBtn');
    btn.disabled = true;
    try{
      const res = await api('/api/admin/telegram/test', {method:'POST'});
      await refreshAuditLog();
      showToast(res.ok ? 'ส่งข้อความทดสอบสำเร็จ' : 'ส่งข้อความทดสอบไม่สำเร็จ', res.message, res.ok);
    }catch(e){ showToast('ทดสอบไม่สำเร็จ', e.message, false); }
    finally{ btn.disabled = false; }
  });

  applyRolePermissions();
}

function renderClassBars(cls){
  return cls.map(c=>`
    <div style="display:flex;align-items:center;gap:10px;">
      <span style="width:150px;font-size:15.5px;color:${c.hi?'var(--ink-primary)':'var(--ink-secondary)'};font-weight:${c.hi?600:400};">${c.label}</span>
      <div style="flex:1;background:var(--surface-2);border-radius:6px;height:14px;overflow:hidden;">
        <div style="width:${c.pct}%;height:100%;background:${c.hi?'var(--accent)':'var(--ink-faint)'};border-radius:6px;"></div>
      </div>
      <span class="tabular" style="width:40px;text-align:right;font-size:15.5px;color:var(--ink-secondary);">${c.pct}%</span>
    </div>`).join('');
}

