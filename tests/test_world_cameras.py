"""Parsing of the camera lists read straight from each agency (world_cameras.py)."""
from backend.vision import world_cameras as w

PAKKRED = '''
const tourStops = [[{"lat":13.9055,"lng":100.5211},"\u0e16\u0e19\u0e19 1",1],[{"lat":13.9077,"lng":100.5039},"x",2]];
<a onclick='view_cctv("CAMPK001", "1. ถนน 1")'>1</a> <a onclick='view_cctv("CAMPK002", "2. x")'>2</a>
'''
SAMUI = '''<script>const cameras = [{"id":1,"name":"สามแยก","location":"อ่างทอง","lat":9.53,"lng":99.93},
{"id":"x","name":"bad","lat":9.5,"lng":99.9}];</script>'''


def test_pakkred(monkeypatch):
    monkeypatch.setattr(w, "_get", lambda url, *a, **k: PAKKRED.encode())
    cams = w.read_pakkred()
    assert [c["camid"] for c in cams] == ["pakkred-CAMPK001", "pakkred-CAMPK002"]
    assert cams[0]["title"] == "ถนน 1" and cams[0]["province"] == "นนทบุรี"
    assert cams[0]["imgurl"].endswith("name=CAMPK001_thumb.jpg")


def test_samui(monkeypatch):
    monkeypatch.setattr(w, "_get", lambda url, *a, **k: SAMUI.encode())
    cams = w.read_samui()
    assert len(cams) == 1 and cams[0]["media"] == "video"
    assert cams[0]["video_url"].endswith("stream.php?id=1")
    assert cams[0]["province"] == "สุราษฎร์ธานี"


def test_pattaya_skips_offline(monkeypatch):
    data = b'{"details":{"items":[{"id":"a","name":"CC-1","location":"x","lat":12.9,"lng":100.9,"monitorState":"online"},' \
           b'{"id":"b","name":"CC-2","location":"","lat":12.9,"lng":100.9,"monitorState":"unknown"},' \
           b'{"id":"c","name":"CC-3","location":"y","lat":12.9,"lng":100.9,"monitorState":"offline"}]}}'
    monkeypatch.setattr(w, "_get", lambda url, *a, **k: data)
    assert [c["title"] for c in w.read_pattaya()] == ["x (CC-1)", "CC-2"]


def test_image_bytes_only_for_listed_dwr_cameras(tmp_path, monkeypatch):
    monkeypatch.setattr(w, "IMAGE_DIR", str(tmp_path))
    cams = w.WorldCameras.__new__(w.WorldCameras)
    cams._by_id = {"pakkred-CAMPK001": {"camid": "pakkred-CAMPK001", "source": "pakkred"}}
    assert cams.image_bytes("pakkred-CAMPK001") is None
    assert cams.image_bytes("dwr-unknown") is None


def test_hatyai_keeps_recent_cctv_only(monkeypatch):
    import json, time
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    rows = [
        {"enable": 1, "name": "bangsala", "title": "สะพานบางศาลา", "atDate": now, "photo": "https://h/b.jpg", "location": {"latitude": 6.93, "longitude": 100.44}},
        {"enable": 1, "name": "radartmd", "title": "เรดาร์สทิงพระ", "atDate": now, "photo": "https://h/r.jpg", "location": {"latitude": 7.4, "longitude": 100.4}},
        {"enable": 1, "name": "utapao", "title": "ประตูระบายน้ำ", "atDate": "2026-01-01 00:00:00", "photo": "https://h/u.jpg", "location": {"latitude": 6.98, "longitude": 100.4}},
    ]
    monkeypatch.setattr(w, "_get", lambda url, *a, **k: json.dumps({"items": rows}).encode())
    assert [c["camid"] for c in w.read_hatyai()] == ["hatyai-bangsala"]


def test_thaiwater_takes_egat_https_only(monkeypatch):
    import json
    def row(i, agency, url):
        return {"id": i, "title": f"t{i}", "lat": "6.3", "long": "101.2", "is_active": True, "cctv_url": url,
                "agency": {"agency_shortname": {"en": agency}}, "geocode": {"province_name": {"th": "ยะลา"}}}
    data = {"data": [row(1, "EGAT", "https://e/1.jpg"), row(2, "EGAT", "http://e/2.jpg"), row(3, "DWR", "https://d/3.jpg")]}
    monkeypatch.setattr(w, "_get", lambda url, *a, **k: json.dumps(data).encode())
    cams = w.read_thaiwater()
    assert [c["camid"] for c in cams] == ["egat-1"] and cams[0]["province"] == "ยะลา"
