import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, test, vi } from 'vitest';

// Modules read window at import time and the page reads window.matchMedia on first render; SSR has no window,
// so a minimal one is set before the page is imported.
vi.hoisted(() => {
  globalThis.window = { matchMedia: undefined };
});
const { default: DashboardPage } = await import('./DashboardPage.jsx');

describe('DashboardPage overview cards', () => {
  test('shows the time range, vehicle, KPI, BMA and recent-incident cards in plain Thai', () => {
    const html = renderToStaticMarkup(
      <DashboardPage isActive={false} incidents={{ camera: [], longdo: [] }} onNavigate={() => {}} />,
    );
    expect(html).toContain('role="tablist"');
    expect(html).toContain('ดาวน์โหลด');
    expect(html).toContain('รถที่ผ่านกล้อง AI');
    expect(html).toContain('คะแนนจราจร กทม.');
    expect(html).toContain('รถเฉลี่ยต่อกล้อง กทม.');
    expect(html).toContain('เหตุบนถนนล่าสุด');
    expect(html).not.toContain('NaN');
  });
});
