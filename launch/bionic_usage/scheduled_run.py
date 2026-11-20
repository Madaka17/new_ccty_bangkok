"""Scheduled task entry point: collect the new Bionic log records, then rebuild the report.

The scheduled task runs this file with pythonw.exe, which has no console, so
nothing here may write to stdout or stderr without checking they exist. Any
failure is written to collect.log next to the database and the run still exits 0,
so a bad night of logs never stops the next run.
"""

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import collect  # noqa: E402
import report  # noqa: E402


def main() -> int:
    """Run collect, then report without opening a browser."""
    try:
        collect.main()
    except Exception:
        collect._append_log(collect.DEFAULT_DB.parent / "collect.log", traceback.format_exc())
    try:
        report.main([])
    except Exception:
        collect._append_log(collect.DEFAULT_DB.parent / "collect.log", traceback.format_exc())
    return 0


if __name__ == "__main__":
    sys.exit(main())
