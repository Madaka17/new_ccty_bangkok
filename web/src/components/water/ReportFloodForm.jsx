// The form of the แจ้งน้ำท่วม page. The pin is placed on the page's map (tap it, drag the pin, or
// "ตำแหน่งของฉัน"); this collects how deep, an optional photo and a short note, shrinks the photo in the
// browser and sends it. The server checks it with AI before it reaches the maps; the page shows the result.
import { useState } from 'react';
import { postUserReport } from '../../lib/api.js';
import { Button, FOCUS } from '../dashboard/ui.jsx';

const DEPTHS = [
  ['ankle', 'ตาตุ่ม', '~10 ซม.'],
  ['shin', 'ครึ่งแข้ง', '~25 ซม.'],
  ['knee', 'เข่า', '~45 ซม.'],
  ['thigh', 'เลยเข่า', '60+ ซม.'],
];
const PHOTO_SIDE = 1600;

// A JPEG data: URL at most PHOTO_SIDE px: a small upload, and the canvas leaves the phone's EXIF (GPS) behind
async function shrinkPhoto(file) {
  try {
    const bmp = await createImageBitmap(file, { imageOrientation: 'from-image' });
    const s = Math.min(1, PHOTO_SIDE / Math.max(bmp.width, bmp.height));
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(bmp.width * s);
    canvas.height = Math.round(bmp.height * s);
    canvas.getContext('2d').drawImage(bmp, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL('image/jpeg', 0.85);
  } catch {
    // a format this browser cannot draw: send it as it is and let the server try
    return new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => resolve(r.result);
      r.onerror = reject;
      r.readAsDataURL(file);
    });
  }
}

export default function ReportFloodForm({ pin, locating, onUseMyLocation, onSent }) {
  const [depth, setDepth] = useState('');
  const [photo, setPhoto] = useState(null);
  const [note, setNote] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');

  const pickPhoto = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setPhoto(await shrinkPhoto(file));
  };

  const send = async () => {
    setSending(true);
    setError('');
    try {
      const r = await postUserReport({ lat: pin.lat, lng: pin.lng, depth, note: note.trim(), photo });
      if (r.status === 'rejected') setError(r.message);
      else onSent({ ...r, photo });
    } catch (err) {
      setError(err.message);
    } finally {
      setSending(false);
    }
  };

  return (
    <form
      className="rounded-lg border border-slate-200 bg-white p-4 text-sm flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (pin && depth && !sending) send();
      }}
    >
      <div>
        <p className="text-xs font-medium text-slate-700">1. ตำแหน่ง</p>
        <p className={`text-xs mt-0.5 ${pin ? 'text-emerald-700' : 'text-slate-500'}`}>
          {pin ? `ปักหมุดแล้ว ${pin.lat.toFixed(5)}, ${pin.lng.toFixed(5)} · แตะแผนที่หรือลากหมุดเพื่อขยับ` : 'แตะแผนที่ตรงจุดที่น้ำท่วม หรือกดปุ่มด้านล่างเพื่อใช้ตำแหน่งที่ยืนอยู่'}
        </p>
        <Button type="button" size="sm" variant="secondary" className="mt-1.5" onClick={onUseMyLocation} loading={locating}>📍 ตำแหน่งของฉัน</Button>
      </div>

      <fieldset>
        <legend className="text-xs font-medium text-slate-700">2. น้ำสูงแค่ไหน</legend>
        <div className="mt-1.5 grid grid-cols-2 gap-1.5">
          {DEPTHS.map(([k, label, cm]) => (
            <button
              key={k}
              type="button"
              aria-pressed={depth === k}
              onClick={() => setDepth(k)}
              className={`rounded-lg border px-2 py-1.5 text-left ${FOCUS} ${depth === k ? 'border-blue-600 bg-blue-50 text-blue-800' : 'border-slate-200 text-slate-700 hover:border-slate-400'}`}
            >
              <span className="block text-sm font-medium">{label}</span>
              <span className="block text-[11px] text-slate-500">{cm}</span>
            </button>
          ))}
        </div>
      </fieldset>

      <div>
        <p className="text-xs font-medium text-slate-700">3. รูปถ่าย (ไม่บังคับ แต่ช่วยให้คนอื่นเชื่อ)</p>
        {/* the real input is hidden; the label is the button, so it reads the same in light and dark themes */}
        <input id="report-photo" type="file" accept="image/*" capture="environment" onChange={pickPhoto} className="peer sr-only" />
        <label htmlFor="report-photo" className={`mt-1.5 inline-flex items-center gap-1.5 h-8 px-3 rounded-lg border border-slate-300 bg-white text-xs font-medium text-slate-800 cursor-pointer hover:bg-slate-50 peer-focus-visible:ring-2 peer-focus-visible:ring-blue-600 peer-focus-visible:ring-offset-2`}>
          📷 {photo ? 'เปลี่ยนรูป' : 'ถ่ายรูป / เลือกรูป'}
        </label>
        {photo && (
          <div className="mt-1.5 relative">
            <img src={photo} alt="รูปที่จะส่ง" className="w-full max-h-40 object-cover rounded-md" />
            <button type="button" onClick={() => setPhoto(null)} className={`absolute top-1 right-1 rounded-md bg-white/90 px-2 py-0.5 text-[11px] text-slate-700 ${FOCUS}`}>ลบรูป</button>
          </div>
        )}
      </div>

      <div>
        <label htmlFor="report-note" className="text-xs font-medium text-slate-700">4. บอกจุดเพิ่ม (ไม่บังคับ)</label>
        <input
          id="report-note"
          type="text"
          value={note}
          maxLength={100}
          onChange={(e) => setNote(e.target.value)}
          placeholder="เช่น หน้าปากซอยลาดพร้าว 101"
          className={`mt-1.5 h-9 w-full rounded-lg border border-slate-300 bg-white px-2.5 text-sm text-slate-800 ${FOCUS}`}
        />
      </div>

      {error && <p role="alert" className="rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-2 text-xs text-amber-800">{error}</p>}

      <Button type="submit" variant="primary" disabled={!pin || !depth} loading={sending}>
        {sending ? (photo ? 'กำลังส่ง · AI กำลังตรวจรูป' : 'กำลังส่ง') : 'ส่งรายงาน'}
      </Button>
      {(!pin || !depth) && <p className="-mt-2 text-[11px] text-slate-500">{!pin ? 'ปักหมุดตำแหน่งก่อน' : 'เลือกระดับน้ำก่อน'} จึงจะส่งได้</p>}
      <p className="text-[11px] text-slate-500 leading-4">
        รายงานขึ้นแผนที่ 6 ชั่วโมงในชื่อ "ประชาชนแจ้ง ยังไม่ยืนยัน" · AI ตรวจรูปก่อนขึ้น · ไม่เก็บชื่อ เบอร์โทร หรือข้อมูลพิกัดในไฟล์รูป
      </p>
    </form>
  );
}
