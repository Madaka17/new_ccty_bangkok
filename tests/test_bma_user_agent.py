"""The BMA Traffic site resets the connection for Chrome/124 (from 2026-10-26); the Pi went 0 frames on it."""
from backend.bma.bma_session import BmaSession


def test_bma_session_does_not_send_the_blocked_chrome_124_user_agent():
    ua = BmaSession()._get_session().headers["User-Agent"]
    assert "Chrome/124." not in ua
    assert "python-requests" not in ua
