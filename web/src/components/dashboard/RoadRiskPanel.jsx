// Per-road flood outlook for Bangkok and the five metro provinces (/api/roads/risk, road_service.py).
// Each row joins four different live measurements around one road: centimetres of water on the road
// (Bangkok sensors only), 24 h rainfall at the nearest gauge, the nearest canal or river as a % of
// its bank, and how congested the road is now. The score ranks them; the columns show why.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchRoadRisk } from '../../lib/api.js';
import { Card, Badge, Button, SectionHeader, Segmented, Skeleton, EmptyState, Truncate, FOCUS } from './ui.jsx';
import { StatTile, StatusBanner } from './primitives.jsx';
import { fmtNum, fmtTime } from './format.js';

const POLL_MS = 120000;
const PAGE = 25;

const RISK = {
  high: { tone: 'red', text: 'text-red-700', bar: 'bg-red-500' },
  medium: { tone: 'yellow', text: 'text-amber-700', bar: 'bg-amber-500' },
  low: { tone: 'blue', text: 'text-sky-700', bar: 'bg-sky-500' },
  none: { tone: 'green', text: 'text-emerald-700', bar: 'bg-emerald-500' },
};
const LEVELS = [['all', 'ทุกระดับ'], ['high', 'เสี่ยงสูง'], ['medium', 'เฝ้าระวัง'], ['low', 'เสี่ยงต่ำ']];
const TREND_MARK = { rising: '▲', falling: '▼', steady: '▬' };

