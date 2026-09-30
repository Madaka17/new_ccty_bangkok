// Plain-language parts of the น้ำเหนือ → ภาคกลาง detail view: a guide to the terms on the page and the
// 10-minute discharge table for every gauge, plus the helpers both views share.
import { useMemo } from 'react';
import { Card, SectionHeader, FOCUS } from '../dashboard/ui.jsx';
import { fmtNum, fmtTime } from '../dashboard/format.js';

const RIVER_TH = { ping: 'ปิง', wang: 'วัง', yom: 'ยม', nan: 'น่าน', chao_phraya: 'เจ้าพระยา', sakae_krang: 'สะแกกรัง', pasak: 'ป่าสัก' };
const SLOTS = 7; // the last hour, every 10 minutes
const fmtQ = (q) => (q == null ? '–' : fmtNum(Math.round(q)));

// Freshest reading of a gauge: the 10-minute estimate when it is newer than the hourly RID figure
export function nowOf(s) {
  if (!s) return {};
  const l = s.latest10;
  if (l && (!s.ts || l.t > s.ts)) return { q: l.q, t: l.t, pct: s.qmax ? (100 * l.q) / s.qmax : s.pct, est: true, change1h: l.change_1h };
  return { q: s.q, t: s.ts, pct: s.pct, est: false, change1h: null };
}

export const fullness = (pct) => (pct == null ? '' : pct >= 100 ? 'ล้นตลิ่งแล้ว' : pct >= 90 ? 'ใกล้เต็มตลิ่ง' : pct >= 70 ? 'น้ำมาก' : 'ยังรับน้ำได้อีก');

const cellTone = (pct) => (pct == null ? '' : pct >= 100 ? 'bg-red-50 text-red-800' : pct >= 70 ? 'bg-amber-50 text-amber-800' : '');

