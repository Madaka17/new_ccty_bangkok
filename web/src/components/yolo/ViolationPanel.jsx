// Wrong-way / no-helmet log for the live AI camera, plus how much of the camera's
// direction-of-travel map has been learned (wrong-way needs it).
import { useEffect, useState } from 'react';
import { fetchViolations, fetchViolationStatus } from '../../lib/api.js';
import { FOCUS } from '../dashboard/ui.jsx';

const POLL_MS = 60000;
const KIND = {
  wrong_way: { label: 'ย้อนศร', cls: 'bg-red-50 text-red-700 border-red-200' },
  no_helmet: { label: 'ไม่สวมหมวก', cls: 'bg-amber-50 text-amber-700 border-amber-200' },
};

function ago(ts) {
  const m = Math.round((Date.now() / 1000 - ts) / 60);
  if (m < 1) return 'เมื่อสักครู่';
  if (m < 60) return `${m} นาทีก่อน`;
  const h = Math.floor(m / 60);
  return h < 24 ? `${h} ชม.ก่อน` : `${Math.round(h / 24)} วันก่อน`;
}

export default function ViolationPanel({ active, camid }) {
  const [data, setData] = useState(null);
  const [status, setStatus] = useState(null);
  const [scope, setScope] = useState('camera'); // camera | all
  const [open, setOpen] = useState(null);

  useEffect(() => {
    if (!active) return;
    let alive = true;
    const load = async () => {
      try {
        const [v, st] = await Promise.all([
          fetchViolations({ hours: 24, camid: scope === 'camera' ? camid : undefined, limit: 20 }),
          fetchViolationStatus(camid),
        ]);
        if (alive) {
          setData(v);
          setStatus(st);
        }
      } catch {}
    };
    load();
    const id = setInterval(load, POLL_MS);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [active, camid, scope]);

  const flow = status?.cameras?.[camid];
  // Progress over cells vehicles actually cross (sky / pillars never learn); a brand-new camera has none yet
  const learned = flow && flow.active ? Math.round((100 * flow.known) / flow.active) : 0;
  const items = data?.items || [];
  const counts = data?.counts || {};

  return (
    <div className="glass rounded-xl p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-ink-600">ตรวจจับผิดกฎจราจร (24 ชม.)</p>
        <div role="tablist" aria-label="ขอบเขตรายการ" className="inline-flex rounded-lg border border-slate-300 p-0.5 text-xs">
          {[
            ['camera', 'กล้องนี้'],
            ['all', 'ทุกกล้อง'],
          ].map(([k, t]) => (
            <button
              key={k}
              type="button"
              role="tab"
              aria-selected={scope === k}
              onClick={() => setScope(k)}
              className={`cursor-pointer rounded-md h-8 px-3 font-medium transition-colors duration-150 ${FOCUS} ${scope === k ? 'bg-lavender-100 text-lavender-700' : 'text-ink-600 hover:text-ink-900'}`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-2 flex flex-wrap gap-2 text-xs">
        <span className="rounded-md border border-red-200 bg-red-50 px-2 py-0.5 text-red-700">ย้อนศร {counts.wrong_way || 0}</span>
        <span className="rounded-md border border-amber-200 bg-amber-50 px-2 py-0.5 text-amber-700">ไม่สวมหมวก {counts.no_helmet || 0}</span>
      </div>

      <div className="mt-3 text-xs text-ink-600">
        <div className="flex items-center gap-2">
          <span className="shrink-0">ทิศทางจราจรที่เรียนรู้แล้ว</span>
          <div className="flex-1 h-1.5 rounded-full bg-slate-200 overflow-hidden">
            <div className="h-full bg-lavender-600" style={{ width: `${learned}%` }} />
          </div>
          <span className="tabular-nums shrink-0" title={flow ? `${flow.known} จาก ${flow.active} ช่องที่มีรถผ่าน · ${flow.samples.toLocaleString('th-TH')} ตัวอย่าง` : ''}>{learned}%</span>
        </div>
        <p className="mt-1">
          {learned < 10 ? 'กล้องใหม่: ต้องดูรถวิ่งสักพักก่อนจึงจับย้อนศรได้' : 'จับย้อนศรได้ในบริเวณที่เรียนรู้แล้ว'} ·{' '}
          {status?.helmet_checks ? 'ตรวจหมวกกันน็อกด้วย AI vision' : 'ตรวจหมวกปิดอยู่ (ไม่มี GEMINI_API_KEY / ANTHROPIC_API_KEY)'}
        </p>
      </div>

      <div className="mt-3 flex flex-col gap-1.5 max-h-64 overflow-y-auto scroll-soft">
        {!data ? (
          <div className="h-10 rounded-md animate-pulse bg-slate-200" aria-hidden="true" />
        ) : items.length === 0 ? (
          <p className="text-xs text-ink-600 py-2">ยังไม่พบการฝ่าฝืนใน 24 ชม.</p>
        ) : null}
        {items.map((v) => {
          const k = KIND[v.kind] || { label: v.kind_th || v.kind, cls: 'bg-slate-200 text-slate-700 border-slate-300' };
          return (
            <button
              key={v.id}
              type="button"
              onClick={() => setOpen(open === v.id ? null : v.id)}
              aria-expanded={open === v.id}
              className={`cursor-pointer text-left rounded-lg px-3 py-2.5 hover:bg-lavender-50 transition-colors duration-150 ${FOCUS}`}
            >
              <div className="flex items-center gap-2 text-xs">
                <span className={`rounded-md border px-1.5 py-0.5 font-medium ${k.cls}`}>{k.label}</span>
                <span className="text-ink-900 truncate flex-1">{scope === 'all' ? v.title : v.description}</span>
                <span className="text-ink-600 shrink-0">{ago(v.ts)}</span>
              </div>
              {open === v.id && (
                <div className="mt-2">
                  <img src={v.image} alt={`หลักฐาน ${k.label}`} className="w-full rounded-md border border-slate-300" loading="lazy" />
                  <p className="text-xs text-ink-600 mt-1">
                    {v.title} · {v.description} · ความมั่นใจ {Math.round((v.confidence || 0) * 100)}%
                  </p>
                </div>
              )}
            </button>
          );
        })}
      </div>
      <p className="text-xs text-ink-600 mt-3">
        {data?.archive_dir && (
          <>
            ภาพหลักฐานสำเนาไว้ที่ <span className="font-mono">{data.archive_dir}</span>
            {data.archive_ok === false && <span className="text-red-700"> (ไม่พบไดรฟ์)</span>} ·{' '}
          </>
        )}
        ผลจาก AI ใช้เป็นข้อมูลเบื้องต้น ต้องให้เจ้าหน้าที่ตรวจสอบภาพหลักฐานก่อนทุกครั้ง
      </p>
    </div>
  );
}
