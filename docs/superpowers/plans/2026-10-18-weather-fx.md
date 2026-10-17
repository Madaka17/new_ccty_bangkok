# Weather Effects Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The whole site's background follows the weather now:
- rain falls when it rains;
- a storm adds soft lightning;
- the sky goes grey when it is cloudy;
- warm sunlight shows on a sunny day.

On top of any of these, a cool blue mist shows when it is cold (cool season), and pale streaks blow across when the wind is strong. Clear nights look as they do today.

A small badge in the header names the weather that matters. The effects turn themselves off for "reduce motion", low battery and data saver, and a button turns them off by hand.

**Architecture:**
- **Backend:** add wind speed to `/api/weather/now`.
- **Pure helpers** in `web/src/lib/weatherFx.js`: weather to scene, and whether the effects are allowed. Tested with vitest.
- **Hook** `useWeatherScene()`: polls `/api/weather/now` every 10 min. It uses the viewer's spot only if location permission is already granted, and never asks for it.
- **Component** `web/src/components/fx/WeatherFx.jsx`: a fixed layer just above `RiverBackdrop`, behind the content, never takes a tap. It is CSS-only animation.
- **Toggle** `WeatherFxToggle`: sits next to `ThemeToggle`.

**Tech Stack:** React 18, Tailwind 4, CSS keyframes in `web/src/index.css`, vitest; FastAPI/pytest for the backend field. No new dependencies.

`/api/weather/now` answers `{temp, humidity, rain_1h, symbol, text, tone, lat, lng, updated_at}`. `symbol` is a MET Norway code such as `lightrain`, `heavyrainshowers_day`, `rainandthunder`, `cloudy`, `fog`, `partlycloudy_night`, `clearsky_day` or `fair_day`.

**Spec:** the user's requests (2026-10-18): "ปรับ UI ตามสภาพอากาศ ถ้าฝนตกให้มี UI ฝนตก", then "ถ้าแดดออก แล้ว ตอนหน้าหนาว และมีลมแรง". Decisions:
- **States:** rain, storm, cloudy and sunny, plus cool and windy modifiers. The controller chose the thresholds: cool at temp ≤ 22 °C, windy at wind ≥ 8 m/s.
- **Place:** Bangkok, or the viewer's spot if already shared.
- **Where on the page:** the whole-site background plus a small header badge.
- **Off switch:** off automatically, plus a button.

## Global Constraints

- **Decoration only.** The layer is `pointer-events: none` and `aria-hidden="true"`, sits behind the content (below `main` in stacking order) and never covers text.
- **Badge text** is the only text, in plain Thai, picked in this order:
  - `ฝนฟ้าคะนอง` (storm)
  - `ฝนกำลังตก` (rain)
  - `ลมแรง` (windy)
  - `อากาศเย็น` (cool)
  - otherwise no badge.
- **Lightning is safe.** At most one flash per 8 s, never more than 3 flashes in any second. Peak opacity ≤ 0.35, never full white.
- **Effects are off when any of these holds:**
  - `prefers-reduced-motion: reduce`;
  - `navigator.connection.saveData`;
  - battery under 20 % and not charging (if `navigator.getBattery` exists);
  - the viewer turned them off. That choice is stored in `localStorage` key `weather-fx` (`'on'` / `'off'`), wrapped in try/catch.
- **Badge stays even when effects are off.** It is information.
- **Performance.** Only `transform`/`opacity` animations. Rain drop counts: light 40, moderate 80, heavy 140, halved below 640 px. Wind streaks: 16, halved below 640 px. All of them are generated once per scene, not per frame.
- **Themes.** Light and dark both read well, using colours from the existing tokens or rgba. Works at 360 px.
- **Preview override.** `?fx=` in the URL forces the scene (a comma list), e.g. `?fx=heavyrain`, `?fx=storm`, `?fx=sunny,windy`, `?fx=clear,cool`.
- **Location.** Never call `getCurrentPosition` unless `navigator.permissions.query({name: 'geolocation'})` says `granted`. Coordinates are rounded to 2 decimals.
- **Commits.** Messages end with a Co-Authored-By trailer. Never build into `instances/production/dist`. Never start, stop or restart servers.

## Review Focus

1. **Unknown or missing values.** A null `symbol`, `temp` or `wind_speed`, or an unknown code, gives `clear` with `cool` and `windy` false, never a crash. Test in Task 1.
2. **Rain amount beats the symbol.** `rain_1h >= 0.5` with a cloudy symbol gives rain, sized by the amount. Test in Task 1.
3. **Weather fetch fails.** The scene stays as the last good one (clear at first), with no badge flicker and no console error loop. Check in Task 2.
4. **Toggle persists,** and storage throwing does not break the page. Test in Task 1.
5. **Readable content** with heavy rain, sunny + windy and cool at 360 px in both themes. Controller check with CDP screenshots using `?fx=`.

