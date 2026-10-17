// เขตของฉัน: pick one of Bangkok's 50 districts once, then see its dust, flooding, flood reports, traffic,
// accidents, closures, events and cameras on one page. Backend: /api/district/{name}.
import { useEffect, useState } from 'react';
import { fetchDistrict, getBmaSnapshotUrl } from '../lib/api.js';
import { BKK_DISTRICTS } from '../lib/bkkDistricts.js';
import { band } from '../lib/air.js';
import { readMyDistrict, writeMyDistrict, deepestFirst, visibleCameras, CAMERA_SHOWN } from '../lib/district.js';
import { kindLabel, timeRange } from '../lib/events.js';
import { trackView } from '../lib/telemetry.js';
import { Button, Card, ErrorState, Skeleton } from './dashboard/ui.jsx';
import { PageHeader } from './dashboard/primitives.jsx';
import { fmtDateTime } from './dashboard/format.js';

const POLL_MS = 120000;
const UNKNOWN = 'ยังไม่มีข้อมูลในเขตนี้';
const SOURCE_LINE = 'ข้อมูลจาก กทม., กรมควบคุมมลพิษ, Longdo Traffic และ Traffy';
const FLOOD_WORD = { flood: 'น้ำท่วม', slight: 'น้ำท่วมเล็กน้อย' };
const TRAFFIC_TONE = { คล่องตัว: 'text-emerald-700', ชะลอตัว: 'text-amber-700', ติดขัด: 'text-red-700' };
const KNOWN = new Set(BKK_DISTRICTS);

// Dark ink, or white on the darkest dust band, so the pill stays readable
const pillText = (level) => (level === 'very_unhealthy' ? '#ffffff' : '#1a2228');

// Strips a typed เขต prefix; the name is kept only when it is one of the 50 districts
const asDistrict = (text) => {
  const name = String(text || '').trim().replace(/^เขต\s*/, '');
  return KNOWN.has(name) ? name : null;
};

function Section({ title, children }) {
  return (
    <Card className="p-4">
      <h3 className="text-[15px] font-semibold text-slate-900">{title}</h3>
      <div className="mt-3">{children}</div>
    </Card>
  );
}

const Unknown = () => <p className="text-sm text-slate-600">{UNKNOWN}</p>;
const Nothing = ({ children }) => <p className="text-sm text-slate-700">{children}</p>;

function DustCard({ air }) {
  if (air === null) return <Unknown />;
  const { color, label, level } = band(air.pm25);
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-3">
        <span className="inline-flex items-center rounded-md px-2 py-0.5 text-sm font-semibold" style={{ backgroundColor: color, color: pillText(level) }}>
          {label}
        </span>
        <span className="text-2xl font-semibold tabular-nums text-slate-900" title="ไมโครกรัมต่อลูกบาศก์เมตร">{air.pm25}</span>
      </div>
      <p className="text-xs text-slate-500">เฉลี่ยจาก {air.points} จุดวัดในเขต</p>
    </div>
  );
}

