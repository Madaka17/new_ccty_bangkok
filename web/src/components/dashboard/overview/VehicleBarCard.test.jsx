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

describe('VehicleBars sizing', () => {
  test('draws at the measured width, 240 units tall, 1 unit per CSS px', () => {
    const html = renderToStaticMarkup(<VehicleBars rows={rows} width={360} />);
    expect(html).toContain('viewBox="0 0 360 240"');
    expect(html).toContain('height="240"');
    expect(html).toContain('width="100%"');
  });

  test('axis labels are 12 px', () => {
    const html = renderToStaticMarkup(<VehicleBars rows={rows} />);
    expect(html).not.toContain('font-size="11"');
    expect(html).toContain('font-size="12"');
  });

  test('narrow charts (under 480 px) thin the x labels harder', () => {
    const many = Array.from({ length: 24 }, (_, i) => ({ key: `k${i}`, label: `${i} น.`, cars: 1, motorcycles: 1 }));
    const narrow = renderToStaticMarkup(<VehicleBars rows={many} width={360} />);
    const wide = renderToStaticMarkup(<VehicleBars rows={many} width={640} />);
    // thinLabels(24, 6) = 4 gives labels at 0,4,...,20 = six; thinLabels(24, 12) = 2 gives twelve
    expect(narrow.match(/text-anchor="middle"/g)).toHaveLength(6);
    expect(wide.match(/text-anchor="middle"/g)).toHaveLength(12);
  });

  test('bars keep width 6 when they fit and shrink (min 2) when there are too many buckets', () => {
    const few = renderToStaticMarkup(<VehicleBars rows={rows} width={640} />);
    expect(few).toMatch(/<rect x="[^"]*" y="[^"]*" width="6"[^>]*fill="var\(--c-series-a\)"/);
    const many = Array.from({ length: 100 }, (_, i) => ({ key: `k${i}`, label: `${i} น.`, cars: 5, motorcycles: 5 }));
    const html = renderToStaticMarkup(<VehicleBars rows={many} width={640} />);
    const widths = [...html.matchAll(/<rect x="[^"]*" y="[^"]*" width="([^"]+)"[^>]*fill="var\(--c-series-[ab]\)"/g)].map((m) => Number(m[1]));
    expect(widths).toHaveLength(200);
    for (const w of widths) {
      expect(w).toBeGreaterThanOrEqual(2);
      expect(w).toBeLessThan(6);
    }
  });
});
