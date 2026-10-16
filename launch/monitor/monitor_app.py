r"""
BKK Monitor: the desktop window (Desktop icon "BKK Monitor", made by launch\monitor\install.ps1).

    .venv\Scripts\pythonw.exe launch\monitor\monitor_app.py

The phone reads the same state through launch\monitor\monitor_web.py (read-only page on 127.0.0.1:8090).

Shows what the collector (launch\monitor\collector.py) stored in state\monitor.db: status cards, every check,
and the history of changes. The buttons run the same files as the Desktop shortcuts (launch\<folder>\start.bat,
restart.bat, stop.bat) in the background, and switch YOLO through launch\yolo_switch.py. The page asks for
confirmation first; this side only runs actions from a fixed list.
"""
import csv
import io
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]
import yolo_switch  # noqa: E402
from monitor_checks import ROOT, SERVERS  # noqa: E402
import monitor_processes  # noqa: E402
from monitor_store import DEFAULT_DB, Store  # noqa: E402

BAT_TARGETS = {"production", "test", "enviro"}
BAT_VERBS = {"start", "restart", "stop"}
YOLO_TARGETS = {"production", "test"}
ALIVE_S = 180
DETACHED = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


def run_in_new_window(args):
    subprocess.Popen(args, cwd=str(ROOT), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


class Api:
    def __init__(self, store, runner=None, yolo_call=None, now=time.time):
        self._store = store
        self._run = runner or run_in_new_window
        self._yolo = yolo_call or yolo_switch.call
        self._now = now
        self._window = None     # set by main(); used for the save dialog

    def status(self):
        at = self._store.get_meta("collector_at")
        at = int(at) if at else None
        return {"collector_at": at, "collector_alive": bool(at) and self._now() - at < ALIVE_S,
                "items": self._store.current()}

    def _query(self, filters):
        f = filters or {}
        hours = f.get("hours")
        target = f.get("target") or None
        if target == "services":
            target = ["gateway", "tunnel", "camera", "watchdog", "disk", "public"]
        return {"target": target, "state": f.get("state") or None, "q": f.get("q") or None,
                "since": self._now() - float(hours) * 3600 if hours else None}

    def events(self, filters):
        f = filters or {}
        limit = max(1, min(500, int(f.get("limit") or 25)))
        return self._store.events(**self._query(f), limit=limit, offset=max(0, int(f.get("offset") or 0)))

    def check_now(self):
        self._store.set_meta("check_now", "1")
        return {"ok": True}

    def start_collector(self):
        try:
            subprocess.Popen([str(ROOT / ".venv" / "Scripts" / "pythonw.exe"), str(HERE / "collector.py")],
                             cwd=str(ROOT), creationflags=DETACHED, close_fds=True)
        except OSError as e:
            return {"ok": False, "message": str(e)}
        return {"ok": True, "message": "collector started"}

    def action(self, target, verb):
        if target in BAT_TARGETS and verb in BAT_VERBS:
            bat = ROOT / "launch" / target / f"{verb}.bat"
            # `start` opens the .bat in its own console window, like double-clicking the Desktop shortcut
            self._run(["cmd.exe", "/c", "start", "", str(bat)])
            return {"ok": True, "message": f"{verb} {target}: ran {bat.name} (the server runs in the background; see Processes)"}
        if target in YOLO_TARGETS and verb in ("yolo_on", "yolo_off"):
            want = verb == "yolo_on"
            try:
                out = self._yolo(SERVERS[target], "POST", {"enabled": want}, 120)
            except Exception as e:  # noqa: BLE001 - shown to the user as is
                return {"ok": False, "message": f"YOLO switch failed: {e}"}
            self.check_now()
            return {"ok": True, "message": f"YOLO {'on' if out.get('enabled') else 'off'} on {target}"}
        return {"ok": False, "message": "not allowed"}

    def processes(self):
        return [monitor_processes.info(n) for n in monitor_processes.NAMES]

    def log_tail(self, name, offset=None):
        if name not in monitor_processes.NAMES:
            return {"lines": [], "offset": 0, "reset": False, "error": "unknown"}
        return monitor_processes.tail(name, offset)

    def open_log(self, name):
        if name not in monitor_processes.NAMES:
            return {"ok": False}
        os.startfile(str(monitor_processes.LOG_DIR))     # the folder: the rotated files sit beside the newest
        return {"ok": True}

    def csv_text(self, filters):
        rows = self._store.events(**self._query(filters), limit=100000)["rows"]
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(["time", "target", "check", "from", "to", "detail"])
        for r in rows:
            w.writerow([datetime.fromtimestamp(r["ts"]).strftime("%Y-%m-%d %H:%M:%S"), r["target"], r["name"],
                        r["old"] or "", r["new"], r["detail"] or ""])
        return buf.getvalue()

    def export_csv(self, filters):
        import webview
        name = f"bkk-monitor-{datetime.now():%Y%m%d-%H%M}.csv"
        picked = self._window.create_file_dialog(webview.FileDialog.SAVE, save_filename=name,
                                                 file_types=("CSV files (*.csv)",))
        if not picked:
            return {"ok": False, "message": "cancelled"}
        path = picked if isinstance(picked, str) else picked[0]
        Path(path).write_text(self.csv_text(filters), encoding="utf-8-sig")
        return {"ok": True, "path": path}


def main():
    import webview
    api = Api(Store(DEFAULT_DB))
    api._window = webview.create_window("BKK Monitor", str(HERE / "ui" / "index.html"), js_api=api,
                                         width=1360, height=860, min_size=(980, 640), background_color="#0b0d10")
    webview.start()


if __name__ == "__main__":
    main()
