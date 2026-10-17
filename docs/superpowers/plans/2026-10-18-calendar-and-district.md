# Road-Closure Calendar and "เขตของฉัน" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Two features on the public site.
1. **Road-closure calendar** ("ปิดถนน งานใหญ่"). It shows closures and big events: ongoing now, today, tomorrow and the next 7 days. The team can add events by hand. It appears as a tab on the traffic overview and as pins on the map.
2. **"เขตของฉัน" page.** Pick one of Bangkok's 50 districts once and see that district's dust, flooding, flood reports, traffic, accidents, closures and cameras on one page.

**Architecture:**
- Two new backend modules, each with its own routes:
  - `backend/traffic/events_calendar.py` merges the existing closure feeds with a team-edited JSON store.
  - `backend/traffic/district_view.py` assembles one district from the live services already in `backend/services.py`.
- The web gets a dashboard tab plus map pins, and a new page plus a dashboard shortcut.

**Tech Stack:** FastAPI, pytest; React 18, Tailwind 4, maplibre (already used), vitest. No new dependencies.

**Spec:** the user's request (2026-10-18), "ทำของใหม่ข้อ 1 และ 2", with these decisions:
- **Calendar data:** automatic feeds plus events the team adds.
- **Calendar place:** a new tab in ภาพรวมจราจร, plus map pins.
- **District:** a new page `#/district` plus a dashboard button; the 50 Bangkok districts only.

## Global Constraints

- **Plain Thai** on the public pages. Use the existing words (`ปิดถนน`, `เบี่ยงจราจร`, `ติดขัด`/`ชะลอตัว`/`คล่องตัว`, `จุดวัดฝุ่น`, `เครื่องวัดน้ำบนถนน`, `คนแจ้ง`). No codes, no English, no source acronyms without their meaning.
- **Team writes** (POST/DELETE) rely on the existing `access_guard` rule: POST/DELETE outside `PUBLIC_WRITE_PREFIXES` is operator-only. Do not add the new paths to the public prefixes. GET is public.
- **Team events file:** `DATA_DIR/cache/team_events.json`.
  - Writes are atomic (write a temp file, then replace).
  - At most 300 events. Events that ended more than 30 days ago are pruned on write.
- **Input limits:**
  - title ≤ 120 characters, detail ≤ 600, place ≤ 120;
  - `start < end`, and `end` no more than 120 days ahead;
  - kind ∈ `closure|diversion|event|run|concert|ceremony`;
  - lat/lng optional, but if given they must be numbers inside Thailand's bounding box (lat 5–21, lng 97–106);
  - district optional, and must be one of the 50 Bangkok districts.
  - Reject anything else with 422.
- **Calendar scope:** Bangkok and vicinity by default, meaning provinces กรุงเทพมหานคร, นนทบุรี, ปทุมธานี, สมุทรปราการ, สมุทรสาคร, นครปฐม. `?scope=all` gives the whole country.
- **Bangkok time:** UTC+7, used for today/tomorrow/7-day buckets.
- **No new external calls.** Both modules read only data the server already holds (the BMA site rate-limits our IP).
- **Responses** use the existing `cached_json` for GET. DELETE/POST clear that cache key, or the cache TTL must be short enough; check `response_cache` and choose.
- **Commits** end with a Co-Authored-By trailer. Never build into `instances/production/dist`. Never start, stop or restart servers.

## Review Focus

1. **Feed items with no time.** A BMA bulletin has no start/end, and some Longdo items have only `stop`. They land in "กำลังปิดอยู่", never in a wrong day. Test in Task 1.
2. **Duplicates.** The same closure from BMA road-work and from a Longdo closure, within 300 m with similar titles, shows once. Test in Task 1.
3. **Broken or missing team file.** Treated as empty, with one warning, and never a 500. Test in Task 1.
4. **District with no data for a section.** For example, no dust station in that district: the section says `ยังไม่มีข้อมูลในเขตนี้`. It never shows 0 as if measured. Test in Task 3.
5. **Unknown district name in the URL.** 404, not 500. Test in Task 3.

