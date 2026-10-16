"""Step load test against the production origin (127.0.0.2:8000, the address cloudflared uses).

Each request carries a fake visitor IP (198.18.0.0/15, benchmark range) in CF-Connecting-IP so the
per-IP limiter sees many visitors, plus the page-session cookie and Sec-Fetch-Site like a browser.
Only endpoints that read background snapshots and cached map tiles are used: nothing here makes the
server call ThaiWater, MET Norway, Longdo, BMA or the AI gateway.
"""
import asyncio
import json
import multiprocessing as mp
import os
import random
import sys
import time

import aiohttp
import psutil

BASE = "http://127.0.0.2:8000"
PROCS = 4
STEPS = [int(s) for s in os.getenv("LT_STEPS", "").split(",") if s] or [50, 100, 200, 350, 500, 750, 1000, 1500, 2000]   # requests per second, all processes together
STEP_SECONDS = int(os.getenv("LT_SECONDS", "30"))
TIMEOUT = 10
STOP_ERR = 0.05
STOP_P95_MS = 3000

API = [  # (path, weight per visit): one dashboard visit plus its 60 s polls, plus a short look at the map
    ("/api/traffic/summary?top=25", 4), ("/api/traffic/guidance", 1), ("/api/traffic/areas", 4),
    ("/api/flood/status", 4), ("/api/flood/reports", 1), ("/api/air/stations", 1), ("/api/news", 1),
    ("/api/bma/analytics", 4), ("/api/alerts/recent?limit=20", 1), ("/api/cameras", 1), ("/api/ai/stats", 1),
    ("/api/survey/ranking", 1), ("/api/incidents", 2), ("/api/telemetry/online", 4),
    ("/api/cameras/all", 1), ("/api/cameras/down", 1),
]


def build_mix(assets, tiles):
    skip = set(filter(None, os.getenv("LT_SKIP", "").split(",")))
    mix = [("/", 1)] + [(a, 1) for a in assets] + [x for x in API if x[0] not in skip] + [("TILE", 6)]
    paths = [p for p, _ in mix]
    weights = [w for _, w in mix]
    return paths, weights, tiles


def fake_ip(rng):
    return f"198.{rng.randint(18, 19)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"


async def worker_main(idx, rate_q, out_q, cookie, assets, tiles):
    rng = random.Random(idx)
    paths, weights, tiles = build_mix(assets, tiles)
    pool = [fake_ip(rng) for _ in range(1500)]   # 6,000 visitors in all: far under 600 requests/min each
    conn = aiohttp.TCPConnector(limit=600, force_close=False)
    timeout = aiohttp.ClientTimeout(total=TIMEOUT)
    async with aiohttp.ClientSession(connector=conn, timeout=timeout) as http:
        while True:
            msg = rate_q.get()
            if msg is None:
                return
            rate, seconds = msg
            lat, codes, inflight, per = [], {}, set(), {}

            async def one(path):
                key = path
                if path == "TILE":
                    path = rng.choice(tiles)
                headers = {"CF-Connecting-IP": rng.choice(pool), "Cookie": f"bkk_s={cookie}",
                           "Sec-Fetch-Site": "same-origin" if path.startswith("/api/") else "none",
                           "Referer": "https://bkksmartstreet.com/", "Host": "bkksmartstreet.com",
                           "User-Agent": "Mozilla/5.0 loadtest"}
                t0 = time.perf_counter()
                try:
                    async with http.get(BASE + path, headers=headers) as r:
                        await r.read()
                        code = r.status
                except asyncio.TimeoutError:
                    code = "timeout"
                except Exception as e:  # noqa: BLE001
                    code = type(e).__name__
                ms = (time.perf_counter() - t0) * 1000
                lat.append(ms)
                per.setdefault(key, []).append((ms, code))
                codes[code] = codes.get(code, 0) + 1

            start = time.perf_counter()
            n = 0
            while time.perf_counter() - start < seconds:
                due = int((time.perf_counter() - start) * rate)
                while n < due:
                    path = rng.choices(paths, weights)[0]
                    t = asyncio.create_task(one(path))
                    inflight.add(t)
                    t.add_done_callback(inflight.discard)
                    n += 1
                await asyncio.sleep(0.005)
            if inflight:
                await asyncio.wait(inflight, timeout=TIMEOUT + 2)
            out_q.put((idx, lat, codes, n, per))


