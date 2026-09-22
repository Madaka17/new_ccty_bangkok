import { useEffect, useState } from 'react';
import { fetchWaterSummary, fetchAirStations } from '../../lib/api.js';
import { fmtTime } from './format.js';

// One glance, four answers: traffic / rain-water / dust / incidents. Each tile is a link to its page.
// tone: green = fine, yellow = watch, red = act, neutral = no data

const TONE = {
  green: 'border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-900/50 dark:bg-emerald-950/40 dark:text-emerald-200',
  yellow: 'border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/40 dark:text-amber-200',
  red: 'border-red-200 bg-red-50 text-red-900 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-200',
  neutral: 'border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-200',
};
const DOT = { green: 'bg-emerald-500', yellow: 'bg-amber-500', red: 'bg-red-500', neutral: 'bg-slate-400' };

const ICONS = {
  traffic: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
      <path d="M5 17h14M5 12h14M5 7h14" />
    </svg>
  ),
  water: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
      <path d="M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z" />
    </svg>
  ),
  air: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
      <path d="M3 8h11a3 3 0 1 0-3-3M3 14h14a3 3 0 1 1-3 3M3 11h7" />
    </svg>
  ),
  incident: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-5 h-5">
      <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01" />
    </svg>
  ),
};

function Tile({ icon, title, status, tone, detail, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`cursor-pointer text-left rounded-xl border px-4 py-3 flex items-start gap-3 transition-colors hover:brightness-95 dark:hover:brightness-110 focus-visible:outline-2 focus-visible:outline-blue-500 ${TONE[tone] || TONE.neutral}`}
    >
      <span className="mt-0.5 shrink-0 opacity-80">{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="block text-xs opacity-80">{title}</span>
        <span className="flex items-center gap-2 text-lg font-semibold leading-7">
          <span className={`inline-block w-2.5 h-2.5 rounded-full ${DOT[tone] || DOT.neutral}`} />
          {status}
        </span>
        <span className="block text-sm opacity-90 leading-5">{detail}</span>
      </span>
    </button>
  );
}

export default function CityStatusStrip({ summary, incidents, flood, onNavigate, isActive }) {
  const [water, setWater] = useState(null);
  const [air, setAir] = useState(null);

  useEffect(() => {
    if (!isActive) return;
    let alive = true;
    const tick = () => {
      fetchWaterSummary().then((w) => alive && setWater(w)).catch(() => {});
      fetchAirStations().then((a) => alive && setAir(a)).catch(() => {});
    };
    tick();
    const id = setInterval(tick, 300000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [isActive]);

  // Traffic
  const flow = summary?.flow_index;
  const trafficTone = flow == null ? 'neutral' : flow >= 75 ? 'green' : flow >= 50 ? 'yellow' : 'red';
  const trafficStatus = flow == null ? 'กำลังโหลด' : flow >= 75 ? 'คล่องตัว' : flow >= 50 ? 'ชะลอตัว' : 'ติดขัด';
  const worst = summary?.congested?.[0];
  const trafficDetail = flow == null ? '' : `ระบายได้ ${flow}/100 · แดง ${summary.red_pct}%${worst ? ` · ติดสุด ${worst.name}` : ''}`;

  // Rain + water. Flooded-road counts come from the BMA drainage sensors (flood_service.py, ~250
  // stations); ThaiWater relays only about 107 of them, so it is the fallback.
  const roads = water?.flood_roads;
  const flooding = flood
    ? (flood.counts?.flood || 0) + (flood.counts?.slight || 0)
    : (roads?.flooding || 0) + (roads?.slight || 0);
  const deepest = flood?.wet?.[0];
  const overflow = water?.river_counts?.overflow || 0;
  const heavyRain = (water?.ntw?.rain_counts?.heavy || 0) + (water?.ntw?.rain_counts?.extreme || 0);
  const worstZone = water?.weather?.[0];
  const waterTone = !water ? 'neutral' : flooding > 0 || worstZone?.watch === 'red' ? 'red' : heavyRain > 0 || overflow > 0 || worstZone?.watch === 'yellow' ? 'yellow' : 'green';
  const waterStatus = !water ? 'กำลังโหลด' : flooding > 0 ? `น้ำท่วมขัง ${flooding} จุด` : worstZone?.watch === 'red' ? `เฝ้าระวัง ${worstZone.name}` : overflow > 0 ? `ล้นตลิ่ง ${overflow} สถานี` : heavyRain > 0 ? `ฝนหนัก ${heavyRain} จุด` : 'ปกติ';
  const waterDetail = !water
    ? ''
    : deepest
      ? `ลึกสุด ${deepest.short_name} ${deepest.level_cm} ซม.${deepest.district ? ` (เขต${deepest.district})` : ''}`
      : worstZone
        ? `${worstZone.name}: ฝน 24 ชม.ข้างหน้า ${worstZone.rain_24h ?? 0} มม. (โอกาส ${worstZone.prob_24h ?? 0}%)${worstZone.storm_at ? ` · พายุฝน ${worstZone.storm_at} น.` : ''}`
        : `ถนนท่วม ${flooding} · ล้นตลิ่ง ${overflow} · ฝนหนัก ${heavyRain} สถานี`;

  // Air
  const pm = air?.avg_pm25;
  const worstPm = air?.items?.[0];
  const airTone = pm == null ? 'neutral' : pm <= 25 ? 'green' : pm <= 37.5 ? 'yellow' : 'red';
  const airStatus = pm == null ? 'กำลังโหลด' : pm <= 15 ? 'อากาศดีมาก' : pm <= 25 ? 'อากาศดี' : pm <= 37.5 ? 'ปานกลาง' : pm <= 75 ? 'เริ่มมีผลต่อสุขภาพ' : 'มีผลต่อสุขภาพ';
  const airDetail = pm == null ? '' : `PM2.5 เฉลี่ย ${pm} µg/m³${worstPm ? ` · สูงสุด ${worstPm.area || worstPm.name} ${worstPm.pm25}` : ''}`;

  // Incidents
  const cam = incidents?.camera || [];
  const longdo = incidents?.longdo || [];
  const total = cam.length + longdo.length;
  const incTone = !incidents ? 'neutral' : total === 0 ? 'green' : total <= 2 ? 'yellow' : 'red';
  const incStatus = !incidents ? 'กำลังโหลด' : total === 0 ? 'ไม่มีเหตุ' : `${total} เหตุการณ์`;
  const first = cam[0] || longdo[0];
  const incDetail = !incidents ? '' : first ? first.title : `กล้อง AI + รายงาน Longdo · อัปเดต ${fmtTime(incidents.updated)} น.`;

  return (
    <section aria-label="สถานการณ์เมืองตอนนี้" className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
      <Tile icon={ICONS.traffic} title="จราจรทั้งเมือง" status={trafficStatus} tone={trafficTone} detail={trafficDetail} onClick={() => onNavigate('map')} />
      <Tile icon={ICONS.water} title="ฝนและน้ำ" status={waterStatus} tone={waterTone} detail={waterDetail} onClick={() => onNavigate('water')} />
      <Tile icon={ICONS.air} title="ฝุ่น PM2.5" status={airStatus} tone={airTone} detail={airDetail} onClick={() => onNavigate('map')} />
      <Tile icon={ICONS.incident} title="เหตุการณ์บนถนน" status={incStatus} tone={incTone} detail={incDetail} onClick={() => onNavigate('dashboard')} />
    </section>
  );
}
