import { flowLevel, fmtNum } from '../format.js';

// Good states use the green chip tokens; everything else takes its status tone.
function chipClass(key) {
  if (key === 'green') return 'bg-[var(--c-chip-up-bg)] text-[var(--c-chip-up-text)]';
  return `tone-${key} bg-[var(--t-tint)] text-[var(--t-text)]`;
}

// Four headline numbers. Each tile is a button that opens the page behind it.
export default function KpiCards({ bkkFlow, incidentCount, floodCount, online, onNavigate, onIncidents }) {
  const flow = flowLevel(bkkFlow ?? null);
  const hasFlood = floodCount != null;
  const floodChip = !hasFlood
    ? { label: 'รอข้อมูล', key: 'neutral' }
    : floodCount === 0
      ? { label: 'ไม่มี', key: 'green' }
      : { label: 'ต้องระวัง', key: 'yellow' };

  const tiles = [
    {
      id: 'traffic',
      label: 'คะแนนจราจร กทม.',
      value: bkkFlow != null ? fmtNum(bkkFlow) : '–',
      chip: flow.label,
      chipKey: flow.key,
      onClick: () => onNavigate?.('map'),
    },
    {
      id: 'incidents',
      label: 'อุบัติเหตุและรถเสีย',
      value: incidentCount != null ? fmtNum(incidentCount) : '–',
      chip: 'ตอนนี้',
      chipKey: 'neutral',
      onClick: () => onIncidents?.(),
    },
    {
      id: 'flood',
      label: 'ถนนน้ำท่วม',
      value: hasFlood ? fmtNum(floodCount) : '–',
      chip: floodChip.label,
      chipKey: floodChip.key,
      onClick: () => onNavigate?.('water'),
    },
    {
      id: 'visitors',
      label: 'คนดูอยู่ตอนนี้',
      value: online != null ? fmtNum(online) : '–',
      chip: 'สด',
      chipKey: 'green',
      onClick: () => onNavigate?.('visitors'),
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {tiles.map((t) => (
        <button
          key={t.id}
          type="button"
          onClick={t.onClick}
          className="dash-card flex min-h-11 cursor-pointer flex-col gap-2 p-4 text-left transition-colors duration-150 hover:bg-[var(--c-raised)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--c-primary)]"
        >
          <span className="text-xs text-[var(--c-muted)]">{t.label}</span>
          <span className="flex items-end gap-1.5">
            <span className="num text-[28px] font-bold leading-9 text-[var(--c-ink)]">{t.value}</span>
          </span>
          <span className={`w-fit rounded-full px-2.5 py-0.5 text-xs font-medium ${chipClass(t.chipKey)}`}>{t.chip}</span>
        </button>
      ))}
    </div>
  );
}
