"""Parsing of the Traffy Fondue, TMD, HDMS and JS100 feeds."""
from backend.water.flood_feeds import parse_hdms, parse_js100, parse_tmd, parse_traffy

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
