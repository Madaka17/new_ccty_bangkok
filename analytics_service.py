"""
Urban & platform analytics: one summary that joins the live services into five sections
(traffic overview, flood surveillance + 1-6 h prediction, road density tiers, accident
black spots + countermeasures, dashboard visitors) for /api/analytics/*.

Every number is derived from data other services already hold; nothing here fetches
the internet. Speed tiers are a proxy from Longdo colour classes (no km/h feed exists).
Flood prediction and countermeasures are deterministic rules, documented next to the code.
"""
import csv
import glob
import io
import json
import os
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

import rsc_service
import water_service
from bma_events import bma_feed
from telemetry_service import telemetry
from traffic_service import traffic

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
from instance import DATA_DIR   # cache / db root: project root, or local/stage for the test server
RSC_POINTS_GLOB = os.path.join(DATA_DIR, "cache", "rsc", "points_*.json")
BKK_TZ = timezone(timedelta(hours=7))

SUMMARY_TTL = 60
POINTS_TTL = 3600
MAJOR_ROAD_KM = 5.0          # a named road at least this long counts as "สายหลัก"
EVENT_HOURS = 6              # BMA reports this recent can explain a slow road
BLACK_SPOT_CELL = 0.0025     # ~275 m grid for clustering accident points
BLACK_SPOTS = 10

# Speed proxy: Longdo colour -> density tier (definition given by the analytics brief)
TIERS = (
    {"id": "heavy", "label": "หนาแน่น", "speed": "< 15 กม./ชม.", "note": "มีแถวคอยสะสมยาว", "color": "red", "level": "ติดขัด"},
    {"id": "moderate", "label": "ปานกลาง", "speed": "15–35 กม./ชม.", "note": "เคลื่อนตัวได้ตามรอบสัญญาณไฟ", "color": "yellow", "level": "ปานกลาง"},
    {"id": "free", "label": "คล่องตัว", "speed": "> 35 กม./ชม.", "note": "เคลื่อนตัวได้ต่อเนื่อง", "color": "green", "level": "โล่ง"},
)

CAUSE_LABEL = {
    "roadwork": "มีการก่อสร้าง / ปิดเบี่ยงการจราจร",
    "accident": "อุบัติเหตุบนเส้นทาง",
    "breakdown": "รถเสียกีดขวางช่องจราจร",
    "flood": "น้ำท่วมขังผิวจราจร",
    "fire": "เหตุเพลิงไหม้ใกล้เส้นทาง",
    "tree": "ต้นไม้ / ป้ายล้มกีดขวาง",
    "camera": "กล้อง AI พบรถจอดนิ่ง / ชนกัน",
}
NO_CAUSE = "ไม่มีรายงานเหตุ - คาดว่าเกิดจากปริมาณรถสะสมและจุดตัดสัญญาณไฟ"

# Countermeasure table for black spots, keyed by what the place name says about the road
COUNTERMEASURES = (
    (("แยก",), "ทางแยก", [
        "ปรับรอบสัญญาณไฟ: แยกเฟสเลี้ยวขวาออกจากทางตรง และเพิ่มเวลาเคลียร์แยก (all-red) 2 วินาที",
        "ปรับกายภาพทางแยก: ตีเส้นช่องรอเลี้ยว ขยายเกาะกลาง เพิ่มไฟส่องสว่างที่จุดตัด",
        "ติดกล้องตรวจจับฝ่าไฟแดงและตรวจจับความเร็วก่อนถึงแยก",
    ]),
    (("ด่วน", "ต่างระดับ", "มอเตอร์เวย์", "ทางลง", "ทางขึ้น", "สะพาน", "วงแหวน", "กาญจนาภิเษก"), "ทางด่วน / ทางต่างระดับ", [
        "ติดกล้องตรวจจับความเร็วและป้ายเตือนจำกัดความเร็วก่อนโค้งและทางลง",
        "ติดตั้งราวกันอันตรายและแผงกันชน (crash cushion) ที่จุดแยกทางลง",
        "ทำแถบสั่นเตือน (rumble strip) ก่อนถึงจุดชะลอความเร็ว",
    ]),
    (("โค้ง",), "ทางโค้ง", [
        "ติดป้ายเตือนทางโค้งและเครื่องหมายนำทาง (chevron) ให้เห็นจากระยะ 150 ม.",
        "ปรับผิวทางเพิ่มความเสียดทาน (anti-skid) และตีเส้นสะท้อนแสงใหม่",
        "ติดกล้องตรวจจับความเร็วก่อนเข้าโค้ง",
    ]),
    (("ซอย", "ตลาด", "โรงเรียน", "หน้า", "ปาก"), "ถนนท้องถิ่น / หน้าชุมชน", [
        "ลดความเร็วด้วยเนินชะลอและทางม้าลายยกระดับ (traffic calming)",
        "เพิ่มทางข้ามพร้อมไฟกะพริบและไฟส่องสว่างหน้าชุมชน",
        "จัดระเบียบจุดจอดและป้ายรถเมล์ที่บดบังทัศนวิสัย",
    ]),
)
DEFAULT_MEASURES = ("ถนนสายหลัก", [
    "ติดกล้องตรวจจับความเร็วและกำหนดช่องทางเฉพาะรถจักรยานยนต์ช่องซ้าย",
    "เพิ่มไฟส่องสว่างและเส้นจราจรสะท้อนแสงตลอดช่วงที่เกิดเหตุซ้ำ",
    "ปิดจุดกลับรถอันตรายและย้ายไปจุดกลับรถที่มีสัญญาณไฟ",
])

