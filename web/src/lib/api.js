// The API client: one function per endpoint the pages use, grouped by topic.

// Fetch a JSON endpoint (init as for fetch: method, headers, body); a non-2xx answer throws Error(tag).
async function fetchJson(url, tag, init) {
  const res = await fetch(url, init);
  if (!res.ok) throw new Error(tag);
  return res.json();
}

// ---------------------------------------------------------------- Cameras

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

// Every camera for the live camera page: ours, the rest of iTIC's (via Longdo) and the BMA ones (source 'bma')
export async function fetchAllCameras() {
  const res = await fetch('/api/cameras/all');
  if (!res.ok) throw new Error('all_cameras');
  return (await res.json()).items || [];
}

// { checked_at, items: [camid] }: cameras the newest status check (every 5 minutes) could not pull from
export async function fetchDownCameras() {
  return fetchJson('/api/cameras/down', 'down_cameras');
}

// { checked_at, items: { camid: 'online' | 'offline' } } for the live-AI cameras
export async function fetchCameraHealth() {
  return fetchJson('/api/cameras/health', 'camera_health');
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

export async function fetchRoadCameras(name, maxKm = 0.25) {
  const res = await fetch(`/api/traffic/road_cameras?name=${encodeURIComponent(name)}&max_km=${maxKm}`);
  if (!res.ok) throw new Error('road_cameras');
  return (await res.json()).items || [];
}

// ---------------------------------------------------------------- Live AI camera: stream, counts, settings, incidents, checks

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
  return fetchJson('/api/ai/stats', 'stats');
}

// { range: '24h'|'7d'|'30d' } or { date: 'YYYY-MM-DD' } (hourly for that day)
export async function fetchAIHistory({ range = '24h', date } = {}) {
  const params = date ? `date=${date}` : `range=${range}`;
  return fetchJson(`/api/ai/history?${params}`, 'history');
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

export function resetAIPassed() {
  return fetch('/api/ai/reset_passed', { method: 'POST' });
}

export async function fetchAIAccuracy(limit = 50) {
  return fetchJson(`/api/ai/accuracy?limit=${limit}`, 'accuracy');
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
  return fetchJson(`/api/ai/accuracy/${id}`, 'accuracy', { method: 'DELETE' });
}

export async function fetchViolations({ hours = 24, camid, kind, limit = 30 } = {}) {
  const q = new URLSearchParams({ hours, limit });
  if (camid) q.set('camid', camid);
  if (kind) q.set('kind', kind);
  return fetchJson(`/api/ai/violations?${q}`, 'violations failed');
}

export async function fetchViolationStatus(camid) {
  const q = camid ? `?camid=${encodeURIComponent(camid)}` : '';
  return fetchJson(`/api/ai/violations/status${q}`, 'violation status failed');
}

export async function fetchIncidents() {
  return fetchJson('/api/incidents', 'incidents');
}

// Camera incidents from the last `hours`, including ones already cleared
export async function fetchIncidentHistory(hours = 24) {
  const res = await fetch(`/api/incidents/history?hours=${hours}`);
  if (!res.ok) throw new Error('incident_history');
  return (await res.json()).items || [];
}

export async function fetchCountCameras() {
  return fetchJson('/api/count/cameras', 'count');
}

export async function setCountCameras(camids) {
  return fetchJson('/api/count/cameras', 'count', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ camids }),
  });
}

export async function fetchSurveyRanking() {
  return fetchJson('/api/survey/ranking', 'ranking');
}

// ---------------------------------------------------------------- Traffic: roads, areas, events, risk

export async function fetchTrafficSummary(top = 8) {
  return fetchJson(`/api/traffic/summary?top=${top}`, 'summary');
}

export async function fetchTrafficGuidance() {
  return fetchJson('/api/traffic/guidance', 'guidance');
}

// Roads around a position (the card's "ใกล้ฉัน" button). Rounded to 0.01 degree (about 1 km) before it
// leaves the browser, so the exact position never reaches the server or its logs.
export async function fetchTrafficNear(lat, lng) {
  return fetchJson(`/api/traffic/near?lat=${lat.toFixed(2)}&lng=${lng.toFixed(2)}`, 'traffic_near');
}

