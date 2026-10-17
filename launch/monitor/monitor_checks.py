"""
One round of the monitor's checks (launch\\monitor\\collector.py runs it every 30 s). Returns one status per check:
    server:<target>          production :8000 / test :8001 (/api/health), enviro :5050 (its page)
    agent:<target>:<name>    the AI agents, judged like launch\\ai_status.py (extra: the numbers for the Processes table)
    yolo:<target>:<name>     the YOLO switch and models, judged like launch\\yolo_status.py
    service:tunnel           the cloudflared Windows service
    service:camera           the camera status file (instances\\production\\camera_status.json) is fresh
    service:cam_bma/cam_itic BMA / ITIC cameras working and stopped, from the same camera status file
    service:gateway          the AI gateway (launch\\gateway_status.py), only when the caller says it is due
    service:watchdog         the "BKK StreetSmart watchdog" task still writes its heartbeat (state\\heartbeat)
    service:disk             free space on the data disk (production /api/health data_disk)
    service:public           bkksmartstreet.com and /enviro/ answer through Cloudflare, only when the gateway is due
A server that does not answer while launch\\watchdog\\state\\stopped_<port> exists was stopped on purpose: "stopped".
"""
import json
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
          "tunnel": "Cloudflare tunnel", "camera": "Camera status", "cam_bma": "BMA cameras", "cam_itic": "ITIC cameras",
          "watchdog": "Watchdog", "disk": "Data disk", "public": "Public site"}
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def stopped(port):
    return (STATE_DIR / f"stopped_{port}").exists()


def watchdog_age():
    """Seconds since the watchdog task last wrote its heartbeat (launch\\watchdog\\state\\heartbeat), None when missing."""
    try:
        return time.time() - (STATE_DIR / "heartbeat").stat().st_mtime
    except OSError:
        return None


def camera_age():
    """Seconds since the camera status file was written, None when it is missing."""
    try:
        return time.time() - CAMERA_STATUS.stat().st_mtime
    except OSError:
        return None


def camera_counts(source):
    """(site ok, working ids, stopped ids) of one camera source in the camera status file, None when unreadable."""
    try:
        data = json.loads(CAMERA_STATUS.read_text(encoding="utf-8"))
        cams = [(cid, c.get("state")) for cid, c in (data.get("cameras") or {}).items()
                if isinstance(c, dict) and c.get("source") == source]
        site_ok = ((data.get("sites") or {}).get(source) or {}).get("ok", False)
    except (OSError, ValueError, AttributeError, TypeError):
        return None
    return site_ok, [cid for cid, s in cams if s == "ok"], [cid for cid, s in cams if s == "down"]


def _camera_source_status(target, source):
    counts = camera_counts(source)
    if counts is None:
        return _status(f"service:{target}", "service", target, LABELS[target], "fail", "camera_status.json unreadable")
    site_ok, working, down = counts
    detail = f"{len(working)} working · {len(down)} stopped"
    if down:
        detail += ": " + ", ".join(down[:3]) + (f" +{len(down) - 3}" if len(down) > 3 else "")
    total = len(working) + len(down)
    if not site_ok or not working:
        state = "fail"
        if not site_ok:
            detail = f"{source} site not answering · " + detail
    elif len(down) > total * 0.2:
        state = "warn"
    else:
        state = "ok"
    return _status(f"service:{target}", "service", target, LABELS[target], state, detail)


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


PUBLIC_MAIN = "https://bkksmartstreet.com/"
PUBLIC_ENVIRO = "https://bkksmartstreet.com/enviro/"
# Cloudflare blocks the default Python-urllib User-Agent with 403; a browser-like one gets the page
PUBLIC_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BKKMonitor/1.0"