_lock = threading.Lock()
_cache = {"ts": 0, "data": None}
_points = {"ts": 0, "rows": []}
_incidents = None


def configure(incidents=None):
    """server.py hands over the IncidentManager instance (camera AI + Longdo reports)."""
    global _incidents
    _incidents = incidents


def _safe(fn, default):
    try:
        return fn()
    except Exception as e:
        print(f"[Analytics] {getattr(fn, '__name__', 'part')}: {e}")
        return default


def _road_key(name):
    return (name or "").replace("ถนน", "").replace("ถ.", "").strip().lower()


# ---------------------------------------------------------------- 1. traffic overview
def _delay_causes(road_name, events, longdo, camera):
    key = _road_key(road_name)
    if len(key) < 3:
        return []
    found = []
    for e in events:
        text = f"{e.get('title', '')} {e.get('desc', '')}"
        if key in text.lower():
            kind = e.get("kind") or "other"
            if kind == "accident" and "รถเสีย" in text:
                kind = "breakdown"
            found.append({"kind": kind, "label": CAUSE_LABEL.get(kind, e.get("title", "")), "title": e.get("title", ""), "ts": e.get("ts")})
    for e in longdo:
        text = f"{e.get('title', '')} {e.get('description', '')}"
        if key in text.lower():
            found.append({"kind": "accident", "label": CAUSE_LABEL["accident"], "title": e.get("title", ""), "ts": e.get("start")})
    for e in camera:
        if key in _road_key(e.get("camera_title") or e.get("title") or ""):
            found.append({"kind": "camera", "label": CAUSE_LABEL["camera"], "title": e.get("description", ""), "ts": e.get("ts")})
    # newest first, one line per cause kind
    found.sort(key=lambda c: -(c.get("ts") or 0))
    seen, out = set(), []
    for c in found:
        if c["kind"] not in seen:
            seen.add(c["kind"])
            out.append(c)
    return out[:3]


def _traffic_section():
    summary = traffic.get_summary(top=5)
    roads = traffic.get_roads(limit=5000)
    if not summary.get("ready") or not roads:
        return {"ready": False}
    events = (_safe(lambda: bma_feed.get(hours=EVENT_HOURS, limit=200), {}) or {}).get("items", [])
    inc = _safe(lambda: _incidents.status() if _incidents else {}, {}) or {}
    longdo, camera = inc.get("longdo", []), inc.get("camera", [])

    major = [r for r in roads if r["length_km"] >= MAJOR_ROAD_KM]
    minor = [r for r in roads if r["length_km"] < MAJOR_ROAD_KM]

    def group(rows):
        km = sum(r["length_km"] for r in rows)
        red = sum(r["red_km"] for r in rows)
        return {"roads": len(rows), "km": round(km, 1), "red_km": round(red, 1),
                "red_pct": round(100 * red / km) if km else 0,
                "congested": sum(1 for r in rows if r["level"] == "ติดขัด")}

    # City Congestion Index: share of network-km that is slow, yellow counted half. 0 = free, 100 = gridlock.
    cci = round(summary["red_pct"] + 0.5 * summary["yellow_pct"])
    cci_level = "วิกฤต" if cci >= 60 else "ติดขัดมาก" if cci >= 40 else "ติดขัดปานกลาง" if cci >= 20 else "คล่องตัว"
    top = sorted(roads, key=lambda r: (-r["red_km"], r["flow"]))[:5]
    top5 = []
    for r in top:
        causes = _delay_causes(r["name"], events, longdo, camera)
        top5.append({**r, "major": r["length_km"] >= MAJOR_ROAD_KM, "causes": causes,
                     "cause_text": " / ".join(c["label"] for c in causes) or NO_CAUSE})
    return {
        "ready": True,
        "online": summary.get("online"),
        "updated_at": summary.get("updated_at"),
        "congestion_index": cci,
        "congestion_level": cci_level,
        "flow_index": summary.get("flow_index"),
        "total_km": summary.get("total_km"),
        "road_count": summary.get("road_count"),
        "red_pct": summary["red_pct"], "yellow_pct": summary["yellow_pct"], "green_pct": summary["green_pct"],
        "major": group(major),
        "secondary": group(minor),
        "major_threshold_km": MAJOR_ROAD_KM,
        "top5": top5,
        "reports_6h": len(events),
    }


