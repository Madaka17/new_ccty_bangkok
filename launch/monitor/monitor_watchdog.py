"""
Reads launch\\watchdog\\state\\watchdog.log for the monitor: the watchdog task (every 2 min) appends one line per
failed check ("... did not answer (check 1 of 2)") and per restart ("... down: running ...\\restart.bat").
"""
import re
from datetime import datetime
from pathlib import Path

LINE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) (\w+) :\d+ (.+)$")


def read_new(path, offset):
    """New complete lines since byte `offset`: (lines, new offset). A shorter file (rotated) is read from 0."""
    path = Path(path)
    try:
        size = path.stat().st_size
    except OSError:
        return [], 0
    if size < offset:
        offset = 0
    with open(path, "rb") as f:
        f.seek(offset)
        data = f.read()
    end = data.rfind(b"\n") + 1     # a last line still being written waits for the next round
    text = data[:end].decode("utf-8-sig", errors="replace")
    return [ln.rstrip("\r") for ln in text.split("\n") if ln.strip()], offset + end


def parse(line):
    m = LINE.match(line or "")
    if not m:
        return None
    stamp, target, text = m.groups()
    new = "restart" if "down: running" in text else "warn" if "did not answer" in text else None
    if new is None:
        return None
    return {"ts": datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").timestamp(), "target": target, "new": new, "detail": text}
