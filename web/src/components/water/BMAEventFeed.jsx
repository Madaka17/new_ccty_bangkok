import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchBMAEvents } from '../../lib/api.js';
import { Card, SectionHeader, Badge, Segmented, Skeleton, EmptyState, ErrorState, Truncate } from '../dashboard/ui.jsx';
import { agoText, fmtTime } from '../dashboard/format.js';

const POLL_MS = 60000;
const KIND = {
  flood: { label: 'น้ำท่วมขัง', tone: 'red' },
  accident: { label: 'อุบัติเหตุ', tone: 'yellow' },
  fire: { label: 'เพลิงไหม้', tone: 'red' },
  roadwork: { label: 'ปิด/เบี่ยงจราจร', tone: 'blue' },
  tree: { label: 'ต้นไม้ล้ม', tone: 'yellow' },
  other: { label: 'อื่น ๆ', tone: 'neutral' },
};
const FILTERS = [
  ['all', 'ทั้งหมด'],
  ['flood', 'น้ำท่วม'],
  ['accident', 'อุบัติเหตุ'],
];
const NEW_WINDOW_S = 30 * 60;

// Strip the leading "15/09/2569 19.54 น." that BMA repeats in every description
const stripStamp = (s) => (s || '').replace(/^\d{1,2}\/\d{1,2}\/\d{4}\s+\d{1,2}[.:]\d{2}\s*น\.\s*/, '');

export default function BMAEventFeed({ isActive, onToast }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const [filter, setFilter] = useState('all');
  const known = useRef(null);

  const load = useCallback(() => {
    fetchBMAEvents({ hours: 24, limit: 60 })
      .then((d) => {
        setData(d);
        setError(false);
        const ids = new Set(d.items.map((i) => i.id));
        if (known.current) {
          const fresh = d.items.filter((i) => !known.current.has(i.id));
          if (fresh.length && onToast) {
            const f = fresh[0];
            onToast(`${KIND[f.kind]?.label || 'รายงาน'} กทม.: ${f.title}${fresh.length > 1 ? ` และอีก ${fresh.length - 1} รายการ` : ''}`);
          }
        }
        known.current = ids;
      })
      .catch(() => setError(true));
  }, [onToast]);

  useEffect(() => {
    if (!isActive) return;
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [isActive, load]);

  const items = (data?.items || []).filter((i) => filter === 'all' || i.kind === filter);
  const counts = data?.counts || {};
  const weather = data?.bulletins?.find((b) => b.headline.includes('สภาพอากาศ'));
  const now = Date.now() / 1000;

  return (
    <Card aria-labelledby="water-bma-title" className="p-5">
      <SectionHeader
        id="water-bma-title"
        title="รายงานสดจากศูนย์ควบคุมจราจร กทม."
        description={
          data?.updated_at
            ? `cpudapp.bangkok.go.th · ดึงข้อมูลทุก ${data.poll_seconds} วินาที · อัปเดต ${agoText(data.updated_at)} · 24 ชม. ที่ผ่านมา: น้ำท่วม ${counts.flood || 0} · อุบัติเหตุ ${counts.accident || 0}`
            : 'cpudapp.bangkok.go.th · กำลังเชื่อมต่อ'
        }
        action={
          <div className="flex items-center gap-2">
            {data && !data.error && (
              <Badge tone="green" dot>
                LIVE
              </Badge>
            )}
            <Segmented label="ประเภทรายงาน" value={filter} onChange={setFilter} options={FILTERS} />
          </div>
        }
      />

      {weather && (
        <div className="mt-3 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-900">
          <b>{weather.headline}</b> <span className="text-blue-800">{weather.detail}</span>
          <span className="text-xs text-blue-700"> — {weather.source}</span>
        </div>
      )}

      {data?.error && (
        <p role="status" className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          ดึงข้อมูลรอบล่าสุดไม่สำเร็จ ({data.error}) แสดงรายการที่ได้ล่าสุด
        </p>
      )}

      <div className="mt-3">
        {error && !data ? (
          <ErrorState message="เชื่อมต่อศูนย์ควบคุมจราจร กทม. ไม่สำเร็จ" onRetry={load} />
        ) : !data ? (
          <div className="space-y-2">
            {[...Array(5)].map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : !items.length ? (
          <EmptyState title="ยังไม่มีรายงานในหมวดนี้ใน 24 ชม. ที่ผ่านมา" description={data.updated_at ? undefined : 'ระบบกำลังดึงข้อมูลรอบแรก ลองใหม่ในอีกสักครู่'} />
        ) : (
          <ul className="divide-y divide-slate-100 max-h-[520px] overflow-y-auto pr-1">
            {items.map((e) => {
              const kind = KIND[e.kind] || KIND.other;
              const isNew = e.ts && now - e.ts < NEW_WINDOW_S;
              return (
                <li key={e.id} className="py-2.5">
                  <div className="flex items-start gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge tone={kind.tone}>{kind.label}</Badge>
                        {isNew && <Badge tone="blue">ใหม่</Badge>}
                        <Truncate text={e.title} className="text-sm font-medium text-slate-900 flex-1 min-w-0" />
                      </div>
                      <p className="text-[13px] text-slate-600 mt-0.5 leading-5">{stripStamp(e.desc)}</p>
                      <p className="text-xs text-slate-500 mt-1">
                        {e.ts ? `${fmtTime(e.ts)} น. · ${agoText(e.ts)}` : 'ไม่ระบุเวลา'}
                        {e.source ? ` · ${e.source}` : ''}
                        {e.lat != null && (
                          <>
                            {' · '}
                            <a href={`https://www.google.com/maps?q=${e.lat},${e.lng}`} target="_blank" rel="noreferrer" className="text-blue-700 hover:underline">
                              แผนที่
                            </a>
                          </>
                        )}
                        {' · '}
                        <a href={e.url} target="_blank" rel="noreferrer" className="text-blue-700 hover:underline">
                          ต้นทาง
                        </a>
                      </p>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </Card>
  );
}
