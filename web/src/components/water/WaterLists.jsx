import { useState } from 'react';
import { Card, SectionHeader, Badge, Button, Segmented, Skeleton, EmptyState, Truncate, FOCUS } from '../dashboard/ui.jsx';
import { agoText, fmtTime } from '../dashboard/format.js';

export const LEVEL = {
  overflow: { label: 'ล้นตลิ่ง', tone: 'red', bar: 'bg-red-600' },
  high: { label: 'ใกล้ล้น', tone: 'yellow', bar: 'bg-amber-500' },
  normal: { label: 'ปกติ', tone: 'green', bar: 'bg-emerald-600' },
  low: { label: 'น้ำน้อย', tone: 'neutral', bar: 'bg-slate-400' },
  flooding: { label: 'ท่วมขัง', tone: 'red', bar: 'bg-red-600' },
  slight: { label: 'ท่วมเล็กน้อย', tone: 'yellow', bar: 'bg-amber-500' },
};

const fmtM = (v, d = 2) => (v == null ? '–' : v.toFixed(d));

function TrendArrow({ delta }) {
  if (delta == null || Math.abs(delta) < 0.01) return <span className="text-slate-400">→</span>;
  // A metre or more between two 10-minute readings is a sensor glitch, not a trend
  if (Math.abs(delta) >= 1) return <span className="text-slate-400" title="ค่าวัดกระโดดผิดปกติ">ผิดปกติ</span>;
  return delta > 0 ? <span className="text-red-600">↑ {delta.toFixed(2)}</span> : <span className="text-emerald-600">↓ {Math.abs(delta).toFixed(2)}</span>;
}

