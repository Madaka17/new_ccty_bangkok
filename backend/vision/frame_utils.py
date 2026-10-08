"""
Small helpers the camera patrols share (helmet_service, wrongway_service, violation_service, flood_cam_service):
ids that are safe in file names, a frame fingerprint to spot frozen feeds, box overlap and JPEG writing.
"""
import re

import cv2
import numpy as np

_SAFE_ID = re.compile(r"[\w.-]{1,120}")   # \w as in safe_name(): letters, digits, _


def safe_id(s):
    """An id from a URL, usable in a file name: never a path (no separators, no drive, no ..)."""
    s = str(s)
    if not _SAFE_ID.fullmatch(s) or ".." in s:
        raise ValueError("bad id")
    return s


def fingerprint(frame):
    """Tiny grayscale thumbnail bytes: equal for a frozen feed, different for any real new frame."""
    small = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (24, 18), interpolation=cv2.INTER_AREA)
    return small.tobytes()


def same_scene(a, b, tol=6):
    if a is None or b is None or len(a) != len(b):
        return False
    return int(np.abs(np.frombuffer(a, np.uint8).astype(np.int16) - np.frombuffer(b, np.uint8).astype(np.int16)).mean()) <= tol


def iou(a, b):
    ix1, iy1, ix2, iy2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    if not inter:
        return 0.0
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua else 0.0


def safe_name(s):
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(s))


def write_jpeg(path, img, q=90):
    # cv2.imwrite cannot take non-ASCII paths on Windows (the data dir has a space / Thai in places)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])
    if not ok:
        return False
    with open(path, "wb") as f:
        f.write(buf.tobytes())
    return True
