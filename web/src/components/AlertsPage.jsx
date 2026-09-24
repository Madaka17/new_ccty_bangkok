import { useCallback, useEffect, useState } from 'react';
import { fetchAlertStatus, fetchAlertRecent, subscribeAlerts, unsubscribeAlerts, testAlert } from '../lib/api.js';
import { Card, Badge, Button, Skeleton, EmptyState } from './dashboard/ui.jsx';
import { PageHeader, StatusBanner } from './dashboard/primitives.jsx';
import { fmtDateTime } from './dashboard/format.js';

const POLL_MS = 30000;
const TOPIC_TONE = { flood: 'blue', zone: 'red', incident: 'yellow', air: 'neutral', system: 'green' };
const SUPPORTED = typeof window !== 'undefined' && window.isSecureContext
  && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;

// VAPID public key (base64url) -> the byte array pushManager.subscribe expects
function keyBytes(b64) {
  const s = atob((b64 + '='.repeat((4 - (b64.length % 4)) % 4)).replace(/-/g, '+').replace(/_/g, '/'));
  return Uint8Array.from(s, (c) => c.charCodeAt(0));
}

// Web Push alerts for the team: this browser subscribes to the topics it wants, the server
// (alert_service.py) pushes when a road floods, an area turns red, an accident is reported,
// PM2.5 turns unhealthy or the system has a problem. Subscribing works only from the team network.
export default function AlertsPage({ isActive, onToast }) {
  const [status, setStatus] = useState(null);
  const [recent, setRecent] = useState(null);
  const [sub, setSub] = useState(null);
  const [topics, setTopics] = useState([]);
  const [busy, setBusy] = useState(null);
  const [problem, setProblem] = useState('');

  const load = useCallback(async (endpoint) => {
    try {
      const [st, rc] = await Promise.all([fetchAlertStatus(endpoint), fetchAlertRecent(50)]);
      setStatus(st);
      setRecent(rc.items);
      return st;
    } catch {
      return null;
    }
  }, []);

  // Find this browser's existing subscription, then ask the server which topics it holds
  useEffect(() => {
    if (!isActive) return undefined;
    let cancelled = false;
    (async () => {
      let current = null;
      if (SUPPORTED) {
        try {
          const reg = await navigator.serviceWorker.register('/sw.js');
          current = await reg.pushManager.getSubscription();
        } catch {
          /* the page still lists the alert history */
        }
      }
      if (cancelled) return;
      setSub(current);
      const st = await load(current?.endpoint);
      if (!cancelled && st) setTopics(st.my_topics || Object.keys(st.topics));
    })();
    const id = setInterval(() => load(), POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [isActive, load]);

  const run = async (name, fn) => {
    setBusy(name);
    setProblem('');
    try {
      await fn();
    } catch (e) {
      setProblem(e.message === 'forbidden'
        ? 'เปิดรับแจ้งเตือนได้เฉพาะจากเครือข่ายทีม (LAN / Tailscale) หรือเครื่องเซิร์ฟเวอร์เท่านั้น'
        : 'ทำรายการไม่สำเร็จ ลองใหม่อีกครั้ง');
    } finally {
      setBusy(null);
    }
  };

  const enable = () => run('enable', async () => {
    if ((await Notification.requestPermission()) !== 'granted') {
      setProblem('เบราว์เซอร์ไม่อนุญาตการแจ้งเตือน เปิดสิทธิ์ Notifications ของเว็บนี้ในการตั้งค่าเบราว์เซอร์ก่อน');
      return;
    }
    const reg = await navigator.serviceWorker.ready;
    const s = (await reg.pushManager.getSubscription())
      || (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(status.public_key) }));
    try {
      await subscribeAlerts(s.toJSON(), topics, navigator.userAgent);
    } catch (e) {
      await s.unsubscribe();   // do not leave a browser subscription the server never stored
      throw e;
    }
    setSub(s);
    await load(s.endpoint);
    onToast?.('เปิดรับแจ้งเตือนแล้ว');
  });

  const disable = () => run('disable', async () => {
    await unsubscribeAlerts(sub.endpoint);
    await sub.unsubscribe();
    setSub(null);
    await load();
    onToast?.('ปิดรับแจ้งเตือนแล้ว');
  });

  const saveTopics = (next) => {
    setTopics(next);
    if (sub) run('topics', () => subscribeAlerts(sub.toJSON(), next, navigator.userAgent));
  };

  const test = () => run('test', async () => {
    const r = await testAlert(sub.endpoint);
    onToast?.(r.ok ? 'ส่งแจ้งเตือนทดสอบแล้ว' : 'ส่งไม่สำเร็จ ลองปิดแล้วเปิดรับแจ้งเตือนใหม่');
  });

  const toggle = (t) => saveTopics(topics.includes(t) ? topics.filter((x) => x !== t) : [...topics, t]);
  const topicNames = status?.topics || {};

  return (
    <div className="space-y-4">
      <PageHeader
        title="Alerts"
        description="แจ้งเตือนบนเบราว์เซอร์สำหรับทีม: น้ำท่วมถนน เขตเตือนภัย อุบัติเหตุ/ปิดถนน PM2.5 และระบบ ตรวจทุก 1 นาที"
        actions={sub && <Button size="sm" onClick={test} loading={busy === 'test'}>ส่งแจ้งเตือนทดสอบ</Button>}
      />

      {!SUPPORTED && (
        <StatusBanner tone="yellow" label="ใช้ไม่ได้บนเบราว์เซอร์นี้">
          ต้องเปิดผ่าน https (ลิงก์ Tailscale) หรือ localhost และใช้ Chrome, Edge, Firefox หรือ Safari
          (iPhone/iPad: กดแชร์ แล้ว "เพิ่มไปยังหน้าจอโฮม" ก่อน แล้วเปิดจากไอคอนนั้น)
        </StatusBanner>
      )}
      {status && !status.enabled && (
        <StatusBanner tone="yellow" label="เซิร์ฟเวอร์ยังไม่พร้อม">ติดตั้ง pywebpush บนเซิร์ฟเวอร์ก่อน (pip install -r requirements.txt)</StatusBanner>
      )}
      {problem && <StatusBanner tone="red" label="ไม่สำเร็จ">{problem}</StatusBanner>}

      <Card className="p-4 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-slate-900">เครื่องนี้</p>
            <p className="text-xs text-slate-600 mt-0.5">
              {sub ? 'รับแจ้งเตือนอยู่' : 'ยังไม่ได้รับแจ้งเตือน'}
              {status && ` · ทีมรับแจ้งเตือน ${status.subscribers} เครื่อง`}
              {status?.last_check && ` · ตรวจล่าสุด ${fmtDateTime(status.last_check)}`}
            </p>
          </div>
          {sub ? (
            <Button variant="secondary" onClick={disable} loading={busy === 'disable'}>ปิดรับแจ้งเตือน</Button>
          ) : (
            <Button variant="primary" onClick={enable} loading={busy === 'enable'}
                    disabled={!SUPPORTED || !status?.enabled || !topics.length}>
              เปิดรับแจ้งเตือน
            </Button>
          )}
        </div>

        <fieldset>
          <legend className="text-xs font-medium text-slate-700 mb-2">เรื่องที่ต้องการรับ</legend>
          <div className="flex flex-wrap gap-2">
            {Object.entries(topicNames).map(([id, name]) => (
              <label key={id} className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-3 h-9 text-sm text-slate-800 cursor-pointer hover:bg-slate-50">
                <input type="checkbox" className="accent-blue-600" checked={topics.includes(id)} onChange={() => toggle(id)}
                       disabled={busy === 'topics'} />
                {name}
              </label>
            ))}
          </div>
        </fieldset>
      </Card>

      <Card className="p-4">
        <p className="text-sm font-semibold text-slate-900 mb-3">แจ้งเตือนล่าสุด</p>
        {recent === null ? (
          <div className="space-y-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-12" />)}</div>
        ) : recent.length === 0 ? (
          <EmptyState title="ยังไม่มีแจ้งเตือน" description="เมื่อมีเหตุการณ์เข้าเกณฑ์ จะแสดงที่นี่และส่งไปยังเครื่องที่รับแจ้งเตือน" />
        ) : (
          <ul className="divide-y divide-slate-100">
            {recent.map((a) => (
              <li key={`${a.key}-${a.ts}`} className="py-2.5 flex gap-3">
                <Badge tone={TOPIC_TONE[a.topic]} className="shrink-0 self-start">{topicNames[a.topic] || a.topic}</Badge>
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-slate-900 leading-5">{a.title}</p>
                  {a.body && <p className="text-xs text-slate-600 leading-5 whitespace-pre-line">{a.body}</p>}
                </div>
                <time className="text-xs text-slate-500 shrink-0 tabular-nums">{fmtDateTime(a.ts)}</time>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
