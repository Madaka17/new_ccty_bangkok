// Simple view of the เส้นทางน้ำเหนือ tab: the AI's read of the northern water now and over 7 days, the 3D map of
// the water along the rivers, each province on the way with its water day by day, and what to do
// (/api/water/north/route, north_route.py).
import { useCallback, useEffect, useState } from 'react';
import { Badge, Card, ErrorState, SectionHeader, Skeleton } from '../dashboard/ui.jsx';
import { StatusBanner } from '../dashboard/primitives.jsx';
import { agoText, fmtDateTime } from '../dashboard/format.js';
import NorthRouteMap from './NorthRouteMap.jsx';

const POLL_MS = 5 * 60000;
const LEVEL = {
  critical: { label: 'ล้นตลิ่ง', tone: 'red', cell: 'bg-rose-50 border-rose-300 text-rose-900 dark:bg-rose-950/50 dark:border-rose-700/70 dark:text-rose-200', dot: 'bg-rose-500' },
  flood: { label: 'ใกล้ล้นตลิ่ง', tone: 'yellow', cell: 'bg-orange-50 border-orange-300 text-orange-900 dark:bg-orange-950/40 dark:border-orange-700/60 dark:text-orange-200', dot: 'bg-orange-500' },
  watch: { label: 'น้ำมาก', tone: 'yellow', cell: 'bg-amber-50 border-amber-300 text-amber-900 dark:bg-amber-950/40 dark:border-amber-700/60 dark:text-amber-200', dot: 'bg-amber-500' },
  normal: { label: 'ปกติ', tone: 'green', cell: 'bg-emerald-50 border-emerald-200 text-emerald-800 dark:bg-emerald-950/30 dark:border-emerald-800/50 dark:text-emerald-300', dot: 'bg-emerald-500' },
};
const BKK = 'นนทบุรี-กรุงเทพฯ';
const dayLabel = (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString('th-TH', { weekday: 'short', day: 'numeric', month: 'short' });

function cellValue(p, x) {
  if (p.province === BKK) return x.below_bank > 0 ? `-${x.below_bank.toFixed(2)} ม.` : `+${(-x.below_bank).toFixed(2)} ม.`;
  return x.pct != null ? `${Math.round(x.pct)}%` : '–';
}

function DailyTable({ data }) {
  const dates = data.dates || [];
  return (
    <Card className="p-4 flex flex-col gap-2">
      <SectionHeader id="north-days-title" title="จังหวัดที่น้ำเหนือไหลผ่าน วันนี้และ 7 วันข้างหน้า"
        description="ตัวเลข = น้ำเต็มลำน้ำกี่ % (นนทบุรี-กรุงเทพฯ = ระดับน้ำต่ำ/สูงกว่าตลิ่ง) · ช่องเส้นประ = แนวโน้ม ความแม่นยำน้อยกว่า" />
      <div className="flex flex-wrap items-center gap-3 text-xs text-slate-700">
        {Object.entries(LEVEL).map(([k, v]) => (
          <span key={k} className="inline-flex items-center gap-1.5"><span className={`w-2.5 h-2.5 rounded-full ${v.dot}`} />{v.label}</span>
        ))}
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200">
        <table className="w-full text-sm border-collapse min-w-[820px]">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-200 text-xs text-slate-600">
              <th className="text-left py-2.5 px-3 w-44 sticky left-0 bg-slate-50">จังหวัด (ต้นน้ำ → ปลายน้ำ)</th>
              {dates.map((iso, i) => (
                <th key={iso} className="text-center py-2.5 px-1 min-w-[72px]">
                  <div className="font-semibold text-slate-900">{i === 0 ? 'วันนี้' : `+${i} วัน`}</div>
                  <div className="text-[10px] font-normal text-slate-500">{dayLabel(iso)}</div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data.provinces.map((p) => (
              <tr key={p.province}>
                <td className="py-2 px-3 align-middle sticky left-0 bg-white">
                  <div className="font-semibold text-slate-900">{p.province}</div>
                  <div className="text-[11px] text-slate-500 leading-4">{p.areas.join(' · ')}</div>
                </td>
                {p.days.map((x) => (
                  <td key={x.day} className="p-1 align-middle">
                    <div className={`rounded-lg border text-center py-1.5 px-1 ${LEVEL[x.level].cell} ${x.kind === 'trend' ? 'border-dashed' : ''}`}
                      title={`${dayLabel(dates[x.day])} · ${LEVEL[x.level].label}${x.q != null ? ` · ${x.q.toLocaleString('th-TH')} ลบ.ม./วิ` : ''}${x.kind === 'trend' ? ' · แนวโน้ม' : ''}`}>
                      <div className="flex items-center justify-center gap-1">
                        <span className={`w-1.5 h-1.5 rounded-full ${LEVEL[x.level].dot}`} />
                        <span className="text-[13px] font-bold tabular-nums leading-none">{cellValue(p, x)}</span>
                      </div>
                      <div className="text-[10px] font-medium mt-1 leading-none">{LEVEL[x.level].label}</div>
                      {x.kind === 'trend' && <div className="text-[9px] mt-0.5 leading-none opacity-70">แนวโน้ม</div>}
                    </div>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export default function NorthRouteView({ isActive, onDetail }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const load = useCallback(() => {
    fetch('/api/water/north/route')
      .then((r) => {
        if (!r.ok) throw new Error('route');
        return r.json();
      })
      .then((d) => {
        setData(d);
        setError(false);
      })
      .catch(() => setError(true));
  }, []);
  useEffect(() => {
    if (!isActive) return undefined;
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [isActive, load]);

  if (error && !data) return <ErrorState message="โหลดข้อมูลเส้นทางน้ำเหนือไม่สำเร็จ" onRetry={load} />;
  if (!data) return <Skeleton className="h-[520px] rounded-xl" />;
  if (!data.provinces) return <p className="text-sm text-slate-600 px-1">ระบบกำลังคำนวณเส้นทางน้ำเหนือรอบแรก ลองใหม่ในอีกไม่กี่นาที</p>;

  const ai = data.ai || {};
  const watch = data.provinces.filter((p) => p.level !== 'normal');
  const worst = watch.some((p) => p.level === 'critical') ? 'red' : watch.length ? 'yellow' : 'green';

  return (
    <div className="flex flex-col gap-4">
      <StatusBanner tone={worst} label={worst === 'red' ? 'มีจังหวัดน้ำล้นตลิ่ง' : worst === 'yellow' ? 'เฝ้าระวัง' : 'ปกติ'}>
        {ai.headline || (watch.length ? `จังหวัดที่ต้องระวังใน 7 วัน: ${watch.map((p) => p.province).join(' · ')}` : 'น้ำเหนือยังอยู่ในความจุลำน้ำทุกจังหวัด')}
      </StatusBanner>

      <Card className="p-4 flex flex-col gap-3">
        <SectionHeader id="north-trend-title" title="แนวโน้มน้ำเหนือ"
          description={`ข้อมูลน้ำ ${fmtDateTime(data.data_time)} (${agoText(data.data_time)})${ai.generated_at ? ` · AI วิเคราะห์เมื่อ ${fmtDateTime(ai.generated_at)}` : ''}`} />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          <div className="rounded-xl border border-slate-200 p-3">
            <p className="text-sm font-semibold text-slate-900">ตอนนี้</p>
            <p className="text-sm text-slate-800 leading-6 mt-1">{ai.now || 'ยังไม่มีบทวิเคราะห์จาก AI ดูตัวเลขในตารางด้านล่าง'}</p>
          </div>
          <div className="rounded-xl border border-slate-200 p-3">
            <p className="text-sm font-semibold text-slate-900">7 วันข้างหน้า</p>
            <p className="text-sm text-slate-800 leading-6 mt-1">{ai.next7 || 'ยังไม่มีบทวิเคราะห์จาก AI ดูตัวเลขในตารางด้านล่าง'}</p>
          </div>
        </div>
      </Card>

      <NorthRouteMap data={data} isActive={isActive} />

      <DailyTable data={data} />

      <Card className="p-4 flex flex-col gap-2">
        <SectionHeader id="north-watch-title" title={`จังหวัดที่ต้องระวัง ${watch.length} จังหวัด`} description="น้ำเหนือไหลผ่านส่วนไหน และ 7 วันข้างหน้าจะเป็นอย่างไร" />
        {watch.length === 0 && <p className="text-sm text-slate-600">ทุกจังหวัดตามทางน้ำเหนือยังปกติใน 7 วันข้างหน้า</p>}
        <ul className="flex flex-col divide-y divide-slate-100">
          {watch.map((p) => {
            const a = ai.provinces?.[p.province];
            return (
              <li key={p.province} className="py-3 flex flex-col gap-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-semibold text-slate-900">{p.province}</span>
                  <Badge tone={LEVEL[p.now_level].tone}>วันนี้: {LEVEL[p.now_level].label}</Badge>
                  <Badge tone={LEVEL[p.level].tone} dot>หนักสุด{p.peak_day === 0 ? 'วันนี้' : ` +${p.peak_day} วัน`}: {LEVEL[p.level].label}</Badge>
                </div>
                <p className="text-xs text-slate-500">ทางน้ำ: {p.areas.join(' · ')}</p>
                {a?.outlook && <p className="text-sm text-slate-800 leading-6">{a.outlook}</p>}
                {a?.advice && <p className="text-[13px] text-slate-700 leading-6"><b>คำแนะนำ:</b> {a.advice}</p>}
              </li>
            );
          })}
        </ul>
      </Card>

      {ai.actions?.length > 0 && (
        <Card className="p-4">
          <SectionHeader id="north-actions-title" title="คนริมแม่น้ำควรทำอะไร" />
          <ul className="list-disc pl-5 mt-2 flex flex-col gap-1 text-sm text-slate-800">
            {ai.actions.map((x) => <li key={x}>{x}</li>)}
          </ul>
        </Card>
      )}

      <p className="text-xs text-slate-500 leading-5 px-1">
        ข้อมูลจากกรมชลประทานและ สสน. · วันแรก ๆ คำนวณจากน้ำที่กำลังไหลลงมาจริงตามเวลาเดินทางของน้ำ วันที่เหลือเป็นแนวโน้มจากน้ำที่ไหลลงมาและฝนพยากรณ์ ·
        นนทบุรี-กรุงเทพฯ ใช้คาดการณ์ระดับน้ำ 7 วันของ สสน. · บทวิเคราะห์โดย AI (Qwen) อาจผิดพลาดได้ ·{' '}
        <button type="button" onClick={onDetail} className="underline text-blue-700 cursor-pointer">ดูกราฟและตัวเลขทุกจุดวัด</button>
      </p>
    </div>
  );
}