# ---------------------------------------------------------------- 2. flood surveillance + 1-6 h prediction
def _flood_risk_hours(zone):
    """Deterministic 1-6 h outlook per weather zone.
    base: water already high (+25), already overflowing or road flooded (+45), rain fallen today (+mm/3, max 30)
    then +2.5 per mm of forecast rain accumulated up to that hour, +10 when rain probability >= 70 %."""
    base = 0
    if zone.get("stations_overflow") or zone.get("flood_roads"):
        base += 45
    elif zone.get("stations_high"):
        base += 25
    base += min(30, (zone.get("rain_observed_mm") or 0) / 3)
    prob_bonus = 10 if (zone.get("prob_6h") or 0) >= 70 else 0
    hourly = zone.get("hourly") or []
    out, cum = [], 0.0
    for h in range(1, 7):
        mm = hourly[h - 1]["mm"] if h - 1 < len(hourly) else 0.0
        cum += mm or 0
        score = min(100, round(base + 2.5 * cum + prob_bonus))
        level = "สูง" if score >= 70 else "ปานกลาง" if score >= 40 else "ต่ำ"
        out.append({"h": h, "at": hourly[h - 1]["t"] if h - 1 < len(hourly) else None, "mm": round(mm or 0, 1),
                    "cum_mm": round(cum, 1), "score": score, "level": level})
    return out


def _flood_section():
    w = water_service.get_summary()
    river, canals = w.get("river", []), w.get("canals", [])
    roads = w.get("flood_roads") or {}

    def station(r, kind):
        crit = r.get("bank") if kind == "river" else None
        return {"kind": kind, "name": r.get("name"), "district": r.get("district"), "province": r.get("province"),
                "level": r.get("level"), "msl": r.get("msl"), "critical": crit, "diff_bank": r.get("diff_bank"),
                "storage_pct": r.get("storage_pct"), "trend": r.get("trend"), "ts": r.get("ts")}

    stations = [station(r, "river") for r in river] + [station(r, "canal") for r in canals]
    alert = [s for s in stations if s["level"] in ("overflow", "high")]
    by_district = defaultdict(lambda: {"district": "", "overflow": 0, "high": 0, "flood_roads": 0, "max_depth_cm": 0, "items": []})
    for s in alert:
        d = by_district[s["district"] or s["province"] or "-"]
        d["district"] = s["district"] or s["province"] or "-"
        d[s["level"]] += 1
        d["items"].append(f"{s['name']} ({'ล้นตลิ่ง' if s['level'] == 'overflow' else 'ใกล้วิกฤต'})")
    for r in roads.get("items", []):
        d = by_district[r.get("district") or "-"]
        d["district"] = r.get("district") or "-"
        d["flood_roads"] += 1
        d["max_depth_cm"] = max(d["max_depth_cm"], r.get("depth_cm") or 0)
        d["items"].append(f"{r['name']} น้ำสูง {r.get('depth_cm') or 0} ซม.")
    urgent = sorted(by_district.values(), key=lambda d: (-d["overflow"], -d["flood_roads"], -d["high"]))
    for d in urgent:
        d["items"] = d["items"][:5]
        d["priority"] = "เร่งด่วน" if d["overflow"] or d["max_depth_cm"] >= 10 else "เฝ้าระวัง"

    prediction = []
    for z in w.get("weather", []):
        hours = _flood_risk_hours(z)
        worst = max(hours, key=lambda h: h["score"])
        prediction.append({"zone": z["name"], "areas": z.get("areas"), "watch": z.get("watch"),
                           "rain_6h": z.get("rain_6h"), "prob_6h": z.get("prob_6h"), "rain_observed_mm": z.get("rain_observed_mm"),
                           "peak_score": worst["score"], "peak_level": worst["level"], "peak_h": worst["h"], "hours": hours})
    prediction.sort(key=lambda p: -p["peak_score"])

    return {
        "ready": True,
        "updated_at": w.get("updated_at"),
        "stale": w.get("stale"),
        "station_counts": {"river": w.get("river_counts"), "canal": w.get("canal_counts"), "canal_total": w.get("canal_total")},
        "flood_roads": {k: roads.get(k) for k in ("flooding", "slight", "normal")},
        "alert_stations": sorted(alert, key=lambda s: (s["level"] != "overflow", -(s["storage_pct"] or 0)))[:20],
        "urgent_districts": urgent[:12],
        "prediction": prediction,
        "model_note": "คะแนน = ฐาน(น้ำสูง 25 / ล้น-ถนนท่วม 45 / ฝนที่ตกแล้ว มม.÷3) + 2.5×ฝนสะสมคาดการณ์(มม.) + 10 ถ้าโอกาสฝน ≥ 70%",
    }


