"""Longdo feed: an incident whose "คืบหน้า" update says the road is clear is not active, and each incident
carries in_bkk (inside the Bangkok districts, not just the metro bounding box)."""
import json
import threading
import time

from backend.vision import incident_service as inc

ACC = 3
NEAR = (13.8000, 100.5600)     # inside Bangkok (Watthana / Khlong Toei side)
FAR = (13.9000, 100.7000)      # away from NEAR, same bounding box, past 300 m
NONTHABURI = (13.8600, 100.5150)  # Nonthaburi, outside the Bangkok outline


def _ts(ago=0):
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time() - ago))


def _ev(eid, title, at=NEAR, etype=ACC, start=None, stop=None, desc=''):
    return {'eid': eid, 'type': etype, 'title': title, 'description': desc, 'icon': '', 'contributor': '',
            'latitude': str(at[0]), 'longitude': str(at[1]), 'start': start or _ts(600), 'stop': stop}


class _Resp:
    def __init__(self, body):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


def _refresh(monkeypatch, feed):
    body = json.dumps(feed).encode('utf-8')
    monkeypatch.setattr(inc.urllib.request, 'urlopen', lambda req, timeout=None: _Resp(body))
    m = inc.IncidentManager.__new__(inc.IncidentManager)
    m.lock = threading.Lock()
    m.longdo, m.longdo_recent, m.longdo_floods, m.longdo_floods_national = [], [], [], []
    m.national_incidents, m.closures, m.longdo_updated = [], [], 0
    m._refresh_feed()
    return m


def test_cleared_progress_update_ends_the_accident(monkeypatch):
    feed = [_ev(1, 'อุบัติเหตุ ถนนรัชดา'),
            _ev(2, 'คืบหน้า อุบัติเหตุ ถนนรัชดา เคลื่อนย้ายพ้นกีดขวางแล้ว', start=_ts(60))]
    m = _refresh(monkeypatch, feed)
    assert m.longdo == []
    assert sorted(i['id'] for i in m.longdo_recent) == ['longdo-1', 'longdo-2']


def test_progress_update_that_is_not_clear_keeps_one_active(monkeypatch):
    feed = [_ev(1, 'อุบัติเหตุ ถนนรัชดา'), _ev(2, 'คืบหน้า รถยังติดสะสม')]
    m = _refresh(monkeypatch, feed)
    assert [i['id'] for i in m.longdo] == ['longdo-1']


def test_cleared_update_ends_the_accident_by_title_when_far_away(monkeypatch):
    feed = [_ev(1, 'อุบัติเหตุ ถนนรัชดา หน้าซอย 5'),
            _ev(2, 'คืบหน้า อุบัติเหตุ ถนนรัชดา หน้าซอย 5 เคลื่อนย้ายพ้นกีดขวางแล้ว', at=FAR)]
    m = _refresh(monkeypatch, feed)
    assert m.longdo == []


def test_cleared_update_elsewhere_does_not_end_another_accident(monkeypatch):
    feed = [_ev(1, 'อุบัติเหตุ ถนนรัชดา'),
            _ev(2, 'คืบหน้า อุบัติเหตุ ซอยอื่น เคลื่อนย้ายพ้นกีดขวางแล้ว', at=FAR)]
    m = _refresh(monkeypatch, feed)
    assert [i['id'] for i in m.longdo] == ['longdo-1']


def test_in_bkk_is_false_for_nonthaburi_and_true_for_sukhumvit(monkeypatch):
    feed = [_ev(1, 'อุบัติเหตุ ติวานนท์', at=NONTHABURI), _ev(2, 'อุบัติเหตุ สุขุมวิท', at=NEAR)]
    m = _refresh(monkeypatch, feed)
    flags = {i['id']: i['in_bkk'] for i in m.longdo}
    assert flags == {'longdo-1': False, 'longdo-2': True}


def test_negated_clear_phrase_keeps_the_incident_active(monkeypatch):
    feed = [_ev(1, 'อุบัติเหตุ ถนนรัชดา'), _ev(2, 'คืบหน้า ยังไม่พ้นกีดขวาง')]
    m = _refresh(monkeypatch, feed)
    assert [i['id'] for i in m.longdo] == ['longdo-1']


