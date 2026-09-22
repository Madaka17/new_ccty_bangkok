import { Card, SectionHeader, Badge, Skeleton, EmptyState, Truncate, FOCUS } from '../dashboard/ui.jsx';
import { StatTile, ShareBar } from '../dashboard/primitives.jsx';
import { fmtNum } from '../dashboard/format.js';
import { useMemo } from 'react';
import { getBmaSnapshotUrl } from '../../lib/api.js';

export const LEVEL = {
  heavy: { label: 'หนาแน่น', tone: 'red' },
  moderate: { label: 'ปานกลาง', tone: 'yellow' },
  free: { label: 'คล่องตัว', tone: 'green' },
};
export const levelOf = (lv) => LEVEL[lv] || LEVEL.free;

// KPI row + type/congestion shares + top spots + districts/roads. Everything here is "right now".
export default function BmaOverview({ analytics, cameras, loading, onOpenCamera, onFilterDistrict, onFilterRoad }) {
  const s = analytics?.summary || null;
  // New cache-buster on every analytics poll, otherwise the browser keeps the first thumbnail it loaded
  const tick = useMemo(() => Date.now(), [analytics]);
  const online = s?.online_cameras ?? cameras.filter((c) => c.status === 'online').length;
  const total = s?.total_vehicles ?? cameras.reduce((a, c) => a + (c.total || 0), 0);
  const cars = s?.cars ?? 0;
  const motos = s?.motorcycles ?? 0;
  const trucks = s?.trucks ?? 0;
  const cg = s?.congestion || {};

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <StatTile label="กล้องออนไลน์" value={s ? `${fmtNum(online)} / ${fmtNum(s.total_cameras)}` : '–'} sub={s ? `ออฟไลน์ ${fmtNum(s.offline_cameras)} ตัว` : ''} loading={loading} badge={online > 0 ? <Badge tone="green" dot>LIVE</Badge> : null} />
        <StatTile label="รถที่เห็นตอนนี้ (ทุกกล้อง)" value={s ? `${fmtNum(total)} คัน` : '–'} sub={s ? `เฉลี่ย ${s.avg_per_camera ?? 0} คัน/กล้อง` : ''} loading={loading} tone="blue" />
        <StatTile label="รถยนต์" value={s ? fmtNum(cars) : '–'} sub={s ? `${s.cars_pct ?? 0}% ของทั้งหมด` : ''} loading={loading} />
        <StatTile label="มอเตอร์ไซค์" value={s ? fmtNum(motos) : '–'} sub={s ? `${s.motorcycles_pct ?? 0}% ของทั้งหมด` : ''} loading={loading} />
        <StatTile label="รถบรรทุก / บัส" value={s ? fmtNum(trucks) : '–'} sub={s ? `${s.trucks_pct ?? 0}% ของทั้งหมด` : ''} loading={loading} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card className="p-5">
          <SectionHeader title="สัดส่วนประเภทรถ" description="รวมจากภาพล่าสุดของทุกกล้องที่ออนไลน์" />
          <div className="mt-4">
            {loading ? (
              <Skeleton className="h-16 w-full" />
            ) : (
              <ShareBar
                unit=" คัน"
                parts={[
                  { label: 'รถยนต์', value: cars, color: 'bg-blue-600' },
                  { label: 'มอเตอร์ไซค์', value: motos, color: 'bg-amber-500' },
                  { label: 'บรรทุก/บัส', value: trucks, color: 'bg-slate-500' },
                ]}
              />
            )}
          </div>
        </Card>
        <Card className="p-5">
          <SectionHeader title="สภาพจราจรหน้ากล้อง" description="จำนวนจุดกล้องแยกตามความหนาแน่น (0-4 คัน = คล่องตัว, 5-12 = ปานกลาง, 13+ = หนาแน่น)" />
          <div className="mt-4">
            {loading ? (
              <Skeleton className="h-16 w-full" />
            ) : (
              <ShareBar
                unit=" จุด"
                parts={[
                  { label: 'คล่องตัว', value: cg.free_count || 0, color: 'bg-emerald-600' },
                  { label: 'ปานกลาง', value: cg.moderate_count || 0, color: 'bg-amber-500' },
                  { label: 'หนาแน่น', value: cg.heavy_count || 0, color: 'bg-red-600' },
                ]}
              />
            )}
          </div>
        </Card>
      </div>

      <Card className="p-5">
        <SectionHeader title="จุดที่รถหนาแน่นที่สุดตอนนี้" description="15 กล้องที่เห็นรถมากที่สุดในภาพล่าสุด · แตะเพื่อดูภาพและสตรีมสด" />
        <ol className="mt-3 divide-y divide-slate-100">
          {loading ? (
            [...Array(5)].map((_, i) => (
              <li key={i} className="py-2">
                <Skeleton className="h-9 w-full" />
              </li>
            ))
          ) : !analytics?.top_congested?.length ? (
            <li className="py-2">
              <EmptyState title="ยังไม่มีข้อมูล รอรอบสแกนแรก" />
            </li>
          ) : (
            analytics.top_congested.map((cam, i) => {
              const max = analytics.top_congested[0]?.total || 1;
              const lv = levelOf(cam.level);
              return (
                <li key={cam.camid}>
                  <button
                    type="button"
                    onClick={() => onOpenCamera(cam)}
                    className={`cursor-pointer w-full text-left py-2 px-1 flex items-center gap-3 rounded-lg hover:bg-slate-50 transition-colors ${FOCUS}`}
                  >
                    <span className="w-5 text-xs text-slate-500 tabular-nums text-right shrink-0">{i + 1}</span>
                    <div className="w-14 h-10 rounded-md bg-slate-900 shrink-0 overflow-hidden relative border border-slate-200">
                      <img src={getBmaSnapshotUrl(cam.camid, false, tick)} alt="" loading="lazy" className="w-full h-full object-cover" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <Truncate text={cam.title || `กล้อง ${cam.camid}`} className="text-sm font-medium text-slate-900" />
                      <Truncate text={`${cam.district || 'กทม.'}${cam.road ? ` · ${cam.road}` : ''} · ${cam.camera_code || ''}`} className="text-xs text-slate-500" />
                    </div>
                    <div className="hidden sm:block w-28">
                      <div className="h-1.5 rounded-full bg-slate-100 overflow-hidden">
                        <div className="h-full bg-blue-600" style={{ width: `${Math.max(4, (cam.total / max) * 100)}%` }} />
                      </div>
                    </div>
                    <span className="text-sm font-semibold tabular-nums text-slate-900 w-14 text-right">{cam.total} คัน</span>
                    <Badge tone={lv.tone}>{lv.label}</Badge>
                  </button>
                </li>
              );
            })
          )}
        </ol>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card className="p-5">
          <SectionHeader title="รายเขต" description="รถที่เห็นรวมต่อเขต · แตะเพื่อดูกล้องในเขตนั้น" />
          <div className="mt-3 grid grid-cols-2 sm:grid-cols-3 gap-2 max-h-[360px] overflow-y-auto pr-1">
            {loading
              ? [...Array(6)].map((_, i) => <Skeleton key={i} className="h-16 w-full" />)
              : (analytics?.districts || []).map((d) => (
                  <button
                    key={d.district}
                    type="button"
                    onClick={() => onFilterDistrict(d.district)}
                    className={`cursor-pointer text-left rounded-lg border border-slate-200 bg-white hover:bg-slate-50 px-3 py-2 transition-colors ${FOCUS}`}
                  >
                    <Truncate text={d.district} className="text-xs font-medium text-slate-900" />
                    <p className="text-lg font-semibold text-slate-900 tabular-nums leading-6">
                      {fmtNum(d.total)} <span className="text-xs font-normal text-slate-500">คัน</span>
                    </p>
                    <p className="text-[11px] text-slate-500">
                      {d.cameras} กล้อง · เฉลี่ย {d.avg_vehicles}
                      {d.heavy_count ? ` · หนาแน่น ${d.heavy_count}` : ''}
                    </p>
                  </button>
                ))}
          </div>
        </Card>
        <Card className="p-5">
          <SectionHeader title="ถนนสายหลัก" description="10 ถนนที่รถมากที่สุด · แตะเพื่อดูกล้องบนถนนนั้น" />
          <ul className="mt-3 divide-y divide-slate-100">
            {loading
              ? [...Array(6)].map((_, i) => (
                  <li key={i} className="py-2">
                    <Skeleton className="h-8 w-full" />
                  </li>
                ))
              : (analytics?.major_roads || []).slice(0, 10).map((r) => {
                  const lv = levelOf(r.level);
                  return (
                    <li key={r.road}>
                      <button
                        type="button"
                        onClick={() => onFilterRoad(r.road)}
                        className={`cursor-pointer w-full text-left py-2 px-1 flex items-center gap-3 rounded-lg hover:bg-slate-50 transition-colors ${FOCUS}`}
                      >
                        <Truncate text={r.road} className="text-sm text-slate-900 flex-1 min-w-0" />
                        <span className="text-xs text-slate-500 whitespace-nowrap">{r.cameras} กล้อง</span>
                        <span className="text-sm font-semibold tabular-nums text-slate-900 w-14 text-right">{r.total} คัน</span>
                        <Badge tone={lv.tone}>{lv.label}</Badge>
                      </button>
                    </li>
                  );
                })}
          </ul>
        </Card>
      </div>
    </div>
  );
}
