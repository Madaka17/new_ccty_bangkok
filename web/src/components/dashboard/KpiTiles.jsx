import { Badge } from './ui.jsx';
import { StatTile } from './primitives.jsx';
import { fmtNum, flowLevel } from './format.js';

export default function KpiTiles({ summary }) {
  const loading = !summary;
  const lv = summary ? flowLevel(summary.flow_index) : null;
  const isBma = !!summary?.is_bma;
  const totalKm = summary?.total_km ? Math.round(summary.total_km) : 0;
  const greenKm = totalKm && summary ? Math.round((totalKm * summary.green_pct) / 100) : 0;
  const yellowKm = totalKm && summary ? Math.round((totalKm * summary.yellow_pct) / 100) : 0;
  const redKm = totalKm && summary ? Math.round((totalKm * summary.red_pct) / 100) : 0;

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <StatTile
        label={isBma ? "ภาพรวมการจราจร BMA" : "ภาพรวมการจราจร"}
        value={summary ? `${summary.flow_index} / 100` : '–'}
        sub={summary ? (isBma ? `กล้อง BMA ออนไลน์ ${fmtNum(summary.camera_count)} ตัว` : `${lv.hint} (${fmtNum(summary.road_count)} สาย)`) : 'กำลังโหลดข้อมูล...'}
        badge={summary ? <Badge tone={lv.key === 'neutral' ? 'blue' : lv.key} dot>{lv.label}</Badge> : null}
        loading={loading}
        tone={summary ? (lv.key === 'neutral' ? undefined : lv.key) : undefined}
      />
      <StatTile
        label={isBma ? "กล้องคล่องตัว" : "ถนนคล่องตัว"}
        value={summary ? `${summary.green_pct}%` : '–'}
        sub={summary ? (isBma ? `${fmtNum(summary.free_count || 0)} กล้อง (0-4 คัน)` : `ระยะทาง ~${fmtNum(greenKm)} กม.`) : ''}
        badge={summary ? <Badge tone="green">คล่องตัว</Badge> : null}
        loading={loading}
        tone="green"
      />
      <StatTile
        label={isBma ? "กล้องปานกลาง" : "ถนนปานกลาง"}
        value={summary ? `${summary.yellow_pct}%` : '–'}
        sub={summary ? (isBma ? `${fmtNum(summary.moderate_count || 0)} กล้อง (5-12 คัน)` : `ระยะทาง ~${fmtNum(yellowKm)} กม.`) : ''}
        badge={summary ? <Badge tone="yellow">ปานกลาง</Badge> : null}
        loading={loading}
        tone="yellow"
      />
      <StatTile
        label={isBma ? "กล้องหนาแน่น" : "ถนนหนาแน่น"}
        value={summary ? `${summary.red_pct}%` : '–'}
        sub={summary ? (isBma ? `${fmtNum(summary.heavy_count || 0)} กล้อง (13+ คัน)` : `ระยะทาง ~${fmtNum(redKm)} กม.`) : ''}
        badge={summary ? <Badge tone="red">หนาแน่น</Badge> : null}
        loading={loading}
        tone="red"
      />
    </div>
  );
}

