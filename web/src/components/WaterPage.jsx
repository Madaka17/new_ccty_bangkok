import { useState } from 'react';
import { trackView } from '../lib/telemetry.js';
import { PageHeader } from './dashboard/primitives.jsx';
import { PAGE_TITLES } from './Sidebar.jsx';
import ViewSwitch from './ViewSwitch.jsx';
import BkkDistrictSection from './water/BkkDistrictSection.jsx';
import CitizenReportsSection from './water/CitizenReportsSection.jsx';
import ShelterSection from './water/ShelterSection.jsx';
import NorthFlowSection from './water/NorthFlowSection.jsx';
import NationalWaterSection from './water/NationalWaterSection.jsx';
import FloodForecastSection from './water/FloodForecastSection.jsx';
import NationalRoadsSection from './water/NationalRoadsSection.jsx';
import FloodSummarySection from './water/FloodSummarySection.jsx';

const TABS = [
  { id: 'situation', label: 'ระดับน้ำทั่วประเทศ', hint: 'น้ำในเขื่อนทุกภาค และคาดการณ์ 7 วันข้างหน้า', icon: 'water' },
  { id: 'provinces', label: 'คาดการณ์น้ำท่วม', hint: 'จังหวัดที่น้ำท่วม คาดการณ์ 7 วัน และคนแจ้งน้ำท่วมทั่วประเทศ', icon: 'map' },
  { id: 'roads', label: 'ถนนน้ำท่วม', hint: 'ถนนที่น้ำท่วมทั่วประเทศ และถนนที่อาจท่วมใน 7 วัน', icon: 'map' },
  { id: 'summary', label: 'สรุปสถานการณ์', hint: 'สรุปน้ำท่วมและน้ำในเขื่อนทั้งหมด พร้อมสิ่งที่ควรทำ', icon: 'analytics' },
  { id: 'north', label: 'เส้นทางน้ำเหนือ', hint: 'น้ำจากภาคเหนือไหลผ่านจังหวัดไหน ต้องระวังที่ไหน และ 7 วันข้างหน้า', icon: 'water' },
  { id: 'watch', label: 'เขตเสี่ยงน้ำท่วมในกรุงเทพมหานคร', hint: 'สรุปทั้ง 50 เขต น้ำในคลอง แม่น้ำ ถนน และฝน', icon: 'alerts' },
  { id: 'shelter', label: 'จุดพักพิงใกล้ฉัน', hint: 'จุดพักพิงชั่วคราวของ กทม. ใกล้คุณ พร้อมเบอร์โทรและเส้นทาง', icon: 'map' },
  { id: 'reports', label: 'เรื่องที่คนแจ้ง', hint: 'เรื่องน้ำท่วมที่คนแจ้งผ่าน Traffy Fondue และข่าวจราจร', icon: 'visitors' },
];

export default function WaterPage({ isActive }) {
  const [tab, setTab] = useState('situation');
  const pickTab = (id) => {
    setTab(id);
    trackView(`water:${id}`);
  };

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={PAGE_TITLES.water} description="น้ำท่วม น้ำในเขื่อน และคาดการณ์ 7 วัน ทั่วประเทศ" />

      <ViewSwitch tabs={TABS} value={tab} onChange={pickTab} label="หัวข้อน้ำท่วม" />

      {tab === 'situation' && <NationalWaterSection isActive={isActive} />}

      {tab === 'provinces' && <FloodForecastSection isActive={isActive} />}

      {tab === 'roads' && <NationalRoadsSection isActive={isActive} />}

      {tab === 'summary' && <FloodSummarySection isActive={isActive} onPickTab={pickTab} />}

      {tab === 'north' && <NorthFlowSection isActive={isActive} />}

      {tab === 'watch' && <BkkDistrictSection isActive={isActive} />}

      {tab === 'reports' && <CitizenReportsSection isActive={isActive} />}

      {tab === 'shelter' && <ShelterSection isActive={isActive} />}
    </div>
  );
}
