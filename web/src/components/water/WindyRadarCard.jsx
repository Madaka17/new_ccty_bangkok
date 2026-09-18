import { useState } from 'react';
import { Card, Badge } from '../dashboard/ui.jsx';

export default function WindyRadarCard() {
  const [overlay, setOverlay] = useState('radar'); // 'radar', 'wind', 'satellite'

  const getEmbedUrl = () => {
    const base = 'https://embed.windy.com/embed2.html?lat=13.750&lon=100.500&detailLat=13.750&detailLon=100.500&width=650&height=480&zoom=8&level=surface';
    const params = {
      radar: '&overlay=radar&product=radar&menu=&message=true&marker=&calendar=now&pressure=&type=map&location=coordinates&detail=&metricWind=default&metricTemp=default&radarRange=-1',
      wind: '&overlay=wind&product=ecmwf&menu=&message=true&marker=&calendar=now&pressure=&type=map&location=coordinates&detail=&metricWind=default&metricTemp=default&radarRange=-1',
      satellite: '&overlay=satellite&product=satellite&menu=&message=true&marker=&calendar=now&pressure=&type=map&location=coordinates&detail=&metricWind=default&metricTemp=default&radarRange=-1',
    };
    return `${base}${params[overlay] || params.radar}`;
  };

  return (
    <Card className="p-4 flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <h2 className="text-base font-semibold text-slate-100 flex items-center gap-1.5">
            <span>🛰️</span> เรดาร์สภาพอากาศและกลุ่มฝน (Windy)
          </h2>
          <Badge tone="blue" dot>
            สด Live
          </Badge>
        </div>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => setOverlay('radar')}
            className={`cursor-pointer px-2.5 py-1 text-xs rounded-lg font-medium transition-colors ${
              overlay === 'radar' ? 'bg-blue-600 text-white shadow-sm' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
            }`}
          >
            🌧️ เรดาร์ฝน
          </button>
          <button
            type="button"
            onClick={() => setOverlay('wind')}
            className={`cursor-pointer px-2.5 py-1 text-xs rounded-lg font-medium transition-colors ${
              overlay === 'wind' ? 'bg-blue-600 text-white shadow-sm' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
            }`}
          >
            💨 ทิศทางลม
          </button>
          <button
            type="button"
            onClick={() => setOverlay('satellite')}
            className={`cursor-pointer px-2.5 py-1 text-xs rounded-lg font-medium transition-colors ${
              overlay === 'satellite' ? 'bg-blue-600 text-white shadow-sm' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
            }`}
          >
            ☁️ ดาวเทียม
          </button>
          <a
            href="https://www.windy.com/th/-%E0%B9%80%E0%B8%A3%E0%B8%94%E0%B8%B2%E0%B8%A3%E0%B9%8C%E0%B8%AA%E0%B8%A0%E0%B8%B2%E0%B8%9E%E0%B8%AD%E0%B8%B2%E0%B8%81%E0%B8%B2%E0%B8%A8-radar?radar,13.750,100.500,8"
            target="_blank"
            rel="noopener noreferrer"
            className="ml-1 text-xs text-slate-400 hover:text-blue-400 transition-colors inline-flex items-center gap-0.5"
            title="เปิดบนเว็บไซต์ Windy.com ในแท็บใหม่"
          >
            Windy.com ↗
          </a>
        </div>
      </div>

      <div className="w-full h-[460px] rounded-xl overflow-hidden border border-slate-700/60 bg-slate-950 relative shadow-inner">
        <iframe
          key={overlay}
          src={getEmbedUrl()}
          width="100%"
          height="100%"
          frameBorder="0"
          title="Windy Weather Radar"
          loading="lazy"
          className="w-full h-full block"
        />
      </div>
      <div className="flex items-center justify-between text-[11px] text-slate-400 px-1">
        <span>ข้อมูลพยากรณ์และเรดาร์สดจาก Windy.com · พิกัดกรุงเทพมหานครและปริมณฑล</span>
        <span>กดปุ่ม Play ด้านล่างของแผนที่เพื่อดูแอนิเมชันการเคลื่อนที่ของกลุ่มฝน</span>
      </div>
    </Card>
  );
}
