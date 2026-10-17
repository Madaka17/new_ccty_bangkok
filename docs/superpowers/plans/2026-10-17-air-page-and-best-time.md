# PM2.5 Page and "ออกกี่โมงดี" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a PM2.5 page (`#/air`) with the dust level now, advice, a 3-day outlook and the worst districts. Add a card on the traffic overview that says which hour has the fewest cars on a chosen road.

**Architecture:**
- Two small backend services, each with one GET route:
  - `backend/water/air_forecast.py` reads the Open-Meteo PM2.5 model once an hour. It scales the model to the station average from the existing `air_service`.
  - `backend/bma/bma_best_time.py` builds per-road hourly profiles from `bma_history`. It caches them for one hour.
- Pure helpers in `web/src/lib/` (unit-tested with vitest) feed two new UI pieces: `AirPage.jsx` and `dashboard/BestTimeCard.jsx`.

**Tech Stack:** FastAPI, sqlite3, urllib (backend). React 18, Tailwind 4, vitest (web). Tests: `E:\new_ccty_bangkok\.venv\Scripts\python.exe -m pytest` and `npm test` in `web/`.

**Spec:** the user's request in this session (2026-10-17), with these decisions:
- PM2.5 is a new page "ฝุ่น PM2.5" in the sidebar group "เฝ้าระวังเมือง", right after "น้ำท่วม". The dust answer on the dashboard status strip opens that page.
- "ออกกี่โมงดี" is a card on the traffic overview (`#/dashboard`, tab "รถติดตอนนี้"). It has a road picker and a day picker, a bar per hour, the hour with the fewest cars, and the hour to avoid.
- The dust outlook comes from Open-Meteo (free, no key).

## Global Constraints

- **Plain Thai.** All UI text is short, plain Thai.
  - Traffic words: `คล่องตัว` / `ชะลอตัว` / `ติดขัด`.
  - Call a station `จุดวัดฝุ่น`.
  - No station codes, model names (CAMS, Open-Meteo) or English on the page. A source line in small muted text is allowed: `ข้อมูล: กทม., กรมควบคุมมลพิษ, ค่าพยากรณ์โดยประมาณ`.
- **Page title.** It comes from `PAGE_TITLES`. Sidebar item `{ id: 'air', label: 'ฝุ่น PM2.5', hint: 'ฝุ่นตอนนี้ แต่ละเขต และแนวโน้ม 3 วัน' }`.
- **Dependencies.** No new npm or pip dependencies. Charts are plain divs or inline SVG. Implementers of UI tasks load the `dataviz` skill before the chart code.
- **Colours.** Dust colours come from the station `color` field and the PCD bands already in `air_service.LEVELS`. Do not invent new ones.
- **Off-limits.** No task starts, stops or restarts a server. No task builds into `instances/production/dist`. Task 5 does the deploy, and only after the user agrees.
- **Commits.** Every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **History gap.** BMA history has a gap (2026-10-09 to 10-16, site down), and it only starts on 2026-09-20.
   - An hour with fewer than 3 (camera, date) cells counts as "no data", never as "few cars".
   - The card says `ข้อมูลยังไม่พอ` when no hour has enough data.
   - Tests in Task 1.
2. **Broken road names.** `road` is `ถนนพระรามที่` (number lost) or `ถนนพระราม` for 38 cameras.
   - The number must come back from the title, so "ถนนพระรามที่ 4" and "ถนนพระรามที่ 9" are different roads.
   - Test in Task 1.
3. **Open-Meteo down or slow.** `/api/air/forecast` answers 202 `{"ready": false}` before the first good read. After a read it keeps the last good answer. The page hides only the outlook section. Tests in Task 2, check in Task 3.
4. **No station data.** Air stations empty or `avg_pm25` null: the forecast ratio is 1.0, and the page shows `ยังไม่มีข้อมูลฝุ่น` instead of a 0 or NaN. Tests in Task 2 and Task 3.
5. **Phone width (360 px).** The 17-bar chart and the pickers must fit without horizontal scroll. Hour labels show every 2nd hour on narrow screens. Check in Task 4.

---

### Task 1: Best-time profiles (backend)

**Files:**
- Create: `backend/bma/bma_best_time.py`
- Modify: `backend/api/bma.py` (add route)
- Test: `tests/test_bma_best_time.py`

