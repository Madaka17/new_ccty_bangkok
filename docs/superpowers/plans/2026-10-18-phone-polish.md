# Phone Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Four phone fixes on the public site (bkksmartstreet.com):
1. The floating "ฉุกเฉิน" and AI buttons get out of the way while reading.
2. Pop-up alerts stop covering the header.
3. The weather effects become visible.
4. The dashboard stops asking for location on every visit.

**Architecture:**
- A shared `useScrollDirection()` hook hides the two floating buttons on phones while scrolling down.
- `AlertPopups` moves above the bottom nav on phones and closes after 8 s.
- The weather layer gains a sky band in the header and a faint rain overlay above the cards.
- `CityStatusStrip` asks for location only on a tap, or uses it silently when the permission is already granted.

**Tech Stack:** React 18, Tailwind 4, framer-motion (already used), vitest. Web-only: no backend change, so no restart.

**Spec:** the user's request 2026-10-18 ("ทำข้อ 1-4"), with these decisions:
- (1) Hide on scroll down, show on scroll up; phones only; slightly smaller.
- (2) On phones, above the bottom nav, auto-close in 8 s (severe alerts stay); desktop stays top-right.
- (3) The header turns into a sky, plus faint rain across the cards.
- (4) Ask only when tapped; if already granted, use it without asking.

## Global Constraints

- **Phone breakpoint:** below `lg` (1024 px), the same breakpoint the site already uses for the bottom nav. The desktop look stays unchanged except for the sky band in the sidebar header (item 3).
- **Floating buttons:** never hidden while a dialog they opened is open. Always shown at the top of the page (`scrollY < 80`). Shown again 1.2 s after scrolling stops. On phones they shrink to 48 px (`h-12 w-12`; the AI face inside scales with them). Positions keep `env(safe-area-inset-bottom)`. The transition is `transform`/`opacity` only, and under reduced motion they simply stay visible.
- **Pop-ups:** on phones, the container sits at `bottom: calc(72px + env(safe-area-inset-bottom))` with `left-3 right-3`, so the newest card is nearest the thumb. Desktop stays `top-4 right-4 sm:w-96`. `HIDE_MS` becomes 8000. Level-2 alerts still stay until closed.
- **Rain overlay:** only for rain/storm, only when `allowed`.
  - The layer is `pointer-events: none`, `aria-hidden`, z-index above `main` but below the top bar, bottom nav, pop-ups and dialogs (use `z-30`; the bottom nav and top bar are `z-40`).
  - Streaks are at most 0.18 opacity in dark and 0.14 in light, at half the background drop count. Text must stay readable.
  - Lightning stays in the background layer only, never over the content.
- **Sky band:**
  - Phone: the sticky top bar (App.jsx ~line 287).
  - Desktop: the sidebar brand header.
  - Gradient per scene, ≤ 30 % strength, so the text there keeps contrast in both themes:
    - rain: slate-blue;
    - storm: darker slate with a faint violet;
    - cloudy: grey;
    - sunny: warm amber-to-sky;
    - cool: icy blue;
    - clear: no change.
  - It shows even when effects are off, because it is colour, not motion. Any motion inside it obeys `allowed`.
- **Location:** never call `getCurrentPosition` on load.
  - If `navigator.permissions.query({name:'geolocation'})` is `granted`, read the position silently.
  - Otherwise show the Bangkok weather, with a small text button `ใช้ตำแหน่งของฉัน` under the weather answer that asks on tap.
  - Round to 2 decimals, as today.
- **Copy and commits:** plain Thai only. No new dependencies. Never build into `instances/production/dist`. Never start, stop or restart servers. Commits end with a Co-Authored-By trailer.

## Review Focus

1. **Momentum scroll on iOS.** Many scroll events, but the buttons do not flicker: there is a threshold of 8 px of movement before the direction changes. Test the hook's pure core.
2. **A pop-up and the floating buttons together.** On phones the pop-up stack sits above the bottom nav and must not sit under the floating buttons. The buttons hide while a pop-up is open on phones, or the pop-ups leave a 72 px right margin. Choose one and document it.
3. **Permission API missing** (older Safari). Then nothing is read silently and the tap button shows.
4. **Rain overlay with reduced motion or effects turned off.** Nothing renders.

---

### Task 1: Floating buttons, pop-ups, location (items 1, 2, 4)

**Files:**
- Create: `web/src/lib/scrollDirection.js` (pure `nextVisibility(prev, {y, lastY, now, lastMoveAt}) -> boolean` plus the `useScrollDirection()` hook) and `web/src/lib/scrollDirection.test.js`
- Modify:
  - `web/src/components/EmergencyButton.jsx` (~line 264)
  - `web/src/App.jsx` (AI button ~line 425)
  - `web/src/components/AlertPopups.jsx` (`HIDE_MS`, container ~line 116)
  - `web/src/components/dashboard/CityStatusStrip.jsx` (weather effect ~lines 86-105 and the weather item)

**Visibility rules for `nextVisibility`:**
- Visible if `y < 80`.
- Hidden if it moved down by ≥ 8 px since `lastY`.
- Visible if it moved up by ≥ 8 px.
- Visible if `now - lastMoveAt >= 1200`.
- Otherwise keep `prev`.

- [ ] **Step 1:** Write the failing tests for `nextVisibility`: top of the page; down 20 px hides; down 4 px keeps; up 10 px shows; idle 1.3 s shows.
- [ ] **Step 2:** Run `npm test -- scrollDirection`. Expected: FAIL. Then implement and run again. Expected: PASS.
- [ ] **Step 3:** Wire the buttons (phone only) and the pop-ups, and change the location flow per Global Constraints.
- [ ] **Step 4:** Run `npm test` and `npx vite build --outDir ../instances/test/dist`. Commit `fix(phone): floating buttons hide on scroll, pop-ups above the nav, location on tap`.

### Task 2: Sky band and rain overlay (item 3)

**Files:**
- Modify:
  - `web/src/components/fx/WeatherFx.jsx`: add `WeatherSky` (band) and `WeatherOverlay` (rain over the cards).
  - `web/src/App.jsx`: render the overlay, and the sky in the phone top bar.
  - `web/src/components/Sidebar.jsx`: sky in the brand header.
  - `web/src/index.css`.
- Consumes: the `scene` and `allowed` values already returned by `useWeatherScene()`.

- [ ] **Step 1:** Implement per Global Constraints. Reuse the existing drop generation (no copy-paste: extract a helper if needed).
- [ ] **Step 2:** Run `npm test` and `npx vite build --outDir ../instances/test/dist`. Commit `feat(fx): weather sky in the header and faint rain over the cards`.

### Task 3: Check and deploy (controller)

- [ ] Take CDP 360×800 and 1366×800 screenshots with `?fx=heavyrain`, `?fx=storm`, `?fx=sunny` and `?fx=clear`, in light and dark. Scroll the page and check the buttons hide and come back, and that there is no horizontal scroll.
- [ ] Merge to main, deploy web-only, then commit and push.
