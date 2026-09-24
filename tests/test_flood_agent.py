"""Flood agent: local model report, offline rules, the level floor, skipping unchanged runs, and the alert it feeds."""
import json
import time

import local_llm
from alert_service import AlertService
from flood_agent import REPORT_SCHEMA, FloodAgent


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


def _report(level="critical", roads=()):
    return {"overall_level": level, "headline": "บางนาน้ำท่วมหนัก", "summary": "", "districts": [{"name": "บางนา", "level": level,
            "reason": "", "outlook": ""}], "roads_to_avoid": list(roads), "outlook": "",
            "actions": {"public": [], "operators": []}, "confidence": "high", "data_gaps": [], "answer": ""}


def _agent(tmp_path, monkeypatch, reply=None, **kw):
    """reply: the report the fake local model returns, an exception to raise, or None for the model off."""
    monkeypatch.setattr(local_llm.default, "model", "qwen" if reply is not None else "")
    seen = []

    def fake_chat(messages, **opts):
        seen.append((messages, opts))
        if isinstance(reply, Exception):
            raise reply
        return "```json\n" + json.dumps(reply, ensure_ascii=False) + "\n```"
    monkeypatch.setattr(local_llm.default, "chat", fake_chat)
    agent = FloodAgent(str(tmp_path), _sources(**kw))
    agent.seen = seen
    return agent


def test_rules_report_when_model_off(tmp_path, monkeypatch):
    rep = _agent(tmp_path, monkeypatch, cm=65, traffy=3).run(force=True)
    assert rep["source"] == "rules"
    assert rep["overall_level"] == "warning"       # canal over its bank, one road over 60 cm
    assert rep["roads_to_avoid"][0]["advice"] == "ห้ามขับผ่าน"
    assert {d["name"] for d in rep["districts"]} >= {"บางนา", "ประเวศ"}


def test_local_model_report(tmp_path, monkeypatch):
    agent = _agent(tmp_path, monkeypatch, reply=_report())
    rep = agent.run(force=True)
    assert rep["source"] == "local" and rep["model"] == "qwen" and rep["overall_level"] == "critical"
    messages, opts = agent.seen[0]
    assert opts["json_schema"] is REPORT_SCHEMA
    assert "หน้าวัด" in messages[1]["content"]                 # the facts go into the prompt
    assert {s["tool"] for s in rep["steps"]} >= {"get_road_sensors", "get_rain_outlook"}


def test_local_model_level_floor_and_measured_roads(tmp_path, monkeypatch):
    roads = [{"road": "ก", "district": "", "depth_cm": 0, "advice": ""}, {"road": "ข", "district": "", "depth_cm": 30, "advice": ""}]
    rep = _agent(tmp_path, monkeypatch, reply=_report("normal", roads), cm=65).run(force=True)
    assert rep["overall_level"] == "warning"                # canal over its bank + 65 cm road
    assert [r["road"] for r in rep["roads_to_avoid"]] == ["ข"]


def test_model_failure_falls_back_to_rules(tmp_path, monkeypatch):
    agent = _agent(tmp_path, monkeypatch, reply=RuntimeError("connection refused"))
    rep = agent.run(force=True)
    assert rep["source"] == "rules"
    assert "connection refused" in agent.status()["error"]


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


def test_critical_report_raises_zone_alert(tmp_path, monkeypatch):
    agent = _agent(tmp_path, monkeypatch, reply=_report())
    agent.run(force=True)
    svc = AlertService(str(tmp_path), {"agent": lambda: agent.status()["report"]})
    found = [c for c in svc.candidates() if c["key"] == "agent:overall"]
    assert found and found[0]["level"] == 2


def test_report_schema_is_strict_ready():
    assert REPORT_SCHEMA["additionalProperties"] is False
    assert set(REPORT_SCHEMA["required"]) == set(REPORT_SCHEMA["properties"])
