import { useCallback, useEffect, useMemo, useState } from 'react';
import { Card, SectionHeader, Badge, Button, EmptyState, Skeleton } from '../dashboard/ui.jsx';
import { fmtNum, fmtDuration, fmtDateTime } from '../dashboard/format.js';
import { addAIAccuracy, deleteAIAccuracy, fetchAIAccuracy, resetAIPassed } from '../../lib/api.js';

// Manual count vs AI count for the live camera: the AI side is the detector's passed-vehicle
// counter since "เริ่มนับ"; the user counts the same window by eye and types the number.
// Absolute error = |manual − AI|, accuracy = 100 − error / manual × 100.
const MANUAL = 'bg-blue-600';
const AI = 'bg-amber-500';

const accTone = (p) => (p == null ? 'neutral' : p >= 95 ? 'green' : p >= 85 ? 'yellow' : 'red');

function fmtAcc(p) {
  return p == null ? '–' : `${Number(p).toFixed(1)}%`;
}

function Elapsed({ since }) {
  const [, tick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => tick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, []);
  if (!since) return null;
  const s = Math.max(0, Math.floor(Date.now() / 1000 - since));
  const mm = String(Math.floor(s / 60)).padStart(2, '0');
  const ss = String(s % 60).padStart(2, '0');
  return <span className="tabular-nums">{mm}:{ss}</span>;
}

