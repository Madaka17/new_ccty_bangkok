r"""
BKK Monitor collector: checks everything every 30 s and keeps the history the app shows.

    .venv\Scripts\pythonw.exe launch\monitor\collector.py     started at logon by the "BKK Monitor collector" task
                                                               (launch\monitor\install.ps1); no window
Each round: monitor_checks.run_round (the AI gateway only every 5 minutes: each check takes one of the key's
3 parallel slots), new watchdog.log lines, one Windows toast for changes worth telling. Events older than 30 days
are deleted once an hour. The app asks for an early round by setting the meta value "check_now".
Only one collector runs: a second one exits at once (lock file state\collector.lock).
Errors go to state\collector.log.
"""
import logging
import msvcrt
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import monitor_checks  # noqa: E402
import monitor_notify  # noqa: E402
import monitor_watchdog  # noqa: E402
from monitor_store import DEFAULT_DB, Store  # noqa: E402

HERE = Path(__file__).resolve().parent
STATE = HERE / "state"
DB_PATH = DEFAULT_DB
WATCHDOG_LOG = monitor_checks.STATE_DIR / "watchdog.log"
ROUND_S = 30
GATEWAY_S = 300
KEEP_DAYS = 30
BAD = ("fail", "warn")
GRACE_S = 180           # a server that just left "stopped" may still be booting
DEBOUNCE_ROUNDS = 2     # a new fail/warn must hold this many rounds in a row before it counts
QUIET_UPTIME_S = 600    # after a restart its agent/YOLO rows fail for a while: store, but do not toast
log = logging.getLogger("bkk-monitor")


def import_watchdog(store, now):
    offset = int(store.get_meta("watchdog_offset", "0"))
    lines, offset = monitor_watchdog.read_new(WATCHDOG_LOG, offset)
    events = []
    for ln in lines:
        p = monitor_watchdog.parse(ln)
        if p and p["ts"] >= now - KEEP_DAYS * 86400:
            events.append(store.add_event(p["ts"], f"watchdog:{p['target']}", "watchdog", p["target"], "Watchdog",
                                          None, p["new"], p["detail"]))
    store.set_meta("watchdog_offset", offset)
    return events


def smooth(statuses, stored, now, memory):
    """Hide blips: a server just out of "stopped" is "idle" while it boots, a first bad round is held back."""
    streak, grace = memory["streak"], memory["grace"]
    out = []
    for s in statuses:
        key, prev = s["key"], stored.get(s["key"])
        if key.startswith("server:"):
            if prev == "stopped" and s["state"] == "fail":
                grace.setdefault(key, now)
            if s["state"] == "fail" and key in grace and now - grace[key] < GRACE_S:
                s = {**s, "state": "idle", "detail": f"starting ({int(now - grace[key])} s)"}
            elif s["state"] != "fail":
                grace.pop(key, None)
        if s["state"] in BAD and prev is not None and prev not in BAD:
            streak[key] = streak.get(key, 0) + 1
            if streak[key] < DEBOUNCE_ROUNDS:
                s = {**s, "state": prev}
        else:
            streak.pop(key, None)
        out.append(s)
    return out


def retire_stale(store, final, retired):
    """Drop agent/YOLO rows of a server that gave no health this round, and rows whose name is gone."""
    server = {s["target"]: s["state"] for s in final if s["key"].startswith("server:")}
    present = {s["key"] for s in final}
    stale = []
    for row in store.current():
        if row["group"] in ("agent", "yolo") and row["target"] in ("production", "test"):
            if server.get(row["target"]) not in ("ok", "warn") or row["key"] not in present:
                stale.append(row["key"])
                retired[row["key"]] = row["state"]      # coming back unchanged is not news
    store.retire(stale)


def one_round(store, now, gateway_due, memory=None, quiet=None):
    """memory: the streak/grace counters kept between rounds; quiet: filled with targets that just restarted."""
    memory = memory if memory is not None else {"streak": {}, "grace": {}}
    raw = monitor_checks.run_round(gateway_due)
    if quiet is not None:
        quiet.clear()
        quiet.update(s["target"] for s in raw if s["key"] in ("server:production", "server:test")
                     and s.get("uptime_s", QUIET_UPTIME_S) < QUIET_UPTIME_S)
    stored = {r["key"]: r["state"] for r in store.current()}
    final = smooth(raw, stored, now, memory)
    retired = memory.setdefault("retired", {})
    silent = {s["key"] for s in final if retired.get(s["key"]) == s["state"]}
    events = store.apply(final, now, silent)
    for s in final:
        retired.pop(s["key"], None)
    retire_stale(store, final, retired)
    try:
        events += import_watchdog(store, now)
    except Exception:  # noqa: BLE001 - the status events above are already stored; still return them
        log.exception("watchdog import failed")
    store.set_meta("collector_at", int(now))
    return events


def loop(store):
    last_gateway = last_prune = 0.0
    memory, quiet = {"streak": {}, "grace": {}}, set()
    while True:
        try:
            now = time.time()
            store.set_meta("collector_at", int(now))        # alive even if the round below takes long
            store.set_meta("check_now", "0")    # a refresh asked for during this round starts the next one
            gateway_due = now - last_gateway >= GATEWAY_S
            events = one_round(store, now, gateway_due, memory, quiet)
            if gateway_due:
                last_gateway = now
            if now - last_prune >= 3600:
                store.prune(now, KEEP_DAYS)
                last_prune = now
            msg = monitor_notify.summarize(events, quiet, now)
            if msg:
                monitor_notify.toast(*msg)
        except Exception:  # noqa: BLE001 - a bad round is logged, the next one runs
            log.exception("round failed")
        try:
            for _ in range(ROUND_S):
                time.sleep(1)
                if store.get_meta("check_now") == "1":
                    break
        except Exception:  # noqa: BLE001 - e.g. the database is busy; try again next round
            log.exception("wait failed")
            time.sleep(ROUND_S)


def main():
    STATE.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(STATE / "collector.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    try:
        lock = open(STATE / "collector.lock", "w")
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return 0        # another collector holds the lock
        store = Store(DB_PATH)
        log.info("collector started")
        loop(store)
    except Exception:  # noqa: BLE001 - under pythonw nobody sees a traceback; leave it in the log
        log.exception("collector stopped")
        return 1


if __name__ == "__main__":
    sys.exit(main())