**Interfaces:**
- Produces:
  - `clean_road(cam: dict) -> str`
  - `class BestTime(db_path: str, cameras: list[dict], ttl: int = 3600)` with `.profile(road: str = "", day: str = "workday") -> dict`
  - A module singleton built lazily from `bma_scanner.db.db_path` and `bma_scanner.cameras`.
  - Route `GET /api/bma/best_time?road=&day=workday|weekend` returns `profile()` through `cached_json(request, ("bma/best_time", road, day), ...)`.

**Response shape:**

```json
{"updated_at": 1792250000, "since": "2026-09-20", "days_of_data": 14, "road": "", "day": "workday",
 "roads": [{"road": "ถนนรัชดาภิเษก", "cameras": 29}],
 "hours": [{"h": 6, "avg": 7.4, "samples": 210, "level": "free"}],
 "best": {"from": 10, "to": 11}, "worst": {"from": 17, "to": 18}}
```

**Rules:**
- `clean_road`:
  - If `road` ends with `ที่` or equals `ถนนพระราม`, take `ถนนพระราม(?:ที่)?\s*(\d+)` from `title` and return `ถนนพระรามที่ {n}`.
  - Otherwise return `road.strip()`.
  - When there is no match, return `road`.
- Query (read-only connection, `mode=ro`):

  ```sql
  SELECT camid, date, CAST(substr(hour, 12, 2) AS INTEGER) h, AVG(total) a, COUNT(*) FROM bma_history
  WHERE date >= date('now', 'localtime', '-56 days') GROUP BY camid, date, h
  ```

  Each row is one cell. Keep the cells in memory and rebuild them when older than `ttl`. Use one lock, so one rebuild runs at a time.
- Day type comes from `date`: Monday–Friday is `workday`, Saturday–Sunday is `weekend`. Public holidays are ignored.
- Road filter: `""` means all cameras. Otherwise use cameras whose `clean_road` equals `road`. An unknown road returns hours with `avg: null`.
- Hours returned: 6..22 (17 bars).
  - `avg` is the mean of the cell averages, rounded to 1 decimal.
  - `samples` is the number of cells.
  - When `samples < 3`, set `avg: null` and `level: null`.
- `level`: compute `ratio = avg / max(avg of hours with data)`. Below 0.6 is `free`, below 0.85 is `moderate`, otherwise `heavy`.
- `best` / `worst`: the lowest / highest `avg` among hours 6..21 with data, given as `{"from": h, "to": h+1}`. Use `null` when no hour has data.
- `roads`: roads starting with `ถนน` that have 2 or more cameras. Sort by cameras descending, then by name.
- `since` / `days_of_data`: the min date and the count of distinct dates in the cells.

- [ ] **Step 1: Write the failing tests** in `tests/test_bma_best_time.py`. Build a temp DB with `BmaDatabase(db_path=...)` and insert rows like `tests/test_bma_analytics.py::_insert`, with explicit `date` and `hour`.
  - `test_clean_road_restores_rama_number`: `{"road": "ถนนพระรามที่", "title": "แยกสะพานแดง ด้านถนนพระรามที่ 5"}` gives `"ถนนพระรามที่ 5"`, and `{"road": "ถนนพระราม", "title": "หน้าห้าง ถนนพระราม 4"}` gives `"ถนนพระรามที่ 4"`. `{"road": "ถนนสามเสน", "title": "x"}` gives `"ถนนสามเสน"`.
  - `test_best_and_worst_hours`: one camera on 3 workdays (for example 2026-10-05..07) with total 2 at 10:00 and total 20 at 17:00. The other hours have 10. Assert `best == {"from": 10, "to": 11}` and `worst == {"from": 17, "to": 18}`, and that hour 17 has `level == "heavy"` and hour 10 has `level == "free"`.
  - `test_hours_with_too_few_cells_are_no_data`: an hour present on only 2 dates gets `avg is None` and `level is None`, and is never `best`.
  - `test_weekend_is_separate`: data only on a Saturday and a Sunday. `profile(day="workday")` has `best is None`, and every `avg` is None.
  - `test_road_filter_and_road_list`: two cameras on `ถนนพระรามที่ 4` (via title) and one on `ถนนสามเสน`. `roads` holds only `ถนนพระรามที่ 4` with `cameras == 2`, and `profile(road="ถนนพระรามที่ 4")` uses only those two.
  - Freeze "now" by passing the dates relative to `date.today()`, or give `BestTime` an optional `today: Callable[[], date]` used in the SQL as a parameter instead of `date('now')`.
