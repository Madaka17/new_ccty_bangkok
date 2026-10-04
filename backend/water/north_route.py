"""
The เส้นทางน้ำเหนือ tab: where the water from the North goes, which provinces on the way should watch out, how
the water is trending now and over the next 7 days, and the river course for the 3D map.

Built every REFRESH_SECONDS from north_flow's outlook (RID gauges on the Ping, Wang, Yom, Nan, Sakae Krang,
Pa Sak and Chao Phraya, with the routed hourly outlook for up to 4 days), HII's 7-day level forecast at
Nonthaburi, and national_forecast (7-day rain per province, the large dams' projected storage):

    days    each gauge's discharge for today and the next DAYS days as a share of its bank-full discharge.
            A day the routed outlook covers takes its highest hour ("routed"). After that, and at gauges with no
            routed outlook, the trend carries on: the last daily change, halved each day, plus a little for the
            rain forecast around the gauge ("trend", shown as แนวโน้ม: less sure)
    provinces  the gauges grouped by province, worst day first, with the stretch of river they sit on; Nonthaburi
            -Bangkok from HII's level forecast against the bank
    paths   for each pair of points the water runs between (north_flow.FLOW_EDGES), the river centre line from
            config/north_rivers.json (local/pipeline/fetch_north_rivers.py) joined into one network, so the map
            draws the water along the river and not as a straight line

The Qwen model behind LOCAL_LLM_* (local_llm.default) then writes the plain-Thai read: a headline, the trend
now, the next 7 days, a line and advice per province, and what to do. It runs again only when the picture
changed or the report is older than AI_MAX_AGE; without it the page shows the computed figures.

Served by /api/water/north/route.
"""
import heapq
import json
import math
import os
import threading
import time
from datetime import datetime, timedelta

from backend.core import local_llm
from backend.core.instance import BASE_DIR
from backend.water import north_flow, water_service as ws

REFRESH_SECONDS = int(os.getenv("NORTH_ROUTE_SECONDS", "1800"))
AI_MAX_AGE = int(os.getenv("NORTH_ROUTE_AI_MAX_AGE", "10800"))
DAYS = 7
DAY = 86400
TREND_DECAY = 0.5        # the daily change carried on into a trend day is halved each day
RAIN_GAIN = 1 / 400      # 3-day rain (mm) around a gauge adds this share of its flow, at most RAIN_MAX
RAIN_MAX = 0.25
SNAP_KM = 6              # a point further than this from every river line is joined by a straight line
BRIDGE_KM = 6            # river pieces that do not touch are joined when their ends are this close
RIVERS_FILE = os.path.join(BASE_DIR, "config", "north_rivers.json")
LEVELS = ("critical", "flood", "watch", "normal")
LABELS = {"critical": "ล้นตลิ่ง", "flood": "ใกล้ล้นตลิ่ง", "watch": "น้ำมาก", "normal": "ปกติ"}
# Where each gauge sits on the way down, for the "which areas" list
AREA = {
    "P.1": "ต้นแม่น้ำปิง", "W.4A": "แม่น้ำวัง", "P.7A": "แม่น้ำปิงตอนล่าง", "P.17": "แม่น้ำปิงตอนล่าง",
    "Y.4": "แม่น้ำยม", "Y.16": "แม่น้ำยม", "N.60": "แม่น้ำน่าน", "N.5A": "แม่น้ำน่าน", "N.7A": "แม่น้ำน่านตอนล่าง",
    "N.67": "แม่น้ำน่านตอนล่าง", "C.2": "ปากน้ำโพ (ปิงรวมน่าน เป็นเจ้าพระยา)", "Ct.19": "แม่น้ำสะแกกรัง",
    "C.13": "เขื่อนเจ้าพระยา", "C.3": "เจ้าพระยาตอนกลาง", "C.7A": "เจ้าพระยาตอนกลาง", "C.35": "เจ้าพระยาตอนล่าง",
    "S.26": "แม่น้ำป่าสัก",
}
BKK_PROVINCE = "นนทบุรี-กรุงเทพฯ"

