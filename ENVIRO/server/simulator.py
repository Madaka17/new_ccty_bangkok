"""Background sensor-fleet simulator.

This stands in for the real IoT ingestion pipeline: in production, this
module would be replaced by an MQTT subscriber receiving samples from real
ENVIRO Node One devices. Everything *downstream* of a raw sample --
STA/LTA detection, PGA estimation, multi-node corroboration, event creation,
audit logging, WebSocket broadcast -- is real logic that would not need to
change.
"""
import math
import time
import threading
import uuid
from collections import deque
from datetime import datetime, timezone

from . import db as dbmod
from . import signal as dsp
from . import telegram_notify
from . import world_quakes
from .geo import haversine_km
from .seismology import estimate_magnitude, magnitude_amp_multiplier, mmi_roman, pga_at_distance, predict_mmi

BUFFER_SECONDS = 20
BUFFER_LEN = int(BUFFER_SECONDS * dsp.SAMPLE_RATE_HZ)
VS_KM_S = 3.8  # S-wave speed used for propagation delay, matches the situation view
VP_KM_S = 6.5  # P-wave speed, used for the "wave arrival" countdown
DEFAULT_FOCUS_STATION = "CNX-118"  # เชียงใหม่ -- see server/db.py STATIONS (7-station network)
SHAKE_DURATION_S = 9.0

# Per explicit request: a triggered demo must show a result within ~10s of
# pressing "จำลองแผ่นดินไหว", even at real speed (1x). Genuine STA/LTA
# detection still fires first if it naturally crosses threshold sooner (a
# nearby epicenter, or any speed_multiplier > 1 compresses real wave-travel
# time proportionally) -- this is only a ceiling for the case where the
# focus station (the nearest of only 7 demo stations, which can genuinely be
# 100+ km from a given epicenter) would otherwise take a realistic-but-long
# time (tens of seconds to minutes) to feel real-speed shaking. See tick()
# and _declare_event()'s wave_reached_focus branch.
DETECT_FALLBACK_SEC = 8.0

# The alert *level* is gated on predicted intensity AT THIS REFERENCE STATION,
# not on epicenter magnitude directly -- USGS's own guidance is explicit that
# magnitude and intensity are different things, and one event produces very
# different shaking in different places depending on distance/depth/site
# conditions. Until the app is location-aware per viewer, this fixed
# reference point ("you are here" in the situation view) stands in for "the
# user's location". See server/db.py LEVELS for the full citation.
REFERENCE_STATION = "BKK-201"

# Multi-node corroboration no longer gates the *alert level* -- it only drives
# a separate *confidence* tier: more independent stations agreeing means
# higher confidence in an already-classified severity, which is how real EEW
# networks actually use station counts.
# Rescaled for the 7-station network (server/db.py STATIONS) -- tier 5 now
# needs all 7 stations corroborating rather than an unreachable 12.
NODES_MIN = {1: 1, 2: 2, 3: 3, 4: 5, 5: 7}
CONFIDENCE_LABELS = {1: "ต่ำ", 2: "ปานกลาง", 3: "สูง", 4: "สูงมาก", 5: "ยืนยันแล้ว"}


# A simplified, explicitly-illustrative tsunami-risk heuristic -- NOT an
# official warning system. Thailand's one real tsunami precedent (2004) came
# from a shallow, large subduction-zone rupture under the Andaman Sea; this
# box roughly covers that same offshore area west of the Andaman coast. Any
# large, shallow event whose epicenter falls inside it is flagged so the UI
# can show a separate, overlaid tsunami notice -- real advisories would come
# from PTWC/TMD directly, never be computed client-side like this.
ANDAMAN_TSUNAMI_BBOX = {"minlat": 5.0, "maxlat": 15.0, "minlng": 90.0, "maxlng": 97.5}
TSUNAMI_MIN_MAGNITUDE = 7.0
TSUNAMI_MAX_DEPTH_KM = 60.0

