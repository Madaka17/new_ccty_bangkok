# Commute Hours, Dust Alert, Chat Outlook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Four follow-ups to the PM2.5 page and the "ออกกี่โมงดี" card (docs/AIR_AND_BEST_TIME.md):
1. The card answers the morning and evening travel windows.
2. The team gets a push alert the evening before a dusty day.
3. The chat bot knows the 3-day dust outlook.
4. Both pages are checked at phone width.

**Architecture:**
- `bma_best_time.profile()` gains a `commute` block, and the card shows it.
- `alert_service.candidates()` reads `air_forecast.status()` as a new source.
- `chat_context.air_context()` takes the outlook as an optional argument.
- The phone check uses headless Chrome screenshots, done by the controller.

**Tech Stack:** FastAPI/Python (pytest via `E:\new_ccty_bangkok\.venv\Scripts\python.exe -m pytest`), React (vitest via `npm test` in `web/`).

**Spec:** the user's request in this session (2026-10-18) for items 1–4, with these decisions:
- **Travel windows:** morning 06–10 and evening 16–20.
- **Alert threshold:** tomorrow at "เริ่มมีผลต่อสุขภาพ" or worse. Alert again if tomorrow rises to "มีผลต่อสุขภาพ".
- **Alert time:** from 17:00 on the day before.

## Global Constraints

- **UI copy:** plain Thai. Traffic words `คล่องตัว` / `ชะลอตัว` / `ติดขัด`. No English or model names on public pages.
- **Dependencies:** none new.
- **Servers:** never start, stop or restart a server, and never build into `instances/production/dist`. The deploy is done by the controller after the user agrees.
- **API compatibility:** existing response fields stay as they are (`best`, `worst`, `days`, …). Only add new fields.
- **Commits:** messages end with a Co-Authored-By trailer.

## Review Focus

1. **Commute window with too little data.** A window where no hour reaches 3 cells gives `best: null` / `worst: null` for that window only. The card then shows `ข้อมูลยังไม่พอ` on that line, not a wrong hour. Test in Task 1.
2. **Alert outside the time window.** Before 17:00 Bangkok time, the alert never fires. After midnight, "พรุ่งนี้" moves to the next date, so the old key clears and the new day can alert again. Both cases are tests in Task 2.
3. **Outlook missing.** `air_forecast.status()` is None (202 state): the alert source and the chat give nothing extra and never raise. Test in Task 2.
4. **Severity raise.** If tomorrow goes from `unhealthy` to `very_unhealthy`, a second push goes out, through the existing "severity went up" logic. Test in Task 2.

---

### Task 1: Morning and evening windows on the best-time card

**Files:**
- Modify: `backend/bma/bma_best_time.py` (`profile()`), `tests/test_bma_best_time.py`
- Modify: `web/src/components/dashboard/BestTimeCard.jsx`

**Interfaces:**
- Produces: `profile()` result gains `"commute": {"morning": {"best": {...}|None, "worst": {...}|None}, "evening": {...}}`.
  - Morning picks among start hours 6, 7, 8, 9 (window 06:00–10:00).
  - Evening picks among start hours 16, 17, 18, 19 (window 16:00–20:00).
  - Only hours with data count, as for `best` and `worst` today.
  - Constants: `MORNING_HOURS = range(6, 10)` and `EVENING_HOURS = range(16, 20)`.
  - The existing `best` and `worst` stay unchanged.

**Card copy:** below the bars, replace the two existing lines with two rows.
- Row 1: `ช่วงเช้า (06:00–10:00): รถน้อยที่สุด {hourRange(best)} · ควรเลี่ยง {hourRange(worst)}`
- Row 2: `ช่วงเย็น (16:00–20:00): …` in the same form.
- A window with `best` null shows `ช่วงเช้า (06:00–10:00): ข้อมูลยังไม่พอ`.
- When both windows are null, keep the existing whole-card message `ข้อมูลยังไม่พอ ลองเลือกถนนอื่นหรือทั้งกรุงเทพฯ`.

- [ ] **Step 1:** Write the failing tests:
  - `test_commute_windows`: one camera, 3 workdays. Totals: 07:00 = 2, 09:00 = 30, 17:00 = 40, 19:00 = 3, every other hour 10. Expected: `commute.morning == {"best": {"from": 7, "to": 8}, "worst": {"from": 9, "to": 10}}` and `commute.evening == {"best": {"from": 19, "to": 20}, "worst": {"from": 17, "to": 18}}`.
  - `test_commute_window_without_data`: data only in hours 6–9. Expected: `commute.evening == {"best": None, "worst": None}`, and morning is not None.
