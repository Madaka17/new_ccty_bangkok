import { useCallback, useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { fetchAlertRecent } from '../lib/api.js';
import { Badge } from './dashboard/ui.jsx';

// In-page alerts: every open tab polls the server's alert history (alert_service.py) and pops a
// card for each alert newer than the last one this browser has seen. Unlike Web Push it needs no
// subscription and no https, but it only works while the site is open.
const POLL_MS = 30000;
const HIDE_MS = 20000;        // a severe alert (level 2) stays until it is closed
const MAX_CARDS = 3;
const SEEN_KEY = 'alerts.lastSeen';
const ON_KEY = 'alerts.inPage';
const ON_EVENT = 'alerts-inpage';

const TOPIC = {
  flood: { label: 'น้ำท่วมถนน', tone: 'blue', page: 'water' },
  zone: { label: 'เขตเตือนภัย', tone: 'red', page: 'water' },
  incident: { label: 'อุบัติเหตุ/ปิดถนน', tone: 'yellow', page: 'dashboard' },
  air: { label: 'PM2.5', tone: 'neutral', page: 'map' },
};

const read = (k) => {
  try {
    return localStorage.getItem(k);
  } catch {
    return null;
  }
};
const write = (k, v) => {
  try {
    localStorage.setItem(k, v);
  } catch {
    /* private window: the popups still work for this visit */
  }
};

export const inPageAlertsOn = () => read(ON_KEY) !== '0';
export function setInPageAlerts(on) {
  write(ON_KEY, on ? '1' : '0');
  window.dispatchEvent(new Event(ON_EVENT));
}

// Traffy reports have points on the map; every other flood alert is best read on the water page
const pageOf = (a) => (a.key?.startsWith('traffy:') ? 'map' : TOPIC[a.topic]?.page || 'alerts');

export default function AlertPopups({ onNavigate }) {
  const [cards, setCards] = useState([]);
  const [on, setOn] = useState(inPageAlertsOn);
  const timers = useRef({});

  useEffect(() => {
    const sync = () => setOn(inPageAlertsOn());
    window.addEventListener(ON_EVENT, sync);
    window.addEventListener('storage', sync);
    return () => {
      window.removeEventListener(ON_EVENT, sync);
      window.removeEventListener('storage', sync);
    };
  }, []);

  const close = useCallback((id) => {
    clearTimeout(timers.current[id]);
    delete timers.current[id];
    setCards((cs) => cs.filter((c) => c.id !== id));
  }, []);

  useEffect(() => {
    if (!on) return undefined;
    let alive = true;
    // First visit: start from now, so an open tab does not replay the whole history
    let seen = Number(read(SEEN_KEY)) || null;
    const tick = () =>
      fetchAlertRecent(20)
        .then(({ items }) => {
          if (!alive) return;
          const newest = Math.max(0, ...items.map((a) => a.ts));
          if (seen === null) seen = newest;
          // System alerts (server restarts, disk) are for the operators on the Alerts page only
          const fresh = items.filter((a) => a.ts > seen && TOPIC[a.topic]).slice(0, MAX_CARDS);
          seen = Math.max(seen, newest);
          write(SEEN_KEY, String(seen));
          if (!fresh.length) return;
          const add = fresh.map((a) => ({ ...a, id: `${a.key}-${a.ts}` }));
          setCards((cs) => [...add, ...cs.filter((c) => !add.some((n) => n.id === c.id))].slice(0, MAX_CARDS));
          for (const c of add) {
            if (c.level < 2) timers.current[c.id] = setTimeout(() => close(c.id), HIDE_MS);
          }
        })
        .catch(() => {});
    tick();
    const id = setInterval(tick, POLL_MS);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [on, close]);

  useEffect(() => () => Object.values(timers.current).forEach(clearTimeout), []);

  return (
    <div className="fixed top-4 right-4 left-4 sm:left-auto sm:w-96 z-[70] flex flex-col gap-2 pointer-events-none" aria-live="assertive">
      <AnimatePresence>
        {on && cards.map((a) => {
          const t = TOPIC[a.topic];
          return (
            <motion.div
              key={a.id}
              role="alert"
              initial={{ opacity: 0, x: 40 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 40 }}
              className={`pointer-events-auto rounded-xl bg-white border shadow-xl p-3 flex gap-3 ${a.level >= 2 ? 'border-red-400' : 'border-slate-200'}`}
            >
              <button
                type="button"
                onClick={() => {
                  close(a.id);
                  onNavigate(pageOf(a));
                }}
                className="cursor-pointer min-w-0 flex-1 text-left"
              >
                <span className="flex items-center gap-2 mb-1">
                  <Badge tone={a.level >= 2 ? 'red' : t.tone} dot>{t.label}</Badge>
                  <span className="text-[11px] text-slate-500 tabular-nums">
                    {new Date(a.ts * 1000).toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' })} น.
                  </span>
                </span>
                <span className="block text-sm font-semibold text-slate-900 leading-5">{a.title}</span>
                {a.body && <span className="block text-xs text-slate-600 leading-5 line-clamp-3 whitespace-pre-line mt-0.5">{a.body}</span>}
              </button>
              <button
                type="button"
                onClick={() => close(a.id)}
                className="cursor-pointer shrink-0 self-start w-7 h-7 rounded-md text-slate-500 hover:bg-slate-100 text-lg leading-none"
                aria-label="ปิดแจ้งเตือน"
              >
                ×
              </button>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