DEFAULT_QUAKE = {
    "lat": 20.15, "lng": 99.85, "place": "อ.แม่จัน จ.เชียงราย",
    "fault": "รอยเลื่อนแม่จัน", "region": "เชียงราย",
    "magnitude": 4.8, "depth": 8, "start_s": 20.0, "speed_multiplier": 1.0,
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


class Simulator:
    def __init__(self, broadcast_fn):
        self.broadcast = broadcast_fn
        self.lock = threading.RLock()
        self.t = 0
        self.stations = {}  # id -> {region,lat,lng,buffers:{ew,ns,ud}}
        self.active_event = None
        self.triggered = False
        self.stalta_current = 0.0
        self.quake = dict(DEFAULT_QUAKE)
        self.focus_station = DEFAULT_FOCUS_STATION
        self._load_stations()
        self._load_detector_config()
        self.station_triggered = {sid: False for sid in self.stations}

    def _nearest_station(self, lat, lng):
        return min(self.stations, key=lambda sid: haversine_km(self.stations[sid]["lat"], self.stations[sid]["lng"], lat, lng))

    def nearest_stations_to(self, station_id, n=6):
        base = self.stations[station_id]
        ranked = sorted(
            self.stations.keys(),
            key=lambda sid: haversine_km(base["lat"], base["lng"], self.stations[sid]["lat"], self.stations[sid]["lng"]),
        )
        return ranked[:n]

    def _load_stations(self):
        conn = dbmod.get_conn()
        rows = conn.execute("SELECT id, region, lat, lng FROM stations").fetchall()
        conn.close()
        for r in rows:
            self.stations[r["id"]] = {
                "region": r["region"], "lat": r["lat"], "lng": r["lng"],
                "buffers": {
                    # left empty (not zero-padded) so STA/LTA's warm-up guard -- which
                    # checks len(buffer) -- is meaningful instead of always seeing a
                    # full-length, partly-fake array of leading zeros.
                    "ew": deque(maxlen=BUFFER_LEN),
                    "ns": deque(maxlen=BUFFER_LEN),
                    "ud": deque(maxlen=BUFFER_LEN),
                },
            }

    def _load_detector_config(self):
        conn = dbmod.get_conn()
        row = conn.execute("SELECT * FROM detector_config WHERE id=1").fetchone()
        conn.close()
        self.stalta_threshold = row["stalta_threshold"]
        self.pga_calibration = row["pga_calibration"]

    def reload_detector_config(self):
        with self.lock:
            self._load_detector_config()

    def dist_km(self, station):
        return haversine_km(station["lat"], station["lng"], self.quake["lat"], self.quake["lng"])

    def dist_to_reference_km(self):
        ref = self.stations[REFERENCE_STATION]
        return haversine_km(ref["lat"], ref["lng"], self.quake["lat"], self.quake["lng"])

    def _assess_tsunami_risk(self, magnitude, depth_km, lat, lng):
        box = ANDAMAN_TSUNAMI_BBOX
        in_box = box["minlat"] <= lat <= box["maxlat"] and box["minlng"] <= lng <= box["maxlng"]
        return bool(in_box and magnitude >= TSUNAMI_MIN_MAGNITUDE and depth_km <= TSUNAMI_MAX_DEPTH_KM)

    # ---------------------------------------------------------------- signal
    # Frequencies (Hz) and relative weights spreading the synthetic shake's
    # energy across the ~1-10 Hz band real local/regional earthquakes occupy,
    # instead of one or two pure tones. A pure-tone burst is spectrally
    # "peaky" in exactly the way real machinery/rotating equipment is -- so a
    # frequency-content classifier fed a too-tonal fake earthquake would
    # (correctly, given that input!) call it machinery. Real seismic energy
    # is spread across a band, so the simulated signal needs to be too.
    _SHAKE_COMPONENTS = [(1.4, 0.5, 2.4), (2.2, 1.0, 0.0), (3.6, 0.8, 1.3), (5.1, 0.6, 0.7), (7.3, 0.4, 1.9)]
    _SHAKE_NORM = sum(w for _, w, _ in _SHAKE_COMPONENTS)

    def _sample(self, dist_km, t_sec, phase):
        noise = (self._rand() - 0.5) * 0.10
        vs_eff = VS_KM_S * self.quake.get("speed_multiplier", 1.0)
        arrival = self.quake["start_s"] + dist_km / vs_eff
        if t_sec >= arrival:
            local = t_sec - arrival
            if local < SHAKE_DURATION_S:
                atten = 1.0 / (1.0 + dist_km / 55.0)
                rise = SHAKE_DURATION_S * 0.25
                envelope = math.sin(math.pi * min(1.0, local / rise) / 2) if local < rise \
                    else math.exp(-(local - rise) * 0.75)
                shake = sum(
                    w * math.sin(local * 2 * math.pi * f + phase * ph)
                    for f, w, ph in self._SHAKE_COMPONENTS
                ) / self._SHAKE_NORM
                amp = magnitude_amp_multiplier(self.quake["magnitude"])
                return noise + atten * envelope * shake * amp
        return noise

    _seed = 12345

    def _rand(self):
        # tiny deterministic LCG so repeated runs look stable without extra deps
        self._seed = (1103515245 * self._seed + 12345) & 0x7FFFFFFF
        return self._seed / 0x7FFFFFFF

    # ---------------------------------------------------------------- tick
    def tick(self):
        with self.lock:
            self.t += 1
            t_sec = self.t / dsp.SAMPLE_RATE_HZ
            for sid, st in self.stations.items():
                d = self.dist_km(st)
                st["buffers"]["ew"].append(self._sample(d, t_sec, 0.0))
                st["buffers"]["ns"].append(self._sample(d, t_sec, 1.1))
                st["buffers"]["ud"].append(self._sample(d, t_sec, 2.3))
                if not self.station_triggered[sid]:
                    recent_peak = dsp.peak_abs(list(st["buffers"]["ew"]), n=int(dsp.SAMPLE_RATE_HZ))
                    if recent_peak * self.pga_calibration > 0.6:
                        self.station_triggered[sid] = True

            focus = self.stations[self.focus_station]["buffers"]["ew"]
            self.stalta_current = dsp.sta_lta(list(focus))

            if not self.triggered and t_sec > self.quake["start_s"] and (
                self.stalta_current > self.stalta_threshold
                or t_sec > self.quake["start_s"] + DETECT_FALLBACK_SEC  # see DETECT_FALLBACK_SEC
            ):
                self._declare_event(t_sec)
            elif self.triggered and self.active_event and not self.active_event["fully_confirmed"] and self.t % 20 == 0:
                self._recheck_confidence()

    def trigger_manual_quake(self, lat, lng, magnitude, place, fault, region, depth=8, speed_multiplier=1.0):
        """Schedules a brand-new simulated earthquake a couple of seconds from now,
        resetting detection state so the full real pipeline (STA/LTA -> PGA ->
        multi-node corroboration -> level classification) runs again from scratch.

        `speed_multiplier` scales the wave-propagation speed used for THIS event
        only (default 1.0 = real Vp/Vs). It exists purely for the "full ladder"
        demo trigger: reaching level 5 needs 12/15 stations to feel the wave,
        which at real S-wave speed can take minutes for stations on the far side
        of the country -- physically correct, but too slow to watch live. The
        multiplier is stored on the event and returned to the frontend so the
        countdown, ripple animation, and a visible "sped up" badge all stay
        consistent with each other rather than silently lying about elapsed time.
        """
        with self.lock:
            t_sec_now = self.t / dsp.SAMPLE_RATE_HZ
            # Never schedule a burst before the focus station's STA/LTA buffer
            # has a full 15s of pre-event baseline to compare against (see the
            # DEFAULT_QUAKE start_s=20.0 comment below) -- otherwise, if this
            # is triggered within seconds of server boot, the trigger check
            # would never see a clean baseline and could silently never fire.
            start_s = max(t_sec_now + 2.0, 17.0)
            self.quake = {
                "lat": lat, "lng": lng, "place": place, "fault": fault, "region": region,
                "magnitude": magnitude, "depth": depth, "start_s": start_s,
                "speed_multiplier": speed_multiplier,
            }
            self.focus_station = self._nearest_station(lat, lng)
            self.triggered = False
            self.active_event = None
            self.station_triggered = {sid: False for sid in self.stations}
            vs_eff = VS_KM_S * speed_multiplier
            eta_s = round(min(self.dist_km(st) for st in self.stations.values()) / vs_eff + 2.0, 1)
        self.broadcast({"type": "quake-scheduled", "quake": self.quake, "eta_s": eta_s})
        return eta_s

    def clear_active_event(self):
        """Manually stops the currently running/scheduled simulated quake and
        resets detection state back to idle -- the counterpart to
        trigger_manual_quake(), for the topbar "จำลองแผ่นดินไหว" toggle button.
        Does not touch real detections (there is only ever one active_event,
        real or simulated, but this is only ever called from the demo-trigger
        UI). Returns False if nothing was actually running in memory (the DB
        suppression below still runs regardless, see why)."""
        with self.lock:
            was_active = self.active_event is not None or self.triggered
            self.active_event = None
            self.triggered = False
            self.quake = dict(DEFAULT_QUAKE)
            self.focus_station = DEFAULT_FOCUS_STATION
            self.station_triggered = {sid: False for sid in self.stations}
        # Clearing self.active_event alone is NOT enough: routes/situation.py
        # falls back to "the latest events row" whenever there's no matching
        # in-memory active_event, and that fallback has no notion of
        # "explicitly stopped" -- only felt-radius staleness, which for a
        # real-speed (1x) moderate/large event can take many MINUTES to
        # naturally expire. Without this, pressing "stop" looks like it does
        # nothing: the event keeps being reported as current until that
        # timer runs out on its own. Reusing is_test (already excluded from
        # that query) rather than a schema migration for a new column.
        conn = dbmod.get_conn()
        conn.execute(
            "UPDATE events SET is_test=1 WHERE id = "
            "(SELECT id FROM events WHERE is_test=0 ORDER BY ts DESC LIMIT 1)"
        )
        conn.commit()
        conn.close()
        self.broadcast({"type": "event-cleared"})
        return was_active

    def _corroborating_count(self):
        # Sticky: a station that has ever crossed the trigger threshold during this
        # incident stays counted, even after its own shaking has decayed back to
        # noise -- matching how real EEW networks latch a station's trigger state.
        return sum(1 for v in self.station_triggered.values() if v)

    @staticmethod
    def _confidence_tier(count):
        """Highest confidence tier whose multi-node requirement is met by `count`
        independently-corroborating stations. This no longer influences the
        alert *level* -- only how confident the system is willing to say it is."""
        best = 1
        for tier, need in NODES_MIN.items():
            if count >= need:
                best = max(best, tier)
        return best

    @staticmethod
    def _external_corroboration(lat, lng, ts_iso, magnitude):
        """Cross-check against the live USGS/EMSC/GEOFON/TMD feed (see
        world_quakes.find_corroborating_quake) -- an independent real network
        agreeing on this same event is at least as strong evidence as another
        local station, so it raises the confidence tier the same way more
        stations would, on top of (not instead of) the station-count tier."""
        try:
            ts_ms = datetime.fromisoformat(ts_iso).timestamp() * 1000
        except Exception:
            return None
        return world_quakes.find_corroborating_quake(lat, lng, ts_ms, magnitude)

    @staticmethod
    def _apply_external_boost(tier, external_match):
        """+1 confidence tier (capped at the tier ceiling) when an external
        network corroborates -- a bump, not an override, so a real published
        match can't by itself claim "ยืนยันแล้ว" (tier 5) over a barely-
        detected local event, but it does count for something real."""
        if not external_match:
            return tier
        return min(max(NODES_MIN.keys()), tier + 1)

    def _level_row(self, conn, lv):
        return conn.execute("SELECT lv,name,message,channels,siren,color FROM levels WHERE lv=?", (lv,)).fetchone()

    def _level_for_mmi(self, conn, mmi):
        row = conn.execute(
            "SELECT lv,name,message,channels,siren,color FROM levels "
            "WHERE mmi_min <= ? AND (mmi_max IS NULL OR ? < mmi_max) ORDER BY lv DESC LIMIT 1",
            (mmi, mmi),
        ).fetchone()
        return row or self._level_row(conn, 1)

    def _declare_event(self, t_sec):
        self.triggered = True
        q = self.quake
        dist_km = self.dist_km(self.stations[self.focus_station])
        vs_eff = VS_KM_S * q.get("speed_multiplier", 1.0)
        wave_reached_focus = t_sec >= q["start_s"] + dist_km / vs_eff
        if wave_reached_focus:
            peak = dsp.peak_abs(list(self.stations[self.focus_station]["buffers"]["ew"]), n=int(dsp.SAMPLE_RATE_HZ * 4))
            pga_gal = round(peak * self.pga_calibration, 2)
            mag_est = estimate_magnitude(pga_gal, dist_km, self.pga_calibration)
        else:
            # DETECT_FALLBACK_SEC (see tick()) forced this declare before the
            # simulated wave has actually reached the focus station's own
            # buffer -- reading that buffer right now would be pure
            # background noise, giving a garbage near-zero magnitude. This is
            # a demo-responsiveness measure (guarantees a real-speed trigger
            # with a naturally far focus station -- only 7 stations total --
            # still shows a sensible event within ~10s of the button press),
            # not a claim of real early detection, so fall back to the
            # scenario's own true magnitude and the matching real PGA at this
            # distance (same cited formula _recheck_confidence already uses)
            # instead of estimating from a buffer with nothing in it yet.
            mag_est = q["magnitude"]
            pga_gal = round(pga_at_distance(mag_est, dist_km, q["depth"]), 2)
        corroborating = self._corroborating_count()
        confidence_tier = self._confidence_tier(corroborating)

        # The alert LEVEL is gated on predicted intensity at the reference
        # location, not on magnitude/PGA at the epicenter/focus station --
        # see REFERENCE_STATION and server/db.py LEVELS.
        ref_dist_km = self.dist_to_reference_km()
        predicted_mmi = predict_mmi(mag_est, ref_dist_km, q["depth"])
        tsunami_risk = self._assess_tsunami_risk(mag_est, q["depth"], q["lat"], q["lng"])

        conn = dbmod.get_conn()
        level_row = self._level_for_mmi(conn, predicted_mmi)

        event_id = "ENV-" + datetime.now().strftime("%Y%m%d-%H%M") + "-" + uuid.uuid4().hex[:4].upper()
        ts = now_iso()
        external_match = self._external_corroboration(q["lat"], q["lng"], ts, mag_est)
        confidence_tier = self._apply_external_boost(confidence_tier, external_match)
        # Intensity AT THE EPICENTER itself (dist=0) -- a separate number (and
        # separate severity-name lookup) from the reference-location
        # prediction that actually drives the alert level, shown only for
        # context ("how strong was it right at the source").
        mmi_epicenter_val = predict_mmi(mag_est, 0.0, q["depth"])
        epicenter_level_row = self._level_for_mmi(conn, mmi_epicenter_val)
        mmi_epicenter = f"{mmi_roman(mmi_epicenter_val)} — {epicenter_level_row['name']}"

        conn.execute(
            "INSERT INTO events(id,ts,magnitude,depth,place,fault,lat,lng,mmi_epicenter,predicted_mmi,tsunami_risk,"
            "stations_triggered,level,pga_gal,is_test,speed_multiplier) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?)",
            (event_id, ts, q["magnitude"], q["depth"], q["place"], q["fault"],
             q["lat"], q["lng"], mmi_epicenter, predicted_mmi, int(tsunami_risk),
             corroborating, level_row["lv"], pga_gal, q.get("speed_multiplier", 1.0)),
        )
        conn.execute(
            "INSERT INTO audit_log(ts, username, action) VALUES (?, 'system', ?)",
            (ts, f"ตรวจพบเหตุการณ์ {event_id} จากสถานี {self.focus_station} — ประเมินขนาด M{mag_est} "
                 f"(PGA ประมาณ {pga_gal} Gal) ที่ตำแหน่งอ้างอิงคาดว่าจะรู้สึกได้ MMI {mmi_roman(predicted_mmi)} "
                 f"จัดเป็นระดับ {level_row['lv']} ({level_row['name']}) "
                 f"ความเชื่อมั่น{CONFIDENCE_LABELS[confidence_tier]} ({corroborating} สถานียืนยันร่วม)"
                 + (f" · ยืนยันตรงกับ {external_match['source']} ภายนอก (~{external_match['dist_km']} กม.)" if external_match else "")
                 + (" — มีความเสี่ยงสึนามิ (เบื้องต้น)" if tsunami_risk else "")),
        )
        conn.commit()
        conn.close()

        self.active_event = {
            "id": event_id, "ts": ts, "magnitude": q["magnitude"], "depth": q["depth"],
            "place": q["place"], "fault": q["fault"],
            "lat": q["lat"], "lng": q["lng"], "mmi_epicenter": mmi_epicenter,
            "predicted_mmi": predicted_mmi, "predicted_mmi_roman": mmi_roman(predicted_mmi),
            "tsunami_risk": tsunami_risk,
            "stations_triggered": corroborating, "level": level_row["lv"],
            "level_name": level_row["name"], "pga_gal": pga_gal,
            "magnitude_estimate": mag_est,
            "message": level_row["message"], "channels": level_row["channels"],
            "siren": level_row["siren"], "color": level_row["color"],
            "confidence_tier": confidence_tier, "confidence_label": CONFIDENCE_LABELS[confidence_tier],
            "fully_confirmed": confidence_tier >= 5,
            "external_match": external_match,
            "speed_multiplier": q.get("speed_multiplier", 1.0),
            "focus_station": self.focus_station,
        }
        self.broadcast({"type": "alert", "event": self.active_event})
        telegram_notify.notify_alert(self.active_event, is_new=True)

    def _recheck_confidence(self):
        ev = self.active_event
        corroborating = self._corroborating_count()
        ev["stations_triggered"] = corroborating
        new_tier = self._confidence_tier(corroborating)
        # Re-check the external feed every time too -- the live USGS/EMSC/
        # GEOFON/TMD cache refreshes independently of this simulator (see
        # world_quakes.POLL_SECONDS), and the magnitude estimate used for the
        # match may itself have refined since _declare_event, so a match that
        # wasn't there yet can appear later in the same incident.
        external_match = self._external_corroboration(ev["lat"], ev["lng"], ev["ts"], ev.get("magnitude_estimate"))
        external_changed = external_match != ev.get("external_match")
        new_tier = self._apply_external_boost(new_tier, external_match)

        # The magnitude estimate can also refine as a longer window of the
        # waveform becomes available -- exactly like a real EEW system revising
        # its estimate as more data arrives -- and can shift the level if that
        # refinement crosses a TMD tier boundary. This is now independent of
        # station count: more stations only raises *confidence*, not severity.
        level_changed = False
        peak = dsp.peak_abs(list(self.stations[self.focus_station]["buffers"]["ew"]), n=int(dsp.SAMPLE_RATE_HZ * 8))
        dist_km = self.dist_km(self.stations[self.focus_station])
        pga_gal = round(peak * self.pga_calibration, 2)
        if pga_gal > ev["pga_gal"]:
            mag_est = estimate_magnitude(pga_gal, dist_km, self.pga_calibration)
            ref_dist_km = self.dist_to_reference_km()
            predicted_mmi = predict_mmi(mag_est, ref_dist_km, ev["depth"])
            conn0 = dbmod.get_conn()
            level_row0 = self._level_for_mmi(conn0, predicted_mmi)
            conn0.close()
            ev["pga_gal"] = pga_gal
            ev["magnitude_estimate"] = mag_est
            ev["predicted_mmi"] = predicted_mmi
            ev["predicted_mmi_roman"] = mmi_roman(predicted_mmi)
            # Tsunami risk is assessed at declare time using whatever the
            # very first magnitude estimate happened to be -- which, like the
            # level itself, is often a real underestimate before enough of
            # the waveform has been seen (the same reason the level can climb
            # here too). Re-assess with the refined estimate so a genuinely
            # huge, shallow, Andaman-area event doesn't stay flagged
            # risk-free just because its initial read was too low to qualify.
            tsunami_changed = False
            if not ev["tsunami_risk"]:
                new_tsunami_risk = self._assess_tsunami_risk(mag_est, ev["depth"], ev["lat"], ev["lng"])
                if new_tsunami_risk:
                    ev["tsunami_risk"] = True
                    tsunami_changed = True
            if level_row0["lv"] != ev["level"]:
                level_changed = True
                ev.update({
                    "level": level_row0["lv"], "level_name": level_row0["name"], "message": level_row0["message"],
                    "channels": level_row0["channels"], "siren": level_row0["siren"], "color": level_row0["color"],
                })
        else:
            tsunami_changed = False

        tier_changed = new_tier != ev["confidence_tier"]
        if not (level_changed or tier_changed or tsunami_changed or external_changed):
            return

        ev["confidence_tier"] = new_tier
        ev["confidence_label"] = CONFIDENCE_LABELS[new_tier]
        ev["fully_confirmed"] = new_tier >= 5
        ev["external_match"] = external_match

        conn = dbmod.get_conn()
        ts = now_iso()
        conn.execute("UPDATE events SET level=?, stations_triggered=?, pga_gal=?, predicted_mmi=?, tsunami_risk=? WHERE id=?",
                     (ev["level"], corroborating, ev["pga_gal"], ev["predicted_mmi"], int(ev["tsunami_risk"]), ev["id"]))
        parts = []
        if level_changed:
            parts.append(f"ประเมินขนาดใหม่เป็น M{ev['magnitude_estimate']} (MMI {ev['predicted_mmi_roman']} ที่ตำแหน่งอ้างอิง) → ปรับระดับเป็น {ev['level']} ({ev['level_name']})")
        if tier_changed:
            parts.append(f"ความเชื่อมั่นปรับเป็น{ev['confidence_label']} ({corroborating} สถานียืนยันร่วม)")
        if external_changed and external_match:
            parts.append(f"ยืนยันตรงกับ {external_match['source']} ภายนอก (~{external_match['dist_km']} กม.)")
        if tsunami_changed:
            parts.append("ประเมินใหม่พบความเสี่ยงสึนามิ (เบื้องต้น)")
        conn.execute(
            "INSERT INTO audit_log(ts, username, action) VALUES (?, 'system', ?)",
            (ts, f"อัปเดตเหตุการณ์ {ev['id']}: " + " · ".join(parts)),
        )
        conn.commit()
        conn.close()

        # `level_changed` tells the frontend whether this update is a genuine
        # severity change (replay the siren/voice prompt, re-arm the level-6
        # "repeat until acknowledged" loop) or just a confidence-tier bump
        # (update the badge text only) -- without this flag every routine
        # corroboration update would re-trigger the alert sound/banner even
        # though the actual alert level never moved.
        self.broadcast({"type": "alert-upgrade", "event": ev, "level_changed": level_changed})
        telegram_notify.notify_alert(ev, is_new=False)

    # ------------------------------------------------------------- snapshots
    def snapshot(self):
        with self.lock:
            focus = self.stations[self.focus_station]
            return {
                "t": self.t,
                "stalta": round(self.stalta_current, 3),
                "focus_station": self.focus_station,
                "waveform": {axis: list(buf)[-1:] for axis, buf in focus["buffers"].items()},
                "active_event": self.active_event,
                "quake": self.quake,
            }

    def waveform(self, station_id, axis=None):
        with self.lock:
            st = self.stations.get(station_id)
            if not st:
                return None
            if axis:
                return list(st["buffers"][axis])
            return {a: list(b) for a, b in st["buffers"].items()}

    def stalta_series(self):
        with self.lock:
            buf = list(self.stations[self.focus_station]["buffers"]["ew"])
        return dsp.sta_lta_series(buf)

    def fft(self):
        with self.lock:
            buf = list(self.stations[self.focus_station]["buffers"]["ew"])
        return dsp.fft_spectrum(buf), dsp.dominant_frequency(buf)

    def correlation(self, station_ids):
        with self.lock:
            data = {sid: list(self.stations[sid]["buffers"]["ew"]) for sid in station_ids if sid in self.stations}
        return dsp.correlation_matrix(data)

    def class_probs(self):
        """Edge-AI source classification for the focus station: real frequency
        content + waveform/phase + cross-station coherence features (see
        signal.classify_source), not a single STA/LTA ratio."""
        with self.lock:
            buf = list(self.stations[self.focus_station]["buffers"]["ew"])
            neighbors = self.nearest_stations_to(self.focus_station, 2)
            neighbor_id = neighbors[1] if len(neighbors) > 1 else None
            neighbor_buf = list(self.stations[neighbor_id]["buffers"]["ew"]) if neighbor_id else None
        scores = dsp.classify_source(buf, neighbor_buf)
        top = max(scores, key=scores.get)
        labels = {"earthquake": "แผ่นดินไหว", "vehicle": "ยานพาหนะผ่าน",
                  "machinery": "เครื่องจักรกล/ก่อสร้าง", "noise": "เสียงรบกวนพื้นหลัง"}
        order = ["earthquake", "vehicle", "machinery", "noise"]
        return [{"label": labels[k], "pct": scores[k], "hi": k == top} for k in order]

    def station_status(self):
        with self.lock:
            return [
                {"id": sid, "region": st["region"], "lat": st["lat"], "lng": st["lng"],
                 "dist_km": round(self.dist_km(st), 1), "status": "online"}
                for sid, st in self.stations.items()
            ]


def run_forever(sim: Simulator, stop_event: threading.Event):
    period = 1.0 / dsp.SAMPLE_RATE_HZ
    next_t = time.monotonic()
    while not stop_event.is_set():
        sim.tick()
        next_t += period
        sleep_for = next_t - time.monotonic()
        if sleep_for > 0:
            time.sleep(sleep_for)
        else:
            next_t = time.monotonic()