- [ ] **Step 2:** Run `.venv\Scripts\python.exe -m pytest tests/test_bma_best_time.py -q`. Expected: FAIL (module missing).
- [ ] **Step 3:** Implement `bma_best_time.py` and the route.
- [ ] **Step 4:** Run the same command. Expected: all pass. Then run `.venv\Scripts\python.exe -m pytest tests/test_bma_analytics.py -q`. Expected: pass.
- [ ] **Step 5:** Check against the live DB without a server: `.venv\Scripts\python.exe -X utf8 -c "from backend.bma.bma_best_time import BestTime; import json; ..."` with `db_path='instances/production/vehicle_counts.db'` and the cameras from `config/cameras_bma.json` `items`. Print `best`, `worst` and the first 5 roads. Expected: it runs in under 10 s, and `best`/`worst` are not None for `""`.
- [ ] **Step 6:** Commit `feat(bma): hourly best-time profiles per road`.

### Task 2: PM2.5 outlook (backend)

**Files:**
- Create: `backend/water/air_forecast.py`
- Modify: `backend/api/weather.py` (route), `backend/services.py` (start it next to `air.start()`)
- Test: `tests/test_air_forecast.py`

**Interfaces:**
- Consumes: `air.status()["avg_pm25"]` from `backend/water/air_service.py`, and `_pm25_band(v)` / `LEVELS` from the same module (reuse them; do not copy the breakpoints).
- Produces:
  - `build(model: dict, station_avg: float | None, now: datetime) -> dict` (pure, tested)
  - `class AirForecast` with `.start()` and `.status() -> dict | None`, plus the singleton `air_forecast`
  - Route `GET /api/air/forecast`. It returns 202 `{"ready": false}` while `status()` is None, and otherwise `cached_json(request, ("air/forecast",), air_forecast.status)`.

**Source:** `https://air-quality-api.open-meteo.com/v1/air-quality?latitude=13.75&longitude=100.52&hourly=pm2_5&timezone=Asia%2FBangkok&forecast_days=3`. Refresh every 3600 s. On error keep the last good result and print `[AirForecast] ...`.

**Rules for `build`:**
- `model_now` is the model value at the current hour, or the nearest earlier one.
- `ratio = station_avg / model_now`, clamped to [0.5, 2.0]. Use 1.0 when `station_avg` is None or `model_now` is falsy.
- `hours`: future hours only (from the current hour on), as `{"t": epoch_seconds, "pm25": round(v * ratio, 1)}`. Skip null values.
- `days`: today, tomorrow and the day after (by local date), as `{"date": "YYYY-MM-DD", "label": "วันนี้"|"พรุ่งนี้"|"มะรืนนี้", "mean": .., "max": .., "level": .., "label_th": .., "color": ..}`.
  - `mean` and `max` are over the adjusted hours 06–21 of that date.
  - The level fields come from the band of `mean`.
  - Leave out a day with no values.
- Result: `{"updated_at", "ratio", "hours", "days"}`.

- [ ] **Step 1: Write the failing tests** in `tests/test_air_forecast.py`, using a hand-made `model` dict in Open-Meteo shape (`{"hourly": {"time": [...], "pm2_5": [...]}}`):
  - `test_ratio_scales_to_stations`: model 20 at the current hour, `station_avg` 30. Expected `ratio == 1.5`, and a later model value of 40 becomes 60.0.
  - `test_ratio_is_clamped`: station 100, model 10. Expected `ratio == 2.0`.
  - `test_no_station_average_keeps_model`: `station_avg=None`. Expected `ratio == 1.0`.
  - `test_days_are_labelled_and_banded`: three dates, each with constant values 10 / 30 / 80. Expected labels `วันนี้, พรุ่งนี้, มะรืนนี้`, with levels `very_good`, `moderate`, `very_unhealthy` (from `_pm25_band`).
  - `test_past_hours_and_nulls_are_dropped`: an hour before `now` and a `None` value do not appear in `hours`.
- [ ] **Step 2:** Run `.venv\Scripts\python.exe -m pytest tests/test_air_forecast.py -q`. Expected: FAIL.
- [ ] **Step 3:** Implement the module, the route and the start in `services.py`.
- [ ] **Step 4:** Run the tests. Expected: pass. Then run a live smoke test with no server: `.venv\Scripts\python.exe -X utf8 -c "from backend.water import air_forecast as f; import urllib.request, json, datetime; ..."`. It fetches the URL once and prints `build(model, 23.3, datetime.datetime.now())["days"]`. Expected: 2–3 days with Thai labels.
- [ ] **Step 5:** Commit `feat(air): PM2.5 outlook for the next three days`.

