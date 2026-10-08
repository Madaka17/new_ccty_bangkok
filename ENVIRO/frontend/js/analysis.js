// View 4: data analysis. A classic script (not a module): every js/ file shares one global scope and index.html loads them in order.

/* ============================= VIEW 4: DATA ANALYSIS ============================= */
async function renderAnalysis(){
  const [stalta, fft, corr, perf, risk] = await Promise.all([
    api('/api/analysis/stalta'), api('/api/analysis/fft'), api('/api/analysis/correlation'),
    api('/api/analysis/model-performance'), api('/api/analysis/risk'),
  ]);
  const wf = await api('/api/analysis/waveform');

  const W=600,H=110;
  const series = stalta.series;
  const staltaMax = Math.max(...series, 0.01);
  const staltaIdx = series.indexOf(Math.max(...series));
  const domainMax = Math.max(8, staltaMax * 1.1);
  const staltaPath = pathFromSeries(series, W, H-8, [0, domainMax]);
  const threshY = H-8 - (stalta.threshold/domainMax)*(H-8);
  const trigX = (staltaIdx/(series.length-1))*W;
  const trigY = H-8 - (staltaMax/domainMax)*(H-8);

  const fftMax = Math.max(...fft.bins.map(d=>d.a), 0.01);
  const fw = W/fft.bins.length;
  const fftBars = fft.bins.map((d,i)=>{
    const bh = (d.a/fftMax)*(H-20);
    const isPeak = Math.abs(d.f - fft.dominant_hz) < 0.3;
    return `<rect class="hoverable" data-tip="<div class='tt'>${d.f.toFixed(1)} Hz</div><div class='ts'>แอมพลิจูด ${d.a.toFixed(2)}</div>" x="${(i*fw+1).toFixed(1)}" y="${(H-8-bh).toFixed(1)}" width="${(fw-1.5).toFixed(1)}" height="${Math.max(0,bh).toFixed(1)}" rx="1.5" fill="${isPeak?'var(--accent-strong)':'var(--series-usgs)'}" opacity="${isPeak?1:0.55}"/>`;
  }).join('');

  const nCorr = corr.stations.length;
  const cellSize = 46;
  const heat = [];
  for(let i=0;i<nCorr;i++) for(let j=0;j<nCorr;j++){
    const v = corr.matrix[i][j];
    heat.push(`<g class="hoverable" data-tip="<div class='tt'>${corr.stations[i]} × ${corr.stations[j]}</div><div class='ts'>สหสัมพันธ์ ${v.toFixed(2)}</div>">
      <rect x="${j*cellSize}" y="${i*cellSize}" width="${cellSize-3}" height="${cellSize-3}" rx="4" fill="${seqColor((v+1)/2)}"/>
      <text x="${j*cellSize+(cellSize-3)/2}" y="${i*cellSize+(cellSize-3)/2+4}" text-anchor="middle" font-size="11" fill="${v>0.5?'#fff':'var(--ink-muted)'}">${v.toFixed(2)}</text>
    </g>`);
  }
  const corrLabelsTop = corr.stations.map((n,i)=>`<text x="${i*cellSize+(cellSize-3)/2}" y="-8" text-anchor="middle" font-size="9">${n}</text>`).join('');
  const corrLabelsLeft = corr.stations.map((n,i)=>`<text x="-8" y="${i*cellSize+(cellSize-3)/2+4}" text-anchor="end" font-size="9">${n}</text>`).join('');

  const riskMax = 100;
  const riskRows = risk.map(r=>`
    <div style="display:flex;align-items:center;gap:10px;">
      <span style="width:150px;font-size:15.5px;color:var(--ink-secondary);">${r.region}</span>
      <div style="flex:1;background:var(--surface-2);border-radius:6px;height:15px;">
        <div class="hoverable" data-tip="<div class='tt'>${r.region}</div><div class='ts'>คะแนนความเสี่ยง ${r.score}/100</div>" style="width:${(r.score/riskMax)*100}%;height:100%;background:${seqColor(r.score/100)};border-radius:6px;"></div>
      </div>
      <span class="tabular" style="width:32px;text-align:right;font-size:15.5px;color:var(--ink-primary);">${r.score}</span>
    </div>`).join('');

  document.getElementById('view-analysis').innerHTML = `
    <div class="view-head">
      <h2>วิเคราะห์ข้อมูลเชิงลึก</h2>
      <p class="desc">STA/LTA, รูปคลื่น, การแปลงฟูริเยร์ (FFT), สหสัมพันธ์ระหว่างสถานี (Multi-node correlation), ประสิทธิภาพโมเดล และการประเมินความเสี่ยงแผ่นดินไหวรายภูมิภาค — คำนวณจริงด้วย NumPy ฝั่งเซิร์ฟเวอร์จากบัฟเฟอร์สัญญาณสด</p>
    </div>
    <div class="grid grid-2">
      <div class="panel">
        <div class="panel-head"><h3>อัตราส่วน STA/LTA</h3><span class="hint">สถานี ${stalta.station_id} · เกณฑ์ทริกเกอร์ = ${stalta.threshold}</span></div>
        <svg class="chart" viewBox="0 0 ${W} ${H+16}" preserveAspectRatio="none" style="width:100%;height:${H+16}px;">
          <line class="grid-line" x1="0" y1="${threshY.toFixed(1)}" x2="${W}" y2="${threshY.toFixed(1)}" stroke-width="1" stroke-dasharray="4 4"/>
          <text x="${W-4}" y="${(threshY-4).toFixed(1)}" text-anchor="end" font-size="9">threshold ${stalta.threshold}</text>
          <path d="${staltaPath}" fill="none" stroke="var(--series-enviro)" stroke-width="1.6"/>
          ${staltaMax>stalta.threshold?`<circle class="hoverable" data-tip="<div class='tt'>จุดตรวจจับ (Trigger)</div><div class='ts'>STA/LTA = ${staltaMax.toFixed(2)}</div>" cx="${trigX.toFixed(1)}" cy="${trigY.toFixed(1)}" r="4.5" fill="var(--status-critical)" stroke="#fff" stroke-width="1.2"/>`:''}
          <text x="4" y="${H+13}">0 วินาที</text><text x="${W-4}" y="${H+13}" text-anchor="end">${(series.length/20).toFixed(0)} วินาที</text>
        </svg>
      </div>
      <div class="panel">
        <div class="panel-head"><h3>รูปคลื่นดิบ (Raw Waveform)</h3><span class="hint">สถานี ${wf.station_id} · แกน E–W</span></div>
        ${waveSvg(wf.axes.ew,'var(--series-enviro)',110,'แอมพลิจูด (g)')}
      </div>
      <div class="panel">
        <div class="panel-head"><h3>สเปกตรัมความถี่ (FFT)</h3><span class="hint">ความถี่เด่น ${fft.dominant_hz.toFixed(1)} Hz</span></div>
        <svg class="chart" viewBox="0 0 ${W} ${H+16}" preserveAspectRatio="none" style="width:100%;height:${H+16}px;">
          ${fftBars}
          <text x="4" y="${H+13}">0 Hz</text><text x="${W/2}" y="${H+13}" text-anchor="middle">10 Hz</text><text x="${W-4}" y="${H+13}" text-anchor="end">20 Hz</text>
        </svg>
      </div>
      <div class="panel">
        <div class="panel-head"><h3>สหสัมพันธ์ระหว่างสถานี (Multi-node Correlation)</h3></div>
        <div class="scroll-x" style="padding:24px 0 4px 60px;">
          <svg class="chart" width="${nCorr*cellSize}" height="${nCorr*cellSize}" viewBox="-60 -22 ${nCorr*cellSize+60} ${nCorr*cellSize+22}">
            ${corrLabelsTop}${corrLabelsLeft}${heat.join('')}
          </svg>
        </div>
      </div>
    </div>
    <div class="grid grid-12">
      <div class="panel col-6">
        <div class="panel-head"><h3>ประสิทธิภาพโมเดล Edge AI</h3><span class="badge good">${perf.version}</span></div>
        <div class="grid grid-4" style="gap:10px;">
          <div class="stat-tile" style="padding:12px;"><span class="label">Precision</span><span class="value tabular" style="font-size:24px;">${perf.precision}%</span></div>
          <div class="stat-tile" style="padding:12px;"><span class="label">Recall</span><span class="value tabular" style="font-size:24px;">${perf.recall}%</span></div>
          <div class="stat-tile" style="padding:12px;"><span class="label">F1-score</span><span class="value tabular" style="font-size:24px;">${perf.f1}%</span></div>
          <div class="stat-tile" style="padding:12px;"><span class="label">Accuracy</span><span class="value tabular" style="font-size:24px;">${perf.accuracy}%</span></div>
        </div>
        <table class="data-table" style="margin-top:4px;">
          <thead><tr><th></th><th>ทำนาย: แผ่นดินไหว</th><th>ทำนาย: ไม่ใช่</th></tr></thead>
          <tbody>
            <tr><td class="strong">จริง: แผ่นดินไหว</td><td class="tabular" style="color:var(--status-good);">${perf.tp.toLocaleString()}</td><td class="tabular" style="color:var(--status-warn);">${perf.fn.toLocaleString()}</td></tr>
            <tr><td class="strong">จริง: ไม่ใช่</td><td class="tabular" style="color:var(--status-warn);">${perf.fp.toLocaleString()}</td><td class="tabular" style="color:var(--status-good);">${perf.tn.toLocaleString()}</td></tr>
          </tbody>
        </table>
      </div>
      <div class="panel col-6">
        <div class="panel-head"><h3>การประเมินความเสี่ยงแผ่นดินไหวรายภูมิภาค (Seismic Risk Score)</h3></div>
        <p class="panel-sub">รวมความใกล้รอยเลื่อน ความถี่การเกิดเหตุ และความหนาแน่นประชากรที่เสี่ยงภัย · เต็ม 100</p>
        <div style="display:flex;flex-direction:column;gap:9px;">${riskRows}</div>
      </div>
    </div>`;
}

