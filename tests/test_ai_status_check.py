import importlib.util
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("ai_status_mod", ROOT / "launch" / "ai_status.py")
ai = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ai)


def fake_fetch(responses):
    def fetch(port, path):
        val = responses.get(path.split("?")[0])
        if isinstance(val, Exception):
            raise val
        return val if val is not None else {}
    return fetch


def test_fresh_agent_is_ok_and_stale_agent_fails():
    now = time.time()
    resp = {
        "/api/ai/usage": {"callers": [{"caller": "backend.agents.flood_agent", "model": "qwen", "calls": 2,
                                        "errors": 0, "total_tokens": 900}], "covered_minutes": 60,
                          "calls": 2, "total_tokens": 900},
        "/api/flood/agent": {"report": {"generated_at": now - 60}},
        "/api/flood/analysis": {"feed_time": now - 10 * 3600, "updated_at": now - 10 * 3600},
    }
    out = ai.check_agents(8000, fetch=fake_fetch(resp))
    rows = {r["name"]: r for r in out["rows"]}
    assert rows["Bangkok flood report"]["state"] == "ok"
    assert rows["Bangkok flood report"]["calls"] == 2
    assert rows["Bangkok road water"]["state"] == "fail"
    assert rows["Bangkok road water"]["note"] == "data stale"
    assert "qwen" in out["summary"]


def test_endpoint_error_is_a_fail_row():
    resp = {"/api/ai/usage": {"callers": [], "covered_minutes": 5},
            "/api/flood/agent": OSError("boom")}
    rows = {r["name"]: r for r in ai.check_agents(8000, fetch=fake_fetch(resp))["rows"]}
    assert rows["Bangkok flood report"]["state"] == "fail"
    assert "endpoint error" in rows["Bangkok flood report"]["note"]


def test_usage_failure_raises():
    resp = {"/api/ai/usage": OSError("refused")}
    try:
        ai.check_agents(8000, fetch=fake_fetch(resp))
    except OSError:
        return
    raise AssertionError("expected OSError")


def test_chat_row_is_idle_without_calls():
    resp = {"/api/ai/usage": {"callers": [], "covered_minutes": 60}}
    rows = {r["name"]: r for r in ai.check_agents(8000, fetch=fake_fetch(resp))["rows"]}
    assert rows["Ask AI chat"]["state"] == "idle"
