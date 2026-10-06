// Bangkok roads with standing water now, one plain-Thai notice each in a fixed order: where and what, when,
// what to do, then the source and the reading time (/api/flood/notices, flood_service.notices). The advice comes
// from the depth rule table on the server, not from the AI. Shown on the "ถนนน้ำท่วม" tab of the Water page.
import { useEffect, useState } from 'react';
import { Card, SectionHeader, Skeleton, EmptyState, ErrorState } from '../dashboard/ui.jsx';
import { fetchFloodNotices } from '../../lib/api.js';

const POLL_MS = 5 * 60000;   // the sensors report every 5 minutes
const TONE = {
  passable: 'border-emerald-200 bg-emerald-50 text-emerald-800',
  careful: 'border-amber-200 bg-amber-50 text-amber-800',
  no_car: 'border-red-200 bg-red-50 text-red-800',
  avoid: 'border-red-300 bg-red-100 text-red-900',
};

export default function RoadFloodNotices({ isActive }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);

  const load = () =>
    fetchFloodNotices()
      .then((d) => { setData(d); setError(false); })
      .catch(() => setError(true));

  useEffect(() => {
    if (!isActive) return undefined;
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [isActive]); // eslint-disable-line react-hooks/exhaustive-deps

  if (error && !data) return <ErrorState message="โหลดถนนน้ำขังใน กทม. ไม่สำเร็จ" onRetry={load} />;
  if (!data) return <Skeleton className="h-[160px] rounded-xl" />;

  return (
    <Card className="p-4 flex flex-col gap-3">
      <SectionHeader
        title="ถนนใน กทม. ที่น้ำขังตอนนี้"
        description="จากเครื่องวัดระดับน้ำบนถนนของสำนักการระบายน้ำ กทม. คำแนะนำมาจากความลึกของน้ำ"
      />
      {!data.sensors ? (
        <EmptyState title="ตอนนี้อ่านค่าเครื่องวัดของสำนักการระบายน้ำไม่ได้" description="จึงยังบอกไม่ได้ว่าถนนไหนน้ำขัง ระบบจะลองใหม่เองทุก 5 นาที" />
      ) : data.items.length ? (
        <ul className="flex flex-col gap-2">
          {data.items.map((n) => (
            <li key={n.where} className={`rounded-lg border px-3 py-2 flex flex-col gap-0.5 ${TONE[n.advice]}`}>
              <p className="text-sm font-semibold text-slate-900">{n.where} {n.what}</p>
              {n.when && <p className="text-[13px] text-slate-700">{n.when}</p>}
              <p className="text-sm font-semibold">{n.action}</p>
              <p className="text-xs text-slate-600">ข้อมูล: {n.source}</p>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState title="ตอนนี้ไม่มีถนนใน กทม. ที่น้ำขัง" description="เครื่องวัดที่ขัดข้องไม่นับรวม ไม่ได้แปลว่าบริเวณนั้นไม่ท่วม" />
      )}
    </Card>
  );
}