export default function AccuracyPanel({ active, stats, camTitle, onToast }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [manual, setManual] = useState('');
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await fetchAIAccuracy(50));
    } catch {
      /* keep last */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (active) load();
  }, [active, load]);

  const aiNow = stats?.passed_total ?? 0;
  const manualNum = manual === '' ? null : Number(manual);
  const preview = useMemo(() => {
    if (manualNum == null || Number.isNaN(manualNum)) return null;
    const err = Math.abs(manualNum - aiNow);
    const acc = manualNum <= 0 ? (err === 0 ? 100 : 0) : Math.max(0, 100 - (err * 100) / manualNum);
    return { err, acc };
  }, [manualNum, aiNow]);

  const startCount = async () => {
    try {
      await resetAIPassed();
      setManual('');
      onToast?.('เริ่มนับใหม่แล้ว นับด้วยตาไปพร้อมกับ AI ได้เลย');
    } catch {
      onToast?.('รีเซ็ตตัวนับไม่สำเร็จ');
    }
  };

  const save = async () => {
    if (manualNum == null || Number.isNaN(manualNum) || manualNum < 0) return;
    setSaving(true);
    try {
      // send the AI number the user saw next to their entry, not whatever the counter reaches a second later
      await addAIAccuracy({
        manual_count: Math.round(manualNum),
        ai_count: aiNow,
        camid: stats?.camid,
        title: camTitle || stats?.title,
        duration_s: stats?.passed_since ? Math.floor(Date.now() / 1000 - stats.passed_since) : undefined,
        note: note.trim() || undefined,
      });
      setManual('');
      setNote('');
      await load();
      onToast?.('บันทึกผลเทียบแล้ว');
    } catch (e) {
      onToast?.(`บันทึกไม่สำเร็จ: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  const remove = async (id) => {
    try {
      await deleteAIAccuracy(id);
      await load();
    } catch {
      onToast?.('ลบไม่สำเร็จ');
    }
  };

  const items = data?.items || [];
  const summary = data?.summary;
  const chartRows = items.slice(0, 8).reverse();
  const chartMax = Math.max(1, ...chartRows.flatMap((r) => [r.manual_count, r.ai_count]));

  return (
    <Card className="p-5">
      <SectionHeader
        title="ตรวจความแม่นยำ: นับมือ vs AI"
        description="กด “เริ่มนับ” แล้วนับรถที่ผ่านกล้องด้วยตาไปพร้อมกัน จบแล้วกรอกตัวเลข ระบบคำนวณ Absolute Error และ Accuracy ให้"
        action={
          summary ? (
            <div className="flex items-center gap-2">
              <Badge tone="neutral">MAE {fmtNum(summary.mae)} คัน</Badge>
              <Badge tone={accTone(summary.mean_accuracy_pct)} dot>
                Accuracy เฉลี่ย {fmtAcc(summary.mean_accuracy_pct)}
              </Badge>
            </div>
          ) : null
        }
      />

      {/* Live counter + entry form */}
      <div className="mt-4 grid grid-cols-1 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] gap-4">
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 flex flex-col gap-3">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-xs text-slate-600">AI นับได้ (ตั้งแต่เริ่มนับ) · {camTitle || stats?.title || 'ยังไม่ได้เลือกกล้อง'}</p>
              <p className="text-3xl font-semibold tabular-nums text-amber-700 leading-9">{fmtNum(aiNow)} <span className="text-sm font-normal text-slate-500">คัน</span></p>
              <p className="text-[11px] text-slate-500 mt-0.5">
                รถยนต์ {fmtNum(stats?.passed_cars ?? 0)} · มอเตอร์ไซค์ {fmtNum(stats?.passed_motorcycles ?? 0)} · บรรทุก {fmtNum(stats?.passed_trucks ?? 0)}
                {stats?.passed_since ? <> · เวลา <Elapsed since={stats.passed_since} /></> : null}
              </p>
            </div>
            <Button size="sm" variant="secondary" onClick={startCount} disabled={!stats?.active}>
              เริ่มนับใหม่
            </Button>
          </div>

          <div className="grid grid-cols-[1fr_auto] gap-2 items-end">
            <label className="block">
              <span className="text-xs text-slate-600">จำนวนที่นับด้วยตา (Manual Count)</span>
              <input
                type="number"
                min="0"
                inputMode="numeric"
                value={manual}
                onChange={(e) => setManual(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && save()}
                placeholder="เช่น 1487"
                className="mt-1 w-full h-10 rounded-lg border border-slate-300 bg-white px-3 text-sm tabular-nums focus:outline-none focus:ring-2 focus:ring-blue-600"
              />
            </label>
            <Button variant="primary" onClick={save} loading={saving} disabled={preview == null || !stats?.active}>
              บันทึกผลเทียบ
            </Button>
          </div>
          <input
            type="text"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="หมายเหตุ (ไม่บังคับ) เช่น ช่วงเย็น ฝนตก"
            className="w-full h-9 rounded-lg border border-slate-300 bg-white px-3 text-xs focus:outline-none focus:ring-2 focus:ring-blue-600"
          />

          {preview && (
            <div className="grid grid-cols-3 gap-2 text-center">
              <div className="rounded-lg bg-white border border-slate-200 py-2">
                <p className="text-[11px] text-slate-500">Manual</p>
                <p className="text-lg font-semibold tabular-nums text-blue-700">{fmtNum(manualNum)}</p>
              </div>
              <div className="rounded-lg bg-white border border-slate-200 py-2">
                <p className="text-[11px] text-slate-500">Absolute Error</p>
                <p className="text-lg font-semibold tabular-nums text-slate-900">{fmtNum(preview.err)}</p>
              </div>
              <div className="rounded-lg bg-white border border-slate-200 py-2">
                <p className="text-[11px] text-slate-500">Accuracy</p>
                <p className={`text-lg font-semibold tabular-nums ${preview.acc >= 95 ? 'text-emerald-700' : preview.acc >= 85 ? 'text-amber-700' : 'text-red-700'}`}>{fmtAcc(preview.acc)}</p>
              </div>
            </div>
          )}
        </div>

        {/* Manual vs AI grouped bars */}
        <div className="rounded-xl border border-slate-200 p-4 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <p className="text-sm font-semibold text-slate-900">Manual vs. AI Vehicle Count</p>
            <div className="flex items-center gap-3 text-[11px] text-slate-600">
              <span className="inline-flex items-center gap-1"><span className={`w-2.5 h-2.5 rounded-sm ${MANUAL}`} /> Manual</span>
              <span className="inline-flex items-center gap-1"><span className={`w-2.5 h-2.5 rounded-sm ${AI}`} /> AI</span>
            </div>
          </div>
          {loading ? (
            <Skeleton className="mt-3 h-40 w-full" />
          ) : !chartRows.length ? (
            <div className="mt-3">
              <EmptyState title="ยังไม่มีผลเทียบ" description="บันทึกครั้งแรกแล้วกราฟจะขึ้นที่นี่" />
            </div>
          ) : (
            <div className="mt-3 flex items-end gap-2 h-44 border-b border-slate-200 pb-1">
              {chartRows.map((r) => (
                <div key={r.id} className="flex-1 min-w-0 h-full flex flex-col justify-end items-center gap-1" title={`${r.title}: manual ${r.manual_count} · AI ${r.ai_count} · error ${r.abs_error}`}>
                  <div className="w-full flex items-end justify-center gap-1 h-full">
                    <div className="flex-1 max-w-[26px] flex flex-col items-center justify-end h-full">
                      <span className="text-[9px] tabular-nums text-blue-700 mb-0.5">{fmtNum(r.manual_count)}</span>
                      <div className={`w-full rounded-t ${MANUAL}`} style={{ height: `${Math.max(3, (r.manual_count / chartMax) * 100)}%` }} />
                    </div>
                    <div className="flex-1 max-w-[26px] flex flex-col items-center justify-end h-full">
                      <span className="text-[9px] tabular-nums text-amber-700 mb-0.5">{fmtNum(r.ai_count)}</span>
                      <div className={`w-full rounded-t ${AI}`} style={{ height: `${Math.max(3, (r.ai_count / chartMax) * 100)}%` }} />
                    </div>
                  </div>
                  <span className="text-[10px] text-slate-500 truncate max-w-full">{r.title || r.camid}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Table */}
      <div className="mt-4 overflow-x-auto rounded-xl border border-slate-200">
        <table className="w-full text-xs min-w-[640px]">
          <thead>
            <tr className="bg-slate-50 text-slate-600 border-b border-slate-200">
              <th className="text-left font-medium py-2.5 px-3">Camera / Location</th>
              <th className="text-right font-medium py-2.5 px-3">Manual Count</th>
              <th className="text-right font-medium py-2.5 px-3">AI Count</th>
              <th className="text-right font-medium py-2.5 px-3">Absolute Error</th>
              <th className="text-right font-medium py-2.5 px-3">Accuracy (%)</th>
              <th className="text-right font-medium py-2.5 px-3">เวลา</th>
              <th className="py-2.5 px-2" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading ? (
              <tr><td colSpan={7} className="px-3 py-3"><Skeleton className="h-4 w-full" /></td></tr>
            ) : !items.length ? (
              <tr><td colSpan={7} className="px-3 py-6 text-center text-slate-500">ยังไม่มีข้อมูล — กด “เริ่มนับใหม่” แล้วนับพร้อม AI</td></tr>
            ) : (
              items.map((r) => (
                <tr key={r.id} className="hover:bg-slate-50">
                  <td className="py-2 px-3">
                    <p className="font-medium text-slate-900 truncate max-w-[260px]">{r.title || r.camid}</p>
                    {(r.note || r.duration_s) && (
                      <p className="text-[10px] text-slate-500 truncate max-w-[260px]">
                        {[r.duration_s ? `นับ ${fmtDuration(r.duration_s)}` : null, r.note].filter(Boolean).join(' · ')}
                      </p>
                    )}
                  </td>
                  <td className="py-2 px-3 text-right tabular-nums font-semibold text-blue-700">{fmtNum(r.manual_count)}</td>
                  <td className="py-2 px-3 text-right tabular-nums font-semibold text-amber-700">{fmtNum(r.ai_count)}</td>
                  <td className="py-2 px-3 text-right tabular-nums text-slate-900">{fmtNum(r.abs_error)}</td>
                  <td className="py-2 px-3 text-right"><Badge tone={accTone(r.accuracy_pct)}>{fmtAcc(r.accuracy_pct)}</Badge></td>
                  <td className="py-2 px-3 text-right tabular-nums text-slate-500 whitespace-nowrap">{fmtDateTime(r.ts)}</td>
                  <td className="py-2 px-2 text-right">
                    <button type="button" onClick={() => remove(r.id)} className="cursor-pointer text-slate-400 hover:text-red-600 text-xs" aria-label="ลบ">ลบ</button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
          {summary && (
            <tfoot>
              <tr className="bg-slate-50 border-t border-slate-200 font-semibold text-slate-900">
                <td className="py-2.5 px-3">Average ({summary.count} ครั้ง)</td>
                <td className="py-2.5 px-3 text-right tabular-nums text-slate-500 font-normal">รวม {fmtNum(summary.manual_total)}</td>
                <td className="py-2.5 px-3 text-right tabular-nums text-slate-500 font-normal">รวม {fmtNum(summary.ai_total)}</td>
                <td className="py-2.5 px-3 text-right tabular-nums">{fmtNum(summary.mae)}</td>
                <td className="py-2.5 px-3 text-right tabular-nums">{fmtAcc(summary.mean_accuracy_pct)}</td>
                <td colSpan={2} />
              </tr>
            </tfoot>
          )}
        </table>
      </div>
    </Card>
  );
}
