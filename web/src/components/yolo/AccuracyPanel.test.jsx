import { describe, it, expect } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import AccuracyPanel from './AccuracyPanel.jsx';

const base = { active: true, title: 'ทดสอบ' };

describe('AccuracyPanel without a started count', () => {
  const html = renderToStaticMarkup(<AccuracyPanel active={false} stats={{ ...base, passed_cars: 790, passed_since: null }} />);
  const big = html.slice(html.indexOf('AI นับได้'), html.indexOf('text-[11px]'));   // the counter, not the breakdown line

  it('shows "not counted yet" instead of the lifetime number', () => {
    expect(big).toContain('ยังไม่ได้เริ่มนับ');
    expect(big).not.toContain('790');
  });

  it('disables the compare button and says how to start', () => {
    const btn = html.match(/<button[^>]*>[^<]*บันทึกผลเทียบ<\/button>/)[0];
    expect(btn).toContain('disabled');
    expect(html).toContain('กด &quot;เริ่มนับใหม่&quot; ก่อน');
  });

  it('is collapsed by default behind a details toggle with the new name', () => {
    expect(html).toMatch(/<details(?![^>]*\sopen)/);
    expect(html).toContain('ลองนับรถเทียบกับ AI');
    expect(html).not.toContain('AI นับแม่นแค่ไหน');
  });
});
