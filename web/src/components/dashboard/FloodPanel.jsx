// Road flooding across Bangkok from the BMA drainage sensors (/api/flood/*, see flood_service.py).
// Depth is centimetres of water over the road surface, refreshed by the sensors every 5 minutes;
// the thresholds (5 / 10 cm) are the ones the BMA's own map draws with.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchFloodStatus, fetchFloodRoads, fetchFloodAnalysis, fetchFloodStations } from '../../lib/api.js';
import { Card, Badge, Button, SectionHeader, Segmented, Skeleton, EmptyState, Truncate, FOCUS } from './ui.jsx';
import { StatTile, StatusBanner } from './primitives.jsx';
import { fmtNum, fmtTime, agoText } from './format.js';

const POLL_MS = 60000;

const LEVEL = {
  flood: { tone: 'red', label: 'น้ำท่วม', text: 'text-red-700', bg: 'bg-red-500' },
  slight: { tone: 'yellow', label: 'ท่วมเล็กน้อย', text: 'text-amber-700', bg: 'bg-amber-500' },
  normal: { tone: 'green', label: 'ปกติ', text: 'text-emerald-700', bg: 'bg-emerald-500' },
  offline: { tone: 'neutral', label: 'ขัดข้อง', text: 'text-slate-500', bg: 'bg-slate-400' },
};

// Depth bar: 30 cm is "as deep as this bar goes" (a car stalls well before that)
const barPct = (cm) => Math.max(6, Math.min(100, Math.round(((cm || 0) / 30) * 100)));

// The AI report reads the sensor numbers; severity decides the colour of the card
const SEVERITY = {
  alert: { tone: 'red', label: 'ต้องเฝ้าระวังสูง', card: 'border-red-200 bg-red-50/70 dark:border-red-900/50 dark:bg-red-950/30', dot: 'bg-red-500' },
  watch: { tone: 'yellow', label: 'เฝ้าระวัง', card: 'border-amber-200 bg-amber-50/70 dark:border-amber-900/50 dark:bg-amber-950/30', dot: 'bg-amber-500' },
  normal: { tone: 'green', label: 'ปกติ', card: 'border-emerald-200 bg-emerald-50/70 dark:border-emerald-900/50 dark:bg-emerald-950/30', dot: 'bg-emerald-500' },
};

// The full sensor list at the bottom: every monitored road, not only the wet ones
const FILTERS = [['all', 'ทั้งหมด'], ['wet', 'มีน้ำขัง'], ['normal', 'ปกติ'], ['offline', 'ขัดข้อง']];
const PAGE = 40;

const TREND_MARK = { rising: '▲', falling: '▼', steady: '▬' };
const TREND_CLASS = { rising: 'text-red-600', falling: 'text-emerald-600', steady: 'text-slate-400' };

