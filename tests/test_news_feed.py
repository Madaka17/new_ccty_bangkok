from backend.core import news_feed as nf

NOW = 1791000000   # 2026-10-03


def _rss(*items):
    body = "".join(f"<item><title>{t}</title><link>{l}</link><pubDate>{d}</pubDate></item>" for t, l, d in items)
    return f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>x</title>{body}</channel></rss>'


def test_kind_of_headlines():
    assert nf.kind_of("น้ำท่วมหนัก อยุธยา 12 อำเภอ") == "flood"
    assert nf.kind_of("รถกระบะพลิกคว่ำ ถนนมิตรภาพ เจ็บ 3") == "accident"
    assert nf.kind_of("หนุ่มวัย 28 เมาขับเก๋งชนสาวไทย-เยอรมัน ขณะข้ามถนนย่านทองหล่อ ดับ 2") == "accident"
    assert nf.kind_of("ชายซิ่งกระบะฝ่าไฟแดง ชน 2 ชาวเยอรมันขณะข้ามทางม้าลาย") == "accident"
    assert nf.kind_of("รถเก๋งเฉี่ยวมอไซค์ จุดยูเทิร์น") == "accident"
    assert nf.kind_of("แฟนคลับท่วมท้นงานคอนเสิร์ต") == ""
    assert nf.kind_of("เค้ก ชนัฐกานต์ วินด์เซิร์ฟสาว คว้าทองแดง") == ""
    assert nf.kind_of("ผวจ.อุดรฯชวนนั่งรถไฟ เที่ยวพืชสวนโลก") == ""
    assert nf.kind_of("ทีมรถแข่งไทยชนะเลิศ") == ""
    assert nf.kind_of("หุ้นไทยวันนี้ปิดบวก") == ""


def test_parse_rss_keeps_recent_flood_and_accident_with_province():
    xml = _rss(("น้ำท่วมหนัก จ.สุโขทัย ชาวบ้านอพยพ", "https://www.matichon.co.th/a1", "Sat, 03 Oct 2026 03:00:00 +0700"),
               ("รถชนกันบนถนนมิตรภาพ นครราชสีมา", "https://www.matichon.co.th/a2", "Sat, 03 Oct 2026 02:00:00 +0700"),
               ("ราคาทองวันนี้", "https://www.matichon.co.th/a3", "Sat, 03 Oct 2026 01:00:00 +0700"),
               ("น้ำท่วมเมื่อสัปดาห์ก่อน", "https://www.matichon.co.th/a4", "Sat, 26 Sep 2026 01:00:00 +0700"),
               ("น้ำป่าไหลหลาก", "javascript:alert(1)", "Sat, 03 Oct 2026 01:00:00 +0700"))
    items = nf.parse_rss(xml, "มติชน", now=NOW)
    assert [(i["kind"], i["province"]) for i in items] == [("flood", "สุโขทัย"), ("accident", "นครราชสีมา")]
    assert items[0]["source"] == "มติชน" and items[0]["link"] == "https://www.matichon.co.th/a1"


def test_parse_rss_takes_the_cover_picture():
    xml = ('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/"><channel>'
           '<item><title>น้ำท่วมถนน a</title><link>https://www.matichon.co.th/a1</link><pubDate>Sat, 03 Oct 2026 03:00:00 +0700</pubDate>'
           '<media:content url="https://www.matichon.co.th/big.jpg" type="image/jpeg" medium="image"/>'
           '<media:thumbnail url="https://www.matichon.co.th/a1.jpg"/></item>'
           '<item><title>น้ำท่วมถนน b</title><link>https://www.thairath.co.th/a2</link><pubDate>Sat, 03 Oct 2026 03:00:00 +0700</pubDate>'
           '<enclosure url="https://static.thairath.co.th/a2.jpg" type="image/jpeg"/></item>'
           '<item><title>น้ำท่วมถนน c</title><link>https://www.khaosod.co.th/a3</link><pubDate>Sat, 03 Oct 2026 03:00:00 +0700</pubDate>'
           '<enclosure url="https://www.khaosod.co.th/a3.mp3" type="audio/mpeg"/></item>'
           '<item><title>น้ำท่วมถนน d</title><link>https://www.khaosod.co.th/a4</link><pubDate>Sat, 03 Oct 2026 03:00:00 +0700</pubDate>'
           '<media:thumbnail url="javascript:alert(1)"/></item>'
           '</channel></rss>')
    assert [i["image"] for i in nf.parse_rss(xml, "x", now=NOW)] == [
        "https://www.matichon.co.th/a1.jpg", "https://static.thairath.co.th/a2.jpg", "", ""]


def test_merge_drops_reposts_and_sorts_newest_first():
    a = {"title": "น้ำท่วม อยุธยา", "ts": 1}
    b = {"title": "น้ำท่วม อยุธยา!", "ts": 3}
    c = {"title": "รถคว่ำ ลำปาง", "ts": 2}
    assert nf.merge([a, b, c]) == [b, c]
