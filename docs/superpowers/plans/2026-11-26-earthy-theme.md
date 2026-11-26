# Earthy Theme Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-skin the whole BKK StreetSmart web UI in the look of the Wix "Non-Profit Organization (Earthy)" template (cream ground, forest-green ink and actions, large serif headings, pill buttons, full-bleed photo hero), in light and dark mode, without changing any page's data or layout logic.

**Architecture:** The site is token-driven (`--c-*` CSS variables plus Tailwind colour remaps in `web/src/index.css`), so most of the re-skin is new token values. One new component, `HeroBanner`, adds the template's photo hero to the top of the overview page. Fonts come from Google Fonts in `web/index.html`.

**Tech Stack:** React 18, Tailwind CSS v4 (`@theme`, `@custom-variant dark`), Vite 5, vitest.

**Spec:** User request 2026-11-26 (Thai): "อยากได้ template นี้" for https://www.wix.com/website-template/view/html/wh-1062, test server :8001 first. Answers: re-skin the whole site (not a separate landing page); make dark mode earthy too; hero photo = free Bangkok photo stored in the project. Reference screenshots: template captured headless at 1440 px.

## Global Constraints

- Work only in the worktree `E:\new_ccty_bangkok-earthy` (branch `feat/earthy-theme`). Never `git checkout` in `E:\new_ccty_bangkok`.
- Template palette (light): cream `#fffaf0`, white `#ffffff`, ink `#052812`, action green `#24582a`, muted `#5d7365`, sage tint `#e6eae7`, hairline `#b4bfb8`.
- Template type: display serif = **Fraunces** (light/regular weights) for Latin and digits, **Noto Serif Thai** for Thai glyphs in the same stack: `"Fraunces", "Noto Serif Thai", ui-serif, Georgia, serif`. Body stays **Noto Sans Thai Looped**; figures stay **JetBrains Mono** (`.num`).
- All text at least 4.5:1 contrast on its background in both modes (large hero text at least 3:1 on the photo overlay).
- Status colours keep their meaning: ok = green, watch = yellow, act = red, none = grey. Blue stays only for water data (`--color-blue-*` remap is not changed).
- All UI copy is short plain Thai (no English labels in the UI except the brand name "BKK StreetSmart").
- Hero photo: `web/public/hero/benjakitti-1920.webp` and `benjakitti-960.webp` (already in the worktree). Credit must be visible: `ภาพ: Supanut Arunoprayote (CC BY 4.0)` linking to `https://commons.wikimedia.org/wiki/File:Benjakitti_Forest_Park_(I).jpg`.
- No new npm dependencies. `prefers-reduced-motion` must turn off any new motion.

## Review Focus

- Phone width 360 px: the hero title must wrap without overflow and the hero must not push the status strip below the first screen (hero max 240 px tall on phones).
- Dark mode: every hard-coded zinc value in the `.dark` block of `index.css` (`#27272a`, `#d4d4d8`, `#a1a1aa`, `#ffffff` hover text, `svg text` fill) must move to the green-tinted dark set, or dark pages show grey islands.
- Primary action green and the "ok" status green sit near each other: selected/active fills use `--c-primary-fill`; ok keeps `#1a7f37` ring/text. Both must stay distinguishable (fill vs ring).
- Thai serif at small sizes: serif only on h1/h2 and the hero; h3 and smaller stay sans so dense cards remain readable.
- Image load: the hero must reserve its height (no layout shift) and use `srcset` so phones fetch the 960 px file.

---

### Task 1: Earthy tokens and fonts

**Files:**
- Modify: `web/index.html` (Google Fonts link)
- Modify: `web/src/index.css` (`@theme` fonts, `:root`, `.dark`, `:root:not(.dark)` slate remap, `.dark` utility overrides, `h1, h2, h3` rule, body backdrop)

**Interfaces:**
- Produces: CSS variables used by Task 2: `--font-display`, `--c-primary-fill`, `--c-on-primary`, `--c-ground`, `--c-ink`, `--c-muted`, `--c-border`; new utility class `.font-serif-display` (= `font-family: var(--font-display)`).

- [ ] **Step 1: Fonts.** In `web/index.html` extend the existing Google Fonts URL with `family=Fraunces:opsz,wght@9..144,300;9..144,400;9..144,500` and `family=Noto+Serif+Thai:wght@400;500;600` (keep the current families and `display=swap`). In `@theme` set `--font-display: "Fraunces", "Noto Serif Thai", ui-serif, Georgia, serif;` (leave `--font-sans` and `--font-mono`).

