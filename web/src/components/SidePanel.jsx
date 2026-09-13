import { useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { FlowerIcon, StarIcon, LocateIcon } from './Icons.jsx';
import CameraCard from './CameraCard.jsx';
import { distanceKm } from '../lib/store.js';

const CHIPS = [
  { id: 'all', label: 'ทั้งหมด', tone: 'bg-apricot-100 text-apricot-700 border-apricot-200', active: 'bg-apricot-400 text-white border-apricot-400' },
  { id: 'bkk', label: 'กรุงเทพฯ', tone: 'bg-sage-100 text-sage-700 border-sage-200', active: 'bg-sage-600 text-white border-sage-600' },
  { id: 'near', label: 'ใกล้ฉัน', tone: 'bg-lavender-100 text-lavender-700 border-lavender-200', active: 'bg-lavender-600 text-white border-lavender-600', icon: LocateIcon },
  { id: 'fav', label: 'รายการโปรด', tone: 'bg-gold-100 text-gold-700 border-gold-200', active: 'bg-gold-400 text-ink-900 border-gold-400', icon: StarIcon },
];

export default function SidePanel({
  cameras,
  camStatus = {},
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
  onClearAll,
}) {
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

  return (
    <aside className="glass rounded-[2rem] flex flex-col h-full overflow-hidden">
      <div className="px-5 pt-5 pb-3">
        <h2 className="font-serif text-lg font-semibold text-ink-900">ช่องมองภาพของคุณ</h2>
        <p className="text-sm text-ink-600">เลือกกล้องที่อยากดู แล้วภาพจะมาโผล่ที่หน้าต่างเมือง</p>
      </div>

      {/* Search */}
      <div className="px-5">
        <label htmlFor="cam-search" className="sr-only">ค้นหาถนนหรือแยก</label>
        <div className="flex items-center gap-2 rounded-full bg-white/85 border border-cream-200 px-4 py-2.5 focus-within:border-lavender-400 transition-colors duration-200">
          <FlowerIcon />
          <input
            id="cam-search"
            type="search"
            value={query}
            onChange={(e) => onQuery(e.target.value)}
            placeholder="ค้นหาถนนหรือแยก..."
            className="flex-1 bg-transparent outline-none text-base text-ink-900 placeholder:text-ink-400"
          />
        </div>
      </div>

      {/* Chips */}
      <div className="px-5 pt-3 pb-2 flex flex-wrap gap-2">
        {CHIPS.map((chip) => {
          const isActive = filter === chip.id;
          const Icon = chip.icon;
          return (
            <motion.button
              key={chip.id}
              type="button"
              whileTap={{ scale: 0.95 }}
              onClick={() => onFilter(chip.id)}
              aria-pressed={isActive}
              className={`cursor-pointer inline-flex items-center gap-1.5 rounded-full border px-4 py-2 text-sm font-medium shadow-soft transition-colors duration-200 ${isActive ? chip.active : chip.tone}`}
            >
              {Icon && <Icon className="w-4 h-4" />}
              {chip.label}
              {chip.id === 'fav' && favorites.size > 0 && (
                <span className="ml-0.5 rounded-full bg-white/70 px-1.5 text-xs text-ink-900">{favorites.size}</span>
              )}
            </motion.button>
          );
        })}
      </div>

      {/* Count / clear */}
      <div className="px-5 pb-2 flex items-center justify-between text-xs text-ink-600">
        <span>
          พบ <span className="font-serif text-sm text-ink-900">{list.length}</span> กล้อง
          {filter === 'near' && !userPos && <span className="ml-1 text-lavender-700">(กำลังหาตำแหน่งของคุณ...)</span>}
        </span>
        {active.length > 0 && (
          <button type="button" onClick={onClearAll} className="cursor-pointer rounded-full px-2 py-1 hover:bg-apricot-50 hover:text-apricot-700 transition-colors duration-200">
            ปิดทุกกล้อง
          </button>
        )}
      </div>

      {/* List */}
      <div className="scroll-soft flex-1 overflow-y-auto px-3 pb-4 space-y-2">
        <AnimatePresence initial={false}>
          {list.map((cam) => (
            <motion.div
              key={cam.camid}
              layout
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.2 }}
            >
              <CameraCard
                cam={cam}
                status={camStatus[cam.camid]}
                isActive={active.includes(cam.camid)}
                isFav={favorites.has(cam.camid)}
                km={cam._km}
                onToggleActive={() => onToggleActive(cam.camid)}
                onToggleFav={() => onToggleFav(cam.camid)}
                onOpenAI={() => onOpenAI(cam.camid)}
              />
            </motion.div>
          ))}
        </AnimatePresence>
        {list.length === 0 && (
          <div className="text-center text-sm text-ink-600 py-10">
            <FlowerIcon className="w-8 h-8 mx-auto mb-2" />
            ยังไม่พบกล้องที่ตรงกัน ลองคำอื่นดูนะ
          </div>
        )}
      </div>
    </aside>
  );
}
