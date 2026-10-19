import { useEffect, useState } from 'react';

const WEATHER_POLL_MS = 600000;
import { fetchWaterSummary, fetchAirStations, fetchFloodReports, fetchWeatherNow } from '../../lib/api.js';
import { flowLevel, fmtTime } from './format.js';
import { bkkAverage } from '../../lib/air.js';
import { cityVerdict } from '../../lib/cityVerdict.js';
import { incidentCheck, waterCheck, waterReportCount } from '../../lib/cityChecks.js';
import { freshness, FRESH_LIMIT } from '../../lib/freshness.js';

// One glance, six answers: traffic / weather where the viewer is / rain-water / flood reports / dust / incidents.
// Shown as a status panel on top (verdict + one plain sentence + ask AI), then on a wide screen the six checks as
// the stages of one pipeline, on a phone one list of rows with the ones that need care first.
// Every answer is a link to its page.
// tone: green = fine, yellow = watch, red = act, neutral = no data (colours: .tone-* in index.css).
// `known` = the answer has data. An answer without data is never counted as fine: the summary says the data is
// not all in yet instead of "ออกได้", while a danger already known is shown at once (rules in lib/cityVerdict.js).

const TONE_LABEL = { green: 'ปกติ', yellow: 'เฝ้าดู', red: 'ควรระวัง', neutral: 'รอข้อมูล' };

