import { describe, it, expect } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { Bars } from './AccidentSection.jsx';

describe('Bars hourly chart', () => {
  const values = Array.from({ length: 24 }, (_, i) => (i % 5) + 1);
  const html = renderToStaticMarkup(<Bars values={values} highlight={new Set([3])} />);

  it('gives every bar column full height so the percentage resolves', () => {
    const cols = html.match(/<div class="flex-1 [^"]*"/g);
    expect(cols).toHaveLength(24);
    for (const c of cols) expect(c).toContain('h-full');
  });

  it('renders non-zero percentage heights', () => {
    const heights = [...html.matchAll(/style="height:([\d.]+)%"/g)].map((m) => Number(m[1]));
    expect(heights).toHaveLength(24);
    expect(Math.min(...heights)).toBeGreaterThan(0);
  });
});
