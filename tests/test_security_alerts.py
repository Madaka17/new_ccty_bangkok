import logging

from launch.security_check import alerts


class Clock:
    def __init__(self, t=1.78e9):
        self.t = t

    def __call__(self):
        return self.t


class Sender:
    def __init__(self, code=200):
        self.sent = []
        self.code = code

    def __call__(self, text):
        self.sent.append(text)
        return self.code


def mk(tmp_path, code=200):
    clock, sender = Clock(), Sender(code)
    a = alerts.Alerter(sender=sender, clock=clock, state_path=str(tmp_path / "st.json"), sync=True)
    return a, clock, sender


def web(ip="9.9.9.9", owner=False):
    return {"type": "web", "kind": "probe", "ip": ip, "owner": owner, "cc": "RU", "country": "Russia"}


def ssh(event, ip="9.9.9.9", owner=False):
    return {"type": "ssh", "event": event, "ip": ip, "user": "root", "owner": owner, "cc": "CN", "country": "China"}


def test_ssh_accepted_outside_alerts_immediately(tmp_path):
    a, _, s = mk(tmp_path)
    out = a.observe(ssh("accepted"))
    assert len(out) == 1 and out[0]["level"] == "critical" and out[0]["type"] == "alert"
    assert out[0]["text"] == "🚨 มีคนเข้า SSH เครื่อง Pi สำเร็จจากนอกบ้าน: 9.9.9.9 (China) ผู้ใช้ root"
    assert s.sent == [out[0]["text"]]


def test_owner_events_never_alert_or_send(tmp_path):
    a, _, s = mk(tmp_path)
    assert a.observe(ssh("accepted", owner=True)) == []
    for _ in range(150):
        a.observe(web(owner=True))
    assert s.sent == []


def test_self_check_ignored(tmp_path):
    a, _, s = mk(tmp_path)
    ev = web()
    ev["kind"] = "self_check"
    for _ in range(150):
        assert a.observe(ev) == []


def test_web_burst_at_100_in_60s(tmp_path):
    a, clock, s = mk(tmp_path)
    for i in range(99):
        assert a.observe(web()) == []
        clock.t += 0.1
    out = a.observe(web())
    assert len(out) == 1 and out[0]["level"] == "warn"
    assert out[0]["text"] == "⚠️ เว็บโดนยิงถี่ 100 ครั้งใน 1 นาที ตัวหลัก 9.9.9.9 (Russia)"


def test_web_below_threshold_when_spread_out(tmp_path):
    a, clock, s = mk(tmp_path)
    for _ in range(300):
        assert a.observe(web()) == []
        clock.t += 1.0   # 60 per window at most
    assert s.sent == []


def test_ssh_burst_20_in_5_min(tmp_path):
    a, clock, s = mk(tmp_path)
    outs = []
    for i in range(20):
        outs += a.observe(ssh("failed" if i % 2 else "invalid"))
        clock.t += 10
    assert len(outs) == 1
    assert outs[0]["text"] == "⚠️ มีคนพยายามเดารหัส SSH 20 ครั้งใน 5 นาที จาก 9.9.9.9"


def test_cooldown_30_min_per_rule(tmp_path):
    a, clock, s = mk(tmp_path)
    assert len(a.observe(ssh("accepted"))) == 1
    clock.t += 29 * 60
    assert a.observe(ssh("accepted")) == []
    clock.t += 2 * 60
    assert len(a.observe(ssh("accepted"))) == 1
    assert len(s.sent) == 2


def test_cooldown_is_per_rule(tmp_path):
    a, clock, s = mk(tmp_path)
    a.observe(ssh("accepted"))
    for _ in range(100):
        out = a.observe(web())
    assert len(s.sent) == 2


def test_cap_exactly(tmp_path):
    a, clock, s = mk(tmp_path)
    for _ in range(alerts.DAILY_CAP + 5):
        a._do_send("x")
    assert len(s.sent) == alerts.DAILY_CAP + 1
    assert s.sent[-1] == alerts.CAP_TEXT
    a2 = alerts.Alerter(sender=s, clock=clock, state_path=a.state_path, sync=True)
    a2._do_send("y")
    assert len(s.sent) == alerts.DAILY_CAP + 1   # persisted: still capped after a restart


