// "เขตเสี่ยงน้ำท่วมในกรุงเทพมหานคร" tab of the Water page: every one of Bangkok's 50 districts with how much water
// it has (canals against the bank, main gauges, water on the roads, rain so far and coming, Traffy reports), a
// risk score with its reasons, and Qwen's line per district (/api/flood/bkk-districts, bkk_districts.py).
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Badge, Card, ErrorState, FOCUS, SectionHeader, Skeleton } from '../dashboard/ui.jsx';
import { StatTile, StatusBanner } from '../dashboard/primitives.jsx';
import { agoText, fmtDateTime } from '../dashboard/format.js';
import { CHIP_OFF, CHIP_ON } from './forecastData.js';

const POLL_MS = 5 * 60000;
const LEVEL = {
  high: { label: 'เสี่ยงสูง', tone: 'red', ring: 'border-red-300' },
  medium: { label: 'ปานกลาง', tone: 'yellow', ring: 'border-amber-300' },
  watch: { label: 'เฝ้าระวัง', tone: 'blue', ring: 'border-blue-200' },
  normal: { label: 'ปกติ', tone: 'green', ring: 'border-slate-200' },
};
const gap = (m) => (m > 0 ? `ต่ำกว่าตลิ่ง ${m.toFixed(2)} ม.` : `สูงกว่าตลิ่ง ${(-m).toFixed(2)} ม.`);

function Fact({ label, children }) {
  return (
    <div className="rounded-lg bg-slate-50 border border-slate-200 px-2.5 py-1.5">
      <p className="text-[11px] text-slate-500">{label}</p>
      <p className="text-xs text-slate-900 leading-5">{children}</p>
    </div>
  );
}

function DistrictCard({ d, ai }) {
  const lv = LEVEL[d.level];
  const c = d.canals;
  return (
    <article className={`rounded-xl border bg-white p-4 flex flex-col gap-2 ${lv.ring}`}>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-[15px] font-semibold text-slate-900">เขต{d.district}</h3>
        <Badge tone={lv.tone} dot>{lv.label}</Badge>
        <span className="text-xs text-slate-500">{d.zone}</span>
        <span className="ml-auto text-xs text-slate-600 tabular-nums">คะแนน <b className="text-slate-900">{d.score}</b>/100</span>
      </div>
      {ai?.summary && <p className="text-sm text-slate-800 leading-6">{ai.summary}</p>}
      <div className="grid grid-cols-2 gap-1.5">
        <Fact label={`คลอง ${c.count} จุดวัด`}>
          {c.count === 0 ? 'ไม่มีจุดวัดในเขต' : (
            <>
              {c.overflow ? <b className="text-red-700">ล้น {c.overflow} </b> : null}
              {c.high ? <b className="text-amber-700">ใกล้ล้น {c.high} </b> : null}
              {!c.overflow && !c.high && 'ยังรับน้ำได้ '}
              {c.fullest && <span className="text-slate-600">· เต็มสุด {c.fullest.name} {Math.round(c.fullest.pct)}%</span>}
            </>
          )}
        </Fact>
        <Fact label="แม่น้ำ/คลองสายหลัก">
          {d.river.closest ? <>{d.river.closest} <b className={d.river.below_bank <= 0.3 ? 'text-red-700' : ''}>{gap(d.river.below_bank)}</b></> : 'ไม่มีจุดวัดในเขต'}
          {d.river.outlook_over && <span className="block text-red-700">คาดเจ้าพระยาสูงกว่าตลิ่งใน 7 วัน</span>}
        </Fact>
        <Fact label="น้ำบนถนน">
          {d.roads.length ? d.roads.map((r) => `${r.name} ${r.cm} ซม.`).join(' · ') : 'ไม่มีเครื่องวัดที่เจอน้ำ'}
        </Fact>
        <Fact label="ฝน">
          ตกแล้ว 24 ชม. <b>{Math.round(d.rain24)}</b> มม. · คาด 24 ชม. <b>{Math.round(d.rain_next24)}</b> · 3 วัน <b>{Math.round(d.rain_3d)}</b> มม.
        </Fact>
      </div>
      {d.why.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {d.why.map((w) => <span key={w} className="rounded-md bg-slate-100 px-2 py-0.5 text-[11px] text-slate-700">{w}</span>)}
          {d.reports > 0 && !d.why.some((w) => w.startsWith('คนแจ้ง')) && <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[11px] text-slate-700">คนแจ้ง {d.reports} เรื่อง</span>}
        </div>
      )}
      {ai?.advice && <p className="text-[13px] text-slate-700 leading-6"><b>คำแนะนำ:</b> {ai.advice}</p>}
    </article>
  );
}

