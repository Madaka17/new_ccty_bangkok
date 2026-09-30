// Simple view of the น้ำเหนือ → ภาคกลาง tab, for anyone who opens it: one status line with the AI's plain
// summary, the water's journey down the Chao Phraya in six stops, the Bangkok districts to prepare, what to
// do, the roads at risk once the water arrives and the northern rivers in one line each. Every number and
// chart lives in the detail view.
import { useMemo, useState } from 'react';
import { Card, SectionHeader, Badge, Button, Segmented, Skeleton, FOCUS } from '../dashboard/ui.jsx';
import { agoText, fmtDay, fmtNum, fmtTime } from '../dashboard/format.js';
import { fullness, nowOf } from './NorthFlowExplain.jsx';

const LEVEL_TONE = { normal: 'green', watch: 'yellow', warning: 'red', critical: 'red' };
const TONE = { overflow: 'red', high: 'yellow', normal: 'green', offline: 'neutral' };
const BAR = { overflow: 'bg-red-600', high: 'bg-amber-500', normal: 'bg-emerald-600', offline: 'bg-slate-400' };
const DOT = { overflow: 'bg-red-600', high: 'bg-amber-500', normal: 'bg-emerald-600', offline: 'bg-slate-400' };
const HERO = { red: 'border-red-300 bg-red-50', yellow: 'border-amber-300 bg-amber-50', green: 'border-emerald-300 bg-emerald-50', blue: 'border-blue-300 bg-blue-50', neutral: 'border-slate-200 bg-white' };
const RANK = { overflow: 0, high: 1, normal: 2, offline: 3 };
const STOPS = [
  { code: 'C.2', name: 'นครสวรรค์' },
  { code: 'C.13', name: 'ชัยนาท', note: 'ท้ายเขื่อนเจ้าพระยา' },
  { code: 'C.3', name: 'สิงห์บุรี' },
  { code: 'C.7A', name: 'อ่างทอง' },
  { code: 'C.35', name: 'อยุธยา' },
];
const RIVERS = [
  { name: 'ปิง-วัง', codes: ['P.1', 'W.4A', 'P.7A', 'P.17'], dams: ['ภูมิพล'] },
  { name: 'ยม', codes: ['Y.4', 'Y.16'], dams: [] },
  { name: 'น่าน', codes: ['N.60', 'N.5A', 'N.7A', 'N.67'], dams: ['สิริกิติ์', 'แควน้อยบำรุงแดน'] },
  { name: 'สะแกกรัง', codes: ['Ct.19'], dams: [] },
  { name: 'ป่าสัก', codes: ['S.26'], dams: ['ป่าสักชลสิทธิ์'] },
];
const AREAS = [
  ['all', 'ทั้งหมด'],
  ['bkk', 'กรุงเทพฯ'],
  ['other', 'นนทบุรีและปริมณฑล'],
];
const FALLBACK_ACTIONS = ['ติดตามประกาศของกรมชลประทาน กรุงเทพมหานคร และสำนักงานเขต', 'น้ำท่วมหรือต้องการความช่วยเหลือ โทร 1784 (ปภ.) หรือ 1555 (กทม.)'];

const inText = (h) => (h < 36 ? `~${h} ชม.` : `~${(h / 24).toFixed(1).replace('.0', '')} วัน`);
const pctStatus = (pct) => (pct == null ? 'offline' : pct >= 100 ? 'overflow' : pct >= 70 ? 'high' : 'normal');

// Rising / steady / falling from the last hour of 10-minute data, else the last 24 h of hourly data
function trendOf(s) {
  const n = nowOf(s);
  let ch;
  let thr;
  if (n.change1h != null) {
    ch = n.change1h;
    thr = Math.max(5, 0.005 * (n.q || 0));
  } else if (s?.change_24h != null) {
    ch = s.change_24h;
    thr = Math.max(20, 0.03 * (n.q || 0));
  } else return null;
  if (ch >= thr) return { icon: '▲', text: 'กำลังเพิ่มขึ้น', cls: 'text-red-700' };
  if (ch <= -thr) return { icon: '▼', text: 'กำลังลดลง', cls: 'text-emerald-700' };
  return { icon: '●', text: 'ทรงตัว', cls: 'text-slate-600' };
}