### Task 3: PM2.5 page (web)

**Files:**
- Create: `web/src/lib/air.js`, `web/src/lib/air.test.js`, `web/src/components/AirPage.jsx`
- Modify:
  - `web/src/lib/api.js`: add `fetchAirForecast()` returning `null` on 202, like the NASA fetchers.
  - `web/src/components/Sidebar.jsx`: add the item from Global Constraints after `water`.
  - `web/src/App.jsx`: add `'air'` to `PAGES`, add `const AirPage = lazyPage(...)`, and render `{page === 'air' && <AirPage isActive onNavigate={navigate} />}`.
  - `web/src/components/dashboard/CityStatusStrip.jsx:155`: change `go: () => onNavigate('map')` to `onNavigate('air')`.

**Interfaces:**
- Consumes: `/api/air/stations` items (`province`, `area`, `pm25`, `level`, `label`, `color`, `source`) and `/api/air/forecast` from Task 2.
- Produces (in `lib/air.js`):
  - `band(pm25) -> { level, label, color }`. Mirrors the PCD breakpoints (≤15 `very_good`, ≤25 `good`, ≤37.5 `moderate`, ≤75 `unhealthy`, above that `very_unhealthy`), with the labels and colours of `air_service.LEVELS`.
  - `bkkAverage(items) -> { pm25, level, label, color } | null`. Only items with `province === 'กรุงเทพมหานคร'`. The average is rounded to 1 decimal, and its level comes from `band()`.
  - `districtRanking(items) -> [{ district, pm25, level, label, color, points }]`. Bangkok items grouped by `area` with the `เขต` prefix removed. `pm25` is the mean, `points` is the count. Sorted by pm25 descending.
  - `airAdvice(level) -> string`, with this exact copy:
    - `very_good` / `good`: `อากาศดี ทำกิจกรรมนอกบ้านได้ตามปกติ`
    - `moderate`: `ทำกิจกรรมนอกบ้านได้ เด็ก ผู้สูงอายุ และคนที่แพ้ง่ายควรสังเกตอาการ`
    - `unhealthy`: `ควรใส่หน้ากาก N95 เมื่ออยู่นอกบ้าน และลดเวลาอยู่กลางแจ้ง`
    - `very_unhealthy`: `ควรอยู่ในอาคาร ปิดหน้าต่าง ถ้าต้องออกนอกบ้านให้ใส่หน้ากาก N95`
    - unknown: `''`

**Page layout** (top to bottom, one column on a phone, two columns from `lg`):
1. `PageHeader` with title `PAGE_TITLES.air` and description `ข้อมูลล่าสุด {fmtDateTime(updated)}`.
2. Summary card: the big level label in the band colour, the number with a small `ไมโครกรัมต่อลูกบาศก์เมตร` in a `title` tooltip only, and `airAdvice`. When there is no data, show `ยังไม่มีข้อมูลฝุ่น`.
3. Card `ฝุ่น 3 วันข้างหน้า`: one tile per `days` entry (label, level label, colour), and a small line chart of `hours` (inline SVG). Hidden when the forecast is null. Note: `ค่าประมาณ อาจต่างจากจุดวัดจริง`.
4. Card `เขตที่ฝุ่นมากที่สุด`: the top 10 of `districtRanking` as rows (name, bar width ∝ pm25, level label), with a `ดูทุกเขต` toggle for the rest.
5. A button `ดูจุดวัดฝุ่นบนแผนที่` that calls `onNavigate('map')`.
6. A source line in muted small text, as in Global Constraints.

Poll both endpoints every 10 min while `isActive`, like `CityStatusStrip`.

- [ ] **Step 1: Write the failing tests** in `web/src/lib/air.test.js`:
  - `bkkAverage` ignores other provinces: two Bangkok items 20 and 30, plus one Samut Sakhon item 88. Expected `pm25 === 25` and `level === 'good'`.
  - `bkkAverage([])` returns `null`.
  - `districtRanking` groups `เขตปทุมวัน` ×2 (10, 30) and `เขตบางบอน` (40). Expected `[{district:'บางบอน', pm25:40, points:1}, {district:'ปทุมวัน', pm25:20, points:2}]` (compare those fields).
  - `airAdvice('unhealthy')` equals the exact copy above, and `airAdvice('x') === ''`.
