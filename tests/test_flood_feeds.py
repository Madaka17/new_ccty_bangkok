"""Parsing of the Traffy Fondue and TMD feeds."""
from flood_feeds import parse_tmd, parse_traffy

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