- [ ] **Step 2: Light tokens (`:root`).** Set exactly:
  `--c-backdrop: #fffaf0; --c-ground: #fffaf0; --c-surface: #ffffff; --c-raised: #f6f1e4; --c-border: #e8e1cf; --c-border-strong: #b4bfb8; --c-ink: #052812; --c-muted: #5d7365; --c-line: #052812; --c-here: #24582a; --c-here-tint: #e6eae7; --c-here-text: #24582a; --c-primary: #24582a; --c-primary-fill: #24582a; --c-primary-hover: #1c4521; --c-primary-tint: #e6eae7; --c-on-primary: #ffffff; --c-wave: #d3ccb8; --c-glow: 0 8px 18px -10px rgba(36, 88, 42, 0.45); --c-shadow: 0 1px 0 rgba(5, 40, 18, 0.04); --c-card-shadow: 0 1px 2px rgba(5, 40, 18, 0.04), 0 8px 24px -14px rgba(5, 40, 18, 0.16); --c-radius-card: 14px;`
  Leave `--c-yours*`, `--c-series-*`, `--c-chip-up-*` and all `--ok/--watch/--act/--none-*` as they are.

- [ ] **Step 3: Light neutrals.** In `:root:not(.dark)` replace the zinc slate remap with warm green-grey: slate-50 `#fbf8ef`, 100 `#f3efe3`, 200 `#e6e0cf`, 300 `#d3ccb8`, 400 `#a3ab9f`, 500 `#5d7365`, 600 `#4f6657`, 700 `#34503d`, 800 `#1d3a26`, 900 `#052812`. Also map the legacy `--color-cream*` / `--color-ink-*` in `@theme` to the same family (cream `#ffffff`, cream-100 `#f3efe3`, cream-200 `#e6e0cf`, cream-300 `#d3ccb8`, ink-900 `#052812`, ink-600 `#4f6657`, ink-400 `#a3ab9f`).

- [ ] **Step 4: Dark tokens (`.dark`).** Set exactly:
  `--c-ground: #0b1a10; --c-surface: #11241a; --c-raised: #183022; --c-border: #22392b; --c-border-strong: #33503e; --c-ink: #f6f1e4; --c-muted: #b4bfb8; --c-line: #f6f1e4; --c-here: #9fd3a6; --c-here-tint: rgba(125, 190, 135, 0.16); --c-here-text: #9fd3a6; --c-primary: #9fd3a6; --c-primary-fill: #7dbe87; --c-primary-hover: #93cc9b; --c-primary-tint: rgba(125, 190, 135, 0.16); --c-on-primary: #052812; --c-wave: #33503e; --c-glow: 0 8px 22px -10px rgba(125, 190, 135, 0.5); --c-radius-card: 14px;` and `--none-tint: #183022`. Keep the dark ok/watch/act values.

- [ ] **Step 5: Dark utility overrides.** In the `.dark { ... }` slate remap block and the per-utility overrides that follow it, replace every zinc literal with the green-tinted set: surfaces `#27272a`→`#1f3a29`, text `#d4d4d8`→`#ddd6c4`, `#a1a1aa`→`#b4bfb8`, hover text `#ffffff`→`#fffaf0`, `.dark svg text { fill: #b4bfb8; }`. Run `grep -nE "#(27272a|3f3f46|52525b|71717a|a1a1aa|d4d4d8|e4e4e7|f4f4f5|18181b|0f0f10)" web/src/index.css` — expected afterwards: no hits inside `.dark` rules (hits elsewhere only in `.tone-*` band colours are fine).

- [ ] **Step 6: Type and ground.** `h1, h2 { font-family: var(--font-display); font-weight: 500; letter-spacing: -0.01em; }` and `h3 { font-family: var(--font-sans); }` (replace the current `h1, h2, h3` rule). Add `.font-serif-display { font-family: var(--font-display); }`. Light body: flat cream (`background: var(--c-backdrop)` already does it; remove `background-attachment: fixed` only if the backdrop is no longer a gradient).

- [ ] **Step 7: Verify.** In `web/`: `npx vite build --outDir ../local/earthy-check` → exits 0; `npx vitest run` → same pass count as on `main` (run it on main first if unsure); `npx eslint src` → no new errors.

- [ ] **Step 8: Commit** `feat(theme): earthy palette and serif headings (light and dark)`.

### Task 2: Photo hero on the overview page, pill buttons

**Files:**
- Create: `web/src/components/dashboard/HeroBanner.jsx`
- Modify: `web/src/components/DashboardPage.jsx:205-231` (header area)
- Modify: `web/src/components/dashboard/ui.jsx` (`Button` corners)
- Modify: `web/src/index.css` (`.hero-*` rules)

