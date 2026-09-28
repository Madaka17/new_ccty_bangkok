import threading
from collections import deque
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from .. import auth
from .. import db as dbmod
from .. import signal as dsp
from ..ws import broadcast

# Real physical hardware nodes (e.g. firmware/prototype_node) reporting their
# OWN onboard sensors -- separate from server/routes/stations.py, which is
# ENVIRO's simulated 7-station seismic network. See schema.sql's real_nodes/
# real_node_log tables for the data model.
bp = Blueprint("nodes", __name__, url_prefix="/api/nodes")

# The prototype firmware uploads once per second (see loop()'s 1Hz block in
# prototype_node.ino) -- anything quieter than a few missed uploads reads as
# offline rather than waiting for a long, arbitrary timeout.
ONLINE_TIMEOUT_SEC = 90

# ~5 minutes of history at the node's 1 reading/sec upload rate -- enough for
# a dashboard sparkline, not meant as a real time-series archive.
LOG_KEEP_PER_NODE = 300

# Telemetry fields a node may report on each upload; anything else in the
# JSON body is ignored. Kept as a flat list (rather than nested JSON) to
# match the very plain, hand-built JSON the firmware sends -- no server-side
# schema library needed on either end.
NODE_FIELDS = [
    "temperature_c", "pressure_hpa", "battery_v", "battery_pct",
    "accel_x", "accel_y", "accel_z", "gyro_x", "gyro_y", "gyro_z",
    "roll_deg", "pitch_deg", "vibration_g", "uptime_s",
]


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _is_online(last_seen):
    if not last_seen:
        return False
    try:
        ts = datetime.fromisoformat(last_seen)
        return (datetime.now(ts.tzinfo) - ts).total_seconds() <= ONLINE_TIMEOUT_SEC
    except Exception:
        return False


def _public(row):
    d = dict(row)
    # `paused` (see edit_node's "สถานะ" field) always reads as offline
    # regardless of how fresh last_seen is -- an explicit admin/operator
    # override for testing an offline state on demand, rather than waiting
    # out ONLINE_TIMEOUT_SEC or actually disconnecting a device.
    d["online"] = False if d.get("paused") else _is_online(d.get("last_seen"))
    d.pop("api_key", None)  # never leaves the server, even to a logged-in dashboard user
    return d


# ---- Real per-node raw waveform buffer -----------------------------------
#
# In-memory only (like Simulator's own station buffers in simulator.py) --
# not persisted, rebuilt from scratch on every server restart as new uploads
# arrive. Each node gets its own rolling window of the last WAVE_WINDOW_SEC
# seconds of raw x/y/z acceleration samples (appended from every upload's
# "wave" field -- see post_telemetry below and prototype_node.ino's
# uploadTelemetry()), which node_waveform() below runs through the exact
# same real signal-processing primitives (server/signal.py) already used
# for the simulated station network's STA/LTA, FFT, and source classifier --
# just fed real accelerometer data instead of a synthetic waveform.
WAVE_WINDOW_SEC = 60
WAVE_BUFFER_LEN = int(WAVE_WINDOW_SEC * dsp.SAMPLE_RATE_HZ)  # 1200 @ 20Hz

_wave_lock = threading.Lock()
_wave_buffers = {}  # node_id -> {"x": deque, "y": deque, "z": deque}


def _buffers_for(node_id):
    with _wave_lock:
        bufs = _wave_buffers.get(node_id)
        if bufs is None:
            bufs = {
                "x": deque(maxlen=WAVE_BUFFER_LEN),
                "y": deque(maxlen=WAVE_BUFFER_LEN),
                "z": deque(maxlen=WAVE_BUFFER_LEN),
            }
            _wave_buffers[node_id] = bufs
        return bufs


