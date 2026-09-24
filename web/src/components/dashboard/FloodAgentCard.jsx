// Flood analyst agent (flood_agent.py): Claude reads the road sensors, river/canal gauges, rain outlook,
// Traffy reports, TMD warnings and road risk through tools and files one situation report. The server
// re-runs it on a timer; operators can run it now or ask it a question (POST is operator-only).
import { useCallback, useEffect, useState } from 'react';
import { fetchFloodAgent, runFloodAgent } from '../../lib/api.js';
import { Card, Badge, Button, SectionHeader, Skeleton, EmptyState, FOCUS } from './ui.jsx';
import { StatusBanner } from './primitives.jsx';
import { fmtTime, agoText } from './format.js';

const POLL_MS = 60000;
const LEVEL = {
  normal: { tone: 'green', label: 'ปกติ', bar: 'bg-emerald-500' },
  watch: { tone: 'yellow', label: 'เฝ้าระวัง', bar: 'bg-amber-400' },
  warning: { tone: 'red', label: 'เตือนภัย', bar: 'bg-orange-500' },
  critical: { tone: 'red', label: 'วิกฤต', bar: 'bg-red-600' },
};
const SOURCE = { claude: 'Claude', local: 'โมเดลในเครื่อง', gemini: 'Gemini', rules: 'กฎพื้นฐาน (ออฟไลน์)' };
const CONFIDENCE = { low: 'ต่ำ', medium: 'ปานกลาง', high: 'สูง' };
const TOOL_TH = {
  get_road_sensors: 'เซ็นเซอร์น้ำบนถนน',
  get_rivers_canals: 'แม่น้ำ/คลอง',
  get_rain_outlook: 'พยากรณ์ฝน',
  get_citizen_reports: 'Traffy Fondue',
  get_weather_warnings: 'ประกาศกรมอุตุฯ',
  get_road_risk: 'ความเสี่ยงรายถนน',
  get_bma_events: 'ศูนย์จราจร กทม.',
};

function List({ title, items }) {
  if (!items?.length) return null;
  return (
    <div>
      <p className="text-xs font-semibold text-slate-700 mb-1">{title}</p>
      <ul className="list-disc pl-5 space-y-0.5 text-[13px] text-slate-700">
        {items.map((t, i) => <li key={i}>{t}</li>)}
      </ul>
    </div>
  );
}

