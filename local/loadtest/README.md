# Load test

Step load test against a running server's origin. It never goes through Cloudflare.

    .venv\Scripts\python.exe -I local\loadtest\loadtest.py instances\production\cache\osm

- Each request carries a fake visitor IP from 198.18.0.0/15 (benchmark range) in CF-Connecting-IP, so the
  per-IP limiter sees many visitors. It also sends the page-session cookie and `Sec-Fetch-Site`, like a browser.
- Only endpoints that read background snapshots and cached map tiles are used. Nothing calls ThaiWater,
  MET Norway, Longdo, BMA or the AI gateway, and no telemetry is written.
- It stops by itself at > 5 % errors or p95 > 3 s. Real visitors feel each step: run it when the site is quiet.
- LT_STEPS=100,200 sets the steps (req/s), LT_SECONDS the seconds per step, LT_SKIP=/api/x leaves a path out.
  In Git Bash, set MSYS_NO_PATHCONV=1 when LT_SKIP starts with "/", or Git Bash rewrites it into a Windows path.
- Results go to results.json next to the script: per step, p50/p95/p99, error codes, server CPU and memory,
  and per-path latency.
