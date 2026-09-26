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

The flood agent uses `default`. The chat bot uses `chat`, which reads the same names with a CHAT_LLM_
prefix and falls back to the LOCAL_LLM_ value for any it does not set, so the chat can point at another
endpoint (a hosted API, a LiteLLM proxy) while the flood agent stays on the local model. With the server
off or the model not loaded, both fall back to their Thai rule-based answers.
"""
import json
import os
import re

import requests

# Thai text runs about 2.2 characters per token on the Qwen tokenizer (measured on the chat context)
CHARS_PER_TOKEN = 2.2
_THINK = re.compile(r"<think>.*?</think>", re.S)


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
        resp = requests.post(f"{self.url}/chat/completions", json=body, headers=headers, timeout=timeout or self.timeout)
        if resp.status_code == 400 and "context" in resp.text:
            raise ContextTooLong(resp.text[:200])
        resp.raise_for_status()
        choice = resp.json()["choices"][0]
        text = _THINK.sub("", choice["message"].get("content") or "").strip()
        if not text:
            raise RuntimeError(f"empty reply (finish_reason={choice.get('finish_reason')})")
        return text


default = Client("LOCAL_LLM")
chat_client = Client("CHAT_LLM")
