# Orange Console Theme Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the BKK StreetSmart web app to the user's reference screenshot: near-black ground, orange accent, filled-orange active menu row, and a desktop top bar with a page search.

**Architecture:** Nearly every colour already flows through CSS custom properties in `web/src/index.css` (`--c-*`, status `--ok/--watch/--act-*`, remapped Tailwind `--color-slate-*`). Task 1 swaps the token values. Task 2 restyles the sidebar's selected row and the segmented tabs. Task 3 adds a pure `searchPages()` helper and a `TopBar` component shown from `lg` up. Page content is not edited.

**Tech Stack:** React 18, Tailwind v4 (`@tailwindcss/vite`), Vite 5, Vitest 2.

**Spec:** User decisions from 2026-11-12 (this session). Reference: `C:\Users\user\Pictures\Screenshots\Screenshot 2026-11-12 211618.png`. Scope: colours + menu + top bar only. Keep light mode (orange on white). Status "watch" becomes bright yellow. Keep Noto Sans Thai Looped. No hero section, no table-row-as-card rework.

## Global Constraints

- All user-visible text in short plain Thai (memory: public-views-plain-thai).
- Colours only through tokens in `web/src/index.css`; no raw hex in `.jsx`.
- Text contrast ≥ 4.5:1 in both themes; touch targets ≥ 44px (`min-h-11`).
- Orange = action / selected / clickable only. Yellow `#facc15` = "watch" status. Green / red keep their meaning.
- Tailwind `blue-*` stays blue (water / info data colour). Only `.bg-blue-600` buttons follow the primary fill (existing rule).
- Respect `prefers-reduced-motion` (existing rule covers new transitions).
- Ship to test `:8001` first (`npm run build -- --outDir ../instances/test/dist`). Never build into production dist. Production only on user's go.
- Work on a new branch `feat/orange-console` cut from `main`.

## Review Focus

- Orange fill with text: dark text `#0f0f10` on `#f97316` (≈7:1). White text on that orange fails (≈2.8:1) — any `text-white` child inside a `.bg-blue-600` button must still read; check visually.
- Page search with a Thai query that matches only a hint, not a label (e.g. "หมวกกันน็อก" → กล้อง AI). Test in Task 3.
- Page search with empty / whitespace query: no dropdown, Enter does nothing. Test in Task 3.
- Light mode: yellow status text on white must use the dark yellow `#854d0e`, not `#facc15`.
- Pages reached only from home (`air`, `district`) appear in search results. Test in Task 3.

---

### Task 0: Branch

- [ ] **Step 1:** `git switch main && git switch -c feat/orange-console` (the uncommitted `launch/test/start.bat` change rides along; do not commit it).

### Task 1: Orange token palette

**Files:**
- Modify: `web/src/index.css` (`:root` block ~L72-100, `.dark` block ~L101-130, `.tone-yellow` ~L134, `:root:not(.dark)` slate remap ~L139-150, `.dark` Tailwind remap ~L247-285, dark text overrides ~L286-300, `.rounded-xl.border` radius rule ~L174)

**Interfaces:**
- Produces: new token `--c-glow` (box-shadow value) used by Task 2. All existing token names unchanged.

- [ ] **Step 1: Set light (`:root`) values**

| token | value |
|---|---|
| `--c-ground` | `#f7f7f8` |
| `--c-surface` | `#ffffff` |
| `--c-raised` | `#f1f1f3` |
| `--c-border` | `#e4e4e7` |
| `--c-border-strong` | `#d4d4d8` |
| `--c-ink` / `--c-line` | `#18181b` |
| `--c-muted` | `#52525b` |
| `--c-here`, `--c-primary` | `#c2410c` |
| `--c-here-text` | `#9a3412` |
| `--c-here-tint`, `--c-primary-tint` | `#fff1e6` |
| `--c-primary-fill` | `#f97316` |
| `--c-primary-hover` | `#ea580c` |
| `--c-on-primary` | `#0f0f10` |
| `--c-sel-bg` | `#18181b` |
| `--c-glow` | `0 6px 16px -8px rgba(234, 88, 12, 0.45)` |
| `--watch-ring` | `#ca8a04` |
| `--watch-fill`, `--watch-tint` | `#fef9c3` |
| `--watch-text` | `#854d0e` |

