import { ROAD_LEVEL } from './format.js';

// The five most jammed roads now (Longdo, /api/traffic/summary "congested"), each with how long the jam is,
// a level pill and a button that opens the cameras on that road.
const LEVEL = {
  red: { label: 'ติดมาก', bars: 3, tone: 'tone-red' },
  yellow: { label: 'ติดปานกลาง', bars: 2, tone: 'tone-yellow' },
  green: { label: 'โล่ง', bars: 1, tone: 'tone-green' },
  neutral: { label: 'ไม่มีข้อมูล', bars: 0, tone: 'tone-neutral' },
};

export default function AvoidRoadsCard({ summary, onOpenRoad, onNavigate }) {
  const rows = (summary?.congested || []).slice(0, 5);
  return (
    <section aria-labelledby="avoid-h" className="min-w-0 rounded-md border border-[var(--c-border)] bg-[var(--c-surface)] p-5 sm:p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="avoid-h" className="text-xl font-bold">ถนนที่ควรเลี่ยงตอนนี้</h2>
        {onNavigate && (
          <button type="button" onClick={() => onNavigate('map')} className="cursor-pointer min-h-11 text-[15px] font-semibold underline underline-offset-4 hover:opacity-80">
            ดูทุกสาย
          </button>
        )}
      </div>
      {!summary?.ready ? (
        <p className="mt-4 text-sm text-[var(--c-muted)]">กำลังโหลดข้อมูลรถติด...</p>
      ) : rows.length === 0 ? (
        <p className="mt-4 text-sm text-[var(--c-muted)]">ตอนนี้ไม่มีถนนที่รถติดมาก</p>
      ) : (
        <ol className="mt-2">
          {rows.map((r, i) => {
            const lv = LEVEL[ROAD_LEVEL[r.level] || 'neutral'];
            return (
              <li key={r.name} className={`${lv.tone} flex items-center gap-3 py-3 border-t border-[var(--c-border)] first:border-t-0`}>
                <span className="w-9 h-9 shrink-0 rounded-md bg-[var(--c-line)] text-[var(--c-surface)] font-display text-[17px] font-bold grid place-items-center">{i + 1}</span>
                <span className="flex-1 min-w-0">
                  <span className="block truncate text-base font-semibold" title={r.name}>{r.name}</span>
                  <span className="block text-sm text-[var(--c-muted)]">{r.red_km ? `ติดยาว ${r.red_km} กม. จาก ${r.length_km} กม.` : `ช่วงที่มีข้อมูล ${r.length_km} กม.`}</span>
                </span>
                <span className="hidden sm:inline-flex shrink-0 items-center gap-2 rounded-full px-3 py-1 text-sm font-semibold bg-[var(--t-tint)] text-[var(--t-text)]">
                  <span aria-hidden="true" className="inline-flex gap-0.5">
                    {[0, 1, 2].map((k) => (
                      <span key={k} className={`w-[5px] h-3.5 rounded-sm ${k < lv.bars ? 'bg-[var(--t-ring)]' : 'bg-[var(--c-border)]'}`} />
                    ))}
                  </span>
                  {lv.label}
                </span>
                <button
                  type="button"
                  onClick={() => onOpenRoad?.(r.name)}
                  aria-label={`ดูกล้องบน${r.name}`}
                  className="cursor-pointer shrink-0 inline-flex items-center gap-1.5 min-h-11 px-3 rounded-md border border-[var(--c-border-strong)] bg-[var(--c-surface)] text-sm font-semibold hover:bg-[var(--c-raised)]"
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="w-[18px] h-[18px]" aria-hidden="true">
                    <rect x="3" y="7" width="13" height="10" rx="2" />
                    <path d="M16 11l5-3v8l-5-3" />
                  </svg>
                  <span className="hidden sm:inline">ดูกล้อง</span>
                </button>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
