// Range picker (24 h / 7 days / 30 days) with the CSV download and any extra controls on the right.
const RANGES = [
  ['24h', '24 ชั่วโมง'],
  ['7d', '7 วัน'],
  ['30d', '30 วัน'],
];

export default function TimeRangeToolbar({ range, onRange, onDownload, downloadDisabled = false, extra }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div role="group" aria-label="ช่วงเวลา" className="flex w-full rounded-xl bg-[var(--c-raised)] p-1 sm:w-auto">
        {RANGES.map(([key, text]) => {
          const on = range === key;
          return (
            <button
              key={key}
              type="button"
              aria-pressed={on}
              onClick={() => onRange(key)}
              className={`min-h-11 flex-1 rounded-lg px-4 text-sm font-medium transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--c-primary)] sm:flex-none ${
                on
                  ? 'bg-[var(--c-surface)] text-[var(--c-ink)] shadow-[var(--c-card-shadow)] dark:bg-[var(--c-sel-bg)] dark:text-[var(--c-sel-text)]'
                  : 'text-[var(--c-muted)] hover:text-[var(--c-ink)]'
              }`}
            >
              {text}
            </button>
          );
        })}
      </div>
      <div className="flex w-full flex-wrap items-center gap-2 sm:ml-auto sm:w-auto">
        <button
          type="button"
          onClick={onDownload}
          disabled={downloadDisabled}
          className="inline-flex min-h-11 cursor-pointer items-center gap-1.5 rounded-xl border border-[var(--c-border)] bg-[var(--c-surface)] px-3 text-sm font-medium text-[var(--c-ink)] transition-colors duration-150 hover:bg-[var(--c-raised)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--c-primary)] disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-[var(--c-surface)]"
        >
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4" aria-hidden="true">
            <path d="M8 2v8M4.5 6.5L8 10l3.5-3.5M3 13h10" />
          </svg>
          ดาวน์โหลด
        </button>
        {extra}
      </div>
    </div>
  );
}
