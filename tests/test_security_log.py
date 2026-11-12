import sqlite3
from datetime import datetime

from backend.core.security_log import SecurityLog

T0 = datetime(2026, 11, 1, 10, 0, 0).timestamp()


class Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t


def make(tmp_path, clock=None, **kw):
    return SecurityLog(str(tmp_path / "sec.db"), clock=clock or Clock(), **kw)


def test_flush_counts_by_hour_and_kind(tmp_path):
    lg = make(tmp_path)
    for _ in range(3):
        lg.record("probe", "1.1.1.1", "/x")
    lg.record("rate_limited", "1.1.1.1", "/y")
    assert lg.flush() == 4
    s = lg.summary()
    assert s["by_kind"] == {"probe": 3, "rate_limited": 1}
    assert s["total"] == 4


def test_summary_missing_db_is_zero(tmp_path):
    s = SecurityLog(str(tmp_path / "none.db")).summary(30)
    assert s["total"] == 0 and len(s["by_day"]) == 30 and all(d["n"] == 0 for d in s["by_day"])
    assert not (tmp_path / "none.db").exists()


def test_recent_capped_at_500(tmp_path):
    lg = make(tmp_path)
    for i in range(600):
        lg.record("probe", "1.1.1.1", f"/p{i}")
    lg.flush()
    con = sqlite3.connect(str(tmp_path / "sec.db"))
    assert con.execute("SELECT COUNT(*) FROM recent").fetchone()[0] == 500
    con.close()


def test_old_hours_pruned_after_30_days(tmp_path):
    clock = Clock()
    lg = make(tmp_path, clock)
    lg.record("probe", "1.1.1.1", "/x")
    lg.flush()
    clock.t = T0 + 31 * 86400
    lg.flush()
    assert lg.summary()["total"] == 0
    con = sqlite3.connect(str(tmp_path / "sec.db"))
    assert con.execute("SELECT COUNT(*) FROM hourly").fetchone()[0] == 0
    con.close()


def test_idle_flush_does_not_create_db(tmp_path):
    lg = make(tmp_path)
    assert lg.flush() == 0
    assert not (tmp_path / "sec.db").exists()


def test_buffer_overflow_counts_dropped(tmp_path):
    lg = make(tmp_path, buffer_max=5)
    for _ in range(8):
        lg.record("probe", "1.1.1.1", "/x")
    lg.flush()
    assert lg.summary()["by_kind"]["dropped"] == 3


def test_top_ips_and_paths(tmp_path):
    lg = make(tmp_path)
    for _ in range(3):
        lg.record("probe", "A", "/a")
    lg.record("probe", "B", "/b")
    lg.flush()
    s = lg.summary()
    assert s["top_ips"][0] == {"ip": "A", "n": 3}
    assert s["top_paths"][0] == {"path": "/a", "n": 3}
    assert len(s["recent"]) == 4 and s["recent"][0]["ts"] >= s["recent"][-1]["ts"]


def test_record_never_raises(tmp_path):
    lg = SecurityLog(str(tmp_path / "missing" / "dir" / "x.db"), clock=Clock())
    lg.record("probe", "1.1.1.1", "/x" * 500, ua="u" * 500)
    assert lg.flush() == 0


def test_summary_excludes_self_check(tmp_path):
    lg = make(tmp_path)
    for i in range(2):
        lg.record("probe", "1.1.1.1", "/x")
    for i in range(3):
        lg.record("self_check", "9.9.9.9", "/.env")
    lg.flush()
    s = lg.summary()
    assert s["total"] == 2 and s["self_checks"] == 3
    assert "self_check" not in s["by_kind"]
    assert sum(d["n"] for d in s["by_day"]) == 2
    assert [i["ip"] for i in s["top_ips"]] == ["1.1.1.1"]
    assert all(p["path"] != "/.env" for p in s["top_paths"])
    assert all(r["kind"] != "self_check" for r in s["recent"])
