import { useEffect, useState } from 'react';

const WEATHER_POLL_MS = 600000;
import { fetchWaterSummary, fetchAirStations, fetchFloodReports, fetchLongdoFloods, fetchWeatherNow } from '../../lib/api.js';

// One glance, six answers: traffic / weather where the viewer is / rain-water / flood reports / dust / incidents. Headline only, no detail line. Each tile is a link to its page.
// tone: green = fine, yellow = watch, red = act, neutral = no data

const TONE_CONFIG = {
  green: {
    border: 'border-slate-200/90 dark:border-slate-800/90 hover:border-emerald-500/50 dark:hover:border-emerald-500/50',
    topBar: 'from-emerald-500 via-teal-400 to-transparent',
    glow: 'bg-emerald-500/10 dark:bg-emerald-500/15',
    iconBg: 'bg-emerald-50 text-emerald-600 border-emerald-200/80 dark:bg-emerald-500/10 dark:text-emerald-400 dark:border-emerald-500/20',
    statusColor: 'text-emerald-600 dark:text-emerald-400',
    dot: 'bg-emerald-500',
    ping: 'bg-emerald-400',
  },
  yellow: {
    border: 'border-slate-200/90 dark:border-slate-800/90 hover:border-amber-500/50 dark:hover:border-amber-500/50',
    topBar: 'from-amber-500 via-orange-400 to-transparent',
    glow: 'bg-amber-500/10 dark:bg-amber-500/15',
    iconBg: 'bg-amber-50 text-amber-600 border-amber-200/80 dark:bg-amber-500/10 dark:text-amber-400 dark:border-amber-500/20',
    statusColor: 'text-amber-600 dark:text-amber-400',
    dot: 'bg-amber-500',
    ping: 'bg-amber-400',
  },
  red: {
    border: 'border-slate-200/90 dark:border-slate-800/90 hover:border-rose-500/50 dark:hover:border-rose-500/50',
    topBar: 'from-rose-500 via-red-400 to-transparent',
    glow: 'bg-rose-500/10 dark:bg-rose-500/15',
    iconBg: 'bg-rose-50 text-rose-600 border-rose-200/80 dark:bg-rose-500/10 dark:text-rose-400 dark:border-rose-500/20',
    statusColor: 'text-rose-600 dark:text-rose-400',
    dot: 'bg-rose-500',
    ping: 'bg-rose-400',
  },
  neutral: {
    border: 'border-slate-200/90 dark:border-slate-800/90 hover:border-slate-300 dark:hover:border-slate-700',
    topBar: 'from-slate-400 via-slate-300 to-transparent dark:from-slate-600 dark:via-slate-700',
    glow: 'bg-slate-400/5 dark:bg-slate-500/5',
    iconBg: 'bg-slate-100 text-slate-600 border-slate-200/80 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700/50',
    statusColor: 'text-slate-800 dark:text-slate-100',
    dot: 'bg-slate-400',
    ping: 'bg-slate-400',
  },
};

const ICONS = {
  traffic: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
      <path d="M5 17h14M5 12h14M5 7h14" />
    </svg>
  ),
  water: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
      <path d="M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z" />
    </svg>
  ),
  air: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
      <path d="M3 8h11a3 3 0 1 0-3-3M3 14h14a3 3 0 1 1-3 3M3 11h7" />
    </svg>
  ),
  weather: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
      <path d="M7 18a4 4 0 1 1 .9-7.9A5 5 0 0 1 17.6 11 3.5 3.5 0 1 1 17.5 18H7z" />
    </svg>
  ),
  report: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
      <path d="M4 5h16v11H8l-4 4V5zM12 8v4M12 14.5h.01" />
    </svg>
  ),
  incident: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4">
      <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01" />
    </svg>
  ),
};

