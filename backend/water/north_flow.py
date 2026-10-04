"""
Water from the North on its way to the Central Plain: how much the Ping, Wang, Yom and Nan carry now,
and when and how much of it reaches Nakhon Sawan, the Chao Phraya Dam, Sing Buri, Ang Thong and Ayutthaya.

Data: RID key gauges relayed by ThaiWater (the same keyed API as water_service): hourly water level and
discharge (m3/s) for the last FIT_DAYS days, the bank height and each gauge's bank-full discharge
(qmax, the "ความจุลำน้ำ" RID reports against). Upstream dams come from the National Thai Water snapshot
water_service already caches, and the HII 7-day level forecasts at Nakhon Sawan, Ayutthaya and
Nonthaburi from water_service.get_forecast.

Model (flow routing, not a hydraulic simulation): each reach passes the change in its upstream discharge
down after a travel time,
    D(now + h) = D(now) + a * (U(now + h - lag) - U(now - lag)),
where U is the sum of the reach's inputs. The gain a (floodplain storage, side streams, canal diversions
at the Chao Phraya Dam) and the lag (the prior, or 25% shorter or longer) are fitted on the last
FIT_DAYS days at every refresh. Once the lag runs past now a reach reads its inputs' own forecasts, so
the Ayutthaya outlook starts from the water measured at Kamphaeng Phet and Phichit. The top gauges
(P.7A, N.7A, Ct.19) are held at their latest value: a node's outlook follows measured water for its
`lead_h` hours and after that assumes the upstream flow stays level.
Backtest on Sep 2026 data (60 start times): 24 h ahead the Chao Phraya gauges C.2-C.35 are off by 4-6%
(holding the current flow: 6-9%), 48 h ahead by 8-12% (11-15%). The Ping reach P.7A -> P.17 does no
better than holding: side streams below Kamphaeng Phet feed it as much as the Ping does. The Chao Phraya
Dam (C.13) release is set by RID, so its outlook shows what passes if the dam lets the water through as
it did in the last two weeks.

Every 10 minutes: RID sends discharge once an hour, but HII gauges next to most RID gauges send the water
level every 10 minutes. For each RID gauge the nearest HII gauges (within MATCH_KM) are tried: a rating
curve (discharge as a quadratic of the HII level) is fitted on the last FIT_DAYS days and kept only if it
predicts the last 48 RID hours within MATCH_MAPE percent. Those gauges get a 10-minute discharge estimate
(`ten_min`, `latest10`) between the hourly RID reports. start() refreshes everything every 10 minutes.

Served by /api/water/north; brief() is the short form for the AI analysts.
"""
import threading
import time
from bisect import bisect_left, bisect_right
from datetime import datetime, timedelta

import numpy as np

from backend.water import water_service as ws

FLOW_TTL = 600           # the outlook, with the 10-minute estimates
RID_TTL = 1800           # ThaiWater relays the RID gauges hourly
RATING_TTL = 6 * 3600    # gauge pairing and rating curves are refitted this often
MATCH_KM = 15
MATCH_MAPE = 5.0         # % error on the last 48 RID hours a rating must beat to be used
TEN_MIN_H = 12           # 10-minute estimates sent to the page
FIT_DAYS = 14
HISTORY_H = 72           # observed hours sent to the page
HORIZON_H = 96
STALE_H = 6              # a gauge with no reading for this long is offline
HOUR = 3600

RIVERS = {"ping": "แม่น้ำปิง", "wang": "แม่น้ำวัง", "yom": "แม่น้ำยม", "nan": "แม่น้ำน่าน",
          "chao_phraya": "แม่น้ำเจ้าพระยา", "sakae_krang": "แม่น้ำสะแกกรัง", "pasak": "แม่น้ำป่าสัก"}