export default function CityStatusStrip({ summary, bkkFlow, trafficAt, incidents, flood, avoid, onNavigate, onIncidents, onAskText, isActive, emergency }) {
  const [water, setWater] = useState(null);
  const [air, setAir] = useState(null);
  const [traffy, setTraffy] = useState(null);
  const [traffyFailed, setTraffyFailed] = useState(false);   // this page's last request for the reports failed
  const [weather, setWeather] = useState(null);   // { temp, code, rain, place }

  useEffect(() => {
    if (!isActive) return;
    let alive = true;
    const tick = () => {
      fetchWaterSummary().then((w) => alive && setWater(w)).catch(() => {});
      fetchAirStations().then((a) => alive && setAir(a)).catch(() => {});
    };
    // flood reports move faster than the rest: every minute
    const reports = () => {
      fetchFloodReports()
        .then((r) => {
          if (!alive) return;
          setTraffy(r);
          setTraffyFailed(false);
        })
        .catch(() => alive && setTraffyFailed(true));
    };
    tick();
    reports();
    const id = setInterval(tick, 300000);
    const rid = setInterval(reports, 60000);
    return () => {
      alive = false;
      clearInterval(id);
      clearInterval(rid);
    };
  }, [isActive]);

  // Weather now at the viewer's location (/api/weather/now, MET Norway via the server). Bangkok centre first;
  // the browser's position is read only if the viewer taps ใช้ตำแหน่งของฉัน, or silently when location is already granted
  const [locateTries, setLocateTries] = useState(0);   // +1 on each tap, so every tap runs the request again
  const [geoDenied, setGeoDenied] = useState(false);
  useEffect(() => {
    if (!isActive) return;
    let alive = true;
    let spot = null;
    const load = () => {
      fetchWeatherNow(spot?.lat, spot?.lng)
        .then((d) => alive && setWeather({ ...d, mine: !!spot }))
        .catch(() => {});
    };
    const locate = () => {
      navigator.geolocation?.getCurrentPosition(
        (p) => { if (!alive) return; spot = { lat: p.coords.latitude.toFixed(2), lng: p.coords.longitude.toFixed(2) }; load(); },
        (err) => { if (alive && err?.code === 1) setGeoDenied(true); },   // 1 = PERMISSION_DENIED
        { timeout: 8000, maximumAge: 600000 },
      );
    };
    load();   // Bangkok now; the viewer's own spot replaces it when located
    let status = null;   // the geolocation PermissionStatus, watched for changes
    if (locateTries > 0) locate();   // a tap asks now
    // Older browsers have no Permissions API: then nothing is read silently and the button shows
    let perm = null;
    try { perm = navigator.permissions?.query?.({ name: 'geolocation' }); } catch { perm = null; }
    perm?.then((r) => {
      if (!alive) return;
      status = r;
      let first = true;
      const apply = () => {
        if (!alive) return;
        setGeoDenied(r.state === 'denied');
        // granted: read silently, except right after a tap, which is already asking
        if (r.state === 'granted' && !(first && locateTries > 0)) locate();
        first = false;
      };
      apply();
      // Allowed (or reset) later in the browser settings: follow it without a reload
      r.onchange = apply;
    }).catch(() => {});
    const id = setInterval(load, WEATHER_POLL_MS);
    return () => {
      alive = false;
      clearInterval(id);
      if (status) status.onchange = null;
    };
  }, [isActive, locateTries]);
  const showLocate = !!weather && !weather.mine;   // the viewer's own spot is not in use yet
  const askLocation = () => setLocateTries((n) => n + 1);
  const locateHint = <LocateHint onAsk={askLocation} denied={geoDenied} />;
  const weatherStatus = !weather ? 'กำลังโหลด' : `${Math.round(weather.temp)}°C ${weather.text}`;

  // Traffic: Bangkok's score from every road with a colour on the map (traffic/areas, ~3,300 km), the same figure
  // as Bangkok on the traffic panel; the main-roads summary (68 roads) only stands in until it has loaded
  const flow = bkkFlow ?? summary?.flow_index;
  const level = flowLevel(flow);
  const trafficTone = level.key;
  const trafficStatus = flow == null ? 'กำลังโหลด' : level.label;

  // Rain and water in Bangkok (lib/cityChecks.js: what counts, and what is only named as ปริมณฑล)
  const wc = waterCheck(water, flood);
  const { flooding } = wc;

  // Flood reports: people on Traffy Fondue in the last 6 h who say the water is there now. Aid requests for a past
  // flood and drain complaints are left out (the server's report_kind). Flooded roads from traffic news are not
  // people's reports and stay out of it. Until Traffy has answered once there is no count: "no reports" would be a
  // wrong all-clear. After that a failed update keeps the old count, marked as old.
  const citizen = waterReportCount(traffy);
  const repFailed = !!traffy?.error || traffyFailed;
  // People's reports are a reason to look, never a reason to stay home: at most "watch"
  const repTone = citizen == null ? 'neutral' : citizen === 0 ? 'green' : 'yellow';
  const repStatus = citizen != null ? (citizen === 0 ? 'ไม่มีคนแจ้ง' : `${citizen} เรื่อง`) : repFailed ? 'ยังโหลดไม่ได้' : 'กำลังโหลด';
  const repNote = citizen != null && repFailed ? `อัปเดตไม่สำเร็จ · ข้อมูล ${fmtTime(traffy.updated_at)}\u00a0น.` : null;

  // Air
  // Bangkok's own stations, the same figure as the headline on the PM2.5 page
  const pm = bkkAverage(air?.items)?.pm25 ?? null;
  const airTone = pm == null ? 'neutral' : pm <= 25 ? 'green' : pm <= 37.5 ? 'yellow' : 'red';
  const airStatus = pm == null ? 'กำลังโหลด' : pm <= 15 ? 'อากาศดีมาก' : pm <= 25 ? 'อากาศดี' : pm <= 37.5 ? 'ปานกลาง' : pm <= 75 ? 'เริ่มมีผลต่อสุขภาพ' : 'มีผลต่อสุขภาพ';

  // Accidents and breakdowns, counted apart (lib/cityChecks.js)
  const inc = incidentCheck(incidents);

  // Roads first (what a trip needs), then water, then the weather and the air
  const items = [
    { id: 'traffic', q: 'รถติดไหม', a: trafficStatus, say: `รถ${level.label}`, tone: trafficTone, known: flow != null, at: trafficAt, limit: FRESH_LIMIT.traffic, go: () => onNavigate('map') },
    { id: 'incident', q: 'มีเหตุบนถนนไหม', a: inc.status, say: inc.total ? inc.status : 'ไม่มีอุบัติเหตุ', tone: inc.tone, known: inc.known, at: incidents?.updated, limit: FRESH_LIMIT.incident, go: () => (onIncidents ? onIncidents() : onNavigate('dashboard')) },
    { id: 'water', q: 'ฝนและน้ำ', a: wc.status, say: wc.status, tone: wc.tone, known: wc.known, at: water?.updated_at || flood?.updated_at, limit: FRESH_LIMIT.water, go: () => onNavigate('water') },
    { id: 'report', q: 'มีคนแจ้งว่าน้ำท่วมไหม', sub: 'ใน 6 ชม.', a: repStatus, say: `คนแจ้งว่าน้ำท่วม ${repStatus}`, note: repNote, tone: repTone, known: citizen != null, at: traffy?.updated_at, limit: FRESH_LIMIT.report, go: () => onNavigate('water') },
    { id: 'weather', q: weather?.mine ? 'อากาศตรงนี้' : 'อากาศ กทม.', a: weatherStatus, say: weatherStatus, tone: weather?.tone || 'neutral', known: !!weather, at: weather?.updated_at, limit: FRESH_LIMIT.weather, go: () => onNavigate('water') },
    { id: 'air', q: 'ฝุ่น PM2.5', a: pm == null ? airStatus : `${pm} · ${bkkAverage(air?.items).label}`, say: `ฝุ่น PM2.5 ${pm ?? ''} ${airStatus}`, tone: airTone, known: pm != null, at: air?.source_ts || air?.updated_at, limit: FRESH_LIMIT.air, go: () => onNavigate('air') },
  ];
  // The summary: one answer word and one sentence, made from the six answers (rules, no AI: lib/cityVerdict.js)
  const { care, calm, pending, ...verdict } = cityVerdict({ items, trafficTone, flooding, avoid: avoid || [] });
  const { headline, detail } = verdict;

  // Phones read the checks as one list, the ones that need care first; wide screens keep the fixed pipeline order
  const ranked = [...care, ...calm, ...pending];
  const counts = [
    care.length ? `ระวัง ${care.length}` : null,
    calm.length ? `ปกติ ${calm.length}` : null,
    pending.length ? `รอข้อมูล ${pending.length}` : null,
  ].filter(Boolean).join(' · ');

  return (
    <>
      <CityHero verdict={verdict} headline={headline} detail={detail} onAskText={onAskText} emergency={emergency} />

      {/* wide screens: the six checks as the stages of one pipeline, in a fixed order. The seam between two stages is
          solid when both have data, dashed while one is still waiting. The glyph's shape names the tone, so colour
          is never the only sign. */}
      <section aria-labelledby="city-now" className="hidden md:block rounded-lg border border-[var(--c-border)] bg-[var(--c-surface)]">
        <div className="flex flex-wrap items-center justify-between gap-2 px-5 py-1.5 min-h-12 border-b border-[var(--c-border)]">
          <h2 id="city-now" className="panel-label">เช็กก่อนออก 6 เรื่อง</h2>
          <div className="flex items-center gap-3">
            <p className="text-xs text-[var(--c-muted)]">{counts} · แตะเพื่อดูรายละเอียด</p>
            {showLocate && locateHint}
          </div>
        </div>
        <ol className="grid grid-cols-3 xl:grid-cols-6 gap-4 p-5">
          {items.map((i, idx) => {
            const next = items[idx + 1];
            const solid = items.slice(0, idx + 2).every((x) => x.known);   // every check up to the next one has data
            const md = idx % 3 !== 2;
            const xl = idx < items.length - 1;
            return (
              <li key={i.id} className={`tone-${i.tone} relative flex flex-col`}>
                <button
                  type="button"
                  onClick={i.go}
                  className="group cursor-pointer w-full h-full flex-1 rounded-md border border-[var(--c-border)] bg-[var(--c-raised)] px-3.5 py-3 flex flex-col gap-1.5 text-left transition-colors duration-150 hover:border-[var(--t-ring)] focus-visible:outline-2 focus-visible:outline-[var(--t-ring)]"
                >
                  <span className="flex items-start gap-2 min-w-0">
                    <StateGlyph tone={i.tone} known={i.known} className="w-[18px] h-[18px] shrink-0 mt-0.5" />
                    <span className="text-sm leading-snug text-[var(--c-muted)]">
                      {i.q}
                      {i.sub && <span className="text-xs"> · {i.sub}</span>}
                    </span>
                  </span>
                  <span className="text-lg font-bold leading-snug text-[var(--t-text)]">{i.a}</span>
                  <span className="text-xs text-[var(--t-text)]">
                    {TONE_LABEL[i.tone]}
                    <Fresh at={i.at} limit={i.limit} />
                  </span>
                  {i.note && <span className="text-xs text-[var(--watch-text)]">{i.note}</span>}
                </button>
                {next && (
                  <span
                    aria-hidden="true"
                    className={`hidden ${md ? 'md:block' : ''} ${xl ? 'xl:block' : 'xl:hidden'} absolute top-[22px] -right-4 w-4 border-t border-[var(--c-border-strong)] ${solid ? 'border-solid' : 'border-dashed'}`}
                  >
                    {solid && <span className="seam-fill block -mt-px h-px bg-[var(--c-muted)]" style={{ animationDelay: `${idx * 70}ms` }} />}
                  </span>
                )}
              </li>
            );
          })}
        </ol>
      </section>

      {/* phones: one panel of rows, the ones that need care first */}
      <section aria-labelledby="city-now-m" className="md:hidden rounded-lg border border-[var(--c-border)] bg-[var(--c-surface)] overflow-hidden">
        <div className="flex items-baseline justify-between gap-2 px-4 py-2.5 border-b border-[var(--c-border)]">
          <h2 id="city-now-m" className="panel-label">เช็กก่อนออก 6 เรื่อง</h2>
          <p className="text-xs text-[var(--c-muted)]">{counts}</p>
        </div>
        <ul className="divide-y divide-[var(--c-border)]">
          {ranked.map((i) => {
            const big = care.includes(i);
            return (
              <li key={i.id}>
                <button type="button" onClick={i.go} className={`tone-${i.tone} cursor-pointer w-full min-h-14 px-4 py-2.5 flex items-center gap-3 text-left hover:bg-[var(--c-raised)]`}>
                  <StateGlyph tone={i.tone} known={i.known} className="w-5 h-5 shrink-0" />
                  <span className="flex-1 min-w-0 text-[15px] text-[var(--c-muted)]">
                    {i.q}
                    {i.sub && <span className="text-xs"> ({i.sub})</span>}
                  </span>
                  <span className="text-right min-w-0 max-w-[55%]">
                    <span className={`block font-bold leading-snug text-[var(--t-text)] ${big ? 'text-lg' : 'text-base'}`}>{i.a}</span>
                    <span className="block text-xs"><Fresh at={i.at} limit={i.limit} lead="" /></span>
                    {i.note && <span className="block text-xs text-[var(--watch-text)]">{i.note}</span>}
                  </span>
                  <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-3.5 h-3.5 shrink-0 text-[var(--c-muted)]" aria-hidden="true">
                    <path d="M6 4l4 4-4 4" />
                  </svg>
                </button>
                {i.id === 'weather' && showLocate && <div className="px-4 pb-2 -mt-1">{locateHint}</div>}
              </li>
            );
          })}
        </ul>
        {onAskText && (
          <div className="px-4 pt-1 pb-4 border-t border-[var(--c-border)]">
            <AskForm id="city-ask-m" onAskText={onAskText} />
          </div>
        )}
      </section>
    </>
  );
}

