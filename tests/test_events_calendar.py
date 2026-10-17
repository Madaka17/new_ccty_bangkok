"""Road-closure and big-event calendar: buckets in Bangkok time, scope, dedup, team events file."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from backend.traffic.events_calendar import EventsCalendar

BKK = timezone(timedelta(hours=7))


def bkk(day, hour=0, minute=0, month=10):
    return datetime(2026, month, day, hour, minute, tzinfo=BKK).timestamp()


NOW = bkk(18, 12)   # 2026-10-18 12:00 Bangkok


def longdo(id_, start=None, stop=None, province="กรุงเทพมหานคร", lat="13.73", lng="100.56", title="ปิดถนนทดสอบ",
           kind="closed", amphoe="วัฒนา"):
    fmt = lambda t: None if t is None else datetime.fromtimestamp(t, BKK).strftime("%Y-%m-%d %H:%M:%S")
    return {"id": f"longdo-{id_}", "source": "longdo", "kind": kind, "reason": "", "title": title, "description": "รายละเอียด",
            "latitude": lat, "longitude": lng, "start": fmt(start), "stop": fmt(stop),
            "contributor": "", "province": province, "amphoe": amphoe}


def make(tmp_path, closures=(), bma=(), bulletins=(), now=NOW, locate=None, name="team.json"):
    sources = {"closures": lambda: list(closures), "bma": lambda: list(bma), "bulletins": lambda: list(bulletins)}
    return EventsCalendar(str(tmp_path / name), sources, now=lambda: now, locate=locate)


def ids(bucket):
    return [i["id"] for i in bucket]


def test_bucket_placement_with_fixed_now(tmp_path):
    closures = [
        longdo("today", start=bkk(18, 9), stop=bkk(18, 18)),
        longdo("today-edge", start=bkk(18, 0), stop=bkk(18, 20)),
        longdo("tomorrow", start=bkk(19, 8), stop=bkk(19, 20)),
        longdo("tomorrow-edge", start=bkk(19, 0), stop=bkk(19, 20)),
        longdo("week", start=bkk(20, 0), stop=bkk(21, 20)),
        longdo("week-last", start=bkk(25, 23), stop=bkk(26, 20)),
        longdo("beyond", start=bkk(26, 0), stop=bkk(27, 20)),
    ]
    out = make(tmp_path, closures=closures).calendar()
    assert set(ids(out["today"])) == {"longdo-today", "longdo-today-edge"}
    assert set(ids(out["tomorrow"])) == {"longdo-tomorrow", "longdo-tomorrow-edge"}
    assert set(ids(out["week"])) == {"longdo-week", "longdo-week-last"}
    assert out["ongoing"] == []
    everything = ids(out["today"]) + ids(out["tomorrow"]) + ids(out["week"])
    assert "longdo-beyond" not in everything


def test_bulletin_goes_to_ongoing(tmp_path):
    bulletins = [
        {"id": "b1", "headline": "ปิดถนนสุขุมวิท", "detail": "ช่วงหน้าวัด", "image": None, "source": "ศูนย์จราจร"},
        {"id": "b2", "headline": "ฝนตกหนัก", "detail": "ระวังน้ำท่วม", "image": None, "source": "ศูนย์จราจร"},
        {"id": "b3", "headline": "เบี่ยงจราจร", "detail": "", "image": None, "source": ""},
    ]
    out = make(tmp_path, bulletins=bulletins).calendar()
    assert set(ids(out["ongoing"])) == {"bma_bulletin-b1", "bma_bulletin-b3"}
    item = out["ongoing"][0]
    assert item["source"] == "bma_bulletin" and item["start"] is None and item["end"] is None


def test_longdo_started_in_past_with_stop_tomorrow_is_ongoing(tmp_path):
    closures = [longdo("old", start=bkk(15, 6), stop=bkk(19, 2))]
    out = make(tmp_path, closures=closures).calendar()
    assert ids(out["ongoing"]) == ["longdo-old"]
    assert out["today"] == [] and out["tomorrow"] == []


def test_feed_item_with_only_stop_is_ongoing_not_a_day(tmp_path):
    closures = [longdo("stop-only", start=None, stop=bkk(20, 10))]
    out = make(tmp_path, closures=closures).calendar()
    assert ids(out["ongoing"]) == ["longdo-stop-only"]
    assert out["today"] == [] and out["tomorrow"] == [] and out["week"] == []


def test_ended_item_is_dropped(tmp_path):
    closures = [longdo("done", start=bkk(15, 6), stop=bkk(18, 11))]
    out = make(tmp_path, closures=closures).calendar()
    assert all(out[k] == [] for k in ("ongoing", "today", "tomorrow", "week"))


def test_scope_hides_chiang_mai_for_bkk_and_shows_it_for_all(tmp_path):
    closures = [
        longdo("bkk", start=bkk(15), stop=bkk(19, 2)),
        longdo("cnx", start=bkk(15), stop=bkk(19, 2), province="เชียงใหม่", lat="18.79", lng="98.98"),
    ]
    cal = make(tmp_path, closures=closures)
    assert ids(cal.calendar("bkk")["ongoing"]) == ["longdo-bkk"]
    assert set(ids(cal.calendar("all")["ongoing"])) == {"longdo-bkk", "longdo-cnx"}


def test_bma_roadwork_and_longdo_closure_nearby_show_once_longdo_kept(tmp_path):
    closures = [longdo("lg", start=bkk(18, 6), stop=bkk(19, 6), title="ถนนพระราม 4 ซ่อมท่อ", lat="13.7300", lng="100.5600")]
    bma = [{"id": 77, "kind": "roadwork", "title": "ถนนพระราม 4 ซ่อมท่อ", "desc": "", "ts": bkk(18, 7),
            "lat": 13.7303, "lng": 100.5604, "url": None, "source": "bma"}]
    out = make(tmp_path, closures=closures, bma=bma).calendar()
    everything = ids(out["ongoing"]) + ids(out["today"])
    assert everything.count("longdo-lg") == 1
    assert not any(i.startswith("bma-") for i in everything)


def test_bma_roadwork_far_or_unrelated_is_not_deduped(tmp_path):
    closures = [longdo("lg", start=bkk(18, 6), stop=bkk(19, 6), title="ถนนพระราม 4 ซ่อมท่อ", lat="13.7300", lng="100.5600")]
    bma = [
        {"id": 1, "kind": "roadwork", "title": "ถนนพระราม 4 ซ่อมท่อ", "desc": "", "ts": bkk(18, 7),
         "lat": 13.8000, "lng": 100.5600, "url": None},          # about 7 km away
        {"id": 2, "kind": "roadwork", "title": "สะพานลอยลาดพร้าว", "desc": "", "ts": bkk(18, 7),
         "lat": 13.7301, "lng": 100.5601, "url": None},          # close, but no shared word
    ]
    out = make(tmp_path, closures=closures, bma=bma).calendar()
    assert set(ids(out["today"])) == {"bma-1", "bma-2", "longdo-lg"}
    assert "longdo-lg" in ids(out["today"])


def test_add_validation_rules_each_give_value_error(tmp_path):
    cal = make(tmp_path)
    good = {"title": "งานวิ่ง", "kind": "run", "start": bkk(20, 6), "end": bkk(20, 12), "district": "วัฒนา",
            "lat": 13.73, "lng": 100.56}
    cal.add(dict(good))   # sanity: a good event passes

    bad_cases = [
        {"title": ""},
        {"title": "x" * 121},
        {"detail": "x" * 601},
        {"place": "x" * 121},
        {"kind": "parade"},
        {"lat": 13.73, "lng": None},
        {"lat": 4.0},
        {"lng": 107.0},
        {"district": "เชียงใหม่"},
        {"start": bkk(20, 12), "end": bkk(20, 6)},
        {"start": bkk(20, 6), "end": bkk(18, 6) + 130 * 86400},
        {"start": "tomorrow"},
        {"start": True},
        {"url": "javascript:alert(1)"},
    ]
    for patch in bad_cases:
        with pytest.raises(ValueError) as err:
            cal.add({**good, **patch})
        assert str(err.value), patch


def test_add_and_remove_round_trip_persists(tmp_path):
    cal = make(tmp_path)
    item = cal.add({"title": "คอนเสิร์ตหน้าศาลากลาง", "kind": "concert", "start": bkk(19, 18), "end": bkk(19, 22),
                    "district": "พระนคร", "place": "สนามหน้าพระลาน"})
    assert item["id"].startswith("team-") and item["source"] == "team"
    assert (tmp_path / "team.json").exists()

    fresh = make(tmp_path)   # a new instance reads the file
    assert ids(fresh.calendar()["tomorrow"]) == [item["id"]]
    assert fresh.calendar()["tomorrow"][0]["province"] == "กรุงเทพมหานคร"

    assert fresh.remove(item["id"]) is True
    assert fresh.remove(item["id"]) is False
    assert make(tmp_path).calendar()["tomorrow"] == []


def test_broken_store_file_gives_empty_list_without_exception(tmp_path):
    (tmp_path / "team.json").write_text("{not json", encoding="utf-8")
    cal = make(tmp_path, closures=[longdo("lg", start=bkk(15), stop=bkk(19, 2))])
    out = cal.calendar()
    assert ids(out["ongoing"]) == ["longdo-lg"]
    assert all(i["source"] != "team" for k in out for i in (out[k] if isinstance(out[k], list) else []))
    # a later write replaces the broken file
    cal.add({"title": "งานใหม่", "kind": "event", "start": bkk(20, 9), "end": None})
    assert json.loads((tmp_path / "team.json").read_text(encoding="utf-8"))


def test_events_ended_over_30_days_ago_are_pruned_on_write(tmp_path):
    old_now = bkk(1, 12, month=9)                  # 2026-09-01
    cal = make(tmp_path, now=old_now)
    cal.add({"title": "งานเก่า", "kind": "event", "start": bkk(2, 9, month=9), "end": bkk(2, 18, month=9)})
    recent = make(tmp_path, now=NOW)               # 47 days later
    recent.add({"title": "งานใหม่", "kind": "event", "start": bkk(20, 9), "end": bkk(20, 18)})
    stored = json.loads((tmp_path / "team.json").read_text(encoding="utf-8"))
    titles = [e["title"] for e in stored]
    assert titles == ["งานใหม่"]