export default function RoadRiskPanel({ isActive, onOpenRoad }) {
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [level, setLevel] = useState('all');
  const [province, setProvince] = useState('');
  const [query, setQuery] = useState('');
  const [limit, setLimit] = useState(PAGE);

  const load = useCallback(() => {
    setRefreshing(true);
    return fetchRoadRisk({ limit: 2000 })
      .then((d) => { setData(d); setFailed(false); })
      .catch(() => setFailed(true))
      .finally(() => setRefreshing(false));
  }, []);

  useEffect(() => {
    if (!isActive) return;
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [isActive, load]);

  const rows = useMemo(() => {
    if (!data) return [];
    const q = query.trim().toLowerCase();
    return data.items.filter((r) => {
      if (level !== 'all' && r.level !== level) return false;
      if (province && r.province !== province) return false;
      if (!q) return true;
      return r.road.toLowerCase().includes(q) || (r.district || '').toLowerCase().includes(q);
    });
  }, [data, level, province, query]);

  if (!data) {
    return (
      <div className="flex flex-col gap-3">
        <Skeleton className="h-24" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  const c = data.counts || {};
  const ai = data.analysis;
  const provinces = data.provinces || [];

  return (
    <div className="flex flex-col gap-4">
      <Card className="p-5">
        <SectionHeader
          id="road-risk"
          title="ความเสี่ยงน้ำท่วมขังรายถนน"
          description={`${fmtNum(data.total)} สายในกรุงเทพฯ และปริมณฑล · รวมฝน 24 ชม. ระดับน้ำคลอง/แม่น้ำ เซ็นเซอร์น้ำบนถนน และสภาพจราจร`}
          action={
            <div className="flex items-center gap-2">
              {data.updated_at && <Badge tone={c.high ? 'red' : 'green'} dot>{fmtTime(data.updated_at)} น.</Badge>}
              <Button size="sm" onClick={load} loading={refreshing}>รีเฟรช</Button>
            </div>
          }
        />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mt-4">
          <StatTile label="เสี่ยงสูง" value={fmtNum(c.high || 0)} tone={c.high ? 'red' : undefined} sub="คะแนน 60 ขึ้นไป" />
          <StatTile label="เฝ้าระวัง" value={fmtNum(c.medium || 0)} tone={c.medium ? 'yellow' : undefined} sub="คะแนน 35-59" />
          <StatTile label="เสี่ยงต่ำ" value={fmtNum(c.low || 0)} sub="คะแนน 15-34" />
          <StatTile label="ปกติ" value={fmtNum(c.none || 0)} tone="green" sub="คะแนนต่ำกว่า 15" />
        </div>
        {data.error && (
          <div className="mt-3"><StatusBanner tone="yellow" label="สร้างข้อมูลรอบล่าสุดไม่สำเร็จ">{data.error}</StatusBanner></div>
        )}
        {failed && !data.error && <p className="mt-3 text-xs text-amber-700">รีเฟรชรอบล่าสุดไม่สำเร็จ แสดงค่าก่อนหน้า</p>}
      </Card>

      {ai?.headline && (
        <Card className="p-5 border border-slate-200">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={c.high ? 'red' : c.medium ? 'yellow' : 'green'} dot>AI วิเคราะห์รายถนน</Badge>
            <span className="text-xs text-slate-500">{ai.source && ai.source !== 'template' ? ai.source : 'สรุปอัตโนมัติจากตัวเลข'}</span>
          </div>
          <p className="mt-2 text-base font-semibold text-ink-900 leading-6">{ai.headline}</p>
          {ai.detail && <p className="mt-1 text-sm text-slate-700 leading-6">{ai.detail}</p>}
          {ai.roads?.length > 0 && (
            <ol className="mt-3 flex flex-col gap-2">
              {ai.roads.map((r, i) => (
                <li key={`${r.road}-${i}`} className="text-sm">
                  <span className="font-medium text-ink-900">{i + 1}. {r.road}</span>
                  {r.why && <span className="text-slate-700"> — {r.why}</span>}
                  {r.advice && <span className="block text-xs text-slate-500 ml-4">→ {r.advice}</span>}
                </li>
              ))}
            </ol>
          )}
          <p className="mt-3 text-[11px] text-slate-400">{data.note}</p>
        </Card>
      )}

      {provinces.length > 0 && (
        <Card className="p-5">
          <SectionHeader id="road-provinces" title="แยกตามจังหวัด" description="กดเพื่อกรองเฉพาะจังหวัดนั้น" />
          <ul className="mt-3 flex flex-wrap gap-2">
            {provinces.map((p) => {
              const on = province === p.province;
              return (
                <li key={p.province}>
                  <button
                    type="button"
                    onClick={() => { setProvince(on ? '' : p.province); setLimit(PAGE); }}
                    className={`cursor-pointer inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 transition-colors ${FOCUS} ${on ? 'border-blue-500 ring-2 ring-blue-500/30' : 'border-slate-200 hover:border-slate-400'}`}
                  >
                    <span className="text-sm font-medium text-ink-900">{p.province}</span>
                    <span className="text-xs text-slate-500">{fmtNum(p.roads)} สาย</span>
                    {p.high > 0 && <span className="text-xs font-semibold text-red-700">เสี่ยงสูง {p.high}</span>}
                    {p.high === 0 && p.medium > 0 && <span className="text-xs font-semibold text-amber-700">เฝ้าระวัง {p.medium}</span>}
                  </button>
                </li>
              );
            })}
          </ul>
        </Card>
      )}

      <Card className="p-5">
        <SectionHeader
          id="road-table"
          title={province ? `ถนนในจังหวัด${province}` : 'ถนนทุกสาย'}
          description="เรียงตามคะแนนเสี่ยง · แต่ละคอลัมน์คือค่าที่วัดได้จริง ไม่ใช่การพยากรณ์"
          action={<Segmented label="กรองระดับ" options={LEVELS} value={level} onChange={(v) => { setLevel(v); setLimit(PAGE); }} />}
        />
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <input
            value={query}
            onChange={(e) => { setQuery(e.target.value); setLimit(PAGE); }}
            placeholder="ค้นหาชื่อถนน / เขต เช่น สุขุมวิท, รัตนาธิเบศร์, บางกะปิ"
            className="h-9 w-full sm:w-96 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 placeholder:text-slate-400"
          />
          {province && <Button size="sm" onClick={() => setProvince('')}>ล้างตัวกรองจังหวัด</Button>}
        </div>

        {rows.length === 0 ? (
          <div className="mt-3"><EmptyState title="ไม่พบถนนที่ตรงกับเงื่อนไข" description="ลองเปลี่ยนคำค้น ระดับความเสี่ยง หรือล้างตัวกรองจังหวัด" /></div>
        ) : (
          <>
            <p className="mt-2 text-xs text-slate-500">แสดง {fmtNum(Math.min(limit, rows.length))} จาก {fmtNum(rows.length)} สาย</p>
            <div className="mt-2 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-slate-500 border-b border-slate-200">
                    <th className="py-2 pr-3 font-medium">ถนน</th>
                    <th className="py-2 pr-3 font-medium">จังหวัด/เขต</th>
                    <th className="py-2 pr-3 font-medium text-right">น้ำบนถนน</th>
                    <th className="py-2 pr-3 font-medium text-right">ฝน 24 ชม.</th>
                    <th className="py-2 pr-3 font-medium text-right">คลอง/แม่น้ำ</th>
                    <th className="py-2 pr-3 font-medium text-right">รถติด</th>
                    <th className="py-2 font-medium text-right">ความเสี่ยง</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {rows.slice(0, limit).map((r) => {
                    const rk = RISK[r.level] || RISK.none;
                    return (
                      <tr key={r.road} className="align-top">
                        <td className="py-2 pr-3">
                          <button
                            type="button"
                            onClick={() => onOpenRoad?.(r.road)}
                            className={`cursor-pointer text-left text-ink-900 hover:underline ${FOCUS}`}
                          >
                            <Truncate text={r.road} />
                          </button>
                          {r.length_km != null && <span className="block text-[11px] text-slate-500">{r.length_km} กม.</span>}
                        </td>
                        <td className="py-2 pr-3 text-slate-600 whitespace-nowrap">
                          {r.province || '–'}
                          {r.district && <span className="block text-[11px] text-slate-500">{r.district}</span>}
                        </td>
                        <td className="py-2 pr-3 text-right whitespace-nowrap">
                          {r.measured ? (
                            <>
                              <span className={`tabular-nums font-semibold ${r.flood_cm > 10 ? 'text-red-700' : r.flood_cm > 5 ? 'text-amber-700' : 'text-slate-700'}`}>
                                {r.flood_cm} ซม.
                              </span>
                              {r.flood_trend && <span className="block text-[11px] text-slate-500">{TREND_MARK[r.flood_trend]} {r.wet_sensors}/{r.sensors} จุด</span>}
                            </>
                          ) : (
                            <span className="text-[11px] text-slate-400" title="ถนนสายนี้ไม่มีเซ็นเซอร์วัดน้ำบนผิวถนน">ไม่มีเซ็นเซอร์</span>
                          )}
                        </td>
                        <td className="py-2 pr-3 text-right whitespace-nowrap">
                          {r.rain_24h != null ? (
                            <>
                              <span className={`tabular-nums ${r.rain_level === 'heavy' || r.rain_level === 'extreme' ? 'font-semibold text-red-700' : 'text-slate-700'}`}>{r.rain_24h} มม.</span>
                              <span className="block text-[11px] text-slate-500">ห่าง {r.rain_km} กม.</span>
                            </>
                          ) : <span className="text-slate-400">–</span>}
                        </td>
                        <td className="py-2 pr-3 text-right whitespace-nowrap">
                          {r.gauge_pct != null ? (
                            <>
                              <span className={`tabular-nums ${r.gauge_level === 'overflow' ? 'font-semibold text-red-700' : r.gauge_level === 'high' ? 'font-semibold text-amber-700' : 'text-slate-700'}`}>{Math.round(r.gauge_pct)}%</span>
                              <span className="block text-[11px] text-slate-500 max-w-[9rem] truncate">{r.gauge_at}</span>
                            </>
                          ) : <span className="text-slate-400">–</span>}
                        </td>
                        <td className="py-2 pr-3 text-right whitespace-nowrap">
                          <span className="tabular-nums text-slate-700">{r.red_pct}%</span>
                          {r.traffic_level && <span className="block text-[11px] text-slate-500">{r.traffic_level}</span>}
                        </td>
                        <td className="py-2 text-right whitespace-nowrap">
                          <span className={`tabular-nums font-semibold ${rk.text}`}>{Math.round(r.score)}</span>
                          <span className="mt-1 block h-1.5 w-20 ml-auto rounded-full bg-slate-100 overflow-hidden">
                            <span className={`block h-full rounded-full ${rk.bar}`} style={{ width: `${Math.max(3, Math.min(100, r.score))}%` }} />
                          </span>
                          <Badge tone={rk.tone} dot={r.level !== 'none'}>{r.level_th}</Badge>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {rows.length > limit && (
              <Button size="sm" className="mt-3" onClick={() => setLimit((n) => n + PAGE * 2)}>
                ดูเพิ่มอีก {fmtNum(Math.min(PAGE * 2, rows.length - limit))} สาย
              </Button>
            )}
          </>
        )}
        <p className="mt-3 text-[11px] text-slate-400">{data.note}</p>
      </Card>
    </div>
  );
}
