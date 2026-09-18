import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchIncidentHistory } from '../../lib/api.js';
import { Card, SectionHeader, Badge, Button, Segmented, Skeleton, EmptyState, ErrorState, Truncate, FOCUS } from './ui.jsx';
import { agoText, fmtTime, fmtDateTime, fmtDuration } from './format.js';

const KIND = {
  accident: { label: 'อุบัติเหตุ', tone: 'red' },
  breakdown: { label: 'รถเสีย / กีดขวาง', tone: 'yellow' },
};
const SOURCE = { camera: 'กล้อง AI', longdo: 'รายงาน Longdo' };
const FILTERS = [
  ['all', 'ทั้งหมด'],
  ['camera', 'กล้อง AI'],
  ['longdo', 'รายงานจราจร'],
];

// Longdo timestamps are 'YYYY-MM-DD HH:MM:SS' local time
const longdoClock = (s) => (s ? `${s.slice(11, 16)} น.` : '');

function metaLine(i) {
  if (i.source === 'camera') {
    const parts = [`ตรวจพบ ${agoText(i.ts)}`];
    if (i.confidence != null) parts.push(`ความมั่นใจ ${Math.round(i.confidence * 100)}%`);
    return parts.join(' · ');
  }
  const parts = [SOURCE.longdo];
  if (i.start) parts.push(`เริ่ม ${longdoClock(i.start)}`);
  if (i.contributor) parts.push(i.contributor);
  return parts.join(' · ');
}

