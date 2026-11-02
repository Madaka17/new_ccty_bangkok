"""BMA_FETCH=0: a second machine on the same public IP (the Raspberry Pi test) must not double our BMA traffic."""
from backend.bma.bma_service import bma_fetch_enabled


def test_fetch_on_by_default():
    assert bma_fetch_enabled({}) is True


def test_fetch_off_with_zero():
    assert bma_fetch_enabled({"BMA_FETCH": "0"}) is False


def test_fetch_on_with_other_values():
    assert bma_fetch_enabled({"BMA_FETCH": "1"}) is True


def test_off_words_are_accepted():
    for value in ("0", "false", "FALSE", "no", "off", " Off "):
        assert bma_fetch_enabled({"BMA_FETCH": value}) is False, value


def test_yolo_allowed_reads_the_same_off_words():
    from backend.vision.yolo_switch import yolo_allowed
    assert yolo_allowed({}) is True
    assert yolo_allowed({"YOLO_ALLOWED": "1"}) is True
    for value in ("0", "false", "no", "OFF"):
        assert yolo_allowed({"YOLO_ALLOWED": value}) is False, value


class RealSession:
    def __init__(self):
        self.fetches = 0
        self.timeout = 9

    def fetch_snapshot(self, camid, timeout=7.0):
        self.fetches += 1
        return b"jpeg"


def test_no_fetch_session_never_calls_bma():
    # Camera pages, streams and check_now all fetch through scanner.session: none may reach BMA.
    from backend.bma.bma_service import NoFetchSession
    real = RealSession()
    s = NoFetchSession(real)
    assert s.fetch_snapshot("123", timeout=4.0) is None
    assert real.fetches == 0
    assert s.timeout == 9          # everything else still reaches the real session


def test_start_scan_refused_without_fetching():
    import threading
    from backend.bma.bma_service import BmaScanner
    scanner = BmaScanner.__new__(BmaScanner)   # no DB, archiver or cameras needed for this check
    scanner.fetch_enabled = False
    scanner.lock = threading.Lock()
    scanner.is_scanning = False
    out = scanner.start_scan()
    assert out["status"] == "disabled"
    assert scanner.is_scanning is False
