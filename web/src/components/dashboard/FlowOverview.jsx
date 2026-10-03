import { useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { Card, Badge, Skeleton, ErrorState, FOCUS } from './ui.jsx';
import { STATUS, flowLevel, fmtNum, fmtTime } from './format.js';
import BmaSiteNotice, { bmaSiteDown } from '../bma/BmaSiteNotice.jsx';
import { fetchTrafficNear } from '../../lib/api.js';
import { roughWarning } from '../../lib/geo.js';

// Horizontal HUD meter: gradient track (red -> amber -> green), threshold ticks at the
// flowLevel cut-offs, glowing marker at the current value. Replaces the old ring gauge.
// Every position is a percentage of the track, so the meter follows the card width when the window changes.
const ZONES = [
  { from: 0, to: 45, label: 'ติดขัด', key: 'red' },
  { from: 45, to: 75, label: 'ชะลอตัว', key: 'yellow' },
  { from: 75, to: 100, label: 'คล่องตัว', key: 'green' },
];

function Meter({ value, colorHex }) {
  const v = Math.min(100, Math.max(0, value ?? 0));
  return (
    <div className="w-full" role="img" aria-label={`คะแนนรถคล่อง ${value ?? '-'} จาก 100`}>
      <div className="relative h-4 rounded-full bg-slate-100">
        {/* muted zone gradient under everything */}
        <div
          className="absolute inset-0 rounded-full opacity-40"
          style={{ background: 'linear-gradient(90deg, #dc2626 0%, #dc2626 45%, #d97706 45%, #d97706 75%, #059669 75%, #059669 100%)' }}
        />
        {/* lit portion up to the value. Its own overflow keeps the sheen inside it; the glow is its own shadow and
            still shows. Both ends are percentages ('0%' too: mixed units would make framer-motion fix them in px). */}
        <motion.div
          className="absolute inset-y-0 left-0 rounded-full overflow-hidden"
          initial={{ width: '0%' }}
          animate={{ width: `${v}%` }}
          transition={{ type: 'spring', stiffness: 60, damping: 18 }}
          style={{ background: `linear-gradient(90deg, ${colorHex}66, ${colorHex})`, boxShadow: `0 0 14px ${colorHex}80` }}
        >
          <span className="meter-sheen" aria-hidden="true" />
        </motion.div>
        {/* threshold ticks */}
        {[45, 75].map((t) => (
          <span key={t} className="absolute top-[-4px] bottom-[-4px] w-px bg-slate-300" style={{ left: `${t}%` }} aria-hidden="true" />
        ))}
        {/* marker */}
        <motion.div
          className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2"
          initial={{ left: '0%' }}
          animate={{ left: `${v}%` }}
          transition={{ type: 'spring', stiffness: 60, damping: 18 }}
          aria-hidden="true"
        >
          <span className="block w-6 h-6 rounded-full border-2 border-white" style={{ background: colorHex, boxShadow: `0 0 0 3px ${colorHex}33, 0 0 18px ${colorHex}` }} />
        </motion.div>
      </div>
      <div className="relative mt-2 h-4 text-[11px] text-slate-500">
        {ZONES.map((z) => (
          <span
            key={z.key}
            className={`absolute top-0 text-center ${v >= z.from && v < (z.to === 100 ? 101 : z.to) ? `${STATUS[z.key].text} font-medium` : ''}`}
            style={{ left: `${z.from}%`, width: `${z.to - z.from}%` }}
          >
            {z.label}
          </span>
        ))}
      </div>
    </div>
  );
}

function Delta({ history }) {
  // Change vs ~1 hour ago (60 samples x 1 min)
  if (!history) return null;
  // BMA history is one point per hour; Longdo history is one point per minute
  const step = history[history.length - 1]?.hourly ? 1 : 60;
  if (history.length <= step) return null;
  return <DeltaText d={history[history.length - 1].flow - history[history.length - 1 - step].flow} />;
}

function DeltaText({ d }) {
  if (!Number.isFinite(d)) return null;
  if (Math.abs(d) <= 2) return <p className="text-xs text-slate-500">ใกล้เคียงกับ 1 ชม.ก่อน</p>;
  const up = d > 0;
  return (
    <p className={`text-xs font-medium ${up ? 'text-emerald-700' : 'text-red-700'}`}>
      {up ? '▲ รถคล่องขึ้น' : '▼ รถติดขึ้น'}กว่าเมื่อ 1 ชม.ก่อน
    </p>
  );
}

const BANGKOK = '10';
const areaName = (pcode, name) => (pcode === BANGKOK ? `เขต${name}` : `อ.${name}`);
const SELECT = `cursor-pointer rounded-lg border border-slate-300 bg-white text-slate-700 px-2 h-8 text-xs font-medium disabled:opacity-50 disabled:cursor-not-allowed ${FOCUS}`;
const TOP = 8;
const EVENT_TH = { accident: 'อุบัติเหตุ', breakdown: 'รถเสีย', closed: 'ถนนปิด', diversion: 'เบี่ยงจราจร', flood: 'น้ำท่วม' };
const EVENT_TONE = { accident: 'text-red-700', breakdown: 'text-amber-700', closed: 'text-red-700', diversion: 'text-amber-700', flood: 'text-blue-700' };

// Worst first: lowest score, then the most km of red; areas with too little road are left out
function worstFirst(list) {
  return list.filter((a) => a.flow != null).sort((a, b) => a.flow - b.flow || b.red_km - a.red_km);
}

// Ranking of the provinces (none picked) or of the districts of the picked province; a tap picks the row
function AreaRanking({ title, rows, onPick, unit = '' }) {
  const [all, setAll] = useState(false);
  const shown = all ? rows : rows.slice(0, TOP);
  return (
    <div className="mt-5 border-t border-slate-200 pt-4">
      <p className="text-[13px] font-semibold text-slate-900 mb-2">{title}</p>
      <ul className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-1">
        {shown.map((r) => {
          const st = STATUS[flowLevel(r.flow).key];
          return (
            <li key={r.key}>
              <button type="button" onClick={() => onPick?.(r.key)} disabled={!onPick}
                className={`w-full grid grid-cols-[minmax(0,9rem)_1fr_2.5rem_5.5rem] items-center gap-2 rounded-md px-1.5 py-1 text-left text-xs ${onPick ? `hover:bg-slate-50 cursor-pointer ${FOCUS}` : 'cursor-default'}`}>
                <span className="truncate text-slate-800" title={r.label}>{r.label}{unit && r[unit] != null ? <span className="text-slate-500"> · {r[unit]} กม.</span> : null}</span>
                <span className="h-1.5 rounded-full bg-slate-100 overflow-hidden" aria-hidden="true">
                  <span className={`block h-full rounded-full ${st.bar}`} style={{ width: `${r.flow}%` }} />
                </span>
                <b className={`tabular-nums text-right ${st.text}`}>{r.flow}</b>
                <span className="tabular-nums text-right text-slate-500">ติด {fmtNum(r.red_km)} กม.</span>
              </button>
            </li>
          );
        })}
      </ul>
      {rows.length > TOP && (
        <button type="button" onClick={() => setAll((v) => !v)} className={`mt-2 text-xs text-blue-700 cursor-pointer ${FOCUS}`}>
          {all ? 'ย่อ' : `ดูทั้งหมด ${rows.length} แห่ง`}
        </button>
      )}
    </div>
  );
}

export default function FlowOverview({ summary, areas, error, onRetry, retrying }) {
  const [provCode, setProvCode] = useState('');
  const [ampCode, setAmpCode] = useState('');
  // "ใกล้ฉัน": the roads around the visitor (null = off)
  const [near, setNear] = useState(null);
  const [nearBusy, setNearBusy] = useState(false);
  const [nearMsg, setNearMsg] = useState('');
  const provinces = useMemo(() => (areas?.ready ? [...areas.provinces].sort((a, b) => a.province.localeCompare(b.province, 'th')) : []), [areas]);
  const prov = provinces.find((p) => p.code === provCode);
  const amp = prov?.amphoes.find((a) => a.code === ampCode);
  // A picked province or district shows its own score from the map's lines; none picked: the Bangkok summary
  const area = near || amp || prov;
  const pickProvince = (code) => { setProvCode(code); setAmpCode(''); setNear(null); };
  const pickAmphoe = (code) => { setAmpCode(code); setNear(null); };
  const locate = () => {
    if (near) { setNear(null); setNearMsg(''); return; }
    if (!navigator.geolocation) { setNearMsg('เบราว์เซอร์นี้ไม่รองรับตำแหน่ง'); return; }
    setNearBusy(true);
    setNearMsg('');
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude, longitude, accuracy } = pos.coords;
        fetchTrafficNear(latitude, longitude)
          .then((d) => { setNear({ ...d, accuracy }); setProvCode(''); setAmpCode(''); setNearMsg(roughWarning(accuracy)); })
          .catch(() => setNearMsg('ตำแหน่งนี้อยู่นอกประเทศไทย หรือโหลดข้อมูลไม่สำเร็จ'))
          .finally(() => setNearBusy(false));
      },
      () => { setNearBusy(false); setNearMsg('ขอตำแหน่งไม่สำเร็จ (ยังไม่ได้อนุญาตให้เว็บนี้ใช้ตำแหน่ง)'); },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 },
    );
  };
  const nearPlace = near?.province ? ` · ${near.amphoe ? `${near.province === 'กรุงเทพมหานคร' ? 'เขต' : 'อ.'}${near.amphoe} ` : ''}${near.province}` : '';

  const siteDown = !area && summary?.is_bma && bmaSiteDown(summary.site);
  const level = area
    ? (area.flow == null ? { key: 'neutral', label: 'ข้อมูลน้อย', hint: 'ถนนในพื้นที่นี้มีข้อมูลไม่พอ' } : flowLevel(area.flow))
    : siteDown ? { key: 'neutral', label: 'ไม่มีข้อมูลสด', hint: 'รอให้เว็บกล้อง กทม. กลับมา' } : flowLevel(summary?.flow_index);
  const status = STATUS[level.key];
  const flow = area ? area.flow : summary?.flow_index;
  const shown = near ? { updated_at: near.updated_at, online: near.online } : area ? { updated_at: areas.updated_at, online: areas.online } : summary;

  const ranking = near
    ? { title: `ถนนแถวนี้ที่ติดมากสุด (รัศมี ${near.radius_km} กม.)`, unit: 'distance_km',
        rows: near.roads.map((r) => ({ ...r, key: r.name, label: r.name })) }
    : !areas?.ready ? null : prov
    ? (amp ? null : {
        title: `${prov.province}: ${prov.code === BANGKOK ? 'เขต' : 'อำเภอ'}ที่รถติดที่สุดตอนนี้`,
        rows: worstFirst(prov.amphoes).map((a) => ({ ...a, key: a.code, label: areaName(prov.code, a.name) })),
        onPick: pickAmphoe,
      })
    : {
        title: `จังหวัดที่รถติดที่สุดตอนนี้ (ทั้งประเทศ ${areas.national.flow ?? '–'}/100)`,
        rows: worstFirst(provinces).map((p) => ({ ...p, key: p.code, label: p.province })),
        onPick: pickProvince,
      };

  return (
    <Card aria-labelledby="flow-title" className="p-5 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <h2 id="flow-title" className="text-[15px] font-semibold text-slate-900">
            รถติดแค่ไหนตอนนี้
          </h2>
          {/* Where the score comes from: the road-share cards below read the map's line colours instead */}
          {near ? (
            <p className="text-[13px] text-slate-600 mt-0.5">
              รอบตัวคุณ {near.radius_km} กม.{nearPlace} · ถนน {near.road_count} สาย {fmtNum(near.total_km)} กม.
            </p>
          ) : area ? (
            <p className="text-[13px] text-slate-600 mt-0.5">
              {amp ? `${areaName(prov.code, amp.name)} ${prov.province}` : prov.province} · คิดจากสีเส้นจราจรบนถนนสายหลัก {fmtNum(area.total_km)} กม.
            </p>
          ) : summary && (
            <p className="text-[13px] text-slate-600 mt-0.5">
              {summary.is_bma ? `ใช้ข้อมูลจากกล้อง กทม. ${fmtNum(summary.camera_count)} ตัว` : 'คิดจากสีเส้นจราจรบนแผนที่'}
            </p>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" onClick={locate} disabled={nearBusy} aria-pressed={!!near}
            className={`cursor-pointer rounded-lg border px-3 h-8 text-xs font-medium disabled:opacity-60 ${FOCUS} ${near ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-slate-700 border-slate-300 hover:bg-slate-50'}`}>
            {nearBusy ? 'กำลังหาตำแหน่ง…' : near ? 'ใกล้ฉัน ✕' : 'ใกล้ฉัน'}
          </button>
          {provinces.length > 0 && (
            <>
              <select aria-label="เลือกจังหวัด" value={provCode} onChange={(e) => pickProvince(e.target.value)} className={SELECT}>
                <option value="">ทุกจังหวัด</option>
                {provinces.map((p) => <option key={p.code} value={p.code}>{p.province}{p.flow != null ? ` · ${p.flow}` : ''}</option>)}
              </select>
              <select aria-label="เลือกอำเภอ" value={ampCode} onChange={(e) => pickAmphoe(e.target.value)} disabled={!prov} className={SELECT}>
                <option value="">{prov?.code === BANGKOK ? 'ทุกเขต' : 'ทุกอำเภอ'}</option>
                {prov?.amphoes.map((a) => <option key={a.code} value={a.code}>{areaName(prov.code, a.name)}{a.flow != null ? ` · ${a.flow}` : ''}</option>)}
              </select>
            </>
          )}
          {shown ? (
            <Badge tone={shown.online === false ? 'yellow' : 'green'} dot>
              {shown.online === false ? 'ข้อมูลล่าช้า' : 'อัปเดต'} {fmtTime(shown.updated_at)} น.
            </Badge>
          ) : (
            <Skeleton className="h-6 w-28" />
          )}
        </div>
      </div>

      {nearMsg && <p role="status" className="mt-2 text-xs text-amber-700">{nearMsg}</p>}

      {error && !summary && (
        <div className="mt-4">
          <ErrorState message="โหลดข้อมูลรถติดไม่สำเร็จ ลองใหม่อีกครั้ง" onRetry={onRetry} retrying={retrying} />
        </div>
      )}

      {siteDown && (
        <div className="mt-4">
          <BmaSiteNotice source={summary.site} />
        </div>
      )}

      <div className="mt-5 grid grid-cols-1 md:grid-cols-[auto_1fr_auto] gap-6 md:gap-8 items-center">
        {/* score */}
        <div className="flex items-end gap-1.5 shrink-0">
          {summary || area ? (
            <>
              <span className={`text-5xl font-semibold leading-none tabular-nums ${status.text}`} style={{ textShadow: `0 0 24px ${status.hex}66` }}>
                {flow ?? '–'}
              </span>
              <span className="text-sm text-slate-500 pb-1">/ 100</span>
            </>
          ) : (
            <Skeleton className="h-12 w-24" />
          )}
        </div>

        {/* meter */}
        <div className="min-w-0">
          <p className="text-xs text-slate-500 mb-3">คะแนนรถคล่อง (เต็ม 100 ยิ่งมากรถยิ่งคล่อง)</p>
          {summary || area ? <Meter value={flow} colorHex={status.hex} /> : <Skeleton className="h-4 w-full rounded-full" />}
        </div>

        {/* status */}
        <div className="min-w-0 md:max-w-[260px] md:border-l md:border-slate-200 md:pl-6">
          {summary || area ? (
            <>
              <p className={`text-xl font-semibold leading-7 ${status.text}`}>{level.label}</p>
              <p className="text-[13px] text-slate-600 mt-0.5 leading-5">{level.hint}</p>
              {area ? (
                <div className="mt-2">
                  {area.flow != null && area.flow_1h != null && <DeltaText d={area.flow - area.flow_1h} />}
                  <p className="text-xs text-slate-500 mt-1 tabular-nums">
                    ติดขัด {fmtNum(area.red_km)} · ชะลอ {fmtNum(area.yellow_km)} · คล่อง {fmtNum(area.green_km)} กม.
                  </p>
                </div>
              ) : !siteDown && (
                <div className="mt-2">
                  <Delta history={summary.history} />
                </div>
              )}
            </>
          ) : (
            <div className="space-y-2 mt-1">
              <Skeleton className="h-6 w-28" />
              <Skeleton className="h-4 w-56" />
            </div>
          )}
        </div>
      </div>

      {ranking && ranking.rows.length > 0 && <AreaRanking key={near ? 'near' : provCode} {...ranking} />}

      {near && (
        <div className="mt-4 border-t border-slate-200 pt-3">
          <p className="text-[13px] font-semibold text-slate-900 mb-1.5">เหตุใกล้คุณ</p>
          {near.events.length === 0 ? (
            <p className="text-xs text-slate-500">ไม่มีอุบัติเหตุ ถนนปิด หรือน้ำท่วมในรัศมี {near.radius_km} กม.</p>
          ) : (
            <ul className="flex flex-col gap-1 text-xs">
              {near.events.map((e, i) => (
                <li key={i} className="flex items-baseline gap-2">
                  <b className={`shrink-0 ${EVENT_TONE[e.kind] || 'text-slate-700'}`}>{EVENT_TH[e.kind] || 'เหตุบนถนน'}</b>
                  <span className="min-w-0 truncate text-slate-800" title={e.title}>{e.title}{e.depth_cm ? ` · น้ำ ${e.depth_cm} ซม.` : ''}</span>
                  <span className="shrink-0 ml-auto tabular-nums text-slate-500">{e.distance_km} กม.</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Card>
  );
}
