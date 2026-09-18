export async function fetchCameras() {
  try {
    const res = await fetch('/api/cameras');
    if (res.ok) {
      const data = await res.json();
      if (data.items && data.items.length) return data.items;
    }
  } catch {}
  const res = await fetch('/cameras_bkk.json');
  const data = await res.json();
  return data.items || [];
}

export async function fetchLongdoCameras() {
  try {
    const res = await fetch('/api/cameras/longdo');
    if (res.ok) {
      const data = await res.json();
      if (data.items && data.items.length) return data.items;
    }
  } catch {}
  try {
    const res = await fetch('https://traffic.longdo.com/camera.json');
    if (res.ok) {
      const data = await res.json();
      const items = data.item || [];
      if (items.length > 0) {
        return items.map((it) => {
          const title = (it.title || '').trim();
          const m = title.match(/^\(([^)]+)\)/);
          const prov = m ? m[1].replace('จ.', '').trim() : '';
          return {
            camid: it.camid || '',
            title: title,
            short_title: title.replace(/^\([^)]+\)\s*/, ''),
            province: prov || 'กรุงเทพมหานคร',
            organization: it.organization || 'Longdo Traffic',
            hls_url: it.hls_url || '',
            vdourl: it.vdourl || '',
            imgurl: it.imgurl || '',
            latitude: parseFloat(it.latitude) || 0,
            longitude: parseFloat(it.longitude) || 0,
            geocode: it.geocode || '',
            lastupdate: it.lastupdate || '',
          };
        });
      }
    }
  } catch {}
  return fetchCameras();
}

export async function switchAICamera(cam) {
  const params = new URLSearchParams({
    camid: cam.camid,
    stream_url: cam.hls_url || cam.vdourl || '',
    title: cam.short_title || cam.title || '',
    province: cam.province || '',
  });
  return fetch(`/api/ai/switch_camera?${params}`, { method: 'POST' });
}

export async function fetchAIStats() {
  const res = await fetch('/api/ai/stats');
  if (!res.ok) throw new Error('stats');
  return res.json();
}

// { range: '24h'|'7d'|'30d' } or { date: 'YYYY-MM-DD' } (hourly for that day)
export async function fetchAIHistory({ range = '24h', date } = {}) {
  const params = date ? `date=${date}` : `range=${range}`;
  const res = await fetch(`/api/ai/history?${params}`);
  if (!res.ok) throw new Error('history');
  return res.json();
}

export async function fetchCountCameras() {
  const res = await fetch('/api/count/cameras');
  if (!res.ok) throw new Error('count');
  return res.json();
}

export async function fetchSurveyRanking() {
  const res = await fetch('/api/survey/ranking');
  if (!res.ok) throw new Error('ranking');
  return res.json();
}

export async function fetchIncidents() {
  const res = await fetch('/api/incidents');
  if (!res.ok) throw new Error('incidents');
  return res.json();
}

export async function setCountCameras(camids) {
  const res = await fetch('/api/count/cameras', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ camids }),
  });
  if (!res.ok) throw new Error('count');
  return res.json();
}

export function setAIFps(fps) {
  return fetch(`/api/ai/set_fps?fps=${fps}`, { method: 'POST' });
}

export function setAIConf(conf) {
  return fetch(`/api/ai/set_conf?conf=${conf}`, { method: 'POST' });
}

export function setAINightMode(enabled) {
  return fetch(`/api/ai/set_night_mode?enabled=${enabled}`, { method: 'POST' });
}

export function aiStreamUrl(camid) {
  return `/api/ai/stream?camid=${encodeURIComponent(camid)}&t=${Date.now()}`;
}

export async function fetchTrafficSummary(top = 8) {
  const res = await fetch(`/api/traffic/summary?top=${top}`);
  if (!res.ok) throw new Error('summary');
  return res.json();
}

export async function fetchRoadCameras(name, maxKm = 0.25) {
  const res = await fetch(`/api/traffic/road_cameras?name=${encodeURIComponent(name)}&max_km=${maxKm}`);
  if (!res.ok) throw new Error('road_cameras');
  return (await res.json()).items || [];
}

export async function sendChat(messages) {
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages }),
  });
  if (!res.ok) throw new Error('chat');
  return res.json();
}

// Camera incidents from the last `hours`, including ones already cleared
export async function fetchIncidentHistory(hours = 24) {
  const res = await fetch(`/api/incidents/history?hours=${hours}`);
  if (!res.ok) throw new Error('incident_history');
  return (await res.json()).items || [];
}

// ---- Water outlook (ThaiWater / HII + BMA traffic centre)
export async function fetchWaterSummary() {
  const res = await fetch('/api/water/summary');
  if (!res.ok) throw new Error('water_summary');
  return res.json();
}

export async function fetchWaterForecast(stationId) {
  const res = await fetch(`/api/water/forecast?station=${encodeURIComponent(stationId)}`);
  if (!res.ok) throw new Error('water_forecast');
  return res.json();
}

