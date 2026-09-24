"""Alert rules: thresholds, alert once per condition, re-alert on escalation or after it cleared."""
import alert_service
from alert_service import CLEAR_SECONDS, AlertService


def _svc(tmp_path, monkeypatch, **sources):
    pushed = []
    svc = AlertService(str(tmp_path), sources)
    monkeypatch.setattr(svc, "push", lambda topic, title, body, only=None: pushed.append((topic, title, body)) or 1)
    return svc, pushed


def _wet(cm, sid="s1"):
    return lambda: {"wet": [{"id": sid, "name": "หน้าวัด", "road": "ถนนสุขุมวิท", "district": "บางนา", "level_cm": cm}]}


def test_flood_threshold_and_level(tmp_path, monkeypatch):
    for cm, expect in ((20, None), (25, 1), (61, 2)):
        svc, _ = _svc(tmp_path / str(cm), monkeypatch, flood=_wet(cm))
        found = svc.candidates()
        assert (found[0]["level"] if found else None) == expect


def test_alerts_once_while_condition_stays(tmp_path, monkeypatch):
    svc, pushed = _svc(tmp_path, monkeypatch, flood=_wet(30))
    assert len(svc.check(now=1000)) == 1
    assert svc.check(now=1060) == []
    assert len(pushed) == 1


def test_realerts_on_escalation(tmp_path, monkeypatch):
    depth = {"cm": 30}
    svc, pushed = _svc(tmp_path, monkeypatch, flood=lambda: _wet(depth["cm"])())
    svc.check(now=1000)
    depth["cm"] = 70
    assert [a["level"] for a in svc.check(now=1060)] == [2]
    assert pushed[-1][1].startswith("ห้ามขับผ่าน")


def test_realerts_after_condition_cleared(tmp_path, monkeypatch):
    depth = {"cm": 30}
    svc, _ = _svc(tmp_path, monkeypatch, flood=lambda: _wet(depth["cm"])())
    svc.check(now=1000)
    depth["cm"] = 0
    svc.check(now=1000 + CLEAR_SECONDS + 1)
    depth["cm"] = 30
    assert len(svc.check(now=1000 + CLEAR_SECONDS + 60)) == 1


def test_state_survives_restart(tmp_path, monkeypatch):
    svc, _ = _svc(tmp_path, monkeypatch, flood=_wet(30))
    svc.check(now=1000)
    again, pushed = _svc(tmp_path, monkeypatch, flood=_wet(30))
    assert again.check(now=1060) == [] and pushed == []


def test_many_alerts_of_one_topic_go_out_as_one_push(tmp_path, monkeypatch):
    stations = {"wet": [{"id": f"s{i}", "name": f"จุด {i}", "level_cm": 30} for i in range(6)]}
    svc, pushed = _svc(tmp_path, monkeypatch, flood=lambda: stations)
    assert len(svc.check(now=1000)) == 6
    assert len(pushed) == 1
    assert pushed[0][1] == "น้ำท่วมถนน 6 รายการ" and "และอีก 2 รายการ" in pushed[0][2]


def test_sources_and_rules(tmp_path, monkeypatch):
    svc, _ = _svc(
        tmp_path, monkeypatch,
        water=lambda: {"weather": [{"id": "z", "name": "กทม. ใต้", "watch": "red", "areas": "บางนา", "rain_24h": 90, "gust_max": 60},
                                   {"id": "y", "name": "นนทบุรี", "watch": "orange"}],
                       "river": [{"id": "r1", "name": "คลอง", "level": "overflow", "storage_pct": 120}], "canals": []},
        incidents=lambda: {"camera": [{"id": "c1", "kind": "accident", "title": "แยกอโศก"}, {"id": "c2", "kind": "stopped"}],
                           "longdo": [{"id": "l1", "kind": "breakdown", "title": "x"}]},
        bma_events=lambda: {"items": [{"id": 1, "kind": "fire", "title": "ไฟไหม้"}, {"id": 2, "kind": "roadwork", "title": "ปิดการจราจร ถนน A"},
                                      {"id": 3, "kind": "roadwork", "title": "ซ่อมท่อ"}, {"id": 4, "kind": "flood", "title": "น้ำขัง"}]},
        air=lambda: {"items": [{"id": "a1", "level": "very_unhealthy", "pm25": 103}, {"id": "a2", "level": "unhealthy", "pm25": 60}]},
        health=lambda: {"scan": {"ok": False, "age_s": 2000}, "helmet": {"agent_error": None}, "data_disk": {"free_gb": 3, "total_gb": 200}},
    )
    keys = {c["key"] for c in svc.candidates()}
    assert keys == {"zone:z", "bank:r1", "cam:c1", "inc:ไฟไหม้", "inc:ปิดการจราจรถนนA", "air:a1", "sys:scan", "sys:disk"}


