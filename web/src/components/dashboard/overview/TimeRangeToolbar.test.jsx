import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, test } from 'vitest';
import TimeRangeToolbar from './TimeRangeToolbar.jsx';

const render = (props = {}) =>
  renderToStaticMarkup(<TimeRangeToolbar range="7d" onRange={() => {}} onDownload={() => {}} {...props} />);

describe('TimeRangeToolbar', () => {
  test('lists the three ranges in plain Thai in a labelled group, not a tablist', () => {
    const html = render();
    expect(html).toContain('role="group"');
    expect(html).toContain('aria-label="ช่วงเวลา"');
    expect(html).not.toContain('role="tablist"');
    expect(html).not.toContain('role="tab"');
    expect(html).toContain('24 ชั่วโมง');
    expect(html).toContain('7 วัน');
    expect(html).toContain('30 วัน');
  });

  test('marks only the selected range with aria-pressed', () => {
    const html = render({ range: '7d' });
    expect(html.match(/aria-pressed="true"/g)).toHaveLength(1);
    expect(html).toMatch(/aria-pressed="true"[^>]*>7 วัน/);
  });

  test('range buttons and the download button meet the 44px touch target', () => {
    const html = render();
    expect(html).not.toContain('min-h-10');
    expect(html.match(/min-h-11/g)).toHaveLength(4);
  });

  test('has a download button and renders the extra slot', () => {
    const html = render({ extra: <span>ตัวอย่างพิเศษ</span> });
    expect(html).toContain('ดาวน์โหลด');
    expect(html).toContain('ตัวอย่างพิเศษ');
  });

  test('download button is disabled while there are no rows to save', () => {
    expect(render({ downloadDisabled: true })).toMatch(/<button[^>]*disabled=""[^>]*>(?:(?!<\/button>)[\s\S])*ดาวน์โหลด/);
    expect(render({ downloadDisabled: false })).not.toContain('disabled=""');
  });
});
