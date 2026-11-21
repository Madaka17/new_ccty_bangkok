import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, test } from 'vitest';
import { VehicleBars } from './VehicleBarCard.jsx';

const rows = [
  { key: '2026-11-21T08:00', label: '08 น.', cars: 120, motorcycles: 40 },
  { key: '2026-11-21T09:00', label: '09 น.', cars: 0, motorcycles: 0 },
  { key: '2026-11-21T10:00', label: '10 น.', cars: 90, motorcycles: 75 },
];

describe('VehicleBars', () => {
  test('empty input shows the plain Thai empty state and no SVG', () => {
    const html = renderToStaticMarkup(<VehicleBars rows={[]} />);
    expect(html).toContain('ยังไม่มีข้อมูลรถในช่วงนี้');
    expect(html).not.toContain('<svg');
  });

  test('draws an accessible chart with a text table fallback', () => {
    const html = renderToStaticMarkup(<VehicleBars rows={rows} />);
    expect(html).toContain('role="img"');
    expect(html).toContain('aria-label="กราฟรถที่ผ่านกล้อง AI');
    expect(html).toContain('class="sr-only"');
    expect(html).toContain('<td>120</td>');
    expect(html).toContain('<td>75</td>');
  });

  test('each bucket is keyboard focusable with a spoken label', () => {
    const html = renderToStaticMarkup(<VehicleBars rows={rows} />);
    expect(html.match(/tabindex="0"/g)).toHaveLength(3);
    expect(html).toContain('aria-label="08 น. รถยนต์ 120 คัน มอเตอร์ไซค์ 40 คัน"');
  });

  test('never prints NaN', () => {
    const html = renderToStaticMarkup(<VehicleBars rows={rows} />);
    expect(html).not.toContain('NaN');
  });

  test('uses the series tokens, no raw hex colours', () => {
    const html = renderToStaticMarkup(<VehicleBars rows={rows} />);
    expect(html).toContain('var(--c-series-a)');
    expect(html).toContain('var(--c-series-b)');
    expect(html).not.toMatch(/#[0-9a-fA-F]{6}/);
  });
});