def _ingest_wave(node_id, wave):
    if not isinstance(wave, dict):
        return
    wx, wy, wz = wave.get("x"), wave.get("y"), wave.get("z")
    if not (isinstance(wx, list) and isinstance(wy, list) and isinstance(wz, list)):
        return
    n = min(len(wx), len(wy), len(wz))
    if n == 0:
        return
    bufs = _buffers_for(node_id)
    with _wave_lock:
        for i in range(n):
            try:
                bufs["x"].append(float(wx[i]))
                bufs["y"].append(float(wy[i]))
                bufs["z"].append(float(wz[i]))
            except (TypeError, ValueError):
                pass  # one malformed sample shouldn't drop the rest of the batch


CLASS_LABELS = {
    "earthquake": "แผ่นดินไหว", "vehicle": "ยานพาหนะผ่าน",
    "machinery": "เครื่องจักรกล/ก่อสร้าง", "noise": "เสียงรบกวนพื้นหลัง",
}
CLASS_ORDER = ["earthquake", "vehicle", "machinery", "noise"]


@bp.get("")
def list_nodes():
    conn = dbmod.get_conn()
    rows = conn.execute("SELECT * FROM real_nodes ORDER BY node_id").fetchall()
    conn.close()
    return jsonify([_public(r) for r in rows])


@bp.get("/<node_id>")
def get_node(node_id):
    conn = dbmod.get_conn()
    row = conn.execute("SELECT * FROM real_nodes WHERE node_id=?", (node_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "not_found"}), 404
    log_rows = conn.execute(
        "SELECT ts, temperature_c, pressure_hpa, battery_pct, vibration_g, vibration_active "
        "FROM real_node_log WHERE node_id=? ORDER BY id DESC LIMIT 120",
        (node_id,),
    ).fetchall()
    conn.close()
    out = _public(row)
    out["log"] = [dict(r) for r in reversed(log_rows)]
    return jsonify(out)


@bp.patch("/<node_id>/location")
@auth.require_role("admin", "operator")
def set_node_location(node_id):
    """Manually sets a node's placement -- lat/lng, and optionally its
    region label -- via either of the two "จัดการอุปกรณ์" (device
    management) affordances on the สถานีตรวจวัด page: click-to-pin on that
    page's own map (frontend/index.html paintNodesMap/
    toggleDeviceManagementMode), or the "จัดการ" column's inline row editor
    for typing exact values. Neither real nor simulated nodes currently
    report their own GPS, so this is how a node's placement is set/
    corrected until real GPS hardware is wired up -- an explicit admin/
    operator action, logged to audit_log like every other admin write in
    this app (see routes/admin.py)."""
    body = request.get_json(silent=True) or {}
    try:
        lat = float(body.get("lat"))
        lng = float(body.get("lng"))
    except (TypeError, ValueError):
        return jsonify({"error": "invalid_location", "message": "ต้องระบุ lat/lng เป็นตัวเลข"}), 400
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return jsonify({"error": "invalid_location", "message": "ค่าพิกัดอยู่นอกช่วงที่ถูกต้อง"}), 400

    # Region is optional -- the click-to-pin map flow only ever sends
    # lat/lng, while the row editor form sends this too.
    region = body.get("region")
    if region is not None:
        region = str(region).strip()[:100] or None

    conn = dbmod.get_conn()
    row = conn.execute("SELECT node_id, name FROM real_nodes WHERE node_id=?", (node_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "not_found"}), 404

    if region is not None:
        conn.execute("UPDATE real_nodes SET lat=?, lng=?, region=? WHERE node_id=?", (lat, lng, region, node_id))
        action = f'แก้ไขตำแหน่งโหนด "{row["name"]}" ({node_id}) เป็น {region} ({lat:.5f}, {lng:.5f})'
    else:
        conn.execute("UPDATE real_nodes SET lat=?, lng=? WHERE node_id=?", (lat, lng, node_id))
        action = f'ปักตำแหน่งโหนด "{row["name"]}" ({node_id}) ที่ ({lat:.5f}, {lng:.5f})'
    conn.execute("INSERT INTO audit_log(ts, username, action) VALUES (?,?,?)", (_now_iso(), request.user["username"], action))
    conn.commit()
    updated = conn.execute("SELECT * FROM real_nodes WHERE node_id=?", (node_id,)).fetchone()
    conn.close()

    public = _public(updated)
    # Reuses the same message type post_telemetry/apply_node_telemetry
    # broadcast on -- both the สถานีตรวจวัด page and (once wired there too)
    # หน้าสถานการณ์'s node overlay already listen for 'node-telemetry' to
    # refresh a node's marker, and a location change is just another field
    # changing on that same node record.
    broadcast({"type": "node-telemetry", "node": public})
    return jsonify(public)


