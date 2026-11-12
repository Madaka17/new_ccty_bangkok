"""Code the helmet and wrong-way patrols share: SQLite log, evidence archive, cloud vision call, cache cleanup."""
import base64
import csv
import os
import sqlite3
import time
from datetime import datetime

import cv2

from backend.core import local_llm
from backend.vision.frame_utils import safe_name, write_jpeg
from backend.core.log import get_logger


class PatrolStore:
    """One table of checks. The patrol's lock serialises writes."""

    def __init__(self, db_path, table, schema_sql, index_sql, lock):
        self.db_path = db_path
        self.table = table
        self.schema_sql = schema_sql
        self.index_sql = index_sql
        self.lock = lock

    def init(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute(self.schema_sql)
        conn.execute(self.index_sql)
        conn.commit()
        conn.close()

    def connect(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def insert(self, row):
        with self.lock:
            conn = self.connect()
            conn.execute(f"INSERT OR REPLACE INTO {self.table} VALUES ({','.join('?' * len(row))})", row)
            conn.commit()
            conn.close()

    def update(self, item_id, **fields):
        keys = list(fields)
        with self.lock:
            conn = self.connect()
            conn.execute(f"UPDATE {self.table} SET {', '.join(k + ' = ?' for k in keys)} WHERE id = ?",
                         [fields[k] for k in keys] + [item_id])
            conn.commit()
            conn.close()

    def delete_older(self, cutoff_ts, keep_verdict):
        """Drop routine checks older than cutoff; the verdict worth keeping stays forever (evidence is on the data drive)."""
        with self.lock:
            conn = self.connect()
            try:
                conn.execute(f"DELETE FROM {self.table} WHERE ts < ? AND verdict != ?", (int(cutoff_ts), keep_verdict))
                conn.commit()
            finally:
                conn.close()


def clean_cache_dir(cache_dir, cutoff_ts):
    for name in os.listdir(cache_dir):
        p = os.path.join(cache_dir, name)
        try:
            if os.path.getmtime(p) < cutoff_ts:
                os.remove(p)
        except OSError:
            pass   # gone or locked: the next round tries again


def archive_evidence(archive_dir, csv_name, item_id, camid, cam, crop, marked, label, banner_h, text_y, font_scale,
                     header, values, log_tag):
    """Evidence on the data drive: frame with a banner, the crop, one CSV row. Best effort.
    File names carry the capture time (from the id), not the time the verdict came in.
    label holds a {datetime} placeholder; values are the CSV columns between district and frame."""
    try:
        try:
            ts = int(item_id.rsplit("-", 2)[1])
        except (IndexError, ValueError):
            ts = time.time()
        dt = datetime.fromtimestamp(ts)
        stamp = dt.strftime("%Y-%m-%d %H:%M:%S")
        day_dir = os.path.join(archive_dir, dt.strftime("%Y-%m-%d"))
        os.makedirs(day_dir, exist_ok=True)
        stem = os.path.join(day_dir, f"{safe_name(camid)}_{dt.strftime('%H%M%S')}_{item_id[-1]}")
        frame_out, crop_out = stem + ".jpg", stem + "_crop.jpg"
        banner = marked.copy()
        cv2.rectangle(banner, (0, 0), (banner.shape[1], banner_h), (0, 0, 0), -1)
        cv2.putText(banner, label.format(datetime=stamp), (4, text_y), cv2.FONT_HERSHEY_SIMPLEX, font_scale,
                    (255, 255, 255), 1, cv2.LINE_AA)
        write_jpeg(frame_out, banner, 92)
        write_jpeg(crop_out, crop, 92)
        index = os.path.join(archive_dir, csv_name)
        new_file = not os.path.exists(index)
        with open(index, "a", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow(header)
            w.writerow([item_id, stamp, camid, cam.get("title") or "", cam.get("district") or "", *values, frame_out, crop_out])
        return frame_out
    except OSError as e:
        get_logger(log_tag).warning(f"archive to {archive_dir} failed: {e}")
        return None


def ask_cloud_vision(vision, system_prompt, jpeg, context, models, timeout_ms, log_tag=None, caller=None):
    """Gemini (models tried in order on 503/504) or Claude; qwen is the patrol's own business.
    caller: module name the token usage is counted under (defaults to this module)."""
    if vision.provider == "gemini":
        from google.genai import types as genai_types
        for model in dict.fromkeys(models):
            try:
                resp = vision.client.models.generate_content(
                    model=model,
                    contents=[genai_types.Part.from_bytes(data=jpeg, mime_type="image/jpeg"), genai_types.Part(text=context)],
                    config=genai_types.GenerateContentConfig(system_instruction=system_prompt, temperature=0.1,
                                                             max_output_tokens=300, response_mime_type="application/json",
                                                             http_options=genai_types.HttpOptions(timeout=timeout_ms)),
                )
                local_llm.note_cloud(model, resp, caller or __name__)
                return (resp.text or "").strip()
            except Exception as e:  # noqa: BLE001
                # 503 = model overloaded right now: try the next model before giving up
                if any(k in str(e) for k in ("503", "UNAVAILABLE", "504", "DEADLINE")):
                    if log_tag:
                        get_logger(log_tag).info(f"{model} overloaded (503), trying {models[-1]}")
                    continue
                raise
        raise RuntimeError("503 Gemini overloaded on every model")
    response = vision.client.messages.create(
        model=os.environ.get("CLAUDE_VISION_MODEL", "claude-opus-5-5"),
        output_config={"effort": "low"},
        max_tokens=200,
        system=system_prompt,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                         "data": base64.standard_b64encode(jpeg).decode("ascii")}},
            {"type": "text", "text": context},
        ]}],
    )
    local_llm.note_cloud(response.model, response, caller or __name__)
    return "".join(b.text for b in response.content if b.type == "text").strip()
