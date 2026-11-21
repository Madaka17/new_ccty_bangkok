# Light Dashboard Theme Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Light mode becomes a white, rounded admin-dashboard look (sky-blue active pill, soft shadows, pastel backdrop); dark mode stays the orange console. The app shell (sidebar, top bar, frame) changes on every page, and the overview page gets template-style cards.

**Architecture:** Colours stay in the `--c-*` tokens of `web/src/index.css`; light values move to the sky palette and new tokens add the backdrop, card shadow and chart series colours. Shell components read only tokens, so dark mode keeps its orange look. Pure data shaping for the new overview cards lives in `web/src/lib/overviewData.js` (unit-tested with vitest); the cards are small components in `web/src/components/dashboard/overview/`.

**Tech Stack:** React 18, Tailwind v4 (CSS-first `@theme`), Vite 5, vitest. No new dependencies (charts are hand-drawn SVG as in `TrendChart.jsx`).

**Spec:** user's template screenshot (white rounded frame, sidebar with sky pill + badges + collapsible groups + round "+" button + dark-mode switch, top bar with search / bell / avatar chip, segmented time filter + Download, bar chart with two series + legend + tooltip, 4 KPI cards with chips, line chart with two series, "recent" table with thumbnails and sortable headers). Decisions 2026-11-21: light mode = new look, dark = orange console kept; shell on every page + overview page only.

## Global Constraints

- Every visible text in short plain Thai; no codes, units like ลบ.ม./วินาที, model names or English labels. Use the site words: ติดขัด / ชะลอตัว / คล่องตัว, "สด", "คนแจ้ง".
- Never copy the template's brand, logo or name ("WunderUI"); keep the BKK StreetSmart name and skyline mark.
- No raw hex in components: use `var(--c-*)` tokens (new ones below). Text contrast ≥ 4.5:1 in both modes.
- Light tokens (exact): `--c-backdrop: linear-gradient(135deg,#eef3fb 0%,#f3effa 55%,#fbeff5 100%)`, `--c-ground:#f6f8fc`, `--c-surface:#ffffff`, `--c-raised:#f1f4f9`, `--c-border:#e7ebf2`, `--c-border-strong:#d5dbe6`, `--c-ink:#1e2433`, `--c-muted:#5b6475`, `--c-primary:#0a72b5`, `--c-primary-fill:#0b7bc0`, `--c-primary-hover:#0a6aa6`, `--c-primary-tint:#e3f3fd`, `--c-on-primary:#ffffff`, `--c-here*` = same sky values, `--c-glow: 0 8px 18px -8px rgba(11,123,192,.45)`, `--c-card-shadow: 0 1px 2px rgba(30,36,51,.04), 0 6px 20px -10px rgba(30,36,51,.12)`, `--c-series-a:#8b5cf6`, `--c-series-b:#ec4899`, `--c-chip-up-bg:#dcfce7`, `--c-chip-up-text:#15803d`, `--c-radius-card:16px`.
- Dark tokens: `--c-backdrop: var(--c-ground)`, `--c-card-shadow: none`, `--c-series-a:#a78bfa`, `--c-series-b:#f472b6`, `--c-chip-up-bg: rgba(86,211,100,.12)`, `--c-chip-up-text:#56d364`, `--c-radius-card:12px`; every other dark token unchanged.
- Touch targets ≥ 44px; visible focus; `prefers-reduced-motion` respected; layout works at 375px with no horizontal page scroll.

## Review Focus

- No data yet (API down, empty history): every new card shows a plain Thai empty state, never `NaN` or a blank SVG.
- 30-day range with only a few days logged: bars for missing days are zero-height, labels still readable (thin out labels when > 12 bars).
- Dark mode: new cards use tokens only, so they keep the orange-console look (no white cards in dark).
- Phone width 375px: toolbar wraps, chart scrolls inside its card or shrinks, table becomes a list without sideways page scroll.
- Sidebar collapsed group containing the current page stays open.

---

### Task 1: Tokens and app frame

**Files:** Modify `web/src/index.css`, `web/src/App.jsx`.

- [ ] Add the light/dark tokens above to `:root` / `.dark` (replace the light orange values; dark keeps orange). Add classes: `.app-backdrop { background: var(--c-backdrop); }` on `body` in light mode; `.dash-card { background: var(--c-surface); border: 1px solid var(--c-border); border-radius: var(--c-radius-card); box-shadow: var(--c-card-shadow); }`; in light mode `.rounded-xl.border, .rounded-2xl.border` get `border-radius:14px; box-shadow: var(--c-card-shadow)` (cards site-wide get the soft look; dark rule unchanged).
- [ ] `App.jsx` desktop (lg+): outer `div` gets `lg:p-4` and the backdrop; the grid becomes a frame: `lg:rounded-[22px] lg:bg-[var(--c-ground)] lg:border lg:border-[var(--c-border)] lg:shadow-[var(--c-card-shadow)] lg:overflow-clip lg:min-h-[calc(100vh-2rem)]`; sidebar `aside` sticky with `top-4 h-[calc(100vh-2rem)]`; grid columns `248px_1fr`. Phone layout unchanged except the page background token.
- [ ] Verify: `npx vite build` in `web/` succeeds; `npx vitest run` passes. Commit `feat(web): light dashboard tokens and app frame`.

