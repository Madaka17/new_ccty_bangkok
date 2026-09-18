import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fetchWaterSummary } from '../lib/api.js';
import { Badge, Button, ErrorState } from './dashboard/ui.jsx';
import { PageHeader, StatTile, StatusBanner } from './dashboard/primitives.jsx';
import { fmtDateTime } from './dashboard/format.js';
import ForecastChart from './water/ForecastChart.jsx';
import BMAEventFeed from './water/BMAEventFeed.jsx';
import WindyRadarCard from './water/WindyRadarCard.jsx';
import FloodAnalysisGuide from './water/FloodAnalysisGuide.jsx';
import { RiverStations, TideCard, CanalCard, RainCard, UpstreamCard } from './water/WaterLists.jsx';

const POLL_MS = 60000;
const DEFAULT_STATION = '1132'; // สะพานนวลฉวี: nearest official 7-day forecast to Bangkok

// Overall outlook line derived from the pieces we have (kept deliberately simple and explainable)
function outlook(s) {
  if (!s) return null;
  const over = s.river_counts?.overflow || 0;
  const high = s.river_counts?.high || 0;
  const roads = (s.flood_roads?.flooding || 0) + (s.flood_roads?.slight || 0);
  const rain = s.rain_warnings?.some((r) => r.kind === 'forecast');
  const tide = Math.max(0, ...(s.tide || []).map((t) => t.max ?? 0));
  if (over >= 3 || roads >= 5) return { tone: 'red', label: 'เสี่ยงสูง', text: `แม่น้ำ-คลองหลักล้นตลิ่ง ${over} สถานี และมีถนนน้ำท่วมขัง ${roads} จุด ริมน้ำและพื้นที่ลุ่มควรเตรียมรับมือ` };
  if (over >= 1 || high >= 8 || rain || tide >= 1.2) return { tone: 'yellow', label: 'เฝ้าระวัง', text: `${over ? `ล้นตลิ่ง ${over} สถานี · ` : ''}ใกล้ล้น ${high} สถานี${rain ? ' · มีเตือนฝนหนัก 24 ชม.' : ''}${tide >= 1.2 ? ` · น้ำทะเลหนุนสูง ${tide.toFixed(2)} ม.` : ''} ชุมชนริมเจ้าพระยานอกคันกั้นน้ำควรระวังช่วงน้ำขึ้น` };
  return { tone: 'green', label: 'ปกติ', text: 'ระดับน้ำแม่น้ำ-คลองหลักส่วนใหญ่ต่ำกว่าตลิ่ง ไม่มีเตือนฝนหนักในพื้นที่' };
}

