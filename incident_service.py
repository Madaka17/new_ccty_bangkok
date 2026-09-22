"""Accident / incident detection and alerts.

Two sources:
  1. Camera AI: a vehicle stopped for a long time while traffic around it flows (tracker.anomaly())
     is a candidate. A snapshot is sent to Claude vision to confirm before anything is shown.
  2. Longdo Traffic public event feed (type 3 = accident), for reported accidents city-wide.
"""
import base64
import json
import os
import threading
import time
import urllib.request

import cv2

try:
    import anthropic
except ImportError:  # chat_service already tolerates a missing SDK
    anthropic = None
try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    genai = None

# Vision provider order mirrors chat_service: Gemini (GEMINI_API_KEY) first, then Claude
CLAUDE_MODEL = "claude-opus-5"
GEMINI_MODEL = os.environ.get("GEMINI_VISION_MODEL", "gemini-3.6-flash")
LONGDO_FEED = "https://event.longdo.com/feed/json"
LONGDO_ACCIDENT_TYPE = "3"
LONGDO_BREAKDOWN_TYPE = "1"
# Bangkok and vicinity
BBOX = (13.3, 100.1, 14.3, 101.1)  # min lat, min lon, max lat, max lon


def _feed_ts(text):
    """Longdo 'YYYY-MM-DD HH:MM:SS' (local time) -> epoch seconds, or None."""
    try:
        return int(time.mktime(time.strptime(text, '%Y-%m-%d %H:%M:%S')))
    except (TypeError, ValueError):
        return None

SYSTEM_PROMPT = (
    "You review a single frame from a Bangkok traffic CCTV camera. Our tracker flagged either a vehicle that has been "
    "standing still while other traffic keeps moving, or two vehicles that stopped abruptly while touching each other. "
    "Decide whether the frame shows a road incident.\n"
    "Answer ONLY with a JSON object: {\"kind\": \"accident\"|\"breakdown\"|\"none\", \"confidence\": 0..1, "
    "\"description_th\": \"<one short Thai sentence>\"}.\n"
    "accident = collision, overturned vehicle, debris from a crash, injured people, emergency vehicles at a crash.\n"
    "breakdown = a stalled or broken-down vehicle blocking or beside a lane, hazard lights, people pushing or fixing it.\n"
    "none = parked legally, bus stop, waiting to turn, queue at a light, a taxi picking up, or you are not sure.\n"
    "Be conservative: say none unless the evidence is visible in the image."
)


