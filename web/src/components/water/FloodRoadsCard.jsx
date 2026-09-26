// ถนนน้ำท่วมตอนนี้: every flooded road right now, from two feeds in one list, deepest first.
//   - BMA road water-level sensors (/api/flood/roads: the worst station per road, sensors report every 5 min)
//   - Department of Highways HDMS tickets still open (/api/flood/hdms: highways in Bangkok and vicinity)
// Polls every 30 s while the tab is open. The "รายชื่อถนนน้ำท่วม" tab of the Water Forecast page.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchFloodRoads, fetchHdmsFloods } from '../../lib/api.js';
import { Card, Badge, SectionHeader, Segmented, Skeleton, EmptyState } from '../dashboard/ui.jsx';
import { fmtNum } from '../dashboard/format.js';

const POLL_MS = 30000;
const SHOWN = 12;
const TREND = { rising: { text: 'น้ำขึ้น', tone: 'red' }, falling: { text: 'น้ำลด', tone: 'green' }, steady: { text: 'ทรงตัว', tone: 'neutral' } };
const FILTERS = [['all', 'ทั้งหมด'], ['bma', 'ถนน กทม. (เซ็นเซอร์)'], ['hdms', 'ทางหลวง (กรมทางหลวง)']];

const agoTh = (ts) => {
  if (!ts) return '';
  const m = Math.round((Date.now() / 1000 - ts) / 60);
  return m < 1 ? 'เมื่อสักครู่' : m < 60 ? `${m} นาทีก่อน` : `${Math.floor(m / 60)} ชม. ${m % 60} นาทีก่อน`;
};

// HDMS depth is typed by hand: "50", "15-20", "10 - 20", "2 0". The deepest number sorts the row.
function hdmsDepth(text) {
  const nums = String(text || '').replace(/(\d)\s+(\d)(?!\s*-)/g, '$1$2').match(/\d+(\.\d+)?/g);
  return nums ? Math.max(...nums.map(Number)) : null;
}

function mergeRoads(bma, hdms) {
  const rows = [];
  for (const r of bma?.items || []) {
    rows.push({
      id: `bma-${r.road}`, source: 'bma', road: r.road.trim(), where: r.at, area: r.district ? `เขต${r.district}` : '',
      depth: r.level_cm, depthText: r.level_cm != null ? `${r.level_cm.toFixed(1)} ซม.` : '–',
      severe: r.status === 'flood', trend: r.trend, delta: r.delta_cm, ts: r.ts, since: r.started, lat: r.lat, lng: r.lng,
      extra: r.points > 1 ? `${r.points} จุดวัด · สูงสุด ${r.max_cm ?? '–'} ซม.` : r.max_cm != null ? `สูงสุด ${r.max_cm} ซม.` : '',
    });
  }
  for (const h of hdms?.items || []) {
    if (!h.active) continue;
    const depth = hdmsDepth(h.depth_cm);
    const area = h.amphoe ? (h.province === 'กรุงเทพมหานคร' ? `เขต${h.amphoe}` : `อ.${h.amphoe} จ.${h.province}`) : h.province || '';
    rows.push({
      id: h.id, source: 'hdms', road: h.place || h.title, where: h.title, area,
      depth, depthText: h.depth_cm ? `${String(h.depth_cm).trim()} ซม.` : 'ไม่ระบุ', severe: depth == null || depth >= 10,
      ts: h.ts, lat: h.lat, lng: h.lng, photo: h.photos?.[0],
      extra: [h.lane_closure ? 'ปิดช่องจราจร' : null, h.closure].filter(Boolean).join(' · '),
    });
  }
  return rows.sort((a, b) => (b.depth ?? -1) - (a.depth ?? -1));
}

