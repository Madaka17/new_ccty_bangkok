// The server's /api/ wants the page-session cookie (bkk_s, access_guard.py), which it sets only with the
// page itself. A tab that outlived its cookie (asleep for over 12 h, or opened before a server restart that
// turned the check on) or a page shown from the browser cache never gets one, and every API call then
// answers 403. Reload the page once so the server sets a fresh cookie; at most once a minute, so a browser
// that refuses cookies does not reload in a loop.
const KEY = 'bkk_session_reload';
const MIN_GAP_MS = 60000;

function reloadOnce() {
  try {
    const last = Number(sessionStorage.getItem(KEY) || 0);
    if (Date.now() - last < MIN_GAP_MS) return;
    sessionStorage.setItem(KEY, String(Date.now()));
  } catch {
    return;
  }
  window.location.reload();
}

export function installSessionReload() {
  const nativeFetch = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const res = await nativeFetch(input, init);
    if (res.status === 403) {
      const url = new URL(input instanceof Request ? input.url : String(input), window.location.href);
      if (url.origin === window.location.origin && url.pathname.startsWith('/api/')) {
        res.clone().json().then((d) => {
          if (String(d?.error || '').includes('reload the page')) reloadOnce();
        }).catch(() => {});
      }
    }
    return res;
  };
}
