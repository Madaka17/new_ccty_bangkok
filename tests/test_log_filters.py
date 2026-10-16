import logging
import sys

from backend.core.log_filters import DropClientResets, quiet_client_resets


def rec(msg, exc):
    try:
        raise exc
    except Exception:
        info = sys.exc_info()
    return logging.LogRecord("asyncio", logging.ERROR, __file__, 1, msg, None, info)


def test_drops_only_client_reset_in_connection_lost():
    f = DropClientResets()
    assert f.filter(rec("Exception in callback _ProactorBasePipeTransport._call_connection_lost()",
                        ConnectionResetError(10054, "forcibly closed"))) is False
    assert f.filter(rec("Exception in callback _ProactorBasePipeTransport._call_connection_lost()",
                        RuntimeError("other"))) is True
    assert f.filter(rec("Task exception was never retrieved", ConnectionResetError())) is True
    assert f.filter(logging.LogRecord("asyncio", logging.ERROR, __file__, 1, "plain", None, None)) is True


def test_install_is_idempotent():
    quiet_client_resets()
    quiet_client_resets()
    assert sum(isinstance(x, DropClientResets) for x in logging.getLogger("asyncio").filters) == 1
