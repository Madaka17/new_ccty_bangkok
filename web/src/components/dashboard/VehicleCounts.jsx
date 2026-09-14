import { useEffect, useMemo, useState } from 'react';
import { CarIcon, BikeIcon, TruckIcon, CameraIcon, CheckIcon, CloseIcon } from '../Icons.jsx';
import { fetchAIHistory, fetchCountCameras, fetchSurveyRanking, setCountCameras } from '../../lib/api.js';
import { Card, SectionHeader, Badge, Button, Segmented, Skeleton, EmptyState, ErrorState, Truncate, FOCUS } from './ui.jsx';
import { AI_LEVEL, agoText, fmtDay, fmtNum, pad2 } from './format.js';

const RANGES = [
  ['24h', '24 ชม.'],
  ['7d', '7 วัน'],
  ['30d', '30 วัน'],
];
const SORTS = [
  ['busiest', 'รถผ่านมากสุด'],
  ['jammed', 'รถติดสุด'],
  ['quiet', 'รถน้อยสุด'],
];
const ACCENT = '#2563eb';
const ACCENT_SOFT = '#bfdbfe';

const bucketLabel = (bucket, key) => (bucket === 'hour' ? `${pad2(new Date(key).getHours())}:00` : fmtDay(key));
const bucketTitle = (bucket, key) => {
  if (bucket === 'day') return fmtDay(key);
  const h = new Date(key).getHours();
  return `${pad2(h)}:00–${pad2((h + 1) % 24)}:00 น.`;
};
const jamScore = (c) => (c.level === 'heavy' ? 2 : c.level === 'moderate' ? 1 : 0) * 1000 + (100 - (c.moving_pct ?? 100)) * 5 + (c.visible || 0);