// How old a check's data is: muted while fresh, in the watch colour once older than its source should be
function Fresh({ at, limit, lead = ' · ' }) {
  const f = freshness(at, limit);
  if (!f) return null;
  return (
    <span className={f.stale ? 'text-[var(--watch-text)] font-semibold' : 'text-[var(--c-muted)] font-normal'}>
      {lead}{f.stale ? `ข้อมูลเก่า ${f.text}` : f.text}
    </span>
  );
}

// The state of one check as a shape, in its tone's colour: a tick (fine), a half-filled ring (keep an eye on it),
// a warning triangle (take care), a dashed ring (no data yet)
function StateGlyph({ tone, known, className = '' }) {
  const shape = !known || tone === 'neutral' ? 'none' : tone;
  return (
    <svg viewBox="0 0 20 20" fill="none" className={`${className} text-[var(--t-ring)]`} aria-hidden="true">
      {shape === 'green' && (
        <>
          <circle cx="10" cy="10" r="8.25" stroke="currentColor" strokeWidth="1.5" />
          <path d="M6.5 10.2l2.4 2.4 4.6-5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </>
      )}
      {shape === 'yellow' && (
        <>
          <circle cx="10" cy="10" r="8.25" stroke="currentColor" strokeWidth="1.5" />
          <path d="M10 3.75a6.25 6.25 0 0 1 0 12.5z" fill="currentColor" />
        </>
      )}
      {shape === 'red' && (
        <>
          <path d="M8.6 2.9 1.9 14.6a1.6 1.6 0 0 0 1.4 2.4h13.4a1.6 1.6 0 0 0 1.4-2.4L11.4 2.9a1.6 1.6 0 0 0-2.8 0z" fill="currentColor" />
          <path d="M10 7.5v3.6M10 13.9h.01" stroke="var(--c-surface)" strokeWidth="1.8" strokeLinecap="round" />
        </>
      )}
      {shape === 'none' && <circle cx="10" cy="10" r="8.25" stroke="currentColor" strokeWidth="1.5" strokeDasharray="3 2.5" />}
    </svg>
  );
}

