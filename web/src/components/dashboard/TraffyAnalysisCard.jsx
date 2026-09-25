// AI reading of the flood reports people sent through Traffy Fondue in the last 6 h (traffy_agent.py):
// the Qwen model reads the per-district / per-hour numbers and the newest report texts and writes where
// the reports cluster, what people describe and which reports need a team first. The numbers themselves
// are drawn here too, so they stay visible without the model.
import { useCallback, useEffect, useState } from 'react';
import { fetchTraffyAnalysis, runTraffyAnalysis } from '../../lib/api.js';
import { Card, Badge, Button, SectionHeader, Skeleton, EmptyState } from './ui.jsx';
import { fmtDateTime, fmtNum, agoText } from './format.js';

const POLL_MS = 60000;
const LEVEL_TONE = { สูง: 'red', ปานกลาง: 'yellow', ต่ำ: 'green' };
const LEVEL_BAR = { สูง: 'bg-red-500', ปานกลาง: 'bg-amber-400', ต่ำ: 'bg-emerald-500' };
const DEPTH_ORDER = ['ข้อเท้า', 'หน้าแข้ง', 'หัวเข่า', 'ต้นขา', 'เอวขึ้นไป', 'ไม่ระบุ'];
const DEPTH_BAR = { ข้อเท้า: 'bg-sky-300', หน้าแข้ง: 'bg-sky-500', หัวเข่า: 'bg-amber-500', ต้นขา: 'bg-orange-600', เอวขึ้นไป: 'bg-red-600', ไม่ระบุ: 'bg-slate-300' };

// Reports per hour, oldest on the left
function HourBars({ byHour }) {
  const rows = [...(byHour || [])].reverse();
  const max = Math.max(1, ...rows.map((r) => r.reports));
  return (
    <div role="img" aria-label="จำนวนเรื่องแจ้งรายชั่วโมง 6 ชั่วโมงล่าสุด" className="flex items-end gap-1 h-20">
      {rows.map((r) => (
        <div key={r.hours_ago} className="flex-1 flex flex-col items-center justify-end h-full" title={`${r.hours_ago === 0 ? 'ชั่วโมงล่าสุด' : `${r.hours_ago} ชม. ก่อน`}: ${r.reports} เรื่อง`}>
          <span className="text-[10px] tabular-nums text-slate-600">{r.reports}</span>
          <div className={`w-full rounded-t ${r.hours_ago === 0 ? 'bg-blue-600' : 'bg-blue-400/70'}`} style={{ height: `${Math.max(4, (r.reports / max) * 100)}%` }} />
          <span className="text-[10px] text-slate-500 mt-0.5">{r.hours_ago === 0 ? 'ล่าสุด' : `-${r.hours_ago}ชม.`}</span>
        </div>
      ))}
    </div>
  );
}

