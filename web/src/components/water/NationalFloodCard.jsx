// "น้ำท่วมบนถนนทั่วประเทศ" card on the "ระดับน้ำตอนนี้" tab: the same points as the flood pins on the traffic
// map (/api/flood/national-map: flooded roads from Longdo and the Department of Highways with HDMS depths, rivers
// over the bank), added up per province, per depth and per highway, with a summary written from the numbers.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchNationalFloods } from '../../lib/api.js';
import { Badge, Card, ErrorState, FOCUS, SectionHeader, Skeleton } from '../dashboard/ui.jsx';
import { agoText, fmtTime } from '../dashboard/format.js';

const POLL_MS = 3 * 60000;
const TOP = 10;
const RECENT_S = 6 * 3600;
const DEPTHS = [
  { key: 'low', label: 'ไม่ถึง 10 ซม.', color: '#38bdf8' },
  { key: 'mid', label: '10-30 ซม.', color: '#f59e0b' },
  { key: 'deep', label: 'เกิน 30 ซม.', color: '#dc2626' },
  { key: 'unknown', label: 'ไม่ทราบความลึก', color: '#94a3b8' },
];
const HIGHWAY_RE = /(?:ทางหลวง(?:หมายเลข)?|ทล\.)\s*(\d{1,4})/;

const depthOf = (f) => {
  const cm = parseFloat(f.depth_cm);
  return Number.isFinite(cm) ? cm : null;
};
const depthKey = (cm) => (cm == null ? 'unknown' : cm < 10 ? 'low' : cm <= 30 ? 'mid' : 'deep');
const placeTh = (f) => (f.amphoe ? `${f.province === 'กรุงเทพมหานคร' ? 'เขต' : 'อ.'}${f.amphoe}` : '');

function analyse(items) {
  const now = Date.now() / 1000;
  const roads = items.filter((f) => f.kind === 'road');
  const rivers = items.filter((f) => f.kind === 'river');
  const depth = { low: 0, mid: 0, deep: 0, unknown: 0 };
  const provinces = {};
  const highways = {};
  for (const f of items) {
    const p = (provinces[f.province || 'ไม่ทราบจังหวัด'] ||= { province: f.province || 'ไม่ทราบจังหวัด', roads: 0, closed: 0, rivers: 0, maxDepth: null, items: [] });
    p.items.push(f);
    if (f.kind === 'river') {
      p.rivers += 1;
      continue;
    }
    const cm = depthOf(f);
    depth[depthKey(cm)] += 1;
    p.roads += 1;
    if (f.passable === false) p.closed += 1;
    if (cm != null && (p.maxDepth == null || cm > p.maxDepth)) p.maxDepth = cm;
    const hw = HIGHWAY_RE.exec(f.title);
    if (hw) {
      const h = (highways[hw[1]] ||= { no: hw[1], count: 0, closed: 0, provinces: new Set() });
      h.count += 1;
      if (f.passable === false) h.closed += 1;
      if (f.province) h.provinces.add(f.province);
    }
  }
  const byProvince = Object.values(provinces).sort((a, b) => b.closed - a.closed || b.roads - a.roads || b.rivers - a.rivers);
  return {
    roads: roads.length,
    closed: roads.filter((f) => f.passable === false).length,
    recent: roads.filter((f) => f.ts && now - f.ts <= RECENT_S).length,
    rivers: rivers.length,
    depth,
    provinces: byProvince,
    affected: byProvince.filter((p) => p.roads > 0).length,
    highways: Object.values(highways).filter((h) => h.count >= 2).sort((a, b) => b.count - a.count).slice(0, 8),
  };
}