# RID code, ThaiWater station id, ThaiWater station name, province, river; upstream to downstream
STATIONS = [
    ("P.1", 4267, "สะพานนวรัฐ", "เชียงใหม่", "ping"),
    ("W.4A", 4059, "บ้านวังหมัน", "ตาก", "wang"),
    ("P.7A", 3942, "ต.ในเมือง", "กำแพงเพชร", "ping"),
    ("P.17", 3874, "บ้านท่างิ้ว", "นครสวรรค์", "ping"),
    ("Y.4", 4027, "ต.ธานี", "สุโขทัย", "yom"),
    ("Y.16", 3983, "บางระกำ", "พิษณุโลก", "yom"),
    ("N.60", 4106, "บ้านเด่นสำโรง", "อุตรดิตถ์", "nan"),
    ("N.5A", 3995, "สะพานสุพรรณกัลยา", "พิษณุโลก", "nan"),
    ("N.7A", 3937, "บ้านราชช้างขวัญ", "พิจิตร", "nan"),
    ("N.67", 3863, "วัดเกยไชยเหนือ", "นครสวรรค์", "nan"),
    ("C.2", 3837, "ค่ายจิรประวัติ", "นครสวรรค์", "chao_phraya"),
    ("Ct.19", 3819, "บ้านดอนใหญ่", "อุทัยธานี", "sakae_krang"),
    ("C.13", 3786, "ท้ายเขื่อนเจ้าพระยา", "ชัยนาท", "chao_phraya"),
    ("C.3", 3765, "บ้านบางพุทรา", "สิงห์บุรี", "chao_phraya"),
    ("C.7A", 3668, "บ้านบางแก้ว", "อ่างทอง", "chao_phraya"),
    ("C.35", 3651, "บ้านป้อม", "พระนครศรีอยุธยา", "chao_phraya"),
    ("S.26", 3666, "ท้ายเขื่อนพระรามหก", "พระนครศรีอยุธยา", "pasak"),
]
# Routed reaches, upstream first: gauge <- ((input gauge, prior travel time in hours), ...).
# Priors are the lags that fit Sep 2026 best; the Yom reaches the Nan above N.67 through the Bang Rakam
# floodplain and has no discharge at its lower gauges, so it is shown but not routed.
REACHES = [
    ("P.17", (("P.7A", 18),)),
    ("N.67", (("N.7A", 18),)),
    ("C.2", (("P.17", 9), ("N.67", 9))),
    ("C.13", (("C.2", 18), ("Ct.19", 9))),
    ("C.3", (("C.13", 9),)),
    ("C.7A", (("C.3", 6),)),
    ("C.35", (("C.7A", 12),)),
]
LAG_SCALES = (0.75, 1.0, 1.25)
GAIN_RANGE = (0.2, 1.5)
# HII 7-day level forecasts along the way (water_service.OFFICIAL_FORECAST_STATIONS)
OFFICIAL = {"C.2": 1648, "C.35": 1142, "S.26": 1143}
BANGKOK_STATION = 1132
BANGKOK_POS = (13.94749, 100.53507)       # สะพานนวลฉวี, as ThaiWater places it
# Upstream dams (National Thai Water names) and the river they release into
DAMS = {"ภูมิพล": "ping", "สิริกิติ์": "nan", "แควน้อยบำรุงแดน": "nan", "ป่าสักชลสิทธิ์": "pasak"}
# Which way the water goes, for the map arrows: gauge codes, "dam:<name>" and "BKK" (Nonthaburi-Bangkok).
# The Wang joins the Ping at Tak, the Yom the Nan at Chum Saeng, the Sakae Krang above the Chao Phraya Dam
# and the Pa Sak at Ayutthaya.
FLOW_EDGES = [
    ("P.1", "dam:ภูมิพล"), ("dam:ภูมิพล", "P.7A"), ("W.4A", "P.7A"), ("P.7A", "P.17"), ("P.17", "C.2"),
    ("Y.4", "Y.16"), ("Y.16", "N.67"),
    ("dam:สิริกิติ์", "N.60"), ("N.60", "N.5A"), ("dam:แควน้อยบำรุงแดน", "N.5A"), ("N.5A", "N.7A"),
    ("N.7A", "N.67"), ("N.67", "C.2"),
    ("C.2", "C.13"), ("Ct.19", "C.13"), ("C.13", "C.3"), ("C.3", "C.7A"), ("C.7A", "C.35"),
    ("dam:ป่าสักชลสิทธิ์", "S.26"), ("S.26", "C.35"), ("C.35", "BKK"),
]
# ThaiWater's river situation classes: above 70% of capacity "น้ำมาก", above 100% over the bank
HIGH_PCT, OVERFLOW_PCT = 70, 100
RISE_PCT, RISE_M3S = 30, 200     # a 24 h rise this large on a gauge is a flood wave worth a line of its own
STATUS_TH = {"overflow": "ล้นตลิ่ง", "high": "น้ำมาก", "normal": "ปกติ", "offline": "ไม่มีข้อมูล"}


