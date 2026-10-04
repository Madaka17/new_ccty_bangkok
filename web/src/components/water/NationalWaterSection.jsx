// "ระดับน้ำทั่วประเทศ" tab of the Water page: water in the large dams now and in 7 days (computed from each
// dam's inflow and release of the last 7 days), the medium reservoirs that are full, the 7-day rain forecast,
// and Qwen's outlook (/api/flood/forecast, national_forecast.py).
import { useMemo, useState } from 'react';
import { Badge, Card, ErrorState, SectionHeader, Skeleton } from '../dashboard/ui.jsx';
import { StatTile, StatusBanner } from '../dashboard/primitives.jsx';
import { agoText, fmtDateTime } from '../dashboard/format.js';
import { fullText, sum, useFloodForecast } from './forecastData.js';

const SHOW = 12;

// Storage bar: today's level and, lighter, where it will be in 7 days; the 100% line is the normal storage
function DamBar({ now, later }) {
  const scale = 130;
  const w = (v) => `${Math.min(100, (Math.max(0, v) / scale) * 100)}%`;
  const color = (v) => (v >= 100 ? 'bg-red-500' : v >= 80 ? 'bg-amber-500' : 'bg-blue-500');
  return (
    <div className="relative h-2.5 rounded-full bg-slate-100 overflow-hidden" aria-hidden="true">
      <div className={`absolute inset-y-0 left-0 opacity-35 ${color(later)}`} style={{ width: w(later) }} />
      <div className={`absolute inset-y-0 left-0 ${color(now)}`} style={{ width: w(now) }} />
      <div className="absolute inset-y-0 w-px bg-slate-700" style={{ left: w(100) }} />
    </div>
  );
}

function DamRow({ d, note }) {
  const full = fullText(d);
  return (
    <li className="py-3 flex flex-col gap-1.5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-slate-900">เขื่อน{d.name}</span>
        <span className="text-xs text-slate-500">{d.province}</span>
        {full && <Badge tone={d.full_day === 0 ? 'red' : 'yellow'} dot>{full}</Badge>}
        <span className="ml-auto text-xs text-slate-700 tabular-nums">
          วันนี้ <b>{Math.round(d.pct)}%</b> → 7 วัน <b className={d.pct_7d >= 100 ? 'text-red-700' : ''}>{Math.round(d.pct_7d)}%</b>
        </span>
      </div>
      <DamBar now={d.pct} later={d.pct_7d} />
      <p className="text-xs text-slate-600">
        {d.net >= 0 ? `น้ำเข้ามากกว่าที่ปล่อยวันละ ${d.net.toFixed(1)} ล้าน ลบ.ม.` : `ปล่อยน้ำมากกว่าที่เข้าวันละ ${Math.abs(d.net).toFixed(1)} ล้าน ลบ.ม.`}
        {` · ฝน 7 วัน ${Math.round(sum(d.rain7))} มม.`}
      </p>
      {note && <p className="text-[13px] text-slate-800 leading-6">{note}</p>}
    </li>
  );
}

