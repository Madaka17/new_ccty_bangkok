import { PAGE_TITLES, PAGE_HINTS } from './navPages.js';

// Every page that can be opened, for the top bar search
export const ALL_PAGES = Object.keys(PAGE_TITLES).map((id) => ({ id, label: PAGE_TITLES[id], hint: PAGE_HINTS[id] || '' }));

// Label matches first, then hint-only matches; input order kept inside each group
export function searchPages(query, pages, limit = 6) {
  const q = String(query || '').trim().toLowerCase();
  if (!q) return [];
  const byLabel = [];
  const byHint = [];
  for (const p of pages) {
    if ((p.label || '').toLowerCase().includes(q)) byLabel.push(p);
    else if ((p.hint || '').toLowerCase().includes(q)) byHint.push(p);
  }
  return [...byLabel, ...byHint].slice(0, limit);
}
