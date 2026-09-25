"""Live traffic-dispersal guidance for the main Bangkok corridors.

Every minute (right after traffic_service refreshes the Longdo tiles) each corridor is rebuilt from
live data only:
  * status / flow          - km-weighted from the Longdo road list that matches the corridor
  * hotspots               - where the red segments are right now, named by the nearest BMA camera
                             (with its latest YOLO count) or the nearest Longdo/ITIC camera
  * alternatives           - candidate bypass roads with their live flow; only roads that are
                             actually free right now are recommended
  * incidents              - camera / Longdo incidents whose text mentions the corridor
The action / signal sentences are written by the AI model from those facts (one call per AI_INTERVAL
for all corridors, JSON in / JSON out): the Qwen model behind LOCAL_LLM_* (local_llm.default), else
Gemini. They fall back to a deterministic Thai template when neither answers, so the card is always
populated.
"""
import json
import math
import os
import threading
import time

import local_llm

try:
    from google import genai
    from google.genai import types as genai_types
except Exception:  # pragma: no cover
    genai = None
    genai_types = None

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
AI_INTERVAL = int(os.environ.get("GUIDANCE_AI_SECONDS", "240"))   # seconds between AI rewrites
BUILD_INTERVAL = 60.0

# Corridor catalogue: which Longdo road names form the corridor, and which roads are realistic
# bypasses. `match` substrings are applied to the Longdo road name; `alternatives` are exact names.
CORRIDORS = [
    {"id": "sukhumvit", "name": "ถนนสุขุมวิท / อโศก / ทองหล่อ", "zone": "กรุงเทพฯ ชั้นใน / ตะวันออก (CBD)",
     "search": "ถนนสุขุมวิท", "match": ["ถนนสุขุมวิท", "ถนนอโศกมนตรี", "ซอยสุขุมวิท 55", "ซอยสุขุมวิท 63"],
     "keys": ["สุขุมวิท", "อโศก", "ทองหล่อ", "เอกมัย"],
     "alternatives": ["ถนนเพชรบุรีตัดใหม่", "ถนนพระราม 4", "ทางพิเศษศรีรัช", "ทางพิเศษเฉลิมมหานคร", "ถนนอ่อนนุช (ซอยสุขุมวิท 77)"]},
    {"id": "rama4", "name": "ถนนพระราม 4", "zone": "กรุงเทพฯ ชั้นใน (CBD ใต้)",
     "search": "ถนนพระราม 4", "match": ["ถนนพระราม 4"], "keys": ["พระราม 4", "พระราม4", "คลองเตย", "สามย่าน"],
     "alternatives": ["ถนนพระราม 3", "ถนนสุรวงศ์", "ถนนสาทรใต้", "ถนนสาทรเหนือ", "ทางพิเศษเฉลิมมหานคร"]},
    {"id": "phetchaburi", "name": "ถนนเพชรบุรี / พระราม 9 / รามคำแหง", "zone": "กรุงเทพฯ ตะวันออก",
     "search": "ถนนเพชรบุรี", "match": ["ถนนเพชรบุรี", "ถนนพระราม 9", "ถนนรามคำแหง"],
     "keys": ["เพชรบุรี", "พระราม 9", "พระราม9", "รามคำแหง"],
     "alternatives": ["ทางพิเศษศรีรัช", "ถนนพัฒนาการ", "ถนนศรีนครินทร์", "ถนนมอเตอร์เวย์สายกรุงเทพ-ชลบุรี", "ถนนลาดพร้าว"]},
    {"id": "vibhavadi", "name": "ถนนวิภาวดีรังสิต", "zone": "กรุงเทพฯ เหนือ (ออกเมือง)",
     "search": "ถนนวิภาวดีรังสิต", "match": ["ถนนวิภาวดีรังสิต"], "keys": ["วิภาวดี", "ดอนเมือง", "โทลล์เวย์"],
     "alternatives": ["ทางยกระดับอุตราภิมุข", "ถนนกำแพงเพชร 6", "ถนนพหลโยธิน", "ทางพิเศษศรีรัช", "ถนนแจ้งวัฒนะ"]},
    {"id": "phahonyothin", "name": "ถนนพหลโยธิน", "zone": "กรุงเทพฯ เหนือ",
     "search": "ถนนพหลโยธิน", "match": ["ถนนพหลโยธิน", "ทางคู่ขนานพหลโยธิน"], "keys": ["พหลโยธิน", "รัชโยธิน", "เกษตร"],
     "alternatives": ["ถนนวิภาวดีรังสิต", "ถนนรัชดาภิเษก", "ถนนประเสริฐมนูกิจ", "ทางพิเศษฉลองรัช (รามอินทรา-อาจณรงค์)", "ถนนรามอินทรา"]},
    {"id": "ngamwongwan", "name": "ถนนงามวงศ์วาน / รัตนาธิเบศร์", "zone": "นนทบุรี - กรุงเทพฯ เหนือ",
     "search": "ถนนงามวงศ์วาน", "match": ["ถนนงามวงศ์วาน"], "keys": ["งามวงศ์วาน", "พงษ์เพชร", "แคราย", "รัตนาธิเบศร์"],
     "alternatives": ["ถนนรัตนาธิเบศร์", "ถนนติวานนท์", "ทางพิเศษศรีรัช", "ถนนประชาชื่น", "ถนนแจ้งวัฒนะ"]},
    {"id": "sathorn_silom", "name": "ถนนสาทร / ถนนสีลม (ข้ามแม่น้ำ)", "zone": "กรุงเทพฯ กลาง - ข้ามแม่น้ำเจ้าพระยา",
     "search": "ถนนสาทร", "match": ["ถนนสาทรเหนือ", "ถนนสาทรใต้", "ถนนสีลม", "ถนนนราธิวาสราชนครินทร์"],
     "keys": ["สาทร", "สีลม", "ตากสิน", "สุรศักดิ์"],
     "alternatives": ["ถนนพระราม 3", "ถนนเจริญกรุง", "ถนนพระราม 4", "ถนนสุรวงศ์", "ทางพิเศษเฉลิมมหานคร"]},
    {"id": "borom", "name": "ถนนบรมราชชนนี / ปิ่นเกล้า", "zone": "กรุงเทพฯ ตะวันตก - ฝั่งธนบุรี",
     "search": "ถนนบรมราชชนนี", "match": ["ถนนบรมราชชนนี", "ถนนสมเด็จพระปิ่นเกล้า", "ถนนอรุณอมรินทร์"],
     "keys": ["บรมราชชนนี", "ปิ่นเกล้า", "อรุณอมรินทร์", "คู่ขนานลอยฟ้า"],
     "alternatives": ["ทางคู่ขนานลอยฟ้าบรมราชชนนี", "ถนนพรานนก-พุทธมณฑล สาย 4 (ถนนพระเทพตัดใหม่)", "ถนนจรัญสนิทวงศ์", "ถนนราชพฤกษ์", "สะพานพระราม 8"]},
    {"id": "rama2", "name": "ถนนพระราม 2 (ทล.35)", "zone": "กรุงเทพฯ ใต้ - สมุทรสาคร",
     "search": "ถนนพระราม 2", "match": ["ถนนพระราม 2"], "keys": ["พระราม 2", "พระราม2", "บางขุนเทียน", "แสมดำ", "มหาชัย"],
     "alternatives": ["ถนนกัลปพฤกษ์", "ถนนราชพฤกษ์", "ถนนเพชรเกษม", "ถนนเอกชัย", "ทางพิเศษพระราม 3-ดาวคะนอง-วงแหวนรอบนอกตะวันตก"]},
    {"id": "suksawat_taksin", "name": "ถนนสุขสวัสดิ์ / สมเด็จพระเจ้าตากสิน", "zone": "ฝั่งธนบุรีใต้",
     "search": "ถนนสุขสวัสดิ์", "match": ["ถนนสุขสวัสดิ์", "ถนนสมเด็จพระเจ้าตากสิน"],
     "keys": ["สุขสวัสดิ์", "สมเด็จพระเจ้าตากสิน", "ดาวคะนอง", "มไหสวรรย์"],
     "alternatives": ["ถนนราษฎร์บูรณะ", "สะพานภูมิพล 1", "สะพานภูมิพล2", "ถนนพระราม 3", "ทางพิเศษสายบางพลี - สุขสวัสดิ์ (ถนนวงแหวนรอบนอกด้านใต้)"]},
    {"id": "latphrao", "name": "ถนนลาดพร้าว / เกษตร-นวมินทร์", "zone": "กรุงเทพฯ ตะวันออกเฉียงเหนือ",
     "search": "ถนนลาดพร้าว", "match": ["ถนนลาดพร้าว"], "keys": ["ลาดพร้าว", "โชคชัย 4", "บางกะปิ", "ประเสริฐมนูกิจ"],
     "alternatives": ["ถนนประเสริฐมนูกิจ", "ถนนประดิษฐ์มนูธรรม", "ทางพิเศษฉลองรัช (รามอินทรา-อาจณรงค์)", "ถนนรัชดาภิเษก", "ถนนรามอินทรา"]},
    {"id": "ratchaphruek", "name": "ถนนราชพฤกษ์ / กัลปพฤกษ์", "zone": "ฝั่งธนบุรี - นนทบุรี",
     "search": "ถนนราชพฤกษ์", "match": ["ถนนราชพฤกษ์", "ถนนกัลปพฤกษ์"], "keys": ["ราชพฤกษ์", "กัลปพฤกษ์"],
     "alternatives": ["ถนนกาญจนาภิเษก (ถนนวงแหวนรอบนอกด้านตะวันตก)", "ถนนจรัญสนิทวงศ์", "ถนนเพชรเกษม", "ถนนบรมราชชนนี", "ถนนพรานนก-พุทธมณฑล สาย 4 (ถนนพระเทพตัดใหม่)"]},
]