# ---------------------------------------------------------------- series
def _load_station(sid):
    end = datetime.now(ws.BKK_TZ)
    d = ws._get("/data/platform/v1/public/tele_waterlevel/graph", stationId=sid,
                startDate=(end - timedelta(days=FIT_DAYS + 2)).strftime("%Y-%m-%d"),
                endDate=(end + timedelta(days=1)).strftime("%Y-%m-%d"), limit=-1)
    pos = ((d.get("included") or {}).get("attributes") or {})
    info, flow, level = {}, [], []
    for block in d.get("data") or []:
        info = {"qmax": ws._num(block.get("qmax")), "bank": ws._num(block.get("minBank")),
                "ground": ws._num(block.get("groundLevel"))}
        for p in block.get("data") or []:
            t = ws._ts(p.get("datetime"))
            if t is None:
                continue
            q, v = ws._num(p.get("discharge")), ws._num(p.get("value"))
            if q is not None and q >= 0:
                flow.append((t, q))
            if v is not None:
                level.append((t, v))
    return {**info, "lat": ws._num(pos.get("latitude")), "lng": ws._num(pos.get("longitude")),
            "flow": clean(flow), "level": level[-1] if level else None, "levels": level}


def _hii_stations():
    """Every HII telemetry gauge in the country with its position (they report every 10 minutes)."""
    out = []
    for fc in (ws._get("/v2/waterlevel").get("data") or {}).values():
        for f in fc.get("features", []):
            p = f.get("properties") or {}
            st = p.get("station") or {}
            if (p.get("agency") or {}).get("agencyShort") == "สสน." and st.get("latitude"):
                out.append({"id": st.get("id"), "name": st.get("station") or "",
                            "lat": ws._num(st.get("latitude")), "lng": ws._num(st.get("longitude"))})
    return out


def _level_series(sid, days):
    end = datetime.now(ws.BKK_TZ)
    d = ws._get("/data/platform/v1/public/tele_waterlevel/graph", stationId=sid,
                startDate=(end - timedelta(days=days)).strftime("%Y-%m-%d"),
                endDate=(end + timedelta(days=1)).strftime("%Y-%m-%d"), limit=-1)
    pts = {}
    for block in d.get("data") or []:
        for p in block.get("data") or []:
            t, v = ws._ts(p.get("datetime")), ws._num(p.get("value"))
            if t is not None and v is not None:
                pts[t] = v
    return sorted(pts.items())


def fit_rating(pairs, holdout=48):
    """Discharge as a quadratic of the level from (level, discharge) pairs in time order. The last
    `holdout` pairs test a fit on the rest; the curve must also rise over the whole level range seen.
    Returns {"coef", "mape", "h_min", "h_max"} with the curve refitted on every pair, or None."""
    if len(pairs) < holdout + 72:
        return None
    h = np.array([p[0] for p in pairs])
    q = np.array([p[1] for p in pairs])
    if h.max() - h.min() < 0.1:
        return None
    test = np.polyfit(h[:-holdout], q[:-holdout], 2)
    mape = float(np.mean(np.abs(np.polyval(test, h[-holdout:]) - q[-holdout:]) / np.maximum(q[-holdout:], 1))) * 100
    coef = np.polyfit(h, q, 2)
    if np.any(np.diff(np.polyval(coef, np.linspace(h.min(), h.max(), 25))) <= 0):
        return None
    return {"coef": [float(c) for c in coef], "mape": round(mape, 2), "h_min": float(h.min()), "h_max": float(h.max())}


def stage_rating(s, max_mape=15.0):
    """A gauge's own rating curve (fit_rating on its RID level and discharge, hour by hour), so a discharge
    outlook can be read as a water level against the bank; None when the fit is poor or there is too little."""
    flow = s.get("flow") or {}
    pairs = [(v, flow[t - t % HOUR]) for t, v in sorted(s.get("levels") or []) if t % HOUR == 0 and (t - t % HOUR) in flow]
    r = fit_rating(pairs)
    return r if r and r["mape"] <= max_mape else None


def level_for(rating, q):
    """The water level (m above sea) at which `rating` passes discharge q: the curve inverted by bisection,
    carried on as a straight line beyond the levels it was fitted on."""
    a, b, c = rating["coef"]
    lo, hi = rating["h_min"], rating["h_max"]

    def flow_at(h):
        if h < lo:
            return a * lo * lo + b * lo + c + (2 * a * lo + b) * (h - lo)
        if h > hi:
            return a * hi * hi + b * hi + c + (2 * a * hi + b) * (h - hi)
        return a * h * h + b * h + c

    x, y = lo - 10, hi + 10
    for _ in range(60):
        m = (x + y) / 2
        if flow_at(m) < q:
            x = m
        else:
            y = m
    return (x + y) / 2


