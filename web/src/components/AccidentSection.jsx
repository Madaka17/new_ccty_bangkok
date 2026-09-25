// Thai RSC accidents with the black spots and the measures for each (from /api/analytics/summary
// `accidents`). Was a tab of City Analytics; now a tab of the Accidents & Risk page.
import { Card, Badge, SectionHeader, EmptyState } from './dashboard/ui.jsx';
import { StatTile, StatusBanner } from './dashboard/primitives.jsx';
import { fmtNum } from './dashboard/format.js';

const PRIORITY_TONE = { เร่งด่วน: 'red', สูง: 'yellow', ปานกลาง: 'neutral', เฝ้าระวัง: 'yellow' };

// ---------------------------------------------------------------- hourly bars chart
function Bars({ values, labelOf, highlight }) {
  if (!values?.length) return null;
  const max = Math.max(1, ...values);
  return (
    <div>
      <div className="flex items-end gap-[3px] h-28" role="img" aria-label="ผู้เสียชีวิตรายชั่วโมง">
        {values.map((v, i) => {
          const isHigh = highlight?.has(i);
          const pct = Math.max(4, (v / max) * 100);
          return (
            <div key={i} className="flex-1 flex flex-col justify-end items-center group relative" title={`${String(i).padStart(2, '0')}:00 · ${v} คน`}>
              <span className="opacity-0 group-hover:opacity-100 transition-opacity absolute -top-6 text-[10px] font-semibold tabular-nums text-slate-700 bg-white px-1 rounded shadow-xs border border-slate-200 pointer-events-none z-10 whitespace-nowrap">
                {v} คน
              </span>
              <div
                className={`w-full rounded-sm transition-all duration-200 ${
                  isHigh ? 'bg-red-600 shadow-xs' : i < 6 || i >= 22 ? 'bg-slate-400' : 'bg-slate-200 hover:bg-slate-300'
                }`}
                style={{ height: `${pct}%` }}
              />
            </div>
          );
        })}
      </div>
      <div className="mt-2 flex justify-between text-[11px] text-slate-500 tabular-nums">
        <span>00:00</span>
        <span>06:00</span>
        <span>12:00</span>
        <span>18:00</span>
        <span>23:00</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- 4. accidents
export default function AccidentSection({ d }) {
  if (!d?.ready) return <EmptyState title="ไม่มีข้อมูล Thai RSC" description="ยังดึงสถิติอุบัติเหตุไม่ได้" />;
  const hours = d.dead_by_hour?.length === 24 ? d.dead_by_hour : null;
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatTile label="เสียชีวิตวันนี้" value={fmtNum(d.today?.dead)} sub={`บาดเจ็บ ${fmtNum(d.today?.injured)} ราย`} tone={d.today?.dead ? 'red' : 'green'} />
        <StatTile label={`เสียชีวิตสะสมปี ${d.year_be || ''}`} value={fmtNum(d.ytd?.dead)} sub={`บาดเจ็บ ${fmtNum(d.ytd?.injured)} ราย`} tone="red" />
        <StatTile label="จุดเกิดเหตุกระจุกตัว" value={fmtNum(d.black_spots.length)} sub={`จากพิกัดอุบัติเหตุ ${fmtNum(d.points_total)} จุด`} tone="yellow" />
        <StatTile label="เขตเสี่ยงสูงสุด" value={d.districts[0]?.name || '–'} sub={d.districts[0] ? `เสียชีวิต ${d.districts[0].dead} · บาดเจ็บ ${d.districts[0].injured}` : ''} />
      </div>
      {d.citywide_measures.length > 0 && (
        <StatusBanner tone="yellow" label="มาตรการทั่วเมือง">
          {d.citywide_measures.join(' · ')}
        </StatusBanner>
      )}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-4">
        <Card className="p-5">
          <SectionHeader id="black-spots" title="Black Spots และแนวทางลดอุบัติเหตุเฉพาะพื้นที่" description="จัดกลุ่มพิกัดอุบัติเหตุในรัศมี ~275 ม. · คะแนน = เคส + 3×บาดเจ็บ + 10×เสียชีวิต · มาตรการเลือกตามประเภทถนน" />
          <ol className="mt-3 divide-y divide-slate-100">
            {d.black_spots.map((b, i) => (
              <li key={`${b.lat}-${b.lon}`} className="py-3 flex gap-3">
                <span className="w-6 text-center text-sm font-semibold text-slate-500 tabular-nums shrink-0">{i + 1}</span>
                <div className="flex-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-slate-900 truncate" title={b.place}>{b.place}</span>
                    <Badge tone={PRIORITY_TONE[b.priority]} dot>{b.priority}</Badge>
                    <Badge tone="neutral">{b.road_type}</Badge>
                  </div>
                  <p className="text-xs text-slate-600 mt-1 tabular-nums">
                    เขต{b.district} · {fmtNum(b.cases)} เคส · เสียชีวิต <span className="font-medium text-red-700">{b.dead}</span> · บาดเจ็บ {fmtNum(b.injured)} · ปี {b.years.join('/')}
                  </p>
                  <ul className="mt-1.5 flex flex-col gap-0.5">
                    {b.measures.map((m) => (
                      <li key={m} className="text-xs text-slate-700 flex gap-1.5">
                        <span className="text-blue-600 shrink-0">•</span>
                        <span>{m}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </li>
            ))}
          </ol>
          <p className="text-[11px] text-slate-500 mt-3">{d.injury_note} · แหล่งข้อมูล {d.source || 'Thai RSC'}</p>
        </Card>
        <div className="flex flex-col gap-4">
          <Card className="p-5">
            <SectionHeader id="by-district" title="รายเขต" description="เรียงตามผู้เสียชีวิตสะสมปีนี้" />
            <ul className="mt-3 divide-y divide-slate-100">
              {d.districts.map((x) => (
                <li key={x.name} className="py-1.5 flex items-center text-sm">
                  <span className="text-slate-900">{x.name}</span>
                  <span className="ml-auto text-xs tabular-nums text-slate-600">
                    <span className="font-medium text-red-700">{x.dead}</span> ตาย · {fmtNum(x.injured)} เจ็บ
                  </span>
                </li>
              ))}
            </ul>
          </Card>
          {hours && (
            <Card className="p-5">
              <SectionHeader id="by-hour" title="ผู้เสียชีวิตรายชั่วโมง" description="สะสมปีนี้ ทั้งกรุงเทพฯ" />
              <div className="mt-3">
                <Bars values={hours} labelOf={(i) => `${i}`} highlight={new Set(hours.map((v, i) => [v, i]).sort((a, b) => b[0] - a[0]).slice(0, 3).map((x) => x[1]))} />
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
