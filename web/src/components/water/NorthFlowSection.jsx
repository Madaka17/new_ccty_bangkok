// เส้นทางน้ำเหนือ: the simple view is NorthRouteView (provinces on the way, 7 days, 3D map, north_route.py); the
// detail view keeps every RID discharge gauge from the Ping / Wang / Yom / Nan down the Chao Phraya to Ayutthaya,
// the 10-minute estimates, the routed 4-day outlook (north_flow.py), upstream dams and the warnings they add up to,
// with the AI's line per gauge (north_impact_agent.py).
import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchNorthImpact, fetchWaterNorth } from '../../lib/api.js';
import { Card, SectionHeader, Badge, Button, Segmented, Skeleton, EmptyState, ErrorState, FOCUS } from '../dashboard/ui.jsx';
import { StatTile, StatusBanner } from '../dashboard/primitives.jsx';
import { fmtDateTime, fmtDay, fmtNum, fmtTime } from '../dashboard/format.js';
import NorthFlowMap from './NorthFlowMap.jsx';
import { HowToRead, TenMinuteTable, fullness, nowOf } from './NorthFlowExplain.jsx';
import NorthRouteView from './NorthRouteView.jsx';

const POLL_MS = 5 * 60000;
const STATUS = {
  overflow: { label: 'ล้นตลิ่ง', tone: 'red', bar: 'bg-red-600' },
  high: { label: 'น้ำมาก', tone: 'yellow', bar: 'bg-amber-500' },
  normal: { label: 'ปกติ', tone: 'green', bar: 'bg-emerald-600' },
  offline: { label: 'ไม่มีข้อมูล', tone: 'neutral', bar: 'bg-slate-400' },
};
const TRIBUTARIES = [
  { river: 'ping', title: 'แม่น้ำปิง-วัง', codes: ['P.1', 'W.4A', 'P.7A', 'P.17'], dams: ['ภูมิพล'] },
  { river: 'yom', title: 'แม่น้ำยม', codes: ['Y.4', 'Y.16'], dams: [] },
  { river: 'nan', title: 'แม่น้ำน่าน', codes: ['N.60', 'N.5A', 'N.7A', 'N.67'], dams: ['สิริกิติ์', 'แควน้อยบำรุงแดน'] },
];
// Main stem, upstream first; `joins` is a tributary gauge that enters just above the node
const MAIN = [
  { code: 'C.2', title: 'นครสวรรค์ (ปากน้ำโพ)' },
  { code: 'C.13', title: 'ชัยนาท (ท้ายเขื่อนเจ้าพระยา)', joins: 'Ct.19' },
  { code: 'C.3', title: 'สิงห์บุรี' },
  { code: 'C.7A', title: 'อ่างทอง' },
  { code: 'C.35', title: 'พระนครศรีอยุธยา', joins: 'S.26' },
];
const OBS = '#2563eb';
const TEN = '#0ea5e9';
const LATE = '#64748b';
const CAP = '#dc2626';
const HIGH = '#d97706';
const GRID = { stroke: '#94a3b8', strokeOpacity: 0.25, strokeWidth: 1 };
const W = 720;
const H = 240;
const PAD = { l: 48, r: 14, t: 14, b: 30 };

const fmtQ = (q) => (q == null ? '–' : fmtNum(Math.round(q)));
const inText = (h) => (h < 36 ? `~${h} ชม.` : `~${(h / 24).toFixed(1).replace('.0', '')} วัน`);
const fmtWhen = (ts) => `${fmtDay(ts * 1000)} ${fmtTime(ts)} น.`;

function Change({ value }) {
  if (value == null) return null;
  if (Math.abs(value) < 5) return <span className="text-slate-500">คงที่</span>;
  return value > 0 ? <span className="text-red-700">▲ {fmtQ(value)}</span> : <span className="text-emerald-700">▼ {fmtQ(-value)}</span>;
}

// Change over the last hour (10-minute data) when there is one, else over 24 h (hourly RID data)
function Recent({ s }) {
  const n = nowOf(s);
  return n.change1h != null ? (
    <span>
      1 ชม. <Change value={n.change1h} />
    </span>
  ) : (
    <span>
      24 ชม. <Change value={s?.change_24h} />
    </span>
  );
}