- [ ] **Step 2:** Run `npm test -- air` in `web/`. Expected: FAIL.
- [ ] **Step 3:** Implement `lib/air.js`, then the page and the wiring.
- [ ] **Step 4:** Run `npm test` in `web/`. Expected: all pass. Run `npx vite build --outDir ../instances/test/dist` in `web/`. Expected: build OK and an `AirPage-*.js` chunk.
- [ ] **Step 5:** Commit `feat(web): PM2.5 page with district ranking and 3-day outlook`.

### Task 4: "ออกกี่โมงดี" card (web)

**Files:**
- Create: `web/src/lib/bestTime.js`, `web/src/lib/bestTime.test.js`, `web/src/components/dashboard/BestTimeCard.jsx`
- Modify:
  - `web/src/lib/api.js`: add `fetchBestTime(road, day)` for `/api/bma/best_time?road=..&day=..`, with the road URI-encoded.
  - `web/src/components/DashboardPage.jsx`: in the `section === 'overview'` block, render `<BestTimeCard isActive={isActive} />` after `TrafficGuidanceCard`.

**Interfaces:**
- Consumes: the Task 1 response shape.
- Produces (in `lib/bestTime.js`):
  - `todayDayType(date = new Date()) -> 'workday' | 'weekend'`
  - `hourRange({from, to}) -> 'HH:00–HH:00'` (en dash, two-digit hours)
  - `LEVEL_TH = { free: 'คล่องตัว', moderate: 'ชะลอตัว', heavy: 'ติดขัด' }`

**Card:**
- Title `ออกกี่โมงดี`. Subtitle `ช่วงที่รถน้อยและรถมาก จากกล้อง กทม. {days_of_data} วันที่ผ่านมา`.
- A road `<select>` whose first option is `ทั้งกรุงเทพฯ` (value `""`), followed by `roads` as `ถนน… ({cameras} กล้อง)`.
- A two-button toggle `วันทำงาน` / `เสาร์-อาทิตย์`. The default comes from `todayDayType()`.
- Bars for hours 6–22. The height ∝ `avg`. Colours use the existing tone classes (`tone-green` / `tone-yellow` / `tone-red`) by level. A null hour is a faint dashed bar. The bar for the current hour is outlined. Each bar has an `aria-label` / `title` of `{HH}:00 {LEVEL_TH}`.
- Text lines: `รถน้อยที่สุด {hourRange(best)}` and `ควรเลี่ยง {hourRange(worst)}`. If `best` is null, show only `ข้อมูลยังไม่พอ ลองเลือกถนนอื่นหรือทั้งกรุงเทพฯ`.
- Fetch on mount and on every picker change. No polling: the data changes hourly.

- [ ] **Step 1: Write the failing tests** in `web/src/lib/bestTime.test.js`:
  - `todayDayType(new Date('2026-10-17T09:00:00+07:00')) === 'weekend'` (Saturday), and `todayDayType(new Date('2026-10-19T09:00:00+07:00')) === 'workday'`.
  - `hourRange({from: 9, to: 10}) === '09:00–10:00'`.
- [ ] **Step 2:** Run `npm test -- bestTime`. Expected: FAIL.
- [ ] **Step 3:** Implement the lib and the card.
- [ ] **Step 4:** Run `npm test` and `npx vite build --outDir ../instances/test/dist`. Expected: pass and build OK. Review at 360 px width in the dev build (`npm run dev`, proxied to :8000). Expected: no horizontal scroll, and the hour labels thin out on narrow widths.
- [ ] **Step 5:** Commit `feat(dashboard): best time to travel card`.

### Task 5: Deploy to production (only after the user agrees)

Done by the controller, not a subagent.

- [ ] **Step 1:** Run all backend tests: `.venv\Scripts\python.exe -m pytest -q`. Expected: no new failures.
- [ ] **Step 2:** In `web/`, run `npx vite build --outDir ../instances/production/dist_next`.
- [ ] **Step 3:** Ask the user for a production restart, which is needed because the backend changed. Then do the following, in this order:
  1. Run `launch\kill_server.ps1 -Port 8000`.
  2. Rename `dist` to `dist_old`.
  3. Rename `dist_next` to `dist`.
  4. Start `launch\production\start.bat` in a new window.
- [ ] **Step 4:** Verify:
  - `curl 127.0.0.1:8000/api/air/forecast` answers 200 with `days`.
  - `/api/bma/best_time` answers with `best`.
  - `https://bkksmartstreet.com/#/air` loads.
  - The dashboard card shows bars.
- [ ] **Step 5:** `git push` when the user asks.