---

### Task 1: Calendar backend

**Files:**
- Create: `backend/traffic/events_calendar.py`, `tests/test_events_calendar.py`
- Modify: `backend/api/traffic.py` (routes)

**Interfaces (produces):**
- `class EventsCalendar(store_path, sources: dict[str, Callable], now=time.time)`. `sources` holds:
  - `"closures"`: Longdo/BMA closures, from `incidents.road_events()["closures"]`, items `{id, source, kind ('closed'|'diversion'), reason, title, description, latitude, longitude, start 'YYYY-MM-DD HH:MM:SS', stop, province, amphoe}`;
  - `"bma"`: `bma_feed.get(kind="roadwork", hours=72)` items;
  - `"bulletins"`: BMA traffic-centre bulletins from `bma_feed` (check how `/api/water/bma_events` returns `bulletins`). Keep only bulletins whose headline/detail matches the road-work words (`ปิด`, `เบี่ยง`).
- `calendar(scope='bkk') -> {"updated_at", "ongoing": [...], "today": [...], "tomorrow": [...], "week": [...]}`.
  - Each item is `{id, source: 'team'|'longdo'|'bma'|'bma_bulletin', kind, title, detail, place, district, province, lat, lng, start, end, url}`, with `start`/`end` as epoch seconds or null.
  - Sorted by start, then title.
- `add(event: dict) -> dict` (validated, returns the stored item with a new `id`, prefix `team-`). `remove(id) -> bool`.
- Routes:
  - `GET /api/events/calendar?scope=bkk|all` (cached);
  - `POST /api/events/team` (body as above; 422 on bad input);
  - `DELETE /api/events/team/{id}` (404 if unknown).

**Bucket rules (Bangkok time):**
- **ongoing:** start is null or before today 00:00, and end is null or after now.
- **today:** start in [today 00:00, tomorrow 00:00).
- **tomorrow:** start in [tomorrow 00:00, +1 day).
- **week:** start in [day+2 00:00, day+8 00:00).
- Items that already ended are dropped.

- [ ] **Step 1: Write the failing tests:**
  - bucket placement, with a fixed `now`;
  - a bulletin goes to ongoing;
  - a Longdo item with start in the past and stop tomorrow goes to ongoing;
  - an ended item is dropped;
  - scope filtering: Chiang Mai is hidden for `bkk` and shown for `all`;
  - dedup: BMA road-work and a Longdo closure within 300 m with a shared title word appear once, and the Longdo one is kept;
  - `add` validation (each rule gives a ValueError message);
  - `add` + `remove` round trip persisted to a tmp file;
  - a broken store file gives an empty list with no exception;
  - pruning of events that ended more than 30 days ago.
- [ ] **Step 2:** Run `.venv\Scripts\python.exe -m pytest tests/test_events_calendar.py -q`. Expected: FAIL.
- [ ] **Step 3:** Implement the module and the routes. Wire `EventsCalendar` in `backend/api/traffic.py` with the real sources. Never import `backend.services` in tests.
- [ ] **Step 4:** Run the same command. Expected: PASS.
- [ ] **Step 5:** Commit `feat(events): road-closure and big-event calendar with team events`.

### Task 2: Calendar web (tab + map pins + team form)

**Files:**
- Create: `web/src/components/dashboard/EventsPanel.jsx`, `web/src/lib/events.js` (+ `events.test.js`)
- Modify:
  - `web/src/components/DashboardPage.jsx`: add `{ id: 'events', label: 'ปิดถนน งานใหญ่' }` to `SECTIONS` after `incidents`, and render the panel.
  - `web/src/lib/api.js`: `fetchCalendar(scope)`, `addTeamEvent(body)`, `deleteTeamEvent(id)`.
  - The map: add a layer toggle `งานใหญ่ ปิดถนนล่วงหน้า` that shows calendar items with coordinates. Follow how the existing closures layer and toggles are built (`web/src/components/MapPage.jsx`, `web/src/components/map/roadEvents.js`, `LayerGroup.jsx`).