---

### Task 0: Wind speed in the weather-now answer (backend)

**Files:**
- Modify: `backend/water/weather_now.py` (`get()`, ~line 102)
- Test: new `tests/test_weather_now.py`

`get()` adds `"wind_speed": inst.get("wind_speed")` (m/s, from MET Norway instant details). Nothing else changes.

- [ ] **Step 1: Write the failing test.** Monkeypatch `weather_now._series` (and `_place` if needed) to return one hand-made MET entry:
  - `instant.details = {air_temperature: 21.5, relative_humidity: 80, wind_speed: 9.2}`
  - `next_1_hours = {summary: {symbol_code: 'clearsky_day'}, details: {precipitation_amount: 0}}`

  Assert `get()["wind_speed"] == 9.2` and `get()["temp"] == 21.5`.
- [ ] **Step 2:** Run `E:\new_ccty_bangkok\.venv\Scripts\python.exe -m pytest tests/test_weather_now.py -q`. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the same command. Expected: PASS.
- [ ] **Step 5:** Commit `feat(weather): wind speed in the weather-now answer`.

### Task 1: Scene and permission helpers (pure)

**Files:**
- Create: `web/src/lib/weatherFx.js`, `web/src/lib/weatherFx.test.js`

**Interfaces (produces):**
- `weatherScene(now) -> { kind: 'clear'|'sunny'|'cloudy'|'rain'|'storm', intensity: null|'light'|'moderate'|'heavy', cool: boolean, windy: boolean }`. `now` is the `/api/weather/now` body or null. `cool` = `temp != null && temp <= 22`. `windy` = `wind_speed != null && wind_speed >= 8`.
- `forcedScene(search) -> scene | null`. Reads `?fx=` from a `location.search` string as a comma list.
  - `heavyrain` gives rain heavy, `rain` gives rain moderate, `storm` gives storm moderate.
  - `sunny`, `cloudy` and `clear` give that kind with intensity null.
  - `cool` and `windy` set those flags.
  - The kind defaults to clear. If nothing is recognised, it returns null.
- `fxAllowed({ pref, reducedMotion, saveData, battery }) -> boolean`. `battery` is `{level, charging}` or null. Returns false if `pref === 'off'`, if `reducedMotion`, if `saveData`, or if `battery && battery.level < 0.2 && !battery.charging`. Otherwise true.
- `readPref(storage = localStorage) -> 'on'|'off'` (default `'on'`, and `'on'` if storage throws). `writePref(value, storage = localStorage)` never throws.
- `badgeText(scene) -> string`: the priority from Global Constraints.
- `dropCount(intensity, narrow) -> number`: 40 / 80 / 140 for light / moderate / heavy, halved (rounded down) when `narrow`, and 0 for null.

**Rules for `weatherScene` kind** (first match wins). `s` is the symbol in lower case, `r` is `rain_1h`.
1. `s` contains `thunder` → storm. Intensity heavy if `s` contains `heavy` or `r >= 4`, else moderate.
2. `s` contains `rain`, or `r >= 0.5` → rain. Intensity:
   - heavy if `s` contains `heavy` or `r >= 4`;
   - light if `s` contains `light` or (`r != null` and `r < 1`);
   - else moderate.
3. `s` starts with `cloudy` or `fog` → cloudy.
4. `s` starts with `clearsky_day`, `fair_day` or `partlycloudy_day` → sunny.
5. Otherwise → clear.

Non-rain kinds have intensity null. `cool` and `windy` apply to every kind.

- [ ] **Step 1: Write the failing tests:**
  - `{symbol:'lightrain', rain_1h:0.3}` is rain light.
  - `{symbol:'heavyrainshowers_day'}` is rain heavy.
  - `{symbol:'rain', rain_1h:2}` is rain moderate.
  - `{symbol:'rainandthunder'}` is storm moderate.
  - `{symbol:'heavyrainandthunder'}` is storm heavy.
  - `{symbol:'cloudy', rain_1h:5}` is rain heavy.
  - `{symbol:'fog'}` is cloudy.
  - `{symbol:'clearsky_day', temp:34}` is sunny with cool false.
  - `{symbol:'fair_day', temp:22.5, wind_speed:7.9}` is sunny with cool false and windy false.
  - `{symbol:'clearsky_night', temp:21, wind_speed:9}` is clear with cool true and windy true.
  - `null` and `{symbol:null}` are clear with both flags false.
  - `forcedScene('?fx=storm')` is storm moderate. `forcedScene('?fx=sunny,windy')` is sunny with windy true. `forcedScene('?x=1')` and `forcedScene('?fx=bogus')` are null.
  - `fxAllowed`: true for the defaults. False for each of these on its own: pref off, reducedMotion, saveData, battery `{level:0.1, charging:false}`. True for `{level:0.1, charging:true}`.
  - `readPref` with a throwing `getItem` gives `'on'`. With a fake storage returning `'off'` it gives `'off'`. `writePref` with a throwing storage does not throw.
  - `badgeText`: storm beats windy, rain beats cool, windy beats cool. Sunny alone gives `''`.
  - `dropCount('heavy', true) === 70`; `dropCount(null, false) === 0`.
