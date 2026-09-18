// Road density tiers (หนาแน่น / ปานกลาง / คล่องตัว) from /api/analytics/summary .density.
// Shared by the dashboard overview tab and the analytics page; click a tier card to list its roads.
import { useState } from 'react';
import { Card, Badge, SectionHeader, EmptyState, FOCUS } from './ui.jsx';
import { StatusBanner, ShareBar } from './primitives.jsx';
import { fmtNum, STATUS } from './format.js';

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
          return (
            <Card
              key={t.id}
              as="button"
              type="button"
              aria-pressed={on}
              onClick={() => setOpen(on ? null : t.id)}
              className={`cursor-pointer text-left p-5 border transition-colors duration-150 hover:bg-slate-50 ${FOCUS} ${on ? `${STATUS[t.color].border} ring-2 ring-blue-600` : STATUS[t.color].border}`}
            >
              <div className="flex items-center justify-between">
                <Badge tone={t.color} dot>{t.label}</Badge>
                <span className="text-xs text-slate-500">{t.speed}</span>
              </div>
              <p className={`text-3xl font-semibold mt-2 tabular-nums ${STATUS[t.color].text}`}>{t.km_pct}%</p>
              <p className="text-xs text-slate-600">ของระยะทาง · {t.road_pct}% ของจำนวนสาย ({fmtNum(t.roads)} สาย)</p>
              <p className="text-xs text-slate-500 mt-1">{t.note}</p>
              <p className="text-xs text-blue-700 mt-2">{on ? 'ซ่อนรายชื่อถนน' : `ดูถนนทั้ง ${fmtNum(t.roads)} สาย`}</p>
            </Card>
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