@bp.patch("/<node_id>")
@auth.require_role("admin", "operator")
def edit_node(node_id):
    """General node editor backing the "จัดการ" column's inline row form --
    รหัสโหนด (node_id, rename), ชื่อ (name), ภูมิภาค/Lat/Lng, and สถานะ (a
    "paused" override that forces the node to read as offline regardless of
    last_seen -- see _public() -- for testing an offline state on demand
    without physically disconnecting anything). Every field is optional;
    only keys present in the body are changed. Logged to audit_log like
    every other admin write in this app (see routes/admin.py)."""
    body = request.get_json(silent=True) or {}
    conn = dbmod.get_conn()
    row = conn.execute("SELECT * FROM real_nodes WHERE node_id=?", (node_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "not_found"}), 404

    updates = {}
    if "name" in body:
        name = str(body.get("name") or "").strip()
        if not name:
            conn.close()
            return jsonify({"error": "invalid_name", "message": "ต้องระบุชื่อ"}), 400
        updates["name"] = name[:200]
    if "region" in body:
        region = body.get("region")
        updates["region"] = (str(region).strip()[:100] or None) if region is not None else None
    if "lat" in body or "lng" in body:
        try:
            lat = float(body.get("lat", row["lat"]))
            lng = float(body.get("lng", row["lng"]))
        except (TypeError, ValueError):
            conn.close()
            return jsonify({"error": "invalid_location", "message": "ต้องระบุ lat/lng เป็นตัวเลข"}), 400
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            conn.close()
            return jsonify({"error": "invalid_location", "message": "ค่าพิกัดอยู่นอกช่วงที่ถูกต้อง"}), 400
        updates["lat"] = lat
        updates["lng"] = lng
    if "paused" in body:
        updates["paused"] = 1 if body.get("paused") else 0

    new_node_id = body.get("new_node_id")
    if new_node_id is not None:
        new_node_id = str(new_node_id).strip()
        if not new_node_id:
            conn.close()
            return jsonify({"error": "invalid_node_id", "message": "รหัสโหนดห้ามว่าง"}), 400
        if new_node_id != node_id and conn.execute("SELECT 1 FROM real_nodes WHERE node_id=?", (new_node_id,)).fetchone():
            conn.close()
            return jsonify({"error": "duplicate_node_id", "message": f'มีโหนดรหัส "{new_node_id}" อยู่แล้ว'}), 409

    if updates:
        set_clause = ", ".join(f"{k}=?" for k in updates)
        conn.execute(f"UPDATE real_nodes SET {set_clause} WHERE node_id=?", [*updates.values(), node_id])

    final_id = node_id
    rename_note = ""
    if new_node_id and new_node_id != node_id:
        # Renaming a PRIMARY KEY -- SQLite allows UPDATEing a TEXT primary
        # key value directly. real_node_log rows and the in-memory wave
        # buffer (nodes.py-local, not persisted) are keyed by node_id too,
        # so both need the same rename or they'd silently orphan under the
        # old id.
        conn.execute("UPDATE real_nodes SET node_id=? WHERE node_id=?", (new_node_id, node_id))
        conn.execute("UPDATE real_node_log SET node_id=? WHERE node_id=?", (new_node_id, node_id))
        with _wave_lock:
            if node_id in _wave_buffers:
                _wave_buffers[new_node_id] = _wave_buffers.pop(node_id)
        final_id = new_node_id
        rename_note = f' เปลี่ยนรหัสจาก "{node_id}" เป็น "{new_node_id}"'
        if not row["is_simulated"]:
            # A real device's firmware has NODE_ID hardcoded (see
            # firmware/prototype_node) -- renaming its DB row without also
            # reflashing that constant means its next upload 404s against
            # the old, now-nonexistent id. Simulated nodes have no such
            # constant to keep in sync (node_simulator.py looks them up by
            # the *current* row each tick), so this warning is specific to
            # is_simulated=0.
            rename_note += ' -- โหนดจริงต้องแก้ NODE_ID ในเฟิร์มแวร์ให้ตรงกันด้วย มิฉะนั้นจะอัปโหลดไม่ได้อีก'

    conn.execute(
        "INSERT INTO audit_log(ts, username, action) VALUES (?,?,?)",
        (_now_iso(), request.user["username"], f'แก้ไขข้อมูลโหนด "{row["name"]}" ({node_id}){rename_note}'),
    )
    conn.commit()
    updated = conn.execute("SELECT * FROM real_nodes WHERE node_id=?", (final_id,)).fetchone()
    conn.close()

    public = _public(updated)
    public["rename_warning"] = rename_note.strip(" -") or None
    broadcast({"type": "node-telemetry", "node": public})
    return jsonify(public)


