import { describe, it, expect } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import CityStatusStrip from './CityStatusStrip.jsx';

// The state marks are plain colour dots: a filled dot for green/yellow/red, a hollow ring for no data yet
const render = (props = {}) =>
  renderToStaticMarkup(<CityStatusStrip isActive={false} onNavigate={() => {}} onIncidents={() => {}} onAskText={() => {}} {...props} />);

describe('CityStatusStrip state marks', () => {
  it('draws no tick, triangle or dashed ring', () => {
    const html = render();
    expect(html).not.toContain('stroke-dasharray');
    expect(html).not.toContain('M6.5 10.2');
    expect(html).not.toContain('M8.6 2.9');
  });

  it('draws a hollow ring when there is no data yet', () => {
    const html = render();
    expect(html).toContain('<circle cx="10" cy="10" r="4.5" stroke="currentColor" stroke-width="1.5"');
  });
});

describe('CityStatusStrip colour key', () => {
  it('names the four states with the same words as the answer', () => {
    const html = render();
    expect(html).toContain('ระวังมาก');
    expect(html).toContain('รอข้อมูล');
    expect(html).not.toContain('เฝ้าดู');
    expect(html).not.toContain('ควรระวัง');
  });
});

describe('CityStatusStrip scroll reveal', () => {
  const html = render();

  it('shows the verdict panel at once, without a reveal animation', () => {
    expect(html).toMatch(/<section[^>]*aria-labelledby="city-verdict"/);
    expect(html).not.toMatch(/class="rv [^"]*"[^>]*aria-labelledby="city-verdict"/);
    expect(html).not.toMatch(/--i:0[^>]*aria-labelledby="city-verdict"/);
  });

  it('gives each check item its position index in the wide pipeline and the phone list', () => {
    for (let n = 0; n < 6; n++) {
      const items = html.match(new RegExp(`<li class="rv [^"]*"[^>]*--i:${n}`, 'g')) || [];
      expect(items.length, `index ${n}`).toBe(2);
    }
  });

  it('keeps the list items as children of their list', () => {
    expect(html).toMatch(/<ol[^>]*>(<li class="rv)/);
    expect(html).toMatch(/<ul[^>]*>(<li class="rv)/);
  });
});