// Road cards like fetchTrafficGuidance for one province (amphoe '') or district (area_roads.py)
export async function fetchAreaGuidance(province, amphoe = '') {
  return fetchJson(`/api/traffic/guidance/area?province=${province}${amphoe ? `&amphoe=${amphoe}` : ''}`, 'area_guidance');
}

// Traffic score per province and district over the whole country (Longdo lines)
export async function fetchTrafficAreas() {
  return fetchJson('/api/traffic/areas', 'traffic_areas');
}

// Accidents and closed roads in every province (Longdo feed + BMA traffic centre), for the traffic map
export async function fetchRoadEvents() {
  return fetchJson('/api/road/events', 'road_events');
}

// Per-road flood risk: rain + canal level + road sensors + traffic, scored and ranked
export async function fetchRoadRisk({ level = null, province = null, q = null, measured = null, limit = 400 } = {}) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (level) params.set('level', level);
  if (province) params.set('province', province);
  if (q) params.set('q', q);
  if (measured != null) params.set('measured', String(measured));
  return fetchJson(`/api/roads/risk?${params}`, 'road_risk');
}

// BMA traffic-risk analysis (riskbkk_agent.py): AI report + the per-district / per-hour numbers
export async function fetchRiskAnalysis() {
  return fetchJson('/api/riskbkk/analysis', 'riskbkk_analysis');
}

// Re-run it now; operator only (403 from anywhere else)
export async function runRiskAnalysis() {
  const res = await fetch('/api/riskbkk/analysis/run', { method: 'POST' });
  if (res.status === 403) throw new Error('forbidden');
  if (!res.ok) throw new Error('riskbkk_analysis_run');
  return res.json();
}

export async function fetchRscSummary() {
  return fetchJson('/api/rsc/summary', 'rsc summary failed');
}

export async function fetchRscCameraRisk({ limit, district } = {}) {
  const q = new URLSearchParams();
  if (limit) q.set('limit', limit);
  if (district) q.set('district', district);
  return fetchJson(`/api/rsc/camera_risk?${q}`, 'rsc risk failed');
}

export async function fetchRscPoints(camid, radius) {
  const q = new URLSearchParams({ camid });
  if (radius) q.set('radius', radius);
  return fetchJson(`/api/rsc/points?${q}`, 'rsc points failed');
}

export async function triggerRscRebuild() {
  const res = await fetch('/api/rsc/rebuild', { method: 'POST' });
  return res.json();
}

// ---------------------------------------------------------------- Flooding: sensors, feeds, reports, car parks, provinces

// Road flooding: BMA drainage sensors (weather.bangkok.go.th), depth over the road in cm
export async function fetchFloodStatus() {
  return fetchJson('/api/flood/status', 'flood_status');
}

export async function fetchFloodStations({ status = null, district = null, kind = null, limit = 400 } = {}) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (status) params.set('status', status);
  if (district) params.set('district', district);
  if (kind) params.set('kind', kind);
  return fetchJson(`/api/flood/stations?${params}`, 'flood_stations');
}

export async function fetchFloodAnalysis() {
  return fetchJson('/api/flood/analysis', 'flood_analysis');
}

// One plain-Thai notice per flooded Bangkok road, advice from the depth rule table (flood_service.notices)
export async function fetchFloodNotices() {
  return fetchJson('/api/flood/notices', 'flood_notices');
}

// Flood complaints residents filed on Traffy Fondue in the last few hours (flood_feeds.py)
// Flooded-road reports on the Longdo Traffic feed (iTIC / FM91), newest first (incident_service.floods)
export async function fetchLongdoFloods({ national = false } = {}) {
  return fetchJson(`/api/flood/longdo${national ? '?national=1' : ''}`, 'longdo_floods');
}

// Flooded highways in Bangkok and vicinity from the Department of Highways HDMS dashboard (flood_feeds.py)
export async function fetchHdmsFloods({ national = false } = {}) {
  return fetchJson(`/api/flood/hdms${national ? '?national=1' : ''}`, 'hdms_floods');
}

// Flooded-road items from the JS100 radio traffic news, last 48 h, text only (flood_feeds.py)
export async function fetchJs100Floods() {
  return fetchJson('/api/flood/js100', 'js100_floods');
}

