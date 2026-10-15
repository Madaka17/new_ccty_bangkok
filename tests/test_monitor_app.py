import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "launch"), str(ROOT / "launch" / "monitor")]
import monitor_app  # noqa: E402
from monitor_store import Store  # noqa: E402


def make(tmp_path, now=1000.0):
    ran, posts = [], []
    store = Store(tmp_path / "m.db")
    api = monitor_app.Api(store, runner=lambda args: ran.append(args),
                          yolo_call=lambda port, method, body, timeout: posts.append((port, body)) or {"enabled": body["enabled"]},
                          now=lambda: now)
    return api, store, ran, posts


def test_action_runs_whitelisted_bat(tmp_path):
    api, _, ran, _ = make(tmp_path)
    out = api.action("production", "restart")
    assert out["ok"]
    assert ran and ran[0][-1].endswith(str(Path("launch") / "production" / "restart.bat"))
    assert api.action("enviro", "stop")["ok"]
    assert ran[-1][-1].endswith(str(Path("launch") / "enviro" / "stop.bat"))


def test_action_refuses_unknown(tmp_path):
    api, _, ran, posts = make(tmp_path)
    assert api.action("production", "del /q *")["ok"] is False
    assert api.action("..\\..\\x", "start")["ok"] is False
    assert api.action("enviro", "yolo_on")["ok"] is False
    assert ran == [] and posts == []


def test_yolo_action(tmp_path):
    api, _, _, posts = make(tmp_path)
    assert api.action("test", "yolo_off")["ok"]
    assert posts == [(8001, {"enabled": False})]


def test_status_collector_alive(tmp_path):
    api, store, _, _ = make(tmp_path, now=1000.0)
    assert api.status()["collector_alive"] is False
    store.set_meta("collector_at", 950)
    assert api.status()["collector_alive"] is True
    store.set_meta("collector_at", 800)
    assert api.status()["collector_alive"] is False


def test_events_filters_and_csv(tmp_path):
    api, store, _, _ = make(tmp_path, now=10_000.0)
    store.add_event(9_000, "server:production", "server", "production", "Production", "ok", "fail", 'said "no", bye')
    store.add_event(1_000, "server:test", "server", "test", "Test", "ok", "stopped", "")
    assert api.events({"hours": 1})["total"] == 1
    assert api.events({"limit": 99999})["total"] == 2
    csv = api.csv_text({})
    assert csv.splitlines()[0] == "time,target,check,from,to,detail"
    assert '"said ""no"", bye"' in csv


def test_services_target_covers_gateway_and_tunnel(tmp_path):
    api, store, _, _ = make(tmp_path, now=10_000.0)
    for i, t in enumerate(["production", "gateway", "tunnel", "test"]):
        store.add_event(9_000 + i, f"service:{t}", "service", t, t, "ok", "fail", "")
    got = api.events({"target": "services"})
    assert got["total"] == 2 and {r["target"] for r in got["rows"]} == {"gateway", "tunnel"}
    rows = api.csv_text({"target": "services"}).splitlines()[1:]
    assert len(rows) == 2 and not any("production" in r for r in rows)


def test_check_now_sets_meta(tmp_path):
    api, store, _, _ = make(tmp_path)
    api.check_now()
    assert store.get_meta("check_now") == "1"


def test_processes_and_log_api(tmp_path, monkeypatch):
    import monitor_processes as mp
    monkeypatch.setattr(mp, "LOG_DIR", tmp_path)
    (tmp_path / "test.log").write_bytes(b"hello\n")
    api, _, _, _ = make(tmp_path)
    names = [p["name"] for p in api.processes()]
    assert names == ["production", "test", "enviro", "camera"]
    assert api.log_tail("test")["lines"] == ["hello"]
    assert api.log_tail("../../x").get("error") == "unknown"
    assert api.open_log("nope") == {"ok": False}
