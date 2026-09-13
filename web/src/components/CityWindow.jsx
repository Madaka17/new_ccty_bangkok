import { AnimatePresence, motion } from 'framer-motion';
import VideoSlot from './VideoSlot.jsx';
import { CameraIcon } from './Icons.jsx';

function gridClass(n) {
  if (n <= 1) return 'grid-cols-1';
  if (n <= 4) return 'grid-cols-1 md:grid-cols-2';
  return 'grid-cols-1 md:grid-cols-2 xl:grid-cols-3';
}

export default function CityWindow({ cameras, camStatus = {}, incidents, onClose, onOpenAI }) {
  if (cameras.length === 0) {
    return (
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="glass rounded-[2rem] h-full min-h-[360px] flex flex-col items-center justify-center text-center px-6"
      >
        <div className="w-24 h-24 rounded-full bg-lavender-50 border border-lavender-100 flex items-center justify-center mb-4">
          <CameraIcon className="w-11 h-11" />
        </div>
        <h2 className="font-serif text-2xl font-semibold text-ink-900">หน้าต่างเมืองของคุณ</h2>
        <p className="mt-2 max-w-sm text-ink-600">
          ติ๊กเลือกกล้องจากช่องมองภาพด้านซ้าย ภาพสดจะมาปรากฏตรงนี้ เลือกได้สูงสุด 9 กล้อง
        </p>
      </motion.div>
    );
  }

  return (
    <div className={`grid gap-4 ${gridClass(cameras.length)} auto-rows-[minmax(260px,1fr)]`}>
      <AnimatePresence>
        {cameras.map((cam) => (
          <VideoSlot
            key={cam.camid}
            cam={cam}
            status={camStatus[cam.camid]}
            incident={(incidents?.camera || []).find((i) => i.camid === cam.camid)}
            onClose={() => onClose(cam.camid)}
            onOpenAI={() => onOpenAI(cam.camid)}
          />
        ))}
      </AnimatePresence>
    </div>
  );
}