// One paragraph in plain Thai, built from the numbers
function summaryText(a) {
  if (!a.roads && !a.rivers) return 'ตอนนี้ไม่มีรายงานถนนน้ำท่วมหรือแม่น้ำล้นตลิ่ง';
  const parts = [`ตอนนี้มีถนนน้ำท่วม ${a.roads} จุด ใน ${a.affected} จังหวัด`];
  if (a.closed) parts.push(`รถผ่านไม่ได้ ${a.closed} จุด`);
  if (a.depth.deep) parts.push(`น้ำลึกเกิน 30 ซม. ${a.depth.deep} จุด`);
  const top = a.provinces.filter((p) => p.roads > 0).slice(0, 3);
  let text = parts.join(' ');
  if (top.length) text += ` หนักสุดที่ ${top.map((p) => `${p.province} (${p.roads} จุด${p.closed ? ` ผ่านไม่ได้ ${p.closed}` : ''})`).join(' ')}`;
  if (a.rivers) text += ` แม่น้ำล้นตลิ่ง ${a.rivers} จุด ถนนใกล้แม่น้ำอาจท่วมเพิ่ม`;
  if (a.recent) text += ` แจ้งใหม่ใน 6 ชม. ล่าสุด ${a.recent} จุด`;
  return text;
}

function Mini({ label, value, tone }) {
  const color = { red: 'text-red-700', yellow: 'text-amber-700', blue: 'text-blue-700' }[tone] || 'text-slate-900';
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2">
      <p className="text-[11px] text-slate-600">{label}</p>
      <p className={`text-xl font-semibold tabular-nums ${color}`}>{value}</p>
    </div>
  );
}

