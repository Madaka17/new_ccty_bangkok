import { describe, it, expect, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';

const AI_TEXT = 'มี 2 แห่งที่เต็มแล้ว และอีก 2 แห่งจะเต็มภายใน 7 วัน';
const AI_NOTE = 'จะเต็มความจุภายใน 0 วัน';

const dams = [
  { id: 1, name: 'ภูมิพล', province: 'ตาก', storage: 9000, normal: 13462, pct: 67, pct_7d: 70, full_day: null, net: 0.4, rain7: [1, 2] },
  { id: 2, name: 'สิริกิติ์', province: 'อุตรดิตถ์', storage: 8000, normal: 9510, pct: 84, pct_7d: 90, full_day: 4, net: 0.2, rain7: [0] },
  { id: 3, name: 'ป่าสักชลสิทธิ์', province: 'ลพบุรี', storage: 1900, normal: 1960, pct: 97, pct_7d: 100, full_day: 0, net: 0, rain7: [3] },
];

const baseData = {
  dams,
  medium: { full: 0, count: 10, over80: 0, provinces: [] },
  provinces: [],
  updated_at: Math.floor(Date.now() / 1000) - 60,
};

let mockData;
vi.mock('./forecastData.js', async (importOriginal) => {
  const real = await importOriginal();
  return {
    ...real,
    useFloodForecast: () => ({ data: mockData, error: false, load: () => {} }),
  };
});

const { default: NationalWaterSection } = await import('./NationalWaterSection.jsx');

const HOURS = 3600;
const render = (generatedAt) => {
  mockData = { ...baseData, ai: { generated_at: generatedAt, water: { outlook: AI_TEXT, dams: { ภูมิพล: AI_NOTE } } } };
  return renderToStaticMarkup(<NationalWaterSection isActive />);
};

describe('NationalWaterSection stale AI text', () => {
  it('hides the AI outlook, per-dam notes and the AI time when the AI result is 3 weeks old', () => {
    const html = render(Math.floor(Date.now() / 1000) - 21 * 24 * HOURS);
    expect(html).not.toContain(AI_TEXT);
    expect(html).not.toContain(AI_NOTE);
    expect(html).not.toContain('AI วิเคราะห์เมื่อ');
  });

  it('shows the fallback built from the dams when the AI result is stale', () => {
    const html = render(Math.floor(Date.now() / 1000) - 21 * 24 * HOURS);
    expect(html).toContain('เขื่อนใหญ่เต็มแล้ว 1 แห่ง และจะเต็มใน 7 วันอีก 1 แห่ง จากทั้งหมด 3 แห่ง');
  });

  it('shows the AI outlook, per-dam note and AI time when the AI result is 1 hour old', () => {
    const html = render(Math.floor(Date.now() / 1000) - HOURS);
    expect(html).toContain(AI_TEXT);
    expect(html).toContain(AI_NOTE);
    expect(html).toContain('AI วิเคราะห์เมื่อ');
  });
});
