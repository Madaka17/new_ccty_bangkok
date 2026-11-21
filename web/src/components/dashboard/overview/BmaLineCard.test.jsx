import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, test } from 'vitest';
import BmaLineCard from './BmaLineCard.jsx';

const hourly = [
  { hour: '2026-11-21 08:00:00', cars: 300, motorcycles: 100, cam_count: 4 },
  { hour: '2026-11-21 09:00:00', cars: 200, motorcycles: 50, cam_count: 4 },
  { hour: '2026-11-21 10:00:00', cars: 400, motorcycles: 120, cam_count: 4 },
];

describe('BmaLineCard', () => {
  test('empty input shows the empty state, no SVG', () => {
    const html = renderToStaticMarkup(<BmaLineCard hourly={[]} />);
    expect(html).toContain('ยังไม่มีข้อมูลรายชั่วโมง');
    expect(html).not.toContain('<svg');
  });

  test('shows the title, the latest per-camera total and two lines', () => {
    const html = renderToStaticMarkup(<BmaLineCard hourly={hourly} />);
    expect(html).toContain('รถเฉลี่ยต่อกล้อง กทม.');
    // latest hour: (400 + 120) / 4 = 130 per camera
    expect(html).toContain('130');
    expect(html.match(/<path/g)?.length).toBeGreaterThanOrEqual(2);
    expect(html).toContain('var(--c-series-a)');
    expect(html).toContain('var(--c-series-b)');
  });

  test('never prints NaN', () => {
    const html = renderToStaticMarkup(<BmaLineCard hourly={[{ hour: 'bad', cars: 1 }]} />);
    expect(html).not.toContain('NaN');
  });
});