function AiLine({ text }) {
  if (!text) return null;
  return (
    <p className="mt-1.5 text-xs text-slate-700 leading-5">
      <span className="font-semibold text-blue-700">AI:</span> {text}
    </p>
  );
}

function PctBar({ pct }) {
  if (pct == null) return null;
  const st = pct >= 100 ? STATUS.overflow : pct >= 70 ? STATUS.high : STATUS.normal;
  return (
    <div className="h-1.5 w-full rounded-full bg-slate-100 overflow-hidden" aria-hidden="true">
      <div className={`h-full rounded-full ${st.bar}`} style={{ width: `${Math.min(100, pct)}%` }} />
    </div>
  );
}

// One gauge as a compact, clickable row: flow now, % of the channel's capacity, 24 h change, status
function GaugeRow({ s, selected, onSelect, text }) {
  const st = STATUS[s.status] || STATUS.offline;
  const n = nowOf(s);
  return (
    <button
      type="button"
      onClick={() => s.history?.length && onSelect(s.code)}
      aria-pressed={selected}
      className={`w-full text-left rounded-lg border px-3 py-2 transition-colors ${FOCUS} ${selected ? 'border-blue-300 bg-blue-50' : 'border-slate-200 hover:bg-slate-50'} ${s.history?.length ? 'cursor-pointer' : 'cursor-default'}`}
    >
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-slate-900 truncate">{s.province}</span>
        <span className="text-xs text-slate-500 truncate">{s.code} · {s.name}</span>
        <Badge tone={st.tone} className="ml-auto">{st.label}</Badge>
      </div>
      <div className="mt-1.5 flex items-center gap-3 text-xs text-slate-600 tabular-nums">
        {n.q != null ? (
          <>
            <span className="text-slate-900 font-medium">{fmtQ(n.q)} ลบ.ม./วิ</span>
            {n.pct != null && <span>เต็ม {Math.round(n.pct)}% · {fullness(n.pct)}</span>}
            <span className="ml-auto">
              <Recent s={s} />
            </span>
          </>
        ) : s.below_bank != null ? (
          <span>{s.below_bank > 0 ? `ต่ำกว่าตลิ่ง ${s.below_bank.toFixed(2)} ม.` : `สูงกว่าตลิ่ง ${(-s.below_bank).toFixed(2)} ม.`} (ไม่มีข้อมูลปริมาณน้ำ)</span>
        ) : (
          <span>ไม่มีข้อมูลล่าสุด</span>
        )}
      </div>
      {n.pct != null && (
        <div className="mt-1.5">
          <PctBar pct={n.pct} />
        </div>
      )}
      <AiLine text={text} />
    </button>
  );
}

function Dam({ d }) {
  return (
    <div className="flex items-center gap-2 text-xs text-slate-600 tabular-nums">
      <span className="text-slate-900">เขื่อน{d.name}</span>
      <span>{d.storage_pct != null ? `${Math.round(d.storage_pct)}%` : '–'}</span>
      <span className="ml-auto" title="ล้าน ลบ.ม./วัน แปลงเป็น ลบ.ม./วินาที">
        เข้า {fmtQ(d.inflow_m3s)} · ระบาย {fmtQ(d.released_m3s)} ลบ.ม./วิ
      </span>
    </div>
  );
}

