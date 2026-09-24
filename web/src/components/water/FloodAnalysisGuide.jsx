// Flood outlook card on the Water Forecast page. Every tab is written by the AI model (water_agent.py) from
// the live sources; the server re-checks them every 5 minutes and re-runs the model when they change.
import { useCallback, useEffect, useState } from 'react';
import { fetchWaterAgent, runWaterAgent } from '../../lib/api.js';
import { Card, Badge, Button, Skeleton, EmptyState } from '../dashboard/ui.jsx';
import { fmtDateTime, agoText } from '../dashboard/format.js';

const POLL_MS = 60000;
const TABS = [
  ['forecast', '🔮 คาดการณ์สถานการณ์'],
  ['diagnosis', '🔍 วิเคราะห์ความเสี่ยง 3 น้ำ (เหนือ/หนุน/ฝน)'],
  ['action', '🛡️ แนวทางแก้ไข & มาตรการภาครัฐ'],
  ['public', '🚗 คู่มือประชาชน & ผู้ใช้รถ'],
];
const LEVEL = {
  normal: { tone: 'green', label: 'ปกติ', box: 'bg-emerald-50/70 border-emerald-200 text-emerald-900' },
  watch: { tone: 'yellow', label: 'เฝ้าระวัง', box: 'bg-amber-50/70 border-amber-200 text-amber-900' },
  warning: { tone: 'red', label: 'เตือนภัย', box: 'bg-orange-50/70 border-orange-200 text-orange-900' },
  critical: { tone: 'red', label: 'วิกฤต', box: 'bg-red-50/70 border-red-200 text-red-900' },
};
const ZONE = {
  red: { dot: 'bg-red-600', box: 'border-red-200 bg-red-50/30', foot: 'border-red-100 text-red-700' },
  yellow: { dot: 'bg-amber-500', box: 'border-amber-200 bg-amber-50/30', foot: 'border-amber-100 text-amber-700' },
  blue: { dot: 'bg-blue-500', box: 'border-blue-200 bg-blue-50/30', foot: 'border-blue-100 text-blue-700' },
  green: { dot: 'bg-emerald-500', box: 'border-emerald-200 bg-emerald-50/30', foot: 'border-emerald-100 text-emerald-700' },
};
const WATERS = [
  ['upstream', '🏔️', '1. ปริมาณน้ำเหนือ (Upstream)', 'เขื่อนและแม่น้ำตอนบน'],
  ['tide', '🌊', '2. น้ำทะเลหนุน (Tidal Surge)', 'ปากอ่าวไทยและสถานีปากแม่น้ำ'],
  ['rain', '🌧️', '3. น้ำฝนและน้ำในพื้นที่ (Local Rain)', 'คูคลอง ท่อระบายน้ำ และถนน'],
];
const MEASURES = [
  ['immediate', '⚡', 'มาตรการเร่งด่วน (0 - 24 ชม.)'],
  ['medium', '🔧', 'มาตรการระยะกลาง (1 - 3 เดือน)'],
  ['long', '🏗️', 'มาตรการโครงสร้างระยะยาว'],
];

function Items({ items }) {
  return (
    <ul className="space-y-1.5 text-[12px] text-slate-700 leading-relaxed">
      {(items || []).map((it, i) => (
        <li key={i} className="flex gap-1.5">
          <span className="text-slate-400">•</span>
          <span><strong>{it.title}:</strong> {it.detail}</span>
        </li>
      ))}
    </ul>
  );
}

