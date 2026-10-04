// "สรุปสถานการณ์" tab of the Water page: Qwen's summary of everything on the other three tabs (dams, provinces,
// roads) with the key numbers and what people should do (/api/flood/forecast, national_forecast.py).
import { Card, ErrorState, SectionHeader, Skeleton } from '../dashboard/ui.jsx';
import { StatTile, StatusBanner } from '../dashboard/primitives.jsx';
import { agoText, fmtDateTime } from '../dashboard/format.js';
import { useFloodForecast } from './forecastData.js';

export default function FloodSummarySection({ isActive, onPickTab }) {
  const { data, error, load } = useFloodForecast(isActive);

  if (error && !data) return <ErrorState message="โหลดสรุปสถานการณ์ไม่สำเร็จ" onRetry={load} />;
  if (!data) return <Skeleton className="h-[400px] rounded-xl" />;
  if (!data.provinces) return <p className="text-sm text-slate-600 px-1">ระบบกำลังสรุปสถานการณ์รอบแรก ลองใหม่ในอีกไม่กี่นาที</p>;

  const s = data.ai?.summary;
  const items = data.ai?.provinces?.items || {};
  const risk = (lv) => data.provinces.filter((p) => (items[p.province]?.risk || p.level) === lv).length;
  const fullNow = data.dams.filter((d) => d.full_day === 0).length;
  const fullSoon = data.dams.filter((d) => d.full_day > 0).length;
  const n = data.now_counts || {};
  const tone = risk('critical') ? 'red' : risk('flood') ? 'yellow' : 'green';
  const links = [['situation', 'ดูน้ำในเขื่อน'], ['provinces', 'ดูจังหวัดที่เสี่ยง'], ['roads', 'ดูถนนน้ำท่วม']];

  return (
    <div className="flex flex-col gap-4">
      <StatusBanner tone={tone} label={tone === 'red' ? 'น่าห่วงมาก' : tone === 'yellow' ? 'น่าห่วง' : 'ปกติ'}>
        {s?.headline || `วันนี้วิกฤต ${n.critical || 0} จังหวัด · 7 วันข้างหน้าเสี่ยงสูงมาก ${risk('critical')} จังหวัด`}
      </StatusBanner>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatTile label="จังหวัดที่ท่วมวันนี้" value={(n.critical || 0) + (n.flood || 0)} tone="red" sub={`วิกฤต ${n.critical || 0} จังหวัด`} />
        <StatTile label="จังหวัดเสี่ยงสูงใน 7 วัน" value={risk('critical') + risk('flood')} tone="yellow" sub={`เฝ้าระวังอีก ${risk('watch')} จังหวัด`} />
        <StatTile label="เขื่อนใหญ่ที่เต็ม" value={fullNow} sub={`จะเต็มใน 7 วันอีก ${fullSoon} แห่ง`} />
        <StatTile label="ถนนท่วม / เสี่ยง" value={`${data.roads.flooded.length} / ${data.roads.risk.length}`} sub="ท่วมอยู่ / อาจท่วมใน 7 วัน" />
      </div>

      <Card className="p-4 flex flex-col gap-3">
        <SectionHeader
          id="summary-title"
          title="สรุปสถานการณ์น้ำท่วม"
          description={data.ai?.generated_at ? `AI สรุปเมื่อ ${fmtDateTime(data.ai.generated_at)} (${agoText(data.ai.generated_at)})` : 'ยังไม่มีสรุปจาก AI'}
        />
        {s?.summary ? (
          <p className="text-sm text-slate-800 leading-7">{s.summary}</p>
        ) : (
          <p className="text-sm text-slate-600">{data.ai_running ? 'AI กำลังสรุป...' : 'ยังไม่มีสรุปจาก AI ดูตัวเลขด้านบนและหัวข้ออื่นแทน'}</p>
        )}
        {s?.actions?.length > 0 && (
          <div>
            <p className="text-sm font-semibold text-slate-900 mb-1">ควรทำอะไร</p>
            <ul className="list-disc pl-5 flex flex-col gap-1 text-sm text-slate-800">
              {s.actions.map((a) => <li key={a}>{a}</li>)}
            </ul>
          </div>
        )}
        <div className="flex flex-wrap gap-2">
          {links.map(([id, label]) => (
            <button key={id} type="button" onClick={() => onPickTab(id)}
              className="cursor-pointer rounded-lg border border-slate-300 bg-white px-3 h-8 text-xs font-medium text-slate-700 hover:bg-slate-50">
              {label}
            </button>
          ))}
        </div>
      </Card>

      <p className="text-[11px] text-slate-500 leading-4 px-1">
        สรุปจากน้ำในเขื่อน จุดวัดน้ำ ฝนพยากรณ์ ทางหลวงที่น้ำท่วม และเรื่องที่คนแจ้ง ทั่วประเทศ · เขียนโดย AI (Qwen) อาจผิดพลาดได้ ·
        ติดตามประกาศของหน่วยงานในพื้นที่ประกอบด้วย
      </p>
    </div>
  );
}