export default function FloodPanel({ isActive, onNavigate }) {
  const [status, setStatus] = useState(null);
  const [roads, setRoads] = useState(null);
  const [ai, setAi] = useState(null);
  const [all, setAll] = useState(null);
  const [filter, setFilter] = useState('all');
  const [query, setQuery] = useState('');
  const [limit, setLimit] = useState(PAGE);
  const [failed, setFailed] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [showAll, setShowAll] = useState(false);

  const load = useCallback(() => {
    setRefreshing(true);
    return Promise.allSettled([
      fetchFloodStatus().then((d) => { setStatus(d); setFailed(false); }).catch(() => setFailed(true)),
      fetchFloodRoads(60).then((d) => setRoads(d.items)).catch(() => {}),
      fetchFloodAnalysis().then((d) => setAi(d)).catch(() => {}),
      fetchFloodStations({ limit: 1000 }).then((d) => setAll(d.items)).catch(() => {}),
    ]).finally(() => setRefreshing(false));
  }, []);

  useEffect(() => {
    if (!isActive) return;
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [isActive, load]);

  if (!status) {
    return (
      <div className="flex flex-col gap-3">
        <Skeleton className="h-24" />
        <Skeleton className="h-48" />
      </div>
    );
  }

  const c = status.counts || {};
  const wet = status.wet || [];
  const wetCount = (c.flood || 0) + (c.slight || 0);
  const deepest = wet[0];
  const shown = showAll ? wet : wet.slice(0, 10);

  return (
    <div className="flex flex-col gap-4">
      <Card className="p-5">
        <SectionHeader
          id="flood-now"
          title="น้ำท่วมขังถนน กรุงเทพฯ"
          description={`เซ็นเซอร์วัดระดับน้ำบนผิวถนน ${fmtNum(status.total)} จุด ของสำนักการระบายน้ำ กทม. · วัดทุก 5 นาที`}
          action={
            <div className="flex items-center gap-2">
              {status.feed_time && <Badge tone={wetCount ? 'red' : 'green'} dot>{fmtTime(status.feed_time)} น.</Badge>}
              <Button size="sm" onClick={load} loading={refreshing}>รีเฟรช</Button>
            </div>
          }
        />

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mt-4">
          <StatTile label="น้ำท่วม (เกิน 10 ซม.)" value={fmtNum(c.flood || 0)} tone={c.flood ? 'red' : undefined}
                    sub={deepest && deepest.status === 'flood' ? `ลึกสุด ${deepest.level_cm} ซม.` : 'ไม่มีจุดท่วมขณะนี้'} />
          <StatTile label="ท่วมเล็กน้อย (5-10 ซม.)" value={fmtNum(c.slight || 0)} tone={c.slight ? 'yellow' : undefined}
                    sub="รถเล็กยังผ่านได้ ควรชะลอ" />
          <StatTile label="ถนนปกติ" value={fmtNum(c.normal || 0)} tone="green"
                    sub={`${Math.round(((c.normal || 0) / Math.max(1, status.total)) * 100)}% ของจุดวัดทั้งหมด`} />
          <StatTile label="เครื่องวัดขัดข้อง" value={fmtNum(c.offline || 0)}
                    sub={c.offline ? 'ไม่ส่งค่าล่าสุด ไม่ได้แปลว่าไม่ท่วม' : 'ส่งข้อมูลครบทุกจุด'} />
        </div>

        {status.error && (
          <div className="mt-3">
            <StatusBanner tone="yellow" label="ดึงข้อมูลล่าสุดไม่สำเร็จ">
              แสดงค่าที่บันทึกไว้เมื่อ {fmtTime(status.updated_at)} น. ({agoText(status.updated_at)}) · ระบบจะลองใหม่อัตโนมัติ
            </StatusBanner>
          </div>
        )}
        {!status.error && failed && (
          <p className="mt-3 text-xs text-amber-700">รีเฟรชรอบล่าสุดไม่สำเร็จ แสดงค่าก่อนหน้า</p>
        )}
      </Card>

      {ai?.headline && (() => {
        const sv = SEVERITY[ai.severity] || SEVERITY.normal;
        return (
          <Card className={`p-5 border ${sv.card}`}>
            <div className="flex items-start gap-3">
              <span className={`mt-2 shrink-0 inline-block w-2.5 h-2.5 rounded-full ${sv.dot}`} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={sv.tone} dot>{sv.label}</Badge>
                  <span className="text-xs text-slate-500">
                    AI วิเคราะห์จากค่าเซ็นเซอร์ {ai.facts?.time ? `เวลา ${ai.facts.time} น.` : ''}
                    {ai.source && ai.source !== 'template' ? ` · ${ai.source}` : ' · สรุปอัตโนมัติ'}
                  </span>
                </div>
                <p className="mt-2 text-base font-semibold text-ink-900 leading-6">{ai.headline}</p>
                {ai.detail && <p className="mt-1 text-sm text-slate-700 leading-6">{ai.detail}</p>}

                {ai.hotspots?.length > 0 && (
                  <div className="mt-3">
                    <p className="text-xs font-medium text-slate-600">จุดที่ต้องจับตา</p>
                    <ul className="mt-1.5 flex flex-col gap-1">
                      {ai.hotspots.map((h, i) => (
                        <li key={`${h.where}-${i}`} className="text-sm text-slate-700 flex gap-2">
                          <span className="text-slate-400">{i + 1}.</span>
                          <span className="min-w-0"><span className="font-medium text-ink-900">{h.where}</span>{h.note ? ` — ${h.note}` : ''}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {ai.advice?.length > 0 && (
                  <div className="mt-3">
                    <p className="text-xs font-medium text-slate-600">คำแนะนำ</p>
                    <ul className="mt-1.5 flex flex-col gap-1">
                      {ai.advice.map((a, i) => (
                        <li key={i} className="text-sm text-slate-700 flex gap-2"><span className="text-slate-400">•</span><span>{a}</span></li>
                      ))}
                    </ul>
                  </div>
                )}

                {ai.outlook && <p className="mt-3 text-sm text-slate-600">แนวโน้ม: {ai.outlook}</p>}
                <p className="mt-2 text-[11px] text-slate-400">
                  วิเคราะห์จากตัวเลขเซ็นเซอร์เท่านั้น ไม่ใช่การพยากรณ์ฝน · ตรวจสอบกับรายงานหน้างานก่อนตัดสินใจ
                </p>
              </div>
            </div>
          </Card>
        );
      })()}

      {wetCount === 0 ? (
        <Card className="p-5">
          <div className="flex items-start gap-3">
            <span className="mt-0.5 inline-block w-3 h-3 rounded-full bg-emerald-500 shrink-0" />
            <div className="min-w-0">
              <p className="text-base font-semibold text-ink-900">ไม่มีจุดน้ำท่วมขังขณะนี้</p>
              <p className="text-sm text-slate-600 mt-0.5">
                จุดวัดทั้ง {fmtNum(c.normal || 0)} จุดที่ส่งข้อมูลอยู่ อ่านค่าไม่เกิน {status.thresholds?.slight_cm ?? 5} ซม.
                {c.offline ? ` · มี ${c.offline} จุดที่เครื่องวัดขัดข้อง` : ''}
              </p>
              <Button size="sm" className="mt-3" onClick={() => onNavigate?.('map')}>ดูจุดวัดทั้งหมดบนแผนที่</Button>
            </div>
          </div>
        </Card>
      ) : (
        <Card className="p-5">
          <SectionHeader
            id="flood-points"
            title={`จุดที่มีน้ำท่วมขัง ${fmtNum(wetCount)} จุด`}
            description="เรียงจากลึกที่สุด · กดแถวเพื่อเปิดตำแหน่งบนแผนที่"
            action={<Badge tone={c.flood ? 'red' : 'yellow'} dot>{c.flood ? `ท่วม ${c.flood}` : `เล็กน้อย ${c.slight}`}</Badge>}
          />
          <ol className="mt-3 divide-y divide-slate-100">
            {shown.map((s) => {
              const lv = LEVEL[s.status] || LEVEL.offline;
              return (
                <li key={s.code}>
                  <button
                    type="button"
                    onClick={() => onNavigate?.('map')}
                    className={`cursor-pointer w-full text-left py-2.5 flex items-center gap-3 hover:bg-slate-50 rounded-lg px-2 -mx-2 transition-colors ${FOCUS}`}
                  >
                    <span className={`shrink-0 w-14 text-right text-lg font-semibold tabular-nums ${lv.text}`}>{s.level_cm}</span>
                    <span className="shrink-0 text-[11px] text-slate-500 -ml-2">ซม.</span>
                    <span className="min-w-0 flex-1">
                      <Truncate text={s.short_name} className="text-sm font-medium text-ink-900" />
                      <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-slate-500 mt-0.5">
                        {s.district && <span>เขต{s.district}</span>}
                        {s.road && <span className="truncate max-w-[14rem]">{s.road}</span>}
                        {s.kind === 'tunnel' && <span>อุโมงค์ทางลอด{s.side ? ` ${s.side}` : ''}</span>}
                        {s.started && <span>เริ่มท่วม {s.started.slice(-5)} น.</span>}
                        {s.max_cm ? <span>สูงสุด {s.max_cm} ซม.</span> : null}
                        {s.trend && (
                          <span className={TREND_CLASS[s.trend]}>
                            {TREND_MARK[s.trend]} {s.trend_th}
                            {s.delta_cm ? ` ${s.delta_cm > 0 ? '+' : ''}${s.delta_cm} ซม./25 นาที` : ''}
                          </span>
                        )}
                      </span>
                      <span className="mt-1.5 block h-1.5 w-full max-w-xs rounded-full bg-slate-100 overflow-hidden">
                        <span className={`block h-full rounded-full ${lv.bg}`} style={{ width: `${barPct(s.level_cm)}%` }} />
                      </span>
                    </span>
                    <Badge tone={lv.tone} dot>{lv.label}</Badge>
                  </button>
                </li>
              );
            })}
          </ol>
          {wet.length > 10 && (
            <Button size="sm" className="mt-3" onClick={() => setShowAll((v) => !v)}>
              {showAll ? 'ย่อรายการ' : `ดูทั้งหมด ${fmtNum(wet.length)} จุด`}
            </Button>
          )}
        </Card>
      )}

      {(status.districts || []).length > 0 && (
        <Card className="p-5">
          <SectionHeader id="flood-districts" title="เขตที่มีน้ำท่วมขัง" description="จำนวนจุดที่ท่วมในแต่ละเขต และระดับที่ลึกที่สุดของเขตนั้น" />
          <ul className="mt-3 flex flex-wrap gap-2">
            {status.districts.map((d) => (
              <li key={d.district} className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-1.5">
                <span className="text-sm font-medium text-ink-900">{d.district}</span>
                <span className="text-xs text-slate-500">{d.flood + d.slight} จุด</span>
                <span className={`text-sm font-semibold tabular-nums ${d.flood ? 'text-red-700' : 'text-amber-700'}`}>{d.max_cm} ซม.</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {roads && roads.length > 0 && (
        <Card className="p-5">
          <SectionHeader id="flood-roads" title="สรุปรายถนน" description="จุดที่ลึกที่สุดของแต่ละถนน (ถนนหนึ่งสายอาจมีหลายจุดวัด)" />
          <ol className="mt-3 divide-y divide-slate-100">
            {roads.slice(0, 20).map((r) => {
              const lv = LEVEL[r.status] || LEVEL.offline;
              return (
                <li key={r.road} className="py-2 flex items-center gap-3">
                  <span className={`shrink-0 w-16 text-right text-base font-semibold tabular-nums ${lv.text}`}>{r.level_cm} ซม.</span>
                  <span className="min-w-0 flex-1">
                    <Truncate text={r.road} className="text-sm font-medium text-ink-900" />
                    <span className="block text-xs text-slate-500">
                      {r.district ? `เขต${r.district} · ` : ''}{r.at}{r.points > 1 ? ` · ${r.points} จุดวัด` : ''}
                    </span>
                  </span>
                  <Badge tone={lv.tone} dot>{lv.label}</Badge>
                </li>
              );
            })}
          </ol>
        </Card>
      )}

      <AllStations
        items={all}
        filter={filter}
        onFilter={(f) => { setFilter(f); setLimit(PAGE); }}
        query={query}
        onQuery={(q) => { setQuery(q); setLimit(PAGE); }}
        limit={limit}
        onMore={() => setLimit((n) => n + PAGE * 2)}
      />

      <p className="text-xs text-slate-500">
        ที่มา: {status.source_name} (<a href={status.source} target="_blank" rel="noreferrer" className="underline">weather.bangkok.go.th/flood</a>)
        · เกณฑ์: ไม่เกิน {status.thresholds?.slight_cm ?? 5} ซม. = ปกติ, {status.thresholds?.slight_cm ?? 5}-{status.thresholds?.flood_cm ?? 10} ซม. = ท่วมเล็กน้อย, เกิน {status.thresholds?.flood_cm ?? 10} ซม. = น้ำท่วม
        · ครอบคลุมเฉพาะพื้นที่ กทม. 50 เขต (นนทบุรี ปทุมธานี สมุทรปราการ นครปฐม ไม่มีเซ็นเซอร์สาธารณะ จึงไม่แสดงผล ไม่ได้แปลว่าไม่ท่วม)
      </p>
    </div>
  );
}

// Every monitored point in one searchable table: road, district, current depth, trend, last reading.
// Sorted deepest first so a wet road is always at the top, whatever the filter.
function AllStations({ items, filter, onFilter, query, onQuery, limit, onMore }) {
  const rows = useMemo(() => {
    if (!items) return [];
    const q = query.trim().toLowerCase();
    return items.filter((s) => {
      if (filter === 'wet' && s.status !== 'flood' && s.status !== 'slight') return false;
      if (filter === 'normal' && s.status !== 'normal') return false;
      if (filter === 'offline' && s.status !== 'offline') return false;
      if (!q) return true;
      return [s.short_name, s.name, s.road, s.district, s.code].some((v) => (v || '').toLowerCase().includes(q));
    });
  }, [items, filter, query]);

  if (!items) return <Skeleton className="h-64" />;

  return (
    <Card className="p-5">
      <SectionHeader
        id="flood-all"
        title={`จุดวัดทั้งหมด ${fmtNum(items.length)} จุด`}
        description="ทุกถนนที่มีเซ็นเซอร์วัดระดับน้ำ พร้อมค่าล่าสุด · ค้นหาชื่อถนนหรือเขตได้"
        action={<Segmented label="กรองสถานะ" options={FILTERS} value={filter} onChange={onFilter} />}
      />

      <input
        value={query}
        onChange={(e) => onQuery(e.target.value)}
        placeholder="ค้นหาชื่อถนน / จุดวัด / เขต เช่น สุขุมวิท, ลาดพร้าว, บางกะปิ"
        className="mt-3 h-9 w-full sm:w-96 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 placeholder:text-slate-400"
      />

      {rows.length === 0 ? (
        <div className="mt-3"><EmptyState title="ไม่พบจุดวัดที่ตรงกับเงื่อนไข" description="ลองเปลี่ยนคำค้นหรือกรองสถานะเป็น 'ทั้งหมด'" /></div>
      ) : (
        <>
          <p className="mt-2 text-xs text-slate-500">แสดง {fmtNum(Math.min(limit, rows.length))} จาก {fmtNum(rows.length)} จุด · เรียงจากลึกที่สุด</p>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-slate-500 border-b border-slate-200">
                  <th className="py-2 pr-3 font-medium">จุดวัด</th>
                  <th className="py-2 pr-3 font-medium">ถนน</th>
                  <th className="py-2 pr-3 font-medium">เขต</th>
                  <th className="py-2 pr-3 font-medium text-right">ระดับน้ำ</th>
                  <th className="py-2 pr-3 font-medium">แนวโน้ม</th>
                  <th className="py-2 pr-3 font-medium">สถานะ</th>
                  <th className="py-2 font-medium text-right">อัปเดต</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.slice(0, limit).map((s) => {
                  const lv = LEVEL[s.status] || LEVEL.offline;
                  return (
                    <tr key={`${s.code}-${s.side || ''}`} className="align-top">
                      <td className="py-2 pr-3">
                        <Truncate text={s.short_name} className="text-ink-900" />
                        {s.kind === 'tunnel' && <span className="block text-[11px] text-slate-500">อุโมงค์ทางลอด{s.side ? ` ${s.side}` : ''}</span>}
                      </td>
                      <td className="py-2 pr-3 text-slate-600"><Truncate text={s.road || '–'} /></td>
                      <td className="py-2 pr-3 text-slate-600 whitespace-nowrap">{s.district || '–'}</td>
                      <td className={`py-2 pr-3 text-right tabular-nums font-semibold whitespace-nowrap ${lv.text}`}>
                        {s.status === 'offline' ? '–' : `${s.level_cm} ซม.`}
                      </td>
                      <td className="py-2 pr-3 whitespace-nowrap">
                        {s.trend ? <span className={`text-xs ${TREND_CLASS[s.trend]}`}>{TREND_MARK[s.trend]} {s.trend_th}</span>
                                 : <span className="text-xs text-slate-400">–</span>}
                      </td>
                      <td className="py-2 pr-3"><Badge tone={lv.tone} dot={s.status !== 'normal'}>{lv.label}</Badge></td>
                      <td className="py-2 text-right text-xs text-slate-500 whitespace-nowrap">{s.ts_th ? s.ts_th.slice(-5) : '–'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {rows.length > limit && (
            <Button size="sm" className="mt-3" onClick={onMore}>ดูเพิ่มอีก {fmtNum(Math.min(PAGE * 2, rows.length - limit))} จุด</Button>
          )}
        </>
      )}
    </Card>
  );
}
