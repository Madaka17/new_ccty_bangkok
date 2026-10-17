// PM2.5 page: how dusty it is now, which districts are worst, and the 3-day outlook. Public, for anyone in Bangkok.
import { useEffect, useState } from 'react';
import { fetchAirForecast, fetchAirStations } from '../lib/api.js';
import { airAdvice, bkkAverage, districtRanking } from '../lib/air.js';
import { trackView } from '../lib/telemetry.js';
import { Button, Card, ErrorState, Skeleton } from './dashboard/ui.jsx';
import { PageHeader } from './dashboard/primitives.jsx';
import { fmtDateTime, fmtTime } from './dashboard/format.js';

const POLL_MS = 600000;
const TOP_DISTRICTS = 10;
const SOURCE_LINE = 'ข้อมูล: กทม., กรมควบคุมมลพิษ, ค่าพยากรณ์โดยประมาณ';

// Level pill: the band colour is the fill; text is dark ink, or white on the darkest band, so it stays readable
const textOn = (level) => (level === 'very_unhealthy' ? '#ffffff' : '#1a2228');

function LevelPill({ color, level, children }) {
  return (
    <span
      className="inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold leading-4 max-w-full text-center"
      style={{ backgroundColor: color, color: textOn(level) }}
    >
      {children}
    </span>
  );
}

