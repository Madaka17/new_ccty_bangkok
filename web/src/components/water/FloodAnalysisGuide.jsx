import { useState } from 'react';
import { Card, Badge, Button } from '../dashboard/ui.jsx';

export default function FloodAnalysisGuide({ summary, onNavigate, onAsk }) {
  const [activeTab, setActiveTab] = useState('forecast'); // 'diagnosis' | 'forecast' | 'action' | 'public'

  const overflowCount = summary?.river_counts?.overflow || 0;
  const canalOverflow = summary?.canal_counts?.overflow || 0;
  const highCount = (summary?.river_counts?.high || 0) + (summary?.canal_counts?.high || 0);

  return (
    <Card className="p-5 border-blue-200 bg-white shadow-sm overflow-hidden">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-100">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-600 text-white flex items-center justify-center text-xl shrink-0 shadow-sm">
            📋
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="text-base font-bold text-slate-900">
                วิเคราะห์และคาดการณ์สถานการณ์น้ำท่วม พร้อมแนวทางป้องกัน
              </h3>
              <Badge tone="blue" className="font-semibold">
                Google Flood Hub & ThaiWater
              </Badge>
            </div>
            <p className="text-xs text-slate-600 mt-0.5">
              ประเมินความเสี่ยงแม่น้ำเจ้าพระยา-คลองหลัก และมาตรการรับมือน้ำท่วมสำหรับ กทม. และปริมณฑล
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <Button
            size="sm"
            variant="secondary"
            onClick={() => onNavigate && onNavigate('map')}
            className="border-blue-300 text-blue-800 hover:bg-blue-50 text-xs"
          >
            🗺️ ตรวจสอบจุดเสี่ยงบนแผนที่
          </Button>
          <Button
            size="sm"
            variant="primary"
            onClick={() => onAsk && onAsk('วิเคราะห์สถานการณ์น้ำท่วมในเขตของฉันและเส้นทางเลี่ยงน้ำท่วม')}
            className="bg-blue-600 border-blue-600 hover:bg-blue-700 text-xs"
          >
            🤖 ถาม AI เรื่องน้ำท่วม
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <div className="mt-4 flex items-center gap-1.5 border-b border-slate-100 pb-2 overflow-x-auto scroll-soft">
        <button
          type="button"
          onClick={() => setActiveTab('forecast')}
          className={`cursor-pointer px-3.5 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-colors ${
            activeTab === 'forecast'
              ? 'bg-blue-600 text-white shadow-sm'
              : 'bg-slate-50 text-slate-700 hover:bg-slate-100'
          }`}
        >
          🔮 คาดการณ์สถานการณ์ (24 ชม. - 7 วัน)
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('diagnosis')}
          className={`cursor-pointer px-3.5 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-colors ${
            activeTab === 'diagnosis'
              ? 'bg-blue-600 text-white shadow-sm'
              : 'bg-slate-50 text-slate-700 hover:bg-slate-100'
          }`}
        >
          🔍 วิเคราะห์ความเสี่ยง 3 น้ำ (เหนือ/หนุน/ฝน)
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('action')}
          className={`cursor-pointer px-3.5 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-colors ${
            activeTab === 'action'
              ? 'bg-blue-600 text-white shadow-sm'
              : 'bg-slate-50 text-slate-700 hover:bg-slate-100'
          }`}
        >
          🛡️ แนวทางแก้ไข & มาตรการภาครัฐ
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('public')}
          className={`cursor-pointer px-3.5 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-colors ${
            activeTab === 'public'
              ? 'bg-blue-600 text-white shadow-sm'
              : 'bg-slate-50 text-slate-700 hover:bg-slate-100'
          }`}
        >
          🚗 คู่มือประชาชน & ผู้ใช้รถ
        </button>
      </div>

      {/* Tab 1: คาดการณ์สถานการณ์ */}
      {activeTab === 'forecast' && (
        <div className="mt-4 space-y-3.5 animate-in fade-in duration-200">
          <div className="rounded-xl bg-amber-50/70 border border-amber-200 p-3.5">
            <div className="flex items-center gap-2 mb-1.5">
              <span className="text-base">⚠️</span>
              <h4 className="text-xs font-bold text-amber-900 uppercase tracking-wide">
                สรุปภาพรวมการคาดการณ์ (Outlook Summary)
              </h4>
            </div>
            <p className="text-xs text-amber-800 leading-relaxed">
              กทม. และปริมณฑลอยู่ในสภาวะ <strong>&ldquo;เฝ้าระวังระดับน้ำสูงถึงวิกฤตบางจุด&rdquo;</strong> โดยพบสถานีล้นตลิ่งแล้ว{' '}
              <strong className="text-red-600">{overflowCount + canalOverflow} สถานี</strong> และใกล้ล้นตลิ่งอีก{' '}
              <strong>{highCount} สถานี</strong> โดยมีปัจจัยเร่งหลักจากน้ำทะเลหนุนสูงระลอกวันและอัตราการระบายของคลองตอนในที่ใกล้ขีดจำกัด
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {/* Zone 1 */}
            <div className="rounded-xl border border-red-200 bg-red-50/30 p-3.5 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between gap-1 mb-1.5">
                  <span className="text-xs font-bold text-red-900 flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-red-600" />
                    1. ชุมชนริมเจ้าพระยานอกคันกั้น
                  </span>
                  <Badge tone="red" className="text-[10px]">วิกฤตช่วงน้ำขึ้น</Badge>
                </div>
                <p className="text-[11px] text-slate-700 leading-relaxed mt-1">
                  <strong>พื้นที่เสี่ยง:</strong> 16 ชุมชนใน 7 เขต (ดุสิต, พระนคร, สัมพันธวงศ์, บางพลัด, บางกอกน้อย, คลองสาน, ยานนาวา)
                </p>
                <p className="text-[11px] text-slate-600 leading-relaxed mt-1">
                  <strong>คาดการณ์ 24-48 ชม.:</strong> เมื่อน้ำทะเลหนุนสูงสุด (ช่วงสายและค่ำ) ระดับน้ำจะเอ่อท้นตลิ่งเข้าท่วมทางเดินและบ้านเรือนริมน้ำ 10-30 ซม.
                </p>
              </div>
              <div className="mt-2.5 pt-2 border-t border-red-100 text-[10px] text-red-700 font-medium">
                ⚡ สอดคล้องข้อมูล: สามเสน (96%), สะพานกรุงเทพ (94%), ปตร.พระประแดง (104-110%)
              </div>
            </div>

            {/* Zone 2 */}
            <div className="rounded-xl border border-amber-200 bg-amber-50/30 p-3.5 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between gap-1 mb-1.5">
                  <span className="text-xs font-bold text-amber-900 flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-amber-500" />
                    2. พื้นที่ลุ่มคลองสายหลัก (ตอนเหนือ)
                  </span>
                  <Badge tone="yellow" className="text-[10px]">เสี่ยงน้ำรอระบาย</Badge>
                </div>
                <p className="text-[11px] text-slate-700 leading-relaxed mt-1">
                  <strong>พื้นที่เสี่ยง:</strong> สายไหม, บางเขน, จตุจักร, ดอนเมือง, หลักสี่, ลาดพร้าว
                </p>
                <p className="text-[11px] text-slate-600 leading-relaxed mt-1">
                  <strong>คาดการณ์ 24-48 ชม.:</strong> คลองลาดพร้าว (วัดบางบัว 105.6%) เต็มความจุ หากมีฝนตกเกิน 40-50 มม. จะเกิดน้ำท่วมขังบน ถ.งามวงศ์วาน, ถ.พหลโยธิน, ถ.วิภาวดีฯ ชั่วคราว
                </p>
              </div>
              <div className="mt-2.5 pt-2 border-t border-amber-100 text-[10px] text-amber-800 font-medium">
                ⚡ สอดคล้องข้อมูล: ค.ลาดพร้าว (105.6% ล้นตลิ่ง), ค.บางเขน (90%)
              </div>
            </div>

            {/* Zone 3 */}
            <div className="rounded-xl border border-blue-200 bg-blue-50/30 p-3.5 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between gap-1 mb-1.5">
                  <span className="text-xs font-bold text-blue-900 flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-blue-500" />
                    3. ฝั่งธนบุรี & ลุ่มน้ำท่าจีน
                  </span>
                  <Badge tone="blue" className="text-[10px]">เฝ้าระวังต่อเนื่อง</Badge>
                </div>
                <p className="text-[11px] text-slate-700 leading-relaxed mt-1">
                  <strong>พื้นที่เสี่ยง:</strong> ตลิ่งชัน, ทวีวัฒนา, บางกรวย, นครชัยศรี, สามพราน
                </p>
                <p className="text-[11px] text-slate-600 leading-relaxed mt-1">
                  <strong>คาดการณ์ 3-7 วัน:</strong> ลุ่มน้ำท่าจีน (นครชัยศรี 100.7%, สามพราน 100.3%) มีน้ำล้นตลิ่งต่อเนื่อง น้ำระบายช้าเนื่องจากระดับน้ำทะเลปากอ่าวหนุนดัน
                </p>
              </div>
              <div className="mt-2.5 pt-2 border-t border-blue-100 text-[10px] text-blue-800 font-medium">
                ⚡ สอดคล้องข้อมูล: ค.มหาสวัสดิ์ (95%), แม่น้ำท่าจีน (100.1-100.7%)
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: วิเคราะห์ความเสี่ยง 3 น้ำ */}
      {activeTab === 'diagnosis' && (
        <div className="mt-4 space-y-3 animate-in fade-in duration-200 text-xs">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="p-3.5 rounded-xl border border-slate-200 bg-slate-50">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xl">🏔️</span>
                <div>
                  <h4 className="font-bold text-slate-900">1. ปริมาณน้ำเหนือ (Upstream)</h4>
                  <span className="text-[11px] text-slate-500">เขื่อนเจ้าพระยา & ลุ่มน้ำป่าสัก</span>
                </div>
              </div>
              <ul className="list-disc list-inside space-y-1 text-slate-600 text-[11px] leading-relaxed">
                <li>การระบายน้ำจากท้ายเขื่อนเจ้าพระยาและแม่น้ำป่าสักไหลผ่านอยุธยาเข้าสู่สะพานนวลฉวี (นนทบุรี) อยู่ในเกณฑ์ 93.0%</li>
                <li>ระดับน้ำสะพานนวลฉวีสูง +1.70 ถึง +1.95 ม. รทก. ทำให้หัวน้ำดันเข้าสู่แม่น้ำเจ้าพระยาตอนล่างต่อเนื่อง</li>
                <li><strong>ผลกระทบ:</strong> แม่น้ำเจ้าพระยาช่วงผ่าน กทม. มีมวลน้ำรองรับอยู่เกือบเต็มลำน้ำ</li>
              </ul>
            </div>

            <div className="p-3.5 rounded-xl border border-slate-200 bg-slate-50">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xl">🌊</span>
                <div>
                  <h4 className="font-bold text-slate-900">2. น้ำทะเลหนุนสูง (Tidal Surge)</h4>
                  <span className="text-[11px] text-slate-500">ปากอ่าวไทย & พระประแดง</span>
                </div>
              </div>
              <ul className="list-disc list-inside space-y-1 text-slate-600 text-[11px] leading-relaxed">
                <li>สถานีโทรมาตรปากคลองลัดบางยอและวัดบางกระเจ้านอก (พระประแดง) ระดับน้ำสูงถึง 104-110%</li>
                <li>ระดับน้ำทะเลหนุนสูงสุดวัดได้ +1.20 ถึง +1.50 ม. รทก. ต้านการไหลออกสู่อ่าวไทย</li>
                <li><strong>ผลกระทบ:</strong> ส่งผลให้ประตูระบายน้ำฝั่งเจ้าพระยาต้องปิดเป็นช่วงๆ และน้ำเอ่อท้นจุดฟันหลอ</li>
              </ul>
            </div>

            <div className="p-3.5 rounded-xl border border-slate-200 bg-slate-50">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xl">🌧️</span>
                <div>
                  <h4 className="font-bold text-slate-900">3. น้ำฝนและน้ำในพื้นที่ (Local Rain)</h4>
                  <span className="text-[11px] text-slate-500">ระบบคูคลองและท่อระบายน้ำ กทม.</span>
                </div>
              </div>
              <ul className="list-disc list-inside space-y-1 text-slate-600 text-[11px] leading-relaxed">
                <li>คลองลาดพร้าวมีระดับน้ำ 105.6% ล้นสันเขื่อนวัดบางบัว ทำให้ความสามารถรับน้ำฝนเป็น 0%</li>
                <li>คลองหลอด 3 ถนนบางนา-ตราด ความจุสูงถึง 310% เป็นจุดคอขวดระบายน้ำของเขตบางนา</li>
                <li><strong>ผลกระทบ:</strong> หากเกิดฝนตกเกิน 40 มม./ชม. น้ำจะขังบนผิวถนนทันทีเพราะคลองรับน้ำไม่ทัน</li>
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* Tab 3: แนวทางแก้ไข & มาตรการภาครัฐ */}
      {activeTab === 'action' && (
        <div className="mt-4 space-y-3.5 animate-in fade-in duration-200 text-xs">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {/* Immediate */}
            <div className="rounded-xl border border-cyan-200 bg-cyan-50/30 p-3.5">
              <div className="flex items-center gap-1.5 font-bold text-cyan-900 mb-2">
                <span>⚡</span>
                <h4>มาตรการเร่งด่วน (0 - 24 ชม.)</h4>
              </div>
              <ul className="space-y-1.5 text-slate-700 text-[11px] leading-relaxed">
                <li className="flex items-start gap-1.5">
                  <span className="text-cyan-600 shrink-0 font-bold">•</span>
                  <span><strong>พร่องน้ำล่วงหน้า (Pre-drainage):</strong> เร่งเดินเครื่องสูบน้ำสถานีสูบน้ำพระโขนง บางซื่อ และคลองเตย ช่วงน้ำทะเลลงต่ำสุด</span>
                </li>
                <li className="flex items-start gap-1.5">
                  <span className="text-cyan-600 shrink-0 font-bold">•</span>
                  <span><strong>เปิดประตูระบายน้ำคลองลัดโพธิ์:</strong> เร่งระบายน้ำเลี่ยงโค้งเจ้าพระยาจาก 18 กม. เหลือ 600 ม. ตอนน้ำลง</span>
                </li>
                <li className="flex items-start gap-1.5">
                  <span className="text-cyan-600 shrink-0 font-bold">•</span>
                  <span><strong>อุดแนวฟันหลอ (Sandbags):</strong> วางแนวกระสอบทรายเสริมความสูง +2.80 ม. รทก. ใน 16 ชุมชนนอกคันกั้นน้ำ</span>
                </li>
                <li className="flex items-start gap-1.5">
                  <span className="text-cyan-600 shrink-0 font-bold">•</span>
                  <span><strong>หน่วยเคลื่อนที่เร็ว (BEST):</strong> ประจำจุดเฝ้าระวังและเก็บขยะหน้าตะแกรงท่อระบายน้ำ 24 ชม.</span>
                </li>
              </ul>
            </div>

            {/* Medium-term */}
            <div className="rounded-xl border border-indigo-200 bg-indigo-50/30 p-3.5">
              <div className="flex items-center gap-1.5 font-bold text-indigo-900 mb-2">
                <span>🔧</span>
                <h4>มาตรการระยะกลาง (1 - 3 เดือน)</h4>
              </div>
              <ul className="space-y-1.5 text-slate-700 text-[11px] leading-relaxed">
                <li className="flex items-start gap-1.5">
                  <span className="text-indigo-600 shrink-0 font-bold">•</span>
                  <span><strong>แก้มลิงหน่วงน้ำ (Retention Basins):</strong> ผันน้ำส่วนเกินเข้าบึงมักกะสัน บึงหนองบอน และแก้มลิงใต้ดินรัชวิภา</span>
                </li>
                <li className="flex items-start gap-1.5">
                  <span className="text-indigo-600 shrink-0 font-bold">•</span>
                  <span><strong>เดินเครื่องอุโมงค์ระบายน้ำยักษ์:</strong> ใช้อุโมงค์บางซื่อและอุโมงค์พระราม 9 ดึงน้ำจากคลองลาดพร้าวลงสู่เจ้าพระยา</span>
                </li>
                <li className="flex items-start gap-1.5">
                  <span className="text-indigo-600 shrink-0 font-bold">•</span>
                  <span><strong>ระบบ CCTV AI ตรวจระดับน้ำ:</strong> นำกล้อง กทม. ติดอัลกอริทึมวัดระดับน้ำและตรวจจับน้ำท่วมผิวจราจรอัตโนมัติ</span>
                </li>
              </ul>
            </div>

            {/* Long-term */}
            <div className="rounded-xl border border-emerald-200 bg-emerald-50/30 p-3.5">
              <div className="flex items-center gap-1.5 font-bold text-emerald-900 mb-2">
                <span>🏗️</span>
                <h4>มาตรการโครงสร้างระยะยาว</h4>
              </div>
              <ul className="space-y-1.5 text-slate-700 text-[11px] leading-relaxed">
                <li className="flex items-start gap-1.5">
                  <span className="text-emerald-600 shrink-0 font-bold">•</span>
                  <span><strong>คันกั้นน้ำถาวร (Permanent Floodwall):</strong> ยกระดับคันกั้นน้ำริมเจ้าพระยาทั้ง 88 กม. ให้สูงกว่า +3.00 ถึง +3.50 ม. รทก.</span>
                </li>
                <li className="flex items-start gap-1.5">
                  <span className="text-emerald-600 shrink-0 font-bold">•</span>
                  <span><strong>Pipe Jacking ขยายท่อระบายน้ำ:</strong> ดันท่อระบายน้ำใต้ดินขนาดใหญ่ในถนนสายหลักที่มักท่วมซ้ำซาก</span>
                </li>
                <li className="flex items-start gap-1.5">
                  <span className="text-emerald-600 shrink-0 font-bold">•</span>
                  <span><strong>คลองผันน้ำเลี่ยงเมืองเจ้าพระยา:</strong> เพิ่มช่องทางระบายน้ำตัดตรงลงสู่อ่าวไทยเพื่อลดภาระแม่น้ำเจ้าพระยา</span>
                </li>
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* Tab 4: คู่มือประชาชน & ผู้ใช้รถ */}
      {activeTab === 'public' && (
        <div className="mt-4 space-y-3.5 animate-in fade-in duration-200 text-xs">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
            <div className="p-4 rounded-xl border border-slate-200 bg-slate-50">
              <h4 className="font-bold text-slate-900 mb-2 flex items-center gap-1.5">
                <span>🚗</span> คำแนะนำสำหรับผู้ขับขี่และสัญจรบนถนน
              </h4>
              <ul className="space-y-1.5 text-slate-700 text-[11px] leading-relaxed">
                <li><strong>เช็คกล้อง CCTV สดก่อนเดินทาง:</strong> เปิดดูสภาพผิวจราจรผ่านระบบ CCTV BKK ในจุดเสี่ยง เช่น งามวงศ์วาน, วิภาวดีฯ, รัชดาภิเษก, บางนา-ตราด</li>
                <li><strong>สังเกตระดับน้ำก่อนลุย:</strong> หากระดับน้ำท่วมเกินครึ่งล้อรถยนต์ (&gt; 25 ซม.) ไม่ควรขับลุย เพราะอาจดูดน้ำเข้าท่อไอดีหรือคลัตช์เสียหาย</li>
                <li><strong>เทคนิคขับลุยน้ำขัง:</strong> ใช้เกียร์ต่ำ (เกียร์ L หรือ D1-D2) ปิดเครื่องปรับอากาศ และรักษารอบเครื่องยนต์คงที่ ไม่เบิ้ลเครื่องหรือเหยียบเบรกแรง</li>
                <li><strong>หลังลุยน้ำ:</strong> เหยียบเบรกเบาๆ ซ้ำๆ หลายครั้งเพื่อไล่น้ำออกจากผ้าเบรก และตรวจเช็คน้ำมันเกียร์หากลุยน้ำลึก</li>
              </ul>
            </div>

            <div className="p-4 rounded-xl border border-slate-200 bg-slate-50">
              <h4 className="font-bold text-slate-900 mb-2 flex items-center gap-1.5">
                <span>🏠</span> คำแนะนำสำหรับผู้อยู่อาศัยริมน้ำและพื้นที่ลุ่มต่ำ
              </h4>
              <ul className="space-y-1.5 text-slate-700 text-[11px] leading-relaxed">
                <li><strong>ยกของมีค่าขึ้นที่สูง:</strong> ชุมชนริมแม่น้ำเจ้าพระยาและคลองบางเขน/ลาดพร้าว ควรยกเครื่องใช้ไฟฟ้าและเฟอร์นิเจอร์ขึ้นชั้นสอง</li>
                <li><strong>ตรวจสอบปลั๊กไฟและสายดิน:</strong> ปลดเบรกเกอร์วงจรไฟฟ้าชั้นล่างที่เสี่ยงถูกน้ำท่วมเพื่อป้องกันกระแสไฟฟ้ารั่ว</li>
                <li><strong>เตรียมแนวกระสอบทราย:</strong> วางกระสอบทรายปิดช่องทางน้ำเข้า และติดตั้งเครื่องสูบน้ำขนาดเล็ก (ไดโว่) ประจำจุดซึม</li>
                <li><strong>ติดตามเวลาน้ำขึ้น-น้ำลง:</strong> เช็คตารางน้ำทะเลหนุนในระบบเพื่อเตรียมปิดแผ่นกั้นน้ำก่อนเวลาหนุนสูงสุด 1 ชม.</li>
              </ul>
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}
