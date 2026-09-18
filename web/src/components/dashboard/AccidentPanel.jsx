// Road-safety section: Thai RSC accident reports joined with BMA camera load.
// Two views: risk per camera (points within 300 m) and per district.
import { useEffect, useState } from 'react';
import { Card, SectionHeader, Badge, Button, Skeleton, EmptyState, ErrorState, FOCUS } from './ui.jsx';
import { StatTile, ShareBar } from './primitives.jsx';
import { fmtNum } from './format.js';
import { fetchRscSummary, fetchRscCameraRisk, triggerRscRebuild } from '../../lib/api.js';

const POLL_MS = 60000;

function HourBars({ values }) {
  if (!values?.length) return null;
  const max = Math.max(1, ...values);
  const peak = values.indexOf(max);
  return (
    <div>
      <div className="flex items-end gap-[3px] h-24" role="img" aria-label={`ผู้เสียชีวิตรายชั่วโมง สูงสุด ${max} คน เวลา ${peak}:00`}>
        {values.map((v, h) => (
          <div key={h} className="flex-1 flex flex-col justify-end" title={`${String(h).padStart(2, '0')}:00 · ${v} คน`}>
            <div
              className={`w-full rounded-sm ${h === peak ? 'bg-red-600' : h < 6 || h >= 22 ? 'bg-slate-500' : 'bg-slate-300'}`}
              style={{ height: `${Math.max(2, (v / max) * 100)}%` }}
            />
          </div>
        ))}
      </div>
      <p className="sr-only">
        {values.map((v, h) => `${String(h).padStart(2, '0')}:00 ${v} คน`).join(', ')}
      </p>
      <div className="mt-1 flex justify-between text-xs text-slate-500 tabular-nums">
        <span>00:00</span>
        <span>06:00</span>
        <span>12:00</span>
        <span>18:00</span>
        <span>23:00</span>
      </div>
    </div>
  );
}

function RiskRow({ r, rank, onOpen }) {
  const tone = r.risk_score >= 90 ? 'red' : r.risk_score >= 70 ? 'yellow' : 'neutral';
  return (
    <li>
      <button
        type="button"
        onClick={() => onOpen?.(r)}
        title={`เปิดกล้อง ${r.title}`}
        className={`cursor-pointer w-full text-left flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-slate-50 transition-colors duration-150 group ${FOCUS}`}
      >
        <span className="w-6 text-center text-xs font-medium text-slate-500 tabular-nums shrink-0">{rank}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-slate-900 truncate" title={r.title}>
              {r.title}
            </span>
            <Badge tone={tone} className="ml-auto">
              เสี่ยง {r.risk_score}
            </Badge>
          </div>
          <p className="mt-0.5 text-xs text-slate-600 truncate tabular-nums">
            {r.district || 'กทม.'} · <span className="font-medium text-slate-900">{fmtNum(r.cases_per_year)}</span> เคส/ปี · บาดเจ็บ {fmtNum(r.injured)}
            {r.dead > 0 && (
              <>
                {' '}
                · <span className="font-medium text-red-700">เสียชีวิต {r.dead}</span>
              </>
            )}
            {r.avg_vehicles > 0 && <> · รถเฉลี่ย {r.avg_vehicles} คัน/เฟรม</>}
          </p>
        </div>
        <span className="shrink-0 text-xs text-slate-400 group-hover:text-blue-700 transition-colors" aria-hidden="true">
          เปิดกล้อง
        </span>
      </button>
    </li>
  );
}