// Main-stem node: flow now, where the outlook takes it and when water now at Nakhon Sawan gets here
function MainNode({ s, title, selected, onSelect, text }) {
  const st = STATUS[s?.status] || STATUS.offline;
  const pk = s?.peak;
  const n = nowOf(s);
  return (
    <button
      type="button"
      onClick={() => s?.history?.length && onSelect(s.code)}
      aria-pressed={selected}
      className={`w-full text-left rounded-xl border p-3 transition-colors ${FOCUS} ${selected ? 'border-blue-300 bg-blue-50' : 'border-slate-200 bg-white hover:bg-slate-50'} cursor-pointer`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-slate-900">{title}</span>
        <span className="text-xs text-slate-500">{s?.code} · {s?.name}</span>
        <Badge tone={st.tone} dot className="ml-auto">{st.label}</Badge>
      </div>
      <div className="mt-2 grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-1 text-xs text-slate-600 tabular-nums">
        <div>
          ตอนนี้ <span className="text-base font-semibold text-slate-900">{fmtQ(n.q)}</span> ลบ.ม./วิ
          {n.pct != null && <span> · เต็ม {Math.round(n.pct)}%</span>}
          {n.t && <span className="block text-[11px] text-slate-500">{n.est ? 'ประมาณ' : 'กรมชลฯ'} {fmtTime(n.t)} น.</span>}
        </div>
        <div>
          <Recent s={s} />
          {n.pct != null && <span className="block text-[11px] text-slate-500">{fullness(n.pct)}</span>}
        </div>
        <div className="col-span-2 sm:col-span-1">
          {pk && pk.q > (n.q || 0) * 1.03 ? (
            <span className={pk.status === 'overflow' ? 'text-red-700 font-medium' : pk.status === 'high' ? 'text-amber-700 font-medium' : ''}>
              คาดสูงสุด {fmtQ(pk.q)} ({Math.round(pk.pct)}%) ใน {inText(pk.in_h)}
            </span>
          ) : pk ? (
            <span>คาดว่าไม่สูงขึ้นกว่านี้ใน 4 วัน</span>
          ) : (
            <span className="text-slate-500">ไม่มีค่าคาดการณ์</span>
          )}
        </div>
      </div>
      {n.pct != null && (
        <div className="mt-2">
          <PctBar pct={n.pct} />
        </div>
      )}
      <AiLine text={text} />
      {s?.official && (
        <p className="mt-1.5 text-xs text-slate-500">
          สสน. คาดระดับน้ำสูงสุด 7 วัน {s.official.peak_msl.toFixed(2)} ม.รทก. (ตลิ่ง {s.official.bank?.toFixed(2) ?? '–'}) ราว {fmtDay(s.official.peak_t * 1000)}
        </p>
      )}
    </button>
  );
}

function Connector({ lag, from, joins }) {
  return (
    <div className="flex items-center gap-3 pl-6 py-1 text-xs text-slate-500">
      <span className="w-px h-6 bg-slate-300" aria-hidden="true" />
      <span>↓ เดินทาง {lag != null ? inText(lag) : '–'}{from ? ` (จาก ${from})` : ''}</span>
      {joins && (
        <span className="ml-auto">
          + {joins.river} {fmtQ(joins.q)} ลบ.ม./วิ
        </span>
      )}
    </div>
  );
}

// Observed 72 h + routed outlook for one gauge, against the channel capacity
function FlowChart({ s, dataTime }) {
  const [hover, setHover] = useState(null);
  useEffect(() => setHover(null), [s?.code]);
  const chart = useMemo(() => {
    if (!s?.history?.length) return null;
    const obs = s.history.map((p) => ({ t: p.t, v: p.q }));
    const fut = (s.forecast || []).map((p) => ({ t: p.t, v: p.q }));
    const ten = (s.ten_min || []).map((p) => ({ t: p.t, v: p.q }));
    const now = obs[obs.length - 1].t;
    const t0 = obs[0].t;
    const t1 = fut.length ? fut[fut.length - 1].t : now;
    const hi = Math.max(...obs.map((p) => p.v), ...fut.map((p) => p.v), ...ten.map((p) => p.v), s.qmax || 0) * 1.08 || 1;
    const x = (t) => PAD.l + ((W - PAD.l - PAD.r) * (t - t0)) / Math.max(1, t1 - t0);
    const y = (v) => PAD.t + (H - PAD.t - PAD.b) * (1 - v / hi);
    const path = (pts) => pts.map((p, i) => `${i ? 'L' : 'M'}${x(p.t).toFixed(1)},${y(p.v).toFixed(1)}`).join(' ');
    const step = [100, 250, 500, 1000].find((v) => hi / v <= 6) || 2000;
    const ticks = [];
    for (let v = 0; v <= hi; v += step) ticks.push(v);
    const days = [];
    for (let t = Math.ceil(t0 / 3600) * 3600; t <= t1; t += 3600) if (new Date(t * 1000).getHours() === 0) days.push(t);
    const leadT = s.lead_h != null ? (dataTime || now) + s.lead_h * 3600 : null;
    const measured = leadT ? fut.filter((p) => p.t <= leadT) : fut;
    const assumed = leadT ? fut.filter((p) => p.t >= leadT) : [];
    return { obs, fut, ten, now, t0, t1, x, y, path, ticks, days, leadT, measured, assumed };
  }, [s, dataTime]);

  if (!chart) return <EmptyState title="สถานีนี้ไม่มีข้อมูลปริมาณน้ำย้อนหลัง" description="เลือกสถานีอื่นจากรายการด้านบน" />;

  const onMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const t = chart.t0 + ((((e.clientX - rect.left) / rect.width) * W - PAD.l) / (W - PAD.l - PAD.r)) * (chart.t1 - chart.t0);
    const pool = t <= chart.now || !chart.fut.length ? chart.obs : chart.fut;
    let best = pool[0];
    for (const p of pool) if (Math.abs(p.t - t) < Math.abs(best.t - t)) best = p;
    setHover({ ...best, future: best.t > chart.now });
  };
  const shown = hover || { ...chart.obs[chart.obs.length - 1], future: false };
  const pct = s.qmax ? (100 * shown.v) / s.qmax : null;

  return (
    <div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Stat label={shown.future ? `คาดการณ์ ${fmtWhen(shown.t)}` : `วัดได้ ${fmtWhen(shown.t)}`} value={`${fmtQ(shown.v)} ลบ.ม./วิ`} sub={pct != null ? `${Math.round(pct)}% ของความจุลำน้ำ` : ''} tone={pct >= 100 ? 'red' : undefined} />
        <Stat label="ความจุลำน้ำ (เต็มตลิ่ง)" value={s.qmax ? `${fmtQ(s.qmax)} ลบ.ม./วิ` : '–'} sub={s.below_bank != null ? (s.below_bank > 0 ? `ระดับน้ำต่ำกว่าตลิ่ง ${s.below_bank.toFixed(2)} ม.` : `สูงกว่าตลิ่ง ${(-s.below_bank).toFixed(2)} ม.`) : ''} />
        <Stat
          label="คาดสูงสุดใน 4 วัน"
          value={s.peak ? `${fmtQ(s.peak.q)} ลบ.ม./วิ` : '–'}
          sub={s.peak ? `${Math.round(s.peak.pct ?? 0)}% · ${fmtWhen(s.peak.t)}` : 'สถานีนี้ไม่มีค่าคาดการณ์'}
          tone={s.peak?.status === 'overflow' ? 'red' : undefined}
        />
        <Stat
          label="คำนวณจากน้ำที่วัดได้ต้นทาง"
          value={s.lead_h != null ? inText(s.lead_h) : '–'}
          sub={s.inputs?.length ? `ต้นทาง ${s.inputs.map((i) => `${i.code} (${inText(i.lag_h)})`).join(', ')}` : 'สถานีต้นน้ำ: แสดงค่าที่วัดได้เท่านั้น'}
        />
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="mt-4 w-full h-auto select-none" onMouseMove={onMove} onMouseLeave={() => setHover(null)} role="img" aria-label={`กราฟปริมาณน้ำไหลผ่าน ${s.code} ที่วัดได้และคาดการณ์`}>
        <rect x={chart.x(chart.now)} y={PAD.t} width={Math.max(0, W - PAD.r - chart.x(chart.now))} height={H - PAD.t - PAD.b} className="fill-slate-50" />
        {chart.ticks.map((v) => (
          <g key={v}>
            <line x1={PAD.l} x2={W - PAD.r} y1={chart.y(v)} y2={chart.y(v)} {...GRID} />
            <text x={PAD.l - 8} y={chart.y(v) + 3.5} textAnchor="end" fontSize="10" fill="#64748b">{fmtNum(v)}</text>
          </g>
        ))}
        {chart.days.map((t) => (
          <g key={t}>
            <line x1={chart.x(t)} x2={chart.x(t)} y1={PAD.t} y2={H - PAD.b} {...GRID} />
            <text x={chart.x(t)} y={H - 8} textAnchor="middle" fontSize="10" fill="#64748b">{fmtDay(t * 1000)}</text>
          </g>
        ))}
        {s.qmax && (
          <g>
            <line x1={PAD.l} x2={W - PAD.r} y1={chart.y(s.qmax)} y2={chart.y(s.qmax)} stroke={CAP} strokeWidth="1.5" strokeDasharray="6 4" />
            <text x={W - PAD.r - 4} y={chart.y(s.qmax) - 4} textAnchor="end" fontSize="10" fill={CAP}>ความจุ {fmtNum(Math.round(s.qmax))}</text>
            <line x1={PAD.l} x2={W - PAD.r} y1={chart.y(s.qmax * 0.7)} y2={chart.y(s.qmax * 0.7)} stroke={HIGH} strokeWidth="1" strokeDasharray="2 4" />
            <text x={PAD.l + 4} y={chart.y(s.qmax * 0.7) - 4} fontSize="10" fill={HIGH}>น้ำมาก 70%</text>
          </g>
        )}
        <path d={chart.path(chart.obs)} fill="none" stroke={OBS} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
        {chart.ten.length > 1 && <path d={chart.path(chart.ten)} fill="none" stroke={TEN} strokeWidth="1.5" strokeLinejoin="round" />}
        {chart.measured.length > 0 && (
          <path d={chart.path([chart.obs[chart.obs.length - 1], ...chart.measured])} fill="none" stroke={OBS} strokeWidth="2" strokeDasharray="5 4" strokeLinejoin="round" strokeLinecap="round" />
        )}
        {chart.assumed.length > 1 && <path d={chart.path(chart.assumed)} fill="none" stroke={LATE} strokeWidth="2" strokeDasharray="2 4" strokeLinecap="round" />}
        <line x1={chart.x(chart.now)} x2={chart.x(chart.now)} y1={PAD.t} y2={H - PAD.b} stroke="#94a3b8" strokeWidth="1" />
        <text x={chart.x(chart.now) + 4} y={PAD.t + 10} fontSize="10" fill="#64748b">ตอนนี้</text>
        {hover && (
          <g>
            <line x1={chart.x(hover.t)} x2={chart.x(hover.t)} y1={PAD.t} y2={H - PAD.b} stroke="#94a3b8" strokeWidth="1" strokeDasharray="3 3" />
            <circle cx={chart.x(hover.t)} cy={chart.y(hover.v)} r="4" fill={OBS} stroke="#fff" strokeWidth="2" />
          </g>
        )}
      </svg>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
        {[
          { label: 'กรมชลฯ วัดได้ 72 ชม. (รายชั่วโมง)', color: OBS },
          ...(chart.ten.length ? [{ label: 'ประมาณทุก 10 นาที จากระดับน้ำ สสน.', color: TEN }] : []),
          { label: 'คาดการณ์จากน้ำต้นทางที่วัดได้', color: OBS, dash: '5 4' },
          { label: 'ต่อจากนั้น สมมติว่าน้ำต้นทางคงที่', color: LATE, dash: '2 4' },
          { label: 'ความจุลำน้ำ', color: CAP, dash: '6 4' },
        ].map((it) => (
          <li key={it.label} className="inline-flex items-center gap-1.5">
            <svg width="22" height="8" aria-hidden="true">
              <line x1="1" x2="21" y1="4" y2="4" stroke={it.color} strokeWidth="2" strokeDasharray={it.dash || undefined} />
            </svg>
            {it.label}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Stat({ label, value, sub, tone }) {
  return (
    <div className={`rounded-lg border px-3 py-2.5 ${tone === 'red' ? 'border-red-200 bg-red-50' : 'border-slate-200 bg-slate-50'}`}>
      <p className="text-xs text-slate-600 truncate">{label}</p>
      <p className={`text-lg font-semibold tabular-nums leading-7 ${tone === 'red' ? 'text-red-700' : 'text-slate-900'}`}>{value}</p>
      {sub && <p className="text-xs text-slate-500 truncate" title={sub}>{sub}</p>}
    </div>
  );
}

export default function NorthFlowSection({ isActive }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [code, setCode] = useState('C.2');
  const [allAlerts, setAllAlerts] = useState(false);
  const [impact, setImpact] = useState(null);
  // Simple view for anyone who opens the tab; every table, chart and the map in the detail view
  const [view, setView] = useState('simple');
  const [scrollTo, setScrollTo] = useState(null);

  const loadImpact = useCallback(
    () =>
      fetchNorthImpact()
        .then(setImpact)
        .catch(() => {}),
    [],
  );

  const load = useCallback(() => {
    setRefreshing(true);
    return fetchWaterNorth()
      .then((d) => {
        setData(d);
        setError(false);
      })
      .catch(() => setError(true))
      .finally(() => setRefreshing(false));
  }, []);

  useEffect(() => {
    if (!isActive) return;
    load();
    loadImpact();
    const id = setInterval(() => {
      load();
      loadImpact();
    }, POLL_MS);
    return () => clearInterval(id);
  }, [isActive, load, loadImpact]);

  const by = useMemo(() => Object.fromEntries((data?.stations || []).map((s) => [s.code, s])), [data]);
  const dams = useMemo(() => Object.fromEntries((data?.dams || []).map((d) => [d.name, d])), [data]);
  const texts = useMemo(() => Object.fromEntries((impact?.report?.points || []).map((p) => [p.code, p.text])), [impact]);

  // A link in the simple view opens the detail view at the card it names (a stop's chart, every road)
  useEffect(() => {
    if (view !== 'detail' || !scrollTo) return;
    setScrollTo(null);
    setTimeout(() => document.getElementById(scrollTo)?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50);
  }, [view, scrollTo]);
  const openDetail = (id) => {
    setView('detail');
    setScrollTo(id);
  };

  if (error && !data) return <ErrorState message="เชื่อมต่อข้อมูลกรมชลประทานผ่าน thaiwater.net ไม่สำเร็จ" onRetry={load} retrying={refreshing} />;
  if (!data) {
    return (
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[0, 1, 2, 3].map((i) => (
          <Card key={i} as="div" className="p-4">
            <Skeleton className="h-7 w-24" />
            <Skeleton className="h-3 w-32 mt-2" />
          </Card>
        ))}
      </div>
    );
  }

  const c2 = by['C.2'];
  const c13 = by['C.13'];
  const c35 = by['C.35'];
  const bkk = data.bangkok;
  const alerts = allAlerts ? data.alerts : data.alerts.slice(0, 6);
  const selected = by[code];
  const peakSub = (s) => {
    const n = nowOf(s);
    if (s?.peak && s.peak.q > (n.q || 0) * 1.03) return `คาดสูงสุด ${fmtQ(s.peak.q)} ใน ${inText(s.peak.in_h)}`;
    return n.pct != null ? `เต็ม ${Math.round(n.pct)}% · ${fullness(n.pct)}` : '';
  };
  const tone = (s) => (s?.status === 'overflow' || s?.peak?.status === 'overflow' ? 'red' : s?.status === 'high' || s?.peak?.status === 'high' ? 'yellow' : undefined);

  return (
    <div className="flex flex-col gap-4">
      <div id="north-view" className="flex flex-wrap items-center gap-2 scroll-mt-4">
        <Segmented label="มุมมองน้ำเหนือ" value={view} onChange={setView} options={[['simple', 'สรุปง่าย'], ['detail', 'ข้อมูลละเอียด']]} />
        <span className="text-xs text-slate-500">อัปเดตเองทุก 10 นาที</span>
      </div>
      {data.stale && (
        <p role="status" className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          รีเฟรชล่าสุดไม่สำเร็จ แสดงข้อมูลเมื่อ {fmtDateTime(data.updated_at)}
        </p>
      )}

      {view === 'simple' ? (
        <>
          <NorthRouteView isActive={isActive} onDetail={() => openDetail('north-view')} />
        </>
      ) : (
        <>
          <HowToRead eta={c35?.from_c2_h ? inText(c35.from_c2_h) : null} />

          <StatusBanner tone={data.headline.tone} label={data.headline.label}>
            {data.headline.text}
          </StatusBanner>

          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <StatTile label="นครสวรรค์ C.2 (ลบ.ม./วิ)" value={fmtQ(nowOf(c2).q)} sub={peakSub(c2)} tone={tone(c2)} />
            <StatTile label="ท้ายเขื่อนเจ้าพระยา C.13 (ลบ.ม./วิ)" value={fmtQ(nowOf(c13).q)} sub={peakSub(c13)} tone={tone(c13)} />
            <StatTile label="อยุธยา C.35 (ลบ.ม./วิ)" value={fmtQ(nowOf(c35).q)} sub={peakSub(c35)} tone={tone(c35)} />
            <StatTile
              label="นนทบุรี-กทม. สสน. คาดสูงสุด 7 วัน (ม.รทก.)"
              value={bkk ? bkk.peak_msl.toFixed(2) : '–'}
              sub={bkk ? `สูงสุดราว ${fmtDay(bkk.peak_t * 1000)} · ตลิ่ง ${bkk.bank?.toFixed(2) ?? '–'} ม.รทก.` : 'ไม่มีค่าคาดการณ์ สสน.'}
              tone={bkk && bkk.bank != null && bkk.peak_msl >= bkk.bank ? 'red' : undefined}
            />
          </div>

          <TenMinuteTable stations={data.stations} texts={texts} code={code} onSelect={setCode} />

          {data.alerts.length > 0 && (
            <Card className="p-5" aria-labelledby="north-alerts-title">
              <SectionHeader id="north-alerts-title" title="คำเตือนน้ำเหนือ" description="เรียงจากต้นน้ำลงมา · ล้นตลิ่ง/คาดว่าจะเกินความจุลำน้ำก่อน แล้วจึงน้ำมาก" />
              <ul className="mt-3 divide-y divide-slate-100">
                {alerts.map((a, i) => (
                  <li key={`${a.code}-${i}`} className="py-2 flex items-start gap-2 text-sm">
                    <Badge tone={a.tone} dot className="mt-0.5">{a.tone === 'red' ? 'เตือนภัย' : 'เฝ้าระวัง'}</Badge>
                    <span className="text-slate-800 leading-6">{a.text}</span>
                  </li>
                ))}
              </ul>
              {data.alerts.length > 6 && (
                <Button size="sm" variant="ghost" className="mt-2" onClick={() => setAllAlerts((v) => !v)}>
                  {allAlerts ? 'แสดงน้อยลง' : `ดูทั้งหมด ${data.alerts.length} รายการ`}
                </Button>
              )}
            </Card>
          )}

          <NorthFlowMap data={data} code={code} onSelect={setCode} isActive={isActive} texts={texts} />

          <div className="grid grid-cols-1 xl:grid-cols-5 gap-4">
            <Card className="p-5 xl:col-span-2" aria-labelledby="north-trib-title">
              <SectionHeader id="north-trib-title" title="ต้นน้ำภาคเหนือ" description="น้ำไหลผ่านแต่ละจุดกี่ ลบ.ม. ทุกวินาที และเต็มลำน้ำกี่เปอร์เซ็นต์ · แตะเพื่อดูกราฟ" />
              <div className="mt-3 flex flex-col gap-4">
                {TRIBUTARIES.map((g) => (
                  <div key={g.river}>
                    <h4 className="text-xs font-semibold text-slate-600 mb-1.5">{g.title}</h4>
                    <div className="flex flex-col gap-1.5">
                      {g.dams.filter((n) => dams[n]).map((n) => (
                        <Dam key={n} d={dams[n]} />
                      ))}
                      {g.codes.filter((c) => by[c]).map((c) => (
                        <GaugeRow key={c} s={by[c]} selected={code === c} onSelect={setCode} text={texts[c]} />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </Card>

            <Card className="p-5 xl:col-span-3" aria-labelledby="north-main-title">
              <SectionHeader id="north-main-title" title="แม่น้ำเจ้าพระยา นครสวรรค์ → อยุธยา" description="ปริมาณน้ำตอนนี้ ค่าสูงสุดที่คาดใน 4 วัน และเวลาเดินทางของน้ำระหว่างสถานี" />
              <div className="mt-3">
                <Connector lag={c2?.inputs?.[0]?.lag_h} from="ปิง P.17 + น่าน N.67" />
                {MAIN.map((m, i) => {
                  const s = by[m.code];
                  const j = m.joins && by[m.joins];
                  return (
                    <div key={m.code}>
                      {i > 0 && <Connector lag={s?.inputs?.[0]?.lag_h} joins={j?.q != null ? { river: j.code === 'S.26' ? 'ป่าสัก S.26' : 'สะแกกรัง Ct.19', q: j.q } : null} />}
                      <MainNode s={s} title={m.title} selected={code === m.code} onSelect={setCode} text={texts[m.code]} />
                      {s?.from_c2_h > 0 && <p className="pl-6 pt-1 text-xs text-slate-500">น้ำที่ผ่านนครสวรรค์ตอนนี้ถึงที่นี่ใน {inText(s.from_c2_h)}</p>}
                    </div>
                  );
                })}
                <div className="flex items-center gap-3 pl-6 py-1 text-xs text-slate-500">
                  <span className="w-px h-6 bg-slate-300" aria-hidden="true" />
                  <span>↓ กรุงเทพฯ และปริมณฑล</span>
                </div>
                <div className="rounded-xl border border-slate-200 p-3 text-xs text-slate-600">
                  <p className="text-sm font-semibold text-slate-900">นนทบุรี-กรุงเทพฯ (สะพานนวลฉวี)</p>
                  {bkk ? (
                    <p className="mt-1 tabular-nums">
                      ตอนนี้ {bkk.now_msl != null ? `${bkk.now_msl.toFixed(2)} ม.รทก.` : '–'} · สสน. คาดสูงสุด {bkk.peak_msl.toFixed(2)} ม.รทก. ราว {fmtDay(bkk.peak_t * 1000)} · ตลิ่ง {bkk.bank?.toFixed(2) ?? '–'} ม.รทก.
                      {bkk.over_bank_t && <span className="text-red-700 font-medium"> · คาดสูงกว่าตลิ่งตั้งแต่ {fmtDay(bkk.over_bank_t * 1000)}</span>}
                    </p>
                  ) : (
                    <p className="mt-1">ไม่มีค่าคาดการณ์ สสน. ตอนนี้</p>
                  )}
                  <p className="mt-1 text-slate-500">ช่วงนี้ระดับน้ำขึ้นกับน้ำทะเลหนุนด้วย ดูกราฟรายสถานีในแท็บ “สถานการณ์น้ำ”</p>
                </div>
              </div>
            </Card>
          </div>

          <Card className="p-5" aria-labelledby="north-chart-title">
            <SectionHeader
              id="north-chart-title"
              title={`ปริมาณน้ำไหลผ่าน ${selected ? `${selected.code} ${selected.province}` : ''}`}
              description="หน่วย ลบ.ม./วินาที · เส้นทึบ = วัดได้ 72 ชม. · เส้นประ = คาดการณ์ 4 วัน"
              action={
                <select
                  aria-label="เลือกสถานี"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  className={`h-8 rounded-lg border border-slate-300 bg-white px-2 text-xs text-slate-800 max-w-[260px] ${FOCUS}`}
                >
                  {data.stations.filter((s) => s.history?.length).map((s) => (
                    <option key={s.code} value={s.code}>
                      {s.forecast ? '[คาดการณ์] ' : ''}
                      {s.code} · {s.province} · {s.name}
                    </option>
                  ))}
                </select>
              }
            />
            <div className="mt-4">
              <FlowChart s={selected} dataTime={data.data_time} />
            </div>
            {selected?.code === 'C.13' && <p className="mt-2 text-xs text-slate-500">ท้ายเขื่อนเจ้าพระยา: ปริมาณน้ำขึ้นกับการระบายของกรมชลประทาน ค่าคาดการณ์คือปริมาณที่ผ่านหากเขื่อนระบายแบบเดียวกับ 2 สัปดาห์ที่ผ่านมา</p>}
          </Card>

          <p className="text-xs text-slate-500 leading-5 px-1">
            แหล่งข้อมูล: สถานีวัดน้ำหลักของกรมชลประทาน ผ่านคลังข้อมูลน้ำ สสน. (twa.thaiwater.net) รายชั่วโมง · ปริมาณน้ำทุก 10 นาทีประมาณจากระดับน้ำสถานี สสน. ข้างเคียง · เขื่อนจากคลังข้อมูลน้ำแห่งชาติ สทนช. · คาดการณ์ระดับน้ำ 7 วันของ สสน. ·
            ค่าคาดการณ์ปริมาณน้ำ 4 วันคำนวณในระบบนี้: แต่ละช่วงแม่น้ำส่งการเปลี่ยนแปลงของน้ำต้นทางลงมาตามเวลาเดินทาง ด้วยสัดส่วนที่ปรับจากข้อมูล 14 วันล่าสุด (ทดสอบย้อนหลัง ก.ย. 2569 คลาดเคลื่อนราว 4-6% ที่ 24 ชม. และ 8-12% ที่ 48 ชม.)
            ไม่รวมฝนที่จะตกใหม่ และการเปิด-ปิดประตูระบายน้ำ ใช้ประกอบการเฝ้าระวังเท่านั้น ติดตามประกาศทางการของกรมชลประทานและ ปภ. · ข้อมูลน้ำ ณ {fmtDateTime(data.data_time)}
          </p>
        </>
      )}
    </div>
  );
}