// Bar chart of vehicle counts per hour / day. Clicking a day bar drills into that day.
function CountBars({ bucket, keys, series, onPickDay }) {
  const [hover, setHover] = useState(null);
  const vals = keys.map((k) => series[k]?.total || 0);
  const max = Math.max(1, ...vals);
  const W = 560;
  const H = 110;
  const pad = { l: 4, r: 4, t: 16, b: 20 };
  const gap = 3;
  const bw = (W - pad.l - pad.r) / Math.max(1, keys.length);
  const peakIdx = vals.indexOf(Math.max(...vals));
  const shownIdx = hover ?? (vals[peakIdx] > 0 ? peakIdx : null);
  const labelEvery = bucket === 'hour' ? 6 : keys.length > 10 ? 5 : 1;
  const clickable = bucket === 'day' && onPickDay;
  const s = shownIdx != null ? series[keys[shownIdx]] : null;

  return (
    <div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className={`w-full h-auto select-none ${clickable ? 'cursor-pointer' : ''}`}
        onMouseLeave={() => setHover(null)}
        role="img"
        aria-label="จำนวนรถที่ผ่านกล้อง"
      >
        <line x1={pad.l} x2={W - pad.r} y1={H - pad.b} y2={H - pad.b} stroke="#e2e8f0" strokeWidth="1" />
        {keys.map((k, i) => {
          const v = vals[i];
          const h = v ? Math.max(3, ((H - pad.t - pad.b) * v) / max) : 0;
          const x = pad.l + i * bw + gap / 2;
          const y = H - pad.b - h;
          const on = shownIdx === i;
          return (
            <g key={k} onMouseEnter={() => setHover(i)} onClick={() => clickable && v > 0 && onPickDay(k)}>
              <rect x={x} y={pad.t} width={Math.max(2, bw - gap)} height={H - pad.t - pad.b} fill="transparent" />
              {v > 0 && <rect x={x} y={y} width={Math.max(2, bw - gap)} height={h} rx="2" fill={on ? ACCENT : ACCENT_SOFT} className="transition-colors duration-150" />}
              {i % labelEvery === 0 && (
                <text x={x + (bw - gap) / 2} y={H - 5} textAnchor="middle" fontSize="10" fill="#64748b">
                  {bucketLabel(bucket, k)}
                </text>
              )}
              {on && v > 0 && (
                <text x={x + (bw - gap) / 2} y={y - 4} textAnchor="middle" fontSize="10" fill="#0f172a" fontWeight="600">
                  {v}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      <div className="mt-1 min-h-5 text-xs text-slate-600 flex flex-wrap items-center gap-x-3 gap-y-1">
        {s ? (
          <>
            <span className="font-medium text-slate-900">{bucketTitle(bucket, keys[shownIdx])}</span>
            <span className="inline-flex items-center gap-1"><CarIcon className="w-3.5 h-3.5" /> {fmtNum(s.cars)}</span>
            <span className="inline-flex items-center gap-1"><BikeIcon className="w-3.5 h-3.5" /> {fmtNum(s.motorcycles)}</span>
            <span className="inline-flex items-center gap-1"><TruckIcon className="w-3.5 h-3.5" /> {fmtNum(s.trucks)}</span>
          </>
        ) : (
          <span className="text-slate-400">{clickable ? 'กดแท่งกราฟเพื่อดูรายชั่วโมงของวันนั้น' : ''}</span>
        )}
      </div>
    </div>
  );
}

function CameraCard({ cam, live, bucket, keys, onPickDay }) {
  const status = live?.active
    ? { text: `กำลังนับ · ${live.fps} FPS`, tone: 'green', dot: true }
    : live
    ? { text: live.error || 'กำลังเชื่อมต่อ', tone: 'yellow' }
    : null;
  return (
    <Card as="article" className="p-4 flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <h4 className="text-sm font-medium text-slate-900 leading-5 line-clamp-2" title={cam.title || cam.camid}>
          {cam.title || cam.camid}
        </h4>
        {status && (
          <Badge tone={status.tone} dot={status.dot} className="shrink-0">
            {status.text}
          </Badge>
        )}
      </div>
      <div className="flex items-baseline gap-2">
        <span className="text-2xl font-semibold text-slate-900 leading-8 tabular-nums">{fmtNum(cam.total)}</span>
        <span className="text-xs text-slate-600">คันที่ผ่าน{cam.estimated ? ' (ประมาณการ)' : ''}</span>
      </div>
      <dl className="grid grid-cols-3 gap-2 text-xs">
        {[
          ['รถยนต์', cam.cars, CarIcon],
          ['มอเตอร์ไซค์', cam.motorcycles, BikeIcon],
          ['รถบรรทุก', cam.trucks, TruckIcon],
        ].map(([label, v, Icon]) => (
          <div key={label} className="rounded-lg border border-slate-200 px-2.5 py-2 min-w-0">
            <dt className="flex items-center gap-1 text-slate-500 truncate">
              <Icon className="w-3.5 h-3.5 shrink-0" />
              {label}
            </dt>
            <dd className="text-sm font-semibold text-slate-900 tabular-nums mt-0.5">{fmtNum(v)}</dd>
          </div>
        ))}
      </dl>
      <div className="pt-3 border-t border-slate-100">
        <CountBars bucket={bucket} keys={keys} series={cam.series} onPickDay={onPickDay} />
      </div>
    </Card>
  );
}

function CameraPicker({ cameras, selected, max, saving, onChange, onClose }) {
  const [q, setQ] = useState('');
  const list = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const src = cameras.filter((c) => c.hls_url || c.vdourl);
    const hit = needle ? src.filter((c) => (c.short_title || c.title || '').toLowerCase().includes(needle)) : src;
    return [...hit.filter((c) => selected.includes(c.camid)), ...hit.filter((c) => !selected.includes(c.camid))].slice(0, 60);
  }, [cameras, q, selected]);

  const toggle = (id) => {
    if (selected.includes(id)) onChange(selected.filter((x) => x !== id));
    else if (selected.length < max) onChange([...selected, id]);
  };

  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
      <div className="flex items-center gap-2">
        <label htmlFor="cam-picker-q" className="sr-only">ค้นหากล้อง</label>
        <input
          id="cam-picker-q"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="ค้นหาชื่อกล้องหรือถนน"
          className={`flex-1 min-w-0 h-9 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 placeholder:text-slate-400 ${FOCUS}`}
        />
        <span className="text-xs text-slate-600 tabular-nums shrink-0" aria-live="polite">
          เลือกแล้ว {selected.length}/{max}
          {saving ? ' · กำลังบันทึก' : ''}
        </span>
        <button type="button" onClick={onClose} aria-label="ปิดตัวเลือกกล้อง" className={`cursor-pointer w-8 h-8 rounded-lg hover:bg-slate-200 text-slate-600 flex items-center justify-center ${FOCUS}`}>
          <CloseIcon className="w-4 h-4" />
        </button>
      </div>
      <ul className="mt-3 max-h-64 overflow-y-auto rounded-lg border border-slate-200 bg-white divide-y divide-slate-100" aria-label="รายชื่อกล้อง">
        {list.map((c) => {
          const on = selected.includes(c.camid);
          const full = !on && selected.length >= max;
          return (
            <li key={c.camid}>
              <button
                type="button"
                onClick={() => toggle(c.camid)}
                disabled={full || saving}
                aria-pressed={on}
                className={`w-full text-left px-3 py-2 flex items-center gap-3 text-sm transition-colors ${FOCUS} ${
                  full ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer hover:bg-slate-50'
                }`}
              >
                <span className={`w-4 h-4 rounded border flex items-center justify-center shrink-0 ${on ? 'bg-blue-600 border-blue-600 text-white' : 'border-slate-300 bg-white'}`}>
                  {on && <CheckIcon className="w-3 h-3" />}
                </span>
                <Truncate text={c.short_title || c.title} className="flex-1 text-slate-900" />
                <span className="text-xs text-slate-500 shrink-0">{c.province}</span>
              </button>
            </li>
          );
        })}
        {!list.length && <li className="text-sm text-slate-500 py-4 text-center">ไม่พบกล้องที่ตรงกับคำค้น</li>}
      </ul>
    </div>
  );
}

function CameraRanking({ ranking, history, bucket, keys }) {
  const [sort, setSort] = useState('busiest');
  const [showAll, setShowAll] = useState(false);
  const [open, setOpen] = useState(null);
  const seriesById = useMemo(() => Object.fromEntries((history?.cameras || []).map((c) => [c.camid, c])), [history]);

  const rows = useMemo(() => {
    const list = (ranking?.cameras || []).filter((c) => c.ts);
    if (sort === 'busiest') list.sort((a, b) => b.rate_per_min - a.rate_per_min);
    else if (sort === 'quiet') list.sort((a, b) => a.rate_per_min - b.rate_per_min);
    else list.sort((a, b) => jamScore(b) - jamScore(a));
    return list;
  }, [ranking, sort]);

  if (!ranking)
    return (
      <div className="space-y-2">
        {[1, 2, 3].map((n) => (
          <Skeleton key={n} className="h-12" />
        ))}
      </div>
    );
  const shown = showAll ? rows : rows.slice(0, 10);
  const cycleMin = ranking.cycle_seconds ? Math.max(1, Math.round(ranking.cycle_seconds / 60)) : null;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Segmented options={SORTS} value={sort} onChange={setSort} label="เรียงอันดับกล้อง" />
        <span className="text-xs text-slate-500 tabular-nums">
          วัดแล้ว {rows.length}/{ranking.total_cameras} กล้อง{cycleMin ? ` · วนรอบทุก ~${cycleMin} นาที` : ''}
        </span>
      </div>
      {rows.length === 0 ? (
        <EmptyState title="ยังไม่มีผลการสุ่มวัด" description="ระบบจะเริ่มวัดอัตโนมัติเมื่อ server ทำงาน" />
      ) : (
        <ol className="rounded-lg border border-slate-200 divide-y divide-slate-100 overflow-hidden">
          {shown.map((c, i) => {
            const lv = AI_LEVEL[c.level] || AI_LEVEL.free;
            const hist = seriesById[c.camid];
            const isOpen = open === c.camid;
            return (
              <li key={c.camid}>
                <button
                  type="button"
                  onClick={() => setOpen(isOpen ? null : c.camid)}
                  aria-expanded={isOpen}
                  className={`cursor-pointer w-full text-left px-3 py-2.5 hover:bg-slate-50 transition-colors flex items-center gap-3 ${FOCUS}`}
                >
                  <span className="w-6 text-center text-xs text-slate-500 tabular-nums shrink-0">{i + 1}</span>
                  <div className="flex-1 min-w-0">
                    <Truncate text={c.title} className="text-sm font-medium text-slate-900" />
                    <span className="block text-xs text-slate-500">
                      {c.source === 'count' ? 'นับต่อเนื่อง' : `สุ่ม ${Math.round(c.seconds || ranking.sample_seconds)} วิ`} · {agoText(c.ts)}
                      {c.error ? <span className="text-red-700"> · {c.error}</span> : null}
                    </span>
                  </div>
                  <div className="text-right shrink-0 tabular-nums">
                    <span className="block text-sm font-semibold text-slate-900 leading-5">
                      {c.rate_per_min} <span className="text-xs font-normal text-slate-500">คัน/นาที</span>
                    </span>
                    <span className="block text-xs text-slate-500">ในภาพ {Math.round(c.visible)} · วิ่ง {c.moving_pct}%</span>
                  </div>
                  <Badge tone={lv.key} className="shrink-0">
                    {lv.label}
                  </Badge>
                </button>
                {isOpen && (
                  <div className="px-3 pb-3 pt-2 bg-slate-50 border-t border-slate-100">
                    {hist ? (
                      <>
                        <p className="text-xs text-slate-600 mb-2">
                          {hist.estimated ? 'ประมาณการจากการสุ่มภาพ · ' : ''}
                          รถยนต์ <b className="text-slate-900">{fmtNum(hist.cars)}</b> · มอเตอร์ไซค์ <b className="text-slate-900">{fmtNum(hist.motorcycles)}</b> · รถบรรทุก <b className="text-slate-900">{fmtNum(hist.trucks)}</b>
                        </p>
                        <CountBars bucket={bucket} keys={keys} series={hist.series} />
                      </>
                    ) : (
                      <p className="text-xs text-slate-500 py-1">ยังไม่มีสถิติย้อนหลังของกล้องนี้ในช่วงที่เลือก</p>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ol>
      )}
      {rows.length > 10 && (
        <Button variant="ghost" size="sm" className="self-center" onClick={() => setShowAll((v) => !v)}>
          {showAll ? 'แสดง 10 อันดับแรก' : `ดูทั้งหมด ${rows.length} กล้อง`}
        </Button>
      )}
    </div>
  );
}

export default function VehicleCounts({ cameras }) {
  const [range, setRange] = useState('24h');
  const [date, setDate] = useState(null);
  const [history, setHistory] = useState(null);
  const [histError, setHistError] = useState(false);
  const [counting, setCounting] = useState(null);
  const [ranking, setRanking] = useState(null);
  const [picking, setPicking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let alive = true;
    const tick = () => {
      fetchAIHistory(date ? { date } : { range })
        .then((h) => {
          if (!alive) return;
          setHistory(h);
          setHistError(false);
        })
        .catch(() => alive && setHistError(true));
      fetchCountCameras().then((c) => alive && setCounting(c)).catch(() => {});
      fetchSurveyRanking().then((r) => alive && setRanking(r)).catch(() => {});
    };
    tick();
    const id = setInterval(tick, 30000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [range, date, reloadKey]);

  const selected = counting?.cameras.map((c) => c.camid) || [];
  const liveById = Object.fromEntries((counting?.cameras || []).map((c) => [c.camid, c]));

  const changeSelection = (ids) => {
    setSaving(true);
    setSaveError(false);
    setCountCameras(ids)
      .then((c) => setCounting(c))
      .catch(() => setSaveError(true))
      .finally(() => setSaving(false));
  };

  const cards = useMemo(() => {
    const list = (history?.cameras || []).filter((c) => !c.estimated || selected.includes(c.camid));
    const seen = new Set(list.map((c) => c.camid));
    for (const c of counting?.cameras || []) {
      if (!seen.has(c.camid)) list.push({ camid: c.camid, title: c.title, cars: 0, motorcycles: 0, trucks: 0, total: 0, series: {} });
    }
    return list;
  }, [history, counting, selected]);

  const changeRange = (k) => {
    setRange(k);
    setHistory(null);
  };
  const pickDay = (key) => {
    setDate(key);
    setHistory(null);
  };

  return (
    <Card aria-labelledby="counts-title" className="p-5 flex flex-col gap-4">
      <SectionHeader
        id="counts-title"
        title="จำนวนรถที่ผ่านกล้อง AI"
        description="นับแยกประเภทจากกล้องที่เลือกให้นับต่อเนื่อง บันทึกรายชั่วโมง"
        action={
          <Button size="sm" onClick={() => setPicking((v) => !v)} aria-expanded={picking} aria-controls="cam-picker">
            <CameraIcon className="w-3.5 h-3.5" />
            กล้องที่นับ {counting ? `${selected.length}/${counting.max_cameras}` : ''}
          </Button>
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        {date ? (
          <Button size="sm" variant="ghost" onClick={() => { setDate(null); setHistory(null); }}>
            ← กลับ · รายชั่วโมง {fmtDay(date)}
          </Button>
        ) : (
          <Segmented options={RANGES} value={range} onChange={changeRange} label="ช่วงเวลา" />
        )}
      </div>

      {picking && counting && (
        <div id="cam-picker">
          {saveError && <div className="mb-2"><ErrorState message="บันทึกรายการกล้องไม่สำเร็จ" /></div>}
          <CameraPicker cameras={cameras} selected={selected} max={counting.max_cameras} saving={saving} onChange={changeSelection} onClose={() => setPicking(false)} />
        </div>
      )}

      {histError && !history ? (
        <ErrorState message="โหลดสถิติการนับรถไม่สำเร็จ" onRetry={() => setReloadKey((k) => k + 1)} />
      ) : !history ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[1, 2].map((n) => (
            <Skeleton key={n} className="h-64" />
          ))}
        </div>
      ) : !cards.length ? (
        <EmptyState
          title="ยังไม่มีกล้องที่นับต่อเนื่อง"
          description="เลือกกล้องเพื่อเริ่มนับรถอัตโนมัติเบื้องหลัง"
          action={
            <Button size="sm" variant="primary" onClick={() => setPicking(true)}>
              เลือกกล้อง
            </Button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {cards.map((c) => (
            <CameraCard key={c.camid} cam={c} live={liveById[c.camid]} bucket={history.bucket} keys={history.keys} onPickDay={history.bucket === 'day' ? pickDay : null} />
          ))}
        </div>
      )}

      <div className="border-t border-slate-200 pt-4">
        <SectionHeader title="อันดับกล้องทั่วกรุงเทพฯ" description="สุ่มวิเคราะห์ภาพจากกล้องทุกตัว ตัวละ 15 วินาที หมุนเวียนต่อเนื่อง · กดเพื่อดูสถิติย้อนหลัง" className="mb-3" />
        <CameraRanking ranking={ranking} history={history} bucket={history?.bucket || 'hour'} keys={history?.keys || []} />
      </div>
    </Card>
  );
}
