import { CameraIcon, CarIcon, MapPinIcon } from '../Icons.jsx';
import { Card, Badge, Skeleton, Truncate } from './ui.jsx';
import { fmtNum } from './format.js';

function ActivityIcon({ className = 'w-5 h-5' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  );
}

function Tile({ icon: Icon, label, value, sub, badge, loading }) {
  return (
    <Card as="div" className="p-4 flex items-start gap-3">
      <span className="w-9 h-9 rounded-lg bg-slate-100 text-slate-700 flex items-center justify-center shrink-0">
        <Icon className="w-5 h-5" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs text-slate-600 truncate">{label}</p>
          {badge}
        </div>
        {loading ? <Skeleton className="h-7 w-20 mt-1" /> : <p className="text-2xl font-semibold text-slate-900 leading-8 tabular-nums">{value}</p>}
        {sub && <Truncate text={sub} className="text-xs text-slate-500 mt-0.5" />}
      </div>
    </Card>
  );
}

export default function KpiTiles({ summary, ai, liveCount }) {
  const loading = !summary;
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
      <Tile
        icon={CameraIcon}
        label="กล้อง CCTV ที่เปิดดูอยู่"
        value={`${liveCount} ตัว`}
        sub={liveCount ? 'ดูภาพสดได้ในหน้ากล้อง' : 'ยังไม่ได้เปิดกล้อง'}
        badge={liveCount > 0 ? <Badge tone="green" dot>LIVE</Badge> : null}
      />
      <Tile
        icon={CarIcon}
        label="รถหน้ากล้อง AI ตอนนี้"
        value={ai?.active ? `${fmtNum(ai.total)} คัน` : '–'}
        sub={ai?.active ? ai.title : 'ยังไม่ได้เปิดกล้อง AI'}
        badge={ai?.active ? <Badge tone="blue">YOLO11</Badge> : <Badge>ว่าง</Badge>}
      />
      <Tile
        icon={MapPinIcon}
        label="ถนนที่ติดตาม"
        value={summary ? `${fmtNum(summary.road_count)} สาย` : '–'}
        sub="วิเคราะห์จากเส้นจราจร Longdo ทุก 3 นาที"
        loading={loading}
      />
      <Tile
        icon={ActivityIcon}
        label="สัดส่วนถนนที่คล่องตัว"
        value={summary ? `${summary.green_pct}%` : '–'}
        sub={summary ? `ติดขัด ${summary.red_pct}% · ปานกลาง ${summary.yellow_pct}%` : ''}
        loading={loading}
      />
    </div>
  );
}