def apply_node_telemetry(node_id, body):
    """Writes one telemetry reading for `node_id` -- the DB row, its log
    entry, its wave buffer -- and broadcasts it, exactly the same whether it
    came from a genuine HTTP upload (post_telemetry below, after that
    route's own auth check) or from server/node_simulator.py's background
    generator for the 7 simulated real-shaped nodes. Returns the public node
    dict, or None if `node_id` isn't a row in real_nodes at all.

    `body` uses the same flat-JSON shape a real node's HTTP upload sends
    (see NODE_FIELDS + firmware/prototype_node's uploadTelemetry())."""
    conn = dbmod.get_conn()
    row = conn.execute("SELECT 1 FROM real_nodes WHERE node_id=?", (node_id,)).fetchone()
    if not row:
        conn.close()
        return None

    values = {}
    for f in NODE_FIELDS:
        v = body.get(f)
        if v is None:
            continue
        try:
            values[f] = float(v)
        except (TypeError, ValueError):
            pass  # malformed field on one reading shouldn't drop the rest of the upload
    if "battery_pct" in values:
        values["battery_pct"] = int(round(values["battery_pct"]))

    vibration_active = 1 if body.get("vibration_active") else 0
    bmp_ok = 1 if body.get("bmp_ok") else 0
    imu_ok = 1 if body.get("imu_ok") else 0
    ts = _now_iso()

    set_clause = "".join(f", {f}=?" for f in values)
    conn.execute(
        f"UPDATE real_nodes SET last_seen=?, vibration_active=?, bmp_ok=?, imu_ok=?{set_clause} WHERE node_id=?",
        [ts, vibration_active, bmp_ok, imu_ok, *values.values(), node_id],
    )
    conn.execute(
        "INSERT INTO real_node_log(node_id, ts, temperature_c, pressure_hpa, battery_pct, vibration_g, vibration_active, accel_x, accel_y, accel_z) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (node_id, ts, values.get("temperature_c"), values.get("pressure_hpa"),
         values.get("battery_pct"), values.get("vibration_g"), vibration_active,
         values.get("accel_x"), values.get("accel_y"), values.get("accel_z")),
    )
    conn.execute(
        "DELETE FROM real_node_log WHERE node_id=? AND id NOT IN "
        "(SELECT id FROM real_node_log WHERE node_id=? ORDER BY id DESC LIMIT ?)",
        (node_id, node_id, LOG_KEEP_PER_NODE),
    )
    conn.commit()

    _ingest_wave(node_id, body.get("wave"))

    updated = conn.execute("SELECT * FROM real_nodes WHERE node_id=?", (node_id,)).fetchone()
    conn.close()

    public = _public(updated)
    # Pushes the new reading to every open dashboard immediately (see
    # frontend/index.html's ws.onmessage 'node-telemetry' case) instead of
    # waiting for the next poll.
    broadcast({"type": "node-telemetry", "node": public})
    return public