**Interfaces:** `lib/events.js`:
- `kindLabel(kind)`: closure `ปิดถนน`, diversion `เบี่ยงจราจร`, event `งานใหญ่`, run `งานวิ่ง`, concert `คอนเสิร์ต`, ceremony `พิธี / ขบวน`, else `ประกาศ`.
- `sourceLabel(source)`: team `ทีมงาน BKK StreetSmart`, longdo `Longdo Traffic`, bma `ศูนย์จราจร กทม.`, bma_bulletin `ประกาศศูนย์จราจร กทม.`.
- `timeRange(start, end)`: Thai short form in Bangkok time, e.g. `18 ต.ค. 06:00 – 12:00` for the same day, `18 ต.ค. – 20 ต.ค.` across days, `จนกว่าจะประกาศ` when end is null. Test it.

**Panel:**
- Four sections in this order:
  - `กำลังปิดอยู่`
  - `วันนี้`
  - `พรุ่งนี้`
  - `7 วันข้างหน้า`
- An empty section shows `ไม่มีรายการ`.
- Each item shows a kind badge, title, place/district, `timeRange`, a source line, and `ดูบนแผนที่` when it has coordinates (navigate to the map with that layer on).
- A collapsed `เพิ่มงาน (ทีมงาน)` form holds: title, kind select, place, district select (50, optional), start, end (datetime-local, Bangkok), and detail.
  - On submit it POSTs. A 403 shows `เพิ่มได้เฉพาะทีมงาน`.
  - Team items show a small `ลบ` button only after a successful add in this session, or when the user opens the form. A 403 on delete shows the same note.

- [ ] **Step 1:** Write the tests for `timeRange`/`kindLabel`. Run `npm test -- events`. Expected: FAIL. Then implement and run again. Expected: PASS.
- [ ] **Step 2:** Implement the panel, the API helpers and the map layer.
- [ ] **Step 3:** Run `npm test` and `npx vite build --outDir ../instances/test/dist`. Commit `feat(web): closure calendar tab, map pins and team form`.

### Task 3: District backend

**Files:**
- Create: `backend/traffic/district_view.py`, `tests/test_district_view.py`
- Modify: `backend/api/traffic.py` (routes)

**Interfaces (produces):**
- `DISTRICTS`: the 50 Bangkok district names without the `เขต` prefix, loaded once from the district shapes `area_traffic` uses (Bangkok only), sorted Thai.
- `build(name, sources) -> dict | None`. Returns None for an unknown district. `sources` holds callables for:
  - `air`: `air.status()`; items whose `area` holds `เขต<name>`, using the same last-`เขต` rule as the web `districtRanking`;
  - `flood`: `flood_roads.status()`; road sensors with `district == name`;
  - `traffy`: `traffy_reports.status()`; reports in the last 6 h whose district matches. Inspect the fields; fall back to `area_traffic.locate(lat,lng)`;
  - `cameras`: `bma_scanner.db.get_all_latest()`; cameras with `district == name`, each `{camid, title, road, level, total, status}`;
  - `area_traffic`: this district's flow score if the area endpoint has one. Inspect `area_traffic` for a per-amphoe result; else null;
  - `incidents`: `incidents.road_events()`; incidents and closures whose `amphoe`/district matches (`เขต` prefix tolerant);
  - `calendar`: the Task 1 calendar items with `district == name`, if Task 1 is merged; else omit.
- Result: `{district, updated_at, air: {pm25, level, label, points}|null, flood: {points: [...], max_cm}|null, reports: {count, latest: [...]}|null, traffic: {score, level}|null, cameras: [...], incidents: [...], closures: [...], events: [...]}`.
  - A section with no data is null, or an empty list for list sections. Never a fake 0.