// Under the weather answer, when it is Bangkok's and not the viewer's: asks for the position on tap
function LocateHint({ onAsk, denied }) {
  if (denied) return <p className="self-start min-h-11 flex items-center text-xs text-[var(--c-muted)]">เปิดสิทธิ์ตำแหน่งในเบราว์เซอร์ก่อน</p>;
  return (
    <button type="button" onClick={onAsk} className="cursor-pointer self-start min-h-11 flex items-center text-xs font-semibold text-[var(--c-ink)] underline underline-offset-2">
      ใช้ตำแหน่งของฉัน
    </button>
  );
}

// The summary as the console's status panel: the verdict with its glyph and the emergency button beside it, one
// plain sentence, the detail, and on wide screens a box to ask AI about a road (phones get it under the checks)
function CityHero({ verdict, headline, detail, onAskText, emergency }) {
  return (
    <section aria-labelledby="city-verdict" className={`tone-${verdict.tone} rounded-lg border border-[var(--c-border)] bg-[var(--c-surface)]`}>
      <div className="px-5 sm:px-6 pt-5 pb-5 flex flex-col gap-2">
        {/* the emergency button drops under the answer when a narrow phone has no room beside it */}
        <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
          <h2 id="city-verdict" className="min-w-0 inline-flex items-center gap-2.5 text-[28px] sm:text-[36px] font-bold leading-tight text-[var(--t-text)]">
            <span className="sr-only">ตอนนี้ออกไปได้ไหม: </span>
            <StateGlyph tone={verdict.tone} known={verdict.tone !== 'neutral'} className="w-7 h-7 sm:w-8 sm:h-8 shrink-0" />
            {/* breaks only between words ("ออกได้ / แต่ระวัง"), never inside one */}
            <span className="text-balance">
              {verdict.label.split(' ').map((w, k) => <span key={k} className="whitespace-nowrap">{k ? ' ' : ''}{w}</span>)}
            </span>
          </h2>
          {emergency}
        </div>
        <p className="text-xl sm:text-2xl font-semibold leading-snug max-w-[30em] text-balance">{headline}</p>
        {detail && <p className="text-[15px] leading-relaxed text-[var(--c-muted)] max-w-[48em]">{detail}</p>}
        {onAskText && (
          <div className="hidden md:block mt-3 pt-4 border-t border-[var(--c-border)]">
            <AskForm id="city-ask" onAskText={onAskText} />
          </div>
        )}
      </div>
    </section>
  );
}

function AskForm({ id, onAskText }) {
  const [q, setQ] = useState('');
  return (
    <form
      className="flex flex-wrap gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        const text = q.trim();
        if (text) onAskText(text);
      }}
    >
      <label htmlFor={id} className="basis-full text-sm font-semibold pt-2">ถาม AI เรื่องถนนที่จะไป</label>
      <input
        id={id}
        type="text"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="เช่น ลาดพร้าวตอนนี้ติดไหม"
        className="flex-[1_1_160px] min-w-0 h-11 px-3.5 rounded-md bg-[var(--c-ground)] border border-[var(--c-border-strong)] text-base text-[var(--c-ink)] placeholder:text-[var(--c-muted)] focus:outline-none focus:border-[var(--c-primary)] focus:ring-2 focus:ring-[var(--c-primary-tint)]"
      />
      <button type="submit" className="cursor-pointer h-11 px-5 rounded-md bg-[var(--c-primary-fill)] text-[var(--c-on-primary)] text-base font-semibold hover:bg-[var(--c-primary-hover)] transition-colors duration-150">
        ถาม
      </button>
    </form>
  );
}