def worker(idx, rate_q, out_q, cookie, assets, tiles):
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(worker_main(idx, rate_q, out_q, cookie, assets, tiles))


def pct(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * p))]


def main():
    import re
    import urllib.request

    req = urllib.request.Request(BASE + "/", headers={"Host": "bkksmartstreet.com", "CF-Connecting-IP": "198.18.0.1"})
    with urllib.request.urlopen(req, timeout=10) as r:
        html = r.read().decode()
        cookie = re.search(r"bkk_s=([^;]+)", r.headers.get("set-cookie", "")).group(1)
    assets = sorted(set(re.findall(r'/assets/[^"]+\.(?:js|css)', html)))
    tile_dir = sys.argv[1]
    tiles = []
    for z in ("12", "13", "14"):
        zd = os.path.join(tile_dir, z)
        if not os.path.isdir(zd):
            continue
        for x in os.listdir(zd)[:200]:
            for y in os.listdir(os.path.join(zd, x))[:20]:
                tiles.append(f"/api/tiles/base/{z}/{x}/{y}")
    print(f"assets={assets} tiles={len(tiles)}", flush=True)

    server = None
    for c in psutil.net_connections("tcp"):
        if c.laddr and c.laddr.port == 8000 and c.status == psutil.CONN_LISTEN:
            server = psutil.Process(c.pid)
    server.cpu_percent(None)

    rate_qs = [mp.Queue() for _ in range(PROCS)]
    out_q = mp.Queue()
    procs = [mp.Process(target=worker, args=(i, rate_qs[i], out_q, cookie, assets, tiles)) for i in range(PROCS)]
    for p in procs:
        p.start()

    results = []
    try:
        for rate in STEPS:
            for q in rate_qs:
                q.put((rate / PROCS, STEP_SECONDS))
            t0 = time.time()
            lat, codes, sent, per = [], {}, 0, {}
            for _ in range(PROCS):
                _, l, c, n, pp = out_q.get()
                for k, v in pp.items():
                    per.setdefault(k, []).extend(v)
                lat += l
                sent += n
                for k, v in c.items():
                    codes[k] = codes.get(k, 0) + v
            took = time.time() - t0
            cpu = server.cpu_percent(None)
            rss = server.memory_info().rss / 2**20
            ok = codes.get(200, 0) + codes.get(304, 0)
            err = 1 - ok / max(1, sum(codes.values()))
            row = {"target_rps": rate, "done_rps": round(len(lat) / took), "sent": sent,
                   "p50_ms": round(pct(lat, .5)), "p95_ms": round(pct(lat, .95)), "p99_ms": round(pct(lat, .99)),
                   "err_pct": round(err * 100, 2), "codes": {str(k): v for k, v in codes.items()},
                   "server_cpu_pct": round(cpu), "server_rss_mb": round(rss)}
            row["per_path"] = {k: {"n": len(v), "p50": round(pct([m for m, _ in v], .5)), "p95": round(pct([m for m, _ in v], .95)), "bad": sum(1 for _, c in v if c not in (200, 304))} for k, v in sorted(per.items())}
            results.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
            if err > STOP_ERR or row["p95_ms"] > STOP_P95_MS:
                print("STOP: limit reached", flush=True)
                break
    finally:
        for q in rate_qs:
            q.put(None)
        for p in procs:
            p.join(timeout=20)
            if p.is_alive():
                p.terminate()
        with open(os.path.join(os.path.dirname(__file__), "results.json"), "w") as f:
            json.dump(results, f, indent=1)


if __name__ == "__main__":
    main()
