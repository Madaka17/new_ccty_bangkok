// Road density tiers (หนาแน่น / ปานกลาง / คล่องตัว) from /api/analytics/summary .density.
// Shared by the dashboard overview tab and the analytics page; click a tier card to list its roads.
import { useState } from 'react';
import { Card, Badge, SectionHeader, EmptyState, FOCUS } from './ui.jsx';
import { StatusBanner, ShareBar } from './primitives.jsx';
import { fmtNum, STATUS } from './format.js';

const TIER_CONFIG = {
  red: {
    topBar: 'from-rose-500 via-red-400 to-transparent',
    glow: 'bg-rose-500/10 dark:bg-rose-500/15',
    statusColor: 'text-rose-600 dark:text-rose-400',
    badgeTone: 'red',
  },
  yellow: {
    topBar: 'from-amber-500 via-orange-400 to-transparent',
    glow: 'bg-amber-500/10 dark:bg-amber-500/15',
    statusColor: 'text-amber-600 dark:text-amber-400',
    badgeTone: 'yellow',
  },
  green: {
    topBar: 'from-emerald-500 via-teal-400 to-transparent',
    glow: 'bg-emerald-500/10 dark:bg-emerald-500/15',
    statusColor: 'text-emerald-600 dark:text-emerald-400',
    badgeTone: 'green',
  },
};

