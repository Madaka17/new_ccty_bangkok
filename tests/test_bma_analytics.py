"""BMA analytics: the history query uses the hour index, and get_analytics is cached briefly."""
import threading
import time
from datetime import datetime, timedelta

from backend.bma import bma_db, bma_service
from backend.bma.bma_db import BmaDatabase


def _insert(db, hour, cars):
    with db.lock:
        conn = bma_db.sqlite3.connect(db.db_path)
        conn.execute("""INSERT INTO bma_history (camid, hour, cars, motorcycles, trucks, total, level, ts, date, week, month, road, district)
                        VALUES ('c1', ?, ?, 0, 0, ?, 'free', ?, '', '', '', '', '')""",
                     (hour, cars, cars, int(time.time())))
        conn.commit()
        conn.close()


def _hour_str(hours_ago):
    return (datetime.now() - timedelta(hours=hours_ago)).strftime('%Y-%m-%dT%H:00')


def test_history_summary_returns_only_hours_inside_the_window(tmp_path):
    db = BmaDatabase(db_path=str(tmp_path / "v.db"))
    _insert(db, _hour_str(30), 111)
    _insert(db, _hour_str(1), 7)
    rows = db.get_history_summary(hours=24)
    assert [r["hour"] for r in rows] == [_hour_str(1)]
    assert rows[0]["cars"] == 7


def test_history_query_uses_the_hour_index(tmp_path):
    db = BmaDatabase(db_path=str(tmp_path / "v.db"))
    cutoff = (datetime.now() - timedelta(hours=24)).strftime('%Y-%m-%dT%H:00')
    with db.lock:
        conn = bma_db.sqlite3.connect(db.db_path)
        plan = " ".join(str(r) for r in conn.execute(
            "EXPLAIN QUERY PLAN " + bma_db.HISTORY_SUMMARY_SQL, (cutoff,)).fetchall())
        conn.close()
    assert "idx_bma_hist_hour" in plan
    assert "SEARCH" in plan
    assert "SCAN bma_history" not in plan


def _scanner(build):
    scanner = bma_service.BmaScanner.__new__(bma_service.BmaScanner)
    scanner._init_analytics_cache()
    calls = []

    def fake_build():
        calls.append(1)
        return build(len(calls))
    scanner._build_analytics = fake_build
    return scanner, calls


def test_analytics_is_built_once_within_the_ttl(monkeypatch):
    monkeypatch.setattr(bma_service, "ANALYTICS_TTL", 30)
    scanner, calls = _scanner(lambda n: {"n": n})
    first = scanner.get_analytics()
    second = scanner.get_analytics()
    assert len(calls) == 1
    assert first is second


def test_analytics_rebuilds_after_the_ttl(monkeypatch):
    monkeypatch.setattr(bma_service, "ANALYTICS_TTL", 0)
    scanner, calls = _scanner(lambda n: {"n": n})
    scanner.get_analytics()
    scanner.get_analytics()
    assert len(calls) == 2


def test_concurrent_callers_share_one_build(monkeypatch):
    monkeypatch.setattr(bma_service, "ANALYTICS_TTL", 30)

    def slow(n):
        time.sleep(0.2)
        return {"n": n}
    scanner, calls = _scanner(slow)
    results = []
    start = threading.Barrier(8)

    def worker():
        start.wait()
        results.append(scanner.get_analytics())
    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(calls) == 1
    assert len(results) == 8 and all(r is results[0] for r in results)


def test_failing_rebuild_keeps_serving_the_last_good_result(monkeypatch):
    monkeypatch.setattr(bma_service, "ANALYTICS_TTL", 0)

    def flaky(n):
        if n > 1:
            raise RuntimeError("db busy")
        return {"n": n}
    scanner, calls = _scanner(flaky)
    good = scanner.get_analytics()
    assert scanner.get_analytics() is good
    assert len(calls) == 2
