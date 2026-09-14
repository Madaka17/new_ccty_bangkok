import { Card, Badge, Skeleton, ErrorState } from './ui.jsx';
import { STATUS, flowLevel, fmtTime, fmtNum } from './format.js';

function Gauge({ value, colorHex }) {
  const size = 120;
  const stroke = 10;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const v = Math.min(100, Math.max(0, value ?? 0));
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }} role="img" aria-label={`ดัชนีการระบายรถ ${value ?? '-'} จาก 100`}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#e2e8f0" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={colorHex}
          strokeWidth={stroke}
          strokeDasharray={c}
          strokeDashoffset={c - (v / 100) * c}
          strokeLinecap="round"
          className="transition-[stroke-dashoffset] duration-700 ease-out"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-3xl font-semibold text-slate-900 leading-none tabular-nums">{value ?? '–'}</span>
        <span className="text-[11px] text-slate-500 mt-1">/ 100</span>
      </div>
    </div>
  );
}

function StackBar({ green, yellow, red }) {
  const segs = [
    ['green', green, 'โล่ง'],
    ['yellow', yellow, 'ปานกลาง'],
    ['red', red, 'ติดขัด'],
  ];
  return (
    <div>
      <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-slate-100" role="img" aria-label={`โล่ง ${green}% ปานกลาง ${yellow}% ติดขัด ${red}%`}>
        {segs
          .filter(([, v]) => v > 0)
          .map(([k, v]) => (
            <div key={k} className={`h-full ${STATUS[k].bar} transition-[width] duration-500`} style={{ width: `${v}%` }} />
          ))}
      </div>
      <dl className="mt-3 grid grid-cols-3 gap-2">
        {segs.map(([k, v, label]) => (
          <div key={k} className="flex items-center gap-2 min-w-0">
            <span className={`w-2 h-2 rounded-sm shrink-0 ${STATUS[k].bar}`} aria-hidden="true" />
            <dt className="text-xs text-slate-600 truncate">{label}</dt>
            <dd className="text-sm font-semibold text-slate-900 tabular-nums ml-auto">{v}%</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function Delta({ history }) {
  // Change vs ~1 hour ago (20 samples x 3 min)
  if (!history || history.length <= 20) return <p className="text-xs text-slate-500">ยังไม่ครบ 1 ชม. สำหรับเทียบแนวโน้ม</p>;
  const d = history[history.length - 1].flow - history[history.length - 21].flow;
  if (Math.abs(d) <= 2) return <p className="text-xs text-slate-500">ใกล้เคียงกับ 1 ชม.ก่อน</p>;
  const up = d > 0;
  return (
    <p className={`text-xs font-medium ${up ? 'text-emerald-700' : 'text-red-700'}`}>
      {up ? '▲' : '▼'} {up ? 'ดีขึ้น' : 'ชะลอลง'} {Math.abs(d)} จุด จาก 1 ชม.ก่อน
    </p>
  );
}

export default function FlowOverview({ summary, error, onRetry, retrying }) {
  const level = flowLevel(summary?.flow_index);
  const status = STATUS[level.key];

  return (
    <Card aria-labelledby="flow-title" className="p-5 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="flow-title" className="text-[15px] font-semibold text-slate-900">
          ภาพรวมการจราจร กรุงเทพฯ และปริมณฑล
        </h2>
        {summary ? (
          <Badge tone={summary.online === false ? 'yellow' : 'green'} dot>
            {summary.online === false ? 'ข้อมูลล่าช้า' : 'อัปเดต'} {fmtTime(summary.updated_at)} น.
          </Badge>
        ) : (
          <Skeleton className="h-6 w-28" />
        )}
      </div>

      {error && !summary && (
        <div className="mt-4">
          <ErrorState message="ดึงข้อมูลสภาพจราจรไม่สำเร็จ ตรวจสอบว่า server ทำงานอยู่" onRetry={onRetry} retrying={retrying} />
        </div>
      )}

      <div className="mt-5 grid grid-cols-1 md:grid-cols-[auto_1fr] gap-6 md:gap-10 items-center">
        <div className="flex items-center gap-5">
          {summary ? <Gauge value={summary.flow_index} colorHex={status.hex} /> : <Skeleton className="w-[120px] h-[120px] rounded-full" />}
          <div className="min-w-0">
            <p className="text-xs text-slate-500">ดัชนีการระบายรถ</p>
            {summary ? (
              <>
                <p className={`text-xl font-semibold leading-7 ${status.text}`}>{level.label}</p>
                <p className="text-[13px] text-slate-600 mt-0.5 leading-5">{level.hint}</p>
                <div className="mt-2">
                  <Delta history={summary.history} />
                </div>
              </>
            ) : (
              <div className="space-y-2 mt-1">
                <Skeleton className="h-6 w-28" />
                <Skeleton className="h-4 w-56" />
              </div>
            )}
          </div>
        </div>

        <div className="rounded-lg border border-slate-200 p-4">
          <div className="flex items-center justify-between text-xs text-slate-600 mb-3">
            <span>สัดส่วนสภาพถนนทุกสายที่ติดตาม</span>
            <span className="font-medium text-slate-900 tabular-nums">{summary ? `${fmtNum(Math.round(summary.total_km))} กม.` : ''}</span>
          </div>
          {summary?.ready ? <StackBar green={summary.green_pct} yellow={summary.yellow_pct} red={summary.red_pct} /> : <Skeleton className="h-2.5 w-full rounded-full" />}
        </div>
      </div>
    </Card>
  );
}
