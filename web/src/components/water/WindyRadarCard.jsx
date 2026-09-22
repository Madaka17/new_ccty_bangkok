import { useState } from 'react';
import { Card, Badge } from '../dashboard/ui.jsx';

const OVERLAYS = {
  radar: { label: '🌧️ เรดาร์ฝน', product: 'radar' },
  rain: { label: '☔ ฝนสะสม', product: 'ecmwf' },
  wind: { label: '💨 ทิศทางลม', product: 'ecmwf' },
  waves: { label: '🌊 คลื่น', product: 'ecmwfWaves' },
  satellite: { label: '☁️ ดาวเทียม', product: 'satellite' },
};
const COMMON = '&menu=&message=true&marker=&calendar=now&pressure=&type=map&location=coordinates&detail=&metricWind=default&metricTemp=default&radarRange=-1';

// Windy embed. `overlays` picks which layer buttons show; `lat/lon/zoom` set the initial view.
export default function WindyRadarCard({
  title = 'เรดาร์สภาพอากาศและกลุ่มฝน (Windy)',
  overlays = ['radar', 'wind', 'satellite'],
  defaultOverlay = 'radar',
  lat = 13.75,
  lon = 100.5,
  zoom = 8,
}) {
  const [overlay, setOverlay] = useState(defaultOverlay);

  const getEmbedUrl = () => {
    const o = OVERLAYS[overlay] || OVERLAYS.radar;
    return `https://embed.windy.com/embed2.html?lat=${lat}&lon=${lon}&detailLat=${lat}&detailLon=${lon}&width=650&height=480&zoom=${zoom}&level=surface&overlay=${overlay}&product=${o.product}${COMMON}`;
  };
  const siteUrl = `https://www.windy.com/?${overlay},${lat},${lon},${zoom}`;

  return (
    <Card className="p-4 flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <h2 className="text-base font-semibold text-slate-100 flex items-center gap-1.5">
            <span>🛰️</span> {title}
          </h2>
          <Badge tone="blue" dot>
            สด Live
          </Badge>
        </div>
        <div className="flex items-center gap-1.5">
          {overlays.map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => setOverlay(k)}
              className={`cursor-pointer px-2.5 py-1 text-xs rounded-lg font-medium transition-colors ${
                overlay === k ? 'bg-blue-600 text-white shadow-sm' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
              }`}
            >
              {OVERLAYS[k]?.label || k}
            </button>
          ))}
          <a
            href={siteUrl}
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
