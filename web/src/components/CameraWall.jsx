// Live camera page: every camera in the country, picked by search, region and province, under two tabs: a wall of
// tiles (six to a row on a wide screen) and a map with the cameras on screen beside it.
// The tiles are in cameras/Tiles.jsx. A tap opens the camera large, where it can be liked or kept open on top.
import { lazy, Suspense, useCallback, useMemo, useState } from 'react';
import { Skeleton } from './dashboard/ui.jsx';
import ViewSwitch from './ViewSwitch.jsx';
import { distanceKm } from '../lib/store.js';
import CamTile from './cameras/Tiles.jsx';
import useFlood from './cameras/useFlood.js';
import RegionPicker, { inPlace } from './cameras/RegionPicker.jsx';
import FocusView from './cameras/FocusView.jsx';

const MapPanel = lazy(() => import('./cameras/MapPanel.jsx'));   // maplibre loads with the map tab only
const VIEW_KEY = 'camwall_view';   // the tab this viewer had open last time

function readView() {
  try {
    return localStorage.getItem(VIEW_KEY) === 'map' ? 'map' : 'wall';
  } catch {
    return 'wall';
  }
}

const CHIP_OFF = 'bg-white text-slate-700 border-slate-300 hover:bg-slate-50';
const CHIP_ON = 'bg-blue-600 text-white border-blue-600';
const CHIPS = [
  { id: 'all', label: 'ทั้งหมด' },
  { id: 'bkk', label: 'กรุงเทพฯ' },
  { id: 'near', label: 'ใกล้ฉัน' },
  { id: 'fav', label: 'รายการโปรด' },
];
const GRID = 'grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-3';
function Section({ id, title, hint, count, loading, children }) {
  return (
    <section aria-labelledby={id} className="flex flex-col gap-3">
      <div>
        <h2 id={id} className="text-[15px] font-semibold text-slate-900">
          {title} <span className="text-sm font-normal text-slate-500">{loading ? '' : `${count} กล้อง`}</span>
        </h2>
        <p className="text-[13px] text-slate-600">{hint}</p>
      </div>
      {loading ? (
        <div className={GRID}>{Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="aspect-video rounded-xl" />)}</div>
      ) : count ? (
        children
      ) : (
        <p className="text-sm text-slate-500 py-4">ไม่มีกล้องที่ตรงกับที่ค้นหา</p>
      )}
    </section>
  );
}