export default function FloodAgentCard({ isActive, onOpenRoad }) {
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);
  const [running, setRunning] = useState(false);
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState(null);
  const [runError, setRunError] = useState(null);

  const load = useCallback(() => {
    return fetchFloodAgent()
      .then((d) => { setData(d); setFailed(false); })
      .catch(() => setFailed(true));
  }, []);

  useEffect(() => {
    if (!isActive) return;
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [isActive, load]);

  const run = (q) => {
    setRunning(true);
    setRunError(null);
    runFloodAgent(q)
      .then((r) => {
        if (q) setAnswer(r);
        return load();
      })
      .catch((e) => setRunError(e.message === 'forbidden'
        ? 'สั่งวิเคราะห์ได้เฉพาะทีมปฏิบัติการ (เครือข่ายภายใน)'
        : 'วิเคราะห์ไม่สำเร็จ ลองใหม่อีกครั้ง'))
      .finally(() => setRunning(false));
  };

  if (!data) {
    return failed
      ? <Card className="p-5"><EmptyState title="โหลดรายงาน AI น้ำท่วมไม่สำเร็จ" action={<Button size="sm" onClick={load}>ลองใหม่</Button>} /></Card>
      : <Skeleton className="h-48" />;
  }

  const r = data.report;
  const lv = LEVEL[r?.overall_level] || LEVEL.watch;
  const busy = running || data.running;

  return (
    <Card className="p-5" aria-labelledby="flood-agent">
      <SectionHeader
        id="flood-agent"
        title="AI วิเคราะห์สถานการณ์น้ำท่วม"
        description={r
          ? `${SOURCE[r.source] || r.source} · ${fmtTime(r.generated_at)} น. (${agoText(r.generated_at)}) · วิเคราะห์อัตโนมัติทุก ${Math.round((data.interval_s || 900) / 60)} นาที`
          : 'ยังไม่มีรายงาน รอบแรกจะเริ่มหลังเปิดเซิร์ฟเวอร์ราว 2 นาที'}
        action={
          <div className="flex items-center gap-2">
            {r && <Badge tone={lv.tone} dot>{lv.label}</Badge>}
            <Button size="sm" onClick={() => run('')} loading={busy}>{busy ? 'กำลังวิเคราะห์' : 'วิเคราะห์ใหม่'}</Button>
          </div>
        }
      />

      {runError && <p role="alert" className="mt-3 text-xs text-red-700">{runError}</p>}
      {data.error && r?.source !== 'claude' && (
        <p className="mt-3 text-xs text-amber-700">ใช้ผู้ให้บริการสำรอง: {data.error}</p>
      )}

      {r && (
        <div className="mt-4 flex flex-col gap-4">
          <StatusBanner tone={lv.tone} label={lv.label}>
            <span className="font-semibold">{r.headline}</span>
            {r.summary && <span className="block mt-1 text-[13px] opacity-90">{r.summary}</span>}
          </StatusBanner>

          {r.districts?.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-slate-700 mb-2">เขตที่ต้องจับตา</p>
              <ul className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {r.districts.map((d) => {
                  const dl = LEVEL[d.level] || LEVEL.watch;
                  return (
                    <li key={d.name} className="rounded-lg border border-slate-200 p-3 flex gap-3">
                      <span className={`w-1 rounded-full shrink-0 ${dl.bar}`} aria-hidden="true" />
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold text-slate-900">{d.name}</span>
                          <Badge tone={dl.tone}>{dl.label}</Badge>
                        </div>
                        <p className="text-[13px] text-slate-700 mt-0.5">{d.reason}</p>
                        {d.outlook && <p className="text-xs text-slate-500 mt-0.5">คาดการณ์: {d.outlook}</p>}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}

          {r.roads_to_avoid?.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-slate-700 mb-2">ถนนที่ควรเลี่ยง</p>
              <ul className="flex flex-wrap gap-2">
                {r.roads_to_avoid.map((x, i) => (
                  <li key={`${x.road}-${i}`}>
                    <button
                      type="button"
                      onClick={() => onOpenRoad?.(x.road)}
                      title={x.advice}
                      className={`cursor-pointer inline-flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-1.5 text-[13px] text-red-800 hover:border-red-400 ${FOCUS}`}
                    >
                      <span className="font-medium">{x.road}</span>
                      {x.depth_cm != null && <span className="tabular-nums">{Math.round(x.depth_cm)} ซม.</span>}
                      {x.district && <span className="text-xs text-red-700/80">{x.district}</span>}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {r.outlook && (
            <div>
              <p className="text-xs font-semibold text-slate-700 mb-1">แนวโน้ม 1-6 ชั่วโมง</p>
              <p className="text-[13px] text-slate-700">{r.outlook}</p>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <List title="คำแนะนำประชาชน" items={r.actions?.public} />
            <List title="สำหรับทีมปฏิบัติการ" items={r.actions?.operators} />
          </div>

          {data.history?.length > 1 && (
            <div>
              <p className="text-xs font-semibold text-slate-700 mb-1">ระดับย้อนหลัง</p>
              <div className="flex gap-0.5 h-3" role="img" aria-label="ระดับสถานการณ์ย้อนหลังจากเก่าไปใหม่">
                {data.history.map((h) => (
                  <span
                    key={h.ts}
                    title={`${fmtTime(h.ts)} น. ${LEVEL[h.level]?.label || h.level}: ${h.headline}`}
                    className={`flex-1 rounded-sm ${LEVEL[h.level]?.bar || 'bg-slate-300'}`}
                  />
                ))}
              </div>
            </div>
          )}

          <p className="text-xs text-slate-500">
            ความเชื่อมั่น {CONFIDENCE[r.confidence] || r.confidence || '-'}
            {r.steps?.length > 0 && ` · แหล่งที่ AI ตรวจ: ${[...new Set(r.steps.map((s) => TOOL_TH[s.tool] || s.tool))].join(', ')}`}
            {r.took_s != null && ` · ใช้เวลา ${r.took_s} วินาที`}
            {r.data_gaps?.length > 0 && ` · ข้อมูลที่ขาด: ${r.data_gaps.join(', ')}`}
          </p>
        </div>
      )}

      <form
        className="mt-4 flex flex-wrap gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (question.trim() && !busy) run(question.trim());
        }}
      >
        <label htmlFor="flood-agent-q" className="sr-only">ถาม AI วิเคราะห์น้ำท่วม</label>
        <input
          id="flood-agent-q"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          maxLength={300}
          placeholder="ถามเจาะจง เช่น เขตบางนาจะท่วมไหมใน 3 ชั่วโมงนี้"
          className={`flex-1 min-w-[220px] h-8 rounded-lg border border-slate-300 px-3 text-[13px] ${FOCUS}`}
        />
        <Button size="sm" variant="primary" type="submit" disabled={!question.trim()} loading={running && !!question.trim()}>ถาม AI</Button>
      </form>
      {answer?.answer && (
        <div className="mt-3 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3">
          <p className="text-xs text-blue-800 mb-1">ถาม: {answer.question}</p>
          <p className="text-[13px] text-slate-800 whitespace-pre-line">{answer.answer}</p>
        </div>
      )}
    </Card>
  );
}