# ---------------------------------------------------------------- 3. road density tiers
def _density_section():
    summary = traffic.get_summary(top=1)
    roads = traffic.get_roads(limit=5000)
    if not summary.get("ready") or not roads:
        return {"ready": False}
    total_km = summary.get("total_km") or 0
    km_pct = {"heavy": summary["red_pct"], "moderate": summary["yellow_pct"], "free": summary["green_pct"]}
    tiers = []
    for t in TIERS:
        rows = [r for r in roads if r["level"] == t["level"]]
        tiers.append({**t, "roads": len(rows), "road_pct": round(100 * len(rows) / len(roads)) if roads else 0,
                      "km_pct": km_pct[t["id"]], "km": round(total_km * km_pct[t["id"]] / 100, 1),
                      "examples": [r["name"] for r in sorted(rows, key=lambda r: -r["length_km"])[:5]],
                      # full list so the card can expand into every road of the tier
                      "road_list": [{"name": r["name"], "length_km": r["length_km"], "red_km": r["red_km"], "flow": r["flow"],
                                     "green_pct": r["green_pct"], "yellow_pct": r["yellow_pct"], "red_pct": r["red_pct"]}
                                    for r in sorted(rows, key=lambda r: (-r["red_km"], r["flow"]))]})
    return {"ready": True, "updated_at": summary.get("updated_at"), "total_km": total_km, "road_count": len(roads),
            "tiers": tiers, "proxy_note": "ไม่มีข้อมูลความเร็วจริง: จัดระดับจากสีเส้นจราจร Longdo (แดง/เหลือง/เขียว) แทนช่วงความเร็ว"}


# ---------------------------------------------------------------- 4. accidents + countermeasures
def _load_points():
    now = time.time()
    with _lock:
        if _points["rows"] and now - _points["ts"] < POINTS_TTL:
            return _points["rows"]
    rows = []
    for path in glob.glob(RSC_POINTS_GLOB):
        try:
            with open(path, encoding="utf-8") as f:
                rows.extend(p for p in json.load(f).get("points", []) if p.get("lat") and p.get("lon"))
        except Exception:
            continue
    with _lock:
        _points.update(ts=now, rows=rows)
    return rows


def _measures_for(place):
    for words, kind, measures in COUNTERMEASURES:
        if any(w in place for w in words):
            return kind, measures
    return DEFAULT_MEASURES


def _black_spots(points):
    cells = defaultdict(list)
    for p in points:
        cells[(int(p["lat"] / BLACK_SPOT_CELL), int(p["lon"] / BLACK_SPOT_CELL))].append(p)
    spots = []
    for pts in cells.values():
        cases, dead, injured = len(pts), sum(p["dead"] for p in pts), sum(p["injured"] for p in pts)
        if cases < 3:
            continue
        place = Counter(p["place"] for p in pts if p.get("place")).most_common(1)
        district = Counter(p["district"] for p in pts if p.get("district")).most_common(1)
        name = place[0][0] if place else "-"
        kind, measures = _measures_for(name)
        years = sorted({(p.get("date") or "")[:4] for p in pts if p.get("date")})
        spots.append({
            "place": name, "district": district[0][0] if district else "-", "road_type": kind,
            "lat": round(sum(p["lat"] for p in pts) / cases, 5), "lon": round(sum(p["lon"] for p in pts) / cases, 5),
            "cases": cases, "dead": dead, "injured": injured, "years": years,
            "score": cases + 3 * injured + 10 * dead,
            "priority": "เร่งด่วน" if dead else "สูง" if injured >= 10 else "ปานกลาง",
            "measures": measures,
        })
    spots.sort(key=lambda s: -s["score"])
    return spots[:BLACK_SPOTS]