export default function CameraWall({
  cameras,
  loading,
  camStatus = {},
  incidents,
  favorites,
  active,
  filter,
  onFilter,
  query,
  onQuery,
  userPos,
  onToggleActive,
  onToggleFav,
  onOpenAI,
  aiIds,
}) {
  const [focus, setFocus] = useState(null);
  const [view, setView] = useState(readView);
  const flood = useFlood();
  const pickView = (id) => {
    setView(id);
    try {
      localStorage.setItem(VIEW_KEY, id);
    } catch {}
  };
  const [region, setRegion] = useState('');
  const [province, setProvince] = useState('');
  const list = useMemo(() => {
    let out = cameras;
    if (filter === 'bkk') out = out.filter((c) => c.province === 'กรุงเทพมหานคร');
    if (filter === 'fav') out = out.filter((c) => favorites.has(c.camid));
    if (query.trim()) {
      const q = query.trim().toLowerCase();
      out = out.filter((c) => `${c.title} ${c.short_title} ${c.province} ${c.camid}`.toLowerCase().includes(q));
    }
    if (filter === 'near' && userPos) {
      out = out
        .filter((c) => c.latitude && c.longitude)
        .map((c) => ({ ...c, _km: distanceKm(userPos, { lat: c.latitude, lng: c.longitude }) }))
        .sort((a, b) => a._km - b._km);
    }
    return out;
  }, [cameras, favorites, filter, query, userPos]);
  const nation = useMemo(
    () => list.filter((c) => inPlace(c, region, province)),
    [list, region, province],
  );
  const pickRegion = (r) => {
    setRegion(r);
    setProvince('');
  };
  const pinned = useMemo(() => new Set(active), [active]);
  const close = useCallback(() => setFocus(null), []);

  return (
    <div className="flex flex-col gap-4">
      <ViewSwitch
        label="มุมมองกล้อง"
        value={view}
        onChange={pickView}
        tabs={[
          { id: 'wall', label: 'ช่องกล้อง', icon: 'cameras', hint: 'กล้องทุกตัวเรียงเป็นช่อง' },
          { id: 'map', label: 'แผนที่', icon: 'cammap', hint: 'กล้องบนแผนที่ พร้อมเรดาร์ฝน และช่องกล้องในกรอบแผนที่' },
        ]}
      />
      <div className="glass rounded-xl p-4 flex flex-col gap-3">
        <label htmlFor="cam-search" className="sr-only">ค้นหาถนนหรือแยก</label>
        <input
          id="cam-search"
          type="search"
          value={query}
          onChange={(e) => onQuery(e.target.value)}
          placeholder="ค้นหาถนนหรือแยก..."
          className="w-full rounded-lg bg-white border border-slate-300 px-4 py-2.5 text-base text-ink-900 placeholder:text-ink-400 outline-none focus:border-blue-500"
        />
        <div className="flex flex-wrap items-center gap-2">
          {CHIPS.map((chip) => (
            <button
              key={chip.id}
              type="button"
              onClick={() => onFilter(chip.id)}
              aria-pressed={filter === chip.id}
              className={`cursor-pointer inline-flex items-center gap-1.5 rounded-lg border px-3 h-8 text-xs font-medium transition-colors duration-200 ${filter === chip.id ? CHIP_ON : CHIP_OFF}`}
            >
              {chip.label}
              {chip.id === 'fav' && favorites.size > 0 && <span className="rounded-lg bg-white px-1.5 text-xs text-ink-900">{favorites.size}</span>}
            </button>
          ))}
          <span className="ml-auto text-xs text-slate-600">
            {loading ? 'กำลังโหลดรายชื่อกล้อง...' : `พบ ${nation.length} กล้อง`}
            {filter === 'near' && !userPos && ' (กำลังหาตำแหน่งของคุณ...)'}
          </span>
        </div>
        <div className="border-t border-slate-200 pt-3">
          <RegionPicker cameras={list} region={region} province={province} onRegion={pickRegion} onProvince={setProvince} />
        </div>
      </div>

      <Section id="wall-nation" title={province ? `กล้องใน${province}` : region ? `กล้องใน${region}` : 'กล้องทั่วประเทศ'} count={nation.length} loading={loading}
        hint={view === 'map'
          ? 'แตะวงกลมตัวเลขเพื่อซูมเข้า แตะจุดหรือช่องกล้องข้างแผนที่เพื่อดูภาพใหญ่'
          : 'กล้องจาก iTIC กรมทางหลวง กทม. เมืองพัทยา เทศบาล กรมทรัพยากรน้ำ และเขื่อน แตะช่องกล้องเพื่อดูภาพใหญ่'}>
        {/* only the open tab is on the page: the other one plays and loads nothing */}
        {view === 'map' ? (
          <Suspense fallback={<Skeleton className="h-[70vh] rounded-xl" />}>
            <MapPanel cameras={nation} flood={flood} pinned={pinned} onOpen={setFocus} frameKey={`${region}|${province}|${filter}|${query}`} />
          </Suspense>
        ) : (
          <div className={GRID}>
            {nation.map((cam) => <CamTile key={cam.camid} cam={cam} pinned={pinned.has(cam.camid)} flood={flood.get(cam.camid)} onOpen={setFocus} />)}
          </div>
        )}
      </Section>

      {focus && (
        <FocusView
          cam={focus}
          onClose={close}
          camStatus={camStatus}
          incidents={incidents}
          pinned={pinned.has(focus.camid)}
          fav={favorites.has(focus.camid)}
          onTogglePin={() => onToggleActive(focus.camid)}
          onToggleFav={() => onToggleFav(focus.camid)}
          onOpenAI={!aiIds || aiIds.has(focus.camid) ? () => onOpenAI(focus.camid) : null}
        />
      )}
    </div>
  );
}
