"""
The AI model the server talks to: any OpenAI-compatible chat endpoint, local by default.

LM Studio serves one at http://localhost:1234/v1 (Ollama: http://localhost:11434/v1). The default model is
qwen3.5-4b, a small thinking model, so reasoning is switched off by default: the callers paste in every
fact already, and with thinking on the model spends its whole token budget reasoning and returns nothing.

    LOCAL_LLM_URL         server base URL                       http://localhost:1234/v1
    LOCAL_LLM_MODEL       model id as the server lists it       qwen3.5-4b (empty = AI off)
    LOCAL_LLM_API_KEY     bearer token, if the server wants one (empty = none)
    LOCAL_LLM_REASONING   reasoning_effort sent with a request  none (empty = do not send)
    LOCAL_LLM_CONTEXT     context length of the model, in tokens    8192
    LOCAL_LLM_TIMEOUT     seconds per request                   240
    LOCAL_LLM_EXTRA       extra request fields as JSON; vLLM Qwen ignores reasoning_effort and turns
                          thinking off with {"chat_template_kwargs": {"enable_thinking": false}}
    LOCAL_LLM_MAX_PARALLEL  requests in flight at once per endpoint + key   3

The gateway behind LOCAL_LLM_URL allows 3 requests in flight per key (LiteLLM max_parallel_requests) and
answers 429 to a 4th. The flood watch, the helmet patrol, the agents and the chat bot all share that key,
so every Client waits for one of MAX_PARALLEL slots per endpoint + key, and retries a 429 twice.

The flood agent uses `default`. The chat bot uses `chat`, which reads the same names with a CHAT_LLM_
prefix and falls back to the LOCAL_LLM_ value for any it does not set, so the chat can point at another
endpoint (a hosted API, a LiteLLM proxy) while the flood agent stays on the local model. With the server
off or the model not loaded, both fall back to their Thai rule-based answers.

Every request is counted by the module that made it, with the prompt and reply tokens the server reports
(`usage` in the OpenAI-compatible reply; image tokens are part of the prompt). usage() sums any window of
the last USAGE_KEEP_H hours for /api/ai/usage.
"""
import json
import os
import re
import sys
import threading
import time
from collections import deque

import requests

# Thai text runs about 2.2 characters per token on the Qwen tokenizer (measured on the chat context)
CHARS_PER_TOKEN = 2.2
_THINK = re.compile(r"<think>.*?</think>", re.S)
MAX_PARALLEL = int(os.getenv("LOCAL_LLM_MAX_PARALLEL", "3"))
RETRY_429 = (2, 5)   # seconds to wait before each retry of a 429
_slots = {}          # (url, api_key) -> BoundedSemaphore shared by every Client on that endpoint + key
_slots_lock = threading.Lock()


def _slot(url, api_key):
    with _slots_lock:
        return _slots.setdefault((url, api_key), threading.BoundedSemaphore(MAX_PARALLEL))


USAGE_KEEP_H = 24
_usage = deque()     # (time, caller module, model, prompt tokens, reply tokens, seconds, ok)
_usage_lock = threading.Lock()
_started = time.time()


def _record(caller, model, prompt, reply, seconds, ok):
    now = time.time()
    with _usage_lock:
        _usage.append((now, caller, model, prompt, reply, seconds, ok))
        while _usage and _usage[0][0] < now - USAGE_KEEP_H * 3600:
            _usage.popleft()


def note_cloud(model, resp):
    """Count a Gemini or Claude reply made outside Client.chat under the calling module, so /api/ai/usage
    shows the cloud tokens too (Gemini: usage_metadata, thinking counted as reply; Claude: usage)."""
    caller = sys._getframe(1).f_globals.get("__name__", "?")
    gem = getattr(resp, "usage_metadata", None)
    if gem is not None:
        prompt = gem.prompt_token_count or 0
        reply = (gem.candidates_token_count or 0) + (getattr(gem, "thoughts_token_count", 0) or 0)
    else:
        used = getattr(resp, "usage", None)
        prompt, reply = getattr(used, "input_tokens", 0) or 0, getattr(used, "output_tokens", 0) or 0
    _record(caller, model, int(prompt), int(reply), 0.0, True)


