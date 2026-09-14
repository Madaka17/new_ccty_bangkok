import { CameraIcon } from '../Icons.jsx';
import { Card, SectionHeader, Badge, Skeleton, EmptyState, FOCUS } from './ui.jsx';
import { STATUS, ROAD_LEVEL } from './format.js';

function RoadRow({ r, rank, mode, onOpen }) {
  const key = ROAD_LEVEL[r.level] || 'neutral';
  return (
    <li>
      <button
        type="button"
        onClick={() => onOpen(r.name)}
        title={`เปิดกล้องบน ${r.name}`}
        className={`cursor-pointer w-full text-left flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-slate-50 transition-colors duration-150 group ${FOCUS}`}
      >
        <span className="w-6 text-center text-xs font-medium text-slate-500 tabular-nums shrink-0">{rank}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-slate-900 truncate" title={r.name}>
              {r.name}
            </span>
            <Badge tone={key} className="ml-auto">
              {r.level}
            </Badge>
          </div>
          <div className="mt-1.5 flex items-center gap-3">
            <div className="flex h-1.5 w-24 overflow-hidden rounded-full bg-slate-100 shrink-0" aria-hidden="true">
              {r.green_pct > 0 && <div className={STATUS.green.bar} style={{ width: `${r.green_pct}%` }} />}
              {r.yellow_pct > 0 && <div className={STATUS.yellow.bar} style={{ width: `${r.yellow_pct}%` }} />}
              {r.red_pct > 0 && <div className={STATUS.red.bar} style={{ width: `${r.red_pct}%` }} />}
            </div>
            <span className="text-xs text-slate-600 truncate tabular-nums">
              {mode === 'congested' ? (
                <>
                  ติด <span className="font-medium text-slate-900">{r.red_km}</span> จาก {r.length_km} กม.
                </>
              ) : (
                <>
                  ระบาย <span className="font-medium text-slate-900">{r.flow}</span>/100 · โล่ง {r.green_pct}% · {r.length_km} กม.
                </>
              )}
            </span>
          </div>
        </div>
        <span className="shrink-0 text-slate-400 group-hover:text-blue-600 transition-colors" aria-hidden="true">
          <CameraIcon className="w-4 h-4" />
        </span>
      </button>
    </li>
  );
}

function RoadList({ id, title, description, badge, rows, ready, mode, empty, onOpen }) {
  return (
    <Card aria-labelledby={id} className="p-5">
      <SectionHeader id={id} title={title} description={description} action={badge} />
      <div className="mt-3">
        {!ready ? (
          <div className="space-y-2">
            {[1, 2, 3, 4, 5].map((n) => (
              <Skeleton key={n} className="h-12" />
            ))}
          </div>
        ) : rows.length ? (
          <ol className="-mx-3 divide-y divide-slate-100">
            {rows.map((r, i) => (
              <RoadRow key={r.name} r={r} rank={i + 1} mode={mode} onOpen={onOpen} />
            ))}
          </ol>
        ) : (
          <EmptyState title={empty} />
        )}
      </div>
    </Card>
  );
}

export default function RoadLists({ summary, onOpenRoad }) {
  const ready = !!summary?.ready;
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      <RoadList
        id="roads-congested"
        title="ถนนที่ควรเลี่ยงตอนนี้"
        description="เรียงตามระยะทางที่ติดขัด · กดเพื่อเปิดกล้องบนถนนนั้น"
        badge={<Badge tone="red" dot>ติดขัด</Badge>}
        rows={summary?.congested || []}
        ready={ready}
        mode="congested"
        empty="ไม่มีถนนสายหลักที่ติดขัดในขณะนี้"
        onOpen={onOpenRoad}
      />
      <RoadList
        id="roads-free"
        title="ถนนสายหลักที่วิ่งได้สบาย"
        description="สายยาวที่ระบายรถได้ดี · กดเพื่อเปิดกล้องบนถนนนั้น"
        badge={<Badge tone="green" dot>คล่องตัว</Badge>}
        rows={summary?.free_flow || []}
        ready={ready}
        mode="free"
        empty="ยังไม่มีข้อมูลถนนที่คล่องตัว"
        onOpen={onOpenRoad}
      />
    </div>
  );
}
