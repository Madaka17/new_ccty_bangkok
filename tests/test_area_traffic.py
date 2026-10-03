"""Province and district totals of area_traffic: score, too-little-road cut-off, change against an hour ago."""
import time

from backend.traffic import area_traffic
from backend.traffic.area_traffic import AreaTraffic, _stats


def test_stats_score_and_min_km():
    s = _stats(6.0, 2.0, 2.0)
    assert s["flow"] == 70            # (6 + 0.5 x 2) / 10
    assert s["red_pct"] == 20
    assert _stats(0.3, 0.2, 0.0)["flow"] is None   # under MIN_KM


def test_publish_sums_districts_into_provinces(monkeypatch, tmp_path):
    monkeypatch.setattr(area_traffic, "STATE_FILE", str(tmp_path / "area_traffic.json"))
    a = AreaTraffic()
    a.tiles = [(0, 0)] * 10
    a.names = [("5001", "เมืองเชียงใหม่", "50"), ("5002", "จอมทอง", "50"), ("1001", "พระนคร", "10")]
    a.history = [{"t": int(time.time()) - 3600, "flows": {"50": 90, "5001": 95}}]
    a._publish({0: [8.0, 2.0, 0.0], 1: [0.0, 0.0, 2.0]}, stale=0)
    s = a.status()
    cm = next(p for p in s["provinces"] if p["code"] == "50")
    assert cm["province"] == "เชียงใหม่" and cm["region"] == "ภาคเหนือ"
    assert cm["total_km"] == 12.0 and cm["flow"] == 75   # (8 + 1) / 12
    assert cm["flow_1h"] == 90
    assert {x["code"]: x["flow"] for x in cm["amphoes"]} == {"5001": 90, "5002": 0}
    bkk = next(p for p in s["provinces"] if p["code"] == "10")
    assert bkk["flow"] is None and bkk["amphoes"][0]["flow"] is None
    assert s["national"]["flow"] == 75 and s["online"]
