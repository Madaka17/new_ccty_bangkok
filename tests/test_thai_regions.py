"""Provinces and regions for the nationwide camera tab (thai_regions.py), and the DOH feed key (doh_cameras.py)."""
from collections import Counter

import pytest

from backend.core import thai_regions as t
from backend.vision.doh_cameras import _cell, stream_key


def test_six_regions_hold_77_provinces():
    assert len(t.PROVINCES) == 77
    assert Counter(r for _, r in t.PROVINCES.values()) == {
        t.CENTRAL: 22, t.ISAN: 20, t.SOUTH: 14, t.NORTH: 9, t.EAST: 7, t.WEST: 5}


@pytest.mark.parametrize("raw, name", [
    ("ชลบุรี", "ชลบุรี"), ("จ.ชลบุรี", "ชลบุรี"), ("จังหวัดปทุมธานี", "ปทุมธานี"),
    ("กรุงเทพฯ", "กรุงเทพมหานคร"), ("อยุธยา", "พระนครศรีอยุธยา"), ("Pattaya", ""), ("", ""), (None, ""),
])
def test_normalize(raw, name):
    assert t.normalize(raw) == name


def test_geocode():
    assert t.from_geocode("240101") == "ฉะเชิงเทรา"
    assert t.from_geocode("103605") == "กรุงเทพมหานคร"
    assert t.from_geocode("") == t.from_geocode("99") == ""


@pytest.mark.parametrize("text, name", [
    ("1 - อ.หนองแค จ.สระบุรี", "สระบุรี"),
    ("อ.เมืองกาฬสินธุ์ จ.กาฬสินธุ์", "กาฬสินธุ์"),
    ("122 - ทางเลี่ยงเมืองนครสวรรค์", "นครสวรรค์"),
    ("(กรุงเทพมหานคร) ทางด่วน", "กรุงเทพมหานคร"),
    # short names inside other words are not provinces
    ("สะพานตากสิน เลยแยกไปทางขวา เผยแพร่", ""),
    ("ถ.ลำลูกกา กม.9", ""),
])
def test_find_in_text(text, name):
    assert t.find_in_text(text) == name


def test_in_thailand():
    assert t.in_thailand(13.75, 100.5)
    assert not t.in_thailand(13.73237, 13.73237)   # BMA-1712: latitude in both
    assert not t.in_thailand(0, 0)
    assert not t.in_thailand(None, "x")


@pytest.mark.parametrize("url, key", [
    ("https://camerai1.iticfoundation.org/pass/180.180.242.207:1935/Phase3/PER_3_008_IN.stream/playlist.m3u8", "PER_3_008_IN"),
    ("https://streaming3.highwaytraffic.go.th/PER-3/PER-3-008_IN.stream/playlist.m3u8", "PER_3_008_IN"),
    ("https://streaming1.highwaytraffic.go.th/Phase6/PER_6_029.stream/playlist.m3u8", "PER_6_029"),
    ("https://camera1.iticfoundation.org/hls/10.8.0.21_8002.m3u8", ""),
    (None, ""),
])
def test_stream_key(url, key):
    assert stream_key(url) == key


def test_site_info_cells():
    table = ("<table><tr><td nowrap><b>ชื่อจุดติดตั้ง</b></td><td nowrap>1 - อ.หนองแค จ.สระบุรี</td></tr>"
             "<tr><td nowrap><b>รายละเอียด</b></td><td>ทางหลวง 1\r\n ระหว่าง กม.92-93 </td></tr></table>")
    assert _cell(table, "ชื่อจุดติดตั้ง") == "1 - อ.หนองแค จ.สระบุรี"
    assert _cell(table, "รายละเอียด") == "ทางหลวง 1 ระหว่าง กม.92-93"