- Routes:
  - `GET /api/district/list` returns `{"districts": [...]}`;
  - `GET /api/district/{name}` (cached per name, 404 when unknown). The name may arrive URL-encoded and with or without the `เขต` prefix.

- [ ] **Step 1: Write the failing tests** with fake sources:
  - name normalisation (`เขตดินแดง` and `ดินแดง` are the same);
  - an unknown name gives None;
  - the air average matches the stations in the district;
  - an empty air source gives `air: None`;
  - cameras are filtered by district;
  - incidents are matched with the `เขต` prefix.
- [ ] **Step 2:** Run `.venv\Scripts\python.exe -m pytest tests/test_district_view.py -q`. Expected: FAIL.
- [ ] **Step 3:** Implement the module and the routes.
- [ ] **Step 4:** Run the same command. Expected: PASS.
- [ ] **Step 5:** Commit `feat(district): one Bangkok district at a glance`.

### Task 4: District web page

**Files:**
- Create: `web/src/components/DistrictPage.jsx`, `web/src/lib/district.js` (+ test)
- Modify:
  - `web/src/components/Sidebar.jsx`: add `{ id: 'district', label: 'เขตของฉัน', hint: 'ฝุ่น น้ำท่วม รถติด อุบัติเหตุ และกล้องในเขตที่เลือก' }` in group ภาพรวม after `map`.
  - `web/src/App.jsx`: add `'district'` to `PAGES`, the lazy import and the render.
  - `web/src/lib/api.js`: `fetchDistricts()`, `fetchDistrict(name)`.
  - `web/src/components/DashboardPage.jsx`: a small shortcut under the PageHeader. It reads `เขตของฉัน: <name> ›` when one is saved, else `เลือกเขตของฉัน ›`, and navigates to `district`.

**Interfaces:** `lib/district.js`:
- `readMyDistrict()` / `writeMyDistrict(name)`: localStorage key `my-district`, safe when storage throws.

**Page:**
- A searchable select of the 50 districts, saved on change.
- Then cards, which reuse the existing helpers (`band()` for dust, `LEVEL_TH` words for traffic):
  - **ฝุ่น PM2.5:** value + level.
  - **น้ำท่วมถนน:** sensors with water, deepest first.
  - **คนแจ้งน้ำท่วม (6 ชม.):** count + latest.
  - **รถติด:** score/level.
  - **อุบัติเหตุ:** list.
  - **ปิดถนน งานใหญ่:** list.
  - **กล้องในเขต:** grid of camera thumbnails using `/api/bma/snapshot/{camid}?annotate=0`, lazy-loaded with `loading="lazy"`, at most 12 shown plus `ดูทั้งหมด`.
- Each empty section shows `ยังไม่มีข้อมูลในเขตนี้`.
- Poll every 2 min while active.

- [ ] **Step 1:** Write the tests for `readMyDistrict`/`writeMyDistrict` with a throwing storage. Run them. Expected: FAIL. Then implement and run again. Expected: PASS.
- [ ] **Step 2:** Implement the page, the shortcut and the wiring.
- [ ] **Step 3:** Run `npm test` and `npx vite build --outDir ../instances/test/dist`. Commit `feat(web): เขตของฉัน page and dashboard shortcut`.

### Task 5: Check and deploy (controller)

- [ ] Run the full pytest suite and `npm test`.
- [ ] Merge to main. Build `dist_next`. Production restart: the backend changed, and the user has authorised deploy, commit and push.
- [ ] Run CDP checks at 360 px and 1366 px, light and dark, on `#/dashboard` (events tab), `#/map` (new layer), and `#/district` (pick ดินแดง).
- [ ] Add a team event from localhost (trusted) and see it appear, then delete it.
- [ ] Push.
