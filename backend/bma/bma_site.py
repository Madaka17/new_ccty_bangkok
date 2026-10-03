"""
Where the BMA Traffic site answers: the camera pictures (bma_service.py) and the traffic centre's news
(bma_events.py) come from the same ASP.NET site, which has more than one address.

On 2026-10-03 cpudapp.bangkok.go.th/bmatraffic/ began answering 404 on every page while the same site kept running
at www.bmatraffic.com (http only). The scanner calls failover() after a scan cycle with almost no pictures, which
moves both readers to the first address whose index.aspx answers, so the next move needs no code change.
"""
from urllib.parse import urlparse

import requests

SITES = ("http://www.bmatraffic.com/", "https://cpudapp.bangkok.go.th/bmatraffic/")
INDEX_MIN_BYTES = 50_000     # the real index.aspx is ~400 KB; an error or parking page is far smaller
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BKK-Traffic-CCTV/2.0"

_current = SITES[0]


def base():
    """The site's base URL, ending in "/"."""
    return _current


def host():
    return urlparse(_current).hostname


def failover(timeout=20):
    """Use the first address whose index.aspx answers. True when the address changed."""
    global _current
    for url in SITES:
        try:
            r = requests.get(f"{url}index.aspx", timeout=timeout, headers={"User-Agent": USER_AGENT})
        except requests.RequestException:
            continue
        if r.status_code == 200 and len(r.content) >= INDEX_MIN_BYTES:
            changed, _current = url != _current, url
            return changed
    return False