@bp.post("/<node_id>/telemetry")
def post_telemetry(node_id):
    conn = dbmod.get_conn()
    row = conn.execute("SELECT * FROM real_nodes WHERE node_id=?", (node_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "unknown_node", "message": f'ไม่รู้จักโหนด "{node_id}" -- ต้องเพิ่มลง real_nodes ก่อน'}), 404

    # Machine-to-machine auth, deliberately separate from auth.py's
    # session-token login -- a headless node has no username/password flow,
    # just a static shared secret it sends on every upload. Only the HTTP
    # route needs this check -- node_simulator.py's calls into
    # apply_node_telemetry() are trusted server-internal code, not a
    # network request pretending to be a device.
    key = request.headers.get("X-Node-Key", "")
    if not key or key != row["api_key"]:
        return jsonify({"error": "unauthorized", "message": "X-Node-Key ไม่ถูกต้องหรือไม่มี"}), 401

    body = request.get_json(silent=True) or {}
    apply_node_telemetry(node_id, body)
    return jsonify({"ok": True})


@bp.get("/<node_id>/waveform")
def node_waveform(node_id):
    """Real x/y/z acceleration waveform plus PGA / STA-LTA / dominant
    frequency / source classification, all computed live from this node's
    own accumulated raw samples (see _wave_buffers above) through the same
    real primitives in server/signal.py that already drive the simulated
    station network's analysis page -- nothing here is a lookup table or a
    canned demo value."""
    conn = dbmod.get_conn()
    exists = conn.execute("SELECT 1 FROM real_nodes WHERE node_id=?", (node_id,)).fetchone()
    conn.close()
    if not exists:
        return jsonify({"error": "not_found"}), 404

    bufs = _buffers_for(node_id)
    with _wave_lock:
        x, y, z = list(bufs["x"]), list(bufs["y"]), list(bufs["z"])

    n = min(len(x), len(y), len(z))
    x, y, z = x[-n:], y[-n:], z[-n:]
    low_res = False

    if n == 0:
        # No firmware "wave" burst has ever arrived for this node (see
        # apply_node_telemetry/_ingest_wave) -- fall back to the plain
        # accel_x/y/z each regular telemetry upload already carries, one
        # point per upload (~1 Hz), logged into real_node_log alongside
        # temperature/battery/etc. Genuinely real data, just far coarser
        # than the true 20Hz buffer -- kept HONESTLY labelled as such
        # (low_res=true, sample_rate_hz down at the real ~1Hz) rather than
        # quietly mixed into the 20Hz-assumed STA/LTA/FFT math below, which
        # would silently misreport frequencies and window durations if fed
        # samples 1 second apart instead of 50ms apart.
        conn = dbmod.get_conn()
        rows = conn.execute(
            "SELECT accel_x, accel_y, accel_z FROM real_node_log "
            "WHERE node_id=? AND accel_x IS NOT NULL ORDER BY id DESC LIMIT 60",
            (node_id,),
        ).fetchall()
        conn.close()
        rows = list(reversed(rows))
        x = [r["accel_x"] for r in rows]
        y = [r["accel_y"] for r in rows]
        z = [r["accel_z"] for r in rows]
        n = len(x)
        low_res = n > 0

    magnitude = [((x[i] ** 2 + y[i] ** 2 + z[i] ** 2) ** 0.5) for i in range(n)]
    sample_rate = 1.0 if low_res else dsp.SAMPLE_RATE_HZ
    seconds_available = round(n / sample_rate, 1)

    # STA/LTA, FFT, and the classifier all assume dsp.SAMPLE_RATE_HZ (20Hz)
    # internally -- meaningless (wrong window durations, wrong frequency
    # axis) on the ~1Hz low_res fallback, so those stay at their "not
    # enough data" defaults rather than reporting numbers computed on the
    # wrong timebase. Only the waveform chart itself is honest to show at
    # low_res; the analysis panels wait for the real 20Hz buffer.
    if magnitude and not low_res:
        pga_g = dsp.peak_abs(magnitude)
        stalta_val = dsp.sta_lta(magnitude)
        dominant_hz = dsp.dominant_frequency(magnitude)
        scores = dsp.classify_source(magnitude)  # no neighbour buffer -- see classify_source's docstring on coherence
    else:
        pga_g = dsp.peak_abs(magnitude) if magnitude else 0.0  # peak-of-what-we-have is still meaningful even at low_res
        # STA/LTA is a plain energy ratio -- unlike frequency content, it
        # stays real and meaningful at any sample rate, so it's still worth
        # computing here (coarser, at the buffer's true ~1Hz), just gated on
        # having enough samples for a real lta_sec=15s window at that rate.
        stalta_val = dsp.sta_lta(magnitude, sample_rate_hz=sample_rate) if (magnitude and low_res) else 0.0
        # dominant_hz/classify_source are FFT-based -- at 1Hz the Nyquist
        # limit is 0.5Hz, far below the 1-20Hz range that actually
        # distinguishes an earthquake/vehicle/machinery/noise (see
        # classify_source's docstring on peakiness) -- any "frequency" or
        # category split computed from 1Hz samples would be aliased,
        # fabricated numbers dressed up as real analysis, not genuinely
        # coarser ones. This is a physical (Nyquist) limit of the sample
        # rate itself, not something more code can work around.
        dominant_hz = 0.0
        scores = {k: 0.0 for k in CLASS_ORDER}

    top = max(scores, key=scores.get) if (magnitude and not low_res) else None
    classification_bars = [
        {"label": CLASS_LABELS[k], "pct": scores[k], "hi": k == top} for k in CLASS_ORDER
    ]

    return jsonify({
        "node_id": node_id,
        "sample_rate_hz": sample_rate,
        "low_res": low_res,
        "window_sec": WAVE_WINDOW_SEC,
        "seconds_available": seconds_available,
        "axes": {"x": x, "y": y, "z": z},
        "pga_g": round(pga_g, 4),
        "stalta": round(stalta_val, 3),
        "dominant_hz": round(dominant_hz, 2),
        "classification": scores,
        "classification_bars": classification_bars,
        # classify_source() itself only trusts its own read once >=16s of
        # buffer exist (see its docstring/short-circuit) -- reflecting that
        # same real threshold here as a genuine "how much of the classifier's
        # own minimum window is filled" measure, not a fabricated model score.
        "classification_confidence_pct": 0.0 if low_res else round(min(100.0, seconds_available / 16.0 * 100), 1),
    })