Light slate remap (`:root:not(.dark)`): zinc scale — 50 `#fafafa`, 100 `#f4f4f5`, 200 `#e4e4e7`, 300 `#d4d4d8`, 400 `#a1a1aa`, 500 `#71717a`, 600 `#52525b`, 700 `#3f3f46`, 800 `#27272a`, 900 `#18181b`. Legacy `--color-cream-*` / `--color-ink-*` in `@theme`: point at the same zinc values.

- [ ] **Step 2: Set dark (`.dark`) values**

| token | value |
|---|---|
| `--c-ground` | `#0f0f10` |
| `--c-surface` | `#18181b` |
| `--c-raised` | `#222226` |
| `--c-border` | `#2a2a2f` |
| `--c-border-strong` | `#3a3a40` |
| `--c-ink` / `--c-line` / `--c-sel-bg` | `#f4f4f5` |
| `--c-muted` | `#a1a1aa` |
| `--c-here`, `--c-here-text`, `--c-primary` | `#fb923c` |
| `--c-here-tint`, `--c-primary-tint` | `rgba(249, 115, 22, 0.14)` |
| `--c-primary-fill` | `#f97316` |
| `--c-primary-hover` | `#fb923c` |
| `--c-on-primary` | `#0f0f10` |
| `--c-sel-text` | `#0f0f10` |
| `--c-wave` | `#3a3a40` |
| `--c-glow` | `0 8px 22px -8px rgba(249, 115, 22, 0.55)` |
| `--watch-ring`, `--watch-text` | `#facc15` |
| `--watch-fill` | `rgba(250, 204, 21, 0.25)` |
| `--watch-tint` | `rgba(250, 204, 21, 0.12)` |
| `--none-tint` | `#222226` |

`.tone-yellow`: `--t-band: #facc15; --t-on: #18181b`.
Dark Tailwind remap: slate-50 `#222226`, 100 `#27272a`, 200 `#2a2a2f`, 300 `#3a3a40`; cream `#18181b`, cream-100 `#222226`, cream-200 `#2a2a2f`; ink-900 `#f4f4f5`, ink-600 `#a1a1aa`; amber/gold 50/100/200 → `#2a2410`, `#3a3213`, `#4d4316`. Dark text overrides: slate-700 `#d4d4d8`, slate-600 `#a1a1aa`, slate-500 `#a1a1aa`, amber-700..900 `#facc15`; `.dark svg text { fill: #a1a1aa }`; `hover:bg-slate-50/100` → `#27272a`; overlay rgba `(1,4,9,…)` → `(0,0,0,…)`. `.dark .text-blue-*` stays.

- [ ] **Step 3: Panel radius** — `.rounded-xl.border, .rounded-2xl.border { border-radius: 12px; }`.

- [ ] **Step 4: Verify** — `cd web && npm test` passes (no logic touched); `npm run build` succeeds; `grep -n "#0d1117\|#79c0ff\|#1f6feb\|#e3b341" web/src/index.css` returns only lines outside the token blocks (map, weather) or nothing.

- [ ] **Step 5: Commit** — `git add web/src/index.css && git commit -m "style(web): orange console palette, bright yellow watch status"`

### Task 2: Selected menu row and segmented tabs

**Files:**
- Modify: `web/src/components/Sidebar.jsx` (LogoMark L60, nav button classes L102-104, badge L107)
- Modify: `web/src/components/BottomNav.jsx` (active item colour only, if it uses `--c-raised` for selection)
- Modify: `web/src/index.css` (`.seg-pill`, `[role="tab"].seg-slide[aria-selected="true"]`, `.tab-pill`)