**Interfaces:**
- Consumes: Task 1 tokens, `.font-serif-display`.
- Produces: `export default function HeroBanner({ onPrimary, children })` — `onPrimary()` is called by the hero button; `children` render in a row under the subtitle (optional).

- [ ] **Step 1: `HeroBanner`.** A `<section aria-labelledby="hero-title">` with:
  - `<img>` full-bleed cover: `src="/hero/benjakitti-1920.webp"`, `srcSet="/hero/benjakitti-960.webp 960w, /hero/benjakitti-1920.webp 1920w"`, `sizes="(min-width: 1024px) 1150px, 100vw"`, `alt=""` (decorative), `fetchpriority="high"`, `decoding="async"`, `object-cover`, absolutely positioned.
  - Overlay `linear-gradient(180deg, rgba(5,40,18,0.35) 0%, rgba(5,40,18,0.55) 60%, rgba(5,40,18,0.75) 100%)` so white text passes 4.5:1 for the subtitle.
  - Centred text block: `<h1 id="hero-title">` text `เช็กกรุงเทพฯ ก่อนออกจากบ้าน`, class `font-serif-display`, white, `text-3xl sm:text-5xl lg:text-6xl`, weight 400, `leading-tight`, `text-balance`; subtitle `<p>` `รถติด น้ำท่วม อุบัติเหตุ อัปเดตสดทุกนาที`, white/90, `text-sm sm:text-base`.
  - Outline pill button (template "Learn More"): `ดูสถานะตอนนี้`, `rounded-full border border-white/80 text-white px-6 min-h-11 hover:bg-white hover:text-[#052812] transition-colors duration-200 focus-visible:outline-2 focus-visible:outline-white`, `onClick={onPrimary}`.
  - Credit bottom-right, `text-[11px] text-white/80`: `<a href="https://commons.wikimedia.org/wiki/File:Benjakitti_Forest_Park_(I).jpg" target="_blank" rel="noopener noreferrer">ภาพ: Supanut Arunoprayote (CC BY 4.0)</a>`.
  - Size: `h-[220px] sm:h-[300px] lg:h-[360px]`, `rounded-[var(--c-radius-card)] overflow-hidden relative isolate`. Height is fixed so the image never shifts layout.

- [ ] **Step 2: Wire into `DashboardPage`.** Render `<HeroBanner onPrimary={...} />` as the first child of the page column, on all widths. `onPrimary` focuses and scrolls to the `CityStatusStrip` wrapper (give that wrapper `id="city-status"` and `tabIndex={-1}`; scroll with the existing reduced-motion pattern at lines ~199-202). The page `<h1>` now lives in the hero, so turn the existing `PageHeader` title into the time line only: keep `PageHeader` actions (district, refresh, online count) in a row under the hero; change the phone-only `<h1 className="sr-only">` to a `<p>`-free row (remove that sr-only h1, since the hero h1 exists). There must be exactly one `<h1>` on the page.

- [ ] **Step 3: Pill buttons.** In `ui.jsx` `Button`, change the corner class from `rounded-md`/`rounded-lg` to `rounded-full` for every variant (template buttons are pills). Do not touch `Badge` or `Card`.

- [ ] **Step 4: Verify.** Build as in Task 1 Step 7. Then in the build output `grep -c "benjakitti-960.webp" ../local/earthy-check/assets/*.js` → at least 1. `npx vitest run` and `npx eslint src` as before.

- [ ] **Step 5: Commit** `feat(overview): photo hero in the earthy template style`.

### Task 3: DESIGN.md

**Files:** Modify: `DESIGN.md` (front-matter colour list and the prose that names the orange/blue console).

- [ ] **Step 1:** Replace the colour tokens with the Task 1 values (light and dark), name the look "earthy" (cream ground, forest green action, Fraunces + Noto Serif Thai headings, pill buttons, photo hero on the overview with credit). Keep the status-colour rules and the "blue only for water" rule. Note the source: Wix template wh-1062, adopted 2026-11-26.
- [ ] **Step 2: Commit** `docs(design): earthy theme`.

### Task 4 (controller): test server and screenshots

- [ ] Build `npx vite build --outDir ../instances/test/dist_next` from the worktree's `web/` but with `outDir` pointing at `E:\new_ccty_bangkok\instances\test\dist_next`; swap into `instances\test\dist` (keep the old one as `dist_prev`).
- [ ] Start `launch\test\start.bat` if :8001 is down; check `http://localhost:8001/` answers 200.
- [ ] Headless Chrome screenshots at 1440 and 390 wide, light and dark; compare against the template capture.
