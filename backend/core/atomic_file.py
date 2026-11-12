"""Write a JSON file so a crash or a failed dump never leaves a truncated file behind."""
import json
import os
import threading
import time

# Windows can refuse os.replace while a reader (antivirus, the monitor app) holds the target open
REPLACE_RETRIES = 5


def write_json_atomic(path, data, **dump_kwargs):
    """Dump to a per-thread tmp file, fsync, then swap it over path. On failure the old file stays."""
    tmp = f"{path}.{threading.get_ident()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, **dump_kwargs)
            f.flush()
            os.fsync(f.fileno())
        for attempt in range(REPLACE_RETRIES + 1):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == REPLACE_RETRIES:
                    raise
                time.sleep(0.05)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
