// การแจ้งน้ำท่วม: every flood report in one list, the same reports the Water Forecast map shows as
// "มีรายงานน้ำท่วม" (Longdo Traffic, relayed from iTIC / FM91: /api/flood/longdo) plus what people sent
// through Traffy Fondue in the last 6 h (/api/flood/reports), with the Qwen reading of the Traffy
// reports (TraffyAnalysisCard) below. Both feeds in one list grouped by district, with search and
// district / state filters. Tab of the Water Forecast page.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchFloodReports, fetchLongdoFloods } from '../../lib/api.js';
import { Card, Badge, Button, SectionHeader, Skeleton, EmptyState } from '../dashboard/ui.jsx';
import { fmtNum } from '../dashboard/format.js';
import TraffyAnalysisCard from '../dashboard/TraffyAnalysisCard.jsx';
import TraffyHistoryCard from './TraffyHistoryCard.jsx';

const POLL_MS = 60000;
const REPORTS_SHOWN = 3;   // per district, until the district is expanded
const NO_DISTRICT = 'ไม่ระบุเขต';
const SOURCES = {
  longdo: { label: 'iTIC / FM91', tone: 'blue', hint: 'รายงานบน Longdo Traffic' },
  traffy: { label: 'ประชาชน (Traffy)', tone: 'neutral', hint: 'Traffy Fondue' },
};
const STATE_TONE = { รอรับเรื่อง: 'red', กำลังดำเนินการ: 'yellow', 'ส่งต่อ(ใหม่)': 'yellow', เสร็จสิ้น: 'green', ยังมีน้ำท่วม: 'red', สิ้นสุดแล้ว: 'green' };
const SELECT = 'h-9 rounded-lg border border-slate-300 bg-white px-2 text-sm text-slate-700';
const agoTh = (ts) => {
  const m = Math.round((Date.now() / 1000 - ts) / 60);
  return m < 1 ? 'เมื่อสักครู่' : m < 60 ? `${m} นาทีก่อน` : `${Math.floor(m / 60)} ชม. ${m % 60} นาทีก่อน`;
};

// The 50 Bangkok districts, to tell "เขตดอนเมือง" from "เขตทางหลวง" (highway zone) in free text
const BKK_DISTRICTS = ('พระนคร ป้อมปราบศัตรูพ่าย สัมพันธวงศ์ ดุสิต พญาไท ราชเทวี ดินแดง ห้วยขวาง วังทองหลาง ปทุมวัน บางรัก '
  + 'สาทร บางคอแหลม ยานนาวา คลองเตย วัฒนา พระโขนง บางนา สวนหลวง จตุจักร บางซื่อ ลาดพร้าว หลักสี่ ดอนเมือง สายไหม บางเขน '
  + 'บางกะปิ สะพานสูง บึงกุ่ม คันนายาว ลาดกระบัง ประเวศ มีนบุรี คลองสามวา หนองจอก ธนบุรี คลองสาน บางกอกใหญ่ บางกอกน้อย '
  + 'บางพลัด ตลิ่งชัน ทวีวัฒนา ภาษีเจริญ หนองแขม บางแค บางบอน บางขุนเทียน จอมทอง ราษฎร์บูรณะ ทุ่งครุ').split(' ');

// Group label for a report: "เขต<name>" for Bangkok, "อ.<name>" outside it. Longdo reports carry the
// place only inside the address text ("... แขวงสนามบิน เขตดอนเมือง ...", "... อ.ธัญบุรี จ.ปทุมธานี").
function districtOf(text) {
  const t = text || '';
  const bkk = BKK_DISTRICTS.find((d) => t.includes(`เขต${d}`) || t.includes(`เขต ${d}`));
  if (bkk) return `เขต${bkk}`;
  const m = /(?:อำเภอ|อ\.)\s?([^\s(),]+)/.exec(t);
  if (!m || m[1] === '-') return NO_DISTRICT;
  return BKK_DISTRICTS.includes(m[1]) ? `เขต${m[1]}` : `อ.${m[1]}`;   // Longdo also writes "อ.บางนา จ.กรุงเทพมหานคร"
}