def _ratings(loaded):
    """{code: rating} for the RID gauges with a 10-minute HII neighbour that tracks them well."""
    hii = _hii_stations()
    out = {}
    for code, *_ in STATIONS:
        s = loaded.get(code)
        if not s or not s["flow"] or s.get("lat") is None:
            continue
        near = sorted(((ws._km(s["lat"], s["lng"], h["lat"], h["lng"]), h) for h in hii if h["lat"]), key=lambda x: x[0])
        best = None
        for km, h in [(km, h) for km, h in near if km <= MATCH_KM][:2]:
            try:
                levels = dict(_level_series(h["id"], FIT_DAYS + 1))
            except Exception as e:  # noqa: BLE001 - try the next neighbour
                print(f"[NorthFlow] level {h['id']}: {e}")
                continue
            r = fit_rating([(levels[t], q) for t, q in sorted(s["flow"].items()) if t in levels])
            if r and r["mape"] <= MATCH_MAPE and (best is None or r["mape"] < best["mape"]):
                best = {**r, "station_id": h["id"], "name": h["name"], "km": round(km, 1)}
        if best:
            out[code] = best
    return out


def ten_minute(rating, levels, span=0.3):
    """10-minute discharge estimates from the HII levels; none outside the fitted level range +- span m."""
    out = []
    for t, h in levels:
        if rating["h_min"] - span <= h <= rating["h_max"] + span:
            out.append({"t": t, "h": round(h, 2), "q": round(max(0.0, float(np.polyval(rating["coef"], h))))})
    return out


def clean(points, spike_h=12, spike_frac=0.35, smooth_h=3):
    """Hourly discharge readings -> {hour: m3/s}. A reading more than 35% (+20 m3/s) off the median of
    the surrounding day is a telemetry glitch (the RID rating sometimes sends a third of the real flow)
    and is dropped; the rest is smoothed with a 7 h running median."""
    by_hour = {}
    for t, q in points:
        by_hour[t - t % HOUR] = q
    ts = sorted(by_hour)

    def median_near(src_ts, src, t, half_h):
        return float(np.median(src[bisect_left(src_ts, t - half_h * HOUR):bisect_right(src_ts, t + half_h * HOUR)]))

    vals = [by_hour[t] for t in ts]
    kept = [(t, by_hour[t]) for t in ts
            if abs(by_hour[t] - (m := median_near(ts, vals, t, spike_h))) <= spike_frac * m + 20]
    kts, kvals = [t for t, _ in kept], [q for _, q in kept]
    return {t: median_near(kts, kvals, t, smooth_h) for t in kts}


def value_at(series, t, max_gap_h=6):
    """Discharge at hour t, bridging a gap of up to max_gap_h hours on both sides."""
    if t in series:
        return series[t]
    before = next((t - k * HOUR for k in range(1, max_gap_h + 1) if t - k * HOUR in series), None)
    after = next((t + k * HOUR for k in range(1, max_gap_h + 1) if t + k * HOUR in series), None)
    if before is None or after is None:
        return None
    return series[before] + (series[after] - series[before]) * (t - before) / (after - before)


def latest(series):
    if not series:
        return None, None
    t = max(series)
    return t, series[t]


# ---------------------------------------------------------------- routing
def fit_reach(series, down, inputs, t_end, days=FIT_DAYS, step_h=24):
    """Gain and lags for one reach from its last `days` days: least squares on 24 h changes, through the
    origin, for each lag scale; the scale with the smallest residual wins. None without 48 usable hours."""
    best = None
    for scale in LAG_SCALES:
        lags = [max(1, round(lag * scale)) for _, lag in inputs]
        dx, dy = [], []
        for t in range(t_end - days * 86400, t_end - step_h * HOUR + 1, HOUR):
            y0, y1 = value_at(series[down], t), value_at(series[down], t + step_h * HOUR)
            u0 = [value_at(series[c], t - lag * HOUR) for (c, _), lag in zip(inputs, lags)]
            u1 = [value_at(series[c], t + (step_h - lag) * HOUR) for (c, _), lag in zip(inputs, lags)]
            if y0 is None or y1 is None or None in u0 or None in u1:
                continue
            dx.append(sum(u1) - sum(u0))
            dy.append(y1 - y0)
        if len(dx) < 48:
            continue
        dx, dy = np.array(dx), np.array(dy)
        gain = float(np.dot(dx, dy) / max(1e-9, float(np.dot(dx, dx))))
        gain = min(GAIN_RANGE[1], max(GAIN_RANGE[0], gain))
        rss = float(np.sum((dy - gain * dx) ** 2))
        if best is None or rss < best["rss"]:
            best = {"gain": round(gain, 3), "lags": lags, "rss": rss, "n": len(dx)}
    return best


