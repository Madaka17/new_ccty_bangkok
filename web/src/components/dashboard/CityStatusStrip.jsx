import { useEffect, useState } from 'react';

const WEATHER_POLL_MS = 600000;
import { fetchWaterSummary, fetchAirStations, fetchFloodReports, fetchWeatherNow } from '../../lib/api.js';
import { flowLevel, fmtTime } from './format.js';

// One glance, six answers: traffic / weather where the viewer is / rain-water / flood reports / dust / incidents.
// Shown three ways: a summary sign on top (verdict band + one plain sentence + ask AI), then on a wide screen a
// "station line" (one dot per answer, the same rail look as the menu), on a phone question cards with the ones
// that need care first. Every answer is a link to its page.
// tone: green = fine, yellow = watch, red = act, neutral = no data (colours: .tone-* in index.css).
// `known` = the answer has data. An answer without data is never counted as fine: the summary says the data is
// not all in yet instead of "ปกติ", while a danger already known is shown at once.

const ICONS = {
  traffic: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-full h-full">
      <path d="M5 17h14M5 12h14M5 7h14" />
    </svg>
  ),
  water: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-full h-full">
      <path d="M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z" />
    </svg>
  ),
  air: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-full h-full">
      <path d="M3 8h11a3 3 0 1 0-3-3M3 14h14a3 3 0 1 1-3 3M3 11h7" />
    </svg>
  ),
  weather: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-full h-full">
      <path d="M7 18a4 4 0 1 1 .9-7.9A5 5 0 0 1 17.6 11 3.5 3.5 0 1 1 17.5 18H7z" />
    </svg>
  ),
  report: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-full h-full">
      <path d="M4 5h16v11H8l-4 4V5zM12 8v4M12 14.5h.01" />
    </svg>
  ),
  incident: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-full h-full">
      <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01" />
    </svg>
  ),
};

