import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, test } from 'vitest';
import RecentIncidentsTable from './RecentIncidentsTable.jsx';

const incidents = {
  camera: [{ id: 'c1', title: 'รถชนท้าย', kind: 'accident', ts: 1700000000, image: '/x.jpg' }],
  longdo: [{ id: 'l1', title: 'รถเสียกลางถนน', kind: 'breakdown', start: '2026-11-21 08:30:00' }],
};

describe('RecentIncidentsTable', () => {
  test('empty input shows the plain Thai empty state', () => {
    const html = renderToStaticMarkup(<RecentIncidentsTable incidents={{ camera: [], longdo: [] }} onOpen={() => {}} />);
    expect(html).toContain('ตอนนี้ไม่มีเหตุบนถนน');
  });

  test('lists both sources with kind chips and a sortable time header', () => {
    const html = renderToStaticMarkup(<RecentIncidentsTable incidents={incidents} onOpen={() => {}} />);
    expect(html).toContain('เหตุบนถนนล่าสุด');
    expect(html).toContain('รถชนท้าย');
    expect(html).toContain('รถเสียกลางถนน');
    expect(html).toContain('กล้อง AI');
    expect(html).toContain('ข่าวจราจร');
    expect(html).toContain('aria-sort="descending"');
  });

  test('has a table for wide screens and a stacked list for phones', () => {
    const html = renderToStaticMarkup(<RecentIncidentsTable incidents={incidents} onOpen={() => {}} />);
    expect(html).toContain('hidden md:table');
    expect(html).toContain('md:hidden');
  });

  test('caps the rows at six', () => {
    const many = {
      camera: Array.from({ length: 9 }, (_, i) => ({ id: `c${i}`, title: `เหตุ${i}`, kind: 'accident', ts: 1700000000 - i })),
      longdo: [],
    };
    const html = renderToStaticMarkup(<RecentIncidentsTable incidents={many} onOpen={() => {}} />);
    // each row shows its title in the table and again in the phone list: six rows, two views
    expect(html.match(/เหตุ\d/g)).toHaveLength(12);
  });

  test('a row with no time says so instead of a relative time', () => {
    const html = renderToStaticMarkup(
      <RecentIncidentsTable incidents={{ camera: [{ id: 'x', title: 'ไม่มีเวลา', kind: 'accident' }], longdo: [] }} onOpen={() => {}} />,
    );
    expect(html).toContain('ไม่ทราบเวลา');
    expect(html).not.toContain('ยังไม่ได้วัด');
  });

  test('sort headers and row buttons meet the 44px touch target', () => {
    const html = renderToStaticMarkup(<RecentIncidentsTable incidents={incidents} onOpen={() => {}} />);
    expect(html).not.toContain('min-h-10');
    expect(html).toContain('min-h-11');
  });
});