function ProvinceRow({ p, open, onToggle }) {
  return (
    <li className="border-b border-slate-100 last:border-0">
      <button type="button" onClick={onToggle} aria-expanded={open}
        className={`w-full grid grid-cols-[minmax(0,1fr)_3.5rem_4.5rem_3.5rem_4.5rem] items-center gap-2 px-1.5 py-1.5 text-left text-xs hover:bg-slate-50 cursor-pointer ${FOCUS}`}>
        <span className="truncate text-slate-800">{open ? '▾' : '▸'} {p.province}</span>
        <span className="tabular-nums text-right">{p.roads}</span>
        <span className={`tabular-nums text-right ${p.closed ? 'text-red-700 font-semibold' : 'text-slate-400'}`}>{p.closed}</span>
        <span className="tabular-nums text-right">{p.rivers}</span>
        <span className="tabular-nums text-right text-slate-600">{p.maxDepth != null ? `${p.maxDepth} ซม.` : '–'}</span>
      </button>
      {open && (
        <ul className="pl-5 pr-1.5 pb-2 flex flex-col gap-1 text-[11px] text-slate-700">
          {p.items.map((f) => (
            <li key={f.id}>
              {f.passable === false && <b className="text-red-700">ผ่านไม่ได้ · </b>}
              {f.title}
              <span className="text-slate-500">
                {placeTh(f) ? ` · ${placeTh(f)}` : ''}{depthOf(f) != null ? ` · น้ำ ${depthOf(f)} ซม.` : ''}{f.ts ? ` · ${agoText(f.ts)}` : ''}
              </span>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

export default function NationalFloodCard({ isActive, onNavigate }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const [all, setAll] = useState(false);
  const [open, setOpen] = useState('');

  const load = useCallback(() => {
    fetchNationalFloods().then((d) => { setData(d); setError(false); }).catch(() => setError(true));
  }, []);
  useEffect(() => {
    if (!isActive) return undefined;
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [isActive, load]);

  const a = useMemo(() => (data ? analyse(data.items) : null), [data]);

  if (error && !data) return <ErrorState message="โหลดข้อมูลน้ำท่วมทั่วประเทศไม่สำเร็จ" onRetry={load} />;
  if (!a) return <Skeleton className="h-64 rounded-xl" />;
  const depthTotal = a.roads || 1;
  const rows = all ? a.provinces : a.provinces.slice(0, TOP);

  return (
    <Card className="p-4 flex flex-col gap-4" aria-labelledby="national-flood-title">
      <SectionHeader
        id="national-flood-title"
        title="น้ำท่วมบนถนนทั่วประเทศ"
        description={`ข้อมูลเดียวกับหมุดน้ำท่วมบนแผนที่จราจร · อัปเดต ${fmtTime(data.updated_at)} น.`}
        action={onNavigate && (
          <button type="button" onClick={() => onNavigate('map')} className={`text-xs font-medium text-blue-700 hover:underline cursor-pointer ${FOCUS}`}>
            ดูบนแผนที่จราจร
          </button>
        )}
      />

      <p className="text-sm text-slate-800 leading-6">{summaryText(a)}</p>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
        <Mini label={`ถนนน้ำท่วม (${a.affected} จังหวัด)`} value={a.roads} tone={a.roads ? 'blue' : ''} />
        <Mini label="รถผ่านไม่ได้" value={a.closed} tone={a.closed ? 'red' : ''} />
        <Mini label="น้ำลึกเกิน 30 ซม." value={a.depth.deep} tone={a.depth.deep ? 'yellow' : ''} />
        <Mini label="แม่น้ำล้นตลิ่ง" value={a.rivers} tone={a.rivers ? 'blue' : ''} />
      </div>

      {a.roads > 0 && (
        <div>
          <p className="text-xs text-slate-600 mb-1.5">ความลึกของน้ำบนถนน</p>
          <div className="flex h-3 rounded-full overflow-hidden bg-slate-100" role="img"
            aria-label={DEPTHS.map((d) => `${d.label} ${a.depth[d.key]} จุด`).join(', ')}>
            {DEPTHS.map((d) => a.depth[d.key] > 0 && (
              <span key={d.key} style={{ width: `${(100 * a.depth[d.key]) / depthTotal}%`, background: d.color }} />
            ))}
          </div>
          <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-600">
            {DEPTHS.map((d) => (
              <span key={d.key} className="inline-flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-sm" style={{ background: d.color }} />
                {d.label} <b className="tabular-nums text-slate-900">{a.depth[d.key]}</b>
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[3fr_2fr] gap-4">
        <div>
          <p className="text-[13px] font-semibold text-slate-900 mb-1">จังหวัดที่น้ำท่วมมากสุด</p>
          <div className="grid grid-cols-[minmax(0,1fr)_3.5rem_4.5rem_3.5rem_4.5rem] gap-2 px-1.5 pb-1 text-[11px] text-slate-500 border-b border-slate-200">
            <span>จังหวัด</span><span className="text-right">ถนน</span><span className="text-right">ผ่านไม่ได้</span>
            <span className="text-right">แม่น้ำ</span><span className="text-right">ลึกสุด</span>
          </div>
          <ul>
            {rows.map((p) => (
              <ProvinceRow key={p.province} p={p} open={open === p.province} onToggle={() => setOpen((o) => (o === p.province ? '' : p.province))} />
            ))}
          </ul>
          {a.provinces.length > TOP && (
            <button type="button" onClick={() => setAll((v) => !v)} className={`mt-1.5 text-xs text-blue-700 cursor-pointer ${FOCUS}`}>
              {all ? 'ย่อ' : `ดูทั้งหมด ${a.provinces.length} จังหวัด`}
            </button>
          )}
        </div>
        <div>
          <p className="text-[13px] font-semibold text-slate-900 mb-1">ทางหลวงที่ท่วมหลายจุด</p>
          {a.highways.length === 0 ? (
            <p className="text-xs text-slate-500">ไม่มีทางหลวงที่ท่วมเกิน 1 จุด</p>
          ) : (
            <ul className="flex flex-col gap-1.5">
              {a.highways.map((h) => (
                <li key={h.no} className="flex items-center gap-2 text-xs">
                  <Badge tone={h.closed ? 'red' : 'blue'}>ทล.{h.no}</Badge>
                  <span className="text-slate-800 tabular-nums">{h.count} จุด{h.closed ? ` · ผ่านไม่ได้ ${h.closed}` : ''}</span>
                  <span className="truncate text-slate-500">{[...h.provinces].join(', ')}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <p className="text-[11px] text-slate-500 leading-4">
        ข้อมูลจากกรมทางหลวง (Longdo Traffic และ HDMS) เรื่องที่คนแจ้งผ่าน Longdo และจุดวัดแม่น้ำของคลังข้อมูลน้ำแห่งชาติ ·
        ความลึกน้ำมีเฉพาะจุดที่กรมทางหลวงวัดไว้
      </p>
    </Card>
  );
}
