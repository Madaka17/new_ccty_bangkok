"""The BMA Traffic site moves to the first address that answers (bma_site.py)."""
import requests

from backend.bma import bma_site


class Resp:
    def __init__(self, status, size):
        self.status_code, self.content = status, b"x" * size


def test_failover_picks_the_first_address_that_answers(monkeypatch):
    up = {bma_site.SITES[1]}
    monkeypatch.setattr(bma_site.requests, "get",
                        lambda url, **kw: Resp(200, 400_000) if url.startswith(tuple(up)) else Resp(404, 283))
    monkeypatch.setattr(bma_site, "_current", bma_site.SITES[0])
    assert bma_site.failover() is True and bma_site.base() == bma_site.SITES[1]
    assert bma_site.failover() is False                     # still there: no change
    up.add(bma_site.SITES[0])
    assert bma_site.failover() is True and bma_site.base() == bma_site.SITES[0]   # the first one is back


def test_failover_keeps_the_address_when_none_answers(monkeypatch):
    def down(url, **kw):
        raise requests.ConnectionError()
    monkeypatch.setattr(bma_site.requests, "get", down)
    monkeypatch.setattr(bma_site, "_current", bma_site.SITES[0])
    assert bma_site.failover() is False and bma_site.base() == bma_site.SITES[0]
