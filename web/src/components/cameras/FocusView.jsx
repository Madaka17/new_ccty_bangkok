// A camera opened large over the page (live camera page, camera map): the picture, plus like and keep-open buttons.
import { useEffect } from 'react';
import VideoSlot from '../VideoSlot.jsx';
import { Button } from '../dashboard/ui.jsx';

export default function FocusView({ cam, onClose, camStatus, incidents, pinned, fav, onTogglePin, onToggleFav, onOpenAI }) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  return (
    <div role="dialog" aria-modal="true" aria-label={cam.short_title || cam.title} className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6">
      <button type="button" aria-label="ปิดภาพใหญ่" onClick={onClose} className="absolute inset-0 bg-slate-900/70 cursor-pointer" />
      <div className="relative w-full max-w-4xl flex flex-col gap-2">
        <div className="grid h-[60vh] sm:h-[70vh]">
          <VideoSlot
            cam={cam}
            status={camStatus[cam.camid]}
            incident={(incidents?.camera || []).find((i) => i.camid === cam.camid)}
            onClose={onClose}
            onOpenAI={onOpenAI}
          />
        </div>
        <div className="flex flex-wrap justify-end gap-2">
          <Button size="sm" onClick={onToggleFav}>{fav ? 'เอาออกจากรายการโปรด' : 'เพิ่มในรายการโปรด'}</Button>
          <Button size="sm" variant={pinned ? 'secondary' : 'primary'} onClick={onTogglePin}>
            {pinned ? 'เลิกเปิดค้างไว้' : 'เปิดค้างไว้ด้านบน'}
          </Button>
        </div>
      </div>
    </div>
  );
}

