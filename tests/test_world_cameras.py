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


def test_pakkred_data_attributes(monkeypatch):
    # The page since Oct 2026: the code and number sit in data-camera / data-title
    page = PAKKRED.split("<a")[0] + '''
<button class="camera-item" data-camera="CAMPK001" data-title="1. ถนน 1 " onclick="view_cctv(this.dataset.camera, this.dataset.title)">
<button class="camera-item" data-camera="CAMPK002" data-title="2. x " onclick="view_cctv(this.dataset.camera, this.dataset.title)">
'''
    monkeypatch.setattr(w, "_get", lambda url, *a, **k: page.encode())
    assert [c["camid"] for c in w.read_pakkred()] == ["pakkred-CAMPK001", "pakkred-CAMPK002"]


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


def test_udon_plays_the_stream_not_a_viewer_session(monkeypatch):
    import json
    rows = [{"id": "6", "title": "วงเวียน", "latitude": "17.40", "longitude": "102.79", "status": "online",
             "videoUrl": "https://streaming.udoncity.go.th:1935/live/cctv_121.stream/chunklist_w2010918290.m3u8"},
            {"id": "7", "title": "ดับ", "latitude": "17.41", "longitude": "102.80", "status": "offline",
             "videoUrl": "https://streaming.udoncity.go.th:1935/live/x.stream/chunklist_w1.m3u8"}]
    monkeypatch.setattr(w, "_get", lambda url, *a, **k: json.dumps({"success": True, "data": rows}).encode())
    cams = w.read_udon()
    assert [c["camid"] for c in cams] == ["udon-6"] and cams[0]["province"] == "อุดรธานี"
    assert cams[0]["hls_url"] == "https://streaming.udoncity.go.th:1935/live/cctv_121.stream/playlist.m3u8"


def test_ddpm_reads_every_page(monkeypatch):
    import json
    def station(code, **extra):
        return {"code": code, "name": f"สะพาน {code}", "latitude": 6.87, "longitude": 101.25, "provName": "ปัตตานี",
                "isActive": 1, "deletedAt": None, **extra}
    pages = {1: [station("PTN07"), station("PTN08", isActive=0)], 2: [station("YLA01", deletedAt="2026-01-01"), station("bad/1")]}
    def get(url, *a, **k):
        page = int(url.split("page=")[1].split("&")[0])
        return json.dumps({"data": pages[page], "totalPages": 2}).encode()
    monkeypatch.setattr(w, "_get", get)
    cams = w.read_ddpm()
    assert [c["camid"] for c in cams] == ["ddpm-PTN07"] and cams[0]["province"] == "ปัตตานี"
    assert cams[0]["station"] == "PTN07" and cams[0]["media"] == "image"


def test_nonthaburi_one_camera_per_picture(monkeypatch):
    import json
    url = ("http://182.52.224.70/MilestoneImageService/ImageService.svc/ImageService/GetImage?width=800&height=450"
           "&ondate=2026-10-06 22:34&cameraname=A1-คลองท่าทราย Cam{}")
    rows = [{"code": "A1", "name": "คลองท่าทราย", "location": {"lat": 13.889, "lng": 100.490}, "cctv": [url.format(1), url.format(2)]},
            {"code": "C1", "name": "ตลาดนนท์", "location": {"lat": 13.86, "lng": 100.51}, "cctv": []}]
    monkeypatch.setattr(w, "_get", lambda u, *a, **k: json.dumps({"station": rows}).encode())
    cams = w.read_nonthaburi()
    assert [c["camid"] for c in cams] == ["nonthaburi-A1-1", "nonthaburi-A1-2"]
    assert cams[0]["title"] == "คลองท่าทราย กล้อง 1" and cams[0]["station"] == "A1-คลองท่าทราย Cam1"


def test_image_bytes_ddpm_takes_the_newest_snapshot(tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(w, "IMAGE_DIR", str(tmp_path))
    asked = []
    def get(url, *a, **k):
        asked.append(url)
        if url.endswith("/stations/PTN07"):
            return json.dumps({"histories": [{"snapshotPath": "snapshots/20261006/1189555824/222548_PTN07_01.jpg"}]}).encode()
        return b"\xff\xd8jpeg"
    monkeypatch.setattr(w, "_get", get)
    cams = w.WorldCameras.__new__(w.WorldCameras)
    cams._by_id = {"ddpm-PTN07": {"camid": "ddpm-PTN07", "source": "ddpm", "station": "PTN07"}}
    assert cams.image_bytes("ddpm-PTN07") == b"\xff\xd8jpeg"
    assert asked[-1] == f"{w.DDPM_API}/snapshots/20261006/1189555824/222548_PTN07_01.jpg"
    assert cams.image_bytes("ddpm-PTN07") == b"\xff\xd8jpeg" and len(asked) == 2   # kept on disk
