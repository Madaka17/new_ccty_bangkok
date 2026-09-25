// Accidents & Risk: the Thai RSC accidents with black-spot measures and the AI analysis of the BMA
// risk map, one page with two tabs (both used to be tabs of City Analytics).
import { useCallback, useEffect, useState } from 'react';
import { fetchAnalytics } from '../lib/api.js';
import { trackView } from '../lib/telemetry.js';
import { Button, Card, Skeleton, ErrorState } from './dashboard/ui.jsx';
import { PageHeader } from './dashboard/primitives.jsx';
import { fmtDateTime } from './dashboard/format.js';
import ViewSwitch from './ViewSwitch.jsx';
import AccidentSection from './AccidentSection.jsx';
import RiskAnalysisCard from './dashboard/RiskAnalysisCard.jsx';

const POLL_MS = 60000;
const TABS = [
  { id: 'accidents', label: 'อุบัติเหตุและมาตรการ', hint: 'Thai RSC · Black Spots · มาตรการรายจุด', icon: 'safety' },
  { id: 'riskbkk', label: 'จุดเสี่ยง กทม. (AI)', hint: 'แผนที่เสี่ยง กทม. · AI วิเคราะห์รายเขต', icon: 'analytics' },
];

function Accidents({ isActive }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback((refresh = false) => {
    setRefreshing(true);
    return fetchAnalytics(refresh)
      .then((d) => { setData(d); setError(false); })
      .catch(() => setError(true))
      .finally(() => setRefreshing(false));
  }, []);

  useEffect(() => {
    if (!isActive) return;
    load();
    const id = setInterval(() => load(), POLL_MS);
    return () => clearInterval(id);
  }, [isActive, load]);

  if (error && !data) return <ErrorState onRetry={() => load(true)} retrying={refreshing} />;
  if (!data) {
    return (
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[0, 1, 2, 3].map((i) => (
          <Card key={i} as="div" className="p-4"><Skeleton className="h-7 w-24" /><Skeleton className="h-3 w-32 mt-2" /></Card>
        ))}
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-3 text-xs text-slate-500">
        อัปเดต {fmtDateTime(data.generated_at)}
        <Button size="sm" loading={refreshing} onClick={() => load(true)}>รีเฟรช</Button>
      </div>
      <AccidentSection d={data.accidents} />
    </div>
  );
}

export default function SafetyPage({ isActive }) {
  const [tab, setTab] = useState('accidents');
  const pick = (id) => {
    setTab(id);
    trackView(`safety:${id}`);
  };
  return (
    <div className="flex flex-col gap-4">
      <PageHeader title="Accidents & Risk" description="อุบัติเหตุ มาตรการลดอุบัติเหตุรายจุด และจุดเสี่ยงจราจร กทม. ที่ AI วิเคราะห์" />
      <ViewSwitch tabs={TABS} value={tab} onChange={pick} label="มุมมองอุบัติเหตุและจุดเสี่ยง" />
      {tab === 'accidents' && <Accidents isActive={isActive} />}
      {tab === 'riskbkk' && <RiskAnalysisCard isActive={isActive} />}
    </div>
  );
}