// showShare=false hides the network share card (dashboard overview only needs the tier cards)
export default function DensityPanel({ d, onOpenRoad, showShare = true }) {
  const [open, setOpen] = useState(null); // tier id whose roads are listed
  if (!d?.ready) return <EmptyState title="รอข้อมูลเส้นจราจร" description="ระบบกำลังสร้างดัชนีถนน" />;
  const tier = d.tiers.find((t) => t.id === open);
  return (
    <div className="flex flex-col gap-4">
      <StatusBanner tone="neutral" label="หมายเหตุ">{d.proxy_note}</StatusBanner>
      {showShare && (
      <Card className="p-5">
        <SectionHeader id="density-share" title="สัดส่วนโครงข่ายถนนตามระดับความหนาแน่น" description={`คิดจากระยะทางรวม ${fmtNum(Math.round(d.total_km))} กม. (${fmtNum(d.road_count)} สายที่มีชื่อ) · กดกล่องด้านล่างเพื่อดูรายชื่อถนน`} />
        <div className="mt-4">
          <ShareBar parts={d.tiers.map((t) => ({ label: t.label, value: t.km, color: STATUS[t.color].bar }))} unit=" กม." />
        </div>
      </Card>
      )}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {d.tiers.map((t) => {
          const on = open === t.id;
          const cfg = TIER_CONFIG[t.color] || TIER_CONFIG.green;
          return (
            <button
              key={t.id}
              type="button"
              aria-pressed={on}
              onClick={() => setOpen(on ? null : t.id)}
              className={`group relative cursor-pointer text-left rounded-2xl border p-4 sm:p-5 flex flex-col justify-between overflow-hidden bg-white/95 dark:bg-slate-900/90 backdrop-blur-md transition-all duration-300 ease-out hover:-translate-y-1 hover:shadow-xl dark:hover:shadow-black/50 ${
                on
                  ? 'border-blue-500 ring-2 ring-blue-500/30 dark:ring-blue-400/40 shadow-lg'
                  : 'border-slate-200/90 dark:border-slate-800/90 hover:border-slate-300 dark:hover:border-slate-700'
              } ${FOCUS}`}
            >
              {/* Top accent gradient line */}
              <span className={`absolute top-0 inset-x-0 h-[3px] bg-gradient-to-r ${cfg.topBar}`} />

              {/* Subtle ambient corner glow */}
              <span className={`pointer-events-none absolute -top-10 -right-10 w-28 h-28 rounded-full blur-2xl transition-opacity duration-300 opacity-40 group-hover:opacity-100 ${cfg.glow}`} />

              <div className="relative z-10 w-full">
                {/* Header row: Status badge + Speed info */}
                <div className="flex items-center justify-between gap-2">
                  <Badge tone={cfg.badgeTone} dot>
                    {t.label}
                  </Badge>
                  <span className="text-xs px-2 py-0.5 rounded-md font-medium border bg-slate-50/90 dark:bg-slate-800/80 border-slate-200/80 dark:border-slate-700/80 text-slate-600 dark:text-slate-300">
                    {t.speed}
                  </span>
                </div>

                {/* Big percentage metric */}
                <div className="mt-3.5 mb-1 flex items-baseline gap-2">
                  <span className={`text-3xl sm:text-4xl font-extrabold tracking-tight tabular-nums ${cfg.statusColor}`}>
                    {t.km_pct}%
                  </span>
                  <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
                    ของระยะทาง
                  </span>
                </div>

                <p className="text-xs text-slate-600 dark:text-slate-300 font-medium">
                  {t.road_pct}% ของจำนวนสาย ({fmtNum(t.roads)} สาย)
                </p>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                  {t.note}
                </p>
              </div>

              {/* Action row at bottom with divider */}
              <div className="relative z-10 mt-3.5 pt-2.5 border-t border-slate-100 dark:border-slate-800/80 flex items-center justify-between w-full">
                <span className={`text-xs font-semibold flex items-center gap-1.5 transition-colors ${
                  on ? 'text-blue-600 dark:text-blue-400' : 'text-slate-600 dark:text-slate-300 group-hover:text-blue-600 dark:group-hover:text-blue-400'
                }`}>
                  {on ? 'ซ่อนรายชื่อถนน' : `ดูถนนทั้ง ${fmtNum(t.roads)} สาย`}
                  <svg
                    viewBox="0 0 16 16"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className={`w-3.5 h-3.5 transition-transform duration-200 ${on ? 'rotate-90' : 'group-hover:translate-x-0.5'}`}
                  >
                    <path d="M6 12l4-4-4-4" />
                  </svg>
                </span>
              </div>
            </button>
          );
        })}
      </div>
      {tier && (
        <Card className="p-5">
          <SectionHeader
            id="tier-roads"
            title={`ถนนระดับ${tier.label} (${tier.speed})`}
            description={`${fmtNum(tier.roads)} สาย · เรียงตามระยะทางที่ติด · กดชื่อถนนเพื่อเปิดกล้อง`}
            action={<Badge tone={tier.color} dot>{tier.label}</Badge>}
          />
          {tier.road_list.length === 0 ? (
            <p className="text-sm text-slate-600 mt-3">ไม่มีถนนในระดับนี้ขณะนี้</p>
          ) : (
            <ol className="mt-3 divide-y divide-slate-100 max-h-[32rem] overflow-y-auto scroll-soft">
              {tier.road_list.map((r, i) => (
                <li key={r.name}>
                  <button
                    type="button"
                    onClick={() => onOpenRoad?.(r.name)}
                    title={`เปิดกล้องบน ${r.name}`}
                    className={`cursor-pointer w-full text-left flex items-center gap-3 px-2 py-2 rounded-lg hover:bg-slate-50 transition-colors duration-150 ${FOCUS}`}
                  >
                    <span className="w-7 text-center text-xs text-slate-500 tabular-nums shrink-0">{i + 1}</span>
                    <span className="text-sm text-slate-900 truncate flex-1 min-w-0">{r.name}</span>
                    <div className="flex h-1.5 w-20 overflow-hidden rounded-full bg-slate-100 shrink-0" aria-hidden="true">
                      {r.green_pct > 0 && <div className={STATUS.green.bar} style={{ width: `${r.green_pct}%` }} />}
                      {r.yellow_pct > 0 && <div className={STATUS.yellow.bar} style={{ width: `${r.yellow_pct}%` }} />}
                      {r.red_pct > 0 && <div className={STATUS.red.bar} style={{ width: `${r.red_pct}%` }} />}
                    </div>
                    <span className="text-xs text-slate-600 tabular-nums whitespace-nowrap shrink-0">
                      ติด {r.red_km} / {r.length_km} กม. · ระบาย {r.flow}
                    </span>
                  </button>
                </li>
              ))}
            </ol>
          )}
        </Card>
      )}
    </div>
  );
}