export async function fetchFloodReports() {
  return fetchJson('/api/flood/reports', 'flood_reports');
}

// Flood reports from the public (user_reports.py): the published ones of the last hours
export async function fetchUserReports() {
  return fetchJson('/api/flood/user-reports', 'user_reports');
}

export async function fetchReportLocations() {
  const res = await fetch('/api/flood/report-locations');
  if (!res.ok) throw new Error('โหลดรายชื่อจังหวัดและอำเภอไม่ได้');
  return (await res.json()).provinces;
}

// Send one: { province, district, lat, lng, depth, note?, photo? (data: URL) } -> { id, status: published | pending | rejected, message }
export async function postUserReport(body) {
  const res = await fetch('/api/flood/user-reports', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const byStatus = { 413: 'รูปใหญ่เกินไป', 429: 'แจ้งถี่เกินไป ลองใหม่ภายหลัง' };
    throw new Error(byStatus[res.status] || data.detail || 'ส่งไม่สำเร็จ ลองใหม่อีกครั้ง');
  }
  return data;
}

// Announced flood car parks (flood_parking.py) with the public's recent "full" reports
export async function fetchFloodParking() {
  return fetchJson('/api/flood/parking', 'flood_parking');
}

export async function postParkingFull(id) {
  const res = await fetch(`/api/flood/parking/${encodeURIComponent(id)}/full`, { method: 'POST' });
  if (!res.ok) throw new Error(res.status === 429 ? 'แจ้งถี่เกินไป ลองใหม่ภายหลัง' : 'ส่งไม่สำเร็จ ลองใหม่อีกครั้ง');
  return res.json();
}

// AI flood watch on every BMA camera (flood_cam_service.py): counts + the cameras with water (all: every checked one)
export async function fetchFloodCameras({ all = false } = {}) {
  return fetchJson(`/api/flood/cameras${all ? '?all=1' : ''}`, 'flood_cameras');
}

// Traffy flood reports today vs yesterday / this week vs last week (traffy_history.py)
export async function fetchTraffyHistory() {
  return fetchJson('/api/traffy/history', 'traffy_history');
}

// AI reading of the Traffy Fondue flood reports of the last 6 h (traffy_agent.py): report + numbers
export async function fetchTraffyAnalysis() {
  return fetchJson('/api/traffy/analysis', 'traffy_analysis');
}

// Re-run it now; operator only (403 from anywhere else)
export async function runTraffyAnalysis() {
  const res = await fetch('/api/traffy/analysis/run', { method: 'POST' });
  if (res.status === 403) throw new Error('forbidden');
  if (!res.ok) throw new Error('traffy_analysis_run');
  return res.json();
}

// Flooded roads and rivers over the bank in every province, for the traffic map
export async function fetchNationalFloods() {
  return fetchJson('/api/flood/national-map', 'national_floods');
}

// Flood situation in every province (province_flood.py), also used by the Alerts page
export async function fetchProvinceFloods() {
  return fetchJson('/api/flood/provinces', 'province_floods');
}

// ---------------------------------------------------------------- Water outlook (ThaiWater / HII + BMA traffic centre)

export async function fetchWaterSummary() {
  return fetchJson('/api/water/summary', 'water_summary');
}

// Every metro water / rain gauge and the upstream dams as map points (Water Forecast station map)
export async function fetchWaterMap() {
  return fetchJson('/api/water/map', 'water_map');
}

// Northern rivers to the Central Plain: RID discharge, routed 4-day outlook, dams, warnings (north_flow.py)
export async function fetchWaterNorth() {
  return fetchJson('/api/water/north', 'water_north');
}

export async function fetchBMAEvents({ kind, hours = 24, limit = 60 } = {}) {
  const params = new URLSearchParams({ hours, limit });
  if (kind) params.set('kind', kind);
  return fetchJson(`/api/water/bma_events?${params}`, 'bma_events');
}

// ---------------------------------------------------------------- Weather, wind, air and NASA