- [ ] **Step 2:** Run `.venv\Scripts\python.exe -m pytest tests/test_bma_best_time.py -q`. Expected: FAIL.
- [ ] **Step 3:** Implement the backend, then the card.
- [ ] **Step 4:** Run pytest (pass), `npm test` (pass) and `npx vite build --outDir ../instances/test/dist` (OK).
- [ ] **Step 5:** Commit `feat(best-time): morning and evening travel windows`.

### Task 2: Dust alert for tomorrow, and the outlook in chat

**Files:**
- Modify: `backend/core/alert_service.py` (candidates, `TOPIC_URL`), `backend/api/site.py` (AlertService sources), `tests/test_alert_service.py`
- Modify: `backend/agents/chat_context.py` (`air_context`), `backend/agents/chat_service.py` (both call sites), `backend/api/chat.py` (sources list ~line 45); new test `tests/test_chat_air_forecast.py`

**Interfaces:**
- Consumes: `air_forecast.status()` from `backend.water.air_forecast`. It returns None or `{"updated_at", "ratio", "hours": [...], "days": [{"date", "label": "วันนี้"|"พรุ่งนี้"|"มะรืนนี้", "mean", "max", "level", "label_th", "color"}]}`.
- Produces:
  - Alert source key `"air_forecast"`.
  - `air_context(air, question, forecast=None)`.
  - Chat source `("air_forecast", air_forecast.status)`, read as `ex.get("air_forecast")`.

**Alert rules** (inside `candidates(now=None)`; use `now` / Bangkok local time the same way the method already handles time):
- Only when the local hour is 17 or later.
- Take the `days` entry with `label == "พรุ่งนี้"`.
  - If its `level` is `unhealthy`, add `{"topic": "air", "key": f"airfc:{date}", "level": 1, ...}`.
  - If its `level` is `very_unhealthy`, use `"level": 2`.
- Title: `พรุ่งนี้ฝุ่น PM2.5 {label_th}`.
- Body: `ค่าเฉลี่ยประมาณ {round(mean)} สูงสุดประมาณ {round(max)} · ควรเตรียมหน้ากาก N95`.
- Province: `กรุงเทพมหานคร`.
- `TOPIC_URL["air"]` becomes `"/#air"`.
- When the source returns None or raises, add no candidate (the existing `_call` already catches errors).

**Chat:** `air_context` appends one line when `forecast` has `days`:
- Format: `ฝุ่นคาดการณ์ กทม. (ค่าประมาณ): วันนี้ เฉลี่ย 23 ดี สูงสุด 35; พรุ่งนี้ …; มะรืนนี้ …`.
- Use rounded integers and `label_th`.
- When `items` is empty but a forecast exists, still return the forecast line.

- [ ] **Step 1:** Write the failing tests:
  - Alert tests use a fake `air_forecast` source and a fixed `now`:
    - `test_dust_alert_tomorrow_after_17`: at 18:00 local with tomorrow `unhealthy`, one candidate with key `airfc:<date>` and level 1.
    - `test_dust_alert_not_before_17`: at 16:59, no candidate.
    - `test_dust_alert_level_raise`: tomorrow `very_unhealthy` gives level 2. Also, `check()` called twice, first with `unhealthy` then with `very_unhealthy`, pushes twice. Follow how the existing tests in `tests/test_alert_service.py` stub push.
    - `test_dust_alert_no_outlook`: source returns None, so no candidate and no exception.
  - Chat tests:
    - `test_air_context_adds_outlook`: the line contains `พรุ่งนี้ เฉลี่ย` and the rounded mean.
    - `test_air_context_outlook_without_stations`: `items` is empty and a forecast exists, so exactly 1 line.
    - `test_air_context_without_outlook_unchanged`: `forecast=None` gives the same lines as before.
- [ ] **Step 2:** Run the new tests. Expected: FAIL.
- [ ] **Step 3:** Implement and wire the sources.
- [ ] **Step 4:** Run `.venv\Scripts\python.exe -m pytest tests/test_alert_service.py tests/test_chat_air_forecast.py tests/test_chat_service.py -q`. Expected: pass.
- [ ] **Step 5:** Commit `feat(air): evening alert for a dusty tomorrow, outlook in chat`.

### Task 3: Phone-width check (controller)

- [ ] Take headless Chrome screenshots at 360×800 of `/#/air` and `/#/dashboard`, scrolled to the card. Use the Chrome on this PC with `--headless=new --window-size=360,800 --screenshot`, against production after the deploy, or a test build served locally. Check that there is no horizontal scroll (`scrollWidth <= 360`) and that nothing overlaps.
- [ ] Fix anything found as its own small task, with a review.

### Task 4: Deploy (controller, only after the user agrees)

The backend changed, so production needs a restart. Follow `production-web-build`: build `dist_next`, stop :8000, swap the folders, start in a new window, then check `/api/bma/best_time` (it has `commute`) and that `/api/alerts/status` answers.