- [ ] **Step 2:** Run `npm test -- weatherFx` in `web/`. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run `npm test`. Expected: pass.
- [ ] **Step 5:** Commit `feat(fx): weather scene helpers`.

### Task 2: Weather layer, badge and toggle (UI)

**Files:**
- Create: `web/src/components/fx/WeatherFx.jsx` (default `WeatherFx`, named `WeatherBadge` and `WeatherFxToggle`), `web/src/lib/useWeatherScene.js`
- Modify:
  - `web/src/App.jsx`: render `<WeatherFx scene allowed />` right after `<RiverBackdrop />`, and put the badge and toggle next to `ThemeToggle` at ~line 303.
  - `web/src/components/Sidebar.jsx`: put the toggle next to `ThemeToggle withLabel` at ~line 144, with a label.
  - `web/src/index.css`: keyframes and classes near `.river-backdrop` (~line 337), plus a `prefers-reduced-motion` block.

**Interfaces:**
- Consumes: Task 1 helpers and `fetchWeatherNow(lat, lng)` from `web/src/lib/api.js`.
- Produces: `useWeatherScene() -> { scene, allowed, pref, setPref }`.
  - `scene` = `forcedScene(location.search) ?? weatherScene(lastGoodNow)`.
  - `allowed` is kept live: it listens to the reduced-motion media query change and the battery `levelchange`/`chargingchange` events.

**Layer design:**
- **Rain.** `dropCount` thin slanted streaks (1 px wide, 14–28 px tall, random x, delay and duration 0.5–1.1 s; heavy is faster). Colour is light blue-grey at 0.35–0.55 opacity in dark and slate at 0.25–0.4 in light. A slightly darker sky overlay (moderate 0.08, heavy 0.15). The slant is about 12°, or about 25° when windy.
- **Storm.** Rain, plus a pale flash overlay that peaks at ≤ 0.35 for about 120 ms in a 9 s loop.
- **Cloudy.** A grey overlay of 0.10 in light and 0.18 in dark, with 2–3 large soft blurred clouds drifting slowly (60–90 s).
- **Sunny.** A warm soft light from the top corner (radial gradient, amber at 0.10 in light and 0.14 in dark) with 2–3 faint rays that rotate very slowly (≥ 60 s per turn). No flashing.
- **Cool (modifier).** A cool blue tint (0.06 in light and 0.10 in dark) plus a thin low mist band drifting slowly near the bottom.
- **Windy (modifier).** 16 short pale horizontal streaks blowing across (1.5–3 s each, staggered), 8 below 640 px.
- **Clear.** No base effect, but the modifiers still show.
- **Off.** When not `allowed`, nothing renders.

**Badge:**
- A small pill with an icon matching the badge (rain, storm, wind or thermometer) and `badgeText(scene)`, `role="status"`.
- It shows whenever the text is non-empty, even when effects are off.
- On phones it may show the icon only, with the text as `aria-label`.

**Toggle:**
- An icon button with `aria-pressed`.
- `aria-label`/`title` are `ปิดเอฟเฟกต์อากาศ` when on and `เปิดเอฟเฟกต์อากาศ` when off. The sidebar version shows that text as its label.
- `min-h-11 min-w-11`, same style as `ThemeToggle`.

- [ ] **Step 1:** Implement the hook, component and CSS, then wire them into App and Sidebar.
- [ ] **Step 2:** Run `npm test` (pass) and `npx vite build --outDir ../instances/test/dist` (OK).
- [ ] **Step 3:** Self-check in the code:
  - the layer sits under `main`;
  - `pointer-events: none`;
  - no polling faster than 10 min;
  - no geolocation prompt;
  - a missing `wind_speed` (old server) means not windy.
- [ ] **Step 4:** Commit `feat(fx): weather background (rain, storm, cloudy, sunny, cool, windy) with badge and off switch`.

### Task 3: Phone and theme check (controller)

- [ ] Take CDP 360×800 screenshots in light and dark of `?fx=heavyrain`, `?fx=storm`, `?fx=sunny,windy`, `?fx=clear,cool` and `?fx=cloudy` on the dashboard, after a web-only deploy (Task 0 needs a production restart for real wind data, while the `?fx=` previews work without it). Check:
  - text is readable;
  - no horizontal scroll;
  - the badge shows;
  - the toggle hides the layer.
- [ ] Fix anything found as one small task with a review.
