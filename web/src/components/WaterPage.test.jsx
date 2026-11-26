import { describe, it, expect, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';

// Sidebar.jsx pulls in theme.js, which touches window at import time; this suite runs in node, so stub the title map
vi.mock('./Sidebar.jsx', () => ({ PAGE_TITLES: { water: 'น้ำท่วม' } }));
const { default: WaterPage } = await import('./WaterPage.jsx');

const html = renderToStaticMarkup(<WaterPage isActive />);

// Tab labels in the order the page must show them (Bangkok first)
const ORDER = [
  'น้ำท่วมใน กทม.',
  'จุดพักพิงใกล้ฉัน',
  'เรื่องที่คนแจ้ง',
  'จุดจอดรถหนีน้ำ',
  'น้ำในเขื่อนทั่วประเทศ',
  'คาดการณ์น้ำท่วม',
  'ถนนน้ำท่วมทั่วประเทศ',
  'สรุปสถานการณ์',
  'เส้นทางน้ำเหนือ',
];

// The tab text sits in its own span, so ">label<" finds the label and not the hover hint
const at = (label) => html.indexOf(`>${label}<`);

describe('WaterPage tabs', () => {
  it('lists the tabs in the Bangkok-first order', () => {
    const positions = ORDER.map(at);
    positions.forEach((p, i) => expect(p, ORDER[i]).toBeGreaterThanOrEqual(0));
    const sorted = [...positions].sort((a, b) => a - b);
    expect(positions).toEqual(sorted);
  });

  it('opens on the Bangkok tab by default', () => {
    const selected = html.match(/role="tab" aria-selected="true"[\s\S]*?<span class="block[^>]*>([^<]+)<\/span>/);
    expect(selected?.[1]).toBe('น้ำท่วมใน กทม.');
  });
});