def test_cap_resets_next_day(tmp_path):
    a, clock, s = mk(tmp_path)
    for _ in range(alerts.DAILY_CAP + 1):
        a._do_send("x")
    clock.t += 86400 * 1.5
    a._do_send("again")
    assert s.sent[-1] == "again"


def test_page_alert_even_when_line_off(tmp_path):
    a = alerts.Alerter(sender=None, clock=Clock(), state_path=str(tmp_path / "st.json"), sync=True)
    assert a.line_status() == "off"
    out = a.observe(ssh("accepted"))
    assert len(out) == 1


def test_failed_send_marks_status(tmp_path):
    a, _, s = mk(tmp_path, code=401)
    assert a.line_status() == "on"
    a.observe(ssh("accepted"))
    assert a.line_status() == "failed"


def test_disabled_when_env_missing(tmp_path):
    a = alerts.make_alerter(env_path=str(tmp_path / "none.env"), environ={}, state_path=str(tmp_path / "s.json"))
    assert not a.enabled and a.line_status() == "off"
    assert not a.send_now("x")


def test_enabled_from_env_and_dotenv(tmp_path):
    a = alerts.make_alerter(env_path=str(tmp_path / "none.env"),
                            environ={"LINE_CHANNEL_ACCESS_TOKEN": "tok", "LINE_USER_ID": "U1"})
    assert a.enabled
    p = tmp_path / ".env"
    p.write_text("LINE_CHANNEL_ACCESS_TOKEN=abc\nLINE_USER_ID=U2\n", encoding="utf-8")
    assert alerts.load_config(str(p), {}) == ("abc", "U2")


def test_token_never_in_logs(tmp_path, caplog, monkeypatch):
    secret = "SECRET-TOKEN-123"

    class Boom(Exception):
        pass

    def fake_urlopen(req, timeout=None):
        assert req.get_header("Authorization") == "Bearer " + secret
        raise Boom(secret)   # even an exception that carries the token must not reach the log

    monkeypatch.setattr(alerts.urllib.request, "urlopen", fake_urlopen)
    send = alerts.line_sender(secret, "U-SECRET-USER")
    with caplog.at_level(logging.DEBUG, logger="security_live.alerts"):
        assert send("hi") == 0
        a = alerts.Alerter(sender=send, clock=Clock(), state_path=str(tmp_path / "s.json"), sync=True)
        a.observe(ssh("accepted"))
    assert secret not in caplog.text and "U-SECRET-USER" not in caplog.text
    assert a.line_status() == "failed"


def test_cli_test_prints_ok_without_token(monkeypatch, capsys):
    monkeypatch.setattr(alerts, "load_config", lambda *a, **k: ("tok-xyz", "U9"))
    monkeypatch.setattr(alerts, "line_sender", lambda t, u, timeout=10: (lambda text: 200))
    assert alerts.main(["--test"]) == 0
    out = capsys.readouterr().out
    assert out.strip() == "OK" and "tok-xyz" not in out
    monkeypatch.setattr(alerts, "load_config", lambda *a, **k: ("", ""))
    assert alerts.main(["--test"]) == 1
    assert "failed" in capsys.readouterr().out


def test_ssh_accepted_cooldown_is_per_ip(tmp_path):
    a, clock, s = mk(tmp_path)
    assert len(a.observe(ssh("accepted", ip="9.9.9.9"))) == 1
    clock.t += 60
    assert len(a.observe(ssh("accepted", ip="8.8.8.8"))) == 1
    clock.t += 60
    assert a.observe(ssh("accepted", ip="9.9.9.9")) == []
    assert len(s.sent) == 2


def test_fired_entries_pruned(tmp_path):
    a, clock, s = mk(tmp_path)
    a.observe(ssh("accepted", ip="9.9.9.9"))
    clock.t += alerts.COOLDOWN + 1
    a.observe(ssh("accepted", ip="8.8.8.8"))
    assert list(a._fired) == [("ssh_accepted", "8.8.8.8")]
