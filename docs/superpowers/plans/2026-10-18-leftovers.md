# Leftovers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the seven small leftovers from the PM2.5, best-time, weather-effects and phone-polish work, then recheck the site on desktop and phone.

**Architecture:** Each fix is local to one module.
- **Backend:** alert state rule, offline chat line, a holiday list for the best-time profiles.
- **Web:** live narrow-screen tracking for rain, pop-up alignment on tablets.
- **Controller:** a CDP permission test and a clean-up.

**Tech Stack:** Python/pytest, React/vitest.

**Spec:** the user's request (2026-10-18): "ทำเรื่องเล็กที่ค้างไว้ทั้งหมดก่อน และรีเช็คทั้งในคอมและในโทรศัพท์". The list is the controller's leftovers summary, items 1–7.

## Global Constraints

- **Never break existing behaviour or response fields.**
- **Plain Thai** in any UI text.
- **No new dependencies.**
- **Servers.** Never start, stop or restart them. Never build into `instances/production/dist`.
- **Commits.** Messages end with a Co-Authored-By trailer.

## Review Focus

1. **Dust alert sent state.** It must still clear on later dates, and must not grow the state file forever.
2. **Holiday list.** A missing or broken list file must not stop the best-time profiles.

---

### Task 1: Backend leftovers (items 1–3)

**Files:**
- Modify: `backend/core/alert_service.py` (clear sweep ~line 303), `backend/agents/chat_offline.py` (~line 81), `backend/bma/bma_best_time.py` (day type ~line 121)
- Create: `config/thai_holidays.json`
- Tests: `tests/test_alert_service.py`, `tests/test_chat_air_forecast.py` (or a new `tests/test_chat_offline_air.py`), `tests/test_bma_best_time.py`

**Item 1, dust alert repeats near the threshold.**
- Problem: an `airfc:<date>` key clears after 30 min absent (`CLEAR_SECONDS`), so a borderline evening can push 2–3 times.
- Rule: in the clear sweep, keep `airfc:` keys while their date (the `YYYY-MM-DD` after the colon) is today or later in Bangkok time. Clear them normally once the date has passed.
- Tests:
  - `test_dust_alert_once_per_date`: candidate at 18:00 → push. Absent for 45 min → not cleared. Back at 19:00 at the same level → no second push.
  - `test_dust_alert_key_clears_after_its_date`: the day after the date, plus `CLEAR_SECONDS`, the key is gone.

**Item 2, offline chat air reply has no outlook.**
- Fix: in `chat_offline.py` the air branch calls `air_context((extra or {}).get("air"), question, (extra or {}).get("air_forecast"))`.
- Test: `rule_based_reply` with topics air, an empty station list and a forecast gives a reply containing `พรุ่งนี้`. Build the inputs the way the existing chat tests do.

**Item 3, public holidays count as workdays in "ออกกี่โมงดี".**
- Fix: a holiday counts as `weekend`.
  - Create `config/thai_holidays.json` = `{"note": "...", "dates": ["YYYY-MM-DD", ...]}`.
  - It holds the fixed-date Thai public holidays for 2026 and 2027: Jan 1, Apr 6, Apr 13, Apr 14, Apr 15, May 1, May 4, Jun 3, Jul 28, Aug 12, Oct 13, Oct 23, Dec 5, Dec 10, Dec 31.
  - The `note` field says that lunar holidays (มาฆบูชา, วิสาขบูชา, อาสาฬหบูชา, เข้าพรรษา) and substitute days must be added each year from the cabinet announcement.
- `bma_best_time.py` loads the file once (path relative to the repo root, like other `config/` reads). A missing or broken file gives an empty set, with one printed warning.
- Day type: `weekend` if the weekday is 5 or 6, or the date is in the set.
- Test: `test_holiday_counts_as_weekend`. A Friday that is in an injected holiday set goes to weekend. Give `BestTime` an optional `holidays: set[str]` parameter (default: loaded from the file).

- [ ] **Step 1:** Write the failing tests.
- [ ] **Step 2:** Run them and confirm they FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run `.venv\Scripts\python.exe -m pytest tests/test_alert_service.py tests/test_bma_best_time.py tests/test_chat_air_forecast.py tests/test_chat_service.py -q`. Expected: PASS.
- [ ] **Step 5:** Commit `fix: dust alert once per date, offline air outlook, holidays in best time`.

### Task 2: Web leftovers (items 4–5)

**Files:**
- Modify: `web/src/components/fx/WeatherFx.jsx` (`isNarrow()` used once via `useMemo`), `web/src/components/AlertPopups.jsx` (container classes)

**Item 4, rain count does not follow rotation.**
- Replace the one-time `isNarrow()` with a small hook `useNarrow()` that reads `matchMedia('(max-width: 639px)')` and updates on `change`.
- Drops are regenerated only when the value changes.

**Item 5, pop-ups pinned left on tablets (640–1023 px).**
- Phones (< 640 px) stay `inset-x-3`.
- From `sm` up to `lg`, the card sits at the right: `sm:left-auto sm:right-3 sm:w-96`, still at the bottom position.
- `lg` and up stays top-right as now.

- [ ] **Step 1:** Implement both.
- [ ] **Step 2:** Run `npm test` and `npx vite build --outDir ../instances/test/dist`. Expected: pass, OK.
- [ ] **Step 3:** Commit `fix(web): rain follows rotation, tablet pop-ups on the right`.

### Task 3: Controller items 6–7 and the recheck

- [ ] **Item 6, location flow, in a real browser.** Use CDP:
  1. Load the dashboard. Expected: the `ใช้ตำแหน่งของฉัน` button shows and there is no prompt.
  2. Call `Browser.grantPermissions(['geolocation'])` and `Emulation.setGeolocationOverride` (a Bangkok point). Expected: without a reload, the weather label becomes `อากาศตรงนี้`.
  3. Call `Browser.resetPermissions`. Expected: the button returns after a reload.
- [ ] **Recheck.** Take CDP screenshots of `#/dashboard`, `#/air`, `#/map`, `#/water` and `#/cameras` at 1366×800 and 360×800, in light and dark. Check: no horizontal scroll, nothing covers the text, the badge and toggle are present.
- [ ] **Item 7.** Delete `instances/production/dist_old` after the recheck passes on production.
