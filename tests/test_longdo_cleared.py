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