def route(series, now, horizon_h=HORIZON_H):
    """Hourly outlook for every routed gauge from `now`. Returns {code: {"points": [(t, q)], "lead_h",
    "inputs": [(code, lag_h)], "gain"}}; a gauge without data or a fit is left out."""
    fore, out, lead = {}, {}, {}

    def val(code, t):
        if t <= now:
            v = value_at(series.get(code) or {}, t)
            return v if v is not None else latest(series.get(code) or {})[1]
        if code in fore:
            return fore[code].get(t)
        return latest(series.get(code) or {})[1]     # top gauge: held at its latest reading

    for down, inputs in REACHES:
        down_t, y0 = latest(series.get(down) or {})
        if y0 is None or now - down_t > STALE_H * HOUR:
            continue
        # An input without recent readings (Ct.19 reports discharge only in the wet season) drops out
        usable = tuple((c, lag) for c, lag in inputs
                       if (lt := latest(series.get(c) or {})[0]) is not None and now - lt <= STALE_H * HOUR)
        if not usable:
            continue
        m = fit_reach(series, down, usable, now)
        if not m:
            continue
        pairs = list(zip([c for c, _ in usable], m["lags"]))
        base = sum(val(c, now - lag * HOUR) for c, lag in pairs)
        pts = []
        for h in range(1, horizon_h + 1):
            t = now + h * HOUR
            u = [val(c, t - lag * HOUR) for c, lag in pairs]
            if None in u:
                break
            pts.append((t, max(0.0, y0 + m["gain"] * (sum(u) - base))))
        if not pts:
            continue
        fore[down] = dict(pts)
        # Hours the outlook follows measured water, along the input that carries the most of it
        main = max(pairs, key=lambda p: val(p[0], now) or 0)
        lead[down] = main[1] + lead.get(main[0], 0)
        out[down] = {"points": pts, "lead_h": lead[down], "inputs": pairs, "gain": m["gain"]}
    return out


# ---------------------------------------------------------------- outlook
def status(q, qmax):
    if q is None or not qmax:
        return None
    pct = 100 * q / qmax
    return "overflow" if pct >= OVERFLOW_PCT else "high" if pct >= HIGH_PCT else "normal"


def _worse(a, b):
    order = ["overflow", "high", "normal", "offline", None]
    return a if order.index(a) <= order.index(b) else b


def _fmt_q(q):
    return f"{q:,.0f}"


def _in_text(hours):
    return f"~{hours} ชม." if hours < 36 else f"~{hours / 24:.1f} วัน".replace(".0 ", " ")


def _official(sid):
    """Peak of the HII 7-day level forecast against the bank, or None."""
    try:
        f = ws.get_forecast(sid)
    except Exception as e:  # noqa: BLE001 - the routed outlook stands without it
        print(f"[NorthFlow] HII forecast {sid}: {e}")
        return None
    peak, bank = f.get("peak"), (f.get("levels") or {}).get("bank")
    if f.get("source") != "hii" or not peak:
        return None
    over = next((p["t"] for p in f.get("official") or [] if bank is not None and p["v"] >= bank), None)
    return {"station_id": str(sid), "peak_msl": peak["v"], "peak_t": peak["t"], "bank": bank,
            "now_msl": (f.get("latest") or {}).get("v"), "over_bank_t": over}