function OutlookChart({ hours }) {
  const [hover, setHover] = useState(null);
  const W = 320;
  const H = 150;
  const L = 34;
  const R = 10;
  const T = 10;
  const B = 24;
  const n = hours.length;
  const top = Math.max(40, Math.ceil(Math.max(...hours.map((h) => h.pm25)) / 10) * 10);
  const x = (i) => L + (i / (n - 1)) * (W - L - R);
  const y = (v) => T + (1 - v / top) * (H - T - B);
  const path = hours.map((h, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)} ${y(h.pm25).toFixed(1)}`).join(' ');
  const yTicks = [0, top / 2, top];
  const xStep = Math.max(1, Math.ceil(n / 6));
  const xLabels = hours.map((h, i) => i).filter((i) => i % xStep === 0);
  const last = hours[n - 1];

  const pick = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const sx = ((e.clientX - rect.left) / rect.width) * W;
    const i = Math.round(((sx - L) / (W - L - R)) * (n - 1));
    setHover(Math.min(n - 1, Math.max(0, i)));
  };

  const hv = hover != null ? hours[hover] : null;
  return (
    <div>
      <p className="text-xs text-slate-600 h-5" aria-live="polite">
        {hv ? `${fmtTime(hv.t)} น. ประมาณ ${Math.round(hv.pm25)}` : ' '}
      </p>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full h-auto touch-pan-y"
        role="img"
        aria-label="กราฟแนวโน้มฝุ่น 3 วันข้างหน้า"
        onPointerMove={pick}
        onPointerDown={pick}
        onPointerLeave={() => setHover(null)}
      >
        {yTicks.map((v) => (
          <g key={v}>
            <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} style={{ stroke: 'var(--c-border)' }} strokeWidth="1" />
            <text x={L - 6} y={y(v) + 4} textAnchor="end" className="text-[10px]" style={{ fill: 'var(--c-muted)' }}>
              {Math.round(v)}
            </text>
          </g>
        ))}
        {xLabels.map((i) => (
          <text key={i} x={x(i)} y={H - 6} textAnchor={i === 0 ? 'start' : 'middle'} className="text-[10px]" style={{ fill: 'var(--c-muted)' }}>
            {fmtTime(hours[i].t)}
          </text>
        ))}
        <path d={path} fill="none" style={{ stroke: 'var(--c-primary)' }} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        {hv && (
          <g>
            <line x1={x(hover)} x2={x(hover)} y1={T} y2={H - B} style={{ stroke: 'var(--c-muted)' }} strokeWidth="1" />
            <circle cx={x(hover)} cy={y(hv.pm25)} r="4" style={{ fill: 'var(--c-primary)', stroke: 'var(--c-surface)' }} strokeWidth="2" />
          </g>
        )}
        <circle cx={x(n - 1)} cy={y(last.pm25)} r="4" style={{ fill: 'var(--c-primary)', stroke: 'var(--c-surface)' }} strokeWidth="2" />
      </svg>
    </div>
  );
}

function Summary({ avg }) {
  if (avg === undefined) return <Skeleton className="h-16 w-48" />;
  if (avg === null) return <p className="text-base text-slate-700">ยังไม่มีข้อมูลฝุ่น</p>;
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-3">
        <LevelPill color={avg.color} level={avg.level}>
          <span className="text-base">{avg.label}</span>
        </LevelPill>
        <span className="text-2xl font-semibold tabular-nums text-slate-900" title="ไมโครกรัมต่อลูกบาศก์เมตร">
          {avg.pm25}
        </span>
      </div>
      <p className="text-sm text-slate-700">{airAdvice(avg.level)}</p>
    </div>
  );
}

export default function AirPage({ isActive, onNavigate }) {
  const [stations, setStations] = useState(null);     // /api/air/stations
  const [forecast, setForecast] = useState(null);     // /api/air/forecast, null until ready
  const [failed, setFailed] = useState(false);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => trackView('air'), []);

  useEffect(() => {
    if (!isActive) return;
    let alive = true;
    const tick = () => {
      fetchAirStations()
        .then((s) => { if (alive) { setStations(s); setFailed(false); } })
        .catch(() => alive && setFailed(true));
      // The outlook is optional: a failed request keeps the last good answer
      fetchAirForecast()
        .then((f) => { if (alive && f) setForecast(f); })
        .catch(() => {});
    };
    tick();
    const id = setInterval(tick, POLL_MS);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [isActive]);

  const items = stations?.items;
  const avg = stations ? bkkAverage(items) : undefined;
  const ranking = stations ? districtRanking(items) : [];
  const maxPm = ranking.length ? Math.max(...ranking.map((r) => r.pm25)) : 0;
  const shown = showAll ? ranking : ranking.slice(0, TOP_DISTRICTS);
  const days = forecast?.days || [];
  const hours = forecast?.hours || [];
  const hasHours = hours.length > 1;

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="ฝุ่น PM2.5"
        description={stations?.updated_at ? `ข้อมูลล่าสุด ${fmtDateTime(stations.updated_at)}` : 'กำลังโหลดข้อมูล'}
      />

      {failed && !stations && <ErrorState message="โหลดข้อมูลฝุ่นไม่สำเร็จ ระบบจะลองใหม่เอง" />}

      <div className="grid gap-4 lg:grid-cols-2 lg:items-start">
        <Card className="p-4 lg:col-span-2">
          <h3 className="text-[15px] font-semibold text-slate-900 mb-2">ตอนนี้ใน กทม.</h3>
          <Summary avg={avg} />
        </Card>

        {forecast && (
          <Card className="p-4">
            <h3 className="text-[15px] font-semibold text-slate-900">ฝุ่น 3 วันข้างหน้า</h3>
            <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
              {days.map((d) => (
                <div key={d.date} className="flex flex-col items-center gap-1 rounded-lg border border-slate-200 p-2 min-w-0 text-center">
                  <span className="text-xs text-slate-600">{d.label}</span>
                  <LevelPill color={d.color} level={d.level}>{d.label_th}</LevelPill>
                </div>
              ))}
            </div>
            {hasHours && (
              <div className="mt-4">
                <OutlookChart hours={hours} />
              </div>
            )}
            <p className="text-xs text-slate-500 mt-2">ค่าประมาณ อาจต่างจากจุดวัดจริง</p>
          </Card>
        )}

        <Card className="p-4">
          <h3 className="text-[15px] font-semibold text-slate-900">เขตที่ฝุ่นมากที่สุด</h3>
          {stations && ranking.length === 0 && <p className="text-sm text-slate-700 mt-3">ยังไม่มีข้อมูลฝุ่น</p>}
          {!stations && <Skeleton className="h-40 mt-3" />}
          <ul className="mt-3 flex flex-col gap-2">
            {shown.map((r) => (
              <li key={r.district} className="grid grid-cols-[minmax(0,6rem)_1fr_auto] items-center gap-2 text-sm">
                <span className="truncate text-slate-800" title={r.district}>{r.district}</span>
                <span className="h-2 rounded-full bg-slate-100 overflow-hidden">
                  <span className="block h-full rounded-full" style={{ width: `${(r.pm25 / maxPm) * 100}%`, backgroundColor: r.color }} />
                </span>
                <span className="text-xs text-slate-700 whitespace-nowrap">{r.label}</span>
              </li>
            ))}
          </ul>
          {ranking.length > TOP_DISTRICTS && (
            <Button size="sm" variant="ghost" className="mt-3" aria-expanded={showAll} onClick={() => setShowAll((v) => !v)}>
              {showAll ? 'ซ่อนบางเขต' : 'ดูทุกเขต'}
            </Button>
          )}
        </Card>

        <div className="lg:col-span-2 flex flex-col gap-3 items-start">
          <Button variant="primary" onClick={() => onNavigate('map')}>ดูจุดวัดฝุ่นบนแผนที่</Button>
          <p className="text-xs text-slate-500">{SOURCE_LINE}</p>
        </div>
      </div>
    </div>
  );
}
