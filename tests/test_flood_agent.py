"""Flood agent: tool loop with a fake Claude, offline rules, skipping unchanged runs, and the alert it feeds."""
import time
from types import SimpleNamespace

import flood_agent
from alert_service import AlertService
from flood_agent import FloodAgent


def _sources(cm=30, traffy=0):
    now = time.time()
    return {
        "flood": lambda: {"counts": {"flood": 1, "slight": 0}, "districts": [],
                          "wet": [{"name": "หน้าวัด", "short_name": "หน้าวัด", "road": "ถนนสุขุมวิท", "district": "บางนา",
                                   "level_cm": cm, "trend": "rising", "delta_cm": 4}]},
        "water": lambda: {"river": [], "canals": [{"name": "คลองประเวศ", "district": "ประเวศ", "level": "overflow", "storage_pct": 104}],
                          "weather": [{"name": "ตะวันออก", "watch": "orange", "rain_6h": 20, "rain_24h": 45}]},
        "forecast": lambda: {"prediction": [{"zone": "ตะวันออก", "peak_score": 72, "hours": [{"h": 1, "score": 72, "cum_mm": 12}]}]},
        "traffy": lambda: {"items": [{"district": "บางนา", "ts": now - 600, "depth": "เข่า", "text": "น้ำท่วม"}] * traffy},
        "tmd": lambda: {"active": []},
        "road_risk": lambda: {"items": []},
        "bma_events": lambda: [],
    }


def _agent(tmp_path, monkeypatch, client=None, **kw):
    monkeypatch.setattr(FloodAgent, "_claude", staticmethod(lambda: client))
    monkeypatch.setattr(FloodAgent, "_gemini", staticmethod(lambda: None))
    return FloodAgent(str(tmp_path), _sources(**kw))


def test_rules_report_without_keys(tmp_path, monkeypatch):
    rep = _agent(tmp_path, monkeypatch, cm=65, traffy=3).run(force=True)
    assert rep["source"] == "rules"
    assert rep["overall_level"] == "warning"       # canal over its bank, one road over 60 cm
    assert rep["roads_to_avoid"][0]["advice"] == "ห้ามขับผ่าน"
    assert {d["name"] for d in rep["districts"]} >= {"บางนา", "ประเวศ"}


def test_unchanged_facts_skip_the_timed_run(tmp_path, monkeypatch):
    agent = _agent(tmp_path, monkeypatch)
    first = agent.run()
    assert agent.run()["generated_at"] == first["generated_at"]
    assert len(agent.history) == 1


def test_question_does_not_replace_standing_report(tmp_path, monkeypatch):
    agent = _agent(tmp_path, monkeypatch)
    standing = agent.run(force=True)
    asked = agent.run(question="บางนาท่วมไหม")
    assert asked["question"] == "บางนาท่วมไหม"
    assert agent.status()["report"]["generated_at"] == standing["generated_at"]


class _FakeClaude:
    """Asks for two tools in parallel, then submits a report built from what it saw."""
    def __init__(self):
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls.append(kw)
        block = lambda **b: SimpleNamespace(**b)
        if len(self.calls) == 1:
            return SimpleNamespace(stop_reason="tool_use", content=[
                block(type="tool_use", id="t1", name="get_road_sensors", input={}),
                block(type="tool_use", id="t2", name="get_citizen_reports", input={"hours": 2}),
            ])
        return SimpleNamespace(stop_reason="tool_use", content=[block(type="tool_use", id="t3", name="submit_report", input={
            "overall_level": "critical", "headline": "บางนาน้ำท่วมหนัก", "summary": "", "districts": [],
            "roads_to_avoid": [], "outlook": "", "actions": {"public": [], "operators": []},
            "confidence": "high", "data_gaps": [], "answer": ""})])


def test_claude_tool_loop(tmp_path, monkeypatch):
    fake = _FakeClaude()
    rep = _agent(tmp_path, monkeypatch, client=fake).run(force=True)
    assert rep["source"] == "claude" and rep["overall_level"] == "critical"
    assert [s["tool"] for s in rep["steps"]] == ["get_road_sensors", "get_citizen_reports"]
    results = fake.calls[1]["messages"][2]["content"]    # task, assistant tool calls, tool results
    assert [r["tool_use_id"] for r in results] == ["t1", "t2"]     # both results in one user message
    assert "หน้าวัด" in results[0]["content"]


def test_critical_report_raises_zone_alert(tmp_path, monkeypatch):
    agent = _agent(tmp_path, monkeypatch, client=_FakeClaude())
    agent.run(force=True)
    svc = AlertService(str(tmp_path), {"agent": lambda: agent.status()["report"]})
    found = [c for c in svc.candidates() if c["key"] == "agent:overall"]
    assert found and found[0]["level"] == 2


def test_local_model_level_floor(tmp_path, monkeypatch):
    agent = _agent(tmp_path, monkeypatch, cm=65)
    monkeypatch.setattr(flood_agent, "LOCAL_MODEL", "qwen")
    monkeypatch.setattr(agent, "_run_local", lambda facts, q: {
        "overall_level": "normal", "headline": "ปกติ", "summary": "", "districts": [], "outlook": "",
        "roads_to_avoid": [{"road": "ก", "district": "", "depth_cm": 0, "advice": ""},
                           {"road": "ข", "district": "", "depth_cm": 30, "advice": ""}],
        "actions": {"public": [], "operators": []}, "confidence": "high", "data_gaps": [], "answer": ""})
    rep = agent.run(force=True)
    assert rep["source"] == "local"
    assert rep["overall_level"] == "warning"                # canal over its bank + 65 cm road
    assert [r["road"] for r in rep["roads_to_avoid"]] == ["ข"]


def test_tools_schema_is_strict_ready():
    submit = next(t for t in flood_agent.TOOLS if t["name"] == "submit_report")
    schema = submit["input_schema"]
    assert submit["strict"] and schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
