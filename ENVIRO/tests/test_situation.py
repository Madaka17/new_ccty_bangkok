"""GET /api/situation (server/routes/situation.py) through the test client.

Runs against a temp DB seeded by the real schema: once empty (no events) and
once with a few inserted event rows: one current, one stale.
"""
from datetime import datetime, timedelta, timezone

import pytest

from server import db as dbmod

TOP_KEYS = {
    "event", "stations", "faults", "cities", "vp_km_s", "vs_km_s",
    "speed_multiplier", "you_are_here", "pending_quake",
}
PENDING_KEYS = {"lat", "lng", "place", "fault", "region", "magnitude", "depth", "start_s", "speed_multiplier"}
CITY_KEYS = {"name", "dist_km", "mmi_label", "p_remaining_sec", "s_remaining_sec", "p_arrived", "s_arrived"}


def _insert_event(event_id, ts, magnitude=5.5, depth=10.0, level=4, stations=4, speed=1.0):
    conn = dbmod.get_conn()
    conn.execute(
        "INSERT INTO events(id,ts,magnitude,depth,place,fault,lat,lng,mmi_epicenter,predicted_mmi,"
        "tsunami_risk,stations_triggered,level,pga_gal,is_test,speed_multiplier) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (event_id, ts, magnitude, depth, "test place", "test fault", 19.0, 99.5, "VI", 6.1,
         0, stations, level, 120.0, 0, speed),
    )
    conn.commit()
    conn.close()


def test_empty_db_returns_200_and_shape(client):
    resp = client.get("/api/situation")
    assert resp.status_code == 200
    body = resp.get_json()
    assert set(body) == TOP_KEYS
    assert body["event"] is None
    assert body["vp_km_s"] == 6.5
    assert body["vs_km_s"] == 3.8
    assert body["speed_multiplier"] == 1.0
    assert body["you_are_here"] == "BKK-201"


def test_empty_db_lists_seeded_stations_faults_and_cities(client):
    body = client.get("/api/situation").get_json()
    assert len(body["stations"]) == 7
    assert {"id", "region", "lat", "lng", "status"} <= set(body["stations"][0])
    assert "CNX-118" in {s["id"] for s in body["stations"]}
    assert len(body["faults"]) == 8
    assert len(body["cities"]) == 7
    for city in body["cities"]:
        assert set(city) == CITY_KEYS
        # no active event: no timing and a fixed "no event" label
        assert city["p_remaining_sec"] is None and city["s_remaining_sec"] is None
        assert city["mmi_label"] == "ไม่มีเหตุการณ์ปัจจุบัน"


def test_empty_db_reports_pending_quake_from_simulator_default(client):
    body = client.get("/api/situation").get_json()
    assert set(body["pending_quake"]) == PENDING_KEYS
    assert body["pending_quake"]["place"] == "อ.แม่จัน จ.เชียงราย"
    # distance from the default quake origin to Chiang Mai (pinned from the current code)
    chiang_mai = next(c for c in body["cities"] if c["name"] == "เชียงใหม่")
    assert chiang_mai["dist_km"] == pytest.approx(176.5, abs=0.05)


def test_current_event_is_returned_with_joined_level_and_confidence(client, temp_db):
    now = datetime.now(timezone.utc).isoformat()
    _insert_event("ev-current", now)
    body = client.get("/api/situation").get_json()

    event = body["event"]
    assert event is not None and event["id"] == "ev-current"
    # level text joined in from the levels table (level 4)
    assert event["level"] == 4
    assert event["level_name"] == "ป้องกันตนทันที"
    assert event["siren"] and event["channels"] and event["message"] and event["color"]
    # historical branch: confidence recomputed from 4 stations triggered
    assert event["confidence_tier"] == 3
    assert event["confidence_label"] == "สูง"
    assert event["fully_confirmed"] is False
    assert event["magnitude_estimate"] == 5.5
    assert event["predicted_mmi_roman"] == "VI"
    assert event["tsunami_risk"] is False
    assert event["external_match"] is None
    # an active event means no pending quake
    assert body["pending_quake"] is None

    for city in body["cities"]:
        assert set(city) == CITY_KEYS
        assert city["mmi_label"] != "ไม่มีเหตุการณ์ปัจจุบัน"
        assert city["p_remaining_sec"] >= 0 and city["s_remaining_sec"] >= 0
        # S waves are slower than P, so S always has at least as far to go
        assert city["s_remaining_sec"] >= city["p_remaining_sec"]


def test_current_event_distance_is_from_event_epicentre(client, temp_db):
    _insert_event("ev-current", datetime.now(timezone.utc).isoformat())
    body = client.get("/api/situation").get_json()
    chiang_mai = next(c for c in body["cities"] if c["name"] == "เชียงใหม่")
    assert chiang_mai["dist_km"] == pytest.approx(59.1, abs=0.05)


def test_stale_event_is_dropped_and_pending_quake_returns(client, temp_db):
    # A 2020 event has long since been felt out to its radius: not "current" any more
    _insert_event("ev-old", "2020-01-01T00:00:00+00:00")
    body = client.get("/api/situation").get_json()
    assert body["event"] is None
    assert set(body["pending_quake"]) == PENDING_KEYS
    assert all(c["p_remaining_sec"] is None for c in body["cities"])


def test_event_three_hours_old_is_past_its_felt_radius(client, temp_db):
    # Three hours of S-wave travel at 3.8 km/s is far beyond the M4.5 felt radius
    ts = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    _insert_event("ev-3h", ts, magnitude=4.5, depth=10.0)
    body = client.get("/api/situation").get_json()
    assert body["event"] is None
