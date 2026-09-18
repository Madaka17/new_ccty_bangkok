import { useState, useMemo } from 'react';
import { Card, Badge, Button } from './ui.jsx';

// คลังข้อมูลทางกายภาพ คอขวด และกลยุทธ์การระบายรถรายสายทางหลัก
const CORRIDOR_PROFILES = [
  {
    id: 'sukhumvit',
    name: 'ถนนสุขุมวิท / อโศก / ทองหล่อ',
    searchRoad: 'ถนนสุขุมวิท',
    matchKeys: ['สุขุมวิท', 'อโศก', 'ทองหล่อ', 'เอกมัย'],
    zone: 'กรุงเทพฯ ชั้นใน / ตะวันออก (CBD)',
    bottleneck: 'แยกอโศกมนตรี, แยกทองหล่อ, แยกเอกมัย, แยกพระโขนง',
    dispersalAction: 'ผันรถออก ถ.เพชรบุรีตัดใหม่ หรือ ถ.พระราม 4 / แนะนำใช้ซอยลัดสุขุมวิท 22, 24, 39, 55, 71 เพื่อเชื่อมข้ามสายทาง',
    signalAdvice: 'เปิดไฟเขียวแนวแกนหลักต่อเนื่อง (Green Wave) ช่วงเร่งด่วน',
    preferredBypass: 'ทางพิเศษศรีรัช หรือ ทางพิเศษเฉลิมมหานคร',
  },
  {
    id: 'rama4',
    name: 'ถนนพระราม 4',
    searchRoad: 'ถนนพระราม 4',
    matchKeys: ['พระราม 4', 'พระราม4', 'คลองเตย', 'สามย่าน'],
    zone: 'กรุงเทพฯ ชั้นใน (CBD ใต้)',
    bottleneck: 'แยกคลองเตย, ใต้ด่วนพระราม 4, แยกวิทยุ, สามย่าน',
    dispersalAction: 'มุ่งหน้าสาทรให้กระจายรถเข้า ถ.พระราม 3 หรือทางเลียบทางรถไฟสายเก่า / มุ่งหน้าหัวลำโพงให้เลี่ยงเข้า ถ.สี่พระยา หรือ ถ.สุรวงศ์',
    signalAdvice: 'ซิงค์ไฟเขียวแยกคลองเตยไม่ให้รับรถจากทางลงด่วนจนล้นข้ามแยก',
    preferredBypass: 'ถนนพระราม 3 หรือ ทางเลียบทางรถไฟสายเก่า',
  },
  {
    id: 'phetchaburi',
    name: 'ถนนเพชรบุรี / พระราม 9 / รามคำแหง',
    searchRoad: 'ถนนเพชรบุรี',
    matchKeys: ['เพชรบุรี', 'พระราม 9', 'พระราม9', 'รามคำแหง'],
    zone: 'กรุงเทพฯ ตะวันออก',
    bottleneck: 'แยกอโศก-เพชรบุรี, แยกคลองตัน, แยกรามคำแหงตัดพระราม 9',
    dispersalAction: 'ออกเมืองไปมอเตอร์เวย์ (ทล.7) ให้ขึ้นทางพิเศษศรีรัช หรือเลี่ยงเข้า ถ.พัฒนาการ ทะลุออกศรีนครินทร์',
    signalAdvice: 'กวดขันจุดกลับรถหน้าศูนย์วิจัยและซอยทองหล่อเหนือเพื่อไม่ให้ปาดหน้ารถทางตรง',
    preferredBypass: 'ทางพิเศษศรีรัช หรือ ถนนพัฒนาการ',
  },
  {
    id: 'vibhavadi',
    name: 'ถนนวิภาวดีรังสิต',
    searchRoad: 'ถนนวิภาวดีรังสิต',
    matchKeys: ['วิภาวดี', 'ดอนเมือง', 'โทลล์เวย์'],
    zone: 'กรุงเทพฯ เหนือ (ออกเมือง)',
    bottleneck: 'จุดเบี่ยงขึ้นโทลล์เวย์ลาดพร้าว, หน้าสนามบินดอนเมือง, แยกหลักสี่',
    dispersalAction: 'ผลักดันรถเข้าช่องด่วน (Main Road) ให้เต็มเลน / หากหน้าดอนเมืองชะลอ ให้กระจายออก ถ.กำแพงเพชร 6 (Local Road) หรือขึ้นโทลล์เวย์ตั้งแต่บางเขน',
    signalAdvice: 'ห้ามรถรับ-ส่งจอดแช่เลนซ้ายหน้าสนามบินเด็ดขาด / ปล่อยไฟเขียวแยกหลักสี่ขาออก',
    preferredBypass: 'ทางยกระดับอุตราภิมุข (โทลล์เวย์) หรือ ถ.กำแพงเพชร 6',
  },
  {
    id: 'phahonyothin',
    name: 'ถนนพหลโยธิน',
    searchRoad: 'ถนนพหลโยธิน',
    matchKeys: ['พหลโยธิน', 'รัชโยธิน', 'เกษตร'],
    zone: 'กรุงเทพฯ เหนือ',
    bottleneck: 'แยกรัชโยธิน, วงเวียนบางเขน, แยกสะพานควาย',
    dispersalAction: 'ออกเมืองไปรังสิต แนะนำตัดเข้า ถ.วิภาวดีรังสิต หรือ ถ.สุขาภิบาล 5 / รามอินทรา ขึ้นทางด่วนฉลองรัช / ช่วงรัชโยธินให้ใช้สะพานข้ามแยก',
    signalAdvice: 'เพิ่มเวลาสัญญาณไฟเขียวแยกเกษตรขาออกเมืองช่วงชั่วโมงเร่งด่วนเย็น',
    preferredBypass: 'ถนนวิภาวดีรังสิต หรือ ทางพิเศษฉลองรัช',
  },
  {
    id: 'ngamwongwan',
    name: 'ถนนงามวงศ์วาน / รัตนาธิเบศร์',
    searchRoad: 'ถนนงามวงศ์วาน',
    matchKeys: ['งามวงศ์วาน', 'พงษ์เพชร', 'แคราย', 'รัตนาธิเบศร์'],
    zone: 'นนทบุรี - กรุงเทพฯ เหนือ',
    bottleneck: 'เชิงสะพานข้ามแยกพงษ์เพชร, หน้าเดอะมอลล์งามวงศ์วาน, แยกแคราย',
    dispersalAction: 'หากสะพานข้ามแยกพงษ์เพชรติดขัด ให้เลี่ยงเข้า ถ.รัตนาธิเบศร์ หรือ ถ.ติวานนท์ ขึ้นด่านงามวงศ์วานทางด่วนศรีรัช',
    signalAdvice: 'เร่งเคลียร์จุดเฉี่ยวชน/รถเสียบนสะพานพงษ์เพชรทันทีเพื่อลดท้ายแถวล้นถึงเกษตร',
    preferredBypass: 'ถนนรัตนาธิเบศร์ หรือ ทางพิเศษศรีรัช',
  },
  {
    id: 'sathorn_silom',
    name: 'ถนนสาทร / ถนนสีลม (ข้ามแม่น้ำ)',
    searchRoad: 'ถนนสาทร',
    matchKeys: ['สาทร', 'สีลม', 'ตากสิน', 'สุรศักดิ์'],
    zone: 'กรุงเทพฯ กลาง - ข้ามแม่น้ำเจ้าพระยา',
    bottleneck: 'เชิงสะพานสมเด็จพระเจ้าตากสิน, แยกสาทร-นราธิวาส, แยกวิทยุ',
    dispersalAction: 'ข้ามไปฝั่งธนบุรีหากสะพานตากสินหนาแน่น ให้ผันรถไปใช้สะพานพระราม 3 หรือสะพานพุทธ-พระปกเกล้า ผ่านเจริญกรุง',
    signalAdvice: 'เปิด Reversible Lane (ช่องทางพิเศษ) ข้ามสะพานตากสินช่วงเร่งด่วนเย็น',
    preferredBypass: 'สะพานพระราม 3 หรือ สะพานพระปกเกล้า',
  },
  {
    id: 'borom',
    name: 'ถนนบรมราชชนนี / ปิ่นเกล้า',
    searchRoad: 'ถนนบรมราชชนนี',
    matchKeys: ['บรมราชชนนี', 'ปิ่นเกล้า', 'อรุณอมรินทร์', 'คู่ขนานลอยฟ้า'],
    zone: 'กรุงเทพฯ ตะวันตก - ฝั่งธนบุรี',
    bottleneck: 'เชิงสะพานสมเด็จพระปิ่นเกล้า, สะพานพระราม 8, แยกอรุณอมรินทร์',
    dispersalAction: 'ดันรถทางไกลขึ้นทางคู่ขนานลอยฟ้าบรมราชชนนี / รถระยะใกล้เลี่ยงไปใช้ ถ.พรานนก-กาญจนาภิเษก หรือ ถ.จรัญสนิทวงศ์',
    signalAdvice: 'สลับไฟแยกศิริราชและอรุณอมรินทร์ไม่ให้หางแถวล้นขึ้นสะพานข้ามแม่น้ำ',
    preferredBypass: 'ทางคู่ขนานลอยฟ้าบรมราชชนนี หรือ ถ.พรานนก-พุทธมณฑลสาย 4',
  },
  {
    id: 'rama2',
    name: 'ถนนพระราม 2 (ทล.35)',
    searchRoad: 'ถนนพระราม 2',
    matchKeys: ['พระราม 2', 'พระราม2', 'บางขุนเทียน', 'แสมดำ', 'มหาชัย'],
    zone: 'กรุงเทพฯ ใต้ - สมุทรสาคร',
    bottleneck: 'เขตก่อสร้างทางยกระดับ, ต่างระดับบางขุนเทียน, หน้าเซ็นทรัลมหาชัย',
    dispersalAction: 'ออกเมืองเลี่ยงไปใช้ ถ.กัลปพฤกษ์-ราชพฤกษ์ หรือ ถ.เพชรเกษม ออกนครปฐมเข้าราชบุรี / หรือ ถ.เอกชัย',
    signalAdvice: 'ควบคุมเปิด-ปิดช่องจราจรเขตก่อสร้างให้มีป้ายเตือนล่วงหน้า 1-2 กม.',
    preferredBypass: 'ถนนกัลปพฤกษ์ - ราชพฤกษ์ หรือ ถนนเอกชัย',
  },
  {
    id: 'suksawat_taksin',
    name: 'ถนนสุขสวัสดิ์ / สมเด็จพระเจ้าตากสิน',
    searchRoad: 'ถนนสุขสวัสดิ์',
    matchKeys: ['สุขสวัสดิ์', 'สมเด็จพระเจ้าตากสิน', 'ดาวคะนอง', 'มไหสวรรย์'],
    zone: 'ฝั่งธนบุรีใต้',
    bottleneck: 'แยกมไหสวรรย์, แยกดาวคะนอง, แยกพระประแดง',
    dispersalAction: 'ผันรถเข้า ถ.ราษฎร์บูรณะ หรือขึ้นสะพานภูมิพล 1, 2 ข้ามไปบางนา-สำโรงโดยตรงเพื่อหลีกเลี่ยงแยกดาวคะนอง',
    signalAdvice: 'เร่งปล่อยสัญญาณไฟแยกดาวคะนองไม่ให้ท้ายแถวย้อนไปชนทางลงด่วนพระราม 9',
    preferredBypass: 'สะพานภูมิพล 1, 2 หรือ ถนนราษฎร์บูรณะ',
  },
  {
    id: 'latphrao',
    name: 'ถนนลาดพร้าว / เกษตร-นวมินทร์',
    searchRoad: 'ถนนลาดพร้าว',
    matchKeys: ['ลาดพร้าว', 'โชคชัย 4', 'บางกะปิ', 'ประเสริฐมนูกิจ'],
    zone: 'กรุงเทพฯ ตะวันออกเฉียงเหนือ',
    bottleneck: 'แยกลาดพร้าว, แยกโชคชัย 4, เดอะมอลล์บางกะปิ',
    dispersalAction: 'เลี่ยงเข้า ถ.ประเสริฐมนูกิจ (เกษตร-นวมินทร์) หรือ ถ.ประดิษฐ์มนูธรรม (เลียบด่วน) ขึ้นทางด่วนฉลองรัช',
    signalAdvice: 'ประสานระบบสัญญาณไฟหน้าสถานีรถไฟฟ้าสายสีเหลืองเพื่อลดจุดชะลอตัว',
    preferredBypass: 'ถนนประเสริฐมนูกิจ (เกษตร-นวมินทร์) หรือ ทางพิเศษฉลองรัช',
  },
  {
    id: 'ratchaphruek',
    name: 'ถนนราชพฤกษ์ / กัลปพฤกษ์',
    searchRoad: 'ถนนราชพฤกษ์',
    matchKeys: ['ราชพฤกษ์', 'กัลปพฤกษ์', 'กาญจนาภิเษก'],
    zone: 'ฝั่งธนบุรี - นนทบุรี',
    bottleneck: 'จุดตัด ถ.บรมราชชนนี, วงเวียนพระราม 5, แยกสาทร-ราชพฤกษ์',
    dispersalAction: 'วิ่งตรงเชื่อมต่อสายทางได้คล่องตัว / หากจุดตัดบรมฯ ชะลอ ให้ใช้ทางขนานวงแหวนกาญจนาภิเษก',
    signalAdvice: 'รักษาความต่อเนื่องของสะพานข้ามแยกทุกจุดตลอดแนวถนนราชพฤกษ์',
    preferredBypass: 'ถนนกาญจนาภิเษก (วงแหวนรอบนอก)',
  },
];