def usage(minutes=30):
    """Requests and tokens per calling module over the last `minutes` (as far back as the server has run)."""
    now = time.time()
    since = now - minutes * 60
    with _usage_lock:
        rows = [u for u in _usage if u[0] >= since]
    by = {}
    for _, caller, model, prompt, reply, seconds, ok in rows:
        d = by.setdefault(caller, {"caller": caller, "model": model, "calls": 0, "errors": 0, "prompt_tokens": 0,
                                   "reply_tokens": 0, "seconds": 0.0})
        d["calls"] += 1
        d["errors"] += 0 if ok else 1
        d["prompt_tokens"] += prompt
        d["reply_tokens"] += reply
        d["seconds"] += seconds
    callers = sorted(by.values(), key=lambda d: -(d["prompt_tokens"] + d["reply_tokens"]))
    for d in callers:
        d["total_tokens"] = d["prompt_tokens"] + d["reply_tokens"]
        d["avg_tokens"] = round(d["total_tokens"] / max(1, d["calls"] - d["errors"]))
        d["seconds"] = round(d["seconds"], 1)
    covered = min(minutes * 60, now - _started)
    total = sum(d["total_tokens"] for d in callers)
    return {"minutes": minutes, "covered_minutes": round(covered / 60, 1), "calls": sum(d["calls"] for d in callers),
            "prompt_tokens": sum(d["prompt_tokens"] for d in callers), "reply_tokens": sum(d["reply_tokens"] for d in callers),
            "total_tokens": total, "tokens_per_hour": round(total * 3600 / covered) if covered >= 300 else None,
            "callers": callers}


# The gateway's Qwen sometimes writes Thai marks out of order with a long Thai prompt: a tone mark before the
# vowel above it ("น้ี" for "นี้"), the same mark twice ("ขััด"), or nikhahit + sara aa for sara am ("น้ํา").
# These look broken in the browser, so they are put back in Unicode order before any caller sees the text.
_TONE_FIRST = re.compile(r"([่-์])([ัิ-ฺ็])")
_TWICE = re.compile(r"([ัิ-ฺ็-๎])\1+")


def fix_thai(text):
    """Thai combining marks in their proper order, each once."""
    text = text.replace("ํา", "ำ")
    text = _TONE_FIRST.sub(r"\2\1", text)
    return _TWICE.sub(r"\1", text)


class ContextTooLong(Exception):
    """The prompt does not fit the context the model is loaded with."""


class Client:
    def __init__(self, prefix="LOCAL_LLM"):
        def env(name, default):
            v = os.getenv(f"{prefix}_{name}")
            if v is None:
                v = os.getenv(f"LOCAL_LLM_{name}", default)
            return v.strip()
        self.url = env("URL", "http://localhost:1234/v1").rstrip("/")
        self.model = env("MODEL", "qwen3.5-4b")
        self.api_key = env("API_KEY", "")
        self.reasoning = env("REASONING", "none")
        self.context = int(env("CONTEXT", "8192"))
        self.timeout = int(env("TIMEOUT", "240"))
        # extra request fields as JSON, e.g. {"chat_template_kwargs": {"enable_thinking": false}} for vLLM
        self.extra = json.loads(env("EXTRA", "") or "{}")

    def enabled(self):
        return bool(self.model)

    def token_budget(self, *texts, reply_tokens=0):
        """Tokens left in the context after these texts and the reply, by the character estimate."""
        used = sum(len(t or "") for t in texts) / CHARS_PER_TOKEN
        return int(self.context - used - reply_tokens)

    def chat(self, messages, max_tokens=1200, temperature=0.4, json_schema=None, timeout=None):
        """messages: [{role: system|user|assistant, content}]. Returns the reply text (thinking stripped)."""
        body = {"model": self.model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature,
                **self.extra}
        if self.reasoning:
            body["reasoning_effort"] = self.reasoning
        if json_schema:
            body["response_format"] = {"type": "json_schema",
                                       "json_schema": {"name": "reply", "strict": True, "schema": json_schema}}
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        timeout = timeout or self.timeout
        caller = sys._getframe(1).f_globals.get("__name__", "?")
        started = time.time()
        slot = _slot(self.url, self.api_key)
        if not slot.acquire(timeout=timeout):
            raise RuntimeError(f"no free slot on the AI endpoint in {timeout}s ({MAX_PARALLEL} in flight)")
        try:
            for wait in (*RETRY_429, None):
                resp = requests.post(f"{self.url}/chat/completions", json=body, headers=headers, timeout=timeout)
                if resp.status_code != 429 or wait is None:
                    break
                time.sleep(wait)
        finally:
            slot.release()
        if not resp.ok:
            _record(caller, self.model, 0, 0, time.time() - started, False)
        if resp.status_code == 400 and "context" in resp.text:
            raise ContextTooLong(resp.text[:200])
        resp.raise_for_status()
        data = resp.json()
        used = data.get("usage") or {}
        _record(caller, self.model, int(used.get("prompt_tokens") or 0), int(used.get("completion_tokens") or 0),
                time.time() - started, True)
        choice = data["choices"][0]
        text = fix_thai(_THINK.sub("", choice["message"].get("content") or "").strip())
        if not text:
            raise RuntimeError(f"empty reply (finish_reason={choice.get('finish_reason')})")
        return text


default = Client("LOCAL_LLM")
chat_client = Client("CHAT_LLM")
