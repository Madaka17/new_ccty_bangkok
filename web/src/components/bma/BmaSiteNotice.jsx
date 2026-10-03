import { StatusBanner } from '../dashboard/primitives.jsx';
import { fmtTime } from '../dashboard/format.js';

// The BMA camera site is down (no pictures) or frozen (the same picture again): bma_service sets
// scan_status.source after every scan. Shown wherever BMA camera numbers or pictures are, so nobody reads
// the last pictures (on Oct 1 2026, the morning's traffic at 10 pm) as live.
export const bmaSiteDown = (source) => source?.state === 'down' || source?.state === 'frozen';

export default function BmaSiteNotice({ source }) {
  if (!bmaSiteDown(source)) return null;
  const since = source.last_frame_at ? ` ตั้งแต่ ${fmtTime(source.last_frame_at)} น.` : '';
  return (
    <StatusBanner tone="red" label={source.state === 'down' ? 'เว็บกล้อง กทม. ล่ม' : 'เว็บกล้อง กทม. ส่งภาพค้าง'}>
      เว็บ www.bmatraffic.com ไม่ส่งภาพใหม่{since} ข้อมูลรถติดและภาพจากกล้อง กทม. จึงยังไม่อัปเดต
      ระบบจะลองใหม่ทุก 3 นาที
    </StatusBanner>
  );
}