### Task 2: Sidebar

**Files:** Modify `web/src/components/Sidebar.jsx`, `web/src/components/ThemeToggle.jsx`.

**Interfaces:** Sidebar props add `onReport: () => void` (App passes `openFloodReport`) and `alertCount: number`.

- [ ] Brand header: no bottom seam, `h-20`, mark in a 36px rounded-xl tile filled `--c-primary-fill` with `--c-on-primary` stroke.
- [ ] Groups: each group label is a button (chevron right/down, `aria-expanded`) that collapses its list; open state per group label kept in `localStorage` key `nav-groups-closed` (JSON array of closed labels, wrapped in try/catch); a group holding the current page is always open. Items in groups after the first are indented `pl-5` with a 1px left guide line (`border-l border-[var(--c-border)] ml-5`).
- [ ] Active row: filled pill `rounded-xl bg-[var(--c-primary-fill)] text-[var(--c-on-primary)] shadow-[var(--c-glow)]`. Count badges: `alerts` shows `alertCount` when > 0 in a pink pill (`bg-[var(--c-series-b)] text-white` for light; same token in dark), `cameras` shows live count in a grey pill (`bg-[var(--c-raised)]`).
- [ ] Footer: round 40px "+" button filled `--c-primary-fill` with label "แจ้งน้ำท่วม" (calls `onReport`, then `onClose?.()`); below it a row "โหมดมืด" with a switch: add `ThemeToggle` prop `variant="switch"` that renders `role="switch" aria-checked={theme==='dark'}` track 40×22 px, knob moves; whole row is the hit target (min-h-11). Weather badge and weather toggle stay.
- [ ] Verify build; commit `feat(web): dashboard-style sidebar`.

### Task 3: Top bar

**Files:** Modify `web/src/components/TopBar.jsx`, `web/src/App.jsx` (pass props).

**Interfaces:** TopBar props add `alertCount: number`, `district: string|null` (from `readMyDistrict()` in `lib/district.js`).

- [ ] Bar background `--c-ground` (no blur seam in light: `border-b` only in dark via `dark:border-b`), search field `rounded-xl bg-[var(--c-raised)] border-transparent`, placeholder "ค้นหาหน้า".
- [ ] Right side: bell button (44px, `aria-label="ประกาศเตือน"`, navigates to `alerts`, red dot when `alertCount > 0`), theme toggle, then avatar chip button (navigates to `district`): 36px circle `bg-[var(--c-primary-tint)] text-[var(--c-primary)]` with the first Thai letter of the district (or skyline icon when none), name = district or "เลือกเขตของฉัน", second line "เขตของฉัน" in `text-xs text-[var(--c-muted)]`.
- [ ] Verify build; commit `feat(web): top bar with bell and my-district chip`.

### Task 4: Overview data helpers

**Files:** Create `web/src/lib/overviewData.js`, `web/src/lib/overviewData.test.js`.

**Interfaces (produces):**
- `sumVehicleHistory(history) -> [{key, label, cars, motorcycles}]`: input is `/api/ai/history` JSON `{bucket:'hour'|'day', keys:[...], cameras:[{series:{[key]:{cars,motorcycles,trucks,total}}}]}`; sums across cameras per key in `keys` order; label = `HH` + ' น.' for hour keys (`'2026-11-21T08:00'` → `'08 น.'`) and `D/M` for day keys (`'2026-11-21'` → `'21/11'`). Missing/empty input → `[]`.
- `bmaHourlyLines(hourly) -> [{t, label, cars, motorcycles}]`: input `bma.hourly_trends` rows `{hour, cars, motorcycles, cam_count}`; values are per camera (`Math.round(x / max(1, cam_count) * 10) / 10`).
- `incidentRows(incidents) -> [{id, title, kind, source, image, at}]`: merges `incidents.camera` and `incidents.longdo`; `at` = epoch seconds (`ts` for camera; `start` 'YYYY-MM-DD HH:MM:SS' parsed as local time for longdo; null if missing).
- `sortRows(rows, key, dir) -> new array` (`dir` 'asc'|'desc'; nulls last).
- `toCsv(rows, columns) -> string`: columns `[{key, label}]`, header line of labels, values quoted when they contain comma/quote/newline, `\r\n` line ends, prefixed with BOM `﻿` so Excel reads Thai.