PROMPT = """คุณคือนักวิเคราะห์น้ำเหนือ อ่านข้อมูลน้ำที่ไหลจากภาคเหนือลงภาคกลางที่แนบมา แล้วเขียน JSON ตาม schema:
- headline: 1 ประโยคสั้น น้ำเหนือตอนนี้น่าห่วงแค่ไหน
- now: แนวโน้มน้ำตอนนี้ 2-3 ประโยค น้ำกำลังขึ้นหรือลด ที่ไหนมาก
- next7: 7 วันข้างหน้า 2-4 ประโยค น้ำก้อนใหญ่จะไปถึงไหนเมื่อไร (วันที่ 5-7 เป็นแนวโน้ม ให้บอกว่าไม่แน่นอน)
- provinces: ทุกจังหวัดในข้อมูลที่ไม่ปกติในวันใดวันหนึ่ง outlook: 1-2 ประโยค ว่าน้ำจะเป็นอย่างไรใน 7 วัน advice: 1 ประโยค
- actions: สิ่งที่ประชาชนริมแม่น้ำควรทำ 2-4 ข้อ
ข้อมูล: provinces[].days = % ของความจุลำน้ำ วันนี้และอีก 7 วัน (100 ขึ้นไป = ล้นตลิ่ง, 85 = ใกล้ล้น, 70 = น้ำมาก),
trend_from = วันที่เริ่มเป็นแนวโน้ม, dams = เขื่อนต้นน้ำ (% ความจุ, ปล่อยน้ำ ลบ.ม./วิ, เต็มใน X วัน), rain7 = ฝนพยากรณ์ 7 วัน (มม.)
หลักการ
- ใช้ชื่อสถานที่ และตัวเลขจากข้อมูลที่แนบมาเท่านั้น ห้ามแต่งตัวเลขหรือสถานที่
- ภาษาไทยง่าย ๆ ประโยคสั้น ข้อความล้วน ไม่ใช้ Markdown ไม่ใส่รหัสสถานี ไม่ใส่ชื่อฟิลด์ภาษาอังกฤษ"""

SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"}, "now": {"type": "string"}, "next7": {"type": "string"},
        "provinces": {"type": "array", "items": {
            "type": "object", "properties": {"province": {"type": "string"}, "outlook": {"type": "string"}, "advice": {"type": "string"}},
            "required": ["province", "outlook", "advice"], "additionalProperties": False}},
        "actions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["headline", "now", "next7", "provinces", "actions"], "additionalProperties": False,
}


def level_of(pct):
    if pct is None:
        return "normal"
    return "critical" if pct >= 100 else "flood" if pct >= 85 else "watch" if pct >= 70 else "normal"


def gauge_days(s, now, rain=None):
    """[{day, q, pct, level, kind}] for day 0 (now) .. DAYS. rain: [mm x DAYS] around the gauge."""
    q0, qmax = s.get("q"), s.get("qmax")
    if q0 is None:
        return []
    by_day = {}
    for p in s.get("forecast") or []:
        d = math.ceil((p["t"] - now) / DAY)
        if 1 <= d <= DAYS:
            by_day[d] = max(by_day.get(d, 0), p["q"])
    # a day counts as routed only if the outlook covers all of it
    last_t = max((p["t"] for p in s.get("forecast") or []), default=now)
    routed = {d for d in by_day if now + d * DAY <= last_t + 3600}
    rain = rain or [0.0] * DAYS
    out = [{"day": 0, "q": round(q0), "kind": "now"}]
    # the trend runs on the flow without rain; each day's rain is added on top, not carried into the next day
    prev2, prev = q0 - (s.get("change_24h") or 0), q0
    for d in range(1, DAYS + 1):
        if d in routed:
            base = q = by_day[d]
            kind = "routed"
        else:
            base = max(0.0, prev + (prev - prev2) * TREND_DECAY)
            q = base * (1 + min(RAIN_MAX, sum(rain[max(0, d - 3):d]) * RAIN_GAIN))
            kind = "trend"
        prev2, prev = prev, base
        out.append({"day": d, "q": round(q), "kind": kind})
    for x in out:
        x["pct"] = round(100 * x["q"] / qmax, 1) if qmax else None
        x["level"] = level_of(x["pct"])
    return out