def test_same_event_from_longdo_and_bma_alerts_once(tmp_path, monkeypatch):
    svc, pushed = _svc(
        tmp_path, monkeypatch,
        incidents=lambda: {"longdo": [{"id": "l9", "kind": "accident", "title": "คืบหน้าอุบัติเหตุ ปากซอยลาดพร้าว 43"}]},
        bma_events=lambda: {"items": [{"id": 7, "kind": "accident", "title": "อุบัติเหตุ ปากซอยลาดพร้าว 43"},
                                      {"id": 8, "kind": "accident", "title": "รถเสีย ถนนรางน้ำ"}]})
    assert len(svc.check(now=1000)) == 1 and len(pushed) == 1


def test_system_alerts_only_after_debounce(tmp_path, monkeypatch):
    err = {"v": "rate limit"}
    svc, _ = _svc(tmp_path, monkeypatch, health=lambda: {"helmet": {"agent_error": err["v"]}})
    assert svc.check(now=1000) == []
    assert svc.check(now=1000 + 599) == []
    assert [a["key"] for a in svc.check(now=1000 + 600)] == ["sys:agent"]
    err["v"] = None                      # a short blip that clears restarts the wait
    svc2, _ = _svc(tmp_path / "b", monkeypatch, health=lambda: {"helmet": {"agent_error": err["v"]}})
    err["v"] = "x"; svc2.check(now=0); err["v"] = None; svc2.check(now=300); err["v"] = "x"
    assert svc2.check(now=700) == []


def test_broken_source_does_not_stop_others(tmp_path, monkeypatch):
    def boom():
        raise RuntimeError("down")
    svc, _ = _svc(tmp_path, monkeypatch, water=boom, flood=_wet(30))
    assert [c["key"] for c in svc.candidates()] == ["flood:s1"]


def test_subscribe_validates_and_filters_topics(tmp_path, monkeypatch):
    svc, _ = _svc(tmp_path, monkeypatch)
    assert not svc.subscribe({"endpoint": "https://push/x"})["ok"]
    r = svc.subscribe({"endpoint": "https://push/x", "keys": {"p256dh": "k", "auth": "a"}}, ["flood", "bogus"])
    assert r == {"ok": True, "topics": ["flood"]}
    svc.subscribe({"endpoint": "https://push/x", "keys": {"p256dh": "k", "auth": "a"}}, ["air"])
    st = svc.status("https://push/x")
    assert st["subscribers"] == 1 and st["my_topics"] == ["air"]
    assert svc.unsubscribe("https://push/x")["removed"] == 1


def test_push_only_to_subscribers_of_topic(tmp_path, monkeypatch):
    svc = AlertService(str(tmp_path), {})
    sent = []
    monkeypatch.setattr(alert_service, "webpush", lambda info, data, **kw: sent.append(info["endpoint"]))
    keys = {"p256dh": "k", "auth": "a"}
    svc.subscribe({"endpoint": "e-flood", "keys": keys}, ["flood"])
    svc.subscribe({"endpoint": "e-all", "keys": keys})
    assert svc.push("air", "t", "b") == 1 and sent == ["e-all"]


def test_vapid_public_key_is_stable(tmp_path):
    a = AlertService(str(tmp_path), {}).public_key
    assert a and a == AlertService(str(tmp_path), {}).public_key