def _build():
    loaded, errors = {}, {}

    def run(code, sid):
        try:
            loaded[code] = ws._cache.get(f"north_rid:{sid}", RID_TTL, lambda: _load_station(sid))[0]
        except Exception as e:  # noqa: BLE001 - one gauge down leaves the others
            errors[code] = str(e)[:160]

    threads = [threading.Thread(target=run, args=(code, sid), daemon=True) for code, sid, *_ in STATIONS]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    if not loaded:
        raise RuntimeError(next(iter(errors.values()), "thaiwater unreachable"))

    series = {c: s["flow"] for c, s in loaded.items()}
    stamps = [latest(s)[0] for s in series.values() if s]
    if not stamps:
        raise RuntimeError("no discharge readings")
    now = max(stamps)
    routed = route(series, now)
    official = {c: _official(sid) for c, sid in OFFICIAL.items()}
    try:
        ratings = ws._cache.get("north_rating", RATING_TTL, lambda: _ratings(loaded))[0]
    except Exception as e:  # noqa: BLE001 - the hourly RID figures stand without it
        print(f"[NorthFlow] ratings: {e}")
        ratings = {}
    tens = {}

    def run10(code, rating):
        try:
            levels = ws._cache.get(f"north_level:{rating['station_id']}", FLOW_TTL,
                                   lambda: _level_series(rating["station_id"], 2))[0]
            tens[code] = [p for p in ten_minute(rating, levels) if p["t"] > time.time() - TEN_MIN_H * HOUR]
        except Exception as e:  # noqa: BLE001 - that gauge keeps its hourly figure only
            print(f"[NorthFlow] 10-min {code}: {e}")

    threads = [threading.Thread(target=run10, args=kv, daemon=True) for kv in ratings.items()]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    # ETA from Nakhon Sawan: the lags along the main stem
    from_c2 = {"C.2": 0}
    for down, _ in REACHES:
        for c, lag in (routed.get(down) or {}).get("inputs", ()):
            if c in from_c2:
                from_c2[down] = from_c2[c] + lag

    stations = []
    for code, sid, name, province, river in STATIONS:
        s = loaded.get(code)
        if not s:
            stations.append({"code": code, "name": name, "province": province, "river": river, "status": "offline"})
            continue
        t, q = latest(s["flow"])
        fresh = t is not None and now - t <= STALE_H * HOUR
        qmax, bank = s.get("qmax"), s.get("bank")
        lv_t, lv = s["level"] or (None, None)
        lv_fresh = lv_t is not None and now - lv_t <= STALE_H * HOUR
        below_bank = round(bank - lv, 2) if lv_fresh and lv is not None and bank is not None else None
        level_pct = None
        if below_bank is not None and s.get("ground") is not None and bank > s["ground"]:
            level_pct = round(100 * (lv - s["ground"]) / (bank - s["ground"]), 1)
        q24 = value_at(s["flow"], t - 24 * HOUR) if fresh else None
        st = status(q, qmax) if fresh else None
        if below_bank is not None:
            st = _worse(st, "overflow" if below_bank <= 0 else "high" if below_bank <= 0.5 else "normal")
        r = routed.get(code)
        fc, peak = None, None
        if r and fresh:
            fc = [{"t": pt, "q": round(pq)} for pt, pq in r["points"]]
            best = max(r["points"], key=lambda p: p[1])
            peak = {"t": best[0], "q": round(best[1]), "in_h": (best[0] - now) // HOUR,
                    "pct": round(100 * best[1] / qmax, 1) if qmax else None, "status": status(best[1], qmax)}
            for key, pct in (("high_at", HIGH_PCT), ("overflow_at", OVERFLOW_PCT)):
                if qmax and q < qmax * pct / 100:
                    peak[key] = next((pt for pt, pq in r["points"] if pq >= qmax * pct / 100), None)
        stations.append({
            "code": code, "station_id": str(sid), "name": name, "province": province, "river": river,
            "lat": s.get("lat"), "lng": s.get("lng"),
            "q": round(q) if fresh else None, "ts": t, "qmax": qmax,
            "pct": round(100 * q / qmax, 1) if fresh and qmax else None,
            "change_24h": round(q - q24) if q24 is not None else None,
            "msl": lv if lv_fresh else None, "bank": bank, "ground": s.get("ground"), "below_bank": below_bank, "level_pct": level_pct,
            "stage": stage_rating(s),
            "status": st or "offline",
            "history": [{"t": ht, "q": round(hq)} for ht, hq in sorted(s["flow"].items()) if ht > now - HISTORY_H * HOUR],
            "forecast": fc, "peak": peak,
            "lead_h": r["lead_h"] if r and fc else None,
            "inputs": [{"code": c, "lag_h": lag} for c, lag in r["inputs"]] if r else [],
            "gain": r["gain"] if r else None,
            "from_c2_h": from_c2.get(code),
            "official": official.get(code),
            **_ten_fields(tens.get(code), ratings.get(code)),
        })

    try:
        ntw_dams = ws._cache.get("ntw", ws.NTW_TTL, ws._load_ntw)[0].get("dams") or []
    except Exception as e:  # noqa: BLE001 - dams are context only
        print(f"[NorthFlow] dams: {e}")
        ntw_dams = []
    dams = [{**d, "river": DAMS[d["name"]],
             "released_m3s": round(d["released"] * 1e6 / 86400) if d.get("released") is not None else None,
             "inflow_m3s": round(d["inflow"] * 1e6 / 86400) if d.get("inflow") is not None else None}
            for d in ntw_dams if d.get("name") in DAMS]

    bangkok = _official(BANGKOK_STATION)
    if bangkok:
        bangkok["lat"], bangkok["lng"] = BANGKOK_POS
    alerts = _alerts(stations, now, bangkok)
    return {
        "updated_at": int(time.time()), "data_time": now, "horizon_h": HORIZON_H,
        "stations": stations, "dams": dams, "alerts": alerts, "headline": _headline(stations, alerts),
        "bangkok": bangkok, "edges": [{"from": a, "to": z} for a, z in FLOW_EDGES], "errors": errors,
    }


