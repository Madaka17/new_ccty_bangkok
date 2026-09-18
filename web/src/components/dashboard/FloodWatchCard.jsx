import { useEffect, useMemo, useState } from 'react';
import { Card, Badge, Button } from './ui.jsx';
import { fetchBmaCameras, fetchWaterSummary, getBmaSnapshotUrl } from '../../lib/api.js';
import { enrichCamerasWithFloodRisk, getRiskWaterStations } from '../../lib/floodRisk.js';

export default function FloodWatchCard({ onNavigate, onOpenAI, onAsk }) {
  const [waterSummary, setWaterSummary] = useState(null);
  const [bmaCameras, setBmaCameras] = useState([]);
  const [filterTab, setFilterTab] = useState('all'); // 'all' | 'overflow' | 'high'
  const [activeModalCam, setActiveModalCam] = useState(null);
  const [refreshKey, setRefreshKey] = useState(Date.now());
  const [loading, setLoading] = useState(true);

  // Fetch water summary & BMA cameras
  useEffect(() => {
    let alive = true;
    const loadData = async () => {
      try {
        const [waterRes, bmaRes] = await Promise.allSettled([
          fetchWaterSummary(),
          fetchBmaCameras(),
        ]);
        if (!alive) return;
        if (waterRes.status === 'fulfilled') setWaterSummary(waterRes.value);
        if (bmaRes.status === 'fulfilled' && bmaRes.value?.items) {
          setBmaCameras(bmaRes.value.items);
        }
      } catch (e) {
        console.warn('[FloodWatchCard] Load error:', e);
      } finally {
        if (alive) setLoading(false);
      }
    };

    loadData();
    const interval = setInterval(() => {
      loadData();
      setRefreshKey(Date.now());
    }, 60000);

    return () => {
      alive = false;
      clearInterval(interval);
    };
  }, []);

  // Risk stations summary
  const riskStations = useMemo(() => {
    return getRiskWaterStations(waterSummary);
  }, [waterSummary]);

  const overflowStations = useMemo(
    () => riskStations.filter((s) => s.level === 'overflow'),
    [riskStations]
  );
  const highStations = useMemo(
    () => riskStations.filter((s) => s.level === 'high'),
    [riskStations]
  );

  // Correlate BMA cameras with flood risk stations
  const floodRiskCameras = useMemo(() => {
    if (!bmaCameras.length || !riskStations.length) return [];
    const enriched = enrichCamerasWithFloodRisk(bmaCameras, waterSummary);
    const matched = enriched.filter((c) => c.floodRisk);

    // Sort: overflow first, then by closest distance
    return matched.sort((a, b) => {
      if (a.floodRisk.isOverflow && !b.floodRisk.isOverflow) return -1;
      if (!a.floodRisk.isOverflow && b.floodRisk.isOverflow) return 1;
      return (a.floodRisk.distanceKm || 99) - (b.floodRisk.distanceKm || 99);
    });
  }, [bmaCameras, riskStations, waterSummary]);

  // Filtered cameras for display
  const displayCameras = useMemo(() => {
    let list = floodRiskCameras;
    if (filterTab === 'overflow') {
      list = list.filter((c) => c.floodRisk?.isOverflow);
    } else if (filterTab === 'high') {
      list = list.filter((c) => !c.floodRisk?.isOverflow);
    }
    return list.slice(0, 8); // Top 8 most critical cameras
  }, [floodRiskCameras, filterTab]);

  return (
    <Card className="p-5 border-cyan-200 bg-gradient-to-b from-cyan-50/40 via-white to-white shadow-sm overflow-hidden">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-100">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl bg-cyan-600 text-white flex items-center justify-center text-xl shrink-0 shadow-sm">
            🌊
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-base font-bold text-slate-900">
                กล้อง CCTV เฝ้าระวังพื้นที่เสี่ยงน้ำท่วม
              </h2>
              <Badge tone="red" dot className="bg-red-50 text-red-700 border-red-200 font-semibold">
                สดจากโทรมาตรน้ำ & CCTV
              </Badge>
            </div>
            <p className="text-xs text-slate-600 mt-0.5">
              ตรวจจับพื้นที่เสี่ยงน้ำล้นตลิ่ง แม่น้ำเจ้าพระยาและคลองสายหลัก เชื่อมโยงภาพสดจากกล้อง กทม.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <Button
            size="sm"
            variant="secondary"
            onClick={() => onNavigate && onNavigate('water')}
            className="border-cyan-300 text-cyan-800 hover:bg-cyan-50 text-xs"
          >
            📊 ดูภาพรวมน้ำท่วม
          </Button>
          <Button
            size="sm"
            variant="primary"
            onClick={() => onNavigate && onNavigate('map')}
            className="bg-cyan-600 border-cyan-600 hover:bg-cyan-700 text-xs"
          >
            🗺️ ดูหมุดบนแผนที่
          </Button>
        </div>
      </div>

      {/* Telemetry Alert Banner */}
      <div className="mt-3.5 grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
        <div className="rounded-lg bg-red-50 border border-red-200 p-2.5 flex items-start gap-2">
          <span className="text-base shrink-0 leading-none">🔴</span>
          <div className="min-w-0">
            <span className="font-bold text-red-900">
              จุดวิกฤตล้นตลิ่ง ({overflowStations.length} จุด):
            </span>{' '}
            <span className="text-red-800">
              {overflowStations.slice(0, 3).map((s) => `${s.name} (${Math.round(s.storagePct)}%)`).join(' · ') ||
                'ไม่มีจุดล้นตลิ่ง'}
            </span>
          </div>
        </div>

        <div className="rounded-lg bg-amber-50 border border-amber-200 p-2.5 flex items-start gap-2">
          <span className="text-base shrink-0 leading-none">🟠</span>
          <div className="min-w-0">
            <span className="font-bold text-amber-900">
              จุดเฝ้าระวังสูง ({highStations.length} จุด):
            </span>{' '}
            <span className="text-amber-800 truncate block">
              {highStations.slice(0, 4).map((s) => `${s.name} (${Math.round(s.storagePct)}%)`).join(' · ') ||
                'ปกติ'}
            </span>
          </div>
        </div>
      </div>

      {/* Filter Tabs & Camera Counter */}
      <div className="mt-4 flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => setFilterTab('all')}
            className={`px-3 py-1 rounded-lg text-xs font-medium border transition-colors ${
              filterTab === 'all'
                ? 'bg-slate-900 text-white border-slate-900'
                : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50'
            }`}
          >
            ทั้งหมด ({floodRiskCameras.length})
          </button>
          <button
            type="button"
            onClick={() => setFilterTab('overflow')}
            className={`px-3 py-1 rounded-lg text-xs font-medium border transition-colors ${
              filterTab === 'overflow'
                ? 'bg-red-600 text-white border-red-600'
                : 'bg-white text-red-700 border-red-200 hover:bg-red-50'
            }`}
          >
            🔴 เสี่ยงล้นตลิ่ง ({floodRiskCameras.filter((c) => c.floodRisk?.isOverflow).length})
          </button>
          <button
            type="button"
            onClick={() => setFilterTab('high')}
            className={`px-3 py-1 rounded-lg text-xs font-medium border transition-colors ${
              filterTab === 'high'
                ? 'bg-amber-600 text-white border-amber-600'
                : 'bg-white text-amber-700 border-amber-200 hover:bg-amber-50'
            }`}
          >
            🟠 เฝ้าระวังสูง ({floodRiskCameras.filter((c) => !c.floodRisk?.isOverflow).length})
          </button>
        </div>

        <span className="text-[11px] text-slate-500">
          แสดงจุดที่มีกล้อง CCTV กทม. ในรัศมีตรวจวัดน้ำ
        </span>
      </div>

      {/* Camera Video / Snapshot Cards Grid */}
      {loading ? (
        <div className="py-12 text-center text-sm text-slate-500">
          กำลังโหลดข้อมูลสถานการณ์น้ำและกล้อง CCTV...
        </div>
      ) : displayCameras.length === 0 ? (
        <div className="py-8 text-center text-sm text-slate-500 bg-slate-50 rounded-xl mt-3 border border-slate-200">
          ไม่พบกล้องในเงื่อนไขที่เลือก
        </div>
      ) : (
        <div className="mt-3.5 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
          {displayCameras.map((cam) => {
            const risk = cam.floodRisk;
            const isOverflow = risk?.isOverflow;
            const snapshotUrl = getBmaSnapshotUrl(cam.camid, false, refreshKey);

            return (
              <div
                key={cam.camid}
                className={`group rounded-xl border bg-white overflow-hidden transition-all duration-200 hover:shadow-md flex flex-col ${
                  isOverflow ? 'border-red-200 hover:border-red-400' : 'border-amber-200 hover:border-amber-400'
                }`}
              >
                {/* Snapshot Image with live badge */}
                <div className="relative aspect-video bg-slate-100 overflow-hidden">
                  <img
                    src={snapshotUrl}
                    alt={cam.short_title || cam.title}
                    loading="lazy"
                    className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                    onError={(e) => {
                      e.target.onerror = null;
                      e.target.src =
                        'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180" viewBox="0 0 320 180"><rect width="100%" height="100%" fill="%23f1f5f9"/><text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" fill="%2394a3b8" font-size="14">ภาพกล้อง CCTV ขอพักครู่หนึ่ง</text></svg>';
                    }}
                  />
                  <div className="absolute top-2 left-2 flex items-center gap-1.5">
                    <span
                      className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-bold text-white shadow-sm ${
                        isOverflow ? 'bg-red-600' : 'bg-amber-600'
                      }`}
                    >
                      {isOverflow ? '🚨 ล้นตลิ่ง' : '⚠️ เฝ้าระวัง'}
                    </span>
                    <span className="bg-slate-900/75 backdrop-blur-sm text-[10px] text-white font-mono px-1.5 py-0.5 rounded">
                      กล้อง #{cam.camid}
                    </span>
                  </div>

                  <button
                    type="button"
                    onClick={() => setActiveModalCam(cam)}
                    className="absolute inset-0 bg-slate-900/20 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center text-white text-xs font-semibold backdrop-blur-[1px]"
                  >
                    🔍 ขยายดูภาพสด
                  </button>
                </div>

                {/* Content */}
                <div className="p-3 flex-1 flex flex-col justify-between">
                  <div>
                    <div className="flex items-center justify-between gap-1 mb-1">
                      <span className="text-[11px] font-semibold text-cyan-800 bg-cyan-50 px-1.5 py-0.5 rounded">
                        {cam.district || 'กทม.'}
                      </span>
                      <span className="text-[10px] text-slate-500">
                        {risk.distanceKm ? `ห่าง ${risk.distanceKm} กม.` : ''}
                      </span>
                    </div>

                    <h4
                      className="text-xs font-bold text-slate-900 line-clamp-1 group-hover:text-cyan-700 transition-colors"
                      title={cam.short_title || cam.title}
                    >
                      {cam.short_title || cam.title}
                    </h4>

                    {/* Water station & storage bar */}
                    <div className="mt-2 p-2 rounded-lg bg-slate-50 border border-slate-100 text-[11px]">
                      <div className="flex items-center justify-between gap-1 mb-1">
                        <span className="text-slate-600 truncate">
                          {risk.stationName}
                        </span>
                        <span
                          className={`font-bold shrink-0 ${
                            isOverflow ? 'text-red-600' : 'text-amber-600'
                          }`}
                        >
                          {risk.storagePct}%
                        </span>
                      </div>
                      {/* Mini capacity bar */}
                      <div className="w-full bg-slate-200 h-1.5 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full ${
                            isOverflow ? 'bg-red-500' : 'bg-amber-500'
                          }`}
                          style={{ width: `${Math.min(100, risk.storagePct)}%` }}
                        />
                      </div>
                    </div>
                  </div>

                  {/* Action Buttons */}
                  <div className="mt-3 grid grid-cols-2 gap-1.5">
                    <button
                      type="button"
                      onClick={() => setActiveModalCam(cam)}
                      className="cursor-pointer inline-flex items-center justify-center gap-1 rounded-lg border border-slate-200 bg-white py-1.5 text-[11px] font-medium text-slate-700 hover:bg-slate-50 transition-colors"
                    >
                      📹 ดูภาพสด
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        if (onAsk) {
                          onAsk(`ตรวจสอบสถานการณ์น้ำท่วมและระดับน้ำที่กล้อง ${cam.short_title || cam.title}`);
                        } else if (onOpenAI) {
                          onOpenAI(cam.camid);
                        }
                      }}
                      className="cursor-pointer inline-flex items-center justify-center gap-1 rounded-lg border border-cyan-300 bg-cyan-50 py-1.5 text-[11px] font-semibold text-cyan-800 hover:bg-cyan-100 transition-colors"
                    >
                      🤖 ถาม AI
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Fullscreen / Modal Live Preview */}
      {activeModalCam && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/70 backdrop-blur-sm p-4">
          <div className="bg-white rounded-2xl max-w-2xl w-full overflow-hidden shadow-2xl border border-slate-200 animate-in fade-in zoom-in-95 duration-150">
            <div className="p-4 border-b border-slate-100 flex items-center justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <span
                    className={`text-xs px-2 py-0.5 rounded-md font-bold text-white ${
                      activeModalCam.floodRisk?.isOverflow ? 'bg-red-600' : 'bg-amber-600'
                    }`}
                  >
                    {activeModalCam.floodRisk?.badgeText}
                  </span>
                  <h3 className="text-sm font-bold text-slate-900">
                    {activeModalCam.short_title || activeModalCam.title}
                  </h3>
                </div>
                <p className="text-xs text-slate-500 mt-0.5">
                  {activeModalCam.district} · ใกล้{activeModalCam.floodRisk?.stationName} (
                  {activeModalCam.floodRisk?.storagePct}%)
                </p>
              </div>
              <button
                type="button"
                onClick={() => setActiveModalCam(null)}
                className="w-8 h-8 rounded-full bg-slate-100 hover:bg-slate-200 flex items-center justify-center text-slate-600 text-base"
              >
                ✕
              </button>
            </div>

            <div className="relative aspect-video bg-black flex items-center justify-center">
              <img
                src={getBmaSnapshotUrl(activeModalCam.camid, true, Date.now())}
                alt={activeModalCam.short_title}
                className="w-full h-full object-contain"
              />
            </div>

            <div className="p-4 bg-slate-50 flex items-center justify-between gap-3">
              <span className="text-xs text-slate-600">
                สตรีมภาพสดจากสำนักการจราจรและขนส่ง (สจส.) กทม.
              </span>
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => {
                    if (onOpenAI) onOpenAI(activeModalCam.camid);
                    setActiveModalCam(null);
                  }}
                >
                  🚀 เปิดวิเคราะห์ YOLO
                </Button>
                <Button
                  size="sm"
                  variant="primary"
                  onClick={() => {
                    if (onAsk) {
                      onAsk(`ตรวจสอบระดับน้ำและสภาพน้ำท่วมขังที่กล้อง ${activeModalCam.short_title || activeModalCam.title}`);
                    }
                    setActiveModalCam(null);
                  }}
                >
                  💬 ถามผู้ช่วย AI
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}