// Share of reports per water depth, one stacked bar
function DepthBar({ depths, total }) {
  const parts = DEPTH_ORDER.filter((k) => depths?.[k]).map((k) => ({ k, n: depths[k] }));
  if (!parts.length || !total) return null;
  return (
    <div>
      <div className="flex h-3 rounded-full overflow-hidden" role="img" aria-label="สัดส่วนระดับน้ำที่ประชาชนแจ้ง">
        {parts.map((p) => <span key={p.k} className={DEPTH_BAR[p.k]} style={{ width: `${(p.n / total) * 100}%` }} title={`${p.k} ${p.n} เรื่อง`} />)}
      </div>
      <ul className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[11.5px] text-slate-600">
        {parts.map((p) => (
          <li key={p.k} className="flex items-center gap-1">
            <span className={`w-2 h-2 rounded-full ${DEPTH_BAR[p.k]}`} aria-hidden="true" />{p.k} <span className="tabular-nums">{p.n}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function TraffyAnalysisCard({ isActive }) {
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState(null);

  const load = useCallback(() => {
    return fetchTraffyAnalysis()
      .then((d) => { setData(d); setFailed(false); })
      .catch(() => setFailed(true));
  }, []);

  useEffect(() => {
    if (!isActive) return;
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [isActive, load]);

  const run = () => {
    setRunning(true);
    setRunError(null);
    runTraffyAnalysis()
      .then(setData)
      .catch((e) => setRunError(e.message === 'forbidden'
        ? 'สั่งวิเคราะห์ใหม่ได้เฉพาะทีมปฏิบัติการ (เครือข่ายภายใน)'
        : 'วิเคราะห์ไม่สำเร็จ ลองใหม่อีกครั้ง'))
      .finally(() => setRunning(false));
  };

  const header = (
    <SectionHeader
      id="traffy-ai"
      title="AI วิเคราะห์เรื่องที่ประชาชนแจ้งน้ำท่วม"
      description="Traffy Fondue 6 ชม.ล่าสุด · Qwen อ่านข้อความทุกเรื่อง สรุปเขตที่ต้องจับตา ปัญหาที่พบ และเรื่องที่ควรส่งทีมก่อน"
      action={<Button size="sm" loading={running || data?.running} onClick={run}>วิเคราะห์ใหม่</Button>}
    />
  );

  if (!data?.report) {
    return (
      <Card className="p-5">
        {header}
        {failed
          ? <EmptyState title="โหลดผลวิเคราะห์ไม่สำเร็จ" action={<Button size="sm" onClick={load}>ลองใหม่</Button>} />
          : <><p className="text-sm text-slate-600 my-3">AI กำลังอ่านเรื่องที่ประชาชนแจ้ง ...</p><Skeleton className="h-32" /></>}
      </Card>
    );
  }

  const r = data.report;
  const st = data.stats || {};
  return (
    <Card className="p-5">
      {header}
      <p className="text-xs text-slate-500 mt-1">
        {data.source === 'local' ? `${data.model} · ` : 'กฎพื้นฐาน (ออฟไลน์) · '}
        {fmtDateTime(data.generated_at)} ({agoText(data.generated_at)}) · วิเคราะห์อัตโนมัติทุก {Math.round((data.interval_s || 600) / 60)} นาที
        {data.error && <span className="text-amber-700"> · AI ไม่ตอบ ใช้กฎพื้นฐานแทน</span>}
      </p>
      {runError && <p className="text-xs text-red-700 mt-1" role="alert">{runError}</p>}

      <div className="mt-3 flex flex-col gap-4">
        <div>
          <p className="text-[15px] font-semibold text-slate-900">{r.headline}</p>
          <p className="text-[13px] text-slate-700 mt-1">{r.summary}</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-[1fr_1.4fr] gap-4">
          <div>
            <p className="text-xs font-semibold text-slate-700 mb-1">
              เรื่องแจ้งรายชั่วโมง <span className="font-normal text-slate-500">· รวม {fmtNum(st.total)} เรื่อง</span>
            </p>
            <HourBars byHour={st.by_hour} />
            {r.trend && <p className="text-xs text-slate-600 mt-1.5">{r.trend}</p>}
          </div>
          <div>
            <p className="text-xs font-semibold text-slate-700 mb-1">ระดับน้ำที่แจ้ง</p>
            <DepthBar depths={st.depths} total={st.total} />
            {st.states && (
              <p className="text-xs text-slate-600 mt-2">
                สถานะเรื่อง: {Object.entries(st.states).map(([k, n]) => `${k} ${n}`).join(' · ')}
              </p>
            )}
          </div>
        </div>

        {r.hotspots?.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-slate-700 mb-2">เขตที่ต้องจับตา</p>
            <ul className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {r.hotspots.map((h) => (
                <li key={h.district} className="rounded-lg border border-slate-200 p-3 flex gap-3">
                  <span className={`w-1 rounded-full shrink-0 ${LEVEL_BAR[h.level] || 'bg-slate-300'}`} aria-hidden="true" />
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-semibold text-slate-900">{h.district}</span>
                      <Badge tone={LEVEL_TONE[h.level] || 'neutral'}>{h.level}</Badge>
                      {h.zone && <Badge>{h.zone}</Badge>}
                    </div>
                    <p className="text-xs text-slate-500 mt-0.5 tabular-nums">
                      {h.reports} เรื่อง · หัวเข่าขึ้นไป {h.deep_reports} · รอรับเรื่อง {h.waiting}
                    </p>
                    <p className="text-[13px] text-slate-700 mt-0.5">{h.issues}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}

        {r.themes?.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-slate-700 mb-1">ปัญหาที่ประชาชนแจ้งซ้ำ</p>
            <ul className="space-y-1.5">
              {r.themes.map((t, i) => (
                <li key={i} className="text-[13px] text-slate-700">
                  <span className="font-medium text-slate-900">{t.title}</span> · {t.detail}
                </li>
              ))}
            </ul>
          </div>
        )}

        {r.urgent?.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-slate-700 mb-1">เรื่องที่ควรส่งทีมก่อน</p>
            <ul className="divide-y divide-slate-100">
              {r.urgent.map((u) => (
                <li key={u.id} className="py-2">
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <a href={u.url} target="_blank" rel="noreferrer" className="font-medium text-blue-700 hover:underline">{u.id}</a>
                    {u.district && <span className="text-slate-700">เขต{u.district}</span>}
                    {u.depth && <Badge tone={u.depth === 'เอวขึ้นไป' || u.depth === 'ต้นขา' ? 'red' : 'yellow'}>{u.depth}</Badge>}
                    {u.state && <span className="text-slate-500">{u.state}</span>}
                    {u.ts && <span className="text-slate-500">{agoText(u.ts)}</span>}
                  </div>
                  <p className="text-[13px] text-slate-800 mt-0.5">{u.reason}</p>
                  {u.text && <p className="text-xs text-slate-500 mt-0.5 line-clamp-2">“{u.text}”</p>}
                </li>
              ))}
            </ul>
          </div>
        )}

        {r.actions?.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-slate-700 mb-1">สำหรับทีมปฏิบัติการ</p>
            <ul className="list-disc pl-5 space-y-0.5 text-[13px] text-slate-700">
              {r.actions.map((a, i) => <li key={i}>{a}</li>)}
            </ul>
          </div>
        )}
      </div>
    </Card>
  );
}
