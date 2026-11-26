import { describe, it, expect } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import ReportFloodForm from './ReportFloodForm.jsx';

describe('ReportFloodForm photo picker', () => {
  const html = renderToStaticMarkup(<ReportFloodForm pin={null} locating={false} onUseMyLocation={() => {}} onPinChange={() => {}} onAreaChange={() => {}} onSent={() => {}} />);
  const input = html.match(/<input[^>]*id="report-photo"[^>]*>/)[0];

  it('hides the native file input but keeps it focusable', () => {
    expect(input).toContain('type="file"');
    expect(input).toContain('sr-only');
  });

  it('shows a Thai pill button linked to the input', () => {
    expect(html).toMatch(/<label[^>]*for="report-photo"[^>]*>[^<]*เลือกรูป/);
  });

  it('shows the Thai no-file line by default', () => {
    expect(html).toContain('ยังไม่ได้เลือกรูป');
    expect(html).not.toContain('No file chosen');
    expect(html).not.toContain('Choose File');
  });
});
