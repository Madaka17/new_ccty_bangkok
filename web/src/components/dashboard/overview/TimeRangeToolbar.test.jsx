import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, test } from 'vitest';
import TimeRangeToolbar from './TimeRangeToolbar.jsx';

const render = (props = {}) =>
  renderToStaticMarkup(<TimeRangeToolbar range="7d" onRange={() => {}} onDownload={() => {}} {...props} />);

describe('TimeRangeToolbar', () => {
  test('lists the three ranges in plain Thai as a tablist', () => {
    const html = render();
    expect(html).toContain('role="tablist"');
    expect(html).toContain('24 ชั่วโมง');
    expect(html).toContain('7 วัน');
    expect(html).toContain('30 วัน');
  });

  test('marks only the selected range', () => {
    const html = render({ range: '7d' });
    expect(html.match(/aria-selected="true"/g)).toHaveLength(1);
    expect(html).toMatch(/aria-selected="true"[^>]*>7 วัน/);
  });

  test('has a download button and renders the extra slot', () => {
    const html = render({ extra: <span>ตัวอย่างพิเศษ</span> });
    expect(html).toContain('ดาวน์โหลด');
    expect(html).toContain('ตัวอย่างพิเศษ');
  });
});
