// BMA traffic-risk analysis (riskbkk_agent.py): the AI model reads the per-district / per-month numbers
// worked out from the riskbkk layers and the Thai RSC accidents 2566-2568 (risk points, congestion
// points, building sites) and
// writes one Thai report. The numbers themselves are drawn here too, so they stay visible without the model.
import { useCallback, useEffect, useState } from 'react';
import { fetchRiskAnalysis, runRiskAnalysis } from '../../lib/api.js';
import { Card, Badge, Button, SectionHeader, Skeleton, EmptyState } from './ui.jsx';
import { StatTile, StatusBanner } from './primitives.jsx';
import { fmtDateTime, fmtNum } from './format.js';

const LEVEL_TONE = { สูง: 'red', ปานกลาง: 'yellow', ต่ำ: 'green' };
const LEVEL_BAR = { สูง: 'bg-red-500', ปานกลาง: 'bg-amber-400', ต่ำ: 'bg-emerald-500' };

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

function Bars({ values, labels, label }) {
  const max = Math.max(1, ...values);
  return (
    <div role="img" aria-label={label} className="flex items-end gap-0.5 h-28">
      {values.map((v, i) => (
        <div key={i} className="flex-1 flex flex-col items-center justify-end h-full" title={`${labels[i]}: ${fmtNum(v)}`}>
          <div className="w-full rounded-t bg-red-500/80" style={{ height: `${(v / max) * 100}%` }} />
          <span className="text-[10px] text-slate-500 mt-0.5 tabular-nums">{labels[i]}</span>
        </div>
      ))}
    </div>
  );
}