function IncidentRow({ i, expanded, onToggle, onOpenAI, onNavigate }) {
  const kind = KIND[i.kind] || KIND.accident;
  const detailId = `incident-${i.id}`;
  return (
    <li className="py-3">
      <div className="flex items-start gap-3">
        {i.image ? (
          <img src={i.image} alt="" loading="lazy" className="w-20 h-14 rounded-md object-cover border border-slate-200 shrink-0 bg-slate-100" />
        ) : (
          <span className="w-20 h-14 rounded-md border border-slate-200 bg-slate-50 flex items-center justify-center text-[11px] text-slate-400 shrink-0" aria-hidden="true">
            ไม่มีภาพ
          </span>
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <Badge tone={kind.tone}>{kind.label}</Badge>
            <Truncate text={i.title} className="text-sm font-medium text-slate-900" />
          </div>
          {i.description && <Truncate text={i.description} className="text-[13px] text-slate-600 mt-0.5" />}
          <p className="text-xs text-slate-500 mt-1">{metaLine(i)}</p>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {i.camid && (
            <Button size="sm" onClick={() => onOpenAI(i.camid)} title="เปิดภาพสดจากกล้องนี้">
              ภาพสด
            </Button>
          )}
          <button
            type="button"
            onClick={onToggle}
            aria-expanded={expanded}
            aria-controls={detailId}
            aria-label={expanded ? 'ซ่อนรายละเอียด' : 'ดูรายละเอียด'}
            className={`cursor-pointer h-8 px-2 rounded-lg text-xs text-slate-600 hover:bg-slate-100 hover:text-slate-900 flex items-center justify-center transition-colors ${FOCUS}`}
          >
            {expanded ? 'ซ่อน' : 'เพิ่มเติม'}
          </button>
        </div>
      </div>

      {expanded && (
        <div id={detailId} className="mt-3 ml-0 sm:ml-[92px] rounded-lg border border-slate-200 bg-slate-50 p-3 grid grid-cols-1 sm:grid-cols-[1fr_auto] gap-3">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
            <dt className="text-slate-500">แหล่งที่มา</dt>
            <dd className="text-slate-900">{SOURCE[i.source] || i.source}</dd>
            <dt className="text-slate-500">เวลาที่พบ</dt>
            <dd className="text-slate-900 tabular-nums">{i.source === 'camera' ? fmtDateTime(i.ts) : longdoClock(i.start) || '–'}</dd>
            {i.source === 'camera' && (
              <>
                <dt className="text-slate-500">อัปเดตล่าสุด</dt>
                <dd className="text-slate-900">{agoText(i.last_seen)}</dd>
                <dt className="text-slate-500">รถหยุดนิ่ง</dt>
                <dd className="text-slate-900">{i.stopped_s != null ? fmtDuration(i.stopped_s) : '–'}</dd>
                <dt className="text-slate-500">คนใกล้จุดเกิดเหตุ</dt>
                <dd className="text-slate-900">{i.persons_near ?? 0} คน</dd>
              </>
            )}
            {i.source === 'longdo' && (
              <>
                <dt className="text-slate-500">คาดว่าสิ้นสุด</dt>
                <dd className="text-slate-900">{longdoClock(i.stop) || 'ไม่ระบุ'}</dd>
                {i.severity && (
                  <>
                    <dt className="text-slate-500">ระดับ</dt>
                    <dd className="text-slate-900">{i.severity}</dd>
                  </>
                )}
              </>
            )}
            {i.description && (
              <>
                <dt className="text-slate-500">รายละเอียด</dt>
                <dd className="text-slate-900 col-span-2 sm:col-span-1 leading-5">{i.description}</dd>
              </>
            )}
          </dl>
          <div className="flex sm:flex-col gap-2 sm:items-end">
            {i.image && (
              <a href={i.image} target="_blank" rel="noreferrer" className={`text-xs font-medium text-blue-700 hover:underline rounded ${FOCUS}`}>
                เปิดภาพขนาดเต็ม
              </a>
            )}
            {i.latitude && i.longitude && (
              <Button size="sm" variant="ghost" onClick={() => onNavigate('map')}>
                ดูบนแผนที่
              </Button>
            )}
          </div>
        </div>
      )}
    </li>
  );
}

function ResolvedList({ items, loading, error, onRetry }) {
  const [open, setOpen] = useState(false);
  if (error && !items) return <ErrorState message="โหลดประวัติเหตุการณ์ไม่สำเร็จ" onRetry={onRetry} />;
  if (loading && !items) return <Skeleton className="h-9" />;
  const n = items?.length || 0;
  return (
    <div className="border-t border-slate-200 pt-3">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls="incident-resolved"
        className={`cursor-pointer w-full flex items-center justify-between text-left rounded-lg px-1 py-1 hover:bg-slate-50 ${FOCUS}`}
      >
        <span className="text-[13px] font-medium text-slate-700">เหตุการณ์ที่คลี่คลายแล้ว ใน 24 ชม.</span>
        <span className="flex items-center gap-2 text-xs text-slate-500">
          {n} รายการ
          {open ? 'ซ่อน' : 'แสดง'}
        </span>
      </button>
      {open && (
        <div id="incident-resolved" className="mt-2">
          {n === 0 ? (
            <p className="text-[13px] text-slate-500 px-1 py-2">ไม่มีเหตุการณ์ที่คลี่คลายใน 24 ชม. ที่ผ่านมา</p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {items.map((i) => {
                const kind = KIND[i.kind] || KIND.accident;
                return (
                  <li key={i.id} className="flex items-center gap-3 px-1 py-2 text-[13px]">
                    <span className="text-xs text-slate-500 tabular-nums w-12 shrink-0">{fmtTime(i.ts)}</span>
                    <Badge tone={kind.tone}>{kind.label}</Badge>
                    <Truncate text={i.title} className="flex-1 text-slate-800" />
                    <span className="text-xs text-slate-500 shrink-0 tabular-nums">นาน {fmtDuration(i.cleared_ts - i.ts)}</span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

// `incidents` comes from the App-level poll (/api/incidents); null while the first request is in flight
export default function IncidentPanel({ incidents, onOpenAI, onNavigate }) {
  const [filter, setFilter] = useState('all');
  const [expanded, setExpanded] = useState(null);
  const [history, setHistory] = useState(null);
  const [histLoading, setHistLoading] = useState(true);
  const [histError, setHistError] = useState(false);

  const loadHistory = useCallback(() => {
    setHistLoading(true);
    return fetchIncidentHistory(24)
      .then((items) => {
        setHistory(items.filter((i) => i.cleared_ts));
        setHistError(false);
      })
      .catch(() => setHistError(true))
      .finally(() => setHistLoading(false));
  }, []);

  useEffect(() => {
    loadHistory();
    const id = setInterval(loadHistory, 60000);
    return () => clearInterval(id);
  }, [loadHistory]);

  const active = useMemo(() => {
    const cam = incidents?.camera || [];
    const longdo = incidents?.longdo || [];
    const all = [...cam, ...longdo];
    return filter === 'all' ? all : all.filter((i) => i.source === filter);
  }, [incidents, filter]);

  const total = (incidents?.camera?.length || 0) + (incidents?.longdo?.length || 0);
  const visionOff = incidents && !incidents.vision_provider;

  return (
    <Card aria-labelledby="incident-title" className="p-5">
      <SectionHeader
        id="incident-title"
        title={
          <span className="inline-flex items-center gap-2">
            เหตุการณ์บนถนน
            {total > 0 ? <Badge tone="red" dot>{total} จุดกำลังเกิด</Badge> : incidents ? <Badge tone="green" dot>ไม่มีเหตุการณ์</Badge> : null}
          </span>
        }
        description={incidents ? `อัปเดต ${fmtTime(incidents.updated)} น. · กล้อง AI ยืนยันด้วยภาพก่อนแจ้ง · รายงานสาธารณะจาก Longdo` : 'กำลังโหลด'}
        action={
          <div className="flex items-center gap-2">
            <Segmented options={FILTERS} value={filter} onChange={setFilter} label="กรองแหล่งที่มา" />
            <Button size="sm" onClick={() => onNavigate('map')} disabled={!total}>
              แผนที่
            </Button>
          </div>
        }
      />

      {visionOff && (
        <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          ยังไม่ได้ตั้งค่า vision API (GEMINI_API_KEY หรือ ANTHROPIC_API_KEY) การตรวจจับอุบัติเหตุจากกล้องจึงปิดอยู่ แสดงเฉพาะรายงานจาก Longdo
        </p>
      )}

      <div className="mt-3">
        {!incidents ? (
          <div className="space-y-3">
            {[1, 2].map((n) => (
              <Skeleton key={n} className="h-16" />
            ))}
          </div>
        ) : active.length === 0 ? (
          <EmptyState
            title={filter === 'all' ? 'ไม่มีเหตุการณ์ที่กำลังเกิดขึ้น' : `ไม่มีเหตุการณ์จาก${FILTERS.find(([k]) => k === filter)[1]}`}
            description="ระบบตรวจสอบกล้องที่นับต่อเนื่องและรายงานสาธารณะทุก 30 วินาที"
          />
        ) : (
          <ul className="divide-y divide-slate-100 -my-1">
            {active.map((i) => (
              <IncidentRow
                key={i.id}
                i={i}
                expanded={expanded === i.id}
                onToggle={() => setExpanded((v) => (v === i.id ? null : i.id))}
                onOpenAI={onOpenAI}
                onNavigate={onNavigate}
              />
            ))}
          </ul>
        )}
      </div>

      <div className="mt-4">
        <ResolvedList items={history} loading={histLoading} error={histError} onRetry={loadHistory} />
      </div>
    </Card>
  );
}
