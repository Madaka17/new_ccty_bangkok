"""
Is the AI model gateway answering? Checks the OpenAI-compatible endpoint behind LOCAL_LLM_URL (the Qwen
gateway the flood, traffic and vision agents share) straight from .env, without the server.

    launch\\gateway_status.bat              in its own window, checked every 5 minutes, beeps when the gateway comes back
    launch\\gateway_status.bat --once       once
    launch\\gateway_status.bat --watch 30   check every 30 seconds (Ctrl+C to stop)

Each check makes two requests:
    proxy   GET  /models              the gateway itself is up and the API key is accepted
    model   POST /chat/completions    one token from LOCAL_LLM_MODEL: the model server behind the gateway answers
The gateway sits behind Cloudflare, so a 52x on the model request means the model server is down while the
proxy still answers. The agents need the model request to work; once it does they recover on their next round
without a server restart. The one-token request takes one of the key's 3 parallel slots for a few seconds.
"""
import json
import os
import sys
import time
from datetime import datetime

import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAG = "[GATEWAY]"
LOG = False                 # --watch: one log line per check, scrolling like the server window
LEVEL_COLOR = {"INFO": "\033[32m", "WARNING": "\033[33m", "ERROR": "\033[31m"}
RESET = "\033[0m"
# Cloudflare answers these itself when it cannot reach the origin behind it
CLOUDFLARE = {520: "origin sent an unknown error", 521: "origin server is down", 522: "origin timed out",
              523: "origin unreachable", 524: "origin took too long to answer", 530: "origin DNS error"}


def load_env():
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(BASE_DIR, ".env"))
    except ImportError:
        pass
    url = os.getenv("LOCAL_LLM_URL", "http://localhost:1234/v1").rstrip("/")
    model = os.getenv("LOCAL_LLM_MODEL", "")
    key = os.getenv("LOCAL_LLM_API_KEY", "")
    try:
        extra = json.loads(os.getenv("LOCAL_LLM_EXTRA") or "{}")
    except ValueError:
        extra = {}
    return url, model, key, extra


def log(level, text):
    print(f"{LEVEL_COLOR[level]}{level}{RESET}:{' ' * (9 - len(level))}{TAG} {datetime.now():%H:%M:%S}  {text}", flush=True)


def why(r):
    """A short reason for a failed reply: the Cloudflare meaning, or the start of the error message."""
    if r.status_code in CLOUDFLARE:
        return f"{r.status_code} {CLOUDFLARE[r.status_code]}"
    try:
        err = r.json().get("error")
        msg = err.get("message") if isinstance(err, dict) else err
    except ValueError:
        msg = r.text
    return f"{r.status_code} {' '.join(str(msg or r.reason).split())[:80]}"


def check(url, model, key, extra):
    """Returns (proxy ok, model ok, proxy note, model note, model seconds)."""
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    try:
        r = requests.get(f"{url}/models", headers=headers, timeout=20)
        proxy_ok = r.ok
        ids = [m.get("id") for m in (r.json().get("data") or [])] if r.ok else []
        proxy_note = (f"{r.status_code}, {model} listed" if model in ids else f"{r.status_code}, {model} NOT listed") \
            if r.ok else why(r)
    except Exception as e:  # noqa: BLE001 - a dead proxy is the answer
        proxy_ok, proxy_note = False, f"no answer ({type(e).__name__})"
    if not model:
        return proxy_ok, False, proxy_note, "LOCAL_LLM_MODEL is empty (AI off)", 0
    body = {**extra, "model": model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1}
    t = time.time()
    try:
        r = requests.post(f"{url}/chat/completions", headers=headers, json=body, timeout=90)
        model_ok, model_note = r.ok, (f"{r.status_code} answered" if r.ok else why(r))
    except Exception as e:  # noqa: BLE001
        model_ok, model_note = False, f"no answer ({type(e).__name__})"
    return proxy_ok, model_ok, proxy_note, model_note, time.time() - t


def report(cfg):
    url, model = cfg[0], cfg[1]
    proxy_ok, model_ok, proxy_note, model_note, secs = check(*cfg)
    mark = lambda ok: "[ OK ]" if ok else "[FAIL]"
    if LOG:
        log("INFO" if model_ok else "ERROR",
            f"{mark(model_ok)} model {model_note} ({secs:.1f}s) · proxy {proxy_note}")
    else:
        print(f"AI gateway status  ·  {url}  ·  {datetime.now():%Y-%m-%d %H:%M:%S}")
        print("-" * 80)
        print(f"  {mark(proxy_ok)}  proxy   /models             {proxy_note}")
        print(f"  {mark(model_ok)}  model   {model:<19} {model_note} ({secs:.1f}s)")
        print("-" * 80)
        print("  gateway works: the agents recover on their next round" if model_ok else
              "  gateway not answering: the AI agents get no new analysis until it works")
    return model_ok


def main(argv):
    watch = 300
    args = list(argv)
    while args:
        a = args.pop(0)
        if a == "--once":
            watch = None
            break
        if a == "--watch":
            watch = int(args.pop(0)) if args and args[0].isdigit() else 300
    if os.name == "nt":
        os.system("")   # let the Windows console take the colour codes
    cfg = load_env()
    if watch is None:
        return 0 if report(cfg) else 1
    global LOG
    LOG = True
    log("INFO", f"watching {cfg[0]} ({cfg[1]}) every {watch}s (Ctrl+C to stop)")
    was = None
    try:
        while True:
            try:
                up = report(cfg)
                if was is False and up:
                    log("INFO", "\a*** gateway is BACK: the model answers again ***")
                elif was and not up:
                    log("ERROR", "\a*** gateway went DOWN ***")
                was = up
            except Exception as e:  # noqa: BLE001 - a bad round is logged, the window keeps watching
                log("ERROR", f"check failed: {e}")
            time.sleep(watch)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