export default function NationalWaterSection({ isActive }) {
  const { data, error, load } = useFloodForecast(isActive);
  const [all, setAll] = useState(false);
  const rainTop = useMemo(
    () => (data?.provinces || []).map((p) => ({ province: p.province, mm: sum(p.rain7) })).sort((a, b) => b.mm - a.mm).slice(0, 10),
    [data],
  );

  if (error && !data) return <ErrorState message="โหลดข้อมูลน้ำในเขื่อนไม่สำเร็จ" onRetry={load} />;
  if (!data) return <Skeleton className="h-[480px] rounded-xl" />;
  if (!data.dams) return <p className="text-sm text-slate-600 px-1">ระบบกำลังรวบรวมข้อมูลเขื่อนรอบแรก ลองใหม่ในอีกไม่กี่นาที</p>;

  const dams = data.dams;
  const fullNow = dams.filter((d) => d.full_day === 0).length;
  const fullSoon = dams.filter((d) => d.full_day > 0).length;
  const ai = data.ai?.water;
  const shown = all ? dams : dams.slice(0, SHOW);

  return (
    <div className="flex flex-col gap-4">
      <StatusBanner tone={fullNow ? 'red' : fullSoon ? 'yellow' : 'green'} label={fullNow ? 'มีเขื่อนเต็ม' : fullSoon ? 'เขื่อนใกล้เต็ม' : 'น้ำในเขื่อนปกติ'}>
        {ai?.outlook || `เขื่อนใหญ่เต็มแล้ว ${fullNow} แห่ง และจะเต็มใน 7 วันอีก ${fullSoon} แห่ง จากทั้งหมด ${dams.length} แห่ง`}
      </StatusBanner>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatTile label="เขื่อนใหญ่ที่เต็มแล้ว" value={`${fullNow} / ${dams.length}`} tone={fullNow ? 'red' : undefined} sub="น้ำเกินความจุปกติ" />
        <StatTile label="เขื่อนใหญ่ที่จะเต็มใน 7 วัน" value={fullSoon} tone={fullSoon ? 'yellow' : undefined} sub="ถ้าปล่อยน้ำเท่าเดิม" />
        <StatTile label="อ่างเก็บน้ำกลางที่เต็ม" value={`${data.medium.full} / ${data.medium.count}`} sub={`เกิน 80% อีก ${data.medium.over80 - data.medium.full} แห่ง`} />
        <StatTile label="ฝน 7 วันมากที่สุด" value={rainTop[0] ? `${Math.round(rainTop[0].mm)} มม.` : '–'} sub={rainTop[0]?.province || ''} />
      </div>

      <Card className="p-4 flex flex-col gap-1">
        <SectionHeader
          id="dams-title"
          title="น้ำในเขื่อนใหญ่ วันนี้และอีก 7 วัน"
          description={`อัปเดต ${fmtDateTime(data.updated_at)} (${agoText(data.updated_at)})${data.ai?.generated_at ? ` · AI วิเคราะห์เมื่อ ${fmtDateTime(data.ai.generated_at)}` : ''}`}
        />
        <p className="text-xs text-slate-500">แถบเข้ม = วันนี้ · แถบจาง = อีก 7 วัน · เส้นดำ = ความจุปกติ (100%)</p>
        <ul className="divide-y divide-slate-100">
          {shown.map((d) => <DamRow key={d.id} d={d} note={ai?.dams?.[d.name]} />)}
        </ul>
        {dams.length > SHOW && (
          <button type="button" onClick={() => setAll((v) => !v)} className="self-start text-xs text-blue-700 cursor-pointer mt-1">
            {all ? 'ย่อ' : `ดูทั้งหมด ${dams.length} เขื่อน`}
          </button>
        )}
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card className="p-4 flex flex-col gap-2">
          <SectionHeader id="medium-title" title="อ่างเก็บน้ำกลางที่น้ำเต็ม รายจังหวัด" />
          <ul className="flex flex-col gap-1.5 text-sm">
            {data.medium.provinces.filter((s) => s.over80).slice(0, 12).map((s) => (
              <li key={s.province} className="flex items-center gap-2">
                <span className="text-slate-900">{s.province}</span>
                <span className="ml-auto text-xs text-slate-600 tabular-nums">
                  เต็ม <b className={s.full ? 'text-red-700' : ''}>{s.full}</b> · เกิน 80% <b>{s.over80}</b> จาก {s.count} แห่ง
                </span>
              </li>
            ))}
          </ul>
        </Card>
        <Card className="p-4 flex flex-col gap-2">
          <SectionHeader id="rain7-title" title="ฝนพยากรณ์ 7 วัน มากที่สุด 10 จังหวัด" />
          <ul className="flex flex-col gap-1.5 text-sm">
            {rainTop.map((r) => (
              <li key={r.province} className="flex items-center gap-2">
                <span className="text-slate-900 w-32 shrink-0">{r.province}</span>
                <div className="flex-1 h-2 rounded-full bg-slate-100 overflow-hidden" aria-hidden="true">
                  <div className="h-full bg-blue-500" style={{ width: `${Math.min(100, (r.mm / Math.max(1, rainTop[0].mm)) * 100)}%` }} />
                </div>
                <span className="text-xs text-slate-700 tabular-nums w-14 text-right">{Math.round(r.mm)} มม.</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      <p className="text-[11px] text-slate-500 leading-4 px-1">
        ข้อมูลเขื่อนจากกรมชลประทาน ผ่านคลังข้อมูลน้ำแห่งชาติ (สสน.) · ฝนพยากรณ์จาก Open-Meteo · ตัวเลข 7 วันคำนวณจากน้ำเข้าลบน้ำที่ปล่อยเฉลี่ย 7 วันล่าสุด
        ถ้าฝนตกมากหรือเขื่อนปล่อยน้ำเพิ่ม ตัวเลขจริงจะต่างไป · บทวิเคราะห์โดย AI (Qwen) อาจผิดพลาดได้
      </p>
    </div>
  );
}