- [ ] Write tests first covering: summing two cameras, hour and day labels, empty input, per-camera rounding, longdo time parsing, null-last sorting both directions, CSV quoting + BOM. Run `npx vitest run src/lib/overviewData.test.js` → FAIL, implement, → PASS. Commit `feat(web): overview data helpers`.

### Task 5: Overview cards on the dashboard

**Files:** Create in `web/src/components/dashboard/overview/`: `TimeRangeToolbar.jsx`, `VehicleBarCard.jsx`, `KpiCards.jsx`, `BmaLineCard.jsx`, `RecentIncidentsTable.jsx`. Modify `web/src/components/DashboardPage.jsx`.

**Interfaces:** consumes Task 4 helpers, `fetchAIHistory({range})` from `lib/api.js`, `fmtNum`/`fmtDateTime`/`agoText` from `dashboard/format.js`, `flowLevel` from `dashboard/format.js`.

- [ ] `TimeRangeToolbar({range, onRange, onDownload, extra})`: segmented `role="tablist"` group in a white rounded-xl tray, options `24h`→"24 ชั่วโมง", `7d`→"7 วัน", `30d`→"30 วัน"; selected = white pill with soft shadow in light / `--c-sel-bg` in dark; right side "ดาวน์โหลด" button (download icon) and the `extra` slot (district button, refresh).
- [ ] `VehicleBarCard({range})`: loads `fetchAIHistory({range})` on range change; title "รถที่ผ่านกล้อง AI", legend top-right (dots `--c-series-a` "รถยนต์", `--c-series-b` "มอเตอร์ไซค์"); SVG grouped thin rounded bars (width 6, gap 3) per bucket, 4 gridlines with values, x labels under bars (show every Nth when > 12); hover/focus a bucket shows a tooltip card (label + both values); bars are keyboard-focusable via a transparent `<rect tabIndex=0>` per bucket with `aria-label`. Exposes its rows upward through `onRows(rows)` for the CSV download. Loading skeleton; empty state "ยังไม่มีข้อมูลรถในช่วงนี้".
- [ ] `KpiCards({bkkFlow, incidentCount, floodCount, online})`: 4 `dash-card` tiles: "คะแนนจราจร กทม." (`bkkFlow`/100, chip = `flowLevel(bkkFlow).label` toned), "อุบัติเหตุและรถเสีย" (count, chip "ตอนนี้"), "ถนนน้ำท่วม" (count from `flood.counts.flood + flood.counts.slight`, chip "ไม่มี" green when 0), "คนดูอยู่ตอนนี้" (online, chip "สด" green). Big number `text-[28px] font-bold num`, label `text-xs text-[var(--c-muted)]`, chip rounded-full `bg-[var(--c-chip-up-bg)] text-[var(--c-chip-up-text)]` for good states, `tone-*` tint for others. Each tile clickable → `onNavigate` (`map`, incidents tab via `onIncidents`, `water`, `visitors`). `grid-cols-2 lg:grid-cols-4`.
- [ ] `BmaLineCard({hourly})`: title "รถเฉลี่ยต่อกล้อง กทม.", big latest total under the title, two smooth lines (`--c-series-a` รถยนต์, `--c-series-b` มอเตอร์ไซค์), hover crosshair + tooltip, empty state.
- [ ] `RecentIncidentsTable({incidents, onOpen})`: title "เหตุบนถนนล่าสุด"; columns เหตุ (thumbnail 36px rounded-lg image or kind icon tile + title), ประเภท (chip อุบัติเหตุ red / รถเสีย yellow), แหล่ง (กล้อง AI / ข่าวจราจร), เวลา (`agoText`); headers ประเภท/เวลา are sort buttons with `aria-sort`; max 6 rows; below md it renders as a stacked list. Empty: "ตอนนี้ไม่มีเหตุบนถนน". Row click → `onOpen()` (opens the incidents tab).
- [ ] `DashboardPage`: replace the md header actions with `TimeRangeToolbar` (extra = DistrictButton + รีเฟรช + online stays in KPI); order: header → toolbar → `VehicleBarCard` → `KpiCards` → grid `lg:grid-cols-[3fr_2fr]` with `BmaLineCard` + `RecentIncidentsTable` → existing `CityStatusStrip` and the rest unchanged. Download = CSV of the bar rows via Task 4 `toCsv` (columns ช่วงเวลา, รถยนต์, มอเตอร์ไซค์), file `bkk-vehicles-<range>.csv` via Blob + temporary `<a download>`.
- [ ] Verify build + tests; commit `feat(web): template-style overview cards`.
