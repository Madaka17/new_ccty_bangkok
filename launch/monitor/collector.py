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
from monitor_store import Store  # noqa: E402

HERE = Path(__file__).resolve().parent
STATE = HERE / "state"
DB_PATH = STATE / "monitor.db"
WATCHDOG_LOG = monitor_checks.STATE_DIR / "watchdog.log"
ROUND_S = 30
GATEWAY_S = 300
KEEP_DAYS = 30
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


def one_round(store, now, gateway_due):
    events = store.apply(monitor_checks.run_round(gateway_due), now)
    events += import_watchdog(store, now)
    store.set_meta("collector_at", int(now))
    return events


def main():
    STATE.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(STATE / "collector.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    lock = open(STATE / "collector.lock", "w")
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        return 0        # another collector holds the lock
    store = Store(DB_PATH)
    log.info("collector started")
    last_gateway = last_prune = 0.0
    while True:
        now = time.time()
        try:
            gateway_due = now - last_gateway >= GATEWAY_S
            events = one_round(store, now, gateway_due)
            if gateway_due:
                last_gateway = now
            if now - last_prune >= 3600:
                store.prune(now, KEEP_DAYS)
                last_prune = now
            msg = monitor_notify.summarize(events)
            if msg:
                monitor_notify.toast(*msg)
        except Exception:  # noqa: BLE001 - a bad round is logged, the next one runs
            log.exception("round failed")
        store.set_meta("check_now", "0")
        for _ in range(ROUND_S):
            time.sleep(1)
            if store.get_meta("check_now") == "1":
                break


if __name__ == "__main__":
    sys.exit(main())
