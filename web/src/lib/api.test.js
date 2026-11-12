import { describe, it, expect, vi, afterEach } from 'vitest';
import { fetchJson } from './api.js';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('fetchJson', () => {
  it('returns the parsed JSON of a 2xx answer', async () => {
    const fetchMock = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ items: [1, 2] }) }));
    vi.stubGlobal('fetch', fetchMock);
    await expect(fetchJson('/api/x', 'x')).resolves.toEqual({ items: [1, 2] });
    expect(fetchMock).toHaveBeenCalledWith('/api/x', undefined);
  });

  it('throws Error(tag) on a non-2xx answer', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 503, json: async () => ({}) })));
    await expect(fetchJson('/api/x', 'my_tag')).rejects.toThrow(new Error('my_tag'));
    await expect(fetchJson('/api/x', 'my_tag')).rejects.toThrow('my_tag');
  });

  it('passes init through to fetch', async () => {
    const fetchMock = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({}) }));
    vi.stubGlobal('fetch', fetchMock);
    const init = { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{"a":1}' };
    await fetchJson('/api/y', 'y', init);
    expect(fetchMock).toHaveBeenCalledWith('/api/y', init);
  });
});