export async function fetchBMAEvents({ kind, hours = 24, limit = 60 } = {}) {
  const params = new URLSearchParams({ hours, limit });
  if (kind) params.set('kind', kind);
  const res = await fetch(`/api/water/bma_events?${params}`);
  if (!res.ok) throw new Error('bma_events');
  return res.json();
}

// ---- BMA Traffic & YOLO Vehicle Counting
export async function fetchBmaCameras() {
  const res = await fetch('/api/bma/cameras');
  if (!res.ok) throw new Error('bma_cameras');
  return res.json();
}

export async function fetchBmaAnalytics() {
  const res = await fetch('/api/bma/analytics');
  if (!res.ok) throw new Error('bma_analytics');
  return res.json();
}

export async function fetchBmaScanStatus() {
  const res = await fetch('/api/bma/scan/status');
  if (!res.ok) throw new Error('bma_scan_status');
  return res.json();
}

export async function triggerBmaScan() {
  const res = await fetch('/api/bma/scan', { method: 'POST' });
  if (!res.ok) throw new Error('bma_scan');
  return res.json();
}

export function getBmaSnapshotUrl(camid, live = false, t = null) {
  const params = new URLSearchParams();
  if (live) params.set('live', '1');
  if (t) params.set('t', String(t));
  const qs = params.toString();
  return `/api/bma/snapshot/${encodeURIComponent(camid)}${qs ? `?${qs}` : ''}`;
}

export function getBmaStreamUrl(camid, t = null) {
  return `/api/bma/stream/${encodeURIComponent(camid)}?t=${t || Date.now()}`;
}

export async function fetchBmaLiveAnalysis(camid) {
  const res = await fetch(`/api/bma/live_analysis/${encodeURIComponent(camid)}`);
  if (!res.ok) throw new Error('bma_live_analysis');
  return res.json();
}

export async function fetchBmaCycle() {
  const res = await fetch('/api/bma/cycle');
  if (!res.ok) throw new Error('bma_cycle');
  return res.json();
}

export async function fetchBmaComparison(period = 'day') {
  const res = await fetch(`/api/bma/comparison?period=${encodeURIComponent(period)}`);
  if (!res.ok) throw new Error('bma_comparison');
  return res.json();
}

export async function fetchBmaDriveDStatus() {
  const res = await fetch('/api/bma/drive_d_status');
  if (!res.ok) throw new Error('bma_drive_d_status');
  return res.json();
}



export async function fetchRscSummary() {
  const res = await fetch('/api/rsc/summary');
  if (!res.ok) throw new Error('rsc summary failed');
  return res.json();
}

export async function fetchRscCameraRisk({ limit, district } = {}) {
  const q = new URLSearchParams();
  if (limit) q.set('limit', limit);
  if (district) q.set('district', district);
  const res = await fetch(`/api/rsc/camera_risk?${q}`);
  if (!res.ok) throw new Error('rsc risk failed');
  return res.json();
}

export async function fetchRscPoints(camid, radius) {
  const q = new URLSearchParams({ camid });
  if (radius) q.set('radius', radius);
  const res = await fetch(`/api/rsc/points?${q}`);
  if (!res.ok) throw new Error('rsc points failed');
  return res.json();
}

export async function triggerRscRebuild() {
  const res = await fetch('/api/rsc/rebuild', { method: 'POST' });
  return res.json();
}

export async function fetchViolations({ hours = 24, camid, kind, limit = 30 } = {}) {
  const q = new URLSearchParams({ hours, limit });
  if (camid) q.set('camid', camid);
  if (kind) q.set('kind', kind);
  const res = await fetch(`/api/ai/violations?${q}`);
  if (!res.ok) throw new Error('violations failed');
  return res.json();
}

export async function fetchViolationStatus(camid) {
  const q = camid ? `?camid=${encodeURIComponent(camid)}` : '';
  const res = await fetch(`/api/ai/violations/status${q}`);
  if (!res.ok) throw new Error('violation status failed');
  return res.json();
}

export async function fetchAnalytics(refresh = false) {
  const res = await fetch(`/api/analytics/summary${refresh ? '?refresh=true' : ''}`);
  if (!res.ok) throw new Error('analytics failed');
  return res.json();
}

export async function fetchOnlineCount() {
  const res = await fetch('/api/telemetry/online');
  if (!res.ok) throw new Error('online count failed');
  const d = await res.json();
  return d.online;
}

// ---- manual-vs-AI accuracy checks (live page)
export async function fetchAIAccuracy(limit = 50) {
  const res = await fetch(`/api/ai/accuracy?limit=${limit}`);
  if (!res.ok) throw new Error('accuracy');
  return res.json();
}

// { manual_count, ai_count?, camid?, title?, duration_s?, note? } — ai_count defaults to the live counter
export async function addAIAccuracy(payload) {
  const res = await fetch('/api/ai/accuracy', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || 'accuracy');
  return res.json();
}

export async function deleteAIAccuracy(id) {
  const res = await fetch(`/api/ai/accuracy/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('accuracy');
  return res.json();
}

export function resetAIPassed() {
  return fetch('/api/ai/reset_passed', { method: 'POST' });
}
