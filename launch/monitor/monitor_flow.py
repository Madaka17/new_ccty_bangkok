"""
The Workflow page's graph (launch\\monitor\\ui\\flow2d.js draws it): the pipeline from images and data through YOLO and
the AI agents to the output, built from the collector's status rows (Store.current()). Called by Api.flow in
monitor_app.py, which the desktop window and the phone page (monitor_web.py) use. Pure: no I/O. A missing row is an
idle node, so a server that is down still gives a full graph.
"""

STAGES = ["Images", "Data", "YOLO", "AI analysis", "Output"]
NOT_JUDGED = ("", "–", None)
BAD_NOTES = ("data stale", "source sent no readings")

# Derived data nodes: id -> (label, stage, the agents that read this feed)
DATA_SOURCES = {
    "water": ("Water & rain feeds", 1, ["Bangkok flood report", "Bangkok road water", "Road flood risk",
                                        "Bangkok districts (50)", "Provinces flood", "National 7-day outlook",
                                        "Northern water route"]),
    "traffic": ("Traffic feeds", 1, ["Traffic guidance", "Road flood risk", "incident_service"]),
    "traffy": ("Traffy Fondue", 1, ["Traffy flood reports"]),
    "riskbkk": ("riskbkk accidents", 1, ["Accident risk (riskbkk)"]),
}


def build(items, target):
    rows = {r["key"]: r for r in items}
    yolo = [r for r in items if r["group"] == "yolo" and r["target"] == target]
    agents = sorted((r for r in items if r["group"] == "agent" and r["target"] == target), key=lambda r: r["name"])
    agents_by_name = {r["name"]: r for r in agents}

    def yolo_named(text):
        return next((r for r in yolo if text in r["name"]), None)

    def yolo_starts(text):
        return next((r for r in yolo if r["name"].startswith(text)), None)

    nodes = [
        _node("cam_bma", "BMA cameras", 0, rows.get("service:cam_bma")),
        _node("cam_itic", "ITIC cameras", 0, rows.get("service:cam_itic")),
        _node("camera", "Camera status file", 0, rows.get("service:camera")),
    ]
    for nid, (label, stage, consumers) in DATA_SOURCES.items():
        nodes.append(_data_node(nid, label, stage, consumers, agents_by_name))
    nodes += [
        _node("yolo_switch", "YOLO switch", 2, rows.get(f"yolo:{target}:YOLO switch")),
        _node("yolo_scan", "BMA camera scan", 2, yolo_named("BMA camera scan")),
        _node("yolo_live", "Live AI camera", 2, yolo_named("live AI camera")),
        _node("helmet", "Helmet detector", 2, yolo_starts("helmet")),
        _node("wrongway", "Wrong-way classifier", 2, yolo_starts("wrong-way")),
        _node("gateway", "AI gateway", 3, rows.get("service:gateway")),
    ]
    nodes += [_node(f"agent:{r['name']}", r["name"], 3, r) for r in agents]
    nodes.append(_node("server", target.capitalize(), 4, rows.get(f"server:{target}")))
    if target == "production":
        nodes += [_node("tunnel", "Cloudflare tunnel", 4, rows.get("service:tunnel")),
                  _node("public", "Public site", 4, rows.get("service:public"))]

    pairs = [("cam_bma", "camera"), ("cam_itic", "camera"), ("camera", "yolo_scan"), ("camera", "yolo_live"),
             ("yolo_switch", "yolo_scan"), ("yolo_switch", "yolo_live"), ("yolo_switch", "helmet"),
             ("yolo_switch", "wrongway"), ("yolo_scan", "helmet"), ("yolo_scan", "wrongway"),
             ("yolo_scan", "agent:Flood cameras (vision)"), ("helmet", "agent:Helmet check (vision)")]
    pairs += [("wrongway", f"agent:{r['name']}") for r in agents if r["name"].startswith("Wrong-way check")]
    for nid, (_, _, consumers) in DATA_SOURCES.items():
        pairs += [(nid, f"agent:{name}") for name in consumers]
    for r in agents:
        pairs += [("gateway", f"agent:{r['name']}"), (f"agent:{r['name']}", "server")]
    if target == "production":
        pairs += [("server", "tunnel"), ("tunnel", "public")]

    return {"target": target, "stages": STAGES, "nodes": nodes, "edges": _edges(nodes, pairs)}


def _node(nid, label, stage, row):
    if row is None:
        return {"id": nid, "stage": stage, "label": label, "state": "idle", "detail": "not checked", "since": None}
    return {"id": nid, "stage": stage, "label": label, "state": row["state"],
            "detail": row.get("detail") or "", "since": row.get("since")}


def _data_node(nid, label, stage, consumers, agents_by_name):
    judged = [agents_by_name[name] for name in consumers if name in agents_by_name
              and agents_by_name[name].get("extra") and agents_by_name[name]["extra"].get("data") not in NOT_JUDGED]
    if not judged:
        return {"id": nid, "stage": stage, "label": label, "state": "idle",
                "detail": "no agent reads it now", "since": None}
    bad = sum(1 for r in judged if _data_bad(r["extra"]))
    state = "fail" if bad == len(judged) else "warn" if bad else "ok"
    return {"id": nid, "stage": stage, "label": label, "state": state,
            "detail": f"{len(judged) - bad} of {len(judged)} agents get fresh data", "since": None}


def _data_bad(extra):
    note = extra.get("note") or ""
    return note in BAD_NOTES or note.startswith("endpoint error")


def _edges(nodes, pairs):
    by_id = {n["id"]: n for n in nodes}
    seen, out = set(), []
    for a, b in pairs:
        if a not in by_id or b not in by_id or (a, b) in seen:
            continue
        seen.add((a, b))
        out.append({"from": a, "to": b, "state": _edge_state(by_id[a]["state"], by_id[b]["state"])})
    return out


def _edge_state(a, b):
    if a == "fail":
        return "fail"
    if a in ("ok", "warn") and b not in ("fail", "stopped"):
        return "ok"
    return "idle"