export default function CityStatusStrip({ summary, incidents, flood, avoid, onNavigate, onIncidents, onAskText, isActive }) {
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

  // Weather now at the viewer's location (/api/weather/now, MET Norway via the server); Bangkok centre until
  // the browser allows location, or if it never does
  useEffect(() => {
    if (!isActive) return;
    let alive = true;
    let spot = null;
    const load = () => {
      fetchWeatherNow(spot?.lat, spot?.lng)
        .then((d) => alive && setWeather({ ...d, mine: !!spot }))
        .catch(() => {});
    };
    load();   // Bangkok now; the viewer's own spot replaces it once the browser allows location
    navigator.geolocation?.getCurrentPosition(
      (p) => { spot = { lat: p.coords.latitude.toFixed(2), lng: p.coords.longitude.toFixed(2) }; load(); },
      () => {},
      { timeout: 8000, maximumAge: 600000 },
    );
    const id = setInterval(load, WEATHER_POLL_MS);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [isActive]);
  const weatherStatus = !weather ? 'กำลังโหลด' : `${Math.round(weather.temp)}°C ${weather.text}`;

  // Traffic
  const flow = summary?.flow_index;
  const level = flowLevel(flow);
  const trafficTone = level.key;
  const trafficStatus = flow == null ? 'กำลังโหลด' : level.label;

  // Rain + water. Flooded-road counts come from the BMA drainage sensors (flood_service.py, ~250
  // stations); ThaiWater relays only about 107 of them, so it is the fallback.
  const roads = water?.flood_roads;
  const flooding = flood
    ? (flood.counts?.flood || 0) + (flood.counts?.slight || 0)
    : (roads?.flooding || 0) + (roads?.slight || 0);
  const overflow = water?.river_counts?.overflow || 0;
  const heavyRain = (water?.ntw?.rain_counts?.heavy || 0) + (water?.ntw?.rain_counts?.extreme || 0);
  const worstZone = water?.weather?.[0];
  const waterTone = flooding > 0 || worstZone?.watch === 'red' ? 'red' : !water ? 'neutral' : heavyRain > 0 || overflow > 0 || worstZone?.watch === 'yellow' ? 'yellow' : 'green';
  const waterStatus = flooding > 0 ? `ถนนน้ำท่วม ${flooding} จุด` : !water ? 'กำลังโหลด' : worstZone?.watch === 'red' ? `เฝ้าระวัง ${worstZone.name}` : overflow > 0 ? `น้ำล้นตลิ่ง ${overflow} จุด` : heavyRain > 0 ? `ฝนหนัก ${heavyRain} จุด` : 'ปกติ';

  // Flood reports: people on Traffy Fondue in the last 6 h only, the same count as the map and the report page.
  // Flooded roads from traffic news are not people's reports and stay out of it.
  // Until Traffy has answered once there is no count: "no reports" would be a wrong all-clear.
  // After that a failed update (Traffy on the server, or this page's request) keeps the old count, marked as old.
  const citizen = traffy?.updated_at ? traffy.items?.length ?? 0 : null;
  const repFailed = !!traffy?.error || traffyFailed;
  const repTone = citizen == null ? 'neutral' : citizen === 0 ? 'green' : citizen < 20 ? 'yellow' : 'red';
  const repStatus = citizen != null ? (citizen === 0 ? 'ไม่มีคนแจ้ง' : `${citizen} เรื่อง`) : repFailed ? 'ยังโหลดไม่ได้' : 'กำลังโหลด';
  const repNote = citizen != null && repFailed ? `อัปเดตไม่สำเร็จ · ข้อมูล ${fmtTime(traffy.updated_at)}\u00a0น.` : null;

  // Air
  const pm = air?.avg_pm25;
  const airTone = pm == null ? 'neutral' : pm <= 25 ? 'green' : pm <= 37.5 ? 'yellow' : 'red';
  const airStatus = pm == null ? 'กำลังโหลด' : pm <= 15 ? 'อากาศดีมาก' : pm <= 25 ? 'อากาศดี' : pm <= 37.5 ? 'ปานกลาง' : pm <= 75 ? 'เริ่มมีผลต่อสุขภาพ' : 'มีผลต่อสุขภาพ';

  // Incidents
  const cam = incidents?.camera || [];
  const longdo = incidents?.longdo || [];
  const total = cam.length + longdo.length;
  const incTone = !incidents ? 'neutral' : total === 0 ? 'green' : total <= 2 ? 'yellow' : 'red';
  const incStatus = !incidents ? 'กำลังโหลด' : total === 0 ? 'ไม่มีเหตุ' : `${total} จุด`;

  const items = [
    { id: 'traffic', q: 'รถติดไหม', a: trafficStatus, say: `รถ${level.label}`, tone: trafficTone, known: flow != null, icon: ICONS.traffic, go: () => onNavigate('map') },
    { id: 'weather', q: weather?.mine ? 'อากาศตรงนี้' : 'อากาศ กทม.', a: weatherStatus, say: weatherStatus, tone: weather?.tone || 'neutral', known: !!weather, icon: ICONS.weather, go: () => onNavigate('water') },
    { id: 'water', q: 'ฝนและน้ำ', a: waterStatus, say: waterStatus, tone: waterTone, known: !!water || flooding > 0, icon: ICONS.water, go: () => onNavigate('water') },
    { id: 'report', q: 'มีคนแจ้งน้ำท่วมไหม', sub: 'ใน 6 ชม.', a: repStatus, say: `คนแจ้งน้ำท่วม ${repStatus}`, note: repNote, tone: repTone, known: citizen != null, icon: ICONS.report, go: () => onNavigate('water') },
    { id: 'air', q: 'ฝุ่นเยอะไหม', a: airStatus, say: `ฝุ่น PM2.5 ${airStatus}`, tone: airTone, known: pm != null, icon: ICONS.air, go: () => onNavigate('map') },
    { id: 'incident', q: 'มีอุบัติเหตุไหม', a: incStatus, say: `อุบัติเหตุและรถเสีย ${incStatus}`, tone: incTone, known: !!incidents, icon: ICONS.incident, go: () => (onIncidents ? onIncidents() : onNavigate('dashboard')) },
  ];
  const reds = items.filter((i) => i.tone === 'red');
  const yellows = items.filter((i) => i.tone === 'yellow');
  const care = [...reds, ...yellows];
  const calm = items.filter((i) => i.known && !care.includes(i));    // has data and nothing to watch
  const pending = items.filter((i) => !i.known);                     // loading, or could not be loaded

  // The summary: one verdict word and one sentence, made from the six answers (rules, no AI)
  const avoidText = avoid?.length ? avoid.slice(0, 2).join(' กับ') : null;
  const verdict = reds.length
    ? { tone: 'red', label: 'ควรระวัง' }
    : yellows.length
      ? { tone: 'yellow', label: 'เฝ้าดู' }
      : pending.length
        ? { tone: 'neutral', label: calm.length ? 'ข้อมูลยังไม่ครบ' : 'กำลังโหลด' }
        : { tone: 'green', label: 'ปกติ' };
  const headline = flooding > 0
      ? `มีถนนน้ำท่วม ${flooding} จุด ดูเส้นทางก่อนออกเดินทาง`
      : trafficTone === 'red'
        ? (avoidText ? `รถติดหลายจุด เลี่ยง${avoidText}` : 'รถติดหลายจุด ดูทางเลี่ยงก่อนออกเดินทาง')
        : trafficTone === 'yellow'
          ? (avoidText ? `ออกเดินทางได้ แต่เลี่ยง${avoidText}` : 'ออกเดินทางได้ แต่เผื่อเวลา')
          : care.length
            ? 'ออกเดินทางได้ มีบางเรื่องต้องระวัง'
            : pending.length
              ? 'กำลังรวมข้อมูลของเมือง ยังสรุปไม่ได้'
              : 'ออกเดินทางได้ตามปกติ';
  const detail = [
    ...care.map((i) => i.say),
    ...(care.length && calm.length && !pending.length ? ['เรื่องอื่นปกติ'] : []),
    ...(pending.length ? [`ยังไม่มีข้อมูล: ${pending.map((i) => i.q).join(', ')}`] : []),
  ].join(' · ');

  return (
    <>
      <CityHero verdict={verdict} headline={headline} detail={detail} onAskText={onAskText} />

      {/* wide screens: the station line */}
      <section aria-labelledby="city-now" className="hidden md:block rounded-md border border-[var(--c-border)] bg-[var(--c-surface)] py-6">
        <div className="flex flex-wrap items-baseline justify-between gap-2 px-6 pb-5">
          <h2 id="city-now" className="text-xl font-bold">เมืองตอนนี้</h2>
          <p className="text-sm text-[var(--c-muted)]">แตะจุดเพื่อดูรายละเอียด</p>
        </div>
        <ul className="grid grid-cols-3 xl:grid-cols-6 gap-y-6">
          {items.map((i) => (
            <li key={i.id} className={`tone-${i.tone}`}>
              <button type="button" onClick={i.go} className="group relative cursor-pointer w-full flex flex-col items-center gap-1 px-2.5 text-center">
                <span aria-hidden="true" className="absolute inset-x-0 top-5 h-1.5 bg-[var(--c-line)]" />
                <span aria-hidden="true" className="relative w-[46px] h-[46px] rounded-full border-[7px] border-[var(--t-ring)] bg-[var(--t-fill)] mb-1.5 transition-transform duration-200 group-hover:scale-110" />
                <span className="text-[15px] leading-snug text-[var(--c-muted)]">
                  {i.q}
                  {i.sub && <span className="block text-xs">{i.sub}</span>}
                </span>
                <span className="font-display text-xl font-bold leading-tight text-[var(--t-text)]">{i.a}</span>
                {i.note && <span className="text-xs text-amber-700">{i.note}</span>}
              </button>
            </li>
          ))}
        </ul>
        <Legend />
      </section>

      {/* phones: questions, the ones that need care first and big */}
      <section aria-label="เมืองตอนนี้" className="md:hidden flex flex-col gap-3">
        {care.length > 0 && (
          <>
            <h2 className="text-[15px] font-semibold text-[var(--act-text)]">ต้องระวัง {care.length} เรื่อง</h2>
            {care.map((i) => (
              <button key={i.id} type="button" onClick={i.go} className={`tone-${i.tone} cursor-pointer w-full text-left flex items-center gap-3.5 rounded-md px-4 py-4 bg-[var(--t-tint)]`}>
                <span className="flex-1 min-w-0">
                  <span className="block text-base text-[var(--c-ink)]">
                    {i.q}
                    {i.sub && <span className="text-sm text-[var(--c-muted)]"> ({i.sub})</span>}
                  </span>
                  <span className="block font-display text-[28px] font-bold leading-tight text-[var(--t-text)]">{i.a}</span>
                  {i.note && <span className="block text-xs text-amber-700">{i.note}</span>}
                </span>
                <span aria-hidden="true" className="w-12 h-12 shrink-0 rounded-md bg-[var(--c-surface)] text-[var(--t-text)] grid place-items-center">
                  <span className="w-6 h-6">{i.icon}</span>
                </span>
              </button>
            ))}
          </>
        )}
        {calm.length > 0 && <QuietList title={`ปกติดี ${calm.length} เรื่อง`} titleClass="text-[var(--ok-text)]" rows={calm} />}
        {pending.length > 0 && <QuietList title={`ยังไม่มีข้อมูล ${pending.length} เรื่อง`} titleClass="text-[var(--c-muted)]" rows={pending} />}
      </section>
    </>
  );
}

// Phones: a short list of answers with nothing to watch (or no data yet); a stale answer keeps its note
function QuietList({ title, titleClass, rows }) {
  return (
    <>
      <h2 className={`mt-1 text-[15px] font-semibold ${titleClass}`}>{title}</h2>
      <div className="rounded-md border border-[var(--c-border)] bg-[var(--c-surface)] overflow-hidden divide-y divide-[var(--c-border)]">
        {rows.map((i) => (
          <button key={i.id} type="button" onClick={i.go} className={`tone-${i.tone} cursor-pointer w-full min-h-15 px-4 py-2 flex items-center gap-3 text-left`}>
            <span className="flex-1 min-w-0 text-base text-[var(--c-muted)]">{i.q}</span>
            <span className="text-right">
              <span className="block font-display text-lg font-bold text-[var(--t-text)]">{i.a}</span>
              {i.note && <span className="block text-xs text-amber-700 dark:text-amber-400">{i.note}</span>}
            </span>
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-3.5 h-3.5 shrink-0 text-[var(--c-muted)]" aria-hidden="true">
              <path d="M6 4l4 4-4 4" />
            </svg>
          </button>
        ))}
      </div>
    </>
  );
}

// The summary as a platform sign: a band in the verdict's colour with the verdict word, the sentence under it
function CityHero({ verdict, headline, detail, onAskText }) {
  const [q, setQ] = useState('');
  return (
    <section aria-label="สรุปตอนนี้" className="rounded-md overflow-hidden border border-[var(--c-border)] bg-[var(--c-surface)]">
      <div className={`tone-${verdict.tone} flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-5 sm:px-6 py-2.5 bg-[var(--t-band)] text-[var(--t-on)]`}>
        <span className="inline-flex items-center gap-2 font-display text-xl font-bold">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5" aria-hidden="true">
            {verdict.tone === 'green' ? (
              <path d="M5 12.5l4.5 4.5L19 7.5" />
            ) : (
              <>
                <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
                <path d="M12 9v4M12 17h.01" />
              </>
            )}
          </svg>
          {verdict.label}
        </span>
        <span className="text-sm font-medium">สรุปจาก 6 เรื่องด้านล่าง</span>
      </div>
      <div className="px-5 sm:px-6 pt-5 pb-6 flex flex-col gap-3">
        <p className="font-display text-[26px] sm:text-[34px] font-bold leading-tight max-w-[26em]">{headline}</p>
        {detail && <p className="text-base leading-relaxed text-[var(--c-muted)] max-w-[44em]">{detail}</p>}
        {onAskText && (
          <form
            className="flex flex-wrap gap-2 mt-3 pt-4 border-t-2 border-[var(--c-ink)]"
            onSubmit={(e) => {
              e.preventDefault();
              const text = q.trim();
              if (text) onAskText(text);
            }}
          >
            <label htmlFor="city-ask" className="basis-full font-display text-base font-bold">ถาม AI เรื่องถนนที่จะไป</label>
            <input
              id="city-ask"
              type="text"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="เช่น ลาดพร้าวตอนนี้ติดไหม"
              className="flex-[1_1_160px] min-w-0 h-12 px-4 rounded-[4px] bg-[var(--c-surface)] border-2 border-[var(--c-border-strong)] text-base text-[var(--c-ink)] placeholder:text-[var(--c-muted)]"
            />
            <button type="submit" className="cursor-pointer h-12 px-6 rounded-[4px] bg-[var(--c-ink)] text-[var(--c-surface)] text-base font-bold hover:opacity-90">
              ถาม
            </button>
          </form>
        )}
      </div>
    </section>
  );
}

function Legend() {
  const dot = 'w-3.5 h-3.5 rounded-full border-3 border-[var(--t-ring)] bg-[var(--t-fill)]';
  return (
    <ul className="flex flex-wrap justify-center gap-5 px-6 pt-6 text-sm text-[var(--c-muted)]">
      <li className="tone-green inline-flex items-center gap-1.5"><span className={dot} aria-hidden="true" />ปกติ</li>
      <li className="tone-yellow inline-flex items-center gap-1.5"><span className={dot} aria-hidden="true" />เฝ้าดู</li>
      <li className="tone-red inline-flex items-center gap-1.5"><span className={dot} aria-hidden="true" />ควรระวัง</li>
    </ul>
  );
}
