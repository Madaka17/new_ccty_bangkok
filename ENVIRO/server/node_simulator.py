"""Background generator for the 7 simulated real-shaped nodes shown
alongside the one genuine PROTO-01 prototype on the "สถานีตรวจวัด" page (see
server/db.py SIMULATED_REAL_NODES and routes/nodes.py).

Produces realistic-looking ambient sensor readings -- a real per-node
random-walk generator, not canned/static values -- and feeds them through
apply_node_telemetry(), the exact same code path a genuine HTTP upload from
firmware/prototype_node goes through. Every downstream computation (PGA/
STA-LTA/FFT/classification, online/offline timeout, WS broadcast) is
therefore identical to the real node's; only the input signal is synthetic
-- the same "synthetic input, genuinely real downstream processing" split
this project already uses for the older simulated 7-station seismic network
in simulator.py/signal.py.
"""
import random
import threading
import time

from . import db as dbmod
from .db import SIMULATED_REAL_NODES

TICK_SEC = 2.0
WAVE_SAMPLE_RATE_HZ = 20.0  # matches server/signal.py SAMPLE_RATE_HZ, and the real node's own IMU rate

# Rough per-node baseline temperature (deg C) -- illustrative only, not a
# real climate model, just enough that each simulated city doesn't read
# identically to the others.
BASE_TEMP_C = {
    "SIM-CNX-118": 26.0, "SIM-PLK-014": 28.0, "SIM-TAK-009": 29.0,
    "SIM-BKK-201": 31.0, "SIM-KKN-022": 29.5, "SIM-CHB-031": 30.0, "SIM-SGK-005": 28.5,
}

_state = {}  # node_id -> slowly-evolving {"temperature_c":..., "pressure_hpa":..., "battery_pct":..., "roll_deg":..., "pitch_deg":...}
_lock = threading.Lock()


def _walk(value, lo, hi, step):
    """One random-walk step, clamped to a plausible range -- smooth,
    continuous evolution instead of a fresh random value every tick."""
    value += random.uniform(-step, step)
    return max(lo, min(hi, value))


def _init_state(node_id):
    base = BASE_TEMP_C.get(node_id, 28.0)
    return {
        "temperature_c": base,
        "pressure_hpa": random.uniform(1006.0, 1011.0),
        "battery_pct": random.uniform(70.0, 100.0),
        "roll_deg": random.uniform(-1.0, 1.0),
        "pitch_deg": random.uniform(-1.0, 1.0),
    }


def _gen_wave(n, amp):
    return [round(random.gauss(0.0, amp), 4) for _ in range(n)]


def _paused_node_ids():
    """Nodes an admin/operator marked "บังคับให้ออฟไลน์" via the จัดการ
    column's edit form (routes/nodes.py edit_node) -- skipped below so a
    "paused" node's sensor fields actually freeze, instead of a supposedly
    offline device still visibly reporting fresh ambient readings.
    Re-queried every tick (cheap at 8 rows) rather than cached, so a status
    flip takes effect on the very next tick."""
    conn = dbmod.get_conn()
    rows = conn.execute("SELECT node_id FROM real_nodes WHERE paused=1").fetchall()
    conn.close()
    return {r["node_id"] for r in rows}


def _tick(apply_fn):
    n_samples = max(1, int(TICK_SEC * WAVE_SAMPLE_RATE_HZ))
    paused = _paused_node_ids()
    for node_id, _name, _api_key, _lat, _lng, _region in SIMULATED_REAL_NODES:
        if node_id in paused:
            continue
        with _lock:
            st = _state.setdefault(node_id, _init_state(node_id))
            base = BASE_TEMP_C.get(node_id, 28.0)
            st["temperature_c"] = _walk(st["temperature_c"], base - 3, base + 3, 0.08)
            st["pressure_hpa"] = _walk(st["pressure_hpa"], 1002.0, 1015.0, 0.15)
            st["battery_pct"] = _walk(st["battery_pct"], 55.0, 100.0, 0.15)
            st["roll_deg"] = _walk(st["roll_deg"], -3.0, 3.0, 0.05)
            st["pitch_deg"] = _walk(st["pitch_deg"], -3.0, 3.0, 0.05)
            snapshot = dict(st)

        # Ambient vibration noise at roughly the real board's own idle
        # amplitude (~0.001-0.004g) -- occasionally (rare) a few-tick
        # amplitude bump stands in for a passing vehicle/door slam, purely
        # so the classifier has something besides flat background noise to
        # occasionally react to, same as a real deployed sensor would.
        amp = 0.003
        if random.random() < 0.03:
            amp = random.uniform(0.02, 0.08)

        wave_x = _gen_wave(n_samples, amp)
        wave_y = _gen_wave(n_samples, amp)
        wave_z = _gen_wave(n_samples, amp * 0.8)
        vib_g = max(abs(wave_x[-1]), abs(wave_y[-1]), abs(wave_z[-1]))

        body = {
            "temperature_c": round(snapshot["temperature_c"], 2),
            "pressure_hpa": round(snapshot["pressure_hpa"], 2),
            "battery_v": round(3.2 + (snapshot["battery_pct"] / 100.0) * 1.0, 3),
            "battery_pct": round(snapshot["battery_pct"]),
            "accel_x": wave_x[-1], "accel_y": wave_y[-1], "accel_z": wave_z[-1],
            "gyro_x": round(random.uniform(-0.1, 0.1), 3),
            "gyro_y": round(random.uniform(-0.1, 0.1), 3),
            "gyro_z": round(random.uniform(-0.1, 0.1), 3),
            "roll_deg": round(snapshot["roll_deg"], 2),
            "pitch_deg": round(snapshot["pitch_deg"], 2),
            "vibration_g": round(vib_g, 4),
            "vibration_active": amp > 0.015,
            "bmp_ok": True, "imu_ok": True,
            "uptime_s": int(time.time()),
            "wave": {"x": wave_x, "y": wave_y, "z": wave_z},
        }
        apply_fn(node_id, body)


def run_forever(stop_event, apply_fn):
    """`apply_fn` is routes.nodes.apply_node_telemetry, passed in (rather
    than imported directly) to avoid a routes -> app -> routes import
    cycle -- see app.py's create_app()."""
    while not stop_event.is_set():
        try:
            _tick(apply_fn)
        except Exception:
            pass  # one bad tick shouldn't kill the whole background thread
        stop_event.wait(TICK_SEC)