def _ten_fields(pts, rating):
    """The 10-minute estimate for one gauge: the series, the latest value with its 10-min and 1 h change."""
    if not pts or not rating:
        return {"ten_min": None, "latest10": None, "rating": None}
    last = pts[-1]
    by = {p["t"]: p["q"] for p in pts}
    q10, q60 = by.get(last["t"] - 600), by.get(last["t"] - 3600)
    return {
        "ten_min": pts,
        "latest10": {"t": last["t"], "q": last["q"], "h": last["h"],
                     "change_10m": last["q"] - q10 if q10 is not None else None,
                     "change_1h": last["q"] - q60 if q60 is not None else None},
        "rating": {"station_id": str(rating["station_id"]), "name": rating["name"], "km": rating["km"], "mape": rating["mape"]},
    }


def _label(s):
    return f"{s['province']} ({s['code']})"


TH_MONTHS = ("", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.")
# Said next to a gauge's outlook: the Chao Phraya Dam passes what RID decides, not what arrives
NOTES = {"C.13": "ปริมาณท้ายเขื่อนขึ้นกับการระบายของกรมชลประทาน"}


def _day(ts):
    d = datetime.fromtimestamp(ts, ws.BKK_TZ)
    return f"{d.day} {TH_MONTHS[d.month]}"


def _alerts(stations, now, bangkok=None):
    """Plain-Thai warning lines, one per gauge, worst first: gauges over or near the bank now, gauges the
    outlook takes there, flood waves (fast 24 h rises) still upstream, and HII level forecasts over the bank."""
    out = []
    for s in stations:
        if s["status"] == "offline":
            continue
        where = f"{RIVERS[s['river']]} {_label(s)}"
        pk = s.get("peak") or {}
        bb = s.get("below_bank")
        now_q = (f" {_fmt_q(s['q'])} ลบ.ม./วินาที ({s['pct']:.0f}% ของความจุลำน้ำ)" if s.get("pct") is not None
                 else "" if bb is None else f" ต่ำกว่าตลิ่ง {bb:.2f} ม." if bb > 0 else f" สูงกว่าตลิ่ง {-bb:.2f} ม.")
        then = (f" คาดสูงสุด {_fmt_q(pk['q'])} ลบ.ม./วินาที ({pk['pct']:.0f}%) ในอีก {_in_text(pk['in_h'])}"
                if pk.get("pct") is not None and pk["q"] > (s["q"] or 0) * 1.03 else "")
        ch = s.get("change_24h")
        rise = ch is not None and s["q"] and ch >= RISE_M3S and ch >= RISE_PCT / 100 * (s["q"] - ch)
        if s["status"] == "overflow":
            tone, text = "red", f"{where} ล้นตลิ่งแล้ว{now_q}{then}"
        elif pk.get("overflow_at"):
            tone, text = "red", f"{where} คาดว่าจะเกินความจุลำน้ำในอีก {_in_text((pk['overflow_at'] - now) // HOUR)}{then}"
        elif pk.get("high_at"):
            tone, text = "yellow", f"{where} คาดว่าน้ำมากในอีก {_in_text((pk['high_at'] - now) // HOUR)}{then}"
        elif s["status"] == "high":
            tone, text = "yellow", f"{where} น้ำมาก{now_q}{then}"
        elif rise:
            tone, text = "yellow", f"{where}{now_q}"
        else:
            continue
        if rise:
            text += f" · น้ำขึ้นเร็ว +{_fmt_q(ch)} ลบ.ม./วินาที ใน 24 ชม."
        if then and s["code"] in NOTES:
            text += f" ({NOTES[s['code']]})"
        out.append({"code": s["code"], "tone": tone, "text": text})
    # HII's own level forecasts over the bank (Nakhon Sawan, Ayutthaya, Pa Sak, Nonthaburi)
    by = {s["code"]: s for s in stations}
    for code, o in [(c, (by.get(c) or {}).get("official")) for c in OFFICIAL] + [("BKK", bangkok)]:
        if not o or o.get("over_bank_t") is None or o.get("bank") is None:
            continue
        st = ws.OFFICIAL_FORECAST_STATIONS.get(int(o["station_id"])) or {}
        over = ("สูงกว่าตลิ่งแล้ว" if (o.get("now_msl") or -99) >= o["bank"]
                else f"สูงกว่าตลิ่งตั้งแต่ {_day(o['over_bank_t'])}")
        out.append({"code": code, "tone": "red",
                    "text": f"สสน. คาดระดับน้ำที่{st.get('name', '')} {st.get('province', '')} {over}"
                            f" สูงสุด {o['peak_msl']:.2f} ม.รทก. (ตลิ่ง {o['bank']:.2f}) ราว {_day(o['peak_t'])}"})
    rank = {"red": 0, "yellow": 1}
    order = {c: i for i, c in enumerate([s["code"] for s in stations] + ["BKK"])}
    out.sort(key=lambda a: (rank[a["tone"]], order[a["code"]]))
    return out


def _province(by, alert):
    return "นนทบุรี-กรุงเทพฯ" if alert["code"] == "BKK" else by[alert["code"]]["province"]


def _headline(stations, alerts):
    by = {s["code"]: s for s in stations}
    c2 = by.get("C.2") or {}
    parts = []
    if c2.get("q") is not None:
        ch = c2.get("change_24h")
        trend = f" ({'+' if ch >= 0 else ''}{_fmt_q(ch)} ใน 24 ชม.)" if ch is not None else ""
        parts.append(f"น้ำเหนือไหลผ่านนครสวรรค์ (C.2) {_fmt_q(c2['q'])} ลบ.ม./วินาที{trend}")
        pk = c2.get("peak")
        if pk and pk["q"] > c2["q"] * 1.03:
            parts.append(f"คาดสูงสุด {_fmt_q(pk['q'])} ในอีก {_in_text(pk['in_h'])}")
    red = [a for a in alerts if a["tone"] == "red"]
    if red:
        tone, label = "red", "เตือนภัย"
        parts.append("ล้นตลิ่ง/คาดล้น: " + ", ".join(dict.fromkeys(_province(by, a) for a in red)))
    elif alerts:
        tone, label = "yellow", "เฝ้าระวัง"
        parts.append("น้ำมาก: " + ", ".join(dict.fromkeys(_province(by, a) for a in alerts)))
    else:
        tone, label = "green", "ปกติ"
        parts.append("แม่น้ำสายหลักจากภาคเหนือถึงอยุธยายังอยู่ในความจุลำน้ำ")
    return {"tone": tone, "label": label, "text": " · ".join(parts)}


def get_outlook():
    data, stale = ws._cache.get("north_flow", FLOW_TTL, _build)
    return {**data, "stale": stale}


def brief():
    """Short form for the water AI analyst and the chat context: no hourly series, and only the gauges
    with an outlook or above normal."""
    d = get_outlook()
    keep = ("code", "name", "province", "river", "q", "pct", "change_24h", "below_bank", "status", "from_c2_h")
    rows = []
    for s in d["stations"]:
        if not s.get("peak") and s["status"] not in ("overflow", "high"):
            continue
        row = {k: s.get(k) for k in keep if s.get(k) is not None}
        if s.get("peak"):
            row["peak"] = {k: s["peak"][k] for k in ("q", "pct", "in_h") if s["peak"].get(k) is not None}
        if s.get("latest10"):
            row["now_10min"] = {k: s["latest10"][k] for k in ("q", "change_1h")}
        rows.append(row)
    return {"headline": d["headline"]["text"], "alerts": [a["text"] for a in d["alerts"]], "stations": rows,
            "dams": [{k: x.get(k) for k in ("name", "storage_pct", "inflow", "released")} for x in d["dams"]],
            "bangkok_hii": d.get("bangkok"), "stale": d["stale"]}


def start():
    """Refresh every 10 minutes whether or not anyone has the page open, so the AI works on fresh figures."""
    def loop():
        while True:
            try:
                get_outlook()
            except Exception as e:  # noqa: BLE001 - keep the timer alive
                print(f"[NorthFlow] refresh failed: {e}")
            time.sleep(FLOW_TTL)
    threading.Thread(target=loop, daemon=True, name="NorthFlow").start()