@bp.get("/<node_id>/analysis")
def node_analysis(node_id):
    """Deeper real signal analysis for the "วิเคราะห์ข้อมูล" page -- the
    full STA/LTA ratio *time series* (not just its current tail value, see
    node_waveform above) against the same admin-configurable trigger
    threshold the simulated network uses (detector_config, see
    simulator.py), plus a real FFT magnitude spectrum -- both computed on
    this node's own accumulated raw buffer through the exact real
    primitives in server/signal.py. Nothing here is canned; an idle node
    genuinely shows a flat STA/LTA line under threshold and a near-empty
    spectrum."""
    conn = dbmod.get_conn()
    exists = conn.execute("SELECT 1 FROM real_nodes WHERE node_id=?", (node_id,)).fetchone()
    if not exists:
        conn.close()
        return jsonify({"error": "not_found"}), 404
    threshold_row = conn.execute("SELECT stalta_threshold FROM detector_config WHERE id=1").fetchone()
    conn.close()
    threshold = threshold_row["stalta_threshold"] if threshold_row else 3.5

    bufs = _buffers_for(node_id)
    with _wave_lock:
        x, y, z = list(bufs["x"]), list(bufs["y"]), list(bufs["z"])
    n = min(len(x), len(y), len(z))
    x, y, z = x[-n:], y[-n:], z[-n:]
    magnitude = [((x[i] ** 2 + y[i] ** 2 + z[i] ** 2) ** 0.5) for i in range(n)]

    stalta_series = dsp.sta_lta_series(magnitude) if magnitude else []
    trigger_index = next((i for i, v in enumerate(stalta_series) if v > threshold), None)
    spectrum = dsp.fft_spectrum(magnitude, max_hz=10.0, bins=32) if magnitude else []

    return jsonify({
        "node_id": node_id,
        "sample_rate_hz": dsp.SAMPLE_RATE_HZ,
        "seconds_available": round(n / dsp.SAMPLE_RATE_HZ, 1),
        "stalta_series": [round(v, 3) for v in stalta_series],
        "stalta_threshold": threshold,
        "trigger_index": trigger_index,
        "trigger_time_s": round(trigger_index / dsp.SAMPLE_RATE_HZ, 1) if trigger_index is not None else None,
        "fft_spectrum": spectrum,
    })


