// The 7-day national outlook (/api/flood/forecast, national_forecast.py) shared by the first four tabs of the
// Water page: dams, provinces, roads and the summary.
import { useCallback, useEffect, useState } from 'react';

const POLL_MS = 5 * 60000;

export const RISK = {
  critical: { label: 'เสี่ยงสูงมาก', tone: 'red' },
  flood: { label: 'เสี่ยงสูง', tone: 'yellow' },
  watch: { label: 'เฝ้าระวัง', tone: 'blue' },
  normal: { label: 'ปกติ', tone: 'green' },
};
export const CHANCE = {
  high: { label: 'โอกาสท่วมสูง', tone: 'red' },
  medium: { label: 'โอกาสท่วมปานกลาง', tone: 'yellow' },
  low: { label: 'โอกาสท่วมต่ำ', tone: 'blue' },
};
export const REGIONS = ['ภาคเหนือ', 'ภาคอีสาน', 'ภาคกลาง', 'ภาคตะวันออก', 'ภาคตะวันตก', 'ภาคใต้'];
export const CHIP_OFF = 'bg-white text-slate-700 border-slate-300 hover:bg-slate-50';
export const CHIP_ON = 'bg-blue-600 text-white border-blue-600';

export const sum = (xs) => (xs || []).reduce((a, b) => a + (b || 0), 0);

// "เต็มแล้ว" / "เต็มใน 3 วัน" / "" for a large dam
export function fullText(d) {
  if (d.full_day === 0) return 'เต็มแล้ว';
  if (d.full_day) return `เต็มใน ${d.full_day} วัน`;
  return '';
}

export function useFloodForecast(isActive) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const load = useCallback(() => {
    fetch('/api/flood/forecast')
      .then((r) => {
        if (!r.ok) throw new Error('forecast');
        return r.json();
      })
      .then((d) => {
        setData(d);
        setError(false);
      })
      .catch(() => setError(true));
  }, []);
  useEffect(() => {
    if (!isActive) return undefined;
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [isActive, load]);
  return { data, error, load };
}
