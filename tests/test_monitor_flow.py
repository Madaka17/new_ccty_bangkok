from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "launch"), str(ROOT / "launch" / "monitor")]
import monitor_flow  # noqa: E402

SINCE = 1760000000.0


def row(key, state, name=None, extra=None):
    group, *rest = key.split(":")
    target = rest[0] if len(rest) == 2 or group == "server" else ""
    return {"key": key, "group": group, "target": target, "name": name or rest[-1], "state": state,
            "detail": "", "since": SINCE, "checked_at": SINCE, "extra": extra}


def build(items, target):
    return monitor_flow.build(items, target)


def node(flow, nid):
    return next(n for n in flow["nodes"] if n["id"] == nid)


def edge(flow, a, b):
    return next((e for e in flow["edges"] if e["from"] == a and e["to"] == b), None)


def test_stages_and_core_nodes():
    items = [row("server:production", "ok"), row("service:cam_bma", "ok"), row("service:camera", "ok")]
    flow = build(items, "production")
    assert flow["stages"] == ["Images", "Data", "YOLO", "AI analysis", "Output"]
    assert node(flow, "cam_bma")["state"] == "ok"
    assert node(flow, "cam_bma")["stage"] == 0
    assert node(flow, "server")["label"] == "Production"
    assert node(flow, "server")["stage"] == 4
    assert edge(flow, "cam_bma", "camera")["state"] == "ok"


def test_server_down_gives_idle_nodes():
    flow = build([row("server:test", "fail")], "test")
    for nid in ("yolo_scan", "yolo_switch"):
        assert node(flow, nid)["state"] == "idle"
        assert node(flow, nid)["detail"] == "not checked"
    assert not any(n["id"].startswith("agent:") for n in flow["nodes"])
    assert "tunnel" not in [n["id"] for n in flow["nodes"]]


def test_data_node_states():
    items = [row("agent:production:Traffic guidance", "ok", extra={"data": "2m", "note": ""}),
             row("agent:production:Road flood risk", "warn", extra={"data": "40m", "note": "data stale"})]
    flow = build(items, "production")
    assert node(flow, "traffic")["state"] == "warn"
    assert node(flow, "traffic")["detail"] == "1 of 2 agents get fresh data"


def test_data_node_fails_when_all_stale():
    items = [row("agent:production:Traffic guidance", "warn", extra={"data": "40m", "note": "data stale"}),
             row("agent:production:Road flood risk", "warn", extra={"data": "40m", "note": "data stale"})]
    flow = build(items, "production")
    assert node(flow, "traffic")["state"] == "fail"


def test_data_node_ignores_rows_without_extra():
    flow = build([row("agent:production:Traffy flood reports", "ok", extra=None)], "production")
    assert node(flow, "traffy")["state"] == "idle"


def test_wrongway_prefix():
    items = [row("agent:production:Wrong-way check (gemma)", "ok"),
             row("yolo:production:wrong-way  wrongway_cls.pt", "ok")]
    flow = build(items, "production")
    assert edge(flow, "wrongway", "agent:Wrong-way check (gemma)") is not None


def test_unknown_agent_still_linked():
    flow = build([row("agent:production:violation_service", "ok")], "production")
    assert edge(flow, "gateway", "agent:violation_service") is not None
    assert edge(flow, "agent:violation_service", "server") is not None


def test_edge_fail_from_failed_node():
    items = [row("service:cam_itic", "fail"), row("service:camera", "ok")]
    flow = build(items, "production")
    assert edge(flow, "cam_itic", "camera")["state"] == "fail"


def test_node_ids_and_edges_are_unique():
    items = [row("agent:production:Traffic guidance", "ok", extra={"data": "2m", "note": ""}),
             row("agent:production:Road flood risk", "ok", extra={"data": "2m", "note": ""}),
             row("yolo:production:helmet  helmet_det_blur.pt", "ok"),
             row("server:production", "ok"), row("service:tunnel", "ok"), row("service:public", "ok")]
    flow = build(items, "production")
    ids = [n["id"] for n in flow["nodes"]]
    pairs = [(e["from"], e["to"]) for e in flow["edges"]]
    assert len(ids) == len(set(ids))
    assert len(pairs) == len(set(pairs))