// The worst of the Chao Phraya stops, when the model has not written a title yet
function fallbackTitle(by) {
  const main = STOPS.map((s) => by[s.code]).filter(Boolean);
  const over = main.filter((s) => (nowOf(s).pct ?? 0) >= 100);
  if (over.length) return `น้ำเหนือล้นตลิ่งแล้วที่${over.map((s) => s.province).join(' ')}`;
  const soon = main.find((s) => (s.peak?.pct ?? 0) >= 100);
  if (soon) return `คาดว่าน้ำจะล้นตลิ่งที่${soon.province} ในอีก ${inText(soon.peak.in_h)}`;
  if (main.some((s) => (nowOf(s).pct ?? 0) >= 70)) return 'น้ำเหนือมาก แต่ยังไม่ล้นตลิ่ง';
  return 'น้ำเหนือยังอยู่ในลำน้ำ ปกติ';
}

function Hero({ data, impact, by }) {
  const r = impact?.report;
  const tone = r ? LEVEL_TONE[r.level] || 'yellow' : data.headline.tone;
  const water = Math.max(0, ...(data.stations || []).map((s) => s.latest10?.t || s.ts || 0));
  return (
    <section className={`rounded-2xl border-2 p-5 sm:p-6 ${HERO[tone] || HERO.neutral}`} aria-labelledby="north-hero-title">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={tone} dot>
          {r?.status_label || data.headline.label}
        </Badge>
        <span className="text-xs text-slate-600">
          ข้อมูลน้ำ {water ? `${fmtTime(water)} น.` : '–'}
          {r ? ` · ${r.source === 'ai' ? 'สรุปโดย AI' : 'สรุปตามเกณฑ์ (AI ไม่พร้อม)'} ${agoText(r.generated_at)}` : ''}
        </span>
      </div>
      <h2 id="north-hero-title" className="mt-2 text-xl sm:text-2xl font-bold text-slate-900 leading-snug">
        {r?.title || fallbackTitle(by)}
      </h2>
      {r?.easy?.length ? (
        <ul className="mt-3 space-y-1.5">
          {r.easy.map((x, i) => (
            <li key={i} className="flex gap-2 text-[15px] leading-7 text-slate-800">
              <span className="mt-2.5 w-1.5 h-1.5 rounded-full bg-slate-500 shrink-0" aria-hidden="true" />
              <span>{x}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-slate-700 leading-6">{data.headline.text}</p>
      )}
    </section>
  );
}

function Step({ n }) {
  return <span className="shrink-0 grid place-items-center w-6 h-6 rounded-full bg-blue-600 text-white text-xs font-semibold">{n}</span>;
}

function Stop({ s, stop, n: step, selected, onSelect }) {
  const n = nowOf(s);
  const st = pctStatus(n.pct);
  const tr = trendOf(s);
  const pk = s?.peak && s.peak.q > (n.q || 0) * 1.03 ? s.peak : null;
  return (
    <button
      type="button"
      onClick={() => s && onSelect(stop.code)}
      aria-pressed={selected}
      className={`w-full text-left rounded-xl border bg-white p-3 transition-colors cursor-pointer ${FOCUS} ${selected ? 'border-blue-400 ring-1 ring-blue-400' : 'border-slate-200 hover:bg-slate-50'}`}
    >
      <div className="flex items-start gap-2">
        <Step n={step} />
        <div className="min-w-0 flex-1">
          <p className="text-base font-semibold text-slate-900 leading-6">{stop.name}</p>
          {stop.note && <p className="text-[11px] text-slate-500">{stop.note}</p>}
        </div>
        <Badge tone={TONE[st]}>{fullness(n.pct) || 'ไม่มีข้อมูล'}</Badge>
      </div>
      {n.pct != null && (
        <>
          <p className="mt-2 tabular-nums">
            <span className="text-3xl font-bold text-slate-900">{Math.round(n.pct)}%</span>
            <span className="ml-1 text-xs text-slate-600">เต็มลำน้ำ</span>
          </p>
          <div className="mt-1.5 h-2 w-full rounded-full bg-slate-100 overflow-hidden" aria-hidden="true">
            <div className={`h-full rounded-full ${BAR[st]}`} style={{ width: `${Math.min(100, n.pct)}%` }} />
          </div>
        </>
      )}
      {tr && (
        <p className={`mt-2 text-sm font-medium ${tr.cls}`}>
          {tr.icon} {tr.text}
        </p>
      )}
      <p className={`mt-1 text-xs leading-5 ${pk?.status === 'overflow' ? 'text-red-700 font-medium' : pk ? 'text-amber-700' : 'text-slate-600'}`}>
        {pk ? `คาดว่าจะขึ้นถึง ${Math.round(pk.pct)}% ในอีก ${inText(pk.in_h)}` : s?.forecast ? 'คาดว่าไม่สูงขึ้นอีกใน 4 วัน' : ''}
      </p>
      {s?.from_c2_h > 0 && <p className="mt-1 text-[11px] text-slate-500">น้ำจากนครสวรรค์ถึงที่นี่ใน {inText(s.from_c2_h)}</p>}
      {n.q != null && <p className="mt-1 text-[11px] text-slate-500 tabular-nums">{fmtNum(Math.round(n.q))} ลบ.ม./วินาที</p>}
    </button>
  );
}

function BangkokStop({ b, n: step }) {
  if (!b) return null;
  const gapNow = b.now_msl != null && b.bank != null ? b.bank - b.now_msl : null;
  const over = b.over_bank_t != null;
  const st = gapNow != null && gapNow <= 0 ? 'overflow' : over ? 'high' : 'normal';
  const cm = (m) => `${Math.round(Math.abs(m) * 100)} ซม.`;
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3">
      <div className="flex items-start gap-2">
        <Step n={step} />
        <div className="min-w-0 flex-1">
          <p className="text-base font-semibold text-slate-900 leading-6">นนทบุรี-กรุงเทพฯ</p>
          <p className="text-[11px] text-slate-500">แม่น้ำเจ้าพระยา สะพานนวลฉวี</p>
        </div>
        <Badge tone={TONE[st]}>{st === 'overflow' ? 'สูงกว่าตลิ่ง' : over ? 'คาดว่าจะล้น' : 'ต่ำกว่าตลิ่ง'}</Badge>
      </div>
      {gapNow != null && (
        <p className="mt-2 text-sm text-slate-800">
          ตอนนี้ระดับน้ำ{gapNow > 0 ? 'ต่ำกว่า' : 'สูงกว่า'}ตลิ่ง <span className="font-bold">{cm(gapNow)}</span>
        </p>
      )}
      <p className={`mt-2 text-xs leading-5 ${over ? 'text-red-700 font-medium' : 'text-slate-600'}`}>
        {over && b.bank != null
          ? `สสน. คาดว่าจะสูงกว่าตลิ่ง ${cm(b.peak_msl - b.bank)} ราว ${fmtDay(b.peak_t * 1000)}`
          : `สสน. คาดว่ายังต่ำกว่าตลิ่งใน 7 วัน (สูงสุดราว ${fmtDay(b.peak_t * 1000)})`}
      </p>
      <p className="mt-1 text-[11px] text-slate-500">ระดับน้ำช่วงนี้ขึ้นลงตามน้ำทะเลหนุนด้วย</p>
    </div>
  );
}

function Journey({ by, bangkok, code, onSelect }) {
  return (
    <Card className="p-5" aria-labelledby="north-journey-title">
      <SectionHeader
        id="north-journey-title"
        title="น้ำไหลจากนครสวรรค์ลงมาถึงกรุงเทพฯ"
        description="เรียงตามทางน้ำ 1 → 6 · เต็มลำน้ำกี่เปอร์เซ็นต์ กำลังขึ้นหรือลง และจะขึ้นถึงเท่าไร · แตะจุดเพื่อดูกราฟ"
      />
      <ol className="mt-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {STOPS.map((stop, i) => (
          <li key={stop.code}>
            <Stop s={by[stop.code]} stop={stop} n={i + 1} selected={code === stop.code} onSelect={onSelect} />
          </li>
        ))}
        <li>
          <BangkokStop b={bangkok} n={STOPS.length + 1} />
        </li>
      </ol>
    </Card>
  );
}