function Tile({ icon, title, status, tone = 'neutral', onClick }) {
  const cfg = TONE_CONFIG[tone] || TONE_CONFIG.neutral;
  return (
    <button
      type="button"
      onClick={onClick}
      className={`group relative cursor-pointer text-left rounded-2xl border p-4 sm:p-5 flex flex-col justify-between overflow-hidden bg-white/95 dark:bg-slate-900/90 backdrop-blur-md transition-all duration-300 ease-out hover:-translate-y-1 hover:shadow-xl dark:hover:shadow-black/50 ${cfg.border} focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-900`}
    >
      {/* Top accent gradient line */}
      <span className={`absolute top-0 inset-x-0 h-[3px] bg-gradient-to-r ${cfg.topBar}`} />

      {/* Subtle ambient corner glow */}
      <span className={`pointer-events-none absolute -top-10 -right-10 w-28 h-28 rounded-full blur-2xl transition-opacity duration-300 opacity-40 group-hover:opacity-100 ${cfg.glow}`} />

      <div className="relative z-10 w-full">
        {/* Header row: Icon & Title on left, Live Beacon & Arrow on right */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2.5 min-w-0">
            <span className={`w-8 h-8 rounded-xl border flex items-center justify-center shrink-0 transition-all duration-300 group-hover:scale-105 shadow-xs ${cfg.iconBg}`}>
              {icon}
            </span>
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 truncate">
              {title}
            </span>
          </div>

          <div className="flex items-center gap-1.5 py-1 px-2 rounded-full text-[11px] font-medium border bg-slate-50/90 dark:bg-slate-800/80 border-slate-200/80 dark:border-slate-700/80 text-slate-600 dark:text-slate-300 shrink-0">
            <span className="relative flex h-2 w-2">
              <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${cfg.ping}`} />
              <span className={`relative inline-flex rounded-full h-2 w-2 ${cfg.dot}`} />
            </span>
            <svg
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="w-3 h-3 opacity-40 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all duration-200"
            >
              <path d="M6 12l4-4-4-4" />
            </svg>
          </div>
        </div>

        {/* Status metric */}
        <div className="mt-3.5 flex items-baseline">
          <p className={`text-lg sm:text-[19px] font-bold tracking-tight leading-snug ${cfg.statusColor}`}>
            {status}
          </p>
        </div>
      </div>

    </button>
  );
}

export default function CityStatusStrip({ summary, incidents, flood, onNavigate, isActive }) {
  const [water, setWater] = useState(null);
  const [air, setAir] = useState(null);
  const [traffy, setTraffy] = useState(null);
  const [weather, setWeather] = useState(null);   // { temp, code, rain, place }
  const [longdoFloods, setLongdoFloods] = useState(null);

  useEffect(() => {
    if (!isActive) return;
    let alive = true;
    const tick = () => {
      fetchWaterSummary().then((w) => alive && setWater(w)).catch(() => {});
      fetchAirStations().then((a) => alive && setAir(a)).catch(() => {});
    };
    // flood reports move faster than the rest: every minute
    const reports = () => {
      fetchFloodReports().then((r) => alive && setTraffy(r)).catch(() => {});
      fetchLongdoFloods().then((r) => alive && setLongdoFloods(r)).catch(() => {});
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
  const trafficTone = flow == null ? 'neutral' : flow >= 75 ? 'green' : flow >= 50 ? 'yellow' : 'red';
  const trafficStatus = flow == null ? 'กำลังโหลด' : flow >= 75 ? 'คล่องตัว' : flow >= 50 ? 'ชะลอตัว' : 'ติดขัด';

  // Rain + water. Flooded-road counts come from the BMA drainage sensors (flood_service.py, ~250
  // stations); ThaiWater relays only about 107 of them, so it is the fallback.
  const roads = water?.flood_roads;
  const flooding = flood
    ? (flood.counts?.flood || 0) + (flood.counts?.slight || 0)
    : (roads?.flooding || 0) + (roads?.slight || 0);
  const overflow = water?.river_counts?.overflow || 0;
  const heavyRain = (water?.ntw?.rain_counts?.heavy || 0) + (water?.ntw?.rain_counts?.extreme || 0);
  const worstZone = water?.weather?.[0];
  const waterTone = !water ? 'neutral' : flooding > 0 || worstZone?.watch === 'red' ? 'red' : heavyRain > 0 || overflow > 0 || worstZone?.watch === 'yellow' ? 'yellow' : 'green';
  const waterStatus = !water ? 'กำลังโหลด' : flooding > 0 ? `น้ำท่วมขัง ${flooding} จุด` : worstZone?.watch === 'red' ? `เฝ้าระวัง ${worstZone.name}` : overflow > 0 ? `ล้นตลิ่ง ${overflow} สถานี` : heavyRain > 0 ? `ฝนหนัก ${heavyRain} จุด` : 'ปกติ';

  // Flood reports: people on Traffy Fondue (last 6 h) + iTIC / FM91 flooded roads still open on Longdo
  const citizen = traffy?.items?.length ?? null;
  const itic = longdoFloods ? longdoFloods.active ?? 0 : null;
  const reportTotal = (citizen || 0) + (itic || 0);
  const repLoading = citizen == null && itic == null;
  const repTone = repLoading ? 'neutral' : reportTotal === 0 ? 'green' : reportTotal < 20 ? 'yellow' : 'red';
  const repStatus = repLoading ? 'กำลังโหลด' : reportTotal === 0 ? 'ไม่มีเรื่องแจ้ง' : `${reportTotal} เคส`;

  // Air
  const pm = air?.avg_pm25;
  const airTone = pm == null ? 'neutral' : pm <= 25 ? 'green' : pm <= 37.5 ? 'yellow' : 'red';
  const airStatus = pm == null ? 'กำลังโหลด' : pm <= 15 ? 'อากาศดีมาก' : pm <= 25 ? 'อากาศดี' : pm <= 37.5 ? 'ปานกลาง' : pm <= 75 ? 'เริ่มมีผลต่อสุขภาพ' : 'มีผลต่อสุขภาพ';

  // Incidents
  const cam = incidents?.camera || [];
  const longdo = incidents?.longdo || [];
  const total = cam.length + longdo.length;
  const incTone = !incidents ? 'neutral' : total === 0 ? 'green' : total <= 2 ? 'yellow' : 'red';
  const incStatus = !incidents ? 'กำลังโหลด' : total === 0 ? 'ไม่มีเหตุ' : `${total} เหตุการณ์`;

  return (
    <section aria-label="สถานการณ์เมืองตอนนี้" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-6 gap-3">
      <Tile icon={ICONS.traffic} title="จราจรทั้งเมือง" status={trafficStatus} tone={trafficTone} onClick={() => onNavigate('map')} />
      <Tile icon={ICONS.weather} title={weather?.mine ? 'อากาศตรงนี้' : 'อากาศ กทม.'} status={weatherStatus} tone={weather?.tone || 'neutral'} onClick={() => onNavigate('water')} />
      <Tile icon={ICONS.water} title="ฝนและน้ำ" status={waterStatus} tone={waterTone} onClick={() => onNavigate('water')} />
      <Tile icon={ICONS.report} title="การแจ้งน้ำท่วม" status={repStatus} tone={repTone} onClick={() => onNavigate('water')} />
      <Tile icon={ICONS.air} title="ฝุ่น PM2.5" status={airStatus} tone={airTone} onClick={() => onNavigate('map')} />
      <Tile icon={ICONS.incident} title="เหตุการณ์บนถนน" status={incStatus} tone={incTone} onClick={() => onNavigate('dashboard')} />
    </section>
  );
}
