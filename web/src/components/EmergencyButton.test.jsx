import { describe, it, expect } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import EmergencyButton from './EmergencyButton.jsx';

describe('EmergencyButton inline (home answer panel)', () => {
  const html = renderToStaticMarkup(<EmergencyButton inline />);
  const btn = html.match(/<button[^>]*>[\s\S]*?ฉุกเฉิน<\/button>/)[0];

  it('is a solid red pill, not a dashed tag', () => {
    expect(btn).toContain('rounded-full');
    expect(btn).toContain('bg-[var(--act-fill)]');
    expect(btn).toContain('text-white');
    expect(btn).not.toContain('border-dashed');
    expect(btn).not.toContain('rounded-md');
  });

  it('switches to dark ink in dark mode so the label stays readable on the red fill', () => {
    expect(btn).toContain('dark:text-[#0f0f10]');
  });

  it('keeps the 44px touch height', () => {
    expect(btn).toContain('h-11');
  });
});
