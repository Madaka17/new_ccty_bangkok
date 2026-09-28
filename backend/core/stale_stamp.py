"""
"ภาพเก่า" stamp on camera frames served while their source is down.

When the BMA site is down the API keeps serving the scanner's last saved snapshot (and the flood watch
its last judged frame), which looks exactly like a live picture. A frame older than its limit gets a red
frame and a bar across the bottom, in Bangkok time:

    ภาพเก่า · ถ่ายเมื่อ 27 ก.ย. 13:11 · 21 ชม.ที่แล้ว

Only the bytes sent to the browser are stamped; the files the scanner and the AI read stay untouched.
"""
import io
import os
import time
from datetime import datetime, timedelta, timezone

from PIL import Image, ImageDraw, ImageFont

SNAPSHOT_STALE_MINUTES = int(os.getenv("SNAPSHOT_STALE_MINUTES", "15"))   # the scanner revisits a camera every ~4 min
BKK_TZ = timezone(timedelta(hours=7))
MONTH_TH = ("ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.")
FONT_CANDIDATES = (
    "C:\\Windows\\Fonts\\tahoma.ttf",
    "C:\\Windows\\Fonts\\leelawad.ttf",
    "/System/Library/Fonts/Supplemental/Tahoma.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf",
)
RED = (220, 38, 38)
_fonts = {}


def _font(size):
    if size not in _fonts:
        path = next((p for p in FONT_CANDIDATES if os.path.exists(p)), None)
        _fonts[size] = ImageFont.truetype(path, size) if path else None
    return _fonts[size]


def _ago(seconds):
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes} นาทีที่แล้ว"
    if minutes < 48 * 60:
        return f"{minutes // 60} ชม.ที่แล้ว"
    return f"{minutes // 1440} วันที่แล้ว"


def label(frame_ts, now=None):
    t = datetime.fromtimestamp(frame_ts, BKK_TZ)
    return f"ภาพเก่า · ถ่ายเมื่อ {t.day} {MONTH_TH[t.month - 1]} {t:%H:%M} · {_ago((now or time.time()) - frame_ts)}"


def stamp(jpeg, frame_ts, stale_minutes=SNAPSHOT_STALE_MINUTES, now=None):
    """The JPEG as is when the frame is recent (or its time unknown), else with the old-picture frame and bar."""
    now = now or time.time()
    if not jpeg or not frame_ts or now - frame_ts <= stale_minutes * 60:
        return jpeg
    try:
        img = Image.open(io.BytesIO(jpeg)).convert("RGB")
    except Exception:  # noqa: BLE001 - not a picture we can draw on: send it unchanged
        return jpeg
    w, h = img.size
    draw = ImageDraw.Draw(img)
    border = max(3, w // 110)
    draw.rectangle([0, 0, w - 1, h - 1], outline=RED, width=border)
    font = _font(max(12, w // 24))
    text = label(frame_ts, now) if font else datetime.fromtimestamp(frame_ts, BKK_TZ).strftime("OLD FRAME %d/%m %H:%M")
    font = font or ImageFont.load_default()
    box = draw.textbbox((0, 0), text, font=font)
    bar_h = box[3] - box[1] + 10
    draw.rectangle([0, h - bar_h, w, h], fill=RED)
    draw.text((max(6, (w - (box[2] - box[0])) // 2), h - bar_h + 5 - box[1]), text, font=font, fill=(255, 255, 255))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=88)
    return out.getvalue()


def stamp_file(path, stale_minutes=SNAPSHOT_STALE_MINUTES, frame_ts=None):
    """A saved frame's bytes, stamped when it is old; frame_ts defaults to the file's modification time."""
    with open(path, "rb") as f:
        jpeg = f.read()
    return stamp(jpeg, frame_ts or os.path.getmtime(path), stale_minutes)
