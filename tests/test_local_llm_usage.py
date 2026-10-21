"""local_llm.note_cloud: Gemini and Claude replies are counted under the module that made the call."""
from types import SimpleNamespace

from backend.core import local_llm


def _mine():
    return next(c for c in local_llm.usage(5)["callers"] if c["caller"] == __name__)


def test_note_cloud_counts_gemini_and_claude(monkeypatch):
    monkeypatch.setattr(local_llm, "_usage", local_llm.deque())
    gemini = SimpleNamespace(usage_metadata=SimpleNamespace(prompt_token_count=1200, candidates_token_count=80,
                                                            thoughts_token_count=20))
    claude = SimpleNamespace(usage=SimpleNamespace(input_tokens=900, output_tokens=40))
    local_llm.note_cloud("gemini-3.5-flash-lite", gemini)
    local_llm.note_cloud("claude-opus-5-5", claude)
    mine = _mine()
    assert mine["calls"] == 2 and mine["errors"] == 0
    assert mine["prompt_tokens"] == 2100
    assert mine["reply_tokens"] == 140
    assert mine["total_tokens"] == 2240


def test_note_cloud_without_usage_counts_the_call(monkeypatch):
    monkeypatch.setattr(local_llm, "_usage", local_llm.deque())
    local_llm.note_cloud("gemini-3.5-flash-lite", SimpleNamespace(usage_metadata=SimpleNamespace(
        prompt_token_count=None, candidates_token_count=None)))
    mine = _mine()
    assert mine["calls"] == 1 and mine["total_tokens"] == 0


def test_429_logs_which_limit_without_the_key(monkeypatch, capsys):
    import pytest
    import requests
    monkeypatch.setattr(local_llm, "_usage", local_llm.deque())
    monkeypatch.setattr(local_llm, "RETRY_429", (0, 0))
    monkeypatch.setenv("LOCAL_LLM_URL", "http://gateway.test/v1")
    resp = requests.Response()
    resp.status_code = 429
    resp._content = (b'{"error":{"message":"Max parallel request limit reached. Hit limit for api_key: '
                     b'3f2a9c1e5b7d4a6f8e0c2b4d6f8a0c1e2b3d4f5a. max_parallel_requests: 3 sk-abc123"}}')
    resp.headers.update({"retry-after": "1", "x-ratelimit-remaining-requests": "0", "content-type": "text/json"})
    calls = []
    monkeypatch.setattr(local_llm.requests, "post", lambda *a, **k: calls.append(1) or resp)
    with pytest.raises(requests.HTTPError):
        local_llm.Client().chat([{"role": "user", "content": "hi"}], caller="tests.x")
    out = capsys.readouterr().out
    assert len(calls) == 3
    assert "[LocalLLM] 429 for tests.x" in out and "max_parallel_requests: 3" in out
    assert "retry-after" in out and "x-ratelimit-remaining-requests" in out
    assert "3f2a9c1e" not in out and "sk-abc123" not in out
