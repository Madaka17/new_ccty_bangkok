"""NASA FIRMS hotspots and EONET events (nasa_feeds.py): parsing and the analysis the map shows."""
from datetime import datetime, timezone

from backend.water import nasa_feeds as n

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc).timestamp()
HEAD = "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,confidence,version,bright_ti5,frp,daynight\n"


def row(lat, lng, date="2026-10-07", hhmm="0600", conf="nominal", frp="3.5"):
    return f"{lat},{lng},330,0.4,0.6,{date},{hhmm},N,{conf},2.0NRT,300,{frp},D\n"


def test_parse_firms_keeps_confident_hotspots_near_thailand():
    text = HEAD + row(18.8, 98.9) + row(18.8, 98.9, conf="low") + row(-8.5, 151.0) + row(18.8, 98.9, date="2026-10-04")
    pts = n.parse_firms(text, NOW)
    assert len(pts) == 1 and pts[0]["conf"] == "n" and pts[0]["frp"] == 3.5


def test_analyse_fires_counts_each_cell_once_and_compares_days():
    def locate(lat, lng):
        return ("เชียงใหม่", "") if lat > 18 else ("ลพบุรี", "")
    pts = []
    # the same fire from two satellites today, another fire near Bangkok today, one fire yesterday, one in Myanmar
    for hhmm in ("0600", "0700"):
        pts += n.parse_firms(HEAD + row(18.80001, 98.9, hhmm=hhmm, frp="25"), NOW)
    pts += n.parse_firms(HEAD + row(14.5, 100.6), NOW)
    pts += n.parse_firms(HEAD + row(18.5, 99.0, date="2026-10-06", hhmm="0300"), NOW)
    pts += n.parse_firms(HEAD + row(20.0, 97.0), NOW)
    out = n.analyse_fires(pts, NOW, locate=locate)
    assert out["th_24h"] == 2 and out["th_prev_24h"] == 1 and out["border_24h"] == 1
    assert out["near_bkk_24h"] == 1 and out["strong_24h"] == 1
    assert {r["region"] for r in out["regions"]} == {"ภาคเหนือ", "ภาคกลาง"}
    assert len(out["points"]) == 3


def test_parse_events_storm_distance_and_trend():
    data = {"events": [
        {"id": "E1", "title": "Typhoon X", "categories": [{"id": "severeStorms"}], "sources": [{"url": "https://jtwc/x"}],
         "geometry": [{"type": "Point", "coordinates": [125.0, 15.0], "date": "2026-10-06T00:00:00Z"},
                      {"type": "Point", "coordinates": [115.0, 15.0], "date": "2026-10-07T00:00:00Z", "magnitudeValue": 80, "magnitudeUnit": "kts"}]},
        {"id": "E2", "title": "Iceberg", "categories": [{"id": "seaLakeIce"}], "geometry": [{"type": "Point", "coordinates": [0, -60]}]},
    ]}
    events = n.parse_events(data, dist=lambda lat, lng: round((lng - 105) * 100))
    assert [e["id"] for e in events] == ["E1"]
    e = events[0]
    assert e["km_to_thailand"] == 1000 and e["trend"] == "closer" and e["magnitude"] == 80 and len(e["track"]) == 2
    assert e["link"] == "https://jtwc/x" and e["kind_th"] == "พายุ"
