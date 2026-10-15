"""
One round of the monitor's checks (launch\\monitor\\collector.py runs it every 30 s). Returns one status per check:
    server:<target>          production :8000 / test :8001 (/api/health), enviro :5050 (its page)
    agent:<target>:<name>    the AI agents, judged like launch\\ai_status.py
    yolo:<target>:<name>     the YOLO switch and models, judged like launch\\yolo_status.py
    service:tunnel           the cloudflared Windows service
    service:camera           the camera status file (instances\\production\\camera_status.json) is fresh
    service:gateway          the AI gateway (launch\\gateway_status.py), only when the caller says it is due
A server that does not answer while launch\\watchdog\\state\\stopped_<port> exists was stopped on purpose: "stopped".
"""
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "launch"))
import ai_status  # noqa: E402
import gateway_status  # noqa: E402
import yolo_status  # noqa: E402

STATE_DIR = ROOT / "launch" / "watchdog" / "state"
CAMERA_STATUS = ROOT / "instances" / "production" / "camera_status.json"
SERVERS = {"production": 8000, "test": 8001, "enviro": 5050}
LABELS = {"production": "Production", "test": "Test", "enviro": "ENVIRO", "gateway": "AI gateway",
          "tunnel": "Cloudflare tunnel", "camera": "Camera status"}
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def stopped(port):
    return (STATE_DIR / f"stopped_{port}").exists()


def camera_age():
    """Seconds since the camera status file was written, None when it is missing."""
    try:
        return time.time() - CAMERA_STATUS.stat().st_mtime
    except OSError:
        return None


def health(port):
    return yolo_status.get_health(port)


def http_up(port):
    """Like the watchdog: the page answers below 500."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=10) as r:
            return r.status < 500
    except urllib.error.HTTPError as e:
        return e.code < 500
    except Exception:  # noqa: BLE001 - no answer is the answer
        return False


def tunnel_running():
    try:
        out = subprocess.run(["sc", "query", "cloudflared"], capture_output=True, text=True, timeout=10,
                             creationflags=NO_WINDOW).stdout
    except Exception:  # noqa: BLE001
        return False
    return "RUNNING" in out


def gateway():
    return gateway_status.check(*gateway_status.load_env())


def agents(port):
    return ai_status.check_agents(port)


def yolo(port, h):
    return yolo_status.check_yolo(port, health=h)


def _status(key, group, target, name, state, detail):
    return {"key": key, "group": group, "target": target, "name": name, "state": state, "detail": detail}


def _uptime(s):
    return f"{s // 60} min" if s < 7200 else f"{s // 3600} h"


def _server(target, port):
    """(status, health or None)."""
    key, name = f"server:{target}", LABELS[target]
    try:
        h = health(port)
    except Exception as e:  # noqa: BLE001 - down or stopped
        if stopped(port):
            return _status(key, "server", target, name, "stopped", f":{port} stopped on purpose"), None
        return _status(key, "server", target, name, "fail", f":{port} not answering ({e})"), None
    gpu = h.get("gpu")
    detail = f":{port} up {_uptime(h.get('uptime_s', 0))}" + \
        (f" · GPU {gpu['used_mb'] / 1024:.1f} / {gpu['total_mb'] / 1024:.1f} GB" if gpu else "")
    state, detail = ("ok", detail) if h.get("ok") else ("warn", detail + " · BMA scan stale (health 503)")
    return {**_status(key, "server", target, name, state, detail), "uptime_s": h.get("uptime_s", 0)}, h


def run_round(gateway_due):
    out = []
    for target in ("production", "test"):
        port = SERVERS[target]
        status, h = _server(target, port)
        out.append(status)
        if h is None:
            continue
        try:
            for r in agents(port)["rows"]:
                parts = [f"data {r['data']}" if r["data"] else "", f"analysis {r['analysis']}" if r["analysis"] else "",
                         f"{r['calls']} calls" if r["calls"] != "" else "",
                         f"{r['fails']} failed" if r["fails"] else "",
                         f"{r['tokens']:,} tokens" if isinstance(r["tokens"], int) and r["tokens"] else "", r["note"]]
                out.append(_status(f"agent:{target}:{r['name']}", "agent", target, r["name"], r["state"],
                                   " · ".join(p for p in parts if p)))
        except Exception as e:  # noqa: BLE001 - the server answered health but not the agent checks
            out.append(_status(f"agent:{target}:checks", "agent", target, "agent checks", "fail", str(e)[:200]))
        try:
            for r in yolo(port, h)["rows"]:
                out.append(_status(f"yolo:{target}:{r['name']}", "yolo", target, r["name"], r["state"], r["detail"]))
        except Exception as e:  # noqa: BLE001
            out.append(_status(f"yolo:{target}:checks", "yolo", target, "YOLO checks", "fail", str(e)[:200]))
    port = SERVERS["enviro"]
    if http_up(port):
        out.append(_status("server:enviro", "server", "enviro", LABELS["enviro"], "ok", f":{port} answering"))
    elif stopped(port):
        out.append(_status("server:enviro", "server", "enviro", LABELS["enviro"], "stopped", f":{port} stopped on purpose"))
    else:
        out.append(_status("server:enviro", "server", "enviro", LABELS["enviro"], "fail", f":{port} not answering"))
    up = tunnel_running()
    out.append(_status("service:tunnel", "service", "tunnel", LABELS["tunnel"], "ok" if up else "fail",
                       "cloudflared service running" if up else "cloudflared service not running: site not public"))
    age = camera_age()
    if age is not None and age < 900:
        out.append(_status("service:camera", "service", "camera", LABELS["camera"], "ok",
                           f"updated {int(age // 60)} min ago"))
    elif stopped(8000):
        out.append(_status("service:camera", "service", "camera", LABELS["camera"], "stopped",
                           "production stopped on purpose"))
    else:
        detail = f"camera_status.json is {int(age // 60)} min old" if age is not None else "camera_status.json missing"
        out.append(_status("service:camera", "service", "camera", LABELS["camera"], "fail", detail))
    if gateway_due:
        try:
            proxy_ok, model_ok, proxy_note, model_note, secs = gateway()
            out.append(_status("service:gateway", "service", "gateway", LABELS["gateway"], "ok" if model_ok else "fail",
                               f"model {model_note} ({secs:.1f}s) · proxy {proxy_note}"))
        except Exception as e:  # noqa: BLE001
            out.append(_status("service:gateway", "service", "gateway", LABELS["gateway"], "fail", str(e)[:200]))
    return out
