// View 2: early warning. A classic script (not a module): every js/ file shares one global scope and index.html loads them in order.

/* ============================= VIEW 2: EARLY WARNING ============================= */
async function renderWarning(){
  const levels = await api('/api/levels');
  const currentLv = LATEST_SNAPSHOT?.active_event?.level;
  const rows = levels.map(l=>`
    <div class="ladder-row ${l.lv===currentLv?'current':''}">
      <div class="ladder-chip" style="background:${l.color};">
        <div class="lv">Lv.${l.lv}</div>
        <div class="lvname">${l.name}</div>
      </div>
      <div class="ladder-body">
        <div class="ladder-field"><span class="k">ความรุนแรงที่คาด (Predicted MMI)</span><span class="v strong tabular">${l.mmi_roman}</span></div>
        <div class="ladder-field"><span class="k">ลักษณะโดยเปรียบเทียบ</span><span class="v">${l.severity_desc}</span></div>
        <div class="ladder-field"><span class="k">ขนาดอ้างอิง (ไม่ใช่เกณฑ์)</span><span class="v">${l.mag_ref}</span></div>
        <div class="ladder-field"><span class="k">PGA อ้างอิง</span><span class="v strong tabular">${l.pga_min}${l.pga_max? '–'+l.pga_max : '+'} Gal</span></div>
        <div class="ladder-field"><span class="k">ความเชื่อมั่น Edge AI ขั้นต่ำ</span><span class="v strong tabular">${l.ai_conf}</span></div>
        <div class="ladder-field"><span class="k">สถานียืนยัน (ระดับความเชื่อมั่น)</span><span class="v strong tabular">${l.nodes_min}</span></div>
        <div class="ladder-field" style="grid-column:1/-1;"><span class="k">ช่องทางแจ้งเตือน</span><span class="v">${l.channels}</span></div>
        <div class="ladder-msg"><b>ข้อความตัวอย่าง:</b> ${l.message}<br><span style="color:var(--ink-muted);font-size:15px;">🔊 ${l.siren}</span></div>
      </div>
    </div>`).join('');

  document.getElementById('view-warning').innerHTML = `
    <div class="view-head">
      <h2>ระบบเตือนภัยล่วงหน้า 6 ระดับ</h2>
      <p class="desc"><b>เกณฑ์หลักคือความรุนแรงที่คาดว่าจะเกิด ณ ตำแหน่งผู้ใช้ (Predicted MMI)</b> ไม่ใช่ขนาดแผ่นดินไหว (Magnitude) เพียงอย่างเดียว เพราะแผ่นดินไหวเหตุการณ์เดียวกันให้ความรุนแรงต่างกันในแต่ละพื้นที่ตามระยะทาง ความลึก และสภาพพื้นที่ (อ้างอิงแนวทาง USGS: Magnitude vs. Intensity และมาตรา Modified Mercalli) ระดับที่ประกาศคือระดับที่ตรงกับความรุนแรงที่ประเมินได้ทันที ไม่ต้องรอสถานียืนยันครบ ส่วนจำนวนสถานีที่ยืนยันร่วมกัน (Multi-node) เป็นตัวบ่งชี้ <b>ความเชื่อมั่น</b> ของการประเมินนั้น ไม่ใช่ตัวกำหนดความรุนแรง</p>
    </div>
    <div class="ladder">${rows}</div>
    <div class="grid grid-2">
      <div class="panel">
        <div class="panel-head"><h3>ช่องทางแจ้งเตือนตามระดับ</h3></div>
        <div class="scroll-x">
          <table class="data-table">
            <thead><tr><th>ช่องทาง</th><th>Lv.1</th><th>Lv.2</th><th>Lv.3</th><th>Lv.4</th><th>Lv.5</th><th>Lv.6</th></tr></thead>
            <tbody>
              <tr><td class="strong">แดชบอร์ด</td><td>●</td><td>●</td><td>●</td><td>●</td><td>●</td><td>●</td></tr>
              <tr><td class="strong">App Push / Vibrate</td><td>—</td><td>●</td><td>●</td><td>●</td><td>●</td><td>●</td></tr>
              <tr><td class="strong">SMS / LINE Alert</td><td>—</td><td>—</td><td>—</td><td>●</td><td>●</td><td>●</td></tr>
              <tr><td class="strong">Cell Broadcast</td><td>—</td><td>—</td><td>—</td><td>—</td><td>●</td><td>●</td></tr>
              <tr><td class="strong">ไซเรนพื้นที่ / แห่งชาติ</td><td>—</td><td>—</td><td>—</td><td>—</td><td>●</td><td>●</td></tr>
              <tr><td class="strong">โทรทัศน์ / วิทยุ</td><td>—</td><td>—</td><td>—</td><td>—</td><td>●</td><td>●</td></tr>
              <tr><td class="strong">ประสานหน่วยงานฉุกเฉิน</td><td>—</td><td>—</td><td>—</td><td>—</td><td>—</td><td>●</td></tr>
            </tbody>
          </table>
        </div>
      </div>
      <div class="panel">
        <div class="panel-head"><h3>รูปแบบการแจ้งเตือนแต่ละระดับ</h3></div>
        <ul class="list-clean">
          <li class="safety-item">${icon('bell')}<span><b>ระดับ 1:</b> ไม่มีเสียง แสดงสถานะสีเขียว</span></li>
          <li class="safety-item">${icon('bell')}<span><b>ระดับ 2:</b> เสียงแจ้งเตือนสั้น 1 ครั้ง พร้อมข้อความข้อมูล</span></li>
          <li class="safety-item">${icon('bell')}<span><b>ระดับ 3:</b> เสียง 2 ครั้งทุก 10 วินาที พร้อมสั่นโทรศัพท์</span></li>
          <li class="safety-item">${icon('bell')}<span><b>ระดับ 4:</b> เสียง 3 จังหวะทุก 5 วินาที พร้อมเสียงพูด "เตรียมหมอบ กำบัง ยึดจับ"</span></li>
          <li class="safety-item">${icon('bell')}<span><b>ระดับ 5:</b> เสียงสลับเร็ว พร้อมหน้าจอเต็มและนับเวลาคลื่นถึง</span></li>
          <li class="safety-item">${icon('bell')}<span><b>ระดับ 6:</b> ไซเรนสลับเสียงพูดต่อเนื่อง จนผู้ใช้กดยืนยันรับทราบ</span></li>
        </ul>
      </div>
    </div>
    <div class="panel" style="margin-top:14px;">
      <div class="panel-head"><h3>เงื่อนไขพิเศษ: การเตือนสึนามิ</h3></div>
      <p class="panel-sub">"เตือนสึนามิ" เป็นสถานะแยกที่สามารถยกระดับทับทั้ง 6 ระดับได้ หากศูนย์กลางแผ่นดินไหวอยู่ในทะเลตื้นบริเวณอันดามันและมีขนาดใหญ่พอ (ตามแนวทาง NOAA/NWS) — เมื่อแรงสั่นหยุด ผู้ที่อยู่ในเขตชายฝั่งควรอพยพขึ้นที่สูงหรือเข้าแผ่นดินทันที โดยไม่ต้องรอการแจ้งเตือนเพิ่มเติม และไม่ควรกลับจนกว่าจะมีประกาศปลอดภัยจากหน่วยงานทางการ (การประเมินนี้เป็นฮิวริสติกอย่างง่ายของระบบสาธิต ไม่ใช่ระบบเตือนภัยสึนามิทางการ)</p>
    </div>`;
}

