"""Flood car parks: only announced spots are shown, and a "full" press fades unless someone presses again."""
import json

import pytest

from backend.water import flood_parking as fp

SPOT = {"id": "mall-1", "name": "อาคารจอดรถ A", "lat": 13.75, "lng": 100.56, "capacity": 200, "fee": "ฟรี",
        "status": "open", "status_at": "2026-10-05T18:40", "source": "สำนักงานเขต", "source_url": "https://example.go.th/a"}


def _parking(tmp_path, spots):
    path = tmp_path / "flood_parking.json"
    path.write_text(json.dumps({"spots": spots}, ensure_ascii=False), encoding="utf-8")
    return fp.FloodParking(str(path))


def test_spot_without_announcement_is_skipped(tmp_path):
    no_link = {**SPOT, "id": "b", "source_url": ""}
    plain_http = {**SPOT, "id": "c", "source_url": "http://example.go.th"}
    no_source = {k: v for k, v in SPOT.items() if k != "source"} | {"id": "d"}
    out = _parking(tmp_path, [SPOT, no_link, plain_http, no_source]).status()
    assert [s["id"] for s in out["spots"]] == ["mall-1"]
    assert out["spots"][0]["status_th"] == "ว่าง" and out["spots"][0]["user_full"] is None


def test_missing_file_means_no_spots(tmp_path):
    assert fp.FloodParking(str(tmp_path / "none.json")).status()["spots"] == []


def test_full_counts_each_reporter_once(tmp_path):
    p = _parking(tmp_path, [SPOT])
    p.report_full("mall-1", "203.0.113.5")
    p.report_full("mall-1", "203.0.113.5")
    full = p.report_full("mall-1", "198.51.100.7")
    assert full["count"] == 2


def test_full_fades_without_a_new_report(tmp_path, monkeypatch):
    p = _parking(tmp_path, [SPOT])
    now = [1_000_000.0]
    monkeypatch.setattr(fp.time, "time", lambda: now[0])
    p.report_full("mall-1", "a")
    now[0] += 60 * 60
    p.report_full("mall-1", "b")                   # a second report renews it
    now[0] += 60 * 60
    assert p.status()["spots"][0]["user_full"]["count"] == 1   # a is older than REPORT_MINUTES, b is not
    now[0] += fp.REPORT_MINUTES * 60
    assert p.status()["spots"][0]["user_full"] is None


def test_unknown_spot(tmp_path):
    with pytest.raises(KeyError):
        _parking(tmp_path, [SPOT]).report_full("nope", "a")


def test_file_change_is_picked_up(tmp_path):
    p = _parking(tmp_path, [])
    assert p.status()["total"] == 0
    path = tmp_path / "flood_parking.json"
    path.write_text(json.dumps({"spots": [SPOT]}), encoding="utf-8")
    p._mtime = None   # same-second writes can keep the mtime; force the re-read the next change would trigger
    assert p.status()["total"] == 1


def test_spot_hides_after_until(tmp_path, monkeypatch):
    p = _parking(tmp_path, [{**SPOT, "until": "2026-10-09T23:59"}])
    end = fp._epoch("2026-10-09T23:59")
    monkeypatch.setattr(fp.time, "time", lambda: end - 60)
    assert p.status()["spots"][0]["until"] == end
    monkeypatch.setattr(fp.time, "time", lambda: end + 60)
    assert p.status()["spots"] == []
    with pytest.raises(KeyError):
        p.report_full("mall-1", "a")


def test_mistyped_until_skips_the_spot(tmp_path):
    assert _parking(tmp_path, [{**SPOT, "until": "9 ต.ค."}]).status()["spots"] == []
