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

export async function fetchWindGrid() {
  const res = await fetch('/api/weather/wind');
  if (!res.ok) throw new Error('wind');
  return res.json();
}

// Per-road flood risk: rain + canal level + road sensors + traffic, scored and ranked
export async function fetchRoadRisk({ level = null, province = null, q = null, measured = null, limit = 400 } = {}) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (level) params.set('level', level);
  if (province) params.set('province', province);
  if (q) params.set('q', q);
  if (measured != null) params.set('measured', String(measured));
  const res = await fetch(`/api/roads/risk?${params}`);
  if (!res.ok) throw new Error('road_risk');
  return res.json();
}

// Road flooding: BMA drainage sensors (weather.bangkok.go.th), depth over the road in cm
export async function fetchFloodStatus() {
  const res = await fetch('/api/flood/status');
  if (!res.ok) throw new Error('flood_status');
  return res.json();
}

export async function fetchFloodStations({ status = null, district = null, kind = null, limit = 400 } = {}) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (status) params.set('status', status);
  if (district) params.set('district', district);
  if (kind) params.set('kind', kind);
  const res = await fetch(`/api/flood/stations?${params}`);
  if (!res.ok) throw new Error('flood_stations');
  return res.json();
}

export async function fetchFloodAnalysis() {
  const res = await fetch('/api/flood/analysis');
  if (!res.ok) throw new Error('flood_analysis');
  return res.json();
}

export async function fetchFloodRoads(limit = 60) {
  const res = await fetch(`/api/flood/roads?limit=${limit}`);
  if (!res.ok) throw new Error('flood_roads');
  return res.json();
}

// Flood complaints residents filed on Traffy Fondue in the last few hours (flood_feeds.py)
// Flooded-road reports on the Longdo Traffic feed (iTIC / FM91), newest first (incident_service.floods)
export async function fetchLongdoFloods() {
  const res = await fetch('/api/flood/longdo');
  if (!res.ok) throw new Error('longdo_floods');
  return res.json();
}

// Traffy flood reports today vs yesterday / this week vs last week (traffy_history.py)
export async function fetchTraffyHistory() {
  const res = await fetch('/api/traffy/history');
  if (!res.ok) throw new Error('traffy_history');
  return res.json();
}

// Weather this hour at a spot (weather_now.py, MET Norway); no lat/lng = Bangkok centre
export async function fetchWeatherNow(lat, lng) {
  const q = lat != null && lng != null ? `?lat=${lat}&lng=${lng}` : '';
  const res = await fetch(`/api/weather/now${q}`);
  if (!res.ok) throw new Error('weather_now');
  return res.json();
}

export async function fetchFloodReports() {
  const res = await fetch('/api/flood/reports');
  if (!res.ok) throw new Error('flood_reports');
  return res.json();
}

// Flood analyst agent (flood_agent.py): latest situation report, level history, whether a run is going
export async function fetchFloodAgent() {
  const res = await fetch('/api/flood/agent');
  if (!res.ok) throw new Error('flood_agent');
  return res.json();
}