export default function WaterPage({ isActive, onToast, onNavigate, onAsk }) {
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [stationId, setStationId] = useState(DEFAULT_STATION);
  const chartRef = useRef(null);
  // Picking a station from a list further down the page: switch and bring the chart into view
  const pickStation = useCallback((id) => {
    setStationId(String(id));
    chartRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, []);

  const load = useCallback(() => {
    setRefreshing(true);
    return fetchWaterSummary()
      .then((s) => {
        setSummary(s);
        setError(false);
      })
      .catch(() => setError(true))
      .finally(() => setRefreshing(false));
  }, []);

  useEffect(() => {
    if (!isActive) return;
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [isActive, load]);

  // Chart station list: upstream official stations first, then every metro station
  const stations = useMemo(() => {
    if (!summary) return [];
    const up = (summary.official_stations || []).filter((s) => !summary.river.some((r) => r.id === s.id)).map((s) => ({ ...s, district: '', official_forecast: true }));
    return [...up, ...summary.river];
  }, [summary]);

  useEffect(() => {
    if (stations.length && !stations.some((s) => s.id === stationId)) setStationId(stations[0].id);
  }, [stations, stationId]);

  const loading = !summary;
  const o = outlook(summary);
  const tideMax = summary?.tide?.length ? summary.tide.reduce((a, b) => ((b.max ?? -9) > (a.max ?? -9) ? b : a)) : null;
  const roads = summary?.flood_roads;

  return (
    <div className="flex flex-col gap-4 max-w-6xl mx-auto w-full">
      <PageHeader
        title="คาดการณ์ระดับน้ำ กรุงเทพฯ และปริมณฑล"
        description={summary ? `ข้อมูล สสน. (thaiwater.net) และสำนักการระบายน้ำ กทม. · อัปเดต ${fmtDateTime(summary.updated_at)} · รีเฟรชเองทุก 2 นาที` : 'กำลังโหลดข้อมูลจาก thaiwater.net'}
        actions={
          <>
            {summary?.stale && <Badge tone="yellow">ข้อมูลเก่า</Badge>}
            <Button size="sm" onClick={load} loading={refreshing}>
              รีเฟรช
            </Button>
          </>
        }
      />

      {error && !summary && <ErrorState message="เชื่อมต่อ thaiwater.net ไม่สำเร็จ" onRetry={load} retrying={refreshing} />}
      {summary?.api_key?.rejected && (
        <p role="status" className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          thaiwater.net ปฏิเสธคีย์ API ตัวเดิม ระบบกำลังค้นหาคีย์ใหม่จากเว็บ twa.thaiwater.net อัตโนมัติทุก 5 นาที
        </p>
      )}
      {error && summary && (
        <p role="status" className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          รีเฟรชล่าสุดไม่สำเร็จ แสดงข้อมูลเมื่อ {fmtDateTime(summary.updated_at)}
        </p>
      )}

      {o && (
        <StatusBanner tone={o.tone} label={o.label}>
          {o.text}
        </StatusBanner>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatTile
          label="สถานีแม่น้ำ-คลองหลักล้นตลิ่ง"
          value={summary ? `${summary.river_counts.overflow} / ${summary.river.length}` : '–'}
          sub={summary ? `ใกล้ล้นอีก ${summary.river_counts.high} สถานี` : ''}
          badge={summary?.river_counts.overflow ? <Badge tone="red" dot>ล้น</Badge> : null}
          loading={loading}
        />
        <StatTile
          label="น้ำทะเลหนุนสูงสุดวันนี้"
          value={tideMax?.max != null ? `${tideMax.max.toFixed(2)} ม.` : '–'}
          sub={tideMax ? `${tideMax.name} เวลา ${tideMax.max_time} น.` : ''}
          badge={tideMax?.max >= 1.2 ? <Badge tone="yellow">หนุนสูง</Badge> : null}
          loading={loading}
        />
        <StatTile
          label="ถนน กทม. มีน้ำท่วมขัง (เซ็นเซอร์)"
          value={roads ? `${roads.flooding + roads.slight} จุด` : '–'}
          sub={roads ? `จากเซ็นเซอร์ ${roads.flooding + roads.slight + roads.normal} จุด · ท่วมขัง ${roads.flooding}` : ''}
          badge={roads?.flooding ? <Badge tone="red" dot>ท่วม</Badge> : null}
          loading={loading}
        />
        <StatTile
          label="คลอง กทม. น้ำสูงผิดปกติ"
          value={summary ? `${summary.canal_counts.overflow + summary.canal_counts.high} / ${summary.canal_total}` : '–'}
          sub={summary ? `ล้น ${summary.canal_counts.overflow} · ใกล้ล้น ${summary.canal_counts.high}` : ''}
          badge={summary?.canal_counts.overflow ? <Badge tone="red" dot>ล้น</Badge> : null}
          loading={loading}
        />
      </div>

      {stations.length > 0 && <ForecastChart stations={stations} stationId={stationId} onPickStation={setStationId} anchorRef={chartRef} />}

      <FloodAnalysisGuide summary={summary} onNavigate={onNavigate} onAsk={onAsk} />

      <WindyRadarCard />

      <BMAEventFeed isActive={isActive} onToast={onToast} />

      <div className="grid grid-cols-1 lg:grid-cols-[1.4fr_1fr] gap-4">
        <RiverStations rows={summary?.river} selectedId={stationId} onSelect={pickStation} loading={loading} />
        <div className="flex flex-col gap-4">
          <UpstreamCard rows={summary?.official_stations} onPick={pickStation} loading={loading} />
          <TideCard rows={summary?.tide} loading={loading} />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <CanalCard canals={summary?.canals} counts={summary?.canal_counts} total={summary?.canal_total} roads={roads} loading={loading} />
        <RainCard rows={summary?.rain_warnings} loading={loading} />
      </div>

      <p className="text-xs text-slate-500 leading-5 px-1">
        แหล่งข้อมูล: สถาบันสารสนเทศทรัพยากรน้ำ (สสน.) ผ่าน twa.thaiwater.net, สำนักการระบายน้ำ กรุงเทพมหานคร, ศูนย์ควบคุมระบบจราจร กทม. (cpudapp.bangkok.go.th) ·
        คาดการณ์ 7 วันเป็นของ สสน. ส่วนค่า “ประเมิน” 48 ชม. คำนวณจากแนวโน้มและรอบน้ำขึ้น-น้ำลงของสถานีนั้นเอง ใช้ประกอบการตัดสินใจเบื้องต้นเท่านั้น
      </p>
    </div>
  );
}
