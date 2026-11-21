import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, test } from 'vitest';
import KpiCards from './KpiCards.jsx';

const render = (props = {}) =>
  renderToStaticMarkup(
    <KpiCards bkkFlow={80} incidentCount={3} floodCount={0} online={12} onNavigate={() => {}} onIncidents={() => {}} {...props} />,
  );

describe('KpiCards', () => {
  test('shows the four tiles with plain Thai labels', () => {
    const html = render();
    expect(html).toContain('คะแนนจราจร กทม.');
    expect(html).toContain('อุบัติเหตุและรถเสีย');
    expect(html).toContain('ถนนน้ำท่วม');
    expect(html).toContain('คนดูอยู่ตอนนี้');
  });

  test('traffic chip follows the flow level', () => {
    expect(render({ bkkFlow: 80 })).toContain('คล่องตัว');
    expect(render({ bkkFlow: 50 })).toContain('ชะลอตัว');
    expect(render({ bkkFlow: 20 })).toContain('ติดขัด');
  });

  test('flood chip says none when zero and a warning otherwise', () => {
    expect(render({ floodCount: 0 })).toContain('ไม่มี');
    expect(render({ floodCount: 4 })).toContain('ต้องระวัง');
  });

  test('missing data shows a dash, never NaN', () => {
    const html = render({ bkkFlow: null, floodCount: null, online: null, incidentCount: 0 });
    expect(html).not.toContain('NaN');
    expect(html).toContain('–');
    expect(html).toContain('รอข้อมูล');
  });

  test('tiles are buttons and use tokens, not raw colours', () => {
    const html = render();
    expect(html.match(/<button/g)).toHaveLength(4);
    expect(html).toContain('var(--c-chip-up-bg)');
    expect(html).not.toMatch(/#[0-9a-fA-F]{6}/);
  });
});
