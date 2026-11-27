import { describe, it, expect } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import HeroBanner from './HeroBanner.jsx';
import { Button } from './ui.jsx';

describe('HeroBanner', () => {
  const html = renderToStaticMarkup(<HeroBanner onPrimary={() => {}} />);

  it('renders exactly one h1 with the hero title', () => {
    const h1s = html.match(/<h1[\s>]/g) || [];
    expect(h1s.length).toBe(1);
    expect(html).toContain('id="hero-title"');
    expect(html).toContain('เช็กกรุงเทพฯ ก่อนออกจากบ้าน');
  });

  it('labels the section with the title and shows the subtitle', () => {
    expect(html).toContain('aria-labelledby="hero-title"');
    expect(html).toContain('รถติด น้ำท่วม อุบัติเหตุ อัปเดตสดทุกนาที');
  });

  it('uses the 960w/1920w photo with a decorative empty alt', () => {
    expect(html).toContain('src="/hero/benjakitti-1920.webp"');
    expect(html).toContain('srcSet="/hero/benjakitti-960.webp 960w, /hero/benjakitti-1920.webp 1920w"');
    expect(html).toContain('alt=""');
  });

  it('has a pill outline button with the primary copy', () => {
    expect(html).toContain('ดูสถานะตอนนี้');
    const btn = html.match(/<button[^>]*>ดูสถานะตอนนี้<\/button>/);
    expect(btn).not.toBeNull();
    expect(btn[0]).toContain('rounded-full');
    expect(btn[0]).toContain('border-white/80');
  });

  it('reveals the title, subtitle and button one after another (indexes 0, 1, 2)', () => {
    expect(html).toMatch(/<h1[^>]*class="rv[^"]*"[^>]*--i:0/);
    expect(html).toMatch(/<p class="rv[^"]*"[^>]*--i:1/);
    expect(html).toMatch(/<button[^>]*class="rv[^"]*"[^>]*--i:2/);
  });

  it('is a thin 112px banner on phones and keeps 300/360px from sm up', () => {
    expect(html).toContain('h-[112px]');
    expect(html).toContain('sm:h-[300px]');
    expect(html).toContain('lg:h-[360px]');
  });

  it('hides the subtitle and the button below sm, so the phone shows only the title', () => {
    expect(html).toMatch(/<p class="rv[^"]*hidden sm:block[^"]*"/);
    const btn = html.match(/<button[^>]*>ดูสถานะตอนนี้<\/button>/);
    expect(btn[0]).toContain('hidden sm:inline-flex');
  });

  it('keeps the credit small (10px) on phones', () => {
    expect(html).toContain('text-[10px]');
  });

  it('marks the photo for the slow settle-in zoom', () => {
    expect(html).toContain('hero-img-settle');
  });

  it('credits the photo with a new-tab CC BY link', () => {
    expect(html).toContain('https://commons.wikimedia.org/wiki/File:Benjakitti_Forest_Park_(I).jpg');
    expect(html).toContain('ภาพ: Supanut Arunoprayote (CC BY 4.0)');
  });
});

describe('Button', () => {
  it('uses pill corners for every variant', () => {
    for (const variant of ['primary', 'secondary', 'ghost', 'danger']) {
      const out = renderToStaticMarkup(<Button variant={variant}>x</Button>);
      expect(out).toContain('rounded-full');
      expect(out).not.toContain('rounded-md');
    }
  });
});