function FloodCard({ flood }) {
  if (flood === null) return <Unknown />;
  if (flood.wet === 0) return <Nothing>ไม่มีน้ำท่วมที่เครื่องวัดน้ำบนถนน {flood.sensors} จุด</Nothing>;
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm text-slate-800">น้ำท่วม {flood.wet} จุด จาก {flood.sensors} จุดวัด</p>
      <ul className="flex flex-col gap-2">
        {deepestFirst(flood.points).map((p, i) => (
          <li key={`${p.where}-${i}`} className="flex items-baseline justify-between gap-3 text-sm">
            <span className="min-w-0 text-slate-800">
              {p.where}
              {p.road && <span className="block text-xs text-slate-500">{p.road}</span>}
            </span>
            <span className="shrink-0 whitespace-nowrap text-slate-700">
              {FLOOD_WORD[p.status] || ''} {p.level_cm != null && <span className="font-semibold tabular-nums">{p.level_cm} ซม.</span>}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ReportCard({ reports }) {
  if (reports === null) return <Unknown />;
  if (reports.count === 0) return <Nothing>ไม่มีคนแจ้งใน 6 ชม.</Nothing>;
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm text-slate-800"><span className="font-semibold tabular-nums">{reports.count}</span> เรื่อง ใน 6 ชม.ที่ผ่านมา</p>
      <ul className="flex flex-col gap-2">
        {reports.latest.map((r) => (
          <li key={r.id} className="text-sm">
            <p className="text-slate-800 line-clamp-2">{r.text}</p>
            <p className="text-xs text-slate-500">{r.address && `${r.address} · `}{r.ts ? fmtDateTime(r.ts) : ''}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}

function TrafficCard({ traffic }) {
  if (traffic === null) return <Unknown />;
  return (
    <div className="flex flex-wrap items-baseline gap-3">
      <span className={`text-2xl font-semibold ${TRAFFIC_TONE[traffic.level] || 'text-slate-900'}`}>{traffic.level}</span>
      <span className="text-xs text-slate-500">คะแนน {traffic.score}</span>
    </div>
  );
}

function ListCard({ items, empty }) {
  if (items === null) return <Unknown />;
  if (!items.length) return <Nothing>{empty}</Nothing>;
  return (
    <ul className="flex flex-col gap-2">
      {items.map((it, i) => (
        <li key={`${it.title}-${i}`} className="text-sm">
          <span className="text-slate-800">{it.title || 'ไม่มีชื่อ'}</span>
          {it.meta && <span className="block text-xs text-slate-500">{it.meta}</span>}
        </li>
      ))}
    </ul>
  );
}

// Road closures plus big events, one list; the same title shows once. null when neither feed has loaded.
function closureItems(d) {
  if (d.closures === null && d.events === null) return null;
  const seen = new Set();
  const out = [];
  for (const c of d.closures || []) {
    if (seen.has(c.title)) continue;
    seen.add(c.title);
    out.push({ title: c.title, meta: kindLabel(c.kind === 'closed' ? 'closure' : c.kind) });
  }
  for (const e of d.events || []) {
    if (seen.has(e.title)) continue;
    seen.add(e.title);
    out.push({ title: e.title, meta: `${kindLabel(e.kind)} · ${timeRange(e.start, e.end)}` });
  }
  return out;
}

function CameraCard({ cams }) {
  const [all, setAll] = useState(false);
  if (cams === null) return <Unknown />;
  if (!cams.length) return <Nothing>ไม่มีกล้องในเขตนี้</Nothing>;
  const shown = visibleCameras(cams, all);
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-2">
        {shown.map((c) => (
          <figure key={c.camid} className="min-w-0 overflow-hidden rounded-lg border border-slate-200">
            <img
              src={getBmaSnapshotUrl(c.camid, false, null, false)}
              alt={c.title || c.road || 'ภาพกล้อง'}
              loading="lazy"
              className="block aspect-video w-full bg-slate-100 object-cover"
            />
            <figcaption className="truncate px-2 py-1 text-xs text-slate-700">{c.road || c.title}</figcaption>
          </figure>
        ))}
      </div>
      {cams.length > CAMERA_SHOWN && (
        <Button size="sm" variant="ghost" className="self-start" aria-expanded={all} onClick={() => setAll((v) => !v)}>
          {all ? 'ดูน้อยลง' : `ดูทั้งหมด (${cams.length})`}
        </Button>
      )}
    </div>
  );
}

export default function DistrictPage({ isActive, onNavigate }) {
  useEffect(() => trackView('district'), []);
  const [name, setName] = useState(readMyDistrict);
  const [typed, setTyped] = useState(name || '');
  const [data, setData] = useState(undefined);   // undefined = loading, object once loaded
  const [failed, setFailed] = useState(false);

  // Poll while the page is open and a district is chosen
  useEffect(() => {
    setData(undefined);
    setFailed(false);
    if (!isActive || !name) return undefined;
    let alive = true;
    const tick = () => {
      fetchDistrict(name)
        .then((d) => { if (alive) { setData(d); setFailed(false); } })
        .catch(() => alive && setFailed(true));
    };
    tick();
    const id = setInterval(tick, POLL_MS);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [isActive, name]);

  const pick = (district) => {
    writeMyDistrict(district);
    setName(district);
    setTyped(district);
  };

  const onType = (e) => {
    setTyped(e.target.value);
    const district = asDistrict(e.target.value);
    if (district && district !== name) pick(district);
  };

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="เขตของฉัน"
        description={name ? `เขต${name} · ${data?.updated_at ? `ข้อมูลล่าสุด ${fmtDateTime(data.updated_at)}` : 'กำลังโหลดข้อมูล'}` : 'เลือกเขตของคุณหนึ่งครั้ง หน้านี้จะจำไว้'}
      />

      <Card className="p-4">
        <label htmlFor="district-pick" className="text-sm font-medium text-slate-800">เลือกเขต</label>
        <input
          id="district-pick"
          type="text"
          list="district-options"
          value={typed}
          onChange={onType}
          placeholder="พิมพ์ชื่อเขต เช่น ดินแดง"
          autoComplete="off"
          className="mt-2 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900"
        />
        <datalist id="district-options">
          {BKK_DISTRICTS.map((d) => <option key={d} value={d} />)}
        </datalist>
        {typed && !asDistrict(typed) && <p className="mt-2 text-xs text-slate-500">ยังไม่พบเขตนี้ ลองเลือกจากรายการ</p>}
      </Card>

      {name && failed && !data && <ErrorState message="โหลดข้อมูลเขตไม่สำเร็จ ระบบจะลองใหม่เอง" />}

      {name && !data && !failed && (
        <div className="grid gap-4 lg:grid-cols-2">
          {Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-28" />)}
        </div>
      )}

      {name && data && (
        <div className="grid gap-4 lg:grid-cols-2 lg:items-start">
          <Section title="ฝุ่น PM2.5"><DustCard air={data.air} /></Section>
          <Section title="น้ำท่วมถนน"><FloodCard flood={data.flood} /></Section>
          <Section title="คนแจ้งน้ำท่วม (6 ชม.)"><ReportCard reports={data.reports} /></Section>
          <Section title="รถติด"><TrafficCard traffic={data.traffic} /></Section>
          <Section title="อุบัติเหตุ"><ListCard items={data.incidents === null ? null : data.incidents.map((i) => ({ title: i.title }))} empty="ไม่มีอุบัติเหตุ" /></Section>
          <Section title="ปิดถนน งานใหญ่"><ListCard items={closureItems(data)} empty="ไม่มีการปิดถนน" /></Section>
          <Section title="กล้องในเขต"><CameraCard cams={data.cameras} /></Section>
        </div>
      )}

      {name && <p className="text-xs text-slate-500">{SOURCE_LINE}</p>}
    </div>
  );
}