**Interfaces:**
- Consumes: `--c-primary-fill`, `--c-on-primary`, `--c-primary-hover`, `--c-glow` from Task 1.

- [ ] **Step 1: Sidebar selected row** — when `on`: `bg-[var(--c-primary-fill)] text-[var(--c-on-primary)] font-semibold shadow-[var(--c-glow)]`; icon has no extra colour class (inherits). Not selected: unchanged muted + `hover:bg-[var(--c-raised)]`. Row corner `rounded-lg`. Badge on selected row: `border-current text-[var(--c-on-primary)]`.
- [ ] **Step 2: Logo** — `LogoMark` stroke `text-[var(--c-primary)]`.
- [ ] **Step 3: Segmented tabs as chips** — `.seg-pill` and `.dark .seg-pill`: `background: var(--c-primary-fill); box-shadow: none;` `[role="tab"].seg-slide[aria-selected="true"] { color: var(--c-on-primary); }`. `.seg-on`: same fill and text.
- [ ] **Step 4: BottomNav** — selected item icon/label use `--c-primary` (orange text, no fill; bar is small).
- [ ] **Step 5: Verify** — `npm test` and `npm run build` pass. Build to test: `npm run build -- --outDir ../instances/test/dist`, open `http://localhost:8001`, check in dark and light: selected row orange with dark text, other rows muted, Tab focus ring visible.
- [ ] **Step 6: Commit** — `git commit -am "style(web): filled orange selected menu row and chip tabs"`

### Task 3: Desktop top bar with page search

**Files:**
- Create: `web/src/lib/pageSearch.js`
- Create: `web/src/lib/pageSearch.test.js`
- Create: `web/src/components/TopBar.jsx`
- Modify: `web/src/components/Sidebar.jsx` (export `PAGE_HINTS`)
- Modify: `web/src/App.jsx` (~L326, insert `<TopBar>` above `<main>` inside the right column)

**Interfaces:**
- Consumes: `NAV_GROUPS`, `PAGE_TITLES` from `Sidebar.jsx`.
- Produces:
  - `Sidebar.jsx`: `export const PAGE_HINTS` — `{ [id]: hint }` from `NAV_GROUPS`, plus `air: 'ค่าฝุ่น PM2.5 ตอนนี้'`, `district: 'ข่าวสารเขตที่คุณเลือก'`.
  - `pageSearch.js`: `searchPages(query: string, pages: {id,label,hint}[], limit = 6) -> {id,label,hint}[]` — trim + lowercase query; empty → `[]`; label match ranks before hint-only match; keeps input order within a rank.
  - `pageSearch.js`: `export const ALL_PAGES` — built from `PAGE_TITLES` + `PAGE_HINTS`, `[{id,label,hint}]`.
  - `TopBar.jsx`: `export default function TopBar({ page, onNavigate, liveCount, weatherScene })`.

- [ ] **Step 1: Write failing tests** (`pageSearch.test.js`)

```js
import { describe, it, expect } from 'vitest';
import { searchPages, ALL_PAGES } from './pageSearch.js';

const pages = [
  { id: 'water', label: 'น้ำท่วม', hint: 'ระดับน้ำ' },
  { id: 'yolo', label: 'กล้อง AI', hint: 'ตรวจคนไม่สวมหมวกกันน็อก' },
  { id: 'cameras', label: 'ดูกล้องสด', hint: 'ภาพสด' },
];

describe('searchPages', () => {
  it('empty or blank query returns nothing', () => {
    expect(searchPages('', pages)).toEqual([]);
    expect(searchPages('   ', pages)).toEqual([]);
  });
  it('matches label', () => {
    expect(searchPages('น้ำ', pages).map((p) => p.id)).toEqual(['water']);
  });
  it('matches hint only', () => {
    expect(searchPages('หมวกกันน็อก', pages).map((p) => p.id)).toEqual(['yolo']);
  });
  it('label matches rank before hint matches', () => {
    const r = searchPages('สด', [{ id: 'a', label: 'x', hint: 'สด' }, { id: 'b', label: 'สด', hint: '' }]);
    expect(r.map((p) => p.id)).toEqual(['b', 'a']);
  });
  it('is case-insensitive for latin text', () => {
    expect(searchPages('ai', pages).map((p) => p.id)).toEqual(['yolo']);
  });
  it('respects limit', () => {
    expect(searchPages('ก', pages, 1)).toHaveLength(1);
  });
  it('ALL_PAGES includes home-only pages air and district', () => {
    const ids = ALL_PAGES.map((p) => p.id);
    expect(ids).toContain('air');
    expect(ids).toContain('district');
  });
});
```

