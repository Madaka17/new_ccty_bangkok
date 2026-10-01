// AI read of which Bangkok districts the northern water will reach, when and why (north_impact_agent.py).
// Falls back to the rule-based report when the model is off; the card says which one it shows.
// NorthFlowSection fetches the report (the easy summary and the gauge sentences come from it too).
import { useState } from 'react';
import { runNorthImpact } from '../../lib/api.js';
import { Card, SectionHeader, Badge, Button, Skeleton, EmptyState } from '../dashboard/ui.jsx';
import { agoText, fmtDateTime } from '../dashboard/format.js';

const LEVEL = { normal: 'green', watch: 'yellow', warning: 'red', critical: 'red' };
const DISTRICT_TONE = { สูง: 'red', ปานกลาง: 'yellow', เฝ้าระวัง: 'blue' };
const DISTRICT_BORDER = { สูง: 'border-red-200', ปานกลาง: 'border-amber-200', เฝ้าระวัง: 'border-slate-200' };

export default function NorthImpactCard({ data, failed, onReload, onData }) {
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState(null);
  const [all, setAll] = useState(false);

  const run = () => {
    setRunning(true);
    setRunError(null);
    runNorthImpact()
      .then(onData)
      .catch((e) => setRunError(e.message === 'forbidden' ? 'สั่งวิเคราะห์ใหม่ได้เฉพาะทีมปฏิบัติการ (เครือข่ายภายใน)' : 'วิเคราะห์ไม่สำเร็จ ลองใหม่อีกครั้ง'))
      .finally(() => setRunning(false));
  };

  const r = data?.report;
  const busy = running || data?.running;
  const districts = r?.districts || [];
  const shown = all ? districts : districts.slice(0, 6);

  return (
    <Card className="p-5" aria-labelledby="north-impact-title">
      <SectionHeader
        id="north-impact-title"
        title="AI วิเคราะห์ผลกระทบต่อเขตในกรุงเทพฯ"
        description={
          r
            ? `${r.source === 'ai' ? `AI ${r.model}` : 'ประเมินตามเกณฑ์ของระบบ (AI ไม่พร้อม)'} · วิเคราะห์ ${fmtDateTime(r.generated_at)} (${agoText(r.generated_at)}) · วิเคราะห์ใหม่ทุก ${Math.round((data.interval_s || 1800) / 60)} นาที`
            : 'AI อ่านน้ำเหนือที่กำลังมา คาดการณ์ สสน. ที่นนทบุรี น้ำทะเลหนุน และระดับคลอง/ถนน/ฝนรายเขต'
        }
        action={
          <div className="flex items-center gap-2">
            {r && (
              <Badge tone={LEVEL[r.level] || 'yellow'} dot>
                {r.status_label}
              </Badge>
            )}
            <Button size="sm" onClick={run} loading={busy}>
              {busy ? 'กำลังวิเคราะห์' : 'วิเคราะห์ใหม่'}
            </Button>
          </div>
        }
      />
      {runError && (
        <p role="alert" className="mt-3 text-xs text-red-700">
          {runError}
        </p>
      )}
      {data?.error && r && <p className="mt-3 text-xs text-amber-700">รอบล่าสุด: {data.error}</p>}

      {!r ? (
        <div className="mt-4">
          {failed ? (
            <EmptyState title="โหลดบทวิเคราะห์ไม่สำเร็จ" action={<Button size="sm" onClick={onReload}>ลองใหม่</Button>} />
          ) : (
            <>
              <p className="text-sm text-slate-600 mb-3">AI กำลังวิเคราะห์ รอบแรกเริ่มหลังเปิดเซิร์ฟเวอร์ราว 2 นาที ...</p>
              <Skeleton className="h-40" />
            </>
          )}
        </div>
      ) : (
        <>
          <p className="mt-4 text-sm text-slate-800 leading-6">{r.summary}</p>

          {r.timeline?.length > 0 && (
            <ol className="mt-4 border-l-2 border-slate-200 pl-4 space-y-2">
              {r.timeline.map((t, i) => (
                <li key={i} className="text-sm leading-6">
                  <span className="font-semibold text-slate-900">{t.when}</span>
                  <span className="text-slate-700"> · {t.event}</span>
                </li>
              ))}
            </ol>
          )}

          {districts.length === 0 ? (
            <p className="mt-4 text-sm text-slate-600">ยังไม่มีเขตที่คาดว่าจะได้รับผลกระทบจากน้ำเหนือ</p>
          ) : (
            <div className="mt-4 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
              {shown.map((d) => (
                <article key={d.district} className={`rounded-xl border p-3 ${DISTRICT_BORDER[d.level] || 'border-slate-200'}`}>
                  <div className="flex items-center gap-2">
                    <h4 className="text-sm font-semibold text-slate-900">เขต{d.district}</h4>
                    <Badge tone={DISTRICT_TONE[d.level] || 'neutral'} dot className="ml-auto">
                      {d.level}
                    </Badge>
                  </div>
                  <p className="mt-1 text-xs font-medium text-slate-700">ช่วงเวลา: {d.when}</p>
                  {d.tags?.length > 0 && <p className="mt-0.5 text-[11px] text-slate-500">ทำเล: {d.tags.join(' · ')}</p>}
                  <p className="mt-2 text-xs text-slate-700 leading-5">
                    <span className="font-medium text-slate-900">สาเหตุ:</span> {d.cause}
                  </p>
                  <p className="mt-1 text-xs text-slate-600 leading-5">
                    <span className="font-medium text-slate-900">ข้อมูล:</span> {d.evidence}
                  </p>
                  <p className="mt-1 text-xs text-slate-700 leading-5">
                    <span className="font-medium text-slate-900">ควรทำ:</span> {d.advice}
                  </p>
                </article>
              ))}
            </div>
          )}
          {districts.length > 6 && (
            <Button size="sm" variant="ghost" className="mt-2" onClick={() => setAll((v) => !v)}>
              {all ? 'แสดงน้อยลง' : `ดูทั้งหมด ${districts.length} เขต`}
            </Button>
          )}

          {r.watch_points?.length > 0 && (
            <div className="mt-4">
              <h4 className="text-xs font-semibold text-slate-600">ติดตามต่อ</h4>
              <ul className="mt-1 space-y-1 text-xs text-slate-700">
                {r.watch_points.map((w, i) => (
                  <li key={i} className="flex gap-1.5">
                    <span className="text-slate-400">•</span>
                    <span>{w}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <p className="mt-4 text-[11px] text-slate-500 leading-5">
            บทวิเคราะห์จาก AI อ้างอิงข้อมูลสดและค่าคาดการณ์ ไม่ใช่ประกาศทางการ ผลกระทบจริงขึ้นกับแนวคันกั้นน้ำ การบริหารประตูระบายน้ำ และฝนที่ตกเพิ่ม ติดตามประกาศของกรุงเทพมหานคร กรมชลประทาน และ ปภ.
          </p>
        </>
      )}
    </Card>
  );
}
