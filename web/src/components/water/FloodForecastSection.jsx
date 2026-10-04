// "คาดการณ์น้ำท่วม" tab of the Water page: which provinces are flooded today and how each may go in the next
// 7 days (a computed score from gauges, dams, reservoirs and rain, read by Qwen), and the floods people report
// in the whole country (/api/flood/forecast, national_forecast.py).
import { useMemo, useState } from 'react';
import { Badge, Card, ErrorState, FOCUS, SectionHeader, Skeleton } from '../dashboard/ui.jsx';
import { StatusBanner } from '../dashboard/primitives.jsx';
import { agoText, fmtDateTime } from '../dashboard/format.js';
import { CHIP_OFF, CHIP_ON, REGIONS, RISK, damLater, mcm, sum, useFloodForecast } from './forecastData.js';

const NOW = {
  critical: { label: 'วันนี้: วิกฤต', tone: 'red' },
  flood: { label: 'วันนี้: น้ำล้นตลิ่ง/ท่วม', tone: 'yellow' },
  watch: { label: 'วันนี้: เฝ้าระวัง', tone: 'blue' },
  normal: { label: 'วันนี้: ปกติ', tone: 'green' },
};
const REPORTS_SHOWN = 30;
// Day cell colours, light and dark (same look as the 6-hour zone table on the เขตเสี่ยงน้ำท่วม tab)
const CELL = {
  normal: 'bg-emerald-50 border-emerald-200 text-emerald-800 dark:bg-emerald-950/30 dark:border-emerald-800/50 dark:text-emerald-300',
  watch: 'bg-amber-50 border-amber-300 text-amber-900 dark:bg-amber-950/40 dark:border-amber-700/60 dark:text-amber-200',
  flood: 'bg-orange-50 border-orange-300 text-orange-900 dark:bg-orange-950/40 dark:border-orange-700/60 dark:text-orange-200',
  critical: 'bg-rose-50 border-rose-300 text-rose-900 dark:bg-rose-950/50 dark:border-rose-700/70 dark:text-rose-200',
};
const DOT = { normal: 'bg-emerald-500', watch: 'bg-amber-500', flood: 'bg-orange-500', critical: 'bg-rose-500' };
const TABLE_SHOWN = 20;
const dayLabel = (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString('th-TH', { weekday: 'short', day: 'numeric', month: 'short' });

// One row per province: today's situation, then the risk index of each of the next 7 days with that day's rain
function DailyTable({ provinces, items }) {
  const [all, setAll] = useState(false);
  const days = provinces[0]?.days || [];
  const rows = all ? provinces : provinces.slice(0, TABLE_SHOWN);
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-3 text-xs text-slate-700">
        <span className="font-medium">คะแนนเสี่ยงน้ำท่วม 0-100:</span>
        {[['normal', 'ปกติ 0-29'], ['watch', 'เฝ้าระวัง 30-49'], ['flood', 'เสี่ยงสูง 50-69'], ['critical', 'เสี่ยงสูงมาก 70-100']].map(([k, label]) => (
          <span key={k} className="inline-flex items-center gap-1.5"><span className={`w-2.5 h-2.5 rounded-full ${DOT[k]}`} />{label}</span>
        ))}
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200">
        <table className="w-full text-sm border-collapse min-w-[760px]">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-200 text-xs text-slate-600">
              <th className="text-left py-2.5 px-3 w-44 sticky left-0 bg-slate-50">จังหวัด</th>
              {days.map((d) => (
                <th key={d.day} className="text-center py-2.5 px-1 min-w-[74px]">
                  <div className="font-semibold text-slate-900">+{d.day} วัน</div>
                  <div className="text-[10px] font-normal text-slate-500">{dayLabel(d.date)}</div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((p) => {
              const risk = RISK[items[p.province]?.risk || p.level];
              return (
                <tr key={p.province}>
                  <td className="py-2.5 px-3 align-middle sticky left-0 bg-white">
                    <div className="font-semibold text-slate-900">{p.province}</div>
                    <div className="text-[11px] text-slate-500">{NOW[p.now].label}</div>
                    <div className="text-[11px] text-slate-500">7 วัน: {risk.label}</div>
                  </td>
                  {p.days.map((d) => (
                    <td key={d.day} className="p-1 align-middle">
                      <div className={`rounded-lg border text-center py-1.5 px-1 ${CELL[d.level]}`}
                        title={`${dayLabel(d.date)} · คะแนน ${d.index}/100 (${RISK[d.level].label}) · ฝน ${Math.round(d.rain)} มม.`}>
                        <div className="flex items-center justify-center gap-1">
                          <span className={`w-1.5 h-1.5 rounded-full ${DOT[d.level]}`} />
                          <span className="text-sm font-bold tabular-nums leading-none">{d.index}</span>
                        </div>
                        <div className="text-[10px] font-medium mt-1 leading-none">{RISK[d.level].label}</div>
                        <div className="text-[10px] tabular-nums mt-1 leading-none opacity-75">ฝน {Math.round(d.rain)} มม.</div>
                      </div>
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {provinces.length > TABLE_SHOWN && (
        <button type="button" onClick={() => setAll((v) => !v)} className="self-start text-xs text-blue-700 cursor-pointer">
          {all ? 'ย่อ' : `ดูทั้งหมด ${provinces.length} จังหวัด`}
        </button>
      )}
      <p className="text-[11px] text-slate-500 leading-4">
        คะแนนเริ่มจากสถานการณ์วันนี้ (วิกฤต 70 · ท่วม 50 · เฝ้าระวัง 30 · ปกติ 10) แล้วเพิ่มขึ้นตามน้ำในเขื่อนใหญ่วันนั้น ฝน 3 วันล่าสุดถึงวันนั้น
        อ่างเก็บน้ำกลางที่เต็ม เขื่อนต้นน้ำในลุ่มน้ำเดียวกันที่เต็ม และแม่น้ำที่กำลังขึ้น ยิ่งมีหลายอย่าง คะแนนยิ่งเข้าใกล้ 100
      </p>
    </div>
  );
}

function ProvinceCard({ p, ai }) {
  const risk = RISK[ai?.risk || p.level];
  const c = p.counts || {};
  return (
    <article className="rounded-xl border border-slate-200 bg-white p-4 flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-[15px] font-semibold text-slate-900">{p.province}</h3>
        <Badge tone={NOW[p.now].tone}>{NOW[p.now].label}</Badge>
        <Badge tone={risk.tone} dot>7 วัน: {risk.label}</Badge>
        <span className="text-xs text-slate-500">{p.region}</span>
      </div>
      <p className="text-sm text-slate-800 leading-6">{ai?.outlook || p.now_summary || 'ระดับน้ำปกติ'}</p>
      {ai?.advice && <p className="text-[13px] text-slate-700 leading-6"><b>คำแนะนำ:</b> {ai.advice}</p>}
      {p.why.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {p.why.map((w) => <span key={w} className="rounded-md bg-slate-100 px-2 py-0.5 text-[11px] text-slate-700">{w}</span>)}
        </div>
      )}
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
        <span>ล้นตลิ่ง <b className="text-slate-900">{c.overflow || 0}</b></span>
        <span>กำลังขึ้น <b className="text-slate-900">{c.rising || 0}</b></span>
        <span>ทางหลวงท่วม <b className="text-slate-900">{p.highways.length}</b></span>
        <span>คนแจ้ง <b className="text-slate-900">{c.reports || 0}</b></span>
        <span>ฝน 7 วัน <b className="text-slate-900">{Math.round(sum(p.rain7))} มม.</b></span>
        {p.dams.map((d) => (
          <span key={d.name}>เขื่อน{d.name} <b className="text-slate-900">{mcm(d.storage)} → {mcm(damLater(d))}</b> / {mcm(d.normal)} ล้าน ลบ.ม.</span>
        ))}
      </div>
    </article>
  );
}

export default function FloodForecastSection({ isActive }) {
  const { data, error, load } = useFloodForecast(isActive);
  const [region, setRegion] = useState('');
  const [allReports, setAllReports] = useState(false);
  const items = data?.ai?.provinces?.items || {};
  const riskOf = (p) => items[p.province]?.risk || p.level;
  const provinces = useMemo(() => (data?.provinces || []).filter((p) => !region || p.region === region), [data, region]);
  const atRisk = provinces.filter((p) => riskOf(p) !== 'normal' || p.now !== 'normal');
  const calm = provinces.filter((p) => riskOf(p) === 'normal' && p.now === 'normal');
  const reports = useMemo(
    () => (data?.provinces || []).flatMap((p) => p.reports.map((r) => ({ ...r, province: p.province }))).sort((a, b) => (b.ts || 0) - (a.ts || 0)),
    [data],
  );

  if (error && !data) return <ErrorState message="โหลดคาดการณ์น้ำท่วมไม่สำเร็จ" onRetry={load} />;
  if (!data) return <Skeleton className="h-[480px] rounded-xl" />;
  if (!data.provinces) return <p className="text-sm text-slate-600 px-1">ระบบกำลังคาดการณ์รอบแรก ลองใหม่ในอีกไม่กี่นาที</p>;

  const count = (lv) => (data.provinces || []).filter((p) => riskOf(p) === lv).length;
  const n = data.now_counts || {};

  return (
    <div className="flex flex-col gap-4">
      <StatusBanner tone={count('critical') ? 'red' : count('flood') ? 'yellow' : 'blue'}
        label={`7 วัน: เสี่ยงสูงมาก ${count('critical')} · เสี่ยงสูง ${count('flood')} · เฝ้าระวัง ${count('watch')} จังหวัด`}>
        {data.ai?.provinces?.overview || `วันนี้วิกฤต ${n.critical || 0} จังหวัด น้ำล้นตลิ่ง/ท่วม ${n.flood || 0} จังหวัด`}
      </StatusBanner>

      <Card className="p-4 flex flex-col gap-3">
        <SectionHeader
          id="forecast-title"
          title="จังหวัดที่น้ำท่วม และคาดการณ์ 7 วัน"
          description={`วันนี้วิกฤต ${n.critical || 0} · น้ำล้นตลิ่ง/ท่วม ${n.flood || 0} จังหวัด · อัปเดต ${fmtDateTime(data.updated_at)} (${agoText(data.updated_at)})`}
        />
        <div role="group" aria-label="เลือกภาค" className="flex flex-wrap gap-2">
          {[['', 'ทุกภาค'], ...REGIONS.map((r) => [r, r])].map(([id, label]) => (
            <button key={id || 'all'} type="button" aria-pressed={region === id} onClick={() => setRegion(id)}
              className={`cursor-pointer rounded-lg border px-3 h-8 text-xs font-medium ${FOCUS} ${region === id ? CHIP_ON : CHIP_OFF}`}>
              {label}
            </button>
          ))}
        </div>
        {provinces[0]?.days && <DailyTable key={region} provinces={provinces} items={items} />}
      </Card>

      {atRisk.length > 0 && <h3 className="text-sm font-semibold text-slate-900 px-1">รายละเอียดจังหวัดที่ต้องระวัง</h3>}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {atRisk.map((p) => <ProvinceCard key={p.province} p={p} ai={items[p.province]} />)}
      </div>
      {calm.length > 0 && <p className="text-xs text-slate-600 px-1">ปกติทั้งวันนี้และ 7 วันข้างหน้า {calm.length} จังหวัด: {calm.map((p) => p.province).join(' · ')}</p>}

      <Card className="p-4 flex flex-col gap-2">
        <SectionHeader id="reports-title" title={`คนแจ้งน้ำท่วมทั่วประเทศ ${reports.length} เรื่อง`} description="จาก Longdo Traffic, แจ้งผ่านเว็บนี้ และ Traffy Fondue · ยังไม่ได้ยืนยัน" />
        {reports.length === 0 && <p className="text-sm text-slate-600">ตอนนี้ยังไม่มีคนแจ้งน้ำท่วม</p>}
        <ul className="flex flex-col divide-y divide-slate-100">
          {(allReports ? reports : reports.slice(0, REPORTS_SHOWN)).map((r, i) => (
            <li key={i} className="py-2 text-sm">
              <span className="font-medium text-slate-900">{r.title}</span>
              {r.depth ? <span className="text-slate-700"> · น้ำ{r.depth}</span> : null}
              <span className="text-xs text-slate-500"> · {r.province} · {r.source}{r.ts ? ` · ${agoText(r.ts)}` : ''}</span>
              {r.text && <p className="text-xs text-slate-600 mt-0.5">{r.text.slice(0, 140)}</p>}
            </li>
          ))}
        </ul>
        {reports.length > REPORTS_SHOWN && (
          <button type="button" onClick={() => setAllReports((v) => !v)} className="self-start text-xs text-blue-700 cursor-pointer">
            {allReports ? 'ย่อ' : `ดูทั้งหมด ${reports.length} เรื่อง`}
          </button>
        )}
      </Card>

      <p className="text-[11px] text-slate-500 leading-4 px-1">
        ระดับเสี่ยง 7 วันคิดจากจุดวัดน้ำ น้ำในเขื่อนใหญ่และอ่างเก็บน้ำกลาง ฝนพยากรณ์ และทางหลวงที่น้ำท่วม แล้วให้ AI (Qwen) อ่านและปรับ · AI อาจผิดพลาดได้
      </p>
    </div>
  );
}