// One line per northern river: its worst gauge, how full, which way, and the dams that feed it
function Upstream({ by, dams }) {
  const rows = RIVERS.map((r) => {
    const worst = r.codes
      .map((c) => by[c])
      .filter((s) => s && s.status !== 'offline')
      .sort((a, b) => RANK[a.status] - RANK[b.status] || (nowOf(b).pct ?? 0) - (nowOf(a).pct ?? 0))[0];
    return { r, s: worst, dams: r.dams.map((n) => dams[n]).filter(Boolean) };
  });
  return (
    <Card className="p-5" aria-labelledby="north-upstream-title">
      <SectionHeader id="north-upstream-title" title="แม่น้ำสายหลักจากภาคเหนือ" description="จุดที่น้ำมากที่สุดของแต่ละสาย และเขื่อนที่ช่วยเก็บน้ำไว้" />
      <ul className="mt-3 divide-y divide-slate-100">
        {rows.map(({ r, s, dams: ds }) => {
          const n = nowOf(s);
          const tr = trendOf(s);
          const st = s ? (n.pct != null ? pctStatus(n.pct) : s.status) : 'offline';
          return (
            <li key={r.name} className="py-2.5 flex flex-wrap items-start gap-x-3 gap-y-1 text-sm">
              <span className={`mt-1.5 w-2.5 h-2.5 rounded-full shrink-0 ${DOT[st]}`} aria-hidden="true" />
              <span className="font-semibold text-slate-900 w-28 shrink-0">แม่น้ำ{r.name}</span>
              <span className="flex-1 min-w-[200px] text-slate-700">
                {s ? (
                  <>
                    {n.pct != null ? `${fullness(n.pct)} ที่${s.province} (เต็ม ${Math.round(n.pct)}%)` : s.status === 'overflow' ? `ล้นตลิ่งที่${s.province}` : `ที่${s.province}`}
                    {tr && <span className={`ml-2 ${tr.cls}`}>{tr.icon} {tr.text}</span>}
                  </>
                ) : (
                  'ไม่มีข้อมูล'
                )}
                {ds.length > 0 && (
                  <span className="block text-xs text-slate-500">
                    {ds.map((d) => `เขื่อน${d.name} เก็บน้ำแล้ว ${Math.round(d.storage_pct ?? 0)}%`).join(' · ')}
                  </span>
                )}
              </span>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

const DISTRICT_LEVELS = [
  ['สูง', 'เสี่ยงสูง', 'red'],
  ['ปานกลาง', 'เสี่ยงปานกลาง', 'yellow'],
  ['เฝ้าระวัง', 'เฝ้าระวัง', 'blue'],
];

function Districts({ report, onDetail }) {
  const [open, setOpen] = useState(null);
  const groups = useMemo(() => DISTRICT_LEVELS.map(([lv, label, tone]) => ({ lv, label, tone, items: (report?.districts || []).filter((d) => d.level === lv) })), [report]);
  const sel = (report?.districts || []).find((d) => d.district === open);
  return (
    <Card className="p-5" aria-labelledby="north-districts-title">
      <SectionHeader id="north-districts-title" title="กรุงเทพฯ: เขตที่ควรเตรียมตัว" description="AI ประเมินจากน้ำเหนือที่กำลังมา ระดับน้ำที่นนทบุรี และระดับคลองในแต่ละเขต · แตะชื่อเขตเพื่อดูเหตุผล" />
      {!report ? (
        <Skeleton className="h-16 mt-3" />
      ) : !report.districts?.length ? (
        <p className="mt-3 text-sm text-slate-700">ยังไม่มีเขตที่คาดว่าจะได้รับผลกระทบจากน้ำเหนือ</p>
      ) : (
        <div className="mt-3 space-y-3">
          {groups
            .filter((g) => g.items.length)
            .map((g) => (
              <div key={g.lv}>
                <p className="text-xs font-semibold text-slate-600 mb-1.5">
                  {g.label} ({g.items.length} เขต)
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {g.items.map((d) => (
                    <button
                      key={d.district}
                      type="button"
                      aria-expanded={open === d.district}
                      onClick={() => setOpen(open === d.district ? null : d.district)}
                      className={`cursor-pointer rounded-full ${FOCUS} ${open === d.district ? 'ring-2 ring-blue-500' : ''}`}
                    >
                      <Badge tone={g.tone} dot>
                        {d.district}
                      </Badge>
                    </button>
                  ))}
                </div>
              </div>
            ))}
          {sel && (
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm leading-6">
              <p className="font-semibold text-slate-900">
                เขต{sel.district} · ช่วงเวลา {sel.when}
              </p>
              <p className="text-slate-700">{sel.cause}</p>
              <p className="text-slate-800">
                <span className="font-medium">ควรทำ:</span> {sel.advice}
              </p>
            </div>
          )}
          <Button size="sm" variant="ghost" onClick={onDetail}>
            ดูเหตุผลและตัวเลขทุกเขตในข้อมูลละเอียด
          </Button>
        </div>
      )}
    </Card>
  );
}

// Roads the AI (or the rules) expects to flood once the water reaches Nonthaburi and Bangkok
export function RoadsCard({ report, onOpenRoad, expanded = false }) {
  const [area, setArea] = useState('all');
  const [all, setAll] = useState(expanded);
  const roads = (report?.roads || []).filter((r) => area === 'all' || (area === 'bkk') === (r.province === 'กรุงเทพมหานคร'));
  const shown = all ? roads : roads.slice(0, 6);
  const tone = { สูง: 'red', ปานกลาง: 'yellow', เฝ้าระวัง: 'blue' };
  return (
    <Card className="p-5" aria-labelledby="north-roads-title">
      <SectionHeader
        id="north-roads-title"
        title="ถนนเสี่ยงน้ำท่วม เมื่อน้ำเหนือมาถึงนนทบุรี-กรุงเทพฯ"
        description={report?.roads_summary || 'AI วิเคราะห์จากระดับน้ำที่คาดการณ์ จุดวัดน้ำท่วมบนถนน คลองข้างถนน และฝน'}
        action={<Segmented label="พื้นที่" value={area} onChange={setArea} options={AREAS} />}
      />
      {!report ? (
        <Skeleton className="h-24 mt-3" />
      ) : !roads.length ? (
        <p className="mt-3 text-sm text-slate-700">ยังไม่มีถนนในพื้นที่นี้ที่เข้าเกณฑ์เสี่ยงจากน้ำเหนือ</p>
      ) : (
        <ul className="mt-3 divide-y divide-slate-100">
          {shown.map((r) => (
            <li key={r.road} className="py-3">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <Badge tone={tone[r.level] || 'neutral'} dot>
                  {r.level === 'เฝ้าระวัง' ? 'เฝ้าระวัง' : `เสี่ยง${r.level}`}
                </Badge>
                {onOpenRoad && r.province === 'กรุงเทพมหานคร' ? (
                  <button type="button" onClick={() => onOpenRoad(r.road)} title="ดูกล้อง CCTV บนถนนนี้" className={`cursor-pointer text-sm font-semibold text-slate-900 hover:text-blue-700 hover:underline text-left ${FOCUS}`}>
                    {r.road}
                  </button>
                ) : (
                  <span className="text-sm font-semibold text-slate-900">{r.road}</span>
                )}
                <span className="text-xs text-slate-500">
                  {r.province === 'กรุงเทพมหานคร' ? `เขต${r.district}` : `อ.${r.district} จ.${r.province}`}
                </span>
                <span className="ml-auto text-xs font-medium text-slate-700">{r.when}</span>
              </div>
              <p className="mt-1 text-sm text-slate-700 leading-6">{r.why}</p>
              <p className="text-xs text-slate-600 leading-5">
                <span className="font-medium text-slate-800">ผู้ใช้ถนน:</span> {r.advice}
              </p>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {roads.length > 6 && (
          <Button size="sm" variant="ghost" onClick={() => setAll((v) => !v)}>
            {all ? 'แสดงน้อยลง' : `ดูทั้งหมด ${roads.length} สาย`}
          </Button>
        )}
        <span className="text-[11px] text-slate-500">
          {report?.roads_by === 'ai' ? 'วิเคราะห์โดย AI' : 'ประเมินตามเกณฑ์'} · นนทบุรีและปริมณฑลไม่มีเซ็นเซอร์วัดน้ำบนถนน ประเมินจากทำเลริมแม่น้ำ · แตะชื่อถนนใน กทม. เพื่อดูกล้อง
        </span>
      </div>
    </Card>
  );
}

const pct = (p) => `${Math.round((p || 0) * 100)}%`;
const chanceTone = (p) => (p >= 0.6 ? 'red' : p >= 0.3 ? 'yellow' : p >= 0.1 ? 'blue' : 'green');
const CHANCE_BAR = { red: 'bg-red-600', yellow: 'bg-amber-500', blue: 'bg-blue-500', green: 'bg-emerald-600' };
const dayLabel = (iso) => fmtDay(`${iso}T12:00:00`);

// Nonthaburi: the chance the Chao Phraya tops its bank at the Nonthaburi gauge in each of the next days, every
// road in the province with its chance, and per road the stretches ranked from the one that floods first
export function NonthaburiCard({ nb, report, onOpenRoad }) {
  const [mode, setMode] = useState('top'); // top 10 at risk, every road at risk, every road
  const [amphoe, setAmphoe] = useState('');
  const [open, setOpen] = useState(null);
  if (!nb) {
    return (
      <Card className="p-5">
        <Skeleton className="h-28" />
      </Card>
    );
  }
  const ch = nb.river || {};
  const top = ch.likeliest;
  const overDays = (ch.observed_peaks || []).filter((d) => d.peak >= ch.bank);
  const ai = report?.nonthaburi;
  const aiText = Object.fromEntries((ai?.roads || []).map((r) => [r.road, r.text]));
  const amphoes = [...new Set((nb.roads || []).flatMap((r) => r.amphoe || []))].sort((a, b) => a.localeCompare(b, 'th'));
  const inArea = (nb.roads || []).filter((r) => !amphoe || (r.amphoe || []).includes(amphoe));
  const risky = inArea.filter((r) => r.p >= 0.1);
  const list = mode === 'all' ? inArea : mode === 'risky' ? risky : risky.slice(0, 10);
  const c = nb.counts || {};
  const maxP = Math.max(0.01, ...(ch.days || []).map((d) => d.p));
  const RANK_LABEL = ['เสี่ยงที่สุด', 'รองลงมา', 'อันดับ 3', 'อันดับ 4', 'อันดับ 5'];
  return (
    <Card className="p-5" aria-labelledby="north-nb-title">
      <SectionHeader
        id="north-nb-title"
        title="นนทบุรี: ถนนทุกสาย ถ้าน้ำเจ้าพระยาล้นตลิ่ง ช่วงไหนท่วมก่อน"
        description={`วิเคราะห์ถนน ${nb.total} สายในจังหวัดนนทบุรี แบ่งแต่ละสายเป็นช่วงละราว ${nb.assumptions?.stretch_m || 330} ม. แล้วเรียงช่วงที่ใกล้แม่น้ำและมีโอกาสท่วมมากที่สุด`}
      />

      <div className={`mt-3 rounded-xl border p-4 ${HERO[chanceTone(ch.p7)] || HERO.neutral}`}>
        <p className="text-sm text-slate-700">โอกาสที่น้ำเจ้าพระยาที่นนทบุรี (สะพานนวลฉวี) จะสูงกว่าตลิ่งใน 7 วันนี้</p>
        <p className="mt-1 tabular-nums">
          <span className="text-3xl font-bold text-slate-900">{pct(ch.p7)}</span>
          {top && <span className="ml-2 text-sm text-slate-700">สูงสุดวันที่ {dayLabel(top.date)} (คาดระดับ {top.peak.toFixed(2)} ม. ตลิ่ง {ch.bank?.toFixed(2)} ม.)</span>}
        </p>
        <p className="mt-1 text-xs text-slate-600">
          ตอนนี้ {ch.now != null ? `${ch.now.toFixed(2)} ม.รทก.` : '–'}
          {overDays.length > 0 && ` · 7 วันที่ผ่านมา น้ำสูงกว่าตลิ่งแล้ว ${overDays.length} วัน (${overDays.map((d) => dayLabel(d.date)).join(', ')})`}
        </p>
        <ol className="mt-3 grid grid-cols-4 sm:grid-cols-8 gap-2">
          {(ch.days || []).map((d) => (
            <li key={d.date} className="flex flex-col items-center gap-1" title={`คาดระดับสูงสุด ${d.peak} ม.รทก. · ความไม่แน่นอน ±${d.sigma} ม.`}>
              <span className="text-xs font-semibold tabular-nums text-slate-900">{pct(d.p)}</span>
              <div className="h-12 w-full max-w-[40px] rounded-md bg-white/60 flex items-end overflow-hidden" aria-hidden="true">
                <div className={`w-full ${CHANCE_BAR[chanceTone(d.p)]}`} style={{ height: `${Math.max(4, (d.p / maxP) * 100)}%` }} />
              </div>
              <span className="text-[11px] text-slate-600">{d.lead === 0 ? 'วันนี้' : dayLabel(d.date)}</span>
            </li>
          ))}
        </ol>
      </div>

      <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
        {[
          ['สูง', 'เสี่ยงสูง ≥60%', 'red'],
          ['ปานกลาง', 'ปานกลาง 30-59%', 'yellow'],
          ['เฝ้าระวัง', 'เฝ้าระวัง 10-29%', 'blue'],
          ['ต่ำ', 'ต่ำ <10% / ไกลแม่น้ำ', 'green'],
        ].map(([k, label, tone]) => (
          <div key={k} className="rounded-lg border border-slate-200 px-2 py-2">
            <p className="text-2xl font-bold tabular-nums text-slate-900">{c[k] ?? 0}</p>
            <p className="text-[11px] text-slate-600 inline-flex items-center gap-1">
              <span className={`w-2 h-2 rounded-full ${CHANCE_BAR[tone]}`} />
              {label}
            </p>
          </div>
        ))}
      </div>

      {ai?.summary && (
        <p className="mt-3 text-sm text-slate-800 leading-6">
          <span className="font-semibold text-blue-700">{ai.by === 'ai' ? 'AI:' : 'สรุป:'}</span> {ai.summary}
        </p>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <label className="text-xs text-slate-600" htmlFor="nb-amphoe">
          อำเภอ
        </label>
        <select
          id="nb-amphoe"
          value={amphoe}
          onChange={(e) => setAmphoe(e.target.value)}
          className={`h-8 rounded-lg border border-slate-300 bg-white px-2 text-xs text-slate-800 ${FOCUS}`}
        >
          <option value="">ทุกอำเภอ</option>
          {amphoes.map((a) => (
            <option key={a} value={a}>
              {a}
            </option>
          ))}
        </select>
        <span className="text-xs text-slate-500">
          ถนนเสี่ยง {risky.length} จาก {inArea.length} สาย · แตะชื่อถนนเพื่อดูว่าช่วงไหนเสี่ยงที่สุดและรองลงมา
        </span>
      </div>

      <ul className="mt-2 divide-y divide-slate-100">
        {list.map((r) => {
          const t = chanceTone(r.p);
          const isOpen = open === r.road;
          return (
            <li key={r.road} className="py-2">
              <button
                type="button"
                onClick={() => setOpen(isOpen ? null : r.road)}
                aria-expanded={isOpen}
                className={`w-full text-left flex flex-wrap items-center gap-x-3 gap-y-1 cursor-pointer rounded-md ${FOCUS}`}
              >
                <span className="text-slate-400 text-xs w-3" aria-hidden="true">
                  {isOpen ? '▾' : '▸'}
                </span>
                <span className="text-sm font-semibold text-slate-900">{r.road}</span>
                <span className="text-xs text-slate-500">{(r.amphoe || []).map((a) => `อ.${a}`).join(' ')}</span>
                <span className="ml-auto flex items-center gap-2 w-44">
                  <span className="h-2 flex-1 rounded-full bg-slate-100 overflow-hidden" aria-hidden="true">
                    <span className={`block h-full ${CHANCE_BAR[t]}`} style={{ width: pct(r.p) }} />
                  </span>
                  <span className="text-sm font-semibold tabular-nums text-slate-900 w-10 text-right">{pct(r.p)}</span>
                </span>
              </button>
              {!isOpen && r.p >= 0.1 && r.stretches?.[0] && (
                <p className="mt-0.5 pl-6 text-xs text-slate-600">
                  เสี่ยงที่สุด: {r.stretches[0].place} · ห่างแม่น้ำ {Math.round(r.stretches[0].km * 1000)} ม.
                </p>
              )}
              {!isOpen && r.p < 0.1 && (
                <p className="mt-0.5 pl-6 text-xs text-slate-500">
                  {r.km == null ? 'ทุกช่วงห่างแม่น้ำเกิน 2 กม. น้ำล้นตลิ่งอย่างเดียวไม่น่าถึง' : `ช่วงที่ใกล้ที่สุดห่างแม่น้ำ ${Math.round(r.km * 1000)} ม.`}
                </p>
              )}
              {isOpen && (
                <div className="mt-2 pl-6">
                  {aiText[r.road] && (
                    <p className="text-xs text-slate-700 leading-5 mb-2">
                      <span className="font-semibold text-blue-700">AI:</span> {aiText[r.road]}
                    </p>
                  )}
                  <ol className="space-y-1.5">
                    {(r.stretches || []).map((s, i) => (
                      <li key={i} className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs">
                        <span className={`shrink-0 grid place-items-center w-5 h-5 rounded-full text-white text-[10px] font-semibold ${CHANCE_BAR[chanceTone(s.p)]}`}>{i + 1}</span>
                        <span className="font-medium text-slate-800">{RANK_LABEL[i]}</span>
                        <span className="text-slate-700">{s.place}</span>
                        <span className="text-slate-500">{s.km != null ? `ห่างแม่น้ำ ${Math.round(s.km * 1000).toLocaleString('th-TH')} ม.` : 'ห่างแม่น้ำเกิน 2 กม.'}</span>
                        <span className="ml-auto font-semibold tabular-nums text-slate-900">{pct(s.p)}</span>
                      </li>
                    ))}
                  </ol>
                  <p className="mt-1.5 text-[11px] text-slate-500">
                    ช่วงที่มีโอกาส 10% ขึ้นไป {r.stretches_at_risk} จาก {r.stretches_total} ช่วง
                    {onOpenRoad && (
                      <>
                        {' · '}
                        <button type="button" onClick={() => onOpenRoad(r.road)} className={`underline text-blue-700 cursor-pointer ${FOCUS}`}>
                          ดูกล้องใกล้ถนนนี้
                        </button>
                      </>
                    )}
                  </p>
                </div>
              )}
            </li>
          );
        })}
      </ul>
      <div className="mt-1 flex flex-wrap gap-2">
        {mode === 'top' && risky.length > 10 && (
          <Button size="sm" variant="ghost" onClick={() => setMode('risky')}>
            ดูถนนเสี่ยงทั้งหมด {risky.length} สาย
          </Button>
        )}
        {mode !== 'all' ? (
          <Button size="sm" variant="ghost" onClick={() => setMode('all')}>
            แสดงถนนทั้งหมด {inArea.length} สาย รวมสายที่เสี่ยงต่ำ
          </Button>
        ) : (
          <Button size="sm" variant="ghost" onClick={() => setMode('top')}>
            แสดงเฉพาะ 10 สายที่เสี่ยงที่สุด
          </Button>
        )}
      </div>

      <p className="mt-3 text-[11px] text-slate-500 leading-5">
        วิธีคิด: โอกาสรายวัน = ความน่าจะเป็นที่ระดับน้ำสูงสุดของวันจะเกินตลิ่ง โดยให้ค่าจริงกระจายรอบค่าคาดการณ์ของ สสน. ตามความคลาดเคลื่อน
        ({ch.sigma_source === 'hii' ? 'จากประวัติการคาดการณ์ของ สสน. ที่ระบบเก็บไว้' : 'ยังเก็บประวัติคาดการณ์ไม่พอ ใช้การเปลี่ยนแปลงของระดับน้ำสูงสุดรายวันจริง 30 วัน ซึ่งกว้างกว่าจริง จึงเผื่อไว้ก่อน'})
        · ภาพรวม 7 วันใช้วันที่โอกาสสูงสุด · แต่ละช่วงถนน = โอกาสภาพรวม × น้ำหนักตามระยะจากแม่น้ำ (≤200 ม. ×1, ≤500 ม. ×0.6, ≤1 กม. ×0.3, ≤2 กม. ×0.1) เป็นสมมติฐาน
        เพราะไม่มีข้อมูลความสูงถนนและแนวกั้นน้ำ ตลิ่งที่ใช้เป็นของสถานีวัด ไม่ใช่ของแต่ละจุด และไม่รวมน้ำท่วมจากฝนหรือคลอง · แนวแม่น้ำและเขตตำบล/อำเภอ © OpenStreetMap contributors (ODbL)
      </p>
    </Card>
  );
}

function Actions({ report }) {
  const items = report?.actions?.length ? report.actions : FALLBACK_ACTIONS;
  return (
    <Card className="p-5" aria-labelledby="north-actions-title">
      <SectionHeader id="north-actions-title" title="ควรทำอะไรตอนนี้" />
      <ol className="mt-3 space-y-2">
        {items.map((x, i) => (
          <li key={i} className="flex gap-3 text-sm leading-6 text-slate-800">
            <span className="shrink-0 grid place-items-center w-6 h-6 rounded-full bg-blue-600 text-white text-xs font-semibold">{i + 1}</span>
            <span>{x}</span>
          </li>
        ))}
      </ol>
    </Card>
  );
}

export default function NorthFlowSimple({ data, impact, nb, by, dams, code, onSelect, onDetail, onOpenRoad }) {
  const r = impact?.report;
  return (
    <div className="flex flex-col gap-4">
      <Hero data={data} impact={impact} by={by} />
      <Journey by={by} bangkok={data.bangkok} code={code} onSelect={onSelect} />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Districts report={r} onDetail={onDetail} />
        <Actions report={r} />
      </div>
      <RoadsCard report={r} onOpenRoad={onOpenRoad} />
      <NonthaburiCard nb={nb} report={r} onOpenRoad={onOpenRoad} />
      <Upstream by={by} dams={dams} />
    </div>
  );
}
