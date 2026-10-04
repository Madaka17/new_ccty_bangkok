import { useEffect, useState } from 'react';
import { fetchReportLocations, postUserReport } from '../../lib/api.js';
import { Button, FOCUS } from '../dashboard/ui.jsx';

const DEPTHS = [['ankle', 'ข้อเท้า'], ['shin', 'หน้าแข้ง'], ['chest', 'อก']];
const NOTE_MAX = 2000;
const FIELD = `mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-base text-slate-800 ${FOCUS}`;

async function shrinkPhoto(file) {
  if (!file.type.startsWith('image/')) throw new Error('กรุณาเลือกไฟล์รูปภาพ');
  if (file.size > 20 * 1024 * 1024) throw new Error('เลือกรูปขนาดไม่เกิน 20 MB');
  const bmp = await createImageBitmap(file, { imageOrientation: 'from-image' });
  try {
    const scale = Math.min(1, 1600 / Math.max(bmp.width, bmp.height));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(bmp.width * scale));
    canvas.height = Math.max(1, Math.round(bmp.height * scale));
    canvas.getContext('2d').drawImage(bmp, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL('image/jpeg', 0.85);
  } finally {
    bmp.close();
  }
}

export default function ReportFloodForm({ pin, locating, onUseMyLocation, onPinChange, onAreaChange, onSent }) {
  const [locations, setLocations] = useState(null);
  const [locationError, setLocationError] = useState('');
  const [retry, setRetry] = useState(0);
  const [province, setProvince] = useState('');
  const [district, setDistrict] = useState('');
  const [latitude, setLatitude] = useState('');
  const [longitude, setLongitude] = useState('');
  const [depth, setDepth] = useState('');
  const [photo, setPhoto] = useState(null);
  const [photoBusy, setPhotoBusy] = useState(false);
  const [note, setNote] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let alive = true;
    setLocationError('');
    fetchReportLocations().then((d) => { if (alive) setLocations(d); })
      .catch((e) => { if (alive) setLocationError(e.message); });
    return () => { alive = false; };
  }, [retry]);

  useEffect(() => {
    if (pin) {
      setLatitude(pin.lat.toFixed(6));
      setLongitude(pin.lng.toFixed(6));
    }
  }, [pin]);

  const pickPhoto = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setPhotoBusy(true);
    setError('');
    try { setPhoto(await shrinkPhoto(file)); }
    catch (e) { setError(e.message.includes('เลือก') ? e.message : 'เปิดรูปนี้ไม่ได้ กรุณาเลือกรูป JPEG, PNG หรือ WebP'); }
    finally { setPhotoBusy(false); }
  };

  const useCoordinates = () => {
    const lat = Number(latitude), lng = Number(longitude);
    if (!latitude.trim() || !longitude.trim() || !Number.isFinite(lat) || !Number.isFinite(lng)
        || lat < 5.5 || lat > 20.5 || lng < 97.3 || lng > 105.7) {
      setError('กรอกละติจูดและลองจิจูดของจุดในประเทศไทยให้ถูกต้อง');
      return;
    }
    setError('');
    onPinChange({ lat, lng });
  };
  const ready = !!pin && !!province && !!district && !!depth && note.length <= NOTE_MAX;
  const send = async (e) => {
    e.preventDefault();
    if (!ready || sending || photoBusy) return;
    setSending(true);
    setError('');
    try {
      const result = await postUserReport({ lat: pin.lat, lng: pin.lng, province, district, depth, note: note.trim(), photo });
      if (result.status === 'rejected') setError(result.message);
      else onSent({ ...result, photo });
    } catch (e) { setError(e.message); }
    finally { setSending(false); }
  };

  return (
    <form onSubmit={send} className="rounded-lg border border-slate-200 bg-white p-4 text-sm">
      <h2 className="text-lg font-bold text-slate-900">แจ้งน้ำท่วมกับ BKK StreetSmart</h2>
      <p className="mt-1 text-sm text-slate-600">เลือกพื้นที่ ปักหมุด และบอกสถานการณ์ที่พบ</p>
      <fieldset disabled={sending} className="mt-4 flex min-w-0 flex-col gap-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-1 gap-3">
          <label className="text-sm font-medium text-slate-700">จังหวัด
            <select required value={province} disabled={!locations} onChange={(e) => {
              setProvince(e.target.value); setDistrict(''); setLatitude(''); setLongitude(''); onPinChange(null);
            }} className={FIELD}>
              <option value="">{locations ? 'เลือกจังหวัด' : 'กำลังโหลดจังหวัด…'}</option>
              {Object.keys(locations || {}).map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </label>
          <label className="text-sm font-medium text-slate-700">อำเภอ / เขต
            <select required value={district} disabled={!province} onChange={(e) => {
              setDistrict(e.target.value);
              setLatitude(''); setLongitude(''); onPinChange(null);
              const area = locations[province].find((d) => d.name === e.target.value);
              if (area) onAreaChange(area);
            }} className={FIELD}>
              <option value="">{province ? 'เลือกอำเภอ / เขต' : 'เลือกจังหวัดก่อน'}</option>
              {(locations?.[province] || []).map((d) => <option key={d.name} value={d.name}>{d.name}</option>)}
            </select>
          </label>
        </div>
        {locationError && <div role="alert" className="text-amber-800">{locationError} <button type="button" onClick={() => setRetry((v) => v + 1)} className="underline cursor-pointer">ลองใหม่</button></div>}

        <div>
          <p className="font-medium text-slate-700">พิกัดจุดน้ำท่วม</p>
          <p role="status" className={`mt-1 text-xs ${pin ? 'text-emerald-700' : 'text-slate-500'}`}>
            {pin ? `ปักหมุดแล้ว ${pin.lat.toFixed(5)}, ${pin.lng.toFixed(5)}` : 'แตะแผนที่เพื่อปักหมุด ใช้ตำแหน่งของฉัน หรือกรอกพิกัดด้านล่าง'}
          </p>
          <Button size="sm" className="mt-2" onClick={onUseMyLocation} loading={locating}>ตำแหน่งของฉัน</Button>
          <div className="mt-2 grid grid-cols-2 gap-2">
            <label className="text-xs text-slate-600">ละติจูด<input value={latitude} onChange={(e) => { setLatitude(e.target.value); onPinChange(null); }} inputMode="decimal" placeholder="13.75630" className={FIELD} /></label>
            <label className="text-xs text-slate-600">ลองจิจูด<input value={longitude} onChange={(e) => { setLongitude(e.target.value); onPinChange(null); }} inputMode="decimal" placeholder="100.50180" className={FIELD} /></label>
          </div>
          <Button size="sm" className="mt-2" onClick={useCoordinates}>ใช้พิกัดนี้</Button>
        </div>

        <fieldset>
          <legend className="font-medium text-slate-700">ระดับน้ำท่วม</legend>
          <div className="mt-2 grid grid-cols-3 gap-2">
            {DEPTHS.map(([key, label]) => (
              <label key={key} className={`cursor-pointer rounded-lg border px-2 py-3 text-center ${depth === key ? 'border-blue-600 bg-blue-50 text-blue-800' : 'border-slate-300 text-slate-700'}`}>
                <input type="radio" name="flood-depth" value={key} checked={depth === key} onChange={() => setDepth(key)} required className="mr-1 accent-blue-600" />{label}
              </label>
            ))}
          </div>
        </fieldset>

        <div>
          <label htmlFor="report-photo" className="font-medium text-slate-700">รูปน้ำท่วม (ไม่บังคับ)</label>
          <input id="report-photo" type="file" accept="image/*" disabled={photoBusy} onChange={pickPhoto} className={`mt-2 block w-full min-w-0 text-sm text-slate-600 file:mr-2 file:rounded-lg file:border file:border-slate-300 file:bg-transparent file:px-3 file:py-2 file:text-inherit ${FOCUS}`} />
          {photoBusy && <p role="status" className="mt-1 text-xs text-slate-500">กำลังเตรียมรูป…</p>}
          {photo && <div className="mt-2"><img src={photo} alt="รูปน้ำท่วมที่จะส่ง" className="w-full max-h-48 rounded-md object-contain" /><Button size="sm" className="mt-1" disabled={photoBusy} onClick={() => setPhoto(null)}>ลบรูป</Button></div>}
        </div>

        <div>
          <label htmlFor="report-note" className="font-medium text-slate-700">รายละเอียด (ไม่เกิน 2,000 ตัวอักษร)</label>
          <textarea id="report-note" rows={5} value={note} maxLength={NOTE_MAX} onChange={(e) => setNote(e.target.value)} placeholder="เช่น ชื่อถนน จุดสังเกต เวลาเริ่มท่วม และสถานการณ์ที่พบ" aria-describedby="report-note-count" className={`${FIELD} resize-y`} />
          <p id="report-note-count" className="mt-1 text-right text-xs text-slate-500">{note.length.toLocaleString('th-TH')} / 2,000 ตัวอักษร</p>
        </div>
        {error && <p role="alert" className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">{error}</p>}
        <Button type="submit" variant="primary" disabled={!ready || photoBusy} loading={sending}>{sending ? 'กำลังส่งรายงาน…' : 'ส่งรายงานน้ำท่วม'}</Button>
        {!ready && <p className="text-xs text-slate-500">เลือกจังหวัด อำเภอ/เขต ปักหมุด และเลือกระดับน้ำให้ครบก่อนส่ง</p>}
      </fieldset>
      <p className="mt-3 text-xs text-slate-500">รายงานบันทึกใน BKK StreetSmart และแสดงบนแผนที่เมื่อผ่านการตรวจสอบ</p>
    </form>
  );
}
