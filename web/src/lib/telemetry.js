// Anonymous visitor telemetry for the analytics page: one `view` per page/tab change,
// one heartbeat every 30 s while the tab is open. Only a random session id is sent.
const KEY = 'bkk_sid';
const HEARTBEAT_MS = 30000;
let current = 'dashboard';

function sid() {
  try {
    let v = localStorage.getItem(KEY);
    if (!v) {
      v = Math.random().toString(36).slice(2, 12) + Date.now().toString(36);
      localStorage.setItem(KEY, v);
    }
    return v;
  } catch {
    return 'anon-' + Math.random().toString(36).slice(2, 12);
  }
}

function post(path, view) {
  fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sid: sid(), view }),
    keepalive: true,
  }).catch(() => {});
}

export function trackView(view) {
  current = view;
  post('/api/telemetry/view', view);
}

export function startHeartbeat() {
  const tick = () => {
    if (document.visibilityState === 'visible') post('/api/telemetry/heartbeat', current);
  };
  const id = setInterval(tick, HEARTBEAT_MS);
  return () => clearInterval(id);
}