// Weather this hour at a spot (weather_now.py, MET Norway); no lat/lng = Bangkok centre
export async function fetchWeatherNow(lat, lng) {
  const q = lat != null && lng != null ? `?lat=${lat}&lng=${lng}` : '';
  return fetchJson(`/api/weather/now${q}`, 'weather_now');
}

// TMD heavy-rain / storm warnings; `active` = issued in the last two days (flood_feeds.py)
export async function fetchWeatherWarnings() {
  return fetchJson('/api/weather/warnings', 'weather_warnings');
}

export async function fetchWindGrid() {
  return fetchJson('/api/weather/wind', 'wind');
}

// Hourly wind (u, v in m/s) on a 1 degree grid over Thailand, for the moving wind lines on the camera map
export async function fetchWindField() {
  return fetchJson('/api/weather/wind_field', 'wind_field');
}

export async function fetchAirStations() {
  return fetchJson('/api/air/stations', 'air');
}

// NASA FIRMS fire hotspots in Thailand and along its borders (last 24 h, with the analysis); null until the
// server's first read (202). See nasa_feeds.py.
export async function fetchNasaFires() {
  const res = await fetch('/api/nasa/fires');
  if (res.status === 202) return null;
  if (!res.ok) throw new Error('nasa_fires');
  return res.json();
}

// NASA EONET natural events from India to the western Pacific (storms with tracks and distance to Thailand)
export async function fetchNasaEvents() {
  const res = await fetch('/api/nasa/events');
  if (res.status === 202) return null;
  if (!res.ok) throw new Error('nasa_events');
  return res.json();
}

// ---------------------------------------------------------------- Patrols on the BMA cameras: helmets, wrong way

export async function fetchHelmetStatus() {
  return fetchJson('/api/helmet/status', 'helmet_status');
}

export async function fetchHelmetRecent({ hours = 24, verdict = null, camid = null, limit = 200 } = {}) {
  const params = new URLSearchParams({ hours: String(hours), limit: String(limit) });
  if (verdict) params.set('verdict', verdict);
  if (camid) params.set('camid', camid);
  return fetchJson(`/api/helmet/recent?${params}`, 'helmet_recent');
}

export async function fetchHelmetCameras() {
  return fetchJson('/api/helmet/cameras', 'helmet_cameras');
}

export async function triggerHelmetCheck(camid) {
  return fetchJson(`/api/helmet/check/${encodeURIComponent(camid)}`, 'helmet_check', { method: 'POST' });
}

export async function reanalyseHelmet(hid, agent = 'cloud') {
  return fetchJson(`/api/helmet/${encodeURIComponent(hid)}/reanalyse?agent=${agent}`, 'helmet_reanalyse', { method: 'POST' });
}

export async function reanalyseHelmetPending(agent = 'cloud', limit = 40) {
  return fetchJson(`/api/helmet/reanalyse_pending?agent=${agent}&limit=${limit}`, 'helmet_reanalyse_pending', { method: 'POST' });
}

// Wrong-way patrol (all BMA cameras): same shape as the helmet API plus the learned lane-direction field
export async function fetchWrongWayStatus() {
  return fetchJson('/api/wrongway/status', 'wrongway_status');
}

export async function fetchWrongWayRecent({ hours = 24, verdict = null, camid = null, limit = 200 } = {}) {
  const params = new URLSearchParams({ hours: String(hours), limit: String(limit) });
  if (verdict) params.set('verdict', verdict);
  if (camid) params.set('camid', camid);
  return fetchJson(`/api/wrongway/recent?${params}`, 'wrongway_recent');
}

export async function fetchWrongWayCameras() {
  return fetchJson('/api/wrongway/cameras', 'wrongway_cameras');
}

export async function fetchWrongWayField(camid) {
  return fetchJson(`/api/wrongway/field/${encodeURIComponent(camid)}`, 'wrongway_field');
}

export async function triggerWrongWayCheck(camid) {
  return fetchJson(`/api/wrongway/check/${encodeURIComponent(camid)}`, 'wrongway_check', { method: 'POST' });
}

export async function reanalyseWrongWay(wid, agent = 'cloud') {
  return fetchJson(`/api/wrongway/${encodeURIComponent(wid)}/reanalyse?agent=${agent}`, 'wrongway_reanalyse', { method: 'POST' });
}