function DistrictTable({ rows }) {
  return (
    <div className="overflow-x-auto -mx-5 px-5">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-xs text-slate-500 border-b border-slate-200">
            <th className="py-2 text-left font-medium">เขต</th>
            <th className="py-2 text-right font-medium">เสียชีวิต</th>
            <th className="py-2 text-right font-medium">บาดเจ็บ</th>
            <th className="py-2 text-right font-medium">กล้อง</th>
            <th className="py-2 text-right font-medium">รถเฉลี่ย/กล้อง</th>
            <th className="py-2 text-right font-medium">มอเตอร์ไซค์</th>
            <th className="py-2 text-right font-medium">หนาแน่น</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 tabular-nums">
          {rows.map((d) => (
            <tr key={d.name}>
              <td className="py-2 text-slate-900 font-medium">{d.name}</td>
              <td className={`py-2 text-right ${d.dead >= 20 ? 'text-red-700 font-medium' : 'text-slate-900'}`}>{fmtNum(d.dead)}</td>
              <td className="py-2 text-right text-slate-700">{fmtNum(d.injured)}</td>
              <td className="py-2 text-right text-slate-700">{d.cameras || '–'}</td>
              <td className="py-2 text-right text-slate-700">{d.cameras ? d.avg_vehicles : '–'}</td>
              <td className="py-2 text-right text-slate-700">{d.moto_share != null ? `${d.moto_share}%` : '–'}</td>
              <td className="py-2 text-right text-slate-700">{d.cameras ? `${d.heavy} กล้อง` : '–'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function AccidentPanel({ isActive = true, onOpenCamera }) {
  const [summary, setSummary] = useState(null);
  const [risk, setRisk] = useState(null);
  const [error, setError] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);

  const load = async () => {
    try {
      const [s, r] = await Promise.all([fetchRscSummary(), fetchRscCameraRisk({ limit: 10 })]);
      setSummary(s);
      setRisk(r);
      setError(false);
    } catch {
      setError(true);
    }
  };

  useEffect(() => {
    if (!isActive) return;
    load();
    const t = setInterval(load, POLL_MS);
    return () => clearInterval(t);
  }, [isActive]);

  const status = risk?.status;
  const building = status?.status === 'running';
  useEffect(() => {
    if (!building) return;
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [building]);

  const rebuild = async () => {
    setRebuilding(true);
    try {
      await triggerRscRebuild();
      await load();
    } finally {
      setRebuilding(false);
    }
  };

  const loading = !summary;
  const deadDelta = summary ? summary.ytd.dead - (summary.cumulative.dead_last[Math.max(0, summary.cumulative.dead.filter(Boolean).length - 1)] || 0) : 0;
  const moto = summary?.dead_by_vehicle?.find((v) => v.en === 'Motorcycle');
  const yearBe = summary?.year_be;

  if (error && !summary) {
    return (
      <Card className="p-5">
        <SectionHeader title="อุบัติเหตุทางถนน (Thai RSC)" description="สถิติรับแจ้งจากบริษัทกลางคุ้มครองผู้ประสบภัยจากรถ" />
        <div className="mt-3">
          <ErrorState message="ดึงข้อมูล Thai RSC ไม่สำเร็จ" onRetry={load} />
        </div>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatTile
          label="วันนี้ · กทม."
          value={summary ? `${summary.today.dead} เสียชีวิต` : '–'}
          sub={summary ? `บาดเจ็บ ${fmtNum(summary.today.injured)} คน · เมื่อวาน ${summary.yesterday.dead} / ${fmtNum(summary.yesterday.injured)}` : ''}
          loading={loading}
          tone={summary?.today.dead > 0 ? 'red' : undefined}
        />
        <StatTile
          label={`เสียชีวิตสะสมปี ${yearBe || ''}`}
          value={summary ? fmtNum(summary.ytd.dead) : '–'}
          sub={summary ? `${deadDelta <= 0 ? 'ลดลง' : 'เพิ่มขึ้น'} ${Math.abs(deadDelta)} จากช่วงเดียวกันปีก่อน` : ''}
          badge={summary ? <Badge tone={deadDelta <= 0 ? 'green' : 'red'}>{deadDelta <= 0 ? 'ดีขึ้น' : 'แย่ลง'}</Badge> : null}
          loading={loading}
        />
        <StatTile
          label={`บาดเจ็บสะสมปี ${yearBe || ''}`}
          value={summary ? fmtNum(summary.ytd.injured) : '–'}
          sub={summary ? `ทั้งประเทศ ${fmtNum(summary.national.ytd.injured)} คน (กทม. ${Math.round((100 * summary.ytd.injured) / summary.national.ytd.injured)}%)` : ''}
          loading={loading}
        />
        <StatTile
          label="ผู้เสียชีวิตขี่มอเตอร์ไซค์"
          value={moto ? `${moto.pct}%` : '–'}
          sub={moto ? `${fmtNum(moto.count)} จาก ${fmtNum(summary.ytd.dead)} คน · ชาย ${summary.dead_by_sex.male_pct}%` : ''}
          loading={loading}
          tone="red"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card aria-labelledby="rsc-hour" className="p-5">
          <SectionHeader id="rsc-hour" title="เสียชีวิตตามชั่วโมง" description="กทม. สะสมปีนี้ · แท่งเข้ม = 22:00-05:59 · แดง = ชั่วโมงสูงสุด" />
          <div className="mt-4">{loading ? <Skeleton className="h-24" /> : <HourBars values={summary.dead_by_hour} />}</div>
        </Card>
        <Card aria-labelledby="rsc-age" className="p-5">
          <SectionHeader id="rsc-age" title="เสียชีวิตตามช่วงอายุ" description="กทม. สะสมปีนี้" />
          <div className="mt-4">
            {loading ? (
              <Skeleton className="h-16" />
            ) : (
              <ShareBar
                unit=" คน"
                parts={summary.dead_by_age.map((a, i) => ({
                  label: a.label,
                  value: a.count,
                  color: ['bg-slate-300', 'bg-slate-400', 'bg-amber-500', 'bg-red-500', 'bg-red-700', 'bg-slate-600'][i] || 'bg-slate-400',
                }))}
              />
            )}
          </div>
        </Card>
      </div>

      <Card aria-labelledby="rsc-risk" className="p-5">
        <SectionHeader
          id="rsc-risk"
          title="กล้องที่อยู่ในจุดเสี่ยงสูงสุด"
          description={
            status
              ? `นับเคสในรัศมี ${status.radius_m} ม. รอบกล้อง ปี ${status.years?.join(', ') || ''} · ${fmtNum(status.points)} จุดในกทม. (ตัดพิกัดหยาบ ${fmtNum(status.coarse_points)}) · กดเพื่อเปิดกล้อง`
              : 'กำลังเตรียมข้อมูล'
          }
          action={
            <div className="flex items-center gap-2">
              {building && <Badge tone="blue" dot>กำลังดึง {status.progress}/{status.total}</Badge>}
              <Button size="sm" onClick={rebuild} loading={rebuilding || building} disabled={building}>
                อัปเดตจุดเสี่ยง
              </Button>
            </div>
          }
        />
        <div className="mt-3">
          {!risk ? (
            <div className="space-y-2">
              {[1, 2, 3, 4, 5].map((n) => (
                <Skeleton key={n} className="h-12" />
              ))}
            </div>
          ) : risk.items.length ? (
            <ol className="-mx-3 divide-y divide-slate-100">
              {risk.items.map((r, i) => (
                <RiskRow key={r.camid} r={r} rank={i + 1} onOpen={onOpenCamera} />
              ))}
            </ol>
          ) : (
            <EmptyState
              title={building ? `กำลังดึงจุดอุบัติเหตุจาก Thai RSC (${status.progress}/${status.total})` : 'ยังไม่มีข้อมูลจุดเสี่ยง'}
              description={status?.error ? `ผิดพลาด: ${status.error}` : 'ครั้งแรกใช้เวลาประมาณ 2-3 นาที'}
              action={!building && <Button size="sm" onClick={rebuild} loading={rebuilding}>เริ่มดึงข้อมูล</Button>}
            />
          )}
        </div>
      </Card>

      <Card aria-labelledby="rsc-district" className="p-5">
        <SectionHeader
          id="rsc-district"
          title="รายเขต: อุบัติเหตุ เทียบปริมาณรถหน้ากล้อง"
          description="เสียชีวิต/บาดเจ็บสะสมปีนี้จาก Thai RSC · รถเฉลี่ยและสัดส่วนมอเตอร์ไซค์จากกล้อง BMA ในเขตนั้น · 10 เขตแรกเรียงตามผู้เสียชีวิต"
        />
        <div className="mt-3">
          {loading ? <Skeleton className="h-64" /> : <DistrictTable rows={summary.districts.slice(0, 10)} />}
        </div>
        {summary && (
          <p className="mt-3 text-xs text-slate-500">
            {summary.updated} · {summary.source} · ข้อมูลรับแจ้งประกัน พ.ร.บ. ไม่รวมเหตุที่ไม่มีผู้บาดเจ็บ
          </p>
        )}
      </Card>
    </div>
  );
}
