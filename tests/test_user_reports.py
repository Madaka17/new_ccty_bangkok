"""Own flood reports: validation, persistence, photos and compatibility with existing reports."""
import base64
import io
import sqlite3
import time

import pytest
from PIL import Image

from backend.water import user_reports as ur


@pytest.fixture
def reports(tmp_path, monkeypatch):
    monkeypatch.setattr(ur, "DB_PATH", str(tmp_path / "reports.db"))
    monkeypatch.setattr(ur, "PHOTO_DIR", str(tmp_path / "photos"))
    monkeypatch.setattr(ur.local_llm.default, "enabled", lambda: False)
    return ur.UserReports()


def payload(**changes):
    return {"lat": 13.7563, "lng": 100.5018, "province": "กรุงเทพมหานคร",
            "district": "พระนคร", "depth": "chest", **changes}


def test_choices_cover_all_provinces_and_bangkok_districts():
    choices = ur.report_locations()
    assert len(choices) == 77
    assert len(choices["กรุงเทพมหานคร"]) == 50
    assert any(d["name"] == "พระนคร" for d in choices["กรุงเทพมหานคร"])
    for districts in choices.values():
        assert len({d["name"] for d in districts}) == len(districts)
        assert all(5.5 <= d["lat"] <= 20.5 and 97.3 <= d["lng"] <= 105.7 for d in districts)


@pytest.mark.parametrize("depth", ["ankle", "shin", "chest"])
def test_depth_and_area_published_round_trip(reports, depth):
    result = reports.create(payload(depth=depth))
    assert result["status"] == "published"
    item, = reports.recent()["items"]
    assert item["province"] == "กรุงเทพมหานคร"
    assert item["district"] == "พระนคร"
    assert item["depth"] == depth
    assert (item["lat"], item["lng"]) == (13.7563, 100.5018)


def test_2000_characters_preserved_and_moderated(reports, monkeypatch):
    note = "น้ำท่วมถนน\n" + "ก" * (2000 - len("น้ำท่วมถนน\n"))
    result = reports.create(payload(note=note))
    assert result["status"] == "pending"
    assert reports.recent()["items"] == []
    with reports._db() as conn:
        assert conn.execute("SELECT note FROM user_flood_reports").fetchone()[0] == note
    monkeypatch.setattr(ur.local_llm.default, "enabled", lambda: True)
    monkeypatch.setattr(ur.local_llm.default, "chat", lambda *a, **k: '{"fit":true,"flood":true,"level":"severe"}')
    assert reports._check(result["id"]) == "published"
    item, = reports.recent()["items"]
    assert item["note"] == note
    assert item["depth_th"] == "อก"


@pytest.mark.parametrize("changes", [
    {"note": "ก" * 2001}, {"province": ""}, {"district": ""},
    {"district": "เมืองเชียงใหม่"}, {"province": "จังหวัดไม่มีจริง"},
    {"depth": "invalid"}, {"lat": None}, {"lat": float("nan")}, {"lng": 1},
    {"photo": "data:image/png;base64,bm90LWFuLWltYWdl"},
])
def test_invalid_reports_leave_no_rows(reports, changes):
    with pytest.raises(ValueError):
        reports.create(payload(**changes))
    with reports._db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM user_flood_reports").fetchone()[0] == 0


def test_photo_saved_as_jpeg_and_hidden_until_published(reports, monkeypatch):
    image = Image.new("RGB", (1600, 800), "blue")
    exif = Image.Exif()
    exif[270] = "private test metadata"
    raw = io.BytesIO()
    image.save(raw, "JPEG", exif=exif)
    result = reports.create(payload(photo="data:image/jpeg;base64," + base64.b64encode(raw.getvalue()).decode()))
    assert result["status"] == "pending"
    assert reports.published_photo(result["id"]) is None
    with Image.open(reports.photo_path(result["id"])) as saved:
        assert saved.format == "JPEG"
        assert saved.size == (1280, 640)
        assert not saved.getexif()
    monkeypatch.setattr(ur.local_llm.default, "enabled", lambda: True)
    monkeypatch.setattr(ur.local_llm.default, "chat", lambda *a, **k: '{"fit":true,"flood":true,"level":"severe"}')
    assert reports._check(result["id"]) == "published"
    assert reports.published_photo(result["id"]) == reports.photo_path(result["id"])


def test_legacy_schema_is_migrated_without_losing_reports(tmp_path, monkeypatch):
    db = tmp_path / "legacy.db"
    monkeypatch.setattr(ur, "DB_PATH", str(db))
    monkeypatch.setattr(ur, "PHOTO_DIR", str(tmp_path / "photos"))
    with sqlite3.connect(db) as conn:
        conn.execute("""CREATE TABLE user_flood_reports
            (id TEXT PRIMARY KEY, ts INTEGER, lat REAL, lng REAL, depth TEXT, note TEXT,
             has_photo INTEGER, status TEXT, ai_level TEXT, ai_note TEXT)""")
        conn.execute("INSERT INTO user_flood_reports VALUES (?,?,?,?,?,?,?,?,?,?)",
                     ("abcdef123456", int(time.time()), 13.75, 100.5, "knee", "", 0, "published", None, None))
    ur.UserReports()
    reports = ur.UserReports()  # repeat startup is safe
    old, = reports.recent()["items"]
    assert old["id"] == "abcdef123456" and old["depth"] == "knee"
    assert old["province"] == old["district"] == ""
    reports.create(payload())
    assert reports.recent()["total"] == 2
