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
