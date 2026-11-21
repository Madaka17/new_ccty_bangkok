import { useMemo, useState } from 'react';
import { incidentRows, sortRows } from '../../../lib/overviewData.js';
import { agoText } from '../format.js';
import { EmptyBlock } from './ChartParts.jsx';

const KIND = {
  accident: { label: 'อุบัติเหตุ', tone: 'tone-red' },
  breakdown: { label: 'รถเสีย', tone: 'tone-yellow' },
};
const SOURCE = { camera: 'กล้อง AI', longdo: 'ข่าวจราจร' };
const MAX_ROWS = 6;
const timeText = (at) => (at == null ? 'ไม่ทราบเวลา' : agoText(at));

function Thumb({ image }) {
  if (image) {
    return <img src={image} alt="" loading="lazy" className="h-9 w-9 shrink-0 rounded-lg object-cover" />;
  }
  return (
    <span aria-hidden="true" className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[var(--c-raised)] text-[var(--c-muted)]">
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" className="h-4 w-4">
        <path d="M8 2.5l6 10.5H2z" />
        <path d="M8 6.5v3M8 11.2v.1" strokeLinecap="round" />
      </svg>
    </span>
  );
}

function KindChip({ kind }) {
  const k = KIND[kind] || KIND.accident;
  return (
    <span className={`${k.tone} inline-flex whitespace-nowrap rounded-full bg-[var(--t-tint)] px-2.5 py-0.5 text-xs font-medium text-[var(--t-text)]`}>
      {k.label}
    </span>
  );
}

// The recent incidents, camera and news merged. Time and kind can be sorted; each row opens the incidents tab.
export default function RecentIncidentsTable({ incidents, onOpen }) {
  const [sort, setSort] = useState({ key: 'at', dir: 'desc' });
  const all = useMemo(() => incidentRows(incidents), [incidents]);
  // sort the whole list first, then take the top rows, so the sort chooses which rows show
  const rows = useMemo(() => sortRows(all, sort.key, sort.dir).slice(0, MAX_ROWS), [all, sort]);

  const toggle = (key) =>
    setSort((s) => ({ key, dir: s.key === key && s.dir === 'asc' ? 'desc' : 'asc' }));
  const ariaSort = (key) => (sort.key !== key ? 'none' : sort.dir === 'asc' ? 'ascending' : 'descending');
  const arrow = (key) => (sort.key !== key ? '↕' : sort.dir === 'asc' ? '↑' : '↓');

  return (
    <section aria-labelledby="recent-incidents-title" className="dash-card p-5">
      <h3 id="recent-incidents-title" className="text-base font-semibold text-[var(--c-ink)]">
        เหตุบนถนนล่าสุด
      </h3>
      <div className="mt-4">
        {rows.length === 0 ? (
          <EmptyBlock text="ตอนนี้ไม่มีเหตุบนถนน" className="min-h-40" />
        ) : (
          <>
            <table className="hidden md:table w-full text-sm">
              <caption className="sr-only">เหตุบนถนนล่าสุด</caption>
              <thead>
                <tr className="text-left text-xs text-[var(--c-muted)]">
                  <th scope="col" className="pb-2 font-medium">เหตุ</th>
                  <th scope="col" aria-sort={ariaSort('kind')} className="pb-2 font-medium">
                    <button type="button" onClick={() => toggle('kind')} className="inline-flex min-h-11 items-center gap-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--c-primary)]">
                      ประเภท <span aria-hidden="true">{arrow('kind')}</span>
                    </button>
                  </th>
                  <th scope="col" className="pb-2 font-medium">แหล่ง</th>
                  <th scope="col" aria-sort={ariaSort('at')} className="pb-2 font-medium">
                    <button type="button" onClick={() => toggle('at')} className="inline-flex min-h-11 items-center gap-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--c-primary)]">
                      เวลา <span aria-hidden="true">{arrow('at')}</span>
                    </button>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-t border-[var(--c-border)]">
                    <td className="py-2 pr-3">
                      <button type="button" onClick={() => onOpen?.()} className="flex min-h-11 items-center gap-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--c-primary)]">
                        <Thumb image={r.image} />
                        <span className="font-medium text-[var(--c-ink)]">{r.title || 'เหตุบนถนน'}</span>
                      </button>
                    </td>
                    <td className="py-2 pr-3"><KindChip kind={r.kind} /></td>
                    <td className="py-2 pr-3 text-[var(--c-muted)]">{SOURCE[r.source] || ''}</td>
                    <td className="num whitespace-nowrap py-2 text-[var(--c-muted)]">{timeText(r.at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <ul className="divide-y divide-[var(--c-border)] md:hidden">
              {rows.map((r) => (
                <li key={r.id}>
                  <button type="button" onClick={() => onOpen?.()} className="flex min-h-11 w-full items-center gap-3 py-2.5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--c-primary)]">
                    <Thumb image={r.image} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium text-[var(--c-ink)]">{r.title || 'เหตุบนถนน'}</span>
                      <span className="mt-1 flex flex-wrap items-center gap-2 text-xs text-[var(--c-muted)]">
                        <KindChip kind={r.kind} />
                        <span>{SOURCE[r.source] || ''}</span>
                        <span className="num">{timeText(r.at)}</span>
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </section>
  );
}
