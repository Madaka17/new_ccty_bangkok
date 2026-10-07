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