// Run the agent now; operator only (403 from anywhere else). `question` is answered in report.answer
export async function runFloodAgent(question = '') {
  const res = await fetch('/api/flood/agent/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  });
  if (res.status === 403) throw new Error('forbidden');
  if (!res.ok) throw new Error('flood_agent_run');
  return res.json();
}

// Water Forecast analyst (water_agent.py): AI outlook, three waters, measures and public guide
export async function fetchWaterAgent() {
  const res = await fetch('/api/water/agent');
  if (!res.ok) throw new Error('water_agent');
  return res.json();
}

export async function runWaterAgent() {
  const res = await fetch('/api/water/agent/run', { method: 'POST' });
  if (res.status === 403) throw new Error('forbidden');
  if (!res.ok) throw new Error('water_agent_run');
  return res.json();
}

// BMA traffic-risk analysis (riskbkk_agent.py): AI report + the per-district / per-hour numbers
export async function fetchRiskAnalysis() {
  const res = await fetch('/api/riskbkk/analysis');
  if (!res.ok) throw new Error('riskbkk_analysis');
  return res.json();
}

// Re-run it now; operator only (403 from anywhere else)
export async function runRiskAnalysis() {
  const res = await fetch('/api/riskbkk/analysis/run', { method: 'POST' });
  if (res.status === 403) throw new Error('forbidden');
  if (!res.ok) throw new Error('riskbkk_analysis_run');
  return res.json();
}

// AI reading of the Traffy Fondue flood reports of the last 6 h (traffy_agent.py): report + numbers
export async function fetchTraffyAnalysis() {
  const res = await fetch('/api/traffy/analysis');
  if (!res.ok) throw new Error('traffy_analysis');
  return res.json();
}

// Re-run it now; operator only (403 from anywhere else)
export async function runTraffyAnalysis() {
  const res = await fetch('/api/traffy/analysis/run', { method: 'POST' });
  if (res.status === 403) throw new Error('forbidden');
  if (!res.ok) throw new Error('traffy_analysis_run');
  return res.json();
}

// TMD heavy-rain / storm warnings; `active` = issued in the last two days (flood_feeds.py)
export async function fetchWeatherWarnings() {
  const res = await fetch('/api/weather/warnings');
  if (!res.ok) throw new Error('weather_warnings');
  return res.json();
}

export async function fetchAirStations() {
  const res = await fetch('/api/air/stations');
  if (!res.ok) throw new Error('air');
  return res.json();
}

export async function fetchTrafficGuidance() {
  const res = await fetch('/api/traffic/guidance');
  if (!res.ok) throw new Error('guidance');
  return res.json();
}

export async function fetchHelmetStatus() {
  const res = await fetch('/api/helmet/status');
  if (!res.ok) throw new Error('helmet_status');
  return res.json();
}

export async function fetchHelmetRecent({ hours = 24, verdict = null, camid = null, limit = 200 } = {}) {
  const params = new URLSearchParams({ hours: String(hours), limit: String(limit) });
  if (verdict) params.set('verdict', verdict);
  if (camid) params.set('camid', camid);
  const res = await fetch(`/api/helmet/recent?${params}`);
  if (!res.ok) throw new Error('helmet_recent');
  return res.json();
}

export async function fetchHelmetCameras() {
  const res = await fetch('/api/helmet/cameras');
  if (!res.ok) throw new Error('helmet_cameras');
  return res.json();
}

export async function triggerHelmetCheck(camid) {
  const res = await fetch(`/api/helmet/check/${encodeURIComponent(camid)}`, { method: 'POST' });
  if (!res.ok) throw new Error('helmet_check');
  return res.json();
}

export async function reanalyseHelmet(hid, agent = 'cloud') {
  const res = await fetch(`/api/helmet/${encodeURIComponent(hid)}/reanalyse?agent=${agent}`, { method: 'POST' });
  if (!res.ok) throw new Error('helmet_reanalyse');
  return res.json();
}

export async function reanalyseHelmetPending(agent = 'cloud', limit = 40) {
  const res = await fetch(`/api/helmet/reanalyse_pending?agent=${agent}&limit=${limit}`, { method: 'POST' });
  if (!res.ok) throw new Error('helmet_reanalyse_pending');
  return res.json();
}

// Wrong-way patrol (all BMA cameras): same shape as the helmet API plus the learned lane-direction field
export async function fetchWrongWayStatus() {
  const res = await fetch('/api/wrongway/status');
  if (!res.ok) throw new Error('wrongway_status');
  return res.json();
}

export async function fetchWrongWayRecent({ hours = 24, verdict = null, camid = null, limit = 200 } = {}) {
  const params = new URLSearchParams({ hours: String(hours), limit: String(limit) });
  if (verdict) params.set('verdict', verdict);
  if (camid) params.set('camid', camid);
  const res = await fetch(`/api/wrongway/recent?${params}`);
  if (!res.ok) throw new Error('wrongway_recent');
  return res.json();
}

export async function fetchWrongWayCameras() {
  const res = await fetch('/api/wrongway/cameras');
  if (!res.ok) throw new Error('wrongway_cameras');
  return res.json();
}

export async function fetchWrongWayField(camid) {
  const res = await fetch(`/api/wrongway/field/${encodeURIComponent(camid)}`);
  if (!res.ok) throw new Error('wrongway_field');
  return res.json();
}

export async function triggerWrongWayCheck(camid) {
  const res = await fetch(`/api/wrongway/check/${encodeURIComponent(camid)}`, { method: 'POST' });
  if (!res.ok) throw new Error('wrongway_check');
  return res.json();
}

export async function reanalyseWrongWay(wid, agent = 'cloud') {
  const res = await fetch(`/api/wrongway/${encodeURIComponent(wid)}/reanalyse?agent=${agent}`, { method: 'POST' });
  if (!res.ok) throw new Error('wrongway_reanalyse');
  return res.json();
}

export async function reanalyseWrongWayPending(agent = 'cloud', limit = 40) {
  const res = await fetch(`/api/wrongway/reanalyse_pending?agent=${agent}&limit=${limit}`, { method: 'POST' });
  if (!res.ok) throw new Error('wrongway_reanalyse_pending');
  return res.json();
}

export async function dismissWrongWay(wid) {
  const res = await fetch(`/api/wrongway/${encodeURIComponent(wid)}/dismiss`, { method: 'POST' });
  if (!res.ok) throw new Error('wrongway_dismiss');
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
  if (res.status === 429) throw new Error('rate_limited');
  if (res.status === 413) throw new Error('too_long');
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

// Every metro water / rain gauge and the upstream dams as map points (Water Forecast station map)
export async function fetchWaterMap() {
  const res = await fetch('/api/water/map');
  if (!res.ok) throw new Error('water_map');
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

export async function fetchVisitorStats() {
  const res = await fetch('/api/telemetry/stats');
  if (!res.ok) throw new Error('visitor stats failed');
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

// ---------------------------------------------------------------- Web Push alerts (alert_service.py)
export async function fetchAlertStatus(endpoint) {
  const params = endpoint ? `?${new URLSearchParams({ endpoint })}` : '';
  const res = await fetch(`/api/alerts/status${params}`);
  if (!res.ok) throw new Error('alerts_status');
  return res.json();
}

export async function fetchAlertRecent(limit = 50) {
  const res = await fetch(`/api/alerts/recent?limit=${limit}`);
  if (!res.ok) throw new Error('alerts_recent');
  return res.json();
}

// Subscribing and the test push are operator-only (access_guard): a 403 means "not on the team network"
async function postAlert(path, body) {
  const res = await fetch(`/api/alerts/${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (res.status === 403) throw new Error('forbidden');
  if (!res.ok) throw new Error(`alerts_${path}`);
  return res.json();
}

export const subscribeAlerts = (subscription, topics, label) => postAlert('subscribe', { subscription, topics, label });
export const unsubscribeAlerts = (endpoint) => postAlert('unsubscribe', { endpoint });
export const testAlert = (endpoint) => postAlert('test', { endpoint });
