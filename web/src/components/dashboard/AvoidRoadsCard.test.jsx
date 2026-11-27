import { describe, it, expect } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import AvoidRoadsCard from './AvoidRoadsCard.jsx';

describe('AvoidRoadsCard', () => {
  const summary = {
    ready: true,
    congested: [{ name: 'Rama 4', level: 'red', red_km: 3.2, length_km: 8.5 }],
  };

  it('shows only the jammed km, not the "จาก N กม." road-length ratio', () => {
    const html = renderToStaticMarkup(<AvoidRoadsCard summary={summary} />);
    expect(html).toContain('ติด 3.2 กม.');
    expect(html).not.toContain('จาก');
    expect(html).not.toContain('ติดยาว');
  });

  it('keeps the data-range fallback when there is no jam length', () => {
    const html = renderToStaticMarkup(
      <AvoidRoadsCard summary={{ ready: true, congested: [{ name: 'Rama 4', level: 'yellow', red_km: 0, length_km: 8.5 }] }} />,
    );
    expect(html).toContain('ช่วงที่มีข้อมูล 8.5 กม.');
  });
});
