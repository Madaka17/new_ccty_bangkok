"""
Are the AI agents really working? For every agent on a running server: did it fetch fresh data, and did it
really ask the model and get an analysis back?

    launch\\ai_status.bat              production (:8000) in its own window, refreshed every 30 s (like the server)
    launch\\ai_status.bat --once       production, once
    launch\\ai_status.bat 8001         the test server
    launch\\ai_status.bat --watch 30   refresh every 30 seconds (Ctrl+C to stop)

It asks the server on 127.0.0.1 (a trusted address, so no browser session is needed):
    data      the time the agent last read its sources; stale when older than about two refresh rounds
    analysis  the time of its last AI report, and the error it reports, if any
    calls     model requests the server really sent for that agent in the last hour (or since the server started), with failures and tokens,
              Gemini/Claude included
              (/api/ai/usage, counted where the request is made, so it cannot be faked by a cached report)
An agent works when its data is fresh and its last analysis is recent and without an error. An agent whose
picture has not changed does not ask the model again, so a recent report with no calls in the hour is fine.
"""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime

M, H = 60, 3600


def get(port, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def dig(d, path):
    for k in path.split("."):
        d = d.get(k) if isinstance(d, dict) else None
    return d


def ago(ts):
    if not ts:
        return "never"
    s = int(time.time() - ts)
    return f"{s}s" if s < 120 else f"{s // M}m" if s < 2 * H else f"{s // H}h"


# name, model caller (local_llm usage), endpoint, data time, AI time, error fields, data max age, AI max age
AGENTS = [
    ("Bangkok flood report", "backend.agents.flood_agent", "/api/flood/agent",
     "report.generated_at", "report.generated_at", ("error",), 15 * M, 30 * M),
    ("Bangkok road water", "backend.water.flood_service", "/api/flood/analysis",
     "feed_time", "updated_at", (), 30 * M, 30 * M),
    ("Road flood risk", "backend.traffic.road_service", "/api/roads/risk",
     "updated_at", "analysis.updated_at", ("error",), 15 * M, 60 * M),
    ("Bangkok districts (50)", "backend.water.bkk_districts", "/api/flood/bkk-districts",
     "updated_at", "ai.generated_at", ("error", "ai_error"), 70 * M, 4 * H),
    ("Provinces flood", "backend.water.province_flood", "/api/flood/provinces",
     "updated_at", "ai.generated_at", ("error", "ai_error"), 70 * M, 2 * H),
    ("National 7-day outlook", "backend.water.national_forecast", "/api/flood/forecast",
     "updated_at", "ai.generated_at", ("error", "ai_error"), 7 * H, 8 * H),
    ("Northern water route", "backend.water.north_route", "/api/water/north/route",
     "updated_at", "ai.generated_at", ("error", "ai_error"), 70 * M, 4 * H),
    ("Traffy flood reports", "backend.agents.traffy_agent", "/api/traffy/analysis",
     "generated_at", "generated_at", ("error",), 30 * M, 30 * M),
    ("Traffic guidance", "backend.traffic.guidance_service", "/api/traffic/guidance",
     "traffic_updated_at", "updated_at", (), 15 * M, 30 * M),
    ("Accident risk (riskbkk)", "backend.agents.riskbkk_agent", "/api/riskbkk/analysis",
     "generated_at", "generated_at", ("error",), 26 * H, 26 * H),
    ("Flood cameras (vision)", "backend.vision.flood_cam_service", "/api/flood/cameras",
     "last_check", "last_check", ("error",), 20 * M, 20 * M),
    ("Helmet check (vision)", "backend.vision.helmet_service", "/api/helmet/status",
     "last_check", "last_check", ("agent_error",), 20 * M, 20 * M),
]


TAG = "[AI]"
LOG = False                 # --watch: one log line per agent, scrolling like the server window
LEVEL_COLOR = {"INFO": "\033[32m", "WARNING": "\033[33m", "ERROR": "\033[31m"}
RESET = "\033[0m"


def log(level, text):
    print(f"{LEVEL_COLOR[level]}{level}{RESET}:{' ' * (9 - len(level))}{TAG} {datetime.now():%H:%M:%S}  {text}", flush=True)


def emit(state, name, data="", analysis="", calls="", fails="", tokens="", note=""):
    """One agent: a table row in a one-off report, a log line when watching. state: ok / fail / idle / warn."""
    mark = {"ok": "[ OK ]", "fail": "[FAIL]", "idle": "[IDLE]", "warn": "[WARN]"}[state]
    if LOG:
        level = {"ok": "INFO", "fail": "ERROR", "idle": "WARNING", "warn": "WARNING"}[state]
        parts = [f"data {data}" if data else "", f"analysis {analysis}" if analysis else "",
                 f"{calls} calls" + (f", {fails} failed" if fails else "") if calls != "" else "",
                 f"{tokens:,} tokens" if tokens else "", note]
        log(level, f"{LEVEL_COLOR[level]}{mark}{RESET} {name:<26} " + " · ".join(p for p in parts if p))
    else:
        tok = f"{tokens:,}" if isinstance(tokens, int) else tokens
        print(f"  {mark}  {name:<26} {data:>6}  {analysis:>8}  {calls!s:>7} {fails!s:>4} {tok:>9}  {note}")


def report(port):
    if not LOG:
        print(f"AI agent status  ·  server :{port}  ·  {datetime.now():%Y-%m-%d %H:%M:%S}")
    try:
        usage = get(port, "/api/ai/usage?minutes=60")
    except Exception as e:  # noqa: BLE001 - the server itself is the first thing to report
        emit("fail", "server", note=f"not answering on :{port} ({e})")
        return 1
    calls = {c["caller"]: c for c in usage.get("callers") or []}
    models = ", ".join(dict.fromkeys(c["model"] for c in usage.get("callers") or [])) or "–"
    window = usage.get("covered_minutes", 0)
    per_hour = usage.get("tokens_per_hour")
    summary = (f"models {models} · last {window:.0f} min: {usage.get('calls', 0)} requests, "
               f"{usage.get('total_tokens', 0):,} tokens" + (f" (~{per_hour:,}/h)" if per_hour else ""))
    if LOG:
        log("INFO", summary)
    else:
        print(f"  {summary}")
        print("-" * 104)
        print(f"  {'':6}  {'agent':<26} {'data':>6}  {'analysis':>8}  {'calls':>7} {'fail':>4} {'tokens':>9}  note")
    bad = 0
    for name, caller, path, data_f, ai_f, err_fs, data_max, ai_max in AGENTS:
        try:
            d = get(port, path)
        except Exception as e:  # noqa: BLE001 - one agent down leaves the others
            emit("fail", name, "–", "–", note=f"endpoint error: {e}")
            bad += 1
            continue
        data_t, ai_t = dig(d, data_f), dig(d, ai_f)
        err = next((dig(d, f) for f in err_fs if dig(d, f)), None)
        u = calls.get(caller) or {}
        fresh = bool(data_t) and time.time() - data_t <= data_max
        analysed = bool(ai_t) and time.time() - ai_t <= ai_max
        failed = u.get("errors", 0) > 0 and u.get("errors", 0) >= u.get("calls", 0)
        ok = fresh and analysed and not err and not failed
        note = str(err)[:60] if err else "model calls failing" if failed else \
            "source sent no readings" if not data_t else "data stale" if not fresh else "no recent analysis" if not analysed else \
            "picture unchanged, last report reused" if not u.get("calls") else ""
        emit("ok" if ok else "fail", name, ago(data_t), ago(ai_t), u.get("calls", 0), u.get("errors", 0), u.get("total_tokens", 0), note)
        bad += not ok
    chat = calls.get("backend.agents.chat_service") or {}
    emit("ok" if chat.get("calls") else "idle", "Ask AI chat", calls=chat.get("calls", 0), fails=chat.get("errors", 0),
         tokens=chat.get("total_tokens", 0), note="" if chat.get("calls") else "answers only when someone asks")
    try:
        ww = get(port, "/api/wrongway/status")
        u = calls.get("backend.vision.wrongway_service") or {}
        emit("ok" if ww.get("enabled") and not ww.get("agent_error") else "warn", f"Wrong-way check ({ww.get('agent')})",
             analysis=ago(ww.get("last_check")), calls=ww.get("calls_last_hour", 0), fails=u.get("errors", 0),
             tokens=u.get("total_tokens", 0), note=ww.get("agent_error") or "")
    except Exception:  # noqa: BLE001 - optional line
        pass
    # model callers with no row above (incident check, violation check, ...): still count their tokens
    shown = {a[1] for a in AGENTS} | {"backend.agents.chat_service", "backend.vision.wrongway_service"}
    for c in usage.get("callers") or []:
        if c["caller"] not in shown:
            emit("ok", c["caller"].rsplit(".", 1)[-1], calls=c["calls"], fails=c["errors"], tokens=c["total_tokens"],
                 note=c["model"])
    if LOG:
        log("INFO" if not bad else "ERROR", "all AI agents are fetching and analysing" if not bad else f"{bad} agent(s) not working")
    else:
        print("-" * 104)
        print(f"  data / analysis = how long ago · calls / tokens = real model requests in the last {window:.0f} min")
        print("  all AI agents are fetching and analysing" if not bad else f"  {bad} agent(s) not working: see [FAIL] above")
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
            watch = int(args.pop(0)) if args and args[0].isdigit() else 30
        elif a.isdigit():
            port = int(a)
    if os.name == "nt":
        os.system("")   # let the Windows console take the colour codes
    if watch is None:
        return report(port)
    global LOG
    LOG = True
    log("INFO", f"watching the AI agents on :{port} every {watch}s (Ctrl+C to stop)")
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