def bangkok_days(now):
    """Nonthaburi-Bangkok from HII's level forecast at สะพานนวลฉวี: [{day, msl, below_bank, level}]."""
    try:
        f = ws.get_forecast(north_flow.BANGKOK_STATION)
    except Exception as e:  # noqa: BLE001 - the province list stands without it
        print(f"[NorthRoute] HII forecast: {e}")
        return [], None
    bank = (f.get("levels") or {}).get("bank")
    if f.get("source") != "hii" or bank is None:
        return [], None
    by_day = {}
    for p in f.get("official") or []:
        d = max(0, math.ceil((p["t"] - now) / DAY))
        if d <= DAYS:
            by_day[d] = max(by_day.get(d, -99), p["v"])
    if (f.get("latest") or {}).get("v") is not None:
        by_day[0] = f["latest"]["v"]
    if not by_day:
        return [], bank
    for d in range(DAYS + 1):   # a day the forecast misses keeps the day before (the table has a column per day)
        if d not in by_day:
            by_day[d] = by_day.get(d - 1, by_day[min(by_day)])
    out = []
    for d in sorted(by_day):
        below = round(bank - by_day[d], 2)
        lv = "critical" if below <= 0 else "flood" if below <= 0.3 else "watch" if below <= 0.8 else "normal"
        out.append({"day": d, "msl": round(by_day[d], 2), "below_bank": below, "level": lv, "kind": "hii"})
    return out, bank


# ---------------------------------------------------------------- river network for the map
def _km(a, b):
    """a, b: (lat, lng)."""
    kx = 111.32 * math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot((a[1] - b[1]) * kx, (a[0] - b[0]) * 110.54)


class RiverNet:
    """The river lines as one graph: shared points join pieces; pieces whose ends are within BRIDGE_KM of
    another piece are joined to its nearest point."""

    def __init__(self, path=RIVERS_FILE):
        with open(path, encoding="utf-8") as f:
            lines = [tuple(map(tuple, x["line"])) for x in json.load(f)["lines"]]
        self.adj = {}
        for line in lines:
            for a, b in zip(line, line[1:]):
                self._link(a, b)
        self.points = list(self.adj)
        ends = [p for line in lines for p in (line[0], line[-1])]
        for e in ends:   # join loose ends to the nearest point on another piece
            comp = self._component(e)
            best = min((p for p in self.points if p not in comp), key=lambda p: _km(e, p), default=None)
            if best is not None and _km(e, best) <= BRIDGE_KM:
                self._link(e, best)

    def _link(self, a, b):
        w = _km(a, b)
        self.adj.setdefault(a, {})[b] = w
        self.adj.setdefault(b, {})[a] = w

    def _component(self, start, cap=400):
        """Points reachable from start within `cap` steps: enough to tell 'same piece' near an end."""
        seen, todo = {start}, [start]
        while todo and len(seen) < cap:
            for n in self.adj[todo.pop()]:
                if n not in seen:
                    seen.add(n)
                    todo.append(n)
        return seen

    def snap(self, p):
        best = min(self.points, key=lambda q: _km(p, q))
        return best if _km(p, best) <= SNAP_KM else None

    def path(self, a, b):
        """[(lat, lng)] along the rivers from the point nearest a to the point nearest b, or None."""
        s, t = self.snap(a), self.snap(b)
        if s is None or t is None:
            return None
        dist, prev, heap = {s: 0.0}, {}, [(0.0, s)]
        while heap:
            d, u = heapq.heappop(heap)
            if u == t:
                break
            if d > dist.get(u, 1e18):
                continue
            for v, w in self.adj[u].items():
                nd = d + w
                if nd < dist.get(v, 1e18):
                    dist[v], prev[v] = nd, u
                    heapq.heappush(heap, (nd, v))
        if t not in dist:
            return None
        out = [t]
        while out[-1] != s:
            out.append(prev[out[-1]])
        return [a] + out[::-1] + [b]


