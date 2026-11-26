import { describe, it, expect } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import Reveal from './Reveal.jsx';

describe('Reveal', () => {
  it('renders the reveal class, its index as --i, and the child', () => {
    const html = renderToStaticMarkup(<Reveal index={2}><p>x</p></Reveal>);
    expect(html).toContain('class="rv');
    expect(html).toContain('--i:2');
    expect(html).toContain('<p>x</p>');
  });

  it('renders the tag it is given', () => {
    const html = renderToStaticMarkup(<Reveal as="li" index={0}>row</Reveal>);
    expect(html).toContain('<li');
    expect(html).toContain('row</li>');
  });

  it('shows at once when there is no IntersectionObserver (server render)', () => {
    const html = renderToStaticMarkup(<Reveal>x</Reveal>);
    expect(html).toMatch(/class="rv in/);
  });
});
