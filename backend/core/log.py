"""
Tagged logging that prints exactly like the old print("[Tag] text") calls.

get_logger("BMA").info("x 1") writes "[BMA] x 1" to stdout. Records do not reach the root logger, so
nothing is printed twice. The handler looks up sys.stdout on each emit, so pytest capsys and the
server's stdout re-wrap still see the output.
"""
import logging
import sys

_ROOT = "bkk"
_HANDLER_NAME = "bkk-stdout"


class _StdoutHandler(logging.Handler):
    def emit(self, record):
        try:
            # Read sys.stdout here, not at setup: the server swaps it at startup and tests capture it.
            stream = sys.stdout
            stream.write(self.format(record) + "\n")
            stream.flush()
        except Exception:
            self.handleError(record)


class _TagFormatter(logging.Formatter):
    def format(self, record):
        text = record.getMessage()  # no %-formatting unless args are given, so "50%" is safe
        tag = record.name[len(_ROOT) + 1:]
        return f"[{tag}] {text}" if tag else text


def _configure():
    root = logging.getLogger(_ROOT)
    # Check by name, not by class: a module reload would otherwise add a second handler.
    if any(h.get_name() == _HANDLER_NAME for h in root.handlers):
        return
    handler = _StdoutHandler()
    handler.set_name(_HANDLER_NAME)
    handler.setFormatter(_TagFormatter())
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    root.propagate = False


def get_logger(tag: str) -> logging.Logger:
    """Logger for one print tag. Same tag, same logger; "" gives the untagged logger."""
    _configure()
    return logging.getLogger(f"{_ROOT}.{tag}" if tag else _ROOT)