// Both feeds in one shape, newest first
function mergeReports(traffy, longdo) {
  const rows = [];
  for (const f of longdo?.items || []) {
    rows.push({
      id: f.id, source: 'longdo', ts: f.ts, title: f.place || f.title, text: f.description,
      district: districtOf(`${f.description || ''} ${f.place || ''}`), state: f.active ? 'ยังมีน้ำท่วม' : 'สิ้นสุดแล้ว',
      by: f.credit || null, url: f.lat && f.lng ? `https://www.google.com/maps?q=${f.lat},${f.lng}` : null, urlLabel: 'ดูแผนที่',
    });
  }
  for (const r of traffy?.items || []) {
    rows.push({
      id: r.id, source: 'traffy', ts: r.ts, title: null, text: r.text,
      district: r.district ? (BKK_DISTRICTS.includes(r.district) ? `เขต${r.district}` : `อ.${r.district}`) : NO_DISTRICT,
      depth: r.depth, state: r.state, photo: r.photo,
    });
  }
  return rows.sort((a, b) => (b.ts || 0) - (a.ts || 0));
}

function ReportList({ rows, loading, updatedAt }) {
  const [query, setQuery] = useState('');
  const [district, setDistrict] = useState('');
  const [state, setState] = useState('');
  const [sort, setSort] = useState('latest');   // latest: district with the newest report first; most: most reports first
  const [open, setOpen] = useState(null);

  const districtNames = useMemo(() => [...new Set(rows.map((r) => r.district))].sort((a, b) => a.localeCompare(b, 'th')), [rows]);
  const states = useMemo(() => [...new Set(rows.map((r) => r.state).filter(Boolean))], [rows]);

  const groups = useMemo(() => {
    const q = query.trim();
    const by = {};
    for (const r of rows) {
      if (district && r.district !== district) continue;
      if (state && r.state !== state) continue;
      if (q && !`${r.title || ''} ${r.text || ''}`.includes(q)) continue;
      (by[r.district] ||= []).push(r);
    }
    const out = Object.entries(by).map(([name, list]) => ({ name, list }));
    return sort === 'latest'
      ? out.sort((a, b) => (b.list[0].ts || 0) - (a.list[0].ts || 0))
      : out.sort((a, b) => b.list.length - a.list.length || b.list[0].ts - a.list[0].ts);
  }, [rows, query, district, state, sort]);
  const shown = groups.reduce((n, g) => n + g.list.length, 0);
  const filtered = query || district || state;

  return (
    <Card className="p-5">
      <SectionHeader
        id="flood-reports"
        title="การแจ้งน้ำท่วม"
        description="จุดที่มีรายงานน้ำท่วมบนแผนที่ (iTIC / FM91 ผ่าน Longdo Traffic) และเรื่องที่ประชาชนแจ้งผ่าน Traffy Fondue 6 ชม.ล่าสุด · ยังไม่ผ่านการตรวจสอบจากเขต"
      />
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <label htmlFor="report-q" className="sr-only">ค้นหาข้อความ</label>
        <input
          id="report-q"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="ค้นหา เช่น ชื่อถนน ซอย หมู่บ้าน"
          className="h-9 flex-1 min-w-[200px] rounded-lg border border-slate-300 bg-white px-3 text-sm"
        />
        <select aria-label="เขต" value={district} onChange={(e) => setDistrict(e.target.value)} className={SELECT}>
          <option value="">ทุกเขต</option>
          {districtNames.map((d) => <option key={d} value={d}>{d}</option>)}
        </select>
        <select aria-label="เรียงลำดับ" value={sort} onChange={(e) => setSort(e.target.value)} className={SELECT}>
          <option value="latest">ล่าสุดก่อน</option>
          <option value="most">แจ้งมากสุดก่อน</option>
        </select>
        <select aria-label="สถานะ" value={state} onChange={(e) => setState(e.target.value)} className={SELECT}>
          <option value="">ทุกสถานะ</option>
          {states.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        {filtered && <Button size="sm" onClick={() => { setQuery(''); setDistrict(''); setState(''); }}>ล้าง</Button>}
      </div>
      <p className="text-xs text-slate-500 mt-2">
        แสดง {fmtNum(shown)} จาก {fmtNum(rows.length)} เรื่อง · {groups.length} เขต{updatedAt ? ` · อัปเดต ${agoTh(updatedAt)}` : ''}
      </p>

      {loading ? (
        <div className="mt-3 space-y-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-14" />)}</div>
      ) : groups.length === 0 ? (
        <EmptyState
          title={rows.length ? 'ไม่พบเรื่องที่ตรงกับตัวกรอง' : 'ไม่มีการแจ้งน้ำท่วม'}
          description={rows.length ? 'ลองเปลี่ยนคำค้นหรือเลือกทุกเขต' : 'ยังไม่มีรายงานน้ำท่วมในช่วงนี้'}
        />
      ) : (
        <div className="mt-3 grid grid-cols-1 lg:grid-cols-2 gap-3">
          {groups.map((g) => (
            <section key={g.name} className="min-w-0">
              <p className="text-xs font-semibold text-slate-700 mb-1">{g.name} · {g.list.length} เรื่อง</p>
              <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
                {(open === g.name ? g.list : g.list.slice(0, REPORTS_SHOWN)).map((r) => (
                  <li key={r.id} className="p-2.5 flex gap-3">
                    {r.photo && <img src={r.photo} alt="" loading="lazy" className="w-16 h-16 rounded-md object-cover shrink-0" />}
                    <div className="min-w-0 flex-1">
                      {r.title && <p className="text-sm font-medium text-slate-900 leading-5">{r.title}</p>}
                      {r.text && <p className={`leading-5 line-clamp-2 ${r.title ? 'text-xs text-slate-600' : 'text-sm text-slate-900'}`}>{r.text}</p>}
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mt-1 text-xs text-slate-500">
                        <Badge tone={SOURCES[r.source].tone}>{SOURCES[r.source].label}</Badge>
                        {r.ts && <span>{agoTh(r.ts)}</span>}
                        {r.depth && <span>ระดับ{r.depth}</span>}
                        {r.state && <Badge tone={STATE_TONE[r.state] || 'neutral'}>{r.state}</Badge>}
                        {r.by && <span>โดย {r.by}</span>}
                        {r.url && <a href={r.url} target="_blank" rel="noopener noreferrer" className="text-blue-700 hover:underline">{r.urlLabel}</a>}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
              {g.list.length > REPORTS_SHOWN && (
                <button type="button" onClick={() => setOpen(open === g.name ? null : g.name)} className="cursor-pointer mt-1 text-xs text-blue-700 hover:underline">
                  {open === g.name ? 'ย่อ' : `ดูอีก ${g.list.length - REPORTS_SHOWN} เรื่อง`}
                </button>
              )}
            </section>
          ))}
        </div>
      )}
    </Card>
  );
}

export default function CitizenReportsSection({ isActive }) {
  const [traffy, setTraffy] = useState(null);
  const [longdo, setLongdo] = useState(null);

  const load = useCallback(() => {
    // one feed failing must not hide the other: a failure counts as an empty list
    fetchFloodReports().then(setTraffy).catch(() => setTraffy((x) => x || { items: [] }));
    fetchLongdoFloods().then(setLongdo).catch(() => setLongdo((x) => x || { items: [] }));
  }, []);

  useEffect(() => {
    if (!isActive) return;
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [isActive, load]);

  const rows = useMemo(() => mergeReports(traffy, longdo), [traffy, longdo]);
  const updatedAt = Math.max(traffy?.updated_at || 0, longdo?.updated_at || 0) || null;

  return (
    <div className="flex flex-col gap-4">
      <ReportList rows={rows} loading={traffy === null || longdo === null} updatedAt={updatedAt} />
      <TraffyAnalysisCard isActive={isActive} />
      <TraffyHistoryCard isActive={isActive} />
    </div>
  );
}
