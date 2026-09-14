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

export function aiStreamUrl(camid) {
  return `/api/ai/stream?camid=${encodeURIComponent(camid)}&t=${Date.now()}`;
}

export async function fetchTrafficSummary(top = 8) {
  const res = await fetch(`/api/traffic/summary?top=${top}`);
  if (!res.ok) throw new Error('summary');
  return res.json();
}

export async function searchRoads(q, limit = 20) {
  const res = await fetch(`/api/traffic/roads?q=${encodeURIComponent(q)}&limit=${limit}`);
  if (!res.ok) throw new Error('roads');
  return (await res.json()).items || [];
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
