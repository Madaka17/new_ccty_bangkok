"""
Road flooding in Bangkok, from the BMA Department of Drainage and Sewerage sensor network.

weather.bangkok.go.th/flood is a map of ~250 water-level sensors sitting on the roads and in the
road tunnels of Bangkok. Its own map calls /Flood/PageMap/GetData?id=0, which answers with the
whole network in one JSON document, so this module polls that every POLL_SECONDS, normalises it
and keeps the last good answer on disk (the site is occasionally unreachable).

What a station reports is the depth of water over the road surface in centimetres, every 5 minutes.
The thresholds are the ones the BMA map itself draws with:

        <= 5 cm   ปกติ (normal)          the sensor is wet but the road is passable
     5 - 10 cm    น้ำท่วมเล็กน้อย         slight flooding
        > 10 cm   น้ำท่วม                 flooding
     no reading   ขัดข้อง                 sensor offline / stale

Each poll is also kept in a short in-memory history per station, so the dashboard can say whether
the water is still rising, and an AI analyst (Gemini, else a Thai template) turns the numbers into
a readable situation report: severity, what is happening, which spots matter and what to do.

Served by /api/flood/*.

Coverage note: these are the 50 districts of Bangkok only. Nonthaburi, Pathum Thani, Samut Prakan
and the rest of the metropolitan area have no equivalent public sensor feed, so the map shows
nothing for them - not "no flooding".
"""
import json
import os
import re
import threading
import time
import urllib.request
from collections import deque
from datetime import datetime, timedelta, timezone

try:
    from google import genai
    from google.genai import types as genai_types
except Exception:  # pragma: no cover - the analyst falls back to a Thai template
    genai = None
    genai_types = None

from backend.core.instance import BASE_DIR  # project root
from backend.core.instance import DATA_DIR   # cache / db root: project root, or local/stage for the test server
CACHE_FILE = os.path.join(DATA_DIR, "cache", "flood_roads.json")
SOURCE_URL = "https://weather.bangkok.go.th/Flood/PageMap/GetData?id=0"
SOURCE_PAGE = "https://weather.bangkok.go.th/flood"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0.0.0 Safari/537.36")
BKK_TZ = timezone(timedelta(hours=7))

POLL_SECONDS = 300          # the sensors themselves report every 5 minutes
TIMEOUT = 25
STALE_MINUTES = 60          # a station whose last reading is older than this counts as offline
SLIGHT_CM = 5.0             # > this = slight flooding
FLOOD_CM = 10.0             # > this = flooding