// What the words and numbers on this tab mean
export function HowToRead({ eta }) {
  const rows = [
    ['ลบ.ม./วินาที', 'ปริมาณน้ำที่ไหลผ่านจุดนั้นใน 1 วินาที (ลูกบาศก์เมตรต่อวินาที) เช่น 2,500 ลบ.ม./วินาที เท่ากับน้ำเต็มสระว่ายน้ำโอลิมปิก 1 สระไหลผ่านทุกวินาที'],
    ['เต็มลำน้ำ …%', 'เทียบกับปริมาณน้ำที่ลำน้ำตรงนั้นรับได้ก่อนล้นตลิ่ง (ความจุลำน้ำของกรมชลประทาน): ต่ำกว่า 70% ยังรับน้ำได้อีก · 70-100% น้ำมาก · เกิน 100% ล้นตลิ่ง'],
    ['ทุก 10 นาที (ประมาณ)', 'กรมชลประทานรายงานปริมาณน้ำชั่วโมงละครั้ง ระบบนี้ประมาณค่าทุก 10 นาทีจากระดับน้ำของสถานี สสน. ที่อยู่ใกล้กัน (ทดสอบแล้วคลาดเคลื่อนไม่เกินราว 5%)'],
    ['คาดสูงสุด / คาดการณ์ 4 วัน', 'คำนวณจากน้ำที่วัดได้ที่ต้นทางและเวลาที่น้ำใช้เดินทางลงมา ยังไม่รวมฝนที่จะตกใหม่ และการเปิด-ปิดประตูระบายน้ำ'],
    ['เวลาเดินทางของน้ำ', `น้ำใช้เวลาหลายชั่วโมงถึงหลายวันกว่าจะไหลถึงจุดถัดไป${eta ? ` เช่น น้ำที่ผ่านนครสวรรค์ตอนนี้จะถึงอยุธยาในราว ${eta}` : ''}`],
    ['ลูกศรบนแผนที่', 'ชี้ทิศทางที่น้ำไหล เส้นยิ่งหนาน้ำยิ่งมาก สีแดง = ล้นตลิ่ง สีส้ม = น้ำมาก สีเขียว = ปกติ'],
    ['ม.รทก.', 'เมตรเหนือระดับน้ำทะเลปานกลาง ใช้บอกความสูงของระดับน้ำและตลิ่ง'],
  ];
  return (
    <details className="group rounded-xl border border-slate-200 bg-white">
      <summary className={`cursor-pointer list-none px-5 py-3 text-sm font-semibold text-slate-900 flex items-center gap-2 ${FOCUS}`}>
        <span className="transition-transform group-open:rotate-90" aria-hidden="true">▸</span>
        อ่านหน้านี้อย่างไร (คำอธิบายคำศัพท์และตัวเลข)
      </summary>
      <dl className="px-5 pb-4 grid grid-cols-1 md:grid-cols-[180px_1fr] gap-x-4 gap-y-2 text-sm">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="font-medium text-slate-900">{k}</dt>
            <dd className="text-slate-700 leading-6">{v}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

// Every gauge, the last hour in 10-minute steps; gauges without a 10-minute neighbour show the hourly RID figure
export function TenMinuteTable({ stations, texts, code, onSelect }) {
  const { slots, rows } = useMemo(() => {
    const live = (stations || []).filter((s) => s.status !== 'offline');
    const last = Math.max(0, ...live.map((s) => s.latest10?.t || 0));
    const slots = last ? Array.from({ length: SLOTS }, (_, i) => last - (SLOTS - 1 - i) * 600) : [];
    const rows = live.map((s) => ({ s, by: Object.fromEntries((s.ten_min || []).map((p) => [p.t, p.q])) }));
    return { slots, rows };
  }, [stations]);

  if (!slots.length) return null;
  return (
    <Card className="p-5" aria-labelledby="north-ten-title">
      <SectionHeader
        id="north-ten-title"
        title="ปริมาณน้ำแต่ละจุด ทุก 10 นาที"
        description="หน่วย ลบ.ม./วินาที · 1 ชั่วโมงล่าสุด เรียงจากภาคเหนือลงมา · ค่าประมาณจากระดับน้ำ สสน. ข้างเคียง · จุดที่ไม่มีสถานี สสน. ใกล้ แสดงค่ารายชั่วโมงของกรมชลประทาน · แตะแถวเพื่อดูกราฟ"
      />
      <div className="mt-3 overflow-x-auto scroll-soft">
        <table className="w-full min-w-[720px] text-xs tabular-nums">
          <thead>
            <tr className="text-slate-500 border-b border-slate-200">
              <th className="text-left font-medium py-2 pr-3">จุดวัด</th>
              {slots.map((t) => (
                <th key={t} className="text-right font-medium py-2 px-1.5">
                  {fmtTime(t)}
                </th>
              ))}
              <th className="text-right font-medium py-2 px-1.5">1 ชม.</th>
              <th className="text-left font-medium py-2 pl-3">สถานะ</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map(({ s, by }) => {
              const n = nowOf(s);
              const has10 = slots.some((t) => by[t] != null);
              const ch = s.latest10?.change_1h;
              return (
                <tr
                  key={s.code}
                  onClick={() => s.history?.length && onSelect(s.code)}
                  title={texts?.[s.code] || ''}
                  className={`${s.history?.length ? 'cursor-pointer hover:bg-slate-50' : ''} ${code === s.code ? 'bg-blue-50' : ''}`}
                >
                  <td className="py-2 pr-3">
                    <span className="block text-sm text-slate-900">{s.province}</span>
                    <span className="text-[11px] text-slate-500">
                      {RIVER_TH[s.river] || ''} · {s.code}
                    </span>
                  </td>
                  {has10 ? (
                    slots.map((t) => {
                      const q = by[t];
                      return (
                        <td key={t} className={`text-right py-2 px-1.5 ${cellTone(q != null && s.qmax ? (100 * q) / s.qmax : null)} ${t === slots[slots.length - 1] ? 'font-semibold text-slate-900' : 'text-slate-700'}`}>
                          {fmtQ(q)}
                        </td>
                      );
                    })
                  ) : (
                    <td colSpan={slots.length} className="py-2 px-1.5 text-slate-500">
                      {s.q != null
                        ? `กรมชลประทานรายงานรายชั่วโมง: ${fmtQ(s.q)} (${fmtTime(s.ts)} น.)`
                        : s.below_bank != null
                          ? `ไม่มีข้อมูลปริมาณน้ำ · ระดับน้ำ${s.below_bank > 0 ? 'ต่ำกว่า' : 'สูงกว่า'}ตลิ่ง ${Math.abs(s.below_bank).toFixed(2)} ม.`
                          : 'ไม่มีข้อมูลล่าสุด'}
                    </td>
                  )}
                  <td className="text-right py-2 px-1.5 whitespace-nowrap">
                    {ch == null ? (
                      <span className="text-slate-400">–</span>
                    ) : Math.abs(ch) < Math.max(5, 0.005 * (n.q || 0)) ? (
                      <span className="text-slate-500">ทรงตัว</span>
                    ) : ch > 0 ? (
                      <span className="text-red-700">▲ {fmtQ(ch)}</span>
                    ) : (
                      <span className="text-emerald-700">▼ {fmtQ(-ch)}</span>
                    )}
                  </td>
                  <td className="py-2 pl-3 whitespace-nowrap text-slate-700">
                    {n.pct != null ? `เต็ม ${Math.round(n.pct)}% · ${fullness(n.pct)}` : s.status === 'overflow' ? 'ล้นตลิ่งแล้ว' : ''}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