FREE_FLOW = 75      # alternative counts as "recommended" from this flow score
LEVEL_TH = {"free": "คล่องตัว", "moderate": "ชะลอตัว", "congested": "ติดขัดสะสม", "incident": "มีเหตุขัดขวาง"}


def _km(lat1, lon1, lat2, lon2):
    x = (lon2 - lon1) * 111.32 * math.cos(math.radians((lat1 + lat2) / 2))
    y = (lat2 - lat1) * 110.57
    return math.hypot(x, y)


def _weighted_flow(roads):
    tot = sum(r["length_km"] for r in roads)
    if not tot:
        return None
    return round(sum(r["flow"] * r["length_km"] for r in roads) / tot)


class GuidanceService:
    def __init__(self, traffic, incidents=None, bma=None, cameras=None):
        self.traffic = traffic
        self.incidents = incidents          # IncidentManager (status())
        self.bma = bma                      # BmaScanner (db.get_all_latest())
        self.cameras = cameras or (lambda: [])   # () -> Longdo/ITIC camera list
        self.lock = threading.Lock()
        self.items = []
        self.updated_at = None
        self.ai_mode = "template"
        self._ai_text = {}                  # corridor id -> {"action","signal"} from Gemini
        self._ai_at = 0.0
        self._ai_sig = None
        self.client = self._gemini()
        self.thread = threading.Thread(target=self._loop, daemon=True)

    def start(self):
        self.thread.start()

    # ------------------------------------------------------------------ data
    def _gemini(self):
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if genai is None or not key:
            return None
        try:
            return genai.Client(api_key=key)
        except Exception:
            return None

    def _camera_near(self, lat, lon, bma_cams, itic_cams, max_km=0.6):
        best, best_d = None, max_km
        for c in bma_cams:
            try:
                d = _km(lat, lon, float(c["latitude"]), float(c["longitude"]))
            except (KeyError, TypeError, ValueError):
                continue
            if d < best_d:
                best, best_d = {"title": c.get("title") or c.get("road") or c.get("camid"), "camid": c.get("camid"),
                                "source": "bma", "total": c.get("total"), "level": c.get("level"),
                                "district": c.get("district")}, d
        if best:
            return best
        for c in itic_cams:
            try:
                d = _km(lat, lon, float(c["latitude"]), float(c["longitude"]))
            except (KeyError, TypeError, ValueError):
                continue
            if d < best_d:
                best, best_d = {"title": c.get("short_title") or c.get("title"), "camid": c.get("camid"),
                                "source": "itic", "total": None, "level": None, "district": None}, d
        return best

    def build(self):
        roads = self.traffic.get_roads(limit=1000)
        by_name = {r["name"]: r for r in roads}
        try:
            bma_cams = self.bma.db.get_all_latest() if self.bma else []
        except Exception:
            bma_cams = []
        itic_cams = self.cameras() or []
        inc = self.incidents.status() if self.incidents else {"camera": [], "longdo": []}
        incident_list = list(inc.get("camera", [])) + list(inc.get("longdo", []))

        items = []
        for c in CORRIDORS:
            main = [r for r in roads if any(r["name"].startswith(m) for m in c["match"])]
            flow = _weighted_flow(main)
            red_km = round(sum(r["red_km"] for r in main), 1)
            length_km = round(sum(r["length_km"] for r in main), 1)

            # Red hotspots, named by the nearest camera
            spots = []
            for r in main:
                for sp in r.get("hotspots", []):
                    cam = self._camera_near(sp["lat"], sp["lon"], bma_cams, itic_cams)
                    if cam:
                        label = cam["title"]
                    else:
                        far = self._camera_near(sp["lat"], sp["lon"], bma_cams, itic_cams, max_km=1.5)
                        label = f"ใกล้ {far['title']}" if far else r["name"]
                    spots.append({"road": r["name"], "km": sp["km"], "lat": sp["lat"], "lon": sp["lon"],
                                  "label": label, "camera": cam})
            spots.sort(key=lambda s: -s["km"])
            spots = spots[:3]

            # Alternatives with live flow
            alts = []
            for name in c["alternatives"]:
                r = by_name.get(name)
                if not r:
                    continue
                alts.append({"name": name, "flow": r["flow"], "level": r["level"], "red_km": r["red_km"],
                             "recommended": r["flow"] >= FREE_FLOW})
            alts.sort(key=lambda a: -a["flow"])

            active_inc = [i for i in incident_list
                          if any(k.lower() in f"{i.get('title', '')} {i.get('description', '')}".lower() for k in c["keys"])]

            if active_inc:
                status, tone, priority = "incident", "red", 1
            elif flow is None:
                status, tone, priority = "unknown", "neutral", 5
            elif flow < 45:
                status, tone, priority = "congested", "red", 1
            elif flow < 75:
                status, tone, priority = "moderate", "yellow", 2
            else:
                status, tone, priority = "free", "green", 4

            item = {
                "id": c["id"], "name": c["name"], "zone": c["zone"], "search_road": c["search"],
                "status": status, "status_label": LEVEL_TH.get(status, "ไม่มีข้อมูล"), "tone": tone, "priority": priority,
                "flow": flow, "red_km": red_km, "length_km": length_km,
                "roads": [{"name": r["name"], "flow": r["flow"], "red_km": r["red_km"], "level": r["level"]} for r in main],
                "hotspots": spots, "alternatives": alts,
                "incidents": [{"id": i.get("id"), "kind": i.get("kind"), "title": i.get("title"),
                               "description": i.get("description", "")} for i in active_inc[:2]],
            }
            item.update(self._template_text(item))
            items.append(item)

        items.sort(key=lambda i: (i["priority"], -(i["red_km"] or 0)))
        return items

    # ------------------------------------------------------------------ text
    @staticmethod
    def _template_text(it):
        rec = [a for a in it["alternatives"] if a["recommended"]]
        slow = [a for a in it["alternatives"] if not a["recommended"]]
        if it["status"] == "free":
            action = f"สายทางคล่องตัว (ระบายได้ {it['flow']}/100) ใช้เส้นทางหลักได้ตามปกติ"
            if slow:
                action += f" · เลี่ยง {slow[0]['name']} ที่กำลังชะลอ ({slow[0]['flow']}/100)"
        else:
            # Hotspots are listed on the card already, so the action text only says where to send the traffic
            parts = []
            if rec:
                parts.append("ผันรถไปใช้ " + " หรือ ".join(f"{a['name']} ({a['flow']}/100)" for a in rec[:2]))
            elif it["alternatives"]:
                parts.append(f"ทางเลี่ยงทุกสายชะลอเช่นกัน ดีสุดคือ {it['alternatives'][0]['name']} ({it['alternatives'][0]['flow']}/100)")
            action = " · ".join(parts) or "ยังไม่มีข้อมูลเส้นจราจรของสายทางนี้"
        heavy = [s for s in it["hotspots"] if (s.get("camera") or {}).get("level") == "heavy"]
        if it["incidents"]:
            signal = f"มีเหตุ {it['incidents'][0]['title']} เร่งเคลียร์ช่องทางและตั้งป้ายเตือนล่วงหน้า"
        elif heavy:
            signal = "เปิดไฟเขียวยาวขึ้นขาที่สะสมบริเวณ " + ", ".join(f"{s['label']} ({s['camera']['total']} คัน)" for s in heavy[:2])
        elif it["status"] in ("congested", "moderate"):
            signal = "ซิงค์สัญญาณไฟตามแนวแกนหลัก (Green Wave) และห้ามจอดแช่ช่องซ้ายบริเวณจุดสะสม"
        else:
            signal = "รักษาจังหวะสัญญาณไฟตามปกติ"
        bypass = " หรือ ".join(a["name"] for a in rec[:2]) if rec else (it["alternatives"][0]["name"] if it["alternatives"] else "-")
        return {"action": action, "signal": signal, "bypass": bypass, "ai": False}

    def _ai_refresh(self, items):
        """One AI call for every corridor, at most once per AI_INTERVAL even when the picture changes."""
        if not self.client and not local_llm.default.enabled():
            return
        sig = json.dumps([(i["id"], i["status"], [s["label"] for s in i["hotspots"]],
                           [a["name"] for a in i["alternatives"] if a["recommended"]]) for i in items], ensure_ascii=False)
        now = time.time()
        if now - self._ai_at < AI_INTERVAL:
            return
        facts = [{"id": i["id"], "name": i["name"], "status": i["status_label"], "flow": i["flow"], "red_km": i["red_km"],
                  "hotspots": [{"where": s["label"], "red_km": s["km"],
                                "camera_vehicles": (s.get("camera") or {}).get("total")} for s in i["hotspots"]],
                  "alternatives": [{"name": a["name"], "flow": a["flow"], "free": a["recommended"]} for a in i["alternatives"]],
                  "incidents": [x["title"] for x in i["incidents"]]} for i in items]
        prompt = (
            "คุณคือเจ้าหน้าที่ศูนย์ควบคุมจราจรกรุงเทพฯ ข้างล่างคือข้อมูลสดของสายทางหลัก (flow 0-100 ยิ่งสูงยิ่งโล่ง, "
            "red_km = ระยะเส้นแดงสะสม, hotspots = จุดที่แดงตอนนี้พร้อมจำนวนรถจากกล้อง, alternatives = ทางเลี่ยงพร้อม flow สด)\n"
            "เขียนคำแนะนำภาษาไทยสำหรับแต่ละสายทาง อิงตัวเลขที่ให้เท่านั้น ห้ามแต่งจุดหรือถนนที่ไม่มีในข้อมูล\n"
            "- action: วิธีระบายรถตอนนี้ 1 ประโยคสั้น (ไม่เกิน 25 คำ) บอกว่าผันรถจากจุดไหนไปทางเลี่ยงใดที่ flow สูงจริง "
            "(ห้ามแนะนำทางเลี่ยงที่ free=false และไม่ต้องทวนรายการจุดสะสม เพราะแสดงแยกอยู่แล้ว)\n"
            "- signal: มาตรการสัญญาณไฟ/ตำรวจจราจร 1 ประโยคสั้น (ไม่เกิน 20 คำ) เจาะจงจุด\n"
            "- ห้ามเขียนชื่อฟิลด์ภาษาอังกฤษ (flow, red_km, free) ในข้อความ ให้เขียนเป็น 'ระบายได้ 96/100' แทน\n"
            "ตอบเป็น JSON array เท่านั้น รูปแบบ [{\"id\":..., \"action\":..., \"signal\":...}]\n\n"
            + json.dumps(facts, ensure_ascii=False)
        )
        try:
            if local_llm.default.enabled():
                text, mode = local_llm.default.chat([{"role": "user", "content": prompt}], max_tokens=3000, temperature=0.3), "qwen"
            else:
                resp = self.client.models.generate_content(
                    model=GEMINI_MODEL, contents=prompt,
                    config=genai_types.GenerateContentConfig(temperature=0.3, max_output_tokens=3000,
                                                             response_mime_type="application/json"))
                text, mode = resp.text or "[]", "gemini"
            data = json.loads(text[text.find("["):text.rfind("]") + 1] or "[]")
            out = {}
            for row in data:
                if isinstance(row, dict) and row.get("id") and row.get("action"):
                    out[row["id"]] = {"action": str(row["action"]).strip(), "signal": str(row.get("signal") or "").strip()}
            if out:
                self._ai_text = out
                self.ai_mode = mode
                print(f"[Guidance] {mode} rewrote {len(out)} corridors")
        except Exception as e:
            print(f"[Guidance] AI failed, using template: {e}")
        self._ai_sig, self._ai_at = sig, now

    # ------------------------------------------------------------------ loop
    def refresh(self):
        items = self.build()
        self._ai_refresh(items)
        for it in items:
            t = self._ai_text.get(it["id"])
            if t:
                it["action"], it["ai"] = t["action"], True
                if t["signal"]:
                    it["signal"] = t["signal"]
        with self.lock:
            self.items = items
            self.updated_at = int(time.time())

    def _loop(self):
        # Wait for the first traffic refresh so the card is never built from an empty road list
        while not self.traffic.summary.get("ready"):
            time.sleep(5)
        while True:
            try:
                self.refresh()
            except Exception as e:
                print(f"[Guidance] refresh error: {e}")
            time.sleep(BUILD_INTERVAL)

    def status(self):
        with self.lock:
            return {"updated_at": self.updated_at, "traffic_updated_at": self.traffic.summary.get("updated_at"),
                    "ai_mode": self.ai_mode if self._ai_text else "template", "items": list(self.items)}