AI_MODEL = os.getenv("FLOOD_AI_MODEL", os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"))
AI_INTERVAL = int(os.getenv("FLOOD_AI_SECONDS", "300"))   # seconds between Gemini rewrites
HISTORY_KEEP = 36            # readings per station (~3 hours at one per 5 minutes)
TREND_WINDOW_S = 1500        # compare against the reading ~25 minutes back
TREND_CM = 2.0               # change below this is "steady"

STATUS_TH = {"flood": "น้ำท่วม", "slight": "น้ำท่วมเล็กน้อย", "normal": "ปกติ", "offline": "เครื่องวัดขัดข้อง"}
TREND_TH = {"rising": "กำลังเพิ่มขึ้น", "falling": "กำลังลดลง", "steady": "ทรงตัว"}
STATUS_EN = {"flood": "flooding", "slight": "slight flooding", "normal": "normal", "offline": "offline"}
_DOTNET_DATE = re.compile(r"/Date\((-?\d+)\)/")


def _epoch(value):
    """BMA sends either '/Date(1790077800000)/' or '2026-09-22T18:45:00'. Both are Bangkok time."""
    if not value:
        return None
    m = _DOTNET_DATE.search(str(value))
    if m:
        return int(m.group(1)) // 1000
    try:
        return int(datetime.fromisoformat(str(value)).replace(tzinfo=BKK_TZ).timestamp())
    except ValueError:
        return None


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class FloodRoads:
    def __init__(self):
        self.lock = threading.Lock()
        self.items = []
        self.updated_at = None      # when we last fetched
        self.feed_time = None       # newest sensor reading in the feed
        self.error = None
        self._history = {}          # code -> deque[(ts, level_cm)] for the rising / falling arrow
        self.analysis = None        # last AI (or template) situation report
        self._ai_sig, self._ai_at, self._ai_client = None, 0.0, None
        self._load_cache()

    # ------------------------------------------------------------ persistence
    def _load_cache(self):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.items = d.get("items", [])
            self.updated_at = d.get("updated_at")
            self.feed_time = d.get("feed_time")
        except (OSError, ValueError):
            pass

    def _save_cache(self):
        try:
            os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump({"items": self.items, "updated_at": self.updated_at, "feed_time": self.feed_time},
                          f, ensure_ascii=False)
        except OSError as e:
            print(f"[Flood] cache save failed: {e}")

    # ------------------------------------------------------------ fetch
    def _fetch(self):
        req = urllib.request.Request(
            f"{SOURCE_URL}&_={int(time.time() * 1000)}",
            headers={"User-Agent": USER_AGENT, "Referer": SOURCE_PAGE, "Accept": "application/json, */*",
                     "Accept-Language": "th,en;q=0.8", "X-Requested-With": "XMLHttpRequest",
                     "Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8", "ignore"))

    @staticmethod
    def _status(row, level, ts, newest):
        """Sensor health first, then the BMA depth thresholds."""
        if row.get("status") == 0 or (row.get("chkStatustxt") or "").strip() == "ขัดข้อง":
            return "offline"
        if level is None:
            return "offline"
        if ts and newest and newest - ts > STALE_MINUTES * 60:
            return "offline"
        if level > FLOOD_CM:
            return "flood"
        if level > SLIGHT_CM:
            return "slight"
        return "normal"

    def _record(self, code, ts, level):
        if ts is None or level is None:
            return
        h = self._history.setdefault(code, deque(maxlen=HISTORY_KEEP))
        if h and h[-1][0] == ts:
            return      # the sensor has not reported since the last poll
        h.append((ts, level))

    def _trend(self, code, level, ts):
        """(label, delta_cm) against the reading ~TREND_WINDOW_S ago, or (None, None) when too new."""
        h = self._history.get(code)
        if not h or level is None or ts is None:
            return None, None
        past = None
        for t, v in h:
            if ts - t >= TREND_WINDOW_S:
                past = v
            else:
                break
        if past is None:
            if len(h) < 2:
                return None, None
            past = h[0][1]
        delta = round(level - past, 1)
        if delta >= TREND_CM:
            return "rising", delta
        if delta <= -TREND_CM:
            return "falling", delta
        return "steady", delta

    def refresh(self):
        data = self._fetch()
        rows = data.get("dtTbl") or []
        if not rows:
            raise RuntimeError("no stations in feed")
        stamps = [t for t in (_epoch(r.get("site_timestamp")) for r in rows) if t]
        newest = max(stamps) if stamps else None
        items, seen = [], set()
        for r in rows:
            code = r.get("flood_code")
            key = (code, r.get("tunnel_sub_name"))
            if not code or key in seen:
                continue     # the feed repeats a few stations across its tables
            seen.add(key)
            lat, lng = _num(r.get("latitude")), _num(r.get("longitude"))
            if not lat or not lng:
                continue
            level = _num(r.get("flood"))
            ts = _epoch(r.get("site_timestamp"))
            status = self._status(r, level, ts, newest)
            if status != "offline":
                self._record(code, ts, level)
            trend, delta = self._trend(code, level, ts)
            items.append({
                "id": r.get("flood_id"),
                "code": code,
                "name": r.get("flood_name") or r.get("flood_shortname") or code,
                "short_name": r.get("flood_shortname") or r.get("flood_name") or code,
                "name_en": r.get("flood_name_en"),
                "road": r.get("road_name"),
                "district": r.get("districtName"),
                "lat": lat, "lng": lng,
                "level_cm": level,
                "status": status,
                "status_th": STATUS_TH[status],
                "status_en": STATUS_EN[status],
                "ts": ts,
                "ts_th": r.get("site_timestatmpTH"),
                "started": r.get("flood_startTH"),
                "stopped": r.get("flood_stopTH"),
                "max_cm": _num(r.get("flood_max")),
                "max_time": r.get("flood_max_time"),
                # typesite 1 = road surface, 2 = road tunnel (which reports an inbound and an outbound side)
                "kind": "tunnel" if r.get("typesite") == 2 else "road",
                "side": r.get("tunnel_sub_name"),
                "trend": trend,
                "trend_th": TREND_TH.get(trend),
                "delta_cm": delta,
            })
        items.sort(key=lambda x: (-(x["level_cm"] or 0), x["name"]))
        with self.lock:
            self.items = items
            self.updated_at = int(time.time())
            self.feed_time = newest
            self.error = None
        self._save_cache()
        try:
            self._analyse()
        except Exception as e:  # noqa: BLE001 - the report must never break the poll
            print(f"[Flood] analysis failed: {e}")
        return len(items)

    def _loop(self):
        while True:
            try:
                self.refresh()
            except Exception as e:  # noqa: BLE001 - one bad poll must not kill the thread
                with self.lock:
                    self.error = str(e)[:200]
                print(f"[Flood] refresh failed: {e}")
            time.sleep(POLL_SECONDS)

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="flood-roads").start()

    # ------------------------------------------------------------ AI analysis
    def _client(self):
        if self._ai_client is not None:
            return self._ai_client
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if genai is None or not key:
            return None
        try:
            self._ai_client = genai.Client(api_key=key)
        except Exception:  # noqa: BLE001
            return None
        return self._ai_client

    def _facts(self):
        """The numbers the report is written from - no prose, no guessing."""
        with self.lock:
            items = list(self.items)
            feed_time = self.feed_time
        wet = [i for i in items if i["status"] in ("flood", "slight")]
        rising = [i for i in wet if i["trend"] == "rising"]
        counts = {k: sum(1 for i in items if i["status"] == k) for k in STATUS_TH}
        districts = {}
        for i in wet:
            d = districts.setdefault(i["district"] or "-", {"district": i["district"] or "-", "points": 0, "max_cm": 0.0})
            d["points"] += 1
            d["max_cm"] = max(d["max_cm"], i["level_cm"] or 0)
        return {
            "time": datetime.fromtimestamp(feed_time, BKK_TZ).strftime("%H:%M") if feed_time else None,
            "sensors_total": len(items),
            "counts": counts,
            "points": [{"where": i["short_name"], "road": i["road"], "district": i["district"],
                        "level_cm": i["level_cm"], "trend": i["trend"], "change_cm": i["delta_cm"],
                        "since": i["started"], "max_cm": i["max_cm"],
                        "tunnel": i["kind"] == "tunnel"} for i in wet[:25]],
            "rising_count": len(rising),
            "districts": sorted(districts.values(), key=lambda d: -d["max_cm"])[:12],
            "deepest_cm": wet[0]["level_cm"] if wet else 0,
        }

    def _template(self, f):
        """Deterministic Thai report, used when there is no Gemini key or the call fails."""
        c, pts = f["counts"], f["points"]
        wet = c.get("flood", 0) + c.get("slight", 0)
        if not wet:
            return {
                "severity": "normal",
                "headline": f"ไม่มีจุดน้ำท่วมขังในขณะนี้ จุดวัด {c.get('normal', 0)} จุดอ่านค่าไม่เกิน {int(SLIGHT_CM)} ซม.",
                "detail": ("เครื่องวัดขัดข้อง %d จุด ซึ่งไม่ได้แปลว่าบริเวณนั้นไม่ท่วม" % c["offline"]) if c.get("offline") else
                          "เซ็นเซอร์ทุกจุดส่งข้อมูลครบ",
                "hotspots": [], "advice": [], "outlook": "", "source": "template",
            }
        worst = pts[0]
        sev = "alert" if c.get("flood", 0) >= 5 or f["deepest_cm"] >= 20 else "watch"
        rising = f["rising_count"]
        return {
            "severity": sev,
            "headline": f"น้ำท่วมขัง {wet} จุด ลึกสุด {worst['level_cm']} ซม. ที่{worst['where']}"
                        + (f" เขต{worst['district']}" if worst.get("district") else ""),
            "detail": f"ท่วมเกิน {int(FLOOD_CM)} ซม. {c.get('flood', 0)} จุด, ท่วมเล็กน้อย {c.get('slight', 0)} จุด"
                      + (f" · ระดับยังเพิ่มขึ้น {rising} จุด" if rising else " · ระดับทรงตัวหรือลดลงทุกจุด"),
            "hotspots": [{"where": p["where"], "note": f"{p['level_cm']} ซม."
                          + (f" {TREND_TH.get(p['trend'])}" if p.get("trend") else "")} for p in pts[:5]],
            "advice": ["เลี่ยงจุดที่ระดับน้ำเกิน 20 ซม. รถเก๋งมีโอกาสเครื่องดับ",
                       "เผื่อเวลาเดินทางและตรวจเส้นทางก่อนออกจากบ้าน"],
            "outlook": "", "source": "template",
        }

    def _analyse(self, force=False):
        """Write the situation report. One Gemini call at most every AI_INTERVAL, and only when the
        picture actually changed; otherwise the previous report stands."""
        f = self._facts()
        sig = json.dumps([f["counts"], [(p["where"], p["level_cm"], p["trend"]) for p in f["points"]]],
                         ensure_ascii=False)
        now = time.time()
        base = self._template(f)
        if not force and sig == self._ai_sig and self.analysis and now - self._ai_at < AI_INTERVAL:
            return self.analysis
        client = self._client()
        if client is None:
            with self.lock:
                self.analysis = {**base, "facts": f, "updated_at": int(now)}
            self._ai_sig, self._ai_at = sig, now
            return self.analysis
        prompt = (
            "คุณคือนักวิเคราะห์สถานการณ์น้ำท่วมขังของศูนย์ควบคุมจราจรกรุงเทพมหานคร "
            "ข้างล่างคือค่าที่อ่านได้สดจากเซ็นเซอร์วัดระดับน้ำบนผิวถนนของสำนักการระบายน้ำ กทม. "
            f"(level_cm = ความลึกของน้ำบนผิวถนนหน่วยเซนติเมตร, เกิน {int(FLOOD_CM)} ซม. ถือว่าน้ำท่วม, "
            f"{int(SLIGHT_CM)}-{int(FLOOD_CM)} ซม. ท่วมเล็กน้อย, trend = แนวโน้มเทียบ 25 นาทีก่อน)\n"
            "เขียนบทวิเคราะห์ภาษาไทยจากตัวเลขที่ให้เท่านั้น ห้ามแต่งชื่อถนน จุด หรือตัวเลขที่ไม่มีในข้อมูล "
            "ห้ามพยากรณ์ฝนหรืออ้างข้อมูลที่ไม่ได้ให้มา\n"
            "ตอบเป็น JSON object เท่านั้น:\n"
            '{"severity":"normal|watch|alert",'
            '"headline":"<1 ประโยค สรุปภาพรวมตอนนี้ ไม่เกิน 30 คำ>",'
            '"detail":"<1-2 ประโยค อธิบายว่ากระจุกอยู่โซนไหน ระดับกำลังขึ้นหรือลง>",'
            '"hotspots":[{"where":"<ชื่อจุดตามข้อมูล>","note":"<เหตุผลสั้น ๆ ว่าทำไมจุดนี้ต้องจับตา ไม่เกิน 15 คำ>"}],'
            '"advice":["<คำแนะนำผู้ใช้รถใช้ถนน สั้น เจาะจงจุดจริง 2-4 ข้อ>"],'
            '"outlook":"<1 ประโยค แนวโน้มระยะสั้นจาก trend เท่านั้น>"}\n'
            "severity: normal = ไม่มีจุดท่วม, watch = มีจุดท่วมแต่ไม่ลึกและไม่เพิ่ม, alert = ลึกเกิน 20 ซม. "
            "หรือมีหลายจุดที่ระดับกำลังเพิ่ม · hotspots ไม่เกิน 5 จุด เรียงตามความสำคัญ\n"
            "ถ้า counts.offline มากกว่า 0 ให้ระบุใน detail ว่ามีเครื่องวัดกี่จุดที่ไม่ส่งค่า และย้ำว่าไม่ได้แปลว่าบริเวณนั้นไม่ท่วม\n"
            "ถ้าไม่มีจุดท่วมเลย ให้ hotspots เป็น [] และ advice เป็น [] ห้ามเขียนคำแนะนำทั่วไปที่ไม่เกี่ยวกับน้ำท่วม "
            "ห้ามอ้างช่วงเวลา สภาพอากาศ หรือฝน เพราะไม่มีในข้อมูล\n\n"
            + json.dumps(f, ensure_ascii=False)
        )
        out = dict(base)
        try:
            resp = client.models.generate_content(
                model=AI_MODEL, contents=prompt,
                config=genai_types.GenerateContentConfig(temperature=0.2, max_output_tokens=1200,
                                                         response_mime_type="application/json"))
            d = json.loads(resp.text or "{}")
            if isinstance(d, dict) and d.get("headline"):
                out = {
                    "severity": d.get("severity") if d.get("severity") in ("normal", "watch", "alert") else base["severity"],
                    "headline": str(d["headline"]).strip(),
                    "detail": str(d.get("detail") or "").strip(),
                    "hotspots": [{"where": str(h.get("where") or "").strip(), "note": str(h.get("note") or "").strip()}
                                 for h in (d.get("hotspots") or []) if isinstance(h, dict) and h.get("where")][:5],
                    "advice": [str(a).strip() for a in (d.get("advice") or []) if str(a).strip()][:4],
                    "outlook": str(d.get("outlook") or "").strip(),
                    "source": AI_MODEL,
                }
        except Exception as e:  # noqa: BLE001
            print(f"[Flood] Gemini analysis failed, using template: {str(e)[:140]}")
        with self.lock:
            self.analysis = {**out, "facts": f, "updated_at": int(now)}
        self._ai_sig, self._ai_at = sig, now
        return self.analysis

    def report(self):
        with self.lock:
            a = self.analysis
        if a:
            return {**a, "feed_time": self.feed_time}
        try:
            return {**self._analyse(force=True), "feed_time": self.feed_time}
        except Exception as e:  # noqa: BLE001
            return {"severity": "normal", "headline": "ยังไม่มีข้อมูลพอจะวิเคราะห์", "detail": str(e)[:160],
                    "hotspots": [], "advice": [], "outlook": "", "source": "none", "feed_time": self.feed_time}

    # ------------------------------------------------------------ api
    def status(self, min_cm=None):
        """Everything the flood layer needs in one call: counts, the wet stations, the district roll-up."""
        with self.lock:
            items = list(self.items)
            updated, feed_time, error = self.updated_at, self.feed_time, self.error
        counts = {k: 0 for k in STATUS_TH}
        districts = {}
        for it in items:
            counts[it["status"]] = counts.get(it["status"], 0) + 1
            if it["status"] in ("flood", "slight"):
                d = districts.setdefault(it["district"] or "-", {"district": it["district"] or "-", "flood": 0,
                                                                 "slight": 0, "max_cm": 0.0})
                d[it["status"]] += 1
                d["max_cm"] = max(d["max_cm"], it["level_cm"] or 0)
        wet = [it for it in items if it["status"] in ("flood", "slight")]
        if min_cm is not None:
            wet = [it for it in wet if (it["level_cm"] or 0) >= min_cm]
        return {
            "updated_at": updated, "feed_time": feed_time, "poll_seconds": POLL_SECONDS, "error": error,
            "source": SOURCE_PAGE, "source_name": "สำนักการระบายน้ำ กรุงเทพมหานคร",
            "thresholds": {"slight_cm": SLIGHT_CM, "flood_cm": FLOOD_CM},
            "total": len(items), "counts": counts,
            "wet": wet,
            "districts": sorted(districts.values(), key=lambda d: (-d["flood"], -d["max_cm"])),
        }

    def stations(self, status=None, district=None, kind=None, limit=400):
        with self.lock:
            items = list(self.items)
        if status:
            items = [i for i in items if i["status"] == status]
        if district:
            items = [i for i in items if (i["district"] or "") == district]
        if kind:
            items = [i for i in items if i["kind"] == kind]
        return {"updated_at": self.updated_at, "feed_time": self.feed_time, "total": len(items),
                "items": items[:limit]}

    def roads(self, limit=60):
        """One row per road: the worst station on it, so the page can list 'which roads are flooded'."""
        with self.lock:
            items = list(self.items)
        by_road = {}
        for it in items:
            if it["status"] not in ("flood", "slight"):
                continue
            name = it["road"] or it["name"]
            r = by_road.get(name)
            if r is None or (it["level_cm"] or 0) > (r["level_cm"] or 0):
                by_road[name] = {"road": name, "district": it["district"], "level_cm": it["level_cm"],
                                 "status": it["status"], "status_th": it["status_th"], "at": it["short_name"],
                                 "lat": it["lat"], "lng": it["lng"], "ts": it["ts"], "ts_th": it["ts_th"],
                                 "started": it["started"], "max_cm": it["max_cm"], "trend": it.get("trend"),
                                 "trend_th": it.get("trend_th"), "delta_cm": it.get("delta_cm"), "points": 0}
            by_road[name]["points"] += 1
        out = sorted(by_road.values(), key=lambda r: -(r["level_cm"] or 0))
        return {"updated_at": self.updated_at, "feed_time": self.feed_time, "total": len(out), "items": out[:limit]}


flood_roads = FloodRoads()
