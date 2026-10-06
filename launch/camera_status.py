"""
Which cameras and camera websites can we really pull from right now? Every camera on the live camera page,
grouped by the website it comes from.

    launch\\camera_status.bat              production (:8000) in its own window, a new round every 5 min
                                          (launch\\production\\start.bat opens it, stop.bat closes it)
    launch\\camera_status.bat --once       production, one round, then a table
    launch\\camera_status.bat 8001         the test server
    launch\\camera_status.bat --watch 600  a new round every 10 minutes (Ctrl+C to stop)
    launch\\camera_status.bat --once --all every camera that is down, not only the first few per website

Each round:
    websites  each source's camera list or page answers (BMA: our scanner's own state, so BMA gets no extra requests)
    cameras   the camera list comes from the running server (/api/cameras/all on 127.0.0.1), then each camera is
              pulled the way the page pulls it:
                HLS     the playlist, and its first variant, must list video segments
                MJPEG   the first bytes must hold a JPEG
                picture the answer must be a picture (or the MP4 the BMA flood centre sends)
                Nakhon  the WebRTC server must have a stream on the camera's path
                Samui   the stream must send data
                BMA     the scanner got a frame from it in the last 20 minutes
                Pattaya only a link to the owner's site: the site is checked, not each camera
At most HOST_LIMIT requests go to one host at a time (fewer for SLOW_HOSTS), and a host that stops answering is skipped for the
rest of the round. Results go to <instance>\\camera_status.json. <instance>\\camera_status.log gets one CHECK line per
round (cameras working out of all, per website) and a DOWN or BACK line for every camera that changed since the last round.
"""
import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from backend.vision import doh_cameras as doh, world_cameras as wc  # noqa: E402 - the source URLs live there

TIMEOUT = 10
WORKERS = 48
HOST_LIMIT = 4              # requests at once to one host
HOST_GIVE_UP = 8            # this many connection failures in a row: the host's other cameras are not tried
# hosts that answer HTTP 429 to HOST_LIMIT at once: (requests at once, seconds between requests)
SLOW_HOSTS = {"nstcctv.nakhoncity.org": (1, 0.4)}
BMA_MAX_AGE = 20 * 60
USER_AGENT = wc.USER_AGENT
INSTANCES = {8000: "production", 8001: "test"}

# source -> label, in the order the report lists them
SOURCES = {
    "itic": "iTIC / Longdo",
    "doh": "DOH highways",
    "bma": "BMA traffic",
    "floodbkk": "BMA flood centre",
    "pattaya": "Pattaya",
    "nakhon": "Nakhon Si Thammarat",
    "dwr": "DWR river cameras",
    "pakkred": "Pak Kret",
    "samui": "Samui",
    "hatyai": "Hat Yai",
    "egat": "EGAT dams (ThaiWater)",
    "udon": "Udon Thani",
    "ddpm": "DDPM water cameras",
    "nonthaburi": "Nonthaburi city",
}
DWR_LIST = f"{wc.DWR_API}/public/reportCctv/listPaginate"
# source -> (url, POST body or None): the list or page each source's cameras are read from
SITES = {
    "itic": ("https://traffic.longdo.com/camera.json", None),
    "doh": (doh.PAGE, None),
    "floodbkk": (wc.FLOOD_LIST, None),
    "pattaya": (wc.PATTAYA_LIST, None),
    "nakhon": (wc.NAKHON_LIST, None),
    "dwr": (DWR_LIST, {"paginate": {"page": 1, "pageSize": 1, "orders": [{"key": "MAIN_BASIN", "desc": False}]}, "search": {}}),
    "pakkred": (wc.PAKKRED_PAGE, None),
    "samui": (wc.SAMUI_MAP, None),
    "hatyai": (wc.HATYAI_LIST, None),
    "egat": (wc.THAIWATER_LIST, None),
    "udon": (wc.UDON_LIST, None),
    "ddpm": (f"{wc.DDPM_API}/stations?limit=1", None),
    "nonthaburi": (wc.NONTHABURI_LIST, None),
}