export default function FloodAnalysisGuide({ isActive, onNavigate, onAsk }) {
  const [tab, setTab] = useState('forecast');
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState(null);

  const load = useCallback(() => {
    return fetchWaterAgent()
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
    runWaterAgent()
      .then(setData)
      .catch((e) => setRunError(e.message === 'forbidden'
        ? 'สั่งวิเคราะห์ใหม่ได้เฉพาะทีมปฏิบัติการ (เครือข่ายภายใน)'
        : 'วิเคราะห์ไม่สำเร็จ ลองใหม่อีกครั้ง'))
      .finally(() => setRunning(false));
  };

  const r = data?.report;
  const lv = LEVEL[r?.level] || LEVEL.watch;
  const busy = running || data?.running;

  return (
    <Card className="p-5 border-blue-200 bg-white shadow-sm overflow-hidden">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-100">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-600 text-white flex items-center justify-center text-xl shrink-0 shadow-sm">📋</div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="text-base font-bold text-slate-900">วิเคราะห์และคาดการณ์สถานการณ์น้ำท่วม พร้อมแนวทางป้องกัน</h3>
              {r && <Badge tone={lv.tone} dot>{lv.label}</Badge>}
            </div>
            <p className="text-xs text-slate-600 mt-0.5">
              {r
                ? `AI ${r.model} · วิเคราะห์ ${fmtDateTime(r.generated_at)} (${agoText(r.generated_at)}) · ดึงข้อมูลใหม่ทุก ${Math.round((data.interval_s || 300) / 60)} นาที วิเคราะห์ใหม่เมื่อข้อมูลเปลี่ยน`
                : 'AI อ่านเซ็นเซอร์น้ำบนถนน แม่น้ำ/คลอง น้ำทะเลหนุน เขื่อน พยากรณ์ฝน Traffy และประกาศกรมอุตุฯ'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Button size="sm" onClick={run} loading={busy}>{busy ? 'กำลังวิเคราะห์' : 'วิเคราะห์ใหม่'}</Button>
          <Button size="sm" onClick={() => onNavigate && onNavigate('map')} className="text-xs">🗺️ ดูบนแผนที่</Button>
          <Button size="sm" variant="primary" onClick={() => onAsk && onAsk('วิเคราะห์สถานการณ์น้ำท่วมในเขตของฉันและเส้นทางเลี่ยงน้ำท่วม')} className="text-xs">
            🤖 ถาม AI เรื่องน้ำท่วม
          </Button>
        </div>
      </div>

      {runError && <p role="alert" className="mt-3 text-xs text-red-700">{runError}</p>}
      {data?.error && <p className="mt-3 text-xs text-amber-700">วิเคราะห์รอบล่าสุดไม่สำเร็จ{r ? ' แสดงผลรอบก่อนหน้า' : ''}: {data.error}</p>}

      {!r ? (
        <div className="mt-4">
          {failed
            ? <EmptyState title="โหลดบทวิเคราะห์ไม่สำเร็จ" action={<Button size="sm" onClick={load}>ลองใหม่</Button>} />
            : <><p className="text-sm text-slate-600 mb-3">AI กำลังวิเคราะห์ข้อมูลน้ำ รอบแรกเริ่มหลังเปิดเซิร์ฟเวอร์ราว 2 นาที ...</p><Skeleton className="h-40" /></>}
        </div>
      ) : (
        <>
          <div role="tablist" aria-label="หมวดบทวิเคราะห์น้ำท่วม" className="mt-4 flex items-center gap-1.5 border-b border-slate-100 pb-2 overflow-x-auto scroll-soft">
            {TABS.map(([id, label]) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={tab === id}
                onClick={() => setTab(id)}
                className={`cursor-pointer px-3.5 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-colors ${
                  tab === id ? 'bg-blue-600 text-white shadow-sm' : 'bg-slate-50 text-slate-700 hover:bg-slate-100'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {tab === 'forecast' && (
            <div className="mt-4 space-y-3.5">
              <div className={`rounded-xl border p-3.5 ${lv.box}`}>
                <h4 className="text-xs font-bold uppercase tracking-wide mb-1.5">⚠️ สรุปภาพรวมการคาดการณ์ · {r.status_label}</h4>
                <p className="text-xs leading-relaxed">{r.outlook_summary}</p>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {(r.zones || []).map((z, i) => {
                  const zs = ZONE[z.tone] || ZONE.blue;
                  return (
                    <div key={i} className={`rounded-xl border p-3.5 flex flex-col justify-between ${zs.box}`}>
                      <div>
                        <div className="flex items-center justify-between gap-1 mb-1.5">
                          <span className="text-xs font-bold text-slate-900 flex items-center gap-1.5">
                            <span className={`w-2 h-2 rounded-full ${zs.dot}`} />
                            {i + 1}. {z.name}
                          </span>
                          <Badge tone={z.tone === 'blue' ? 'blue' : z.tone === 'green' ? 'green' : z.tone === 'red' ? 'red' : 'yellow'} className="text-[10px]">{z.badge}</Badge>
                        </div>
                        <p className="text-[11px] text-slate-700 leading-relaxed mt-1"><strong>พื้นที่เสี่ยง:</strong> {z.areas}</p>
                        <p className="text-[11px] text-slate-600 leading-relaxed mt-1"><strong>คาดการณ์:</strong> {z.forecast}</p>
                      </div>
                      <div className={`mt-2.5 pt-2 border-t text-[10px] font-medium ${zs.foot}`}>⚡ ข้อมูลอ้างอิง: {z.evidence}</div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {tab === 'diagnosis' && (
            <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3">
              {WATERS.map(([key, icon, title, sub]) => {
                const w = r.three_waters?.[key] || {};
                return (
                  <div key={key} className="rounded-xl border border-slate-200 p-3.5">
                    <div className="flex items-start gap-2 mb-2">
                      <span className="text-xl">{icon}</span>
                      <div>
                        <h4 className="text-xs font-bold text-slate-900">{title}</h4>
                        <span className="text-[10px] text-slate-500">{sub}</span>
                      </div>
                    </div>
                    {w.status && <Badge tone="blue" className="text-[10px] mb-2">{w.status}</Badge>}
                    <ul className="list-disc pl-4 space-y-1 text-[11px] text-slate-700 leading-relaxed">
                      {(w.points || []).map((p, i) => <li key={i}>{p}</li>)}
                      {w.impact && <li><strong>ผลกระทบ:</strong> {w.impact}</li>}
                    </ul>
                  </div>
                );
              })}
            </div>
          )}

          {tab === 'action' && (
            <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3">
              {MEASURES.map(([key, icon, title]) => (
                <div key={key} className="rounded-xl border border-slate-200 p-3.5">
                  <h4 className="text-xs font-bold text-slate-900 mb-2 flex items-center gap-1.5"><span>{icon}</span>{title}</h4>
                  <Items items={r.measures?.[key]} />
                </div>
              ))}
            </div>
          )}

          {tab === 'public' && (
            <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3">
              <div className="rounded-xl border border-slate-200 p-3.5">
                <h4 className="text-xs font-bold text-slate-900 mb-2">🚗 คำแนะนำสำหรับผู้ขับขี่และสัญจรบนถนน</h4>
                <Items items={r.public?.drivers} />
              </div>
              <div className="rounded-xl border border-slate-200 p-3.5">
                <h4 className="text-xs font-bold text-slate-900 mb-2">🏠 คำแนะนำสำหรับผู้อยู่อาศัยริมน้ำและพื้นที่ลุ่มต่ำ</h4>
                <Items items={r.public?.residents} />
              </div>
            </div>
          )}
        </>
      )}
    </Card>
  );
}
