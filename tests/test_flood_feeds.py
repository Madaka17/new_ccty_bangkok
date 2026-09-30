"""Parsing of the Traffy Fondue, TMD, HDMS and JS100 feeds."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from backend.water import flood_feeds
from backend.water.flood_feeds import (BKK_TZ, TraffyFloodReports, parse_hdms, parse_hdms_photos, parse_js100,
                                       parse_tmd, parse_traffy, traffy_map_results)

NOW = 1_790_000_000  # 2026-09-21 14:13 UTC


def _ticket(text, ts="2026-09-21 14:00:00.000000+00", kinds=("",)):
    return {"ticket_id": "2026-ABC", "description": text, "timestamp": ts, "problem_type_abdul": list(kinds),
            "address": "แขวงบางนาเหนือ เขตบางนา กรุงเทพมหานคร", "coords": ["100.6", "13.67"], "state": "รอรับเรื่อง"}


def test_traffy_keeps_recent_flood_reports_only():
    items = parse_traffy([
        _ticket("น้ำขัง ไม่ระบายลงท่อ ความสูงระดับข้อเท้า"),
        _ticket("ไฟทางดับ"),
        _ticket("ท่อตัน", kinds=["น้ำท่วม"]),
        _ticket("น้ำท่วม", ts="2026-09-21 01:00:00.000000+00"),
    ], now=NOW)
    assert [i["text"] for i in items] == ["น้ำขัง ไม่ระบายลงท่อ ความสูงระดับข้อเท้า", "ท่อตัน"]
    assert items[0]["district"] == "บางนา" and items[0]["depth"] == "ข้อเท้า"
    assert (items[0]["lat"], items[0]["lng"]) == (13.67, 100.6)


def test_traffy_leaves_out_reports_about_what_follows_a_flood():
    items = parse_traffy([
        _ticket("มีขยะหลังน้ำท่วมหน้าบ้าน #กองขยะน้ำท่วม"),
        _ticket("ขอรับเงินเยียวยาน้ำท่วม"),
        _ticket("ฝนตก เก็บขยะหลังน้ำท่วมให้หน่อย"),        # rain alone does not say the water is there
        _ticket("ขยะอุดท่อ น้ำท่วมขังหน้าบ้าน"),          # the water is there now
        _ticket("ฝนตกทีไรน้ำท่วม ขยะเต็มซอย"),            # it floods every time it rains
        _ticket("ขยะหลังน้ำท่วม", kinds=["น้ำท่วม"]),     # Traffy's own flood type decides
    ], now=NOW)
    assert [i["text"] for i in items] == ["ขยะอุดท่อ น้ำท่วมขังหน้าบ้าน", "ฝนตกทีไรน้ำท่วม ขยะเต็มซอย", "ขยะหลังน้ำท่วม"]


def _map_ticket(ticket_id, when, text="น้ำท่วมขังหน้าซอย", kinds=("น้ำท่วม",)):
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [100.6, 13.67]},
            "properties": {"ticket_id": ticket_id, "description": text, "timestamp": when.strftime("%Y-%m-%d %H:%M:%S"),
                           "problem_type_fondue": list(kinds), "problem_type_abdul": None, "state": "รอรับเรื่อง",
                           "address": "แขวงบางนาเหนือ เขตบางนา กรุงเทพมหานคร", "photo_url": None}}


def test_traffy_map_api_tickets_read_like_search_results():
    # NOW is 21:13:20 in Bangkok; the map API gives Bangkok time without a zone
    items = parse_traffy(traffy_map_results([
        _map_ticket("2026-MAP1", datetime(2026, 9, 21, 21, 0)),
        _map_ticket("2026-MAP2", datetime(2026, 9, 21, 21, 5), text="ขยะหลังน้ำท่วม", kinds=("ความสะอาด",)),
        _map_ticket("2026-MAP3", datetime(2026, 9, 21, 14, 0)),       # over 6 h ago
    ]), now=NOW)
    assert [i["id"] for i in items] == ["2026-MAP1"]
    assert items[0]["ts"] == NOW - 800
    assert (items[0]["district"], items[0]["lat"], items[0]["lng"]) == ("บางนา", 13.67, 100.6)


def test_traffy_reads_the_map_api_when_the_search_api_is_down(monkeypatch):
    recent = datetime.now(BKK_TZ) - timedelta(minutes=10)
    asked = []

    def fake_get(url, timeout=30):
        asked.append(url)
        if "/search" in url:
            raise TimeoutError("The read operation timed out")
        # every query finds the same ticket: it is listed once
        return json.dumps({"features": [_map_ticket("2026-MAP1", recent.replace(tzinfo=None))]})

    monkeypatch.setattr(flood_feeds, "_get", fake_get)
    feed = TraffyFloodReports()
    now = recent.timestamp() + 600
    # found by the last search: one not in the map API (no category yet), one over 6 h old
    feed.items = [{"id": "2026-OLD1", "ts": int(now - 3600)}, {"id": "2026-OLD2", "ts": int(now - 7 * 3600)}]
    items = feed.fetch()
    assert [i["id"] for i in items] == ["2026-MAP1", "2026-OLD1"]
    assert len(asked) == 1 + len(flood_feeds.TRAFFY_MAP_QUERIES)


def test_traffy_joins_the_search_and_map_apis(monkeypatch):
    now = datetime.now(BKK_TZ)
    newest = (now - timedelta(minutes=10)).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.000000+00")

    def fake_get(url, timeout=30):
        if "/search" in url:     # the newest tickets, with or without a category
            return json.dumps({"results": [{**_ticket("น้ำท่วมขังหน้าบ้าน", ts=newest), "ticket_id": "2026-NEW1"}]})
        # the whole 6 h, categorised tickets only; NEW1 is in both and listed once
        return json.dumps({"features": [_map_ticket("2026-NEW1", (now - timedelta(minutes=10)).replace(tzinfo=None)),
                                        _map_ticket("2026-MAP1", (now - timedelta(hours=5)).replace(tzinfo=None))]})

    monkeypatch.setattr(flood_feeds, "_get", fake_get)
    items = TraffyFloodReports().fetch()
    assert [i["id"] for i in items] == ["2026-NEW1", "2026-MAP1"]
    assert items[0]["text"] == "น้ำท่วมขังหน้าบ้าน"


def test_traffy_fails_only_when_both_apis_fail(monkeypatch):
    def fake_get(url, timeout=30):
        raise TimeoutError("The read operation timed out")

    monkeypatch.setattr(flood_feeds, "_get", fake_get)
    with pytest.raises(RuntimeError, match="search API.*map API"):
        TraffyFloodReports().fetch()


def test_traffy_hides_contact_details():
    text = ("น้ำท่วมขังในซอย\nติดต่อคุณ ยุ้ย 0853712178\nบ้านเลขที่: 54/63\n"
            "คุณ พรรณรี เบอร์โทรศัพท์ 093-725-5762 โดยเฉพาะบ้านเลขที่ 68/158 และ 68/110 อีเมล a.b@mail.com")
    (item,) = parse_traffy([_ticket(text)], now=NOW)
    for private in ("0853712178", "093-725-5762", "ยุ้ย", "พรรณรี", "54/63", "68/110", "a.b@mail.com"):
        assert private not in item["text"]
    assert item["text"].startswith("น้ำท่วมขังในซอย\n(ซ่อนข้อมูลติดต่อ)\nบ้านเลขที่: (ซ่อน)\nคุณ(ซ่อนชื่อ)")


PAGE = """
<div class="link-list-content"><div class="link-list-title">
<a href="/warning-and-events/warning-storm/&#xE1D;&#xE19;-6-222-2569">ฝนตกหนักถึงหนักมากบริเวณประเทศไทย (มีผลกระทบจนถึงวันที่ 27 กันยายน 2569) ฉบับที่ 6 (222/2569)</a></div>
<p>ในช่วงวันที่ 24 – 27 ก.ย. 69 ภาคกลาง รวมทั้งกรุงเทพมหานครและปริมณฑล จะมีฝนตกหนัก</p>
<span>วันที่ข้อมูล:</span><span>24 กันยายน 2569</span></div>
</div>
<div class="link-list-content"><div class="link-list-title">
<a href="/warning-and-events/warning-storm/x">คลื่นลมแรงบริเวณทะเลอันดามัน ฉบับที่ 1 (200/2569)</a></div>
<p>ภาคใต้ฝั่งตะวันตก</p><span>วันที่ข้อมูล:</span><span>2 กันยายน 2569</span></div>
</div>
"""


def test_tmd_list_page():
    first, second = parse_tmd(PAGE)
    assert first["series"] == "ฝนตกหนักถึงหนักมากบริเวณประเทศไทย"
    assert first["date"] == "2026-09-24" and first["bkk"] is True
    assert first["url"].startswith("https://www.tmd.go.th/warning-and-events/warning-storm/%E0%B8%9D")
    assert second["bkk"] is False and second["date"] == "2026-09-02"


def _hdms(gid, province="กรุงเทพมหานคร", type_id=1, end=None):
    return {"gid": gid, "incident_type_id": type_id, "province": province, "amphoe": "จตุจักร",
            "start_date": "2026-09-21T10:00:00.000000Z", "end_date": end, "road_code": "0031",
            "section_name": "ดินแดง - งามวงศ์วาน", "km_start": "9+200", "flood_level": "50",
            "case_name": "น้ำท่วมขัง", "latitude": "13.8", "longitude": "100.56",
            "tel": "0800000000", "reporter_name": "someone"}


def test_hdms_keeps_bangkok_vicinity_floods_open_or_just_closed():
    items = parse_hdms([
        _hdms(1),
        _hdms(2, province="ชลบุรี"),
        _hdms(3, type_id=2),
        _hdms(4, end="2026-09-21T13:00:00Z"),   # closed 73 min before NOW: kept, as ended
        _hdms(5, end="2026-09-21T09:00:00Z"),   # closed 5 h before NOW: dropped
    ], now=NOW)
    assert [i["id"] for i in items] == ["hdms-1", "hdms-4"]
    assert items[0]["active"] is True and items[1]["active"] is False
    assert items[0]["place"] == "ทล.31 ดินแดง - งามวงศ์วาน กม.9+200" and items[0]["depth_cm"] == "50"
    assert "tel" not in items[0] and "reporter_name" not in items[0]
    assert items[0]["photos"] == []


def test_hdms_photos_keep_images_with_https_links_only():
    photos = parse_hdms_photos([
        {"file_type": "image", "file_path": "https://hdms.doh.go.th/attachment/s3/a.jpg",
         "file_thumbnail": "https://hdms.doh.go.th/attachment/s3/a-thumbnail.jpg"},
        {"file_type": "image", "file_path": "https://hdms.doh.go.th/attachment/s3/b.jpg", "file_thumbnail": ""},
        {"file_type": "video", "file_path": "https://hdms.doh.go.th/attachment/s3/c.mp4"},
        {"file_type": "image", "file_path": "javascript:alert(1)"},
    ])
    assert photos == [
        {"url": "https://hdms.doh.go.th/attachment/s3/a.jpg", "thumb": "https://hdms.doh.go.th/attachment/s3/a-thumbnail.jpg"},
        {"url": "https://hdms.doh.go.th/attachment/s3/b.jpg", "thumb": "https://hdms.doh.go.th/attachment/s3/b.jpg"},
    ]


JS100_PAGE = """
<li>
<h4>21  กันยายน 2569,   20:50น.</h4>
<p>น้ำท่วมขังเสมอฟุตบาท ถนนเทพรัตน ขาเข้า ตั้งแต่หน้าเมกาบางนา</p>
</li>
<li>
<h4>21  กันยายน 2569,   20:40น.</h4>
<p>น้ำท่วมขัง ถนนสุขุมวิท ขาเข้า ช่วงเลยอินเด็กซ์ ลิฟวิ่ง มอลล์ พัทยา</p>
</li>
<li>
<h4>21  กันยายน 2569,   20:30น.</h4>
<p>รถเสีย สะพานตากสิน ขาออก</p>
</li>
<li>
<h4>18  กันยายน 2569,   08:00น.</h4>
<p>น้ำขัง ถนนวิภาวดีรังสิต</p>
</li>
"""


def test_js100_keeps_recent_flood_items_in_the_area():
    items = parse_js100(JS100_PAGE, now=NOW)
    assert [i["text"] for i in items] == ["น้ำท่วมขังเสมอฟุตบาท ถนนเทพรัตน ขาเข้า ตั้งแต่หน้าเมกาบางนา"]
    assert items[0]["ts"] == NOW - 1400   # 20:50 Bangkok time, NOW is 21:13:20
