"""
Is YOLO really running? A status report of every YOLO model on a running server, for a terminal.

    launch\\yolo_status.bat              production (:8000) in its own window, refreshed every 10 s (like the server)
    launch\\yolo_status.bat --once       production, once
    launch\\yolo_status.bat 8001         the test server
    launch\\yolo_status.bat --watch 10   refresh every 10 seconds (Ctrl+C to stop)

It asks the server on 127.0.0.1 (a trusted address, so no browser session is needed) and judges each model by
recent work, not just by being switched on:
    YOLO26x, BMA camera scan   the 574 BMA cameras counted every 3 minutes: the last cycle must be recent
    YOLO26x, live AI camera    the camera the AI page plays: frames per second while someone watches
    helmet detector            the last helmet check must be recent
    wrong-way classifier       it must be learning the cameras' traffic directions from the scanned frames
plus the GPU memory in use (the models sit on the GPU while they run).
"""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime

SCAN_FRESH_S = 15 * 60      # /api/health calls the scan stale after this too
HELMET_FRESH_S = 15 * 60
TAG = "[YOLO]"
LOG = False                 # --watch: one log line per check, scrolling like the server window
LEVEL_COLOR = {"INFO": "[32m", "WARNING": "[33m", "ERROR": "[31m"}
RESET = "[0m"


def log(level, text):
    print(f"{LEVEL_COLOR[level]}{level}{RESET}:{' ' * (9 - len(level))}{TAG} {datetime.now():%H:%M:%S}  {text}", flush=True)


def say(text):
    """A plain line: printed as is in a one-off report, as an INFO line when watching."""
    if LOG:
        log("INFO", text.strip())
    else:
        print(text)


def get(port, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def ago(ts):
    if not ts:
        return "never"
    s = int(time.time() - ts)
    return f"{s}s ago" if s < 120 else f"{s // 60} min ago" if s < 7200 else f"{s // 3600} h ago"


def line(ok, name, detail):
    mark = {True: "[ OK ]", False: "[FAIL]", None: "[IDLE]"}[ok]
    if LOG:
        level = {True: "INFO", False: "ERROR", None: "WARNING"}[ok]
        log(level, f"{LEVEL_COLOR[level]}{mark}{RESET} {name:<28} {detail}")
    else:
        print(f"  {mark}  {name:<28} {detail}")


def report(port):
    if not LOG:
        print(f"YOLO status  ·  server :{port}  ·  {datetime.now():%Y-%m-%d %H:%M:%S}")
        print("-" * 78)
    try:
        h = get(port, "/api/health")
    except Exception as e:  # noqa: BLE001 - the server itself is the first thing to report
        line(False, "server", f"not answering on :{port} ({e})")
        return 1
    gpu = h.get("gpu")
    say(f"  server :{port} up {h['uptime_s'] // 60} min · GPU {gpu['name']} {gpu['used_mb']:,} / {gpu['total_mb']:,} MB in use"
        if gpu else f"  server :{port} up {h['uptime_s'] // 60} min · no GPU found: the models run on the CPU")
    if not LOG:
        print()
    bad = 0

    scan, src = h.get("scan") or {}, h.get("bma_source") or {}
    fresh = scan.get("age_s") is not None and scan["age_s"] < SCAN_FRESH_S
    state = "scanning now" if scan.get("running") else f"last cycle {scan['age_s']}s ago" if scan.get("age_s") is not None else "no cycle yet"
    working = bool(fresh or scan.get("running"))
    line(working if scan.get("cycle") else None, "YOLO26x  BMA camera scan", f"{state} · cycle {scan.get('cycle')} · frames {src.get('frames_ok', '–')} ok, {src.get('frames_new', '–')} new · source {src.get('state', '–')}")
    bad += bool(scan.get("cycle")) and not working

    ai = get(port, "/api/ai/stats")
    if ai.get("active"):
        live_ok = (ai.get("fps") or 0) > 0
        line(live_ok, f"{ai.get('model', 'YOLO')}  live AI camera", f"{ai.get('fps')} fps (target {ai.get('target_fps')}) · {ai.get('latency_ms')} ms · {ai.get('title') or ai.get('camid')} · {ai.get('total')} vehicles")
        bad += not live_ok
    else:
        why = f"camera offline ({ai.get('title') or ai.get('camid')})" if ai.get("stream_error") else "nobody is watching the AI page"
        line(None, f"{ai.get('model', 'YOLO')}  live AI camera", f"not playing: {why}")

    hs = get(port, "/api/helmet/status")
    if not hs.get("enabled"):
        line(None, "helmet detector", "switched off")
    else:
        recent = hs.get("last_check") and time.time() - hs["last_check"] < HELMET_FRESH_S
        t = hs.get("today") or {}
        line(bool(recent), f"helmet  {hs.get('local_detector', '')}",
             f"last check {ago(hs.get('last_check'))} · {hs.get('calls_last_hour')} checks/h · queue {hs.get('queue')} · today {t.get('captures', 0)} captures, {t.get('no_helmet', 0)} no helmet"
             + (f" · agent error: {hs['agent_error']}" if hs.get("agent_error") else ""))
        bad += not recent

    ww = get(port, "/api/wrongway/status")
    if not ww.get("enabled"):
        line(None, "wrong-way classifier", "switched off")
    else:
        learning = (ww.get("frames_seen") or 0) > 0
        t = ww.get("today") or {}
        line(learning, f"wrong-way  {ww.get('detector', '')}",
             f"{ww.get('frames_seen')} frames read · {ww.get('cameras_learned')}/{ww.get('cameras_seen')} cameras learned · today {t.get('captures', 0)} captures, {t.get('wrong_way', 0)} wrong way"
             + (f" · agent error: {ww['agent_error']}" if ww.get("agent_error") else ""))
        bad += not learning

    if LOG:
        log("INFO" if not bad else "ERROR", "all YOLO models are working" if not bad else f"{bad} model(s) not working")
    else:
        print("-" * 78)
        print("  all YOLO models are working" if not bad else f"  {bad} model(s) not working: see [FAIL] above")
    return 1 if bad else 0


def main(argv):
    port, watch = 8000, None
    args = list(argv)
    while args:
        a = args.pop(0)
        if a == "--once":
            watch = None
            break
        if a == "--watch":
            watch = int(args.pop(0)) if args and args[0].isdigit() else 10
        elif a.isdigit():
            port = int(a)
    if os.name == "nt":
        os.system("")   # let the Windows console take the colour codes
    if watch is None:
        return report(port)
    global LOG
    LOG = True
    log("INFO", f"watching the YOLO models on :{port} every {watch}s (Ctrl+C to stop)")
    try:
        while True:
            try:
                report(port)
            except Exception as e:  # noqa: BLE001 - a bad round is logged, the window keeps watching
                log("ERROR", f"check failed: {e}")
            time.sleep(watch)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
