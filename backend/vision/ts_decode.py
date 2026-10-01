"""
Decode the first frame of HLS segments to JPEG, in a process of its own.

    python -m backend.vision.ts_decode < jobs      (one "<segment.ts>\t<frame.jpg>" per line)

Run by itic_frames.py. FFmpeg inside OpenCV has crashed the server on corrupt Longdo streams before, so
segments are never decoded in the server process: a crash here only loses the frames of one round.
Frames are scaled down to MAX_SIDE, enough for the flood watch and small to keep in memory.
"""
import sys

import cv2

MAX_SIDE = 704


def main():
    for line in sys.stdin:
        src, _, dst = line.rstrip("\r\n").partition("\t")
        if not dst:
            continue
        cap = cv2.VideoCapture(src)
        ok, frame = cap.read()
        cap.release()
        if not ok or frame is None:
            continue
        h, w = frame.shape[:2]
        scale = MAX_SIDE / max(h, w)
        if scale < 1:
            frame = cv2.resize(frame, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
        cv2.imwrite(dst, frame, [cv2.IMWRITE_JPEG_QUALITY, 90])


if __name__ == "__main__":
    main()
