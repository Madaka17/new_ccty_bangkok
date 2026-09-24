import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchAlertStatus, fetchAlertRecent, subscribeAlerts, unsubscribeAlerts, testAlert, fetchFloodReports, fetchWeatherWarnings } from '../lib/api.js';
import { inPageAlertsOn, setInPageAlerts } from './AlertPopups.jsx';
import { Card, Badge, Button, Skeleton, EmptyState } from './dashboard/ui.jsx';
import { PageHeader, StatusBanner } from './dashboard/primitives.jsx';
import { fmtDateTime } from './dashboard/format.js';

const POLL_MS = 30000;
const REPORTS_SHOWN = 3;   // per district, until the district is expanded
const TOPIC_TONE = { flood: 'blue', zone: 'red', incident: 'yellow', air: 'neutral', system: 'green' };
const SUPPORTED = typeof window !== 'undefined' && window.isSecureContext
  && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;

// VAPID public key (base64url) -> the byte array pushManager.subscribe expects
const agoTh = (ts) => {
  const m = Math.round((Date.now() / 1000 - ts) / 60);
  return m < 1 ? 'เมื่อสักครู่' : m < 60 ? `${m} นาทีก่อน` : `${Math.floor(m / 60)} ชม. ${m % 60} นาทีก่อน`;
};
const thaiDate = (iso) => (iso ? new Date(`${iso}T00:00:00`).toLocaleDateString('th-TH', { day: 'numeric', month: 'short', year: '2-digit' }) : '-');

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
  const [popups, setPopups] = useState(inPageAlertsOn);
  const [warnings, setWarnings] = useState(null);
  const [reports, setReports] = useState(null);
  const [openDistrict, setOpenDistrict] = useState(null);

  const load = useCallback(async (endpoint) => {
    try {
      // The flood feeds are extras: the page still works when one of them is down
      fetchWeatherWarnings().then(setWarnings).catch(() => {});
      fetchFloodReports().then(setReports).catch(() => {});
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

  // Reports grouped by district, busiest first
  const districts = useMemo(() => {
    const by = {};
    for (const r of reports?.items || []) (by[r.district || 'ไม่ระบุเขต'] ||= []).push(r);
    return Object.entries(by).map(([name, items]) => ({ name, items })).sort((a, b) => b.items.length - a.items.length || b.items[0].ts - a.items[0].ts);
  }, [reports]);
  // One row per event: the newest issue (the list is newest first), with how many came before it
  const activeWarnings = useMemo(() => {
    const out = [];
    for (const w of warnings?.active || []) {
      const hit = out.find((x) => x.series === w.series);
      if (hit) hit.older += 1;
      else out.push({ ...w, older: 0 });
    }
    return out;
  }, [warnings]);

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

        <label className="flex items-start gap-2 text-sm text-slate-800 cursor-pointer">
          <input type="checkbox" className="accent-blue-600 mt-1" checked={popups}
                 onChange={(e) => { setPopups(e.target.checked); setInPageAlerts(e.target.checked); }} />
          <span>
            เด้งเตือนบนหน้าเว็บอัตโนมัติ
            <span className="block text-xs text-slate-500">
              ระหว่างเปิดเว็บนี้อยู่ ไม่ว่าจะอยู่หน้าไหน จะมีการ์ดเตือนขึ้นมุมขวาบนเมื่อมีแจ้งเตือนใหม่ ไม่ต้องสมัครและไม่ต้องใช้ https (ไม่รวมเรื่องระบบ)
            </span>
          </span>
        </label>
      </Card>

      <Card className="p-4">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
          <p className="text-sm font-semibold text-slate-900">ประกาศเตือนภัยกรมอุตุนิยมวิทยา</p>
          {warnings?.updated_at && <span className="text-xs text-slate-500">อัปเดต {fmtDateTime(warnings.updated_at)}</span>}
        </div>
        {warnings === null ? (
          <Skeleton className="h-16" />
        ) : activeWarnings.length === 0 ? (
          <EmptyState title="ไม่มีประกาศเตือนภัยใน 2 วันล่าสุด" description={warnings.error ? 'ดึงข้อมูลจาก tmd.go.th ไม่สำเร็จ แสดงข้อมูลรอบล่าสุดที่มี' : 'ข้อมูลจาก tmd.go.th ตรวจทุก 15 นาที'} />
        ) : (
          <ul className="divide-y divide-slate-100">
            {activeWarnings.map((w) => (
              <li key={w.url} className="py-2.5">
                <div className="flex flex-wrap items-center gap-2 mb-1">
                  {w.bkk ? <Badge tone="red" dot>กระทบ กทม.</Badge> : <Badge>ต่างจังหวัด</Badge>}
                  <span className="text-xs text-slate-500">{thaiDate(w.date)}{w.older ? ` · ออกมาแล้ว ${w.older + 1} ฉบับ` : ''}</span>
                </div>
                <a href={w.url} target="_blank" rel="noopener noreferrer" className="text-sm font-medium text-slate-900 hover:text-blue-700 leading-5">{w.title}</a>
                {w.summary && <p className="text-xs text-slate-600 leading-5 mt-0.5">{w.summary}</p>}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card className="p-4">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-1">
          <p className="text-sm font-semibold text-slate-900">ประชาชนแจ้งน้ำท่วม (6 ชม.ล่าสุด)</p>
          {reports?.updated_at && <span className="text-xs text-slate-500">อัปเดต {fmtDateTime(reports.updated_at)}</span>}
        </div>
        <p className="text-xs text-slate-500 mb-3">
          จาก Traffy Fondue คัดด้วยคำว่า น้ำท่วม/น้ำขัง ยังไม่ผ่านการตรวจสอบจากเขต · แจ้งเตือนเมื่อเขตเดียวกันมีตั้งแต่ 3 เรื่องใน 1 ชม.
        </p>
        {reports === null ? (
          <div className="space-y-2">{[0, 1].map((i) => <Skeleton key={i} className="h-12" />)}</div>
        ) : districts.length === 0 ? (
          <EmptyState title="ไม่มีเรื่องแจ้งน้ำท่วม" description="ยังไม่มีประชาชนแจ้งน้ำท่วมใน 6 ชั่วโมงที่ผ่านมา" />
        ) : (
          <div className="space-y-3">
            {districts.map((d) => (
              <section key={d.name}>
                <p className="text-xs font-semibold text-slate-700 mb-1">เขต{d.name} · {d.items.length} เรื่อง</p>
                <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
                  {(openDistrict === d.name ? d.items : d.items.slice(0, REPORTS_SHOWN)).map((r) => (
                    <li key={r.id} className="p-2.5 flex gap-3">
                      {r.photo && <img src={r.photo} alt="" loading="lazy" className="w-16 h-16 rounded-md object-cover shrink-0" />}
                      <div className="min-w-0 flex-1">
                        <p className="text-sm text-slate-900 leading-5 line-clamp-2">{r.text}</p>
                        <p className="text-xs text-slate-500 mt-0.5">
                          {agoTh(r.ts)}{r.depth ? ` · ระดับ${r.depth}` : ''} · {r.state || '-'} ·{' '}
                          <a href={r.url} target="_blank" rel="noopener noreferrer" className="text-blue-700 hover:underline">ดูใน Traffy</a>
                        </p>
                      </div>
                    </li>
                  ))}
                </ul>
                {d.items.length > REPORTS_SHOWN && (
                  <button type="button" onClick={() => setOpenDistrict(openDistrict === d.name ? null : d.name)}
                          className="cursor-pointer mt-1 text-xs text-blue-700 hover:underline">
                    {openDistrict === d.name ? 'ย่อ' : `ดูอีก ${d.items.length - REPORTS_SHOWN} เรื่อง`}
                  </button>
                )}
              </section>
            ))}
          </div>
        )}
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