class IncidentManager:
    CHECK_COOLDOWN = 300.0        # seconds between vision checks on the same camera
    MAX_CHECKS_PER_HOUR = 20      # global cap on vision calls
    CLEAR_AFTER_QUIET = 180.0     # camera incident clears when the anomaly has been gone this long
    MAX_ACTIVE = 45 * 60          # ...or after this long no matter what
    FEED_INTERVAL = 180.0

    def __init__(self, vehicle_log, cameras_by_id, snapshot_dir):
        self.vehicle_log = vehicle_log
        self.cameras_by_id = cameras_by_id      # () -> {camid: cam}
        self.snapshot_dir = snapshot_dir
        os.makedirs(snapshot_dir, exist_ok=True)
        self.lock = threading.Lock()
        # camid -> {'last_check': ts, 'last_anomaly': ts, 'checking': bool}
        self._state = {}
        self._checks = []                       # wall times of vision calls (rolling hour)
        self.camera_incidents = {}              # camid -> active incident dict
        self.longdo = []
        self.longdo_updated = 0
        self.longdo_recent = []                 # Longdo events that ended within the last 24 h
        self.provider, self.client = self._client()
        print(f"[Incident] vision provider: {self.provider or 'none (set GEMINI_API_KEY or ANTHROPIC_API_KEY)'}")
        for inc in vehicle_log.active_incidents():
            self.camera_incidents[inc['camid']] = inc
        threading.Thread(target=self._feed_loop, daemon=True).start()

    @staticmethod
    def _client():
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if genai is not None and key:
            try:
                return 'gemini', genai.Client(api_key=key)
            except Exception:
                pass
        if anthropic is not None and (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
                                      or os.path.exists(os.path.join(os.path.expanduser("~"), ".config", "anthropic"))):
            try:
                return 'claude', anthropic.Anthropic(timeout=60.0, max_retries=1)
            except Exception:
                pass
        return None, None

    # ---------------------------------------------------------------- camera path
    def observe(self, camid, title, tracker, frame):
        """Called on every analysed frame of a continuously watched camera."""
        cand = tracker.anomaly()
        now = time.time()
        st = self._state.setdefault(camid, {'last_check': 0.0, 'last_anomaly': 0.0, 'checking': False})
        active = self.camera_incidents.get(camid)

        if cand:
            st['last_anomaly'] = now
            if active:
                active['last_seen'] = int(now)
                return
            if st['checking'] or now - st['last_check'] < self.CHECK_COOLDOWN or not self._budget_ok(now):
                return
            st['checking'] = True
            st['last_check'] = now
            # Snapshot with the flagged vehicle outlined in red (the prompt refers to it)
            img = frame.copy()
            x1, y1, x2, y2 = cand['box']
            cv2.rectangle(img, (x1, y1), (x2, y2), (60, 60, 230), 3)
            if cand.get('box2'):
                bx1, by1, bx2, by2 = cand['box2']
                cv2.rectangle(img, (bx1, by1), (bx2, by2), (60, 60, 230), 3)
            jpeg = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 80])[1].tobytes()
            threading.Thread(target=self._confirm, args=(camid, title, cand, jpeg, st), daemon=True).start()
        elif active:
            # Anomaly gone for a while, or incident too old: clear it
            if now - st['last_anomaly'] > self.CLEAR_AFTER_QUIET or now - active['ts'] > self.MAX_ACTIVE:
                self._clear(camid)

    def _budget_ok(self, now):
        self._checks = [t for t in self._checks if now - t < 3600]
        return len(self._checks) < self.MAX_CHECKS_PER_HOUR and self.client is not None

    def _confirm(self, camid, title, cand, jpeg, st):
        try:
            self._checks.append(time.time())
            verdict = self._ask_vision(jpeg, title, cand)
            print(f"[Incident] {title}: {cand.get('kind', 'stopped')} {cand['stopped_s']}s, "
                  f"persons {cand['persons_near']} -> {verdict}")
            if verdict and verdict.get('kind') in ('accident', 'breakdown') and float(verdict.get('confidence', 0)) >= 0.6:
                self._open(camid, title, cand, jpeg, verdict)
        except Exception as e:
            print(f"[Incident] check failed for {title}: {e}")
        finally:
            st['checking'] = False

    def _ask_vision(self, jpeg, title, cand):
        if cand.get('kind') == 'collision':
            what = (f"Tracker: two vehicles stopped abruptly in contact with each other {cand['stopped_s']} s ago "
                    f"(possible collision). Both are inside red boxes.")
        else:
            what = f"Tracker: vehicle stopped for {cand['stopped_s']} s. The stopped vehicle is inside the red box."
        context = (f"Camera: {title}. {what} {cand['persons_near']} people near it, "
                   f"{cand['moving_pct']}% of other vehicles moving, {cand['total']} vehicles visible.")
        if self.provider == 'gemini':
            resp = self.client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[genai_types.Part.from_bytes(data=jpeg, mime_type='image/jpeg'), genai_types.Part(text=context)],
                config=genai_types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT, temperature=0.1,
                                                         max_output_tokens=1500, response_mime_type='application/json'),
            )
            text = (resp.text or '').strip()
        else:
            text = self._ask_claude(jpeg, context)
        start, end = text.find('{'), text.rfind('}')
        return json.loads(text[start:end + 1]) if start >= 0 and end > start else None

    def _ask_claude(self, jpeg, context):
        response = self.client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=300,
            system=SYSTEM_PROMPT,
            output_config={"effort": "low"},
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                 "data": base64.standard_b64encode(jpeg).decode("ascii")}},
                    {"type": "text", "text": context},
                ],
            }],
        )
        return "".join(b.text for b in response.content if b.type == "text").strip()

    def _open(self, camid, title, cand, jpeg, verdict):
        cam = self.cameras_by_id().get(camid, {})
        now = int(time.time())
        inc = {
            'id': f"{camid}-{now}", 'source': 'camera', 'camid': camid, 'title': title,
            'kind': verdict['kind'], 'confidence': round(float(verdict.get('confidence', 0)), 2),
            'description': verdict.get('description_th', ''), 'ts': now, 'last_seen': now,
            'latitude': cam.get('latitude'), 'longitude': cam.get('longitude'),
            'stopped_s': cand['stopped_s'], 'persons_near': cand['persons_near'],
            'image': f"/api/incidents/{camid}-{now}/image",
        }
        with open(os.path.join(self.snapshot_dir, f"{inc['id']}.jpg"), 'wb') as f:
            f.write(jpeg)
        with self.lock:
            self.camera_incidents[camid] = inc
        self.vehicle_log.add_incident(inc)
        print(f"[Incident] ALERT {inc['kind']} at {title}: {inc['description']}")

    def _clear(self, camid):
        with self.lock:
            inc = self.camera_incidents.pop(camid, None)
        if inc:
            self.vehicle_log.clear_incident(inc['id'])
            print(f"[Incident] cleared at {inc['title']}")

    def snapshot_path(self, incident_id):
        p = os.path.join(self.snapshot_dir, f"{incident_id}.jpg")
        return p if os.path.exists(p) else None

    # ---------------------------------------------------------------- Longdo feed
    def _feed_loop(self):
        while True:
            try:
                self._refresh_feed()
            except Exception as e:
                print(f"[Incident] Longdo feed: {e}")
            time.sleep(self.FEED_INTERVAL)

    def _refresh_feed(self):
        req = urllib.request.Request(LONGDO_FEED, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            items = json.loads(resp.read().decode('utf-8'))
        now = time.strftime('%Y-%m-%d %H:%M:%S')
        out, recent = [], []
        for e in items:
            etype = str(e.get('type') or '')
            title = (e.get('title') or '').strip()
            desc = (e.get('description') or '').strip()
            icon = str(e.get('icon') or '').lower()

            # Identify vehicle breakdown (type 1, carbreakdown icon, or keywords)
            if etype == LONGDO_BREAKDOWN_TYPE or 'carbreakdown' in icon or 'รถเสีย' in title or 'จอดเสีย' in title or 'รถเสีย' in desc or 'จอดเสีย' in desc:
                kind = 'breakdown'
                default_title = 'รถเสีย / กีดขวาง'
            elif etype == LONGDO_ACCIDENT_TYPE or 'accident' in icon or 'อุบัติเหตุ' in title or 'ชนกัน' in title or 'รถชน' in title:
                kind = 'accident'
                default_title = 'อุบัติเหตุ'
            else:
                continue

            try:
                lat, lon = float(e['latitude']), float(e['longitude'])
            except (KeyError, TypeError, ValueError):
                continue
            if not (BBOX[0] <= lat <= BBOX[2] and BBOX[1] <= lon <= BBOX[3]):
                continue
            item = {
                'id': f"longdo-{e.get('eid')}", 'source': 'longdo', 'kind': kind,
                'title': title or default_title, 'description': desc,
                'latitude': lat, 'longitude': lon, 'start': e.get('start'), 'stop': e.get('stop'),
                'contributor': e.get('contributor', ''), 'severity': e.get('severity', ''),
            }
            if e.get('stop') and e['stop'] < now:
                # Ended already: keep it for the "resolved in the last 24 h" list
                ts, cleared = _feed_ts(e.get('start')), _feed_ts(e.get('stop'))
                if cleared and time.time() - cleared <= 24 * 3600:
                    recent.append({**item, 'ts': ts or cleared, 'cleared_ts': cleared})
                continue
            out.append(item)
        with self.lock:
            self.longdo = out
            self.longdo_recent = recent
            self.longdo_updated = int(time.time())

    def recent_longdo(self, hours=24):
        """Longdo events that ended within the last `hours`, shaped like vehicle_log.recent_incidents()."""
        since = time.time() - hours * 3600
        with self.lock:
            return [i for i in self.longdo_recent if i['cleared_ts'] >= since]

    # ---------------------------------------------------------------- API
    def status(self):
        with self.lock:
            return {'updated': int(time.time()), 'longdo_updated': self.longdo_updated,
                    'vision_provider': self.provider,
                    'camera': sorted(self.camera_incidents.values(), key=lambda i: -i['ts']),
                    'longdo': list(self.longdo)}
