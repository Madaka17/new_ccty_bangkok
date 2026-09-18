import { AnimatePresence, motion } from 'framer-motion';
import VideoSlot from './VideoSlot.jsx';

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
 className="glass rounded-xl h-full min-h-[360px] flex flex-col items-center justify-center text-center px-6"
      >
        <h2 className="text-xl font-semibold text-slate-900">ยังไม่ได้เปิดกล้อง</h2>
        <p className="mt-2 max-w-sm text-ink-600">
          ติ๊กเลือกกล้องจากรายการด้านซ้าย ภาพสดจะแสดงตรงนี้ เปิดพร้อมกันได้ 9 กล้อง
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