export default function TrafficGuidanceCard({ summary, trafficSummary, incidents, onOpenRoad, onNavigate, onAsk }) {
  const [filter, setFilter] = useState('all');

  // รวมรายการถนนและสภาพจริงจาก Real-time Map Feed
  const analyzedCorridors = useMemo(() => {
    const congestedList = [
      ...(summary?.congested || []),
      ...(trafficSummary?.congested || []),
    ];
    const freeList = [
      ...(summary?.free_flow || []),
      ...(trafficSummary?.free_flow || []),
    ];
    const incidentList = [
      ...(incidents?.camera || []),
      ...(incidents?.longdo || []),
    ];

    return CORRIDOR_PROFILES.map((p) => {
      // 1. ค้นหาว่ามีอุบัติเหตุหรือรถเสียในเส้นนี้หรือไม่
      const activeIncidents = incidentList.filter((i) => {
        const text = `${i.title || ''} ${i.description || ''}`.toLowerCase();
        return p.matchKeys.some((k) => text.includes(k.toLowerCase()));
      });

      // 2. ค้นหาข้อมูลสภาพจราจรแบบเรียลไทม์
      const matchCongested = congestedList.find((c) => {
        const name = (c.name || c.road || '').toLowerCase();
        return p.matchKeys.some((k) => name.includes(k.toLowerCase()));
      });

      const matchFree = freeList.find((c) => {
        const name = (c.name || c.road || '').toLowerCase();
        return p.matchKeys.some((k) => name.includes(k.toLowerCase()));
      });

      let status = 'normal';
      let statusLabel = 'ปานกลาง / ปกติ';
      let tone = 'neutral';
      let liveMetric = null;
      let priority = 3;

      if (activeIncidents.length > 0) {
        status = 'incident';
        statusLabel = `มีเหตุขัดขวาง (${activeIncidents[0].kind === 'breakdown' ? 'รถเสีย' : 'อุบัติเหตุ'})`;
        tone = 'red';
        liveMetric = activeIncidents[0].title;
        priority = 1;
      } else if (matchCongested) {
        status = 'congested';
        tone = matchCongested.flow < 40 ? 'red' : 'yellow';
        statusLabel = matchCongested.flow < 40 ? 'ติดขัดสะสม' : 'ชะลอตัว';
        const redKm = matchCongested.red_km ? `แดง ${matchCongested.red_km} กม.` : '';
        const flow = matchCongested.flow != null ? `ระบายได้ ${matchCongested.flow}/100` : '';
        const vehicles = matchCongested.total ? `รถ ${matchCongested.total} คัน` : '';
        liveMetric = [redKm, flow, vehicles].filter(Boolean).join(' · ');
        priority = matchCongested.flow < 40 ? 1 : 2;
      } else if (matchFree) {
        status = 'free';
        statusLabel = 'คล่องตัว (แนะนำเลี่ยงมาใช้)';
        tone = 'green';
        liveMetric = `ระบายได้ ${matchFree.flow || 90}/100 · วิ่งสบาย`;
        priority = 4;
      }

      return {
        ...p,
        status,
        statusLabel,
        tone,
        liveMetric,
        priority,
        activeIncidents,
      };
    }).sort((a, b) => a.priority - b.priority);
  }, [summary, trafficSummary, incidents]);

  const filtered = useMemo(() => {
    if (filter === 'congested') {
      return analyzedCorridors.filter((c) => c.status === 'congested' || c.status === 'incident');
    }
    if (filter === 'free') {
      return analyzedCorridors.filter((c) => c.status === 'free');
    }
    if (filter === 'incidents') {
      return analyzedCorridors.filter((c) => c.status === 'incident');
    }
    return analyzedCorridors;
  }, [analyzedCorridors, filter]);

  const countCongested = analyzedCorridors.filter((c) => c.status === 'congested' || c.status === 'incident').length;
  const countFree = analyzedCorridors.filter((c) => c.status === 'free').length;
  const countIncidents = analyzedCorridors.filter((c) => c.status === 'incident').length;

  return (
    <Card className="p-4 sm:p-5 flex flex-col gap-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-3 border-b border-cream-200">
        <div>
          <h2 className="text-base font-semibold text-ink-900 leading-6">
            คำแนะนำการระบายรถตามสภาพแผนที่สด
          </h2>
          <p className="text-xs text-ink-600 mt-1">
            วิเคราะห์จุดคอขวด เส้นทางเลี่ยง และการระบายรถจากสภาพเส้นสีแผนที่จริงและกล้อง CCTV อัตโนมัติ
          </p>
        </div>

        {/* Filter Chips */}
        <div className="flex flex-wrap items-center gap-1.5 self-start sm:self-auto">
          <button
            type="button"
            onClick={() => setFilter('all')}
            className={`cursor-pointer px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
              filter === 'all'
                ? 'bg-ink-900 text-white dark:bg-slate-100 dark:text-slate-900'
                : 'bg-cream-100 text-ink-600 hover:text-ink-900'
            }`}
          >
            ทั้งหมด ({analyzedCorridors.length})
          </button>
          <button
            type="button"
            onClick={() => setFilter('congested')}
            className={`cursor-pointer px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
              filter === 'congested'
                ? 'bg-red-600 text-white'
                : 'bg-cream-100 text-ink-600 hover:text-red-700'
            }`}
          >
            🔴 ต้องเร่งระบาย ({countCongested})
          </button>
          <button
            type="button"
            onClick={() => setFilter('free')}
            className={`cursor-pointer px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
              filter === 'free'
                ? 'bg-emerald-600 text-white'
                : 'bg-cream-100 text-ink-600 hover:text-emerald-700'
            }`}
          >
            🟢 ทางเลี่ยงแนะนำ ({countFree})
          </button>
          {countIncidents > 0 && (
            <button
              type="button"
              onClick={() => setFilter('incidents')}
              className={`cursor-pointer px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
                filter === 'incidents'
                  ? 'bg-amber-600 text-white'
                  : 'bg-cream-100 text-ink-600 hover:text-amber-700'
              }`}
            >
              ⚠️ มีเหตุบนถนน ({countIncidents})
            </button>
          )}
        </div>
      </div>

      {/* Grid of Corridors */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
        {filtered.map((c) => (
          <div
            key={c.id}
            className="rounded-xl border border-cream-200 bg-cream-100/40 p-3.5 flex flex-col justify-between gap-3 hover:border-slate-300 dark:hover:border-slate-600 transition-colors"
          >
            <div className="flex flex-col gap-2">
              {/* Header: Name + Badge */}
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <h3 className="text-sm font-semibold text-ink-900 leading-snug">
                    {c.name}
                  </h3>
                  <span className="text-[11px] text-ink-600">{c.zone}</span>
                </div>
                <div className="flex flex-col items-end gap-1 shrink-0">
                  <Badge tone={c.tone} dot={c.status === 'incident' || c.status === 'congested'}>
                    {c.statusLabel}
                  </Badge>
                  {c.liveMetric && (
                    <span className="text-[10px] text-ink-600 font-mono text-right">
                      {c.liveMetric}
                    </span>
                  )}
                </div>
              </div>

              {/* อุบัติเหตุถ้ามี */}
              {c.activeIncidents?.length > 0 && (
                <div className="rounded-lg bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900/50 p-2 text-xs text-red-800 dark:text-red-300 flex items-start gap-1.5">
                  <span className="shrink-0 mt-0.5">⚠️</span>
                  <div>
                    <span className="font-semibold">เหตุการณ์สด: </span>
                    <span>{c.activeIncidents[0].title}</span>
                    {c.activeIncidents[0].description && (
                      <p className="text-[11px] opacity-90 mt-0.5">{c.activeIncidents[0].description}</p>
                    )}
                  </div>
                </div>
              )}

              {/* Bottlenecks */}
              <div className="text-xs flex items-start gap-2 pt-1">
                <span className="font-medium text-ink-900 shrink-0">📍 คอขวด:</span>
                <span className="text-ink-600 leading-relaxed">{c.bottleneck}</span>
              </div>

              {/* Action / Dispersal Tactic */}
              <div className="text-xs rounded-lg bg-white border border-cream-200 p-2.5 flex flex-col gap-1.5">
                <div className="flex items-start gap-1.5">
                  <span className="text-blue-600 font-bold shrink-0">↪️ วิธีระบายรถ:</span>
                  <span className="text-ink-900 font-medium leading-relaxed">
                    {c.dispersalAction}
                  </span>
                </div>
                <div className="flex items-start gap-1.5 text-[11px] text-ink-600 pt-1 border-t border-cream-200">
                  <span className="font-semibold shrink-0">🚥 สัญญาณไฟ/มาตรการ:</span>
                  <span>{c.signalAdvice}</span>
                </div>
              </div>
            </div>

            {/* Bottom Actions */}
            <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-cream-200">
              <span className="text-[11px] text-ink-600">
                ทางเลี่ยงหลัก: <span className="font-medium text-ink-900">{c.preferredBypass}</span>
              </span>
              <div className="flex items-center gap-1.5">
                {onOpenRoad && (
                  <Button
                    size="sm"
                    onClick={() => onOpenRoad(c.searchRoad)}
                    title={`เปิดดูกล้อง CCTV บน ${c.searchRoad}`}
                  >
                    เปิดดูกล้อง
                  </Button>
                )}
                {onAsk && (
                  <Button
                    size="sm"
                    variant="primary"
                    onClick={() =>
                      onAsk(
                        `ขอแนวทางการระบายรถและเส้นทางเลี่ยงสำหรับ ${c.name} ในช่วงนี้อย่างละเอียด`
                      )
                    }
                    title="ถาม AI เจาะลึกเส้นทางนี้"
                  >
                    ถาม AI
                  </Button>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
