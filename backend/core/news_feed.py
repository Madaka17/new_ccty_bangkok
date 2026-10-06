"""
Flood and road-accident news from the whole country, for the overview page.

Read from the RSS feeds the news outlets publish themselves (Matichon, Khaosod, Prachachat, Thairath): every
headline that names a flood or a road accident, with its outlet, time, link and the cover picture the outlet
puts in its own feed. Only the headline and that picture are kept and shown, and they link to the outlet's own page. Google News is not used: its feed may only be read in a
personal feed reader.

Polls in a background thread and keeps the last good answer when every feed fails. Served by /api/news.
"""
import email.utils
import html
import re
import time
import xml.etree.ElementTree as ET
import zlib

from backend.core import thai_regions
from backend.water.flood_feeds import _Poller, _get

FEEDS = (
    ("มติชน", "https://www.matichon.co.th/feed"),
    ("ข่าวสด", "https://www.khaosod.co.th/feed"),
    ("ประชาชาติธุรกิจ", "https://www.prachachat.net/feed"),
    ("ไทยรัฐ", "https://www.thairath.co.th/rss/news"),
)
REFRESH = 300
KEEP_HOURS = 48
MAX_ITEMS = 60
MRSS = "{http://search.yahoo.com/mrss/}"

# Headline words. "ท่วม" alone is not enough ("ท่วมท้น" = overwhelming); a flood needs water words with it.
FLOOD = re.compile(r"น้ำท่วม|ท่วมขัง|ท่วมสูง|ท่วมหนัก|ท่วมบ้าน|ท่วมถนน|น้ำป่า|น้ำหลาก|อุทกภัย|ล้นตลิ่ง|น้ำล้น|"
                   r"ผู้ประสบภัยน้ำ|ดินโคลนถล่ม|ดินสไลด์|ระดับน้ำ")
# Most crash headlines read "<vehicle or driver> ... ชน / เฉี่ยว ...": a vehicle word, then ชน or เฉี่ยว not followed by a
# vowel or tone mark, so ชนะ (win), ชนิด, names like ยศชนัน and ชวน (invite) stay out.
ACCIDENT = re.compile(r"อุบัติเหตุ|ประสานงา|ชนท้าย|รถคว่ำ|พลิกคว่ำ|ตกข้างทาง|เสียหลัก|รถตกคลอง|ชนเสา|ชนต้นไม้|"
                      r"(?:รถ|เก๋ง|กระบะ|ไซค์|จยย|จักรยานยนต์|สิบล้อ|ซิ่ง|ขับ).{0,30}?(?:ชน|เฉี่ยว)(?![ะัาำิีึืุู็่้๊๋์])")


def kind_of(title):
    """"flood", "accident" or "" for a headline (flood wins when it names both)."""
    if FLOOD.search(title):
        return "flood"
    if ACCIDENT.search(title):
        return "accident"
    return ""


def cover_of(item):
    """The story's cover picture from its feed item, or "": Matichon, Khaosod and Prachachat give media:thumbnail /
    media:content, Thairath an image enclosure. Only https / http addresses are kept."""
    for el in (item.find(MRSS + "thumbnail"), item.find(MRSS + "content"), item.find("enclosure")):
        if el is None:
            continue
        url = (el.get("url") or "").strip()
        kind = el.get("type") or el.get("medium") or "image"
        if url.startswith(("https://", "http://")) and kind.startswith("image"):
            return url
    return ""


def parse_rss(xml_text, source, now=None):
    """RSS 2.0 text -> flood / accident items of the last KEEP_HOURS: {id, kind, title, link, image, source, ts,
    province}."""
    now = now or time.time()
    out = []
    for it in ET.fromstring(xml_text.strip().encode("utf-8")).iter("item"):
        title = re.sub(r"\s+", " ", html.unescape(it.findtext("title") or "")).strip()
        link = (it.findtext("link") or "").strip()
        kind = kind_of(title)
        if not kind or not link.startswith(("https://", "http://")):
            continue
        try:
            ts = int(email.utils.parsedate_to_datetime(it.findtext("pubDate") or "").timestamp())
        except (TypeError, ValueError):
            continue
        if now - ts > KEEP_HOURS * 3600 or ts > now + 3600:
            continue
        out.append({"id": f"news-{zlib.crc32(link.encode())}", "kind": kind, "title": title[:240], "link": link,
                    "image": cover_of(it), "source": source, "ts": ts, "province": thai_regions.find_in_text(title)})
    return out


def merge(items):
    """Newest first, one item per headline (outlets repost the same story), at most MAX_ITEMS."""
    seen, out = set(), []
    for i in sorted(items, key=lambda i: -i["ts"]):
        key = re.sub(r"\W", "", i["title"])[:60]
        if key in seen:
            continue
        seen.add(key)
        out.append(i)
    return out[:MAX_ITEMS]


class NewsFeed(_Poller):
    name = "News"
    refresh_seconds = REFRESH

    def fetch(self):
        found, failed = [], []
        for source, url in FEEDS:
            try:
                found += parse_rss(_get(url, timeout=30), source)
            except Exception as e:  # noqa: BLE001 - the other outlets may still answer
                failed.append(source)
                print(f"[{self.name}] {source}: {str(e)[:160]}")
        if len(failed) == len(FEEDS):
            raise RuntimeError("every news feed failed")
        return merge(found)

    def status(self, kind=None):
        st = super().status()
        if kind in ("flood", "accident"):
            st["items"] = [i for i in st["items"] if i["kind"] == kind]
            st["total"] = len(st["items"])
        st["sources"] = [s for s, _ in FEEDS]
        return st


news_feed = NewsFeed()