@bp.get("/correlation")
def nodes_correlation():
    """Real Pearson cross-correlation between every pair of nodes that
    currently has enough buffered signal -- reuses the same
    signal.correlation_matrix already driving the simulated network's own
    correlation heatmap (routes/analysis.py), just fed real (or
    node_simulator-generated) magnitude buffers instead of the synthetic
    station ones."""
    conn = dbmod.get_conn()
    rows = conn.execute("SELECT node_id, name FROM real_nodes ORDER BY node_id").fetchall()
    conn.close()

    buffers_by_node = {}
    labels = {}
    for row in rows:
        bufs = _buffers_for(row["node_id"])
        with _wave_lock:
            x, y, z = list(bufs["x"]), list(bufs["y"]), list(bufs["z"])
        n = min(len(x), len(y), len(z))
        if n < int(dsp.SAMPLE_RATE_HZ * 8):  # need at least ~8s to say anything meaningful about correlation
            continue
        x, y, z = x[-n:], y[-n:], z[-n:]
        buffers_by_node[row["node_id"]] = [((x[i] ** 2 + y[i] ** 2 + z[i] ** 2) ** 0.5) for i in range(n)]
        labels[row["node_id"]] = row["name"] or row["node_id"]

    names, matrix = dsp.correlation_matrix(buffers_by_node)
    return jsonify({"node_ids": names, "labels": [labels[n] for n in names], "matrix": matrix})


@bp.get("/device-spec")
def device_spec():
    """Describes the actual connected prototype hardware (see
    firmware/prototype_node) -- deliberately real, not the illustrative
    "ENVIRO Node One" household-product copy still served from
    /api/stations/device-spec for the simulated network's own page."""
    return jsonify({
        "name": "Prototype-node",
        "version": "v1 (Heltec WiFi LoRa 32 V4 + GY-91)",
        "sensor": "GY-91: BMP280 (อุณหภูมิ/ความดัน) + MPU-6xxx IMU 6 แกน (ความเร่ง ±2g / ไจโร ±250°/s)",
        "compute": "ESP32-S3 บนบอร์ด Heltec — วิเคราะห์ STA/LTA เบื้องต้นและกรอง Hysteresis บนบอร์ด",
        "connectivity": "Wi-Fi (อัปโหลด HTTP JSON ทุก 1 วินาที ไปยังเซิร์ฟเวอร์ ENVIRO โดยตรง)",
        "install": "จ่ายไฟผ่าน USB — ตั้งค่า WiFi/เซิร์ฟเวอร์ในซอร์สโค้ดก่อนแฟลช",
        "calibration": "Auto-Zero ทุกครั้งที่บูต (เก็บ 300 ตัวอย่างขณะนิ่ง)",
        "sample_rate": "IMU 20 Hz on-board · อัปโหลด raw waveform ~20 ตัวอย่าง/แกน ทุก 1 วินาที",
    })
