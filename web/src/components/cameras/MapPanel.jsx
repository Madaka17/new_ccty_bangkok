// The camera map with the cameras inside the part of the map on screen listed beside it (those the AI sees
// flooded first, then live video). Used by the map tab of the live camera page and the camera map page.
import { useMemo, useState } from 'react';
import CameraMap, { kindOf } from './CameraMap.jsx';
import CamTile from './Tiles.jsx';

const PANEL_MAX = 40;   // tiles beside the map; zoom in for the rest
const ORDER = { live: 0, still: 1, link: 2 };

export default function MapPanel({ cameras, flood, pinned, onOpen, frameKey }) {
  const [view, setView] = useState(null);   // { w, s, e, n } of the map on screen
  const inView = useMemo(() => {
    if (!view) return [];
    return cameras
      .filter((c) => c.latitude >= view.s && c.latitude <= view.n && c.longitude >= view.w && c.longitude <= view.e)
      .sort((a, b) => (flood.has(b.camid) - flood.has(a.camid)) || (ORDER[kindOf(a)] - ORDER[kindOf(b)]));
  }, [cameras, view, flood]);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_340px] gap-3">
      <CameraMap cameras={cameras} flood={flood} onOpen={onOpen} onView={setView} frameKey={frameKey} className="h-[70vh] min-h-[420px]" />
      <aside aria-label="กล้องในกรอบแผนที่" className="flex flex-col gap-2 lg:h-[70vh] lg:min-h-[420px]">
        <p className="text-xs text-slate-600">
          กล้องในกรอบแผนที่ {inView.length} กล้อง{inView.length > PANEL_MAX ? ` (แสดง ${PANEL_MAX} กล้องแรก ซูมเข้าเพื่อดูที่เหลือ)` : ''}
        </p>
        <div className="lg:flex-1 lg:min-h-0 lg:overflow-y-auto lg:pr-1">
          <div className="grid grid-cols-2 lg:grid-cols-1 gap-2">
            {inView.slice(0, PANEL_MAX).map((cam) => (
              <CamTile key={cam.camid} cam={cam} pinned={pinned.has(cam.camid)} flood={flood.get(cam.camid)} onOpen={onOpen} />
            ))}
          </div>
        </div>
      </aside>
    </div>
  );
}
