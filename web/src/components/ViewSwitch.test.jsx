import { describe, it, expect } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import ViewSwitch from './ViewSwitch.jsx';

const makeTabs = (n) => Array.from({ length: n }, (_, i) => ({ id: `t${i}`, label: `Tab ${i}`, icon: 'water' }));

const tablistClass = (html) => html.match(/role="tablist"[^>]*class="([^"]*)"/)?.[1]
  ?? html.match(/class="([^"]*)"[^>]*role="tablist"/)?.[1];

describe('ViewSwitch on phones', () => {
  it('9 tabs: one horizontally scrollable row below sm, grid from sm up', () => {
    const cls = tablistClass(renderToStaticMarkup(<ViewSwitch tabs={makeTabs(9)} value="t0" onChange={() => {}} label="x" />));
    expect(cls).toContain('overflow-x-auto');
    expect(cls).toContain('sm:grid');
  });

  it('3 tabs: unchanged, no horizontal scroll row', () => {
    const cls = tablistClass(renderToStaticMarkup(<ViewSwitch tabs={makeTabs(3)} value="t0" onChange={() => {}} label="x" />));
    expect(cls).not.toContain('overflow-x-auto');
  });
});