class NorthRoute:
    def __init__(self, data_dir, national_forecast):
        self.path = os.path.join(data_dir, "north_route.json")
        self.national = national_forecast
        self.lock = threading.Lock()
        self.data, self.ai, self.ai_sig, self.ai_error, self.ai_running, self.error = {}, {}, None, None, False, None
        self.paths, self.paths_key = {}, None
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            self.data, self.ai, self.ai_sig = d.get("data") or {}, d.get("ai") or {}, d.get("ai_sig")
        except (OSError, ValueError):
            pass

    def _paths(self, nodes, edges):
        """{"from>to": [[lng, lat], ...]} along the rivers; worked out once per set of points."""
        key = json.dumps(sorted((k, round(v[0], 3), round(v[1], 3)) for k, v in nodes.items()))
        if key == self.paths_key:
            return self.paths
        try:
            net = RiverNet()
        except (OSError, ValueError, KeyError) as e:
            print(f"[NorthRoute] river lines: {e}")
            return {}
        out = {}
        for e in edges:
            a, b = nodes.get(e["from"]), nodes.get(e["to"])
            if not a or not b:
                continue
            line = net.path(a, b)
            if line and len(line) > 2:
                out[f"{e['from']}>{e['to']}"] = [[round(p[1], 5), round(p[0], 5)] for p in line]
        self.paths, self.paths_key = out, key
        return out

    def refresh(self):
        o = north_flow.get_outlook()
        now = o["data_time"]
        nat = self.national.status() if self.national else {}
        rain = {p["province"]: p.get("rain7") for p in nat.get("provinces") or []}
        nat_dams = {d["name"]: d for d in nat.get("dams") or []}
        gauges = []
        for s in o["stations"]:
            days = gauge_days(s, now, rain.get(s["province"])) if s.get("status") != "offline" else []
            gauges.append({"code": s["code"], "name": s["name"], "province": s["province"], "river": s["river"],
                           "area": AREA.get(s["code"], ""), "lat": s.get("lat"), "lng": s.get("lng"),
                           "qmax": s.get("qmax"), "status": s["status"], "days": days})
        provinces = {}
        for g in gauges:
            if not g["days"]:
                continue
            p = provinces.setdefault(g["province"], {"province": g["province"], "areas": [], "gauges": [], "days": None})
            if g["area"] and g["area"] not in p["areas"]:
                p["areas"].append(g["area"])
            p["gauges"].append(g["code"])
            if p["days"] is None:
                p["days"] = [dict(x, code=g["code"]) for x in g["days"]]
            else:
                for i, x in enumerate(g["days"]):
                    if i < len(p["days"]) and (x["pct"] or 0) > (p["days"][i]["pct"] or 0):
                        p["days"][i] = dict(x, code=g["code"])
        bkk, bank = bangkok_days(now)
        if bkk:
            provinces[BKK_PROVINCE] = {"province": BKK_PROVINCE, "areas": ["เจ้าพระยาตอนล่าง (สะพานนวลฉวี)"],
                                       "gauges": [], "days": bkk, "bank": bank}
        order = [s["province"] for s in o["stations"]] + [BKK_PROVINCE]
        rows = []
        for p in provinces.values():
            worst = max(p["days"], key=lambda x: (LEVELS[::-1].index(x["level"]), x.get("pct") or -x.get("below_bank", 99)))
            p["peak_day"], p["level"], p["label"] = worst["day"], worst["level"], LABELS[worst["level"]]
            p["now_level"] = p["days"][0]["level"]
            p["trend_from"] = next((x["day"] for x in p["days"] if x["kind"] == "trend"), None)
            rows.append(p)
        rows.sort(key=lambda p: order.index(p["province"]) if p["province"] in order else 99)
        nodes = {g["code"]: (g["lat"], g["lng"]) for g in gauges if g["lat"] is not None}
        for d in o.get("dams") or []:
            if d.get("lat") is not None:
                nodes[f"dam:{d['name']}"] = (d["lat"], d["lng"])
        if o.get("bangkok") and o["bangkok"].get("lat") is not None:
            nodes["BKK"] = (o["bangkok"]["lat"], o["bangkok"]["lng"])
        dams = []
        for d in o.get("dams") or []:
            n = nat_dams.get(d["name"]) or {}
            dams.append({"name": d["name"], "river": d.get("river"), "lat": d.get("lat"), "lng": d.get("lng"),
                         "storage_pct": d.get("storage_pct"), "released_m3s": d.get("released_m3s"),
                         "inflow_m3s": d.get("inflow_m3s"), "pct_7d": n.get("pct_7d"), "full_day": n.get("full_day")})
        data = {"updated_at": int(time.time()), "data_time": now, "days": DAYS,
                "dates": [(datetime.fromtimestamp(now, ws.BKK_TZ) + timedelta(days=d)).date().isoformat() for d in range(DAYS + 1)],
                "gauges": gauges, "provinces": rows, "dams": dams, "edges": o.get("edges") or [],
                "paths": self._paths(nodes, o.get("edges") or []), "bangkok_bank": bank}
        with self.lock:
            self.data, self.error = data, None
        self._save()
        print(f"[NorthRoute] {len(rows)} provinces, {sum(p['level'] != 'normal' for p in rows)} to watch, {len(data['paths'])} river paths")

    def analyse(self):
        with self.lock:
            d = self.data
        if not d.get("provinces"):
            return
        sig = json.dumps([(p["province"], p["level"], p["peak_day"], p["now_level"]) for p in d["provinces"]], ensure_ascii=False)
        if sig == self.ai_sig and time.time() - (self.ai.get("generated_at") or 0) < AI_MAX_AGE:
            return
        if not local_llm.default.enabled():
            with self.lock:
                self.ai_error = "ยังไม่ได้ตั้งค่าโมเดล AI (LOCAL_LLM_MODEL)"
            return
        nat = {p["province"]: p for p in (self.national.status().get("provinces") or [])} if self.national else {}
        facts = {
            "dates": d["dates"],
            "provinces": [{
                "province": p["province"], "areas": p["areas"],
                "days": [x["pct"] for x in p["days"]] if p["province"] != BKK_PROVINCE else None,
                "nonthaburi_bkk_below_bank_m": [x["below_bank"] for x in p["days"]] if p["province"] == BKK_PROVINCE else None,
                "level": p["label"], "peak_day": p["peak_day"], "trend_from": p["trend_from"],
                "rain7": round(sum((nat.get(p["province"]) or {}).get("rain7") or [])),
            } for p in d["provinces"]],
            "dams": [{"name": x["name"], "storage_pct": x["storage_pct"], "released_m3s": x["released_m3s"],
                      "pct_7d": x["pct_7d"], "full_in_days": x["full_day"]} for x in d["dams"]],
        }
        with self.lock:
            self.ai_running = True
        started = time.time()
        prompt = (f"ข้อมูล (JSON):\n{json.dumps(facts, ensure_ascii=False, separators=(',', ':'))}\n\n"
                  f"เวลาปัจจุบัน {datetime.now().strftime('%Y-%m-%d %H:%M')} (เวลาไทย)\nส่งเป็น JSON ตาม schema เท่านั้น")
        try:
            text = local_llm.default.chat([{"role": "system", "content": PROMPT}, {"role": "user", "content": prompt}],
                                          max_tokens=4000, temperature=0.2, json_schema=SCHEMA)
            r = json.loads(text[text.find("{"):text.rfind("}") + 1])
        except Exception as e:  # noqa: BLE001 - model down or bad JSON: keep the last report
            with self.lock:
                self.ai_error, self.ai_running = f"{local_llm.default.model}: {str(e)[:160]}", False
            print(f"[NorthRoute] model failed: {e}")
            return
        known = {p["province"] for p in d["provinces"]}
        ai = {"headline": r.get("headline") or "", "now": r.get("now") or "", "next7": r.get("next7") or "",
              "provinces": {x["province"]: {"outlook": x.get("outlook") or "", "advice": x.get("advice") or ""}
                            for x in r.get("provinces") or [] if x.get("province") in known},
              "actions": [a for a in r.get("actions") or [] if a][:4],
              "model": local_llm.default.model, "generated_at": int(time.time()), "took_s": round(time.time() - started, 1)}
        with self.lock:
            self.ai, self.ai_sig, self.ai_error, self.ai_running = ai, sig, None, False
        self._save()

    def _save(self):
        with self.lock:
            data = {"data": self.data, "ai": self.ai, "ai_sig": self.ai_sig}
        try:
            with open(self.path + ".tmp", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(self.path + ".tmp", self.path)
        except OSError as e:
            print(f"[NorthRoute] save failed: {e}")

    def status(self):
        with self.lock:
            return {**self.data, "ai": self.ai, "ai_error": self.ai_error, "ai_running": self.ai_running,
                    "error": self.error, "interval_s": REFRESH_SECONDS}

    def _loop(self):
        time.sleep(240)   # after north_flow and national_forecast have their first answers
        while True:
            try:
                self.refresh()
            except Exception as e:  # noqa: BLE001 - keep the last good answer
                with self.lock:
                    self.error = str(e)[:200]
                print(f"[NorthRoute] refresh failed: {e}")
            try:
                self.analyse()
            except Exception as e:  # noqa: BLE001 - keep the timer alive
                print(f"[NorthRoute] analysis failed: {e}")
            time.sleep(REFRESH_SECONDS)

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="NorthRoute").start()