export default function BkkDistrictSection({ isActive }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const [zone, setZone] = useState('');
  const [all, setAll] = useState(false);
  const load = useCallback(() => {
    fetch('/api/flood/bkk-districts')
      .then((r) => {
        if (!r.ok) throw new Error('districts');
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

  const inZone = useMemo(() => (data?.districts || []).filter((d) => !zone || d.zone === zone), [data, zone]);
  const shown = all ? inZone : inZone.filter((d) => d.level !== 'normal');
  const calm = inZone.filter((d) => d.level === 'normal');

  if (error && !data) return <ErrorState message="โหลดข้อมูลเขตเสี่ยงน้ำท่วมไม่สำเร็จ" onRetry={load} />;
  if (!data) return <Skeleton className="h-[480px] rounded-xl" />;
  if (!data.districts) return <p className="text-sm text-slate-600 px-1">ระบบกำลังรวบรวมข้อมูลรายเขตรอบแรก ลองใหม่ในอีกไม่กี่นาที</p>;

  const c = data.counts;
  const t = data.totals;
  const ai = data.ai || {};
  const tone = c.high ? 'red' : c.medium ? 'yellow' : c.watch ? 'blue' : 'green';

  return (
    <div className="flex flex-col gap-4">
      <StatusBanner tone={tone} label={`เสี่ยงสูง ${c.high} · ปานกลาง ${c.medium} · เฝ้าระวัง ${c.watch} เขต`}>
        {ai.overview || `กรุงเทพฯ ${50 - c.normal} เขตต้องระวัง จาก 50 เขต`}
      </StatusBanner>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatTile label="เขตที่ต้องระวัง" value={`${50 - c.normal} / 50`} tone={c.high ? 'red' : c.medium ? 'yellow' : undefined} sub={`เสี่ยงสูง ${c.high} · ปานกลาง ${c.medium}`} />
        <StatTile label="คลองล้น / ใกล้ล้น" value={`${t.canal_overflow} / ${t.canal_high}`} tone={t.canal_overflow ? 'red' : t.canal_high ? 'yellow' : undefined} sub={`จากจุดวัดคลอง ${t.canals} จุด`} />
        <StatTile label="ถนนที่มีน้ำ" value={t.roads_wet} sub="จากเครื่องวัดน้ำบนถนนของ กทม." />
        <StatTile label="ฝน 24 ชม. มากสุด" value={`${Math.round(t.rain24_max)} มม.`} sub={`คาด 24 ชม. ข้างหน้ามากสุด ${Math.round(t.rain_next24_max)} มม.`} />
      </div>

      <Card className="p-4 flex flex-col gap-3">
        <SectionHeader id="bkk-districts-title" title="เขตเสี่ยงน้ำท่วมในกรุงเทพมหานคร"
          description={`อัปเดต ${fmtDateTime(data.updated_at)} (${agoText(data.updated_at)})${ai.generated_at ? ` · AI วิเคราะห์เมื่อ ${fmtDateTime(ai.generated_at)}` : ''}`} />
        <div role="group" aria-label="เลือกโซน" className="flex flex-wrap gap-2">
          {[['', 'ทุกโซน'], ...data.zones.map((z) => [z, z])].map(([id, label]) => (
            <button key={id || 'all'} type="button" aria-pressed={zone === id} onClick={() => setZone(id)}
              className={`cursor-pointer rounded-lg border px-3 h-8 text-xs font-medium ${FOCUS} ${zone === id ? CHIP_ON : CHIP_OFF}`}>
              {label}
            </button>
          ))}
          <button type="button" aria-pressed={all} onClick={() => setAll((v) => !v)}
            className={`cursor-pointer rounded-lg border px-3 h-8 text-xs font-medium ${FOCUS} ${all ? CHIP_ON : CHIP_OFF}`}>
            {all ? 'แสดงทุกเขต' : 'เฉพาะเขตที่ต้องระวัง'}
          </button>
        </div>
      </Card>

      {shown.length === 0 && <p className="text-sm text-slate-600 px-1">ทุกเขตในโซนนี้ยังปกติ</p>}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {shown.map((d) => <DistrictCard key={d.district} d={d} ai={ai.districts?.[d.district]} />)}
      </div>
      {!all && calm.length > 0 && (
        <p className="text-xs text-slate-600 px-1">
          ปกติ {calm.length} เขต: {calm.map((d) => d.district).join(' · ')} ·{' '}
          <button type="button" onClick={() => setAll(true)} className="underline text-blue-700 cursor-pointer">ดูรายละเอียดทุกเขต</button>
        </p>
      )}

      <p className="text-[11px] text-slate-500 leading-4 px-1">
        ข้อมูลจากจุดวัดน้ำในคลองและแม่น้ำ (สสน. และสำนักการระบายน้ำ กทม.), เครื่องวัดน้ำบนถนนของ กทม., สถานีวัดฝน, ฝนพยากรณ์ Open-Meteo,
        เรื่องที่คนแจ้งผ่าน Traffy Fondue 12 ชม. ล่าสุด และคาดการณ์ระดับน้ำเจ้าพระยาของ สสน. · คะแนนคิดจากตัวเลขเหล่านี้ · บทวิเคราะห์โดย AI (Qwen) อาจผิดพลาดได้
      </p>
    </div>
  );
}