// ---------------------------------------------------------------- river stations
export function RiverStations({ rows, selectedId, onSelect, loading }) {
  const [filter, setFilter] = useState('all');
  const shown = (rows || []).filter((r) => filter === 'all' || (filter === 'bkk' ? r.province === 'กรุงเทพมหานคร' : r.level === 'overflow' || r.level === 'high'));
  return (
    <Card aria-labelledby="water-river-title" className="p-5">
      <SectionHeader
        id="water-river-title"
        title="สถานีวัดระดับน้ำ แม่น้ำ-คลองหลัก"
        description="สสน. โทรมาตรอัตโนมัติ · แตะแถวเพื่อดูกราฟคาดการณ์ของสถานีนั้น"
        action={<Segmented label="กรองสถานี" value={filter} onChange={setFilter} options={[['all', 'ทั้งหมด'], ['bkk', 'กทม.'], ['risk', 'เสี่ยง']]} />}
      />
      <div className="mt-3 overflow-x-auto">
        {loading ? (
          <div className="space-y-2">
            {[...Array(6)].map((_, i) => (
              <Skeleton key={i} className="h-9 w-full" />
            ))}
          </div>
        ) : !shown.length ? (
          <EmptyState title="ไม่มีสถานีในเงื่อนไขนี้" />
        ) : (
          <table className="w-full text-sm min-w-[560px]">
            <thead>
              <tr className="text-xs text-slate-500 border-b border-slate-200">
                <th className="text-left font-medium py-2 pr-2">สถานี</th>
                <th className="text-left font-medium py-2 pr-2">สถานะ</th>
                <th className="text-right font-medium py-2 pr-2">ระดับ (ม.รทก.)</th>
                <th className="text-right font-medium py-2 pr-2">ห่างตลิ่ง</th>
                <th className="text-right font-medium py-2 pr-2">แนวโน้ม</th>
                <th className="text-right font-medium py-2">วัดเมื่อ</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => {
                const lv = LEVEL[r.level] || LEVEL.normal;
                const on = r.id === String(selectedId);
                return (
                  <tr
                    key={r.id}
                    onClick={() => onSelect(r.id)}
                    tabIndex={0}
                    onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), onSelect(r.id))}
                    aria-selected={on}
                    className={`cursor-pointer border-b border-slate-100 transition-colors ${on ? 'bg-blue-50' : 'hover:bg-slate-50'} ${FOCUS}`}
                  >
                    <td className="py-2 pr-2 max-w-[240px]">
                      <Truncate text={r.name} className="font-medium text-slate-900" />
                      <Truncate text={`${r.district ? `${r.district} · ` : ''}${r.province}`} className="text-xs text-slate-500" />
                    </td>
                    <td className="py-2 pr-2">
                      <Badge tone={lv.tone} dot>
                        {lv.label}
                      </Badge>
                      {r.official_forecast && <Badge tone="blue" className="ml-1">7 วัน</Badge>}
                    </td>
                    <td className="py-2 pr-2 text-right tabular-nums text-slate-900">{fmtM(r.msl)}</td>
                    <td className={`py-2 pr-2 text-right tabular-nums ${r.level === 'overflow' ? 'text-red-700 font-medium' : 'text-slate-700'}`}>
                      {r.diff_bank == null ? '–' : `${r.level === 'overflow' ? '+' : '−'}${fmtM(Math.abs(r.diff_bank))}`}
                    </td>
                    <td className="py-2 pr-2 text-right tabular-nums text-xs">
                      <TrendArrow delta={r.trend} />
                    </td>
                    <td className="py-2 text-right text-xs text-slate-500 whitespace-nowrap">{agoText(r.ts)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
      <p className="mt-2 text-xs text-slate-500">แนวโน้ม = เทียบกับค่าวัดก่อนหน้า (ม.) · สถานีที่มีป้าย “7 วัน” มีคาดการณ์ทางการจาก สสน.</p>
    </Card>
  );
}

// ---------------------------------------------------------------- tide forecast
export function TideCard({ rows, loading }) {
  return (
    <Card aria-labelledby="water-tide-title" className="p-5">
      <SectionHeader id="water-tide-title" title="น้ำทะเลหนุนวันนี้" description="คาดการณ์ระดับน้ำขึ้น-ลง ปากแม่น้ำเจ้าพระยาและท่าจีน (กรมอุทกศาสตร์ ผ่าน สสน.)" />
      <div className="mt-3 space-y-3">
        {loading ? (
          [...Array(3)].map((_, i) => <Skeleton key={i} className="h-12 w-full" />)
        ) : !rows?.length ? (
          <EmptyState title="ยังไม่มีข้อมูลน้ำขึ้นน้ำลง" />
        ) : (
          rows.map((t) => {
            const vals = t.hours.map((h) => h.v).filter((v) => v != null);
            const lo = Math.min(...vals, t.min ?? 0);
            const hi = Math.max(...vals, t.max ?? 0);
            return (
              <div key={t.code} className="rounded-lg border border-slate-200 px-3 py-2.5">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <p className="text-sm font-medium text-slate-900">{t.name}</p>
                  <p className="text-xs text-slate-600 tabular-nums">
                    สูงสุด <span className="font-semibold text-slate-900">{fmtM(t.max)} ม.</span> เวลา {t.max_time} · ต่ำสุด {fmtM(t.min)} ม. เวลา {t.min_time}
                  </p>
                </div>
                <div className="mt-2 flex items-end gap-1.5 h-10" role="img" aria-label={`ระดับน้ำ ${t.name} รายช่วงเวลา`}>
                  {t.hours.map((h) => {
                    const pct = h.v == null ? 0 : hi === lo ? 50 : ((h.v - lo) / (hi - lo)) * 100;
                    return (
                      <div key={h.h} className="flex-1 flex flex-col items-center gap-0.5" title={`${String(h.h).padStart(2, '0')}:00 น. ${fmtM(h.v)} ม.`}>
                        <div className="w-full rounded-sm bg-blue-100 relative h-6">
                          <div className="absolute bottom-0 left-0 right-0 rounded-sm bg-blue-600" style={{ height: `${Math.max(6, pct)}%` }} />
                        </div>
                        <span className="text-[10px] text-slate-500">{String(h.h).padStart(2, '0')}:00</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })
        )}
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------- canals + flood road sensors (BMA)
export function CanalCard({ canals, counts, total, roads, loading }) {
  const [tab, setTab] = useState('canal');
  const risky = (canals || []).filter((c) => c.level !== 'normal');
  // Canals: every raised one, then top up with the fullest normal ones so the list is never a single row
  const canalList = [...risky, ...(canals || []).filter((c) => c.level === 'normal')].slice(0, Math.max(8, risky.length));
  const list = tab === 'canal' ? canalList : roads?.items || [];
  return (
    <Card aria-labelledby="water-canal-title" className="p-5">
      <SectionHeader
        id="water-canal-title"
        title="คลองและถนนในกรุงเทพฯ"
        description="เซ็นเซอร์สำนักการระบายน้ำ กทม. · คลอง = % ความจุ, ถนน = ความลึกน้ำท่วมขัง (ซม.)"
        action={<Segmented label="ประเภท" value={tab} onChange={setTab} options={[['canal', `คลอง ${total || ''}`], ['road', `ถนน ${roads ? roads.flooding + roads.slight + roads.normal : ''}`]]} />}
      />
      {tab === 'canal' ? (
        <p className="mt-2 text-xs text-slate-600">
          ล้นตลิ่ง <b className="text-red-700">{counts?.overflow ?? 0}</b> · ใกล้ล้น <b className="text-amber-700">{counts?.high ?? 0}</b> · ปกติ <b className="text-emerald-700">{counts?.normal ?? 0}</b>
          {!loading && ` · แสดง${risky.length ? 'คลองที่น้ำสูงและ' : ''}คลองที่น้ำสูงสุด ${canalList.length} แห่ง`}
        </p>
      ) : (
        <p className="mt-2 text-xs text-slate-600">
          ท่วมขัง <b className="text-red-700">{roads?.flooding ?? 0}</b> · ท่วมเล็กน้อย <b className="text-amber-700">{roads?.slight ?? 0}</b> · แห้ง <b className="text-emerald-700">{roads?.normal ?? 0}</b> จุด
        </p>
      )}
      <ul className="mt-3 divide-y divide-slate-100">
        {loading ? (
          [...Array(5)].map((_, i) => (
            <li key={i} className="py-2">
              <Skeleton className="h-8 w-full" />
            </li>
          ))
        ) : !list.length ? (
          <li className="py-2">
            <EmptyState title={tab === 'canal' ? 'ไม่มีข้อมูลคลอง' : 'ไม่มีถนนที่มีน้ำท่วมขังจากเซ็นเซอร์ตอนนี้'} description={tab === 'road' && roads?.worst ? `จุดวัดล่าสุด ${roads.worst.name} (${roads.worst.district}) ${agoText(roads.worst.ts)}` : undefined} />
          </li>
        ) : (
          list.map((c) => {
            const lv = LEVEL[c.level] || LEVEL.normal;
            const pct = tab === 'canal' ? Math.min(100, Math.max(0, c.storage_pct ?? 0)) : Math.min(100, ((c.depth_cm ?? 0) / 30) * 100);
            return (
              <li key={c.id} className="py-2 flex items-center gap-3">
                <div className="min-w-0 flex-1">
                  <Truncate text={c.name} className="text-sm text-slate-900" />
                  <p className="text-xs text-slate-500">
                    เขต{c.district} · {agoText(c.ts)}
                  </p>
                </div>
                <div className="w-24 hidden sm:block">
                  <div className="h-1.5 rounded-full bg-slate-100 overflow-hidden">
                    <div className={`h-full ${lv.bar}`} style={{ width: `${pct}%` }} />
                  </div>
                </div>
                <span className="text-sm tabular-nums text-slate-900 w-16 text-right">{tab === 'canal' ? `${fmtM(c.storage_pct, 0)}%` : `${fmtM(c.depth_cm, 0)} ซม.`}</span>
                <Badge tone={lv.tone}>{lv.label}</Badge>
              </li>
            );
          })
        )}
      </ul>
    </Card>
  );
}

// ---------------------------------------------------------------- rain warnings
export function RainCard({ rows, loading }) {
  const forecast = (rows || []).filter((r) => r.kind === 'forecast');
  const observed = (rows || []).filter((r) => r.kind === 'observed').sort((a, b) => (b.mm || 0) - (a.mm || 0));
  return (
    <Card aria-labelledby="water-rain-title" className="p-5">
      <SectionHeader id="water-rain-title" title="ฝนในกรุงเทพฯ และปริมณฑล" description="เตือนฝนหนักล่วงหน้า 24 ชม. และจุดที่ฝนสะสมสูงในรอบ 24 ชม. (สสน.)" />
      <div className="mt-3 space-y-2">
        {loading ? (
          <Skeleton className="h-16 w-full" />
        ) : (
          <>
            {forecast.length ? (
              forecast.map((r, i) => (
                <div key={`f${i}`} className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
                  <b>เตือน {r.text}</b> {r.province}
                  {r.district ? ` (${r.district})` : ''} · คาดฝน {fmtM(r.mm, 0)} มม. {r.ts ? `ภายใน ${fmtTime(r.ts)} น.` : ''}
                </div>
              ))
            ) : (
              <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">ไม่มีประกาศเตือนฝนตกหนักล่วงหน้าในเขตกรุงเทพฯ และปริมณฑล</div>
            )}
            {observed.length > 0 && (
              <ul className="divide-y divide-slate-100">
                {observed.slice(0, 6).map((r, i) => (
                  <li key={`o${i}`} className="py-1.5 flex items-center justify-between gap-3 text-sm">
                    <Truncate text={`${r.district ? `เขต${r.district}` : r.province} · ${r.text}`} className="text-slate-700" />
                    <span className="tabular-nums font-medium text-slate-900 whitespace-nowrap">{fmtM(r.mm, 1)} มม.</span>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------- upstream stations with official forecast
export function UpstreamCard({ rows, onPick, loading }) {
  return (
    <Card aria-labelledby="water-upstream-title" className="p-5">
      <SectionHeader id="water-upstream-title" title="สถานีต้นน้ำที่กำหนดระดับน้ำกรุงเทพฯ" description="สถานีหลักบนเจ้าพระยา-ป่าสัก ที่ สสน. ออกคาดการณ์ 7 วัน" />
      <ul className="mt-3 divide-y divide-slate-100">
        {loading
          ? [...Array(3)].map((_, i) => (
              <li key={i} className="py-2">
                <Skeleton className="h-10 w-full" />
              </li>
            ))
          : (rows || []).map((s) => {
              const over = s.critical != null && s.msl != null && s.msl >= s.critical;
              const warn = !over && s.warning != null && s.msl != null && s.msl >= s.warning;
              return (
                <li key={s.id} className="py-2 flex items-center gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-slate-900">{s.name}</p>
                    <p className="text-xs text-slate-500">
                      {s.province} · เฝ้าระวัง {fmtM(s.warning)} · วิกฤต {fmtM(s.critical)} ม.รทก.
                    </p>
                  </div>
                  <span className="text-sm tabular-nums font-semibold text-slate-900">{fmtM(s.msl)}</span>
                  <Badge tone={over ? 'red' : warn ? 'yellow' : 'green'} dot>
                    {over ? 'วิกฤต' : warn ? 'เฝ้าระวัง' : 'ปกติ'}
                  </Badge>
                  <Button size="sm" onClick={() => onPick(s.id)}>
                    กราฟ
                  </Button>
                </li>
              );
            })}
      </ul>
    </Card>
  );
}