export default function FloodRoadsCard({ isActive, onOpenRoad }) {
  const [bma, setBma] = useState(null);
  const [hdms, setHdms] = useState(null);
  const [filter, setFilter] = useState('all');
  const [query, setQuery] = useState('');
  const [all, setAll] = useState(false);
  const [, setNow] = useState(0);   // re-render the "x นาทีก่อน" text between polls

  const load = useCallback(() => {
    fetchFloodRoads(300).then(setBma).catch(() => setBma((x) => x || { items: [], failed: true }));
    fetchHdmsFloods().then(setHdms).catch(() => setHdms((x) => x || { items: [], failed: true }));
  }, []);

  useEffect(() => {
    if (!isActive) return undefined;
    load();
    const poll = setInterval(load, POLL_MS);
    const tick = setInterval(() => setNow((n) => n + 1), 15000);
    return () => { clearInterval(poll); clearInterval(tick); };
  }, [isActive, load]);

  const rows = useMemo(() => mergeRoads(bma, hdms), [bma, hdms]);
  const shown = useMemo(() => {
    const q = query.trim();
    return rows.filter((r) => (filter === 'all' || r.source === filter) && (!q || `${r.road} ${r.where} ${r.area}`.includes(q)));
  }, [rows, filter, query]);

  const loading = !bma || !hdms;
  const nBma = rows.filter((r) => r.source === 'bma').length;
  const nHdms = rows.length - nBma;
  const rising = rows.filter((r) => r.trend === 'rising').length;
  const updated = Math.max(bma?.feed_time || bma?.updated_at || 0, hdms?.updated_at || 0) || null;

  return (
    <Card className="p-4">
      <SectionHeader
        title={
          <span className="inline-flex items-center gap-2">
            รายชื่อถนนน้ำท่วม
            <span className="relative flex w-2 h-2" aria-hidden="true">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-400 opacity-75" />
              <span className="relative inline-flex w-2 h-2 rounded-full bg-red-500" />
            </span>
          </span>
        }
        description={
          loading
            ? 'กำลังโหลดข้อมูลถนนน้ำท่วม'
            : `ถนน กทม. ${fmtNum(nBma)} สาย (เซ็นเซอร์วัดระดับน้ำ สำนักการระบายน้ำ) · ทางหลวง ${fmtNum(nHdms)} จุด (กรมทางหลวง)${rising ? ` · น้ำกำลังขึ้น ${rising} สาย` : ''} · รีเฟรชเองทุก 30 วินาที${updated ? ` · ข้อมูลล่าสุด ${agoTh(updated)}` : ''}`
        }
      />
      <div className="flex flex-wrap items-center gap-2 mt-3">
        <Segmented options={FILTERS} value={filter} onChange={(v) => { setFilter(v); setAll(false); }} label="แหล่งข้อมูลถนนน้ำท่วม" />
        <input
          type="search"
          value={query}
          onChange={(e) => { setQuery(e.target.value); setAll(false); }}
          placeholder="ค้นหาถนน / เขต"
          aria-label="ค้นหาถนนหรือเขต"
          className="h-8 w-44 rounded-lg border border-slate-300 bg-white px-2 text-xs text-slate-700"
        />
      </div>
      {(bma?.failed || hdms?.failed) && (
        <p role="status" className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          โหลดข้อมูล{bma?.failed ? 'เซ็นเซอร์ กทม.' : 'กรมทางหลวง'}ไม่สำเร็จ จะลองใหม่อัตโนมัติ
        </p>
      )}

      {loading ? (
        <div className="mt-3 space-y-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-12" />)}</div>
      ) : shown.length === 0 ? (
        <div className="mt-3">
          <EmptyState title={rows.length ? 'ไม่พบถนนที่ตรงกับตัวกรอง' : 'ตอนนี้ไม่มีรายงานถนนน้ำท่วม'} description={rows.length ? 'ลองเปลี่ยนคำค้นหรือแหล่งข้อมูล' : 'เซ็นเซอร์ กทม. และกรมทางหลวงไม่พบน้ำท่วมขัง'} />
        </div>
      ) : (
        <>
          <ul className="mt-3 divide-y divide-slate-100 rounded-lg border border-slate-200">
            {(all ? shown : shown.slice(0, SHOWN)).map((r) => {
              const t = TREND[r.trend];
              return (
                <li key={r.id} className="p-2.5 flex gap-3 items-start">
                  {r.photo && (
                    <a href={r.photo.url} target="_blank" rel="noopener noreferrer" className="shrink-0" aria-label={`รูป ${r.road}`}>
                      <img src={r.photo.thumb} alt="" loading="lazy" referrerPolicy="no-referrer" className="w-14 h-14 rounded-md object-cover" />
                    </a>
                  )}
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-baseline gap-x-2">
                      {onOpenRoad && r.source === 'bma' ? (
                        <button type="button" onClick={() => onOpenRoad(r.road)} title="ดูกล้อง CCTV บนถนนนี้" className="cursor-pointer text-sm font-semibold text-slate-900 hover:text-blue-700 hover:underline text-left">{r.road}</button>
                      ) : (
                        <span className="text-sm font-semibold text-slate-900">{r.road}</span>
                      )}
                      <span className="text-xs text-slate-500">{r.area}</span>
                    </div>
                    <p className="text-xs text-slate-600 leading-5">
                      {[r.where !== r.road ? r.where : null, r.extra, r.since ? `ท่วมตั้งแต่ ${r.since}` : null].filter(Boolean).join(' · ')}
                    </p>
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mt-1 text-xs text-slate-500">
                      <Badge tone={r.source === 'bma' ? 'blue' : 'yellow'}>{r.source === 'bma' ? 'เซ็นเซอร์ กทม.' : 'กรมทางหลวง'}</Badge>
                      {t && <Badge tone={t.tone}>{t.text}{r.delta ? ` ${r.delta > 0 ? '+' : ''}${r.delta} ซม.` : ''}</Badge>}
                      {r.ts && <span>{r.source === 'bma' ? 'วัดเมื่อ' : 'แจ้งเมื่อ'} {agoTh(r.ts)}</span>}
                      {r.lat && r.lng && (
                        <a href={`https://www.google.com/maps?q=${r.lat},${r.lng}`} target="_blank" rel="noopener noreferrer" className="text-blue-700 hover:underline">ดูแผนที่</a>
                      )}
                    </div>
                  </div>
                  <div className="shrink-0 text-right">
                    <p className={`text-sm font-semibold tabular-nums ${r.severe ? 'text-red-700' : 'text-amber-700'}`}>{r.depthText}</p>
                  </div>
                </li>
              );
            })}
          </ul>
          {shown.length > SHOWN && (
            <button type="button" onClick={() => setAll(!all)} className="cursor-pointer mt-2 text-xs text-blue-700 hover:underline">
              {all ? 'ย่อ' : `ดูทั้งหมด ${fmtNum(shown.length)} รายการ`}
            </button>
          )}
        </>
      )}
      <p className="text-[11px] text-slate-500 mt-2 leading-4">
        ระดับน้ำเซ็นเซอร์ กทม. วัดทุก 5 นาที (weather.bangkok.go.th/flood) · ทางหลวงเป็นรายงานของเจ้าหน้าที่กรมทางหลวง (hdms.doh.go.th) ระดับน้ำประเมินด้วยตา ·
        ถนนที่ไม่มีเซ็นเซอร์หรือเซ็นเซอร์ออฟไลน์จะไม่อยู่ในรายการ ดูรายงานประชาชนเพิ่มในแท็บ “การแจ้งน้ำท่วม”
      </p>
    </Card>
  );
}