def _accident_section():
    rsc = _safe(rsc_service.get_summary, {}) or {}
    points = _load_points()
    districts = [{"name": d["name"], "accidents": d.get("accidents"), "dead": d.get("dead"), "injured": d.get("injured")}
                 for d in rsc.get("districts", [])]
    by_hour = rsc.get("dead_by_hour") or []
    night = sum(by_hour[18:] + by_hour[:6]) if len(by_hour) == 24 else 0
    total_hour = sum(by_hour) if by_hour else 0
    moto = next((v for v in rsc.get("dead_by_vehicle", []) if "จักรยานยนต์" in (v.get("label") or "")), None)
    citywide = []
    if total_hour and night / total_hour >= 0.5:
        citywide.append(f"ผู้เสียชีวิตช่วง 18:00–06:00 คิดเป็น {round(100 * night / total_hour)}% - เพิ่มไฟส่องสว่างและด่านตรวจแอลกอฮอล์กลางคืนที่จุดเสี่ยง")
    if moto and (moto.get("pct") or 0) >= 50:
        citywide.append(f"รถจักรยานยนต์ {moto['pct']}% ของผู้เสียชีวิต - บังคับใช้หมวกกันน็อกและช่องทางเฉพาะจักรยานยนต์บนถนนสายหลัก")
    return {
        "ready": bool(rsc),
        "updated": rsc.get("updated"),
        "source": rsc.get("source"),
        "year_be": rsc.get("year_be"),
        "today": rsc.get("today"), "ytd": rsc.get("ytd"),
        "districts": districts[:15],
        "injury_note": "Thai RSC รายงานผู้บาดเจ็บรวม ไม่แยกระดับสาหัส",
        "points_total": len(points),
        "black_spots": _black_spots(points),
        "citywide_measures": citywide,
        "dead_by_hour": by_hour,
    }


# ---------------------------------------------------------------- 5. visitors
def _visitor_section():
    return {"ready": True, **telemetry.stats()}


# ---------------------------------------------------------------- summary + export
def _build():
    return {
        "generated_at": int(time.time()),
        "traffic": _safe(_traffic_section, {"ready": False}),
        "flood": _safe(_flood_section, {"ready": False}),
        "density": _safe(_density_section, {"ready": False}),
        "accidents": _safe(_accident_section, {"ready": False}),
        "visitors": _safe(_visitor_section, {"ready": False}),
    }


def get_summary(force=False):
    with _lock:
        fresh = _cache["data"] and time.time() - _cache["ts"] < SUMMARY_TTL
    if fresh and not force:
        return _cache["data"]
    data = _build()
    with _lock:
        _cache.update(ts=time.time(), data=data)
    return data


def export_csv(section):
    """Flat rows for the one section; the JSON export carries the full nested summary."""
    s = get_summary().get(section) or {}
    rows = {
        "traffic": lambda: [{"rank": i + 1, "road": r["name"], "length_km": r["length_km"], "red_km": r["red_km"], "flow": r["flow"],
                             "level": r["level"], "major": r["major"], "cause": r["cause_text"]} for i, r in enumerate(s.get("top5", []))],
        "flood": lambda: [{"zone": p["zone"], "areas": p["areas"], "watch": p["watch"], "hour": h["h"], "at": h["at"], "rain_mm": h["mm"],
                           "cum_mm": h["cum_mm"], "score": h["score"], "level": h["level"]} for p in s.get("prediction", []) for h in p["hours"]],
        "density": lambda: [{"tier": t["label"], "speed": t["speed"], "roads": t["roads"], "road_pct": t["road_pct"], "km": t["km"], "km_pct": t["km_pct"]}
                            for t in s.get("tiers", [])],
        "accidents": lambda: [{"rank": i + 1, "place": b["place"], "district": b["district"], "road_type": b["road_type"], "cases": b["cases"],
                               "dead": b["dead"], "injured": b["injured"], "priority": b["priority"], "lat": b["lat"], "lon": b["lon"],
                               "measures": " | ".join(b["measures"])} for i, b in enumerate(s.get("black_spots", []))],
        "visitors": lambda: [{"hour": h, "views_7d": n} for h, n in enumerate(s.get("hours", []))],
    }.get(section, lambda: [])()
    buf = io.StringIO()
    if rows:
        w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return "﻿" + buf.getvalue()
