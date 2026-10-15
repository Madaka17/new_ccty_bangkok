"""
Log filters for the server console / log file.

quiet_client_resets(): on Windows, asyncio's proactor logs a full traceback ("Exception in callback
_ProactorBasePipeTransport._call_connection_lost() ... ConnectionResetError: [WinError 10054]") every time a
visitor's browser drops the connection first. That is normal traffic, not a fault, and it buried real errors
in the production window. Only that exact case is dropped; every other asyncio error still shows.
"""
import logging


class DropClientResets(logging.Filter):
    def filter(self, record):
        exc = record.exc_info[1] if record.exc_info else None
        return not (isinstance(exc, ConnectionResetError) and "_call_connection_lost" in record.getMessage())


def quiet_client_resets():
    log = logging.getLogger("asyncio")
    if not any(isinstance(f, DropClientResets) for f in log.filters):
        log.addFilter(DropClientResets())
