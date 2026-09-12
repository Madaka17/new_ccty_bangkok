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

export async function sendChat(messages) {
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages }),
  });
  if (!res.ok) throw new Error('chat');
  return res.json();
}