export default function RiskAnalysisCard({ isActive }) {
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState(null);

  const load = useCallback(() => {
    return fetchRiskAnalysis()
      .then((d) => { setData(d); setFailed(false); })
      .catch(() => setFailed(true));
  }, []);

  useEffect(() => {
    if (!isActive) return;
    load();
  }, [isActive, load]);

  // the first run at server start takes ~20 s; poll until it lands
  useEffect(() => {
    if (!isActive || !data || (data.report && !data.running)) return;
    const id = setTimeout(load, 5000);
    return () => clearTimeout(id);
  }, [isActive, data, load]);

  const run = () => {
    setRunning(true);
    setRunError(null);
    runRiskAnalysis()
      .then(setData)
      .catch((e) => setRunError(e.message === 'forbidden'
        ? 'สั่งวิเคราะห์ใหม่ได้เฉพาะทีมปฏิบัติการ (เครือข่ายภายใน)'
        : 'วิเคราะห์ไม่สำเร็จ ลองใหม่อีกครั้ง'))
      .finally(() => setRunning(false));
  };

  if (!data?.report) {
    return failed
      ? <Card className="p-5"><EmptyState title="โหลดผลวิเคราะห์จุดเสี่ยงไม่สำเร็จ" action={<Button size="sm" onClick={load}>ลองใหม่</Button>} /></Card>
      : <Card className="p-5"><p className="text-sm text-slate-600 mb-3">AI กำลังวิเคราะห์ข้อมูลจุดเสี่ยง กทม. ...</p><Skeleton className="h-40" /></Card>;
  }

  const r = data.report;
  const s = data.stats;
  const solve = s.risk100.solve_status || {};
  const busy = running || data.running;
  const months = s.accident.by_month || [];

  return (
    <div className="flex flex-col gap-4">
      <Card className="p-5" aria-labelledby="risk-ai">
        <SectionHeader
          id="risk-ai"
          title="AI วิเคราะห์จุดเสี่ยงจราจร กทม."
          description={`${data.source === 'local' ? data.model : 'กฎพื้นฐาน (ออฟไลน์)'} · ${fmtDateTime(data.generated_at)} · ใช้เวลา ${data.took_s} วิ · ข้อมูลจากแผนที่จุดเสี่ยงกรุงเทพมหานคร (riskbkk)`}
          action={<Button size="sm" onClick={run} loading={busy}>{busy ? 'กำลังวิเคราะห์' : 'วิเคราะห์ใหม่'}</Button>}
        />
        {runError && <p role="alert" className="mt-3 text-xs text-red-700">{runError}</p>}
        {data.error && data.source === 'rules' && (
          <p className="mt-3 text-xs text-amber-700">เชื่อมต่อโมเดล AI ไม่ได้ ใช้รายงานตามเกณฑ์แทน: {data.error}</p>
        )}
        <div className="mt-4 flex flex-col gap-4">
          <StatusBanner tone="red" label="สรุป">
            <span className="font-semibold">{r.headline}</span>
            {r.summary && <span className="block mt-1 text-[13px] opacity-90">{r.summary}</span>}
          </StatusBanner>

          {r.key_findings?.length > 0 && (
            <ul className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {r.key_findings.map((k, i) => (
                <li key={i} className="rounded-lg border border-slate-200 p-3">
                  <p className="text-sm font-semibold text-slate-900">{k.title}</p>
                  <p className="text-[13px] text-slate-700 mt-0.5">{k.detail}</p>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Card>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatTile label="อุบัติเหตุ ปี 2566–68" value={fmtNum(s.accident.cases)} sub={`บาดเจ็บ ${fmtNum(s.accident.injured)} · เสียชีวิต ${fmtNum(s.accident.dead)} (ThaiRSC)`} tone="red" />
        <StatTile label="จุดเสี่ยงอุบัติเหตุ 2566–68" value={fmtNum(s.counts.accident_risk)} sub="ประกาศโดย กทม." tone="yellow" />
        <StatTile label="100 จุดเสี่ยง แก้เสร็จ" value={`${solve['ดำเนินการแล้วเสร็จ'] || 0}/100`} sub={`กำลังทำ ${solve['อยู่ระหว่างดำเนินการ'] || 0} · รอ ${solve['รอดำเนินการ'] || 0}`} tone="blue" />
        <StatTile label="จุดฝืด (รถติดประจำ)" value={fmtNum(s.counts.friction)} sub={`ก่อสร้างอาคารใหญ่ ${fmtNum(s.counts.construction)} แห่ง`} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card className="p-5">
          <SectionHeader id="risk-hotspots" title="เขตที่ควรจัดการก่อน" description="AI จัดลำดับจากตารางรายเขตด้านล่าง" />
          <ul className="mt-3 flex flex-col gap-2">
            {(r.hotspots || []).map((h) => (
              <li key={h.district} className="rounded-lg border border-slate-200 p-3 flex gap-3">
                <span className={`w-1 rounded-full shrink-0 ${LEVEL_BAR[h.level] || 'bg-slate-400'}`} aria-hidden="true" />
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-slate-900">{h.district}</span>
                    <Badge tone={LEVEL_TONE[h.level] || 'neutral'}>{h.level}</Badge>
                  </div>
                  <p className="text-[13px] text-slate-700 mt-0.5">{h.reasons}</p>
                </div>
              </li>
            ))}
          </ul>
        </Card>

        <Card className="p-5">
          <SectionHeader id="risk-time" title="ช่วงเวลาที่เกิดอุบัติเหตุ" description={`รายเดือน รวม ${s.accident.period}${(s.accident.by_year || []).length ? ' · ' + s.accident.by_year.map((y) => `${y.year}: ${fmtNum(y.n)}`).join(' · ') : ''}`} />
          <div className="mt-3">
            <Bars values={months.map((m) => m.n)} labels={months.map((m) => m.month)} label="จำนวนอุบัติเหตุรายเดือน" />
          </div>
          <div className="mt-3 grid grid-cols-7 gap-1 text-center">
            {s.accident.by_weekday.map((d) => (
              <div key={d.day} className="rounded-md bg-slate-100 px-1 py-1.5">
                <p className="text-[11px] text-slate-600">{d.day}</p>
                <p className="text-xs font-semibold tabular-nums text-slate-900">{fmtNum(d.n)}</p>
              </div>
            ))}
          </div>
          {r.time_patterns && <p className="mt-3 text-[13px] text-slate-700">{r.time_patterns}</p>}
        </Card>
      </div>

      <Card className="p-5">
        <SectionHeader id="risk-districts" title="ตารางความเสี่ยงรายเขต" description="คะแนน = อุบัติเหตุ 2566–68 ×3 + จุดเสี่ยงประกาศ ×2 + 100 จุดเสี่ยง ×2 + จุดฝืด ×2 + ก่อสร้าง ×1 (เทียบกับเขตที่สูงสุด)" />
        <div className="mt-3 overflow-x-auto scroll-soft">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="text-left text-xs text-slate-600 border-b border-slate-200">
                <th className="py-2 pr-3 font-medium">เขต</th>
                <th className="py-2 pr-3 font-medium">คะแนน</th>
                <th className="py-2 pr-3 font-medium text-right">อุบัติเหตุ 66–68</th>
                <th className="py-2 pr-3 font-medium text-right">เสียชีวิต</th>
                <th className="py-2 pr-3 font-medium text-right">จุดเสี่ยง 66–68</th>
                <th className="py-2 pr-3 font-medium text-right">100 จุดเสี่ยง (เหตุ)</th>
                <th className="py-2 pr-3 font-medium text-right">จุดฝืด</th>
                <th className="py-2 font-medium text-right">ก่อสร้าง</th>
              </tr>
            </thead>
            <tbody>
              {s.districts.slice(0, 12).map((d) => (
                <tr key={d.district} className="border-b border-slate-100">
                  <td className="py-1.5 pr-3 text-slate-900 font-medium whitespace-nowrap">{d.district}</td>
                  <td className="py-1.5 pr-3 w-40">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-1.5 rounded-full bg-slate-100"><div className="h-1.5 rounded-full bg-red-500" style={{ width: `${d.score}%` }} /></div>
                      <span className="tabular-nums text-slate-700 w-6 text-right">{d.score}</span>
                    </div>
                  </td>
                  <td className="py-1.5 pr-3 text-right tabular-nums">{fmtNum(d.accidents)}</td>
                  <td className="py-1.5 pr-3 text-right tabular-nums">{fmtNum(d.dead)}</td>
                  <td className="py-1.5 pr-3 text-right tabular-nums">{d.risk_points_2566_68}</td>
                  <td className="py-1.5 pr-3 text-right tabular-nums">{d.risk100_points} ({fmtNum(d.risk100_cases)})</td>
                  <td className="py-1.5 pr-3 text-right tabular-nums">{d.friction}</td>
                  <td className="py-1.5 text-right tabular-nums">{d.construction}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card className="p-5">
        <SectionHeader id="risk-actions" title="ข้อเสนอแนะจาก AI" />
        <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-4">
          <List title="ตำรวจ / จราจร" items={r.recommendations?.police} />
          <List title="วิศวกรรมจราจร (สจส.)" items={r.recommendations?.engineering} />
          <List title="ประชาชน" items={r.recommendations?.public} />
        </div>
        {r.data_caveats?.length > 0 && (
          <div className="mt-4 pt-3 border-t border-slate-100">
            <List title="ข้อจำกัดของข้อมูล" items={r.data_caveats} />
          </div>
        )}
      </Card>
    </div>
  );
}
