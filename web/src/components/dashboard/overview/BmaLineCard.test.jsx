import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, test, vi } from 'vitest';
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

describe('BmaLineCard sizing and latest hour', () => {
  test('draws the two-line chart 200 units tall at 1 unit per CSS px', () => {
    const html = renderToStaticMarkup(<BmaLineCard hourly={hourly} />);
    expect(html).toContain('viewBox="0 0 640 200"');
    expect(html).toContain('height="200"');
    expect(html).toContain('width="100%"');
  });

  test('the big number uses the last complete hour while the current hour is still running', () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date(2026, 10, 21, 10, 30));
    try {
      const html = renderToStaticMarkup(<BmaLineCard hourly={hourly} />);
      // 10:00 is still running, so 09:00 is the number: (200 + 50) / 4 = 62.5 per camera
      expect(html).toContain('62.5');
      expect(html).toContain('ล่าสุด 09 น.');
      expect(html).not.toContain('>130<');
    } finally {
      vi.useRealTimers();
    }
  });
});