export async function reanalyseWrongWayPending(agent = 'cloud', limit = 40) {
  return fetchJson(`/api/wrongway/reanalyse_pending?agent=${agent}&limit=${limit}`, 'wrongway_reanalyse_pending', { method: 'POST' });
}

export async function dismissWrongWay(wid) {
  return fetchJson(`/api/wrongway/${encodeURIComponent(wid)}/dismiss`, 'wrongway_dismiss', { method: 'POST' });
}

// ---------------------------------------------------------------- BMA Traffic cameras and YOLO vehicle counting

export async function fetchBmaCameras() {
  return fetchJson('/api/bma/cameras', 'bma_cameras');
}

export async function fetchBmaAnalytics() {
  return fetchJson('/api/bma/analytics', 'bma_analytics');
}

export async function fetchBmaScanStatus() {
  return fetchJson('/api/bma/scan/status', 'bma_scan_status');
}

export async function triggerBmaScan() {
  return fetchJson('/api/bma/scan', 'bma_scan', { method: 'POST' });
}

export function getBmaSnapshotUrl(camid, live = false, t = null, annotate = true) {
  const params = new URLSearchParams();
  if (live) params.set('live', '1');
  if (!annotate) params.set('annotate', '0');   // the plain frame, without running YOLO on it
  if (t) params.set('t', String(t));
  const qs = params.toString();
  return `/api/bma/snapshot/${encodeURIComponent(camid)}${qs ? `?${qs}` : ''}`;
}

export function getBmaStreamUrl(camid, t = null) {
  return `/api/bma/stream/${encodeURIComponent(camid)}?t=${t || Date.now()}`;
}

export async function fetchBmaLiveAnalysis(camid) {
  return fetchJson(`/api/bma/live_analysis/${encodeURIComponent(camid)}`, 'bma_live_analysis');
}

export async function fetchBmaCycle() {
  return fetchJson('/api/bma/cycle', 'bma_cycle');
}

export async function fetchBmaComparison(period = 'day') {
  return fetchJson(`/api/bma/comparison?period=${encodeURIComponent(period)}`, 'bma_comparison');
}

export async function fetchBmaDriveDStatus() {
  return fetchJson('/api/bma/drive_d_status', 'bma_drive_d_status');
}

// ---------------------------------------------------------------- Assistant, site analytics, visitors, news

// `location` ({lat, lng}, optional) is where the person is, for "how do I get to ..." with no start
export async function sendChat(messages, location = null) {
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(location ? { messages, location } : { messages }),
  });
  if (res.status === 429) throw new Error('rate_limited');
  if (res.status === 413) throw new Error('too_long');
  if (!res.ok) throw new Error('chat');
  return res.json();
}

export async function fetchAnalytics(refresh = false) {
  return fetchJson(`/api/analytics/summary${refresh ? '?refresh=true' : ''}`, 'analytics failed');
}

export async function fetchVisitorStats() {
  return fetchJson('/api/telemetry/stats', 'visitor stats failed');
}

export async function fetchOnlineCount() {
  const res = await fetch('/api/telemetry/online');
  if (!res.ok) throw new Error('online count failed');
  const d = await res.json();
  return d.online;
}

// Flood and road-accident headlines from Thai news outlets (news_feed.py); kind: 'flood' | 'accident' | undefined
export async function fetchNews(kind) {
  return fetchJson(kind ? `/api/news?kind=${kind}` : '/api/news', 'news');
}

// ---------------------------------------------------------------- Web Push alerts (alert_service.py)

export async function fetchAlertStatus(endpoint) {
  const params = endpoint ? `?${new URLSearchParams({ endpoint })}` : '';
  return fetchJson(`/api/alerts/status${params}`, 'alerts_status');
}

export async function fetchAlertRecent(limit = 50) {
  return fetchJson(`/api/alerts/recent?limit=${limit}`, 'alerts_recent');
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

export const subscribeAlerts = (subscription, topics, label, provinces) => postAlert('subscribe', { subscription, topics, label, provinces });

export const unsubscribeAlerts = (endpoint) => postAlert('unsubscribe', { endpoint });

export const testAlert = (endpoint) => postAlert('test', { endpoint });