def _public_code(url):
    """The HTTP code the public URL answers with, 0 when nothing answers (DNS, TLS, timeout)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": PUBLIC_UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:  # noqa: BLE001 - no answer is the answer
        return 0


def public_status():
    return _public_code(PUBLIC_MAIN), _public_code(PUBLIC_ENVIRO)


def agents(port):
    return ai_status.check_agents(port)


def yolo(port, h):
    return yolo_status.check_yolo(port, health=h)


def _status(key, group, target, name, state, detail):
    return {"key": key, "group": group, "target": target, "name": name, "state": state, "detail": detail}


def _public_ok(code):
    return 200 <= code <= 399


def _public_text(code):
    if code == 0:
        return "no answer"
    if code == 403:
        return "blocked by Cloudflare (403)"
    return f"{code} {gateway_status.CLOUDFLARE[code]}" if code in gateway_status.CLOUDFLARE else str(code)


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
    prod_h = None
    for target in ("production", "test"):
        port = SERVERS[target]
        status, h = _server(target, port)
        out.append(status)
        if target == "production":
            prod_h = h
        if h is None:
            continue
        try:
            result = agents(port)
            for r in result["rows"]:
                parts = [f"data {r['data']}" if r["data"] else "", f"analysis {r['analysis']}" if r["analysis"] else "",
                         f"{r['calls']} calls" if r["calls"] != "" else "",
                         f"{r['fails']} failed" if r["fails"] else "",
                         f"{r['tokens']:,} tokens" if isinstance(r["tokens"], int) and r["tokens"] else "", r["note"]]
                extra = {"data": r["data"], "analysis": r["analysis"], "calls": r["calls"], "fails": r["fails"],
                         "tokens": r["tokens"] if isinstance(r["tokens"], int) else 0,
                         "window": round(result["window"]), "note": r["note"]}
                out.append({**_status(f"agent:{target}:{r['name']}", "agent", target, r["name"], r["state"],
                                      " · ".join(p for p in parts if p)), "extra": extra})
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
    prod = next(r["state"] for r in out if r["key"] == "server:production")
    if prod in ("ok", "warn"):
        age = camera_age()
        if age is not None and age < 900:
            out.append(_status("service:camera", "service", "camera", LABELS["camera"], "ok",
                               f"updated {int(age // 60)} min ago"))
            out.append(_camera_source_status("cam_bma", "bma"))
            out.append(_camera_source_status("cam_itic", "itic"))
        else:
            detail = f"camera_status.json is {int(age // 60)} min old" if age is not None else "camera_status.json missing"
            out.append(_status("service:camera", "service", "camera", LABELS["camera"], "fail", detail))
    elif stopped(8000):
        out.append(_status("service:camera", "service", "camera", LABELS["camera"], "stopped",
                           "production stopped on purpose"))
    else:
        # camera_status.py reads from :8000, so its file goes stale whenever production is down
        out.append(_status("service:camera", "service", "camera", LABELS["camera"], "idle",
                           "waiting for production"))
    camera = next(r for r in out if r["key"] == "service:camera")
    if camera["state"] != "ok":
        # no fresh counts: the BMA / ITIC cards follow the camera status card instead of keeping their last state
        for t in ("cam_bma", "cam_itic"):
            out.append(_status(f"service:{t}", "service", t, LABELS[t], camera["state"], camera["detail"]))
    age = watchdog_age()
    if age is None:
        out.append(_status("service:watchdog", "service", "watchdog", LABELS["watchdog"], "fail", "no heartbeat file"))
    elif age < 360:
        out.append(_status("service:watchdog", "service", "watchdog", LABELS["watchdog"], "ok", f"last run {int(age)} s ago"))
    else:
        out.append(_status("service:watchdog", "service", "watchdog", LABELS["watchdog"], "fail",
                           f"no run for {int(age // 60)} min (scheduled task 'BKK StreetSmart watchdog')"))
    disk = (prod_h or {}).get("data_disk")
    if prod_h is not None and disk:   # production did not answer: no row, the store keeps the last one
        free, total, path = disk["free_gb"], disk["total_gb"], disk["path"]
        state = "ok" if free >= 20 else "warn" if free >= 5 else "fail"
        out.append(_status("service:disk", "service", "disk", LABELS["disk"], state,
                           f"{free} GB free of {total} GB ({path})"))
    if gateway_due:
        try:
            proxy_ok, model_ok, proxy_note, model_note, secs = gateway()
            out.append(_status("service:gateway", "service", "gateway", LABELS["gateway"], "ok" if model_ok else "fail",
                               f"model {model_note} ({secs:.1f}s) · proxy {proxy_note}"))
        except Exception as e:  # noqa: BLE001
            out.append(_status("service:gateway", "service", "gateway", LABELS["gateway"], "fail", str(e)[:200]))
        try:
            main_c, enviro_c = public_status()
            # ENVIRO stopped on purpose makes /enviro/ fail on purpose: then only the main site is judged
            judge_enviro = not (not _public_ok(enviro_c) and stopped(SERVERS["enviro"]))
            ok = _public_ok(main_c) and (not judge_enviro or _public_ok(enviro_c))
            detail = f"bkksmartstreet.com {_public_text(main_c)} · /enviro/ {_public_text(enviro_c)}"
            if not judge_enviro:
                detail += " (ENVIRO stopped on purpose)"
            out.append(_status("service:public", "service", "public", LABELS["public"], "ok" if ok else "fail", detail))
        except Exception as e:  # noqa: BLE001
            out.append(_status("service:public", "service", "public", LABELS["public"], "fail", str(e)[:200]))
    return out
