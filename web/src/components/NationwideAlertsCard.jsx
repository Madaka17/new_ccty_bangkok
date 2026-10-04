// "สถานการณ์ทั่วประเทศตอนนี้" on the Alerts page: the nationwide things alert_service.py warns about, as they
// stand now - provinces at the flood / critical level (/api/flood/provinces), closed roads and accidents in
// every province (/api/road/events).
import { useEffect, useMemo, useState } from 'react';
import { fetchProvinceFloods, fetchRoadEvents } from '../lib/api.js';
import { Badge, Card, Skeleton } from './dashboard/ui.jsx';
import { fmtDateTime } from './dashboard/format.js';

const POLL_MS = 60000;
const LEVEL = { critical: ['วิกฤต', 'red'], flood: ['น้ำท่วม', 'yellow'] };
const TOP = 8;

function Count({ label, value, tone }) {
  return (
    <div className="rounded-lg border border-slate-200 px-3 py-2">
      <p className="text-[11px] text-slate-600">{label}</p>
      <p className={`text-xl font-semibold tabular-nums ${value ? tone : 'text-slate-900'}`}>{value}</p>
    </div>
  );
}

export default function NationwideAlertsCard({ isActive }) {
  const [floods, setFloods] = useState(null);
  const [road, setRoad] = useState(null);
  const [all, setAll] = useState(false);

  useEffect(() => {
    if (!isActive) return undefined;
    const load = () => {
      fetchProvinceFloods().then(setFloods).catch(() => {});
      fetchRoadEvents().then(setRoad).catch(() => {});
    };
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [isActive]);

  const flooded = useMemo(
    () => (floods?.provinces || []).filter((p) => LEVEL[p.level]).sort((a, b) => (a.level === b.level ? 0 : a.level === 'critical' ? -1 : 1)),
    [floods],
  );
  const closed = useMemo(() => (road?.closures || []).filter((c) => c.kind === 'closed'), [road]);
  const closedBy = useMemo(() => {
    const n = {};
    for (const c of closed) n[c.province || 'ไม่ทราบจังหวัด'] = (n[c.province || 'ไม่ทราบจังหวัด'] || 0) + 1;
    return Object.entries(n).sort((a, b) => b[1] - a[1]);
  }, [closed]);
  const accidents = useMemo(() => (road?.incidents || []).filter((i) => i.kind === 'accident'), [road]);

  return (
    <Card className="p-4 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-semibold text-slate-900">สถานการณ์ทั่วประเทศตอนนี้</p>
        {road?.updated_at && <span className="text-xs text-slate-500">อัปเดต {fmtDateTime(road.updated_at)}</span>}
      </div>
      {floods === null && road === null ? (
        <Skeleton className="h-24" />
      ) : (
        <>
          <div className="grid grid-cols-3 gap-2">
            <Count label="จังหวัดน้ำท่วม" value={flooded.length} tone="text-red-700" />
            <Count label="ถนนปิด" value={closed.length} tone="text-red-700" />
            <Count label="อุบัติเหตุ" value={accidents.length} tone="text-amber-700" />
          </div>

          {flooded.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-slate-700 mb-1">จังหวัดที่น้ำท่วม</p>
              <ul className="divide-y divide-slate-100">
                {(all ? flooded : flooded.slice(0, TOP)).map((p) => (
                  <li key={p.province} className="py-1.5 flex items-start gap-2 text-sm">
                    <Badge tone={LEVEL[p.level][1]} dot className="shrink-0">{LEVEL[p.level][0]}</Badge>
                    <span className="min-w-0">
                      <b className="text-slate-900">{p.province}</b>
                      <span className="text-xs text-slate-600"> · {p.summary}</span>
                    </span>
                  </li>
                ))}
              </ul>
              {flooded.length > TOP && (
                <button type="button" onClick={() => setAll((v) => !v)} className="cursor-pointer mt-1 text-xs text-blue-700 hover:underline">
                  {all ? 'แสดงน้อยลง' : `ดูทั้งหมด ${flooded.length} จังหวัด`}
                </button>
              )}
            </div>
          )}

          {closedBy.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-slate-700 mb-1">ถนนปิด แยกตามจังหวัด</p>
              <div className="flex flex-wrap gap-1.5">
                {closedBy.map(([province, n]) => (
                  <span key={province} className="rounded-md border border-slate-200 px-2 py-0.5 text-xs text-slate-800">
                    {province} <b className="tabular-nums text-red-700">{n}</b>
                  </span>
                ))}
              </div>
            </div>
          )}

          {accidents.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-slate-700 mb-1">อุบัติเหตุตอนนี้</p>
              <ul className="space-y-1 text-sm">
                {accidents.map((i) => (
                  <li key={i.id} className="text-slate-900 leading-5">
                    {i.title}
                    <span className="text-xs text-slate-500">{i.province ? ` · ${i.province}` : ''}{i.start ? ` · เริ่ม ${i.start.slice(11, 16)} น.` : ''}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <p className="text-[11px] text-slate-500">
            เปิดรับแจ้งเตือนแล้ว เว็บจะเตือนเมื่อมีจังหวัดน้ำท่วมใหม่ ถนนปิดใหม่ หรืออุบัติเหตุใหม่ในทุกจังหวัด
          </p>
        </>
      )}
    </Card>
  );
}
