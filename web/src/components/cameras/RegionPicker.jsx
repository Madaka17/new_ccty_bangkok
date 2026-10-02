// Region first, then (optionally) one of its provinces: the nationwide tab of the live camera page and the camera
// map page. Counts are of the cameras passed in, so they follow any search or filter applied before.
import { useMemo } from 'react';

// The six regions, north to south; each camera's region comes from the server (thai_regions.py)
const REGIONS = ['ภาคเหนือ', 'ภาคอีสาน', 'ภาคกลาง', 'ภาคตะวันออก', 'ภาคตะวันตก', 'ภาคใต้'];
const CHIP_OFF = 'bg-white text-slate-700 border-slate-300 hover:bg-slate-50';
const CHIP_ON = 'bg-blue-600 text-white border-blue-600';

export function inPlace(c, region, province) {
  return (!region || c.region === region) && (!province || c.province === province);
}

export default function RegionPicker({ cameras, region, province, onRegion, onProvince }) {
  const perRegion = useMemo(() => {
    const n = {};
    for (const c of cameras) n[c.region] = (n[c.region] || 0) + 1;
    return n;
  }, [cameras]);
  const provinces = useMemo(() => {
    const n = {};
    for (const c of cameras) if (region && c.region === region && c.province) n[c.province] = (n[c.province] || 0) + 1;
    return Object.entries(n).sort((a, b) => a[0].localeCompare(b[0], 'th'));
  }, [cameras, region]);
  const chips = [['', 'ทุกภาค', cameras.length], ...REGIONS.map((r) => [r, r, perRegion[r] || 0])];
  return (
    <div className="flex flex-col gap-3">
      <div role="group" aria-label="เลือกภาค" className="flex flex-wrap gap-2">
        {chips.map(([id, label, n]) => (
          <button
            key={id || 'all'}
            type="button"
            onClick={() => onRegion(id)}
            aria-pressed={region === id}
            disabled={Boolean(id) && !n}
            className={`cursor-pointer inline-flex items-center gap-1.5 rounded-lg border px-3 h-8 text-xs font-medium transition-colors duration-200 disabled:cursor-not-allowed disabled:opacity-40 ${region === id ? CHIP_ON : CHIP_OFF}`}
          >
            {label} <span className="tabular-nums opacity-80">{n}</span>
          </button>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor="cam-province" className="text-xs font-medium text-slate-700">จังหวัด</label>
        <select
          id="cam-province"
          value={province}
          onChange={(e) => onProvince(e.target.value)}
          disabled={!region}
          className="h-9 w-full sm:w-auto sm:min-w-[260px] rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 outline-none focus:border-blue-500 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <option value="">{region ? `ทุกจังหวัดใน${region} (${provinces.length} จังหวัด)` : 'เลือกภาคก่อน แล้วเลือกจังหวัดได้'}</option>
          {provinces.map(([p, n]) => (
            <option key={p} value={p}>{p} ({n} กล้อง)</option>
          ))}
        </select>
      </div>
    </div>
  );
}

