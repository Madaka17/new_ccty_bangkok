import logging
import sys

from backend.core.log import get_logger


def test_same_text_as_print(capsys):
    get_logger("BMA").info("x 1")
    assert capsys.readouterr().out == "[BMA] x 1\n"


def test_untagged(capsys):
    get_logger("").info("=" * 3)
    assert capsys.readouterr().out == "===\n"


def test_warning_same_format(capsys):
    get_logger("Warning").warning("cameras_bkk.json not found")
    captured = capsys.readouterr()
    assert captured.out == "[Warning] cameras_bkk.json not found\n"
    assert captured.err == ""


def test_no_duplicate_handlers():
    for _ in range(3):
        get_logger("BMA")
    # pytest adds its own capture handlers to bkk, so count only ours
    ours = [h for h in logging.getLogger("bkk").handlers if h.get_name() == "bkk-stdout"]
    assert len(ours) == 1


def test_percent_text_is_not_a_format_string(capsys):
    get_logger("BMA").info("50% done")
    assert capsys.readouterr().out == "[BMA] 50% done\n"


def test_same_tag_same_logger_and_tag_spelling_is_exact():
    assert get_logger("AI worker") is get_logger("AI worker")
    assert get_logger("AI worker") is logging.getLogger("bkk.AI worker")
    assert get_logger("AI worker") is not get_logger("AI Worker")


def test_does_not_reach_root_logger(capsys):
    seen = []

    class Catch(logging.Handler):
        def emit(self, record):
            seen.append(record.getMessage())

    root = logging.getLogger()
    catch = Catch()
    root.addHandler(catch)
    try:
        get_logger("BMA").info("only once")
    finally:
        root.removeHandler(catch)
    assert seen == []
    assert capsys.readouterr().out == "[BMA] only once\n"


def test_no_stdout_is_silent(monkeypatch, capsys):
    # A windowless pythonw run has sys.stdout None; print() did nothing there, so logging must too.
    monkeypatch.setattr(sys, "stdout", None)
    get_logger("X").info("y")   # must not raise
    assert capsys.readouterr().err == ""