TAG = "[CAM]"
LOG = False                 # --watch: log lines, scrolling like the server window
LEVEL_COLOR = {"INFO": "\033[32m", "WARNING": "\033[33m", "ERROR": "\033[31m"}
RESET = "\033[0m"


def log(level, text):
    print(f"{LEVEL_COLOR[level]}{level}{RESET}:{' ' * (9 - len(level))}{TAG} {datetime.now():%H:%M:%S}  {text}", flush=True)


class Down(Exception):
    """A camera or site we could not pull from; the message says why."""


class HostDown(Down):
    """The host did not answer at all (timeout, refused, DNS, TLS), as opposed to answering with an error."""


def fetch(url, body=None, headers=None, limit=65536, timeout=TIMEOUT):
    """(content type, first `limit` bytes) of a 200 answer; Down / HostDown otherwise."""
    req = urllib.request.Request(url, data=body, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.headers.get_content_type(), r.read(limit)
    except urllib.error.HTTPError as e:
        raise Down(f"HTTP {e.code}") from None
    except urllib.error.URLError as e:
        reason = e.reason
        if isinstance(reason, (socket.timeout, TimeoutError)):
            raise HostDown("timeout") from None
        if isinstance(reason, socket.gaierror):
            raise HostDown("host name not found") from None
        raise HostDown(str(reason)[:60]) from None
    except (socket.timeout, TimeoutError):
        raise HostDown("timeout") from None
    except (ConnectionError, OSError) as e:
        raise HostDown(str(e)[:60] or type(e).__name__) from None


def server(port, path, timeout=60):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# ---------------------------------------------------------------- one camera
def is_picture(ctype, data):
    return (ctype.startswith(("image/", "video/")) or ctype == "multipart/x-mixed-replace" or data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n"
            or data[:4] in (b"GIF8", b"RIFF") or data[4:8] == b"ftyp")


def probe_hls(url):
    _, data = fetch(url)
    text = data.decode("utf-8", "replace")
    if "#EXTM3U" not in text:
        raise Down("not a playlist")
    if "#EXT-X-STREAM-INF" in text:
        child = next((ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")), "")
        if not child:
            raise Down("playlist has no streams")
        _, data = fetch(urllib.parse.urljoin(url, child))
        text = data.decode("utf-8", "replace")
    if "#EXTINF" not in text:
        raise Down("playlist has no video")


def probe_picture(url):
    ctype, data = fetch(url, limit=4096)
    if not data:
        raise Down("empty answer")
    if not is_picture(ctype, data):
        raise Down(f"not a picture ({ctype})")


def probe_whep(embed_url):
    """Nakhon's player is MediaMTX WebRTC: its WHEP endpoint answers 404 when the path has no stream, and 400
    (our offer is not SDP) when it has one."""
    url = embed_url.split("?")[0].rstrip("/") + "/whep"
    try:
        fetch(url, b"v=0", {"Content-Type": "application/sdp"})
    except Down as e:
        if str(e) == "HTTP 400":
            return
        raise Down("no stream on the camera's path" if str(e) == "HTTP 404" else str(e)) from None


def probe_stream(url):
    _, data = fetch(url, limit=1024)
    if not data:
        raise Down("stream sent nothing")


def plan(cam, base):
    """(how, url) for one camera, or None when it is not probed (BMA: scanner, Pattaya: link only)."""
    src = cam.get("source") or "itic"
    if src in ("bma", "pattaya"):
        return None
    if cam.get("hls_url"):
        return probe_hls, cam["hls_url"]
    if cam.get("vdourl"):
        return probe_picture, cam["vdourl"]
    if cam.get("embed_url"):
        return probe_whep, cam["embed_url"]
    if cam.get("video_url"):
        return probe_stream, cam["video_url"]
    if cam.get("imgurl"):
        url = cam["imgurl"]
        return probe_picture, (base + url if url.startswith("/") else url)
    return False


# ---------------------------------------------------------------- one round
class Hosts:
    """At most HOST_LIMIT requests at once per host, and a host that stops answering is given up on."""

    def __init__(self):
        self.lock = threading.Lock()
        self.gates = {}
        self.fails = Counter()
        self.dead = {}

    def run(self, how, url):
        host = urllib.parse.urlparse(url).netloc
        limit, gap = SLOW_HOSTS.get(host, (HOST_LIMIT, 0))
        with self.lock:
            gate = self.gates.setdefault(host, threading.Semaphore(limit))
            if host in self.dead:
                raise Down(f"{self.dead[host]} (host given up)")
        with gate:
            with self.lock:
                if host in self.dead:
                    raise Down(f"{self.dead[host]} (host given up)")
            try:
                try:
                    how(url)
                except Down as e:
                    if str(e) != "HTTP 429":
                        raise
                    time.sleep(3)     # asked to slow down: one more try
                    how(url)
                finally:
                    time.sleep(gap)
            except HostDown as e:
                with self.lock:
                    self.fails[host] += 1
                    if self.fails[host] >= HOST_GIVE_UP:
                        self.dead.setdefault(host, str(e))
                raise
            with self.lock:
                self.fails[host] = 0


def check_sites(port):
    out = {}
    for src, (url, body) in SITES.items():
        t0 = time.time()
        try:
            data = json.dumps(body).encode() if body else None
            ctype, raw = fetch(url, data, {"Content-Type": "application/json"} if body else None,
                               limit=20 << 20, timeout=30)
            if not raw:
                raise Down("empty answer")
            if body or url.endswith(".json") or "json" in ctype:
                json.loads(raw.decode("utf-8", "replace"))
            out[src] = {"ok": True, "note": f"{len(raw) // 1024:,} KB in {time.time() - t0:.1f}s"}
        except (Down, ValueError) as e:
            out[src] = {"ok": False, "note": str(e) if isinstance(e, Down) else "answer is not JSON"}
    try:
        scan = server(port, "/api/bma/scan/status")
        s = scan.get("source") or {}
        age = time.time() - float(s.get("last_frame_at") or 0)
        ok = s.get("state") == "ok" and age < BMA_MAX_AGE
        out["bma"] = {"ok": ok, "note": f"scanner via {s.get('site', '?')}: {s.get('frames_ok', 0)} frames last cycle, "
                                        f"newest {int(age // 60)} min ago" + ("" if ok else f" (state {s.get('state')})")}
    except Exception as e:  # noqa: BLE001 - the scanner state is optional
        out["bma"] = {"ok": False, "note": f"scanner state unavailable: {e}"}
    return out


def bma_states(port):
    """camid -> (ok, reason) from the BMA scanner: a frame from the camera in the last BMA_MAX_AGE."""
    out = {}
    for c in server(port, "/api/bma/cameras").get("items") or []:
        try:
            age = time.time() - float(c.get("ts") or 0)
        except (TypeError, ValueError):
            age = float("inf")
        if c.get("status") != "online":
            out[f"BMA-{c.get('camid')}"] = (False, f"scanner: {c.get('status') or 'no frame'}")
        elif age > BMA_MAX_AGE:
            out[f"BMA-{c.get('camid')}"] = (False, f"no new frame for {int(age // 60)} min")
        else:
            out[f"BMA-{c.get('camid')}"] = (True, "")
    return out


def interleave(jobs):
    """Jobs ordered host by host in turn, so the workers are spread over the hosts."""
    by_host = defaultdict(deque)
    for j in jobs:
        by_host[urllib.parse.urlparse(j[2]).netloc].append(j)
    out = []
    while by_host:
        for host in list(by_host):
            out.append(by_host[host].popleft())
            if not by_host[host]:
                del by_host[host]
    return out


def check_round(port):
    t0 = time.time()
    base = f"http://127.0.0.1:{port}"
    sites = check_sites(port)
    cams = server(port, "/api/cameras/all", timeout=120).get("items") or []
    bma = bma_states(port)
    hosts = Hosts()
    results, jobs = {}, []
    for c in cams:
        src = c.get("source") or "itic"
        row = {"source": src, "name": c.get("short_title") or c.get("title") or c.get("camid"), "province": c.get("province") or ""}
        p = plan(c, base)
        if p is None and src == "bma":
            ok, why = bma.get(c["camid"], (False, "not in the scanner's list"))
            results[c["camid"]] = {**row, "state": "ok" if ok else "down", "reason": why}
        elif p is None:
            results[c["camid"]] = {**row, "state": "link", "reason": "link to the owner's site only"}
        elif p is False:
            results[c["camid"]] = {**row, "state": "down", "reason": "no stream or picture link"}
        else:
            jobs.append((c["camid"], row, p[1], p[0]))

    def one(job):
        camid, row, url, how = job
        try:
            hosts.run(how, url)
            return camid, {**row, "state": "ok", "reason": "", "url": url}
        except Down as e:
            return camid, {**row, "state": "down", "reason": str(e), "url": url}
        except Exception as e:  # noqa: BLE001 - one odd camera must not end the round
            return camid, {**row, "state": "down", "reason": f"{type(e).__name__}: {e}"[:80], "url": url}

    with ThreadPoolExecutor(WORKERS) as pool:
        results.update(pool.map(one, interleave(jobs)))
    return {"checked_at": int(time.time()), "took_s": round(time.time() - t0), "port": port, "probed": len(jobs),
            "sites": sites, "cameras": results}


# ---------------------------------------------------------------- report
def state_file(port):
    inst = os.path.join(ROOT, "instances", INSTANCES.get(port, "production"))
    return os.path.join(inst, "camera_status.json"), os.path.join(inst, "camera_status.log")


def load_previous(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("cameras") or {}
    except (OSError, ValueError):
        return {}


def save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(path + ".tmp", path)


def summary(data):
    """source -> {total, ok, down, link, reasons: Counter}"""
    out = {s: {"total": 0, "ok": 0, "down": 0, "link": 0, "reasons": Counter()} for s in SOURCES}
    for r in data["cameras"].values():
        s = out.setdefault(r["source"], {"total": 0, "ok": 0, "down": 0, "link": 0, "reasons": Counter()})
        s["total"] += 1
        s[r["state"]] += 1
        if r["state"] == "down":
            s["reasons"][r["reason"]] += 1
    return {k: v for k, v in out.items() if v["total"] or k in data["sites"]}


def reasons_text(reasons, n=3):
    return ", ".join(f"{why} ×{k}" for why, k in reasons.most_common(n))


def report(port, show_all=False, previous=None):
    """One round: check, save, print. Returns the number of websites down plus sources with no camera working."""
    path, logpath = state_file(port)
    if previous is None:
        previous = load_previous(path)
    try:
        data = check_round(port)
    except Exception as e:  # noqa: BLE001 - the server itself is the first thing to report
        if LOG:
            log("ERROR", f"[FAIL] server :{port} not answering ({e})")
        else:
            print(f"  [FAIL]  server :{port} not answering ({e})")
        return 1, None
    save(path, data)
    sums = summary(data)
    bad = 0
    stamp = datetime.fromtimestamp(data["checked_at"]).strftime("%Y-%m-%d %H:%M:%S")
    ok_total = sum(s["ok"] for s in sums.values())
    down_total = sum(s["down"] for s in sums.values())
    link_total = sum(s["link"] for s in sums.values())
    head = (f"{len(data['cameras']):,} cameras: {ok_total:,} working, {down_total:,} down, {link_total:,} link only · "
            f"{data['probed']:,} pulled in {data['took_s']}s")
    if LOG:
        log("INFO", head)
    else:
        print(f"Camera status  ·  server :{port}  ·  {stamp}")
        print(f"  {head}")
        print("-" * 104)
        print(f"  {'':6}  {'website':<24} {'cameras':>7} {'ok':>6} {'down':>6}  site / why down")
    for src, s in sums.items():
        label = SOURCES.get(src, src)
        site = data["sites"].get(src)
        site_txt = ("site ok" if site["ok"] else f"SITE DOWN: {site['note']}") if site else ""
        if s["link"]:
            state = "link" if site and site["ok"] else "fail"
            note = f"link only, {site_txt}"
        else:
            state = "ok" if not s["down"] else "warn" if s["ok"] else "fail"
            note = ", ".join(p for p in (site_txt if site and not site["ok"] else "", reasons_text(s["reasons"])) if p)
        if site and not site["ok"]:
            state = "fail"
        bad += state == "fail"
        mark = {"ok": "[ OK ]", "warn": "[WARN]", "fail": "[FAIL]", "link": "[LINK]"}[state]
        if LOG:
            level = {"ok": "INFO", "link": "INFO", "warn": "WARNING", "fail": "ERROR"}[state]
            counts = f"{s['total']} cameras" + ("" if s["link"] else f": {s['ok']} ok, {s['down']} down")
            log(level, f"{LEVEL_COLOR[level]}{mark}{RESET} {label:<24} {counts}" + (f" · {note}" if note else ""))
        else:
            ok_c = "–" if s["link"] else s["ok"]
            down_c = "–" if s["link"] else s["down"]
            print(f"  {mark}  {label:<24} {s['total']:>7} {ok_c!s:>6} {down_c!s:>6}  {note}")
    # cameras that went down or came back since the last round
    changes = []
    for camid, r in data["cameras"].items():
        before = (previous.get(camid) or {}).get("state")
        if before and before != r["state"] and "link" not in (before, r["state"]):
            changes.append(("DOWN" if r["state"] == "down" else "BACK", camid, r))
    per_site = " · ".join(f"{SOURCES.get(src, src)} " + ("link" if s["link"] else f"{s['ok']}/{s['total']}")
                          for src, s in sums.items())
    with open(logpath, "a", encoding="utf-8") as f:
        f.write(f"{stamp}  CHECK  {ok_total:,}/{len(data['cameras']):,} working · {per_site}"
                + (f" · {bad} website(s) not working" if bad else "") + "\n")
        for kind, camid, r in changes:
            f.write(f"{stamp}  {kind}  {camid}  {SOURCES.get(r['source'], r['source'])}  {r['name']}"
                    + (f"  ({r['reason']})" if r["reason"] else "") + "\n")
    if LOG:
        for kind, camid, r in changes[:30]:
            level = "ERROR" if kind == "DOWN" else "INFO"
            log(level, f"{kind}  {SOURCES.get(r['source'], r['source'])} · {r['name']} ({camid})" + (f" · {r['reason']}" if r["reason"] else ""))
        if len(changes) > 30:
            log("WARNING", f"... and {len(changes) - 30} more changes: see {logpath}")
        if not previous:
            log("INFO", f"first round: every camera's state is in {path}")
        log("INFO" if not bad else "ERROR", f"{down_total:,} cameras down · {len(changes)} changed since the last round"
            + ("" if not bad else f" · {bad} website(s) not working"))
    else:
        print("-" * 104)
        down = defaultdict(list)
        for camid, r in data["cameras"].items():
            if r["state"] == "down":
                down[r["source"]].append((camid, r))
        for src, rows in down.items():
            print(f"  down · {SOURCES.get(src, src)} ({len(rows)})")
            for camid, r in (rows if show_all else rows[:8]):
                print(f"      {camid:<28} {r['name'][:44]:<44} {r['reason']}")
            if not show_all and len(rows) > 8:
                print(f"      ... and {len(rows) - 8} more (--all lists every one)")
        print("-" * 104)
        print(f"  every camera: {path}")
        print(f"  changes:      {logpath}")
    return bad, data["cameras"]


def main(argv):
    port, watch, show_all = 8000, None, False
    args = list(argv)
    while args:
        a = args.pop(0)
        if a == "--once":
            watch = None
        elif a == "--all":
            show_all = True
        elif a == "--watch":
            watch = int(args.pop(0)) if args and args[0].isdigit() else 600
        elif a.isdigit():
            port = int(a)
    if os.name == "nt":
        os.system("")   # let the Windows console take the colour codes
    if watch is None:
        return 1 if report(port, show_all)[0] else 0
    global LOG
    LOG = True
    log("INFO", f"watching every camera and camera website of :{port} every {watch}s (Ctrl+C to stop)")
    previous = None
    try:
        while True:
            t0 = time.time()
            try:
                _, previous = report(port, previous=previous)
            except Exception as e:  # noqa: BLE001 - a bad round is logged, the window keeps watching
                log("ERROR", f"round failed: {e}")
            # server not answering yet (starting with production): try again in a minute
            time.sleep(60 if previous is None else max(30, watch - (time.time() - t0)))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