def test_cannot_open_traffic_does_not_clear_the_incident(monkeypatch):
    feed = [_ev(1, 'อุบัติเหตุ ถนนรัชดา', desc='ไม่สามารถเปิดการจราจรได้')]
    m = _refresh(monkeypatch, feed)
    assert [i['id'] for i in m.longdo] == ['longdo-1']
    assert m.longdo_recent == []


def test_traffic_back_to_normal_clears_the_incident(monkeypatch):
    feed = [_ev(1, 'อุบัติเหตุ ถนนรัชดา', desc='การจราจรกลับมาปกติ')]
    m = _refresh(monkeypatch, feed)
    assert m.longdo == []
    assert [i['id'] for i in m.longdo_recent] == ['longdo-1']


def test_standalone_cleared_item_ages_out_of_the_24_hour_list(monkeypatch):
    feed = [_ev(1, 'อุบัติเหตุ ถนนรัชดา', desc='การจราจรกลับมาปกติ', start=_ts(30 * 3600))]
    m = _refresh(monkeypatch, feed)
    assert m.longdo == [] and m.longdo_recent == []


def test_follow_up_does_not_merge_with_an_incident_more_than_6_hours_older(monkeypatch):
    feed = [_ev(1, 'อุบัติเหตุ ถนนรัชดา', start=_ts(7 * 3600)),
            _ev(2, 'คืบหน้า อุบัติเหตุ ถนนรัชดา เคลื่อนย้ายพ้นกีดขวางแล้ว', start=_ts(60))]
    m = _refresh(monkeypatch, feed)
    assert [i['id'] for i in m.longdo] == ['longdo-1']


def test_follow_up_does_not_merge_with_an_incident_that_started_later(monkeypatch):
    feed = [_ev(1, 'อุบัติเหตุ ถนนรัชดา', start=_ts(60)),
            _ev(2, 'คืบหน้า อุบัติเหตุ ถนนรัชดา เคลื่อนย้ายพ้นกีดขวางแล้ว', start=_ts(600))]
    m = _refresh(monkeypatch, feed)
    assert [i['id'] for i in m.longdo] == ['longdo-1']


def test_breakdown_follow_up_does_not_end_an_accident(monkeypatch):
    feed = [_ev(1, 'อุบัติเหตุ ถนนรัชดา'),
            _ev(2, 'คืบหน้า อุบัติเหตุ ถนนรัชดา เคลื่อนย้ายพ้นกีดขวางแล้ว', etype=1)]
    m = _refresh(monkeypatch, feed)
    assert [i['id'] for i in m.longdo] == ['longdo-1']


def test_the_nearest_incident_is_the_one_that_ends(monkeypatch):
    near_by = (NEAR[0] + 0.0018, NEAR[1])      # about 200 m north of NEAR
    feed = [_ev(1, 'อุบัติเหตุ ถนนรัชดา', start=_ts(900)),
            _ev(2, 'อุบัติเหตุ ถนนรัชดา', at=near_by, start=_ts(800)),
            _ev(3, 'คืบหน้า อุบัติเหตุ ถนนรัชดา เคลื่อนย้ายพ้นกีดขวางแล้ว', at=near_by, start=_ts(60))]
    m = _refresh(monkeypatch, feed)
    assert [i['id'] for i in m.longdo] == ['longdo-1']
    assert 'longdo-2' in [i['id'] for i in m.longdo_recent]


def test_roads_sharing_a_title_prefix_do_not_merge(monkeypatch):
    feed = [_ev(1, 'อุบัติเหตุ ถนนรามอินทรา', at=FAR, start=_ts(900)),
            _ev(2, 'คืบหน้า อุบัติเหตุ ถนนรามคำแหง เคลื่อนย้ายพ้นกีดขวางแล้ว', start=_ts(60))]
    m = _refresh(monkeypatch, feed)
    assert [i['id'] for i in m.longdo] == ['longdo-1']
