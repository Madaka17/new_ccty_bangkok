import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "launch"), str(ROOT / "launch" / "monitor")]
import monitor_notify as mn  # noqa: E402


def ev(old, new, key="server:production", target="production", name="Production"):
    return {"key": key, "target": target, "name": name, "old": old, "new": new, "detail": ""}


def test_rules():
    assert mn.worth_telling(ev("ok", "fail"))
    assert mn.worth_telling(ev(None, "fail"))
    assert mn.worth_telling(ev("ok", "warn"))
    assert mn.worth_telling(ev("fail", "ok"))
    assert not mn.worth_telling(ev("ok", "stopped"))
    assert not mn.worth_telling(ev("ok", "idle"))
    assert not mn.worth_telling(ev("stopped", "ok"))
    assert not mn.worth_telling(ev("fail", "fail"))
    assert mn.worth_telling(ev(None, "restart", key="watchdog:production"))
    assert not mn.worth_telling(ev(None, "warn", key="watchdog:production"))


def test_summary_bad_and_more():
    events = [ev("ok", "fail", key=f"agent:production:a{i}", name=f"a{i}") for i in range(6)]
    title, body = mn.summarize(events)
    assert title == "BKK Monitor: 6 problem(s)"
    assert body.count("\n") == 4 and body.endswith("+2 more")
    assert "Production · a0: fail" in body


def test_summary_back_and_none():
    assert mn.summarize([ev("fail", "ok")])[0] == "BKK Monitor: back to normal"
    assert mn.summarize([ev("ok", "stopped")]) is None
    assert mn.summarize([]) is None