- [ ] **Step 2:** `cd web && npx vitest run src/lib/pageSearch.test.js` — Expected: FAIL (module not found).
- [ ] **Step 3: Implement** `PAGE_HINTS` in `Sidebar.jsx` and `searchPages` / `ALL_PAGES` in `pageSearch.js`.
- [ ] **Step 4:** Re-run — Expected: 7 passed.
- [ ] **Step 5: Implement `TopBar.jsx`**
  - Wrapper: `hidden lg:flex sticky top-0 z-30 h-16 items-center gap-4 px-6 bg-[var(--c-ground)]/90 backdrop-blur border-b border-[var(--c-border)]`.
  - Left: `<h1>` page title `PAGE_TITLES[page]`, `text-xl font-bold`.
  - Centre: search combobox, `max-w-md flex-1`, rounded-lg, `bg-[var(--c-surface)] border-[var(--c-border)]`, magnifier SVG icon (`aria-hidden`), `<input type="search" role="combobox" aria-expanded aria-controls="page-search-list" aria-activedescendant aria-label="ค้นหาหน้า" placeholder="ค้นหาหน้า เช่น น้ำท่วม กล้อง">`, `min-h-11`.
  - Results: `<ul id="page-search-list" role="listbox">` under input, each `<li role="option" aria-selected>` shows label (bold) + hint (muted, truncate). Highlighted option uses `bg-[var(--c-primary-tint)]`.
  - Keys: ArrowDown/ArrowUp move highlight (wrap); Enter navigates to highlighted (default first) result; Escape clears query and closes. Click on option navigates. After navigate: clear query, blur. Close on outside blur (`onBlur` with `setTimeout` 120 ms so click lands). No results with non-empty query: one muted row "ไม่พบหน้านี้".
  - Right: when `liveCount > 0` a text button "ดูสด {n} กล้อง" → `onNavigate('cameras')`; then `<WeatherBadge scene={weatherScene} />`; then `<ThemeToggle />`.
- [ ] **Step 6: Mount in App.jsx** — inside the right column `div` (L327) as first child, before `<main>`: `<TopBar page={page} onNavigate={navigate} liveCount={activeCams.length} weatherScene={weather.scene} />`. Change that column's `pt-4` to `lg:pt-0 pt-4` and give `<main>` `lg:pt-4`.
- [ ] **Step 7: Verify** — `npm test` all pass; `npm run build -- --outDir ../instances/test/dist`; on `http://localhost:8001` at 1440px: type "หมวก" → กล้อง AI listed, ArrowDown+Enter opens it; Escape closes; at 390px width top bar hidden, mobile bar unchanged, no horizontal scroll.
- [ ] **Step 8: Commit** — `git add web/src && git commit -m "feat(web): desktop top bar with page search"`

### Task 4: Record the design

**Files:**
- Modify: `DESIGN.md` (front-matter colours, `rounded.panel: 12px`, description of selected row / glow, watch yellow)

- [ ] **Step 1:** Update front-matter colour values to Task 1 tables (rename `action-*` values to orange; `watch-dark: "#facc15"`, light watch values), `rounded.panel: "12px"`, and the prose: selected menu row is filled orange with dark text and a soft orange glow; orange only marks action / selected.
- [ ] **Step 2: Commit** — `git commit -am "docs: DESIGN.md orange console"`
