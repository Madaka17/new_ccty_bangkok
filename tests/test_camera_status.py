"""launch/camera_status.py: a website down on every camera last round gets only a few cameras pulled."""
import importlib.util
import os

_spec = importlib.util.spec_from_file_location(
    "camera_status", os.path.join(os.path.dirname(__file__), "..", "launch", "camera_status.py"))
cs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cs)


def _round(monkeypatch, working, previous):
    cams = [{"camid": f"flood-{i}", "source": "floodbkk", "imgurl": f"https://flood/{i}.jpg"} for i in range(30)]
    cams += [{"camid": "doh-1", "source": "doh", "imgurl": "https://doh/1.jpg"}]
    pulled = []

    def probe(url):
        pulled.append(url)
        if url not in working:
            raise cs.Down("HTTP 500")

    monkeypatch.setattr(cs, "check_sites", lambda port: {})
    monkeypatch.setattr(cs, "bma_states", lambda port: {})
    monkeypatch.setattr(cs, "server", lambda port, path, timeout=60: {"items": cams})
    monkeypatch.setattr(cs, "plan", lambda c, base: (probe, c["imgurl"]))
    return cs.check_round(8000, previous), pulled


def _all_down():
    prev = {f"flood-{i}": {"source": "floodbkk", "state": "down", "reason": "HTTP 500", "url": "x"} for i in range(30)}
    prev["doh-1"] = {"source": "doh", "state": "ok", "reason": "", "url": "x"}
    return prev


def test_dead_website_gets_a_sample_only(monkeypatch):
    data, pulled = _round(monkeypatch, {"https://doh/1.jpg"}, _all_down())
    assert len(pulled) == cs.DEAD_SAMPLE + 1 and data["probed"] == cs.DEAD_SAMPLE + 1
    flood = [r for c, r in data["cameras"].items() if c.startswith("flood-")]
    assert len(flood) == 30 and all(r["state"] == "down" for r in flood)
    assert sum("not pulled" in r["reason"] for r in flood) == 30 - cs.DEAD_SAMPLE


def test_website_back_gets_every_camera_pulled(monkeypatch):
    working = {"https://flood/0.jpg", "https://flood/17.jpg", "https://doh/1.jpg"}
    data, pulled = _round(monkeypatch, working, _all_down())
    assert len(pulled) == 31
    assert data["cameras"]["flood-17"]["state"] == "ok" and data["cameras"]["flood-5"]["reason"] == "HTTP 500"


def test_first_round_pulls_everything(monkeypatch):
    _, pulled = _round(monkeypatch, set(), None)
    assert len(pulled) == 31
