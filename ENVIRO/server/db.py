import sqlite3
import os
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "enviro.db")
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# Primary gate is now PREDICTED INTENSITY (Modified Mercalli Intensity, MMI)
# at the reference "you are here" location -- not magnitude, and not PGA at
# the epicenter. USGS is explicit that magnitude and intensity are different
# things: the same event produces very different shaking in different places
# depending on distance, depth, rupture directivity, soil, and buildings, so
# the level a specific viewer should see has to be an intensity prediction,
# not a single global magnitude threshold. This 6-tier ladder and its MMI
# bands, comparative-severity text, and per-level advisory copy follow the
# recommendation in "คำแนะนำตามมาตราเมอร์แคลลี" (2026), itself built on:
#   - USGS: "Magnitude vs. Intensity" (why intensity, not magnitude, should
#     drive public alerting)
#   - USGS Modified Mercalli Intensity scale (I-XII) + ShakeAlert alert
#     thresholds (MMI VI as the "may cause damage" start point; public
#     notification starting from MMI III+)
#   - CDC guidance on what to do during/after an earthquake (Drop-Cover-Hold On)
#   - NOAA/National Weather Service guidance for a coastal tsunami overlay
# The `mag_ref` field cross-references the separate Richter-scale magnitude
# table (TMD-style, same one used for "event magnitude" display elsewhere) --
# purely as a loose, honest illustration, since one MMI level can come from
# many different (magnitude, distance) combinations; it is NOT a gate.
#
# Station/network corroboration count still does not affect the level -- it
# only drives a separate confidence tier (see NODES_MIN / _confidence_tier in
# simulator.py): more stations agreeing means higher *confidence* in an
# already-classified severity, not a *higher* severity.
LEVELS = [
    (1, "ปกติ", 1, 2.99, "I–II",
     "เครื่องมือตรวจพบ หรือมีเพียงคนที่อยู่นิ่งในอาคารสูงบางส่วนรู้สึก ไม่มีความเสียหาย",
     "ใกล้เคียงมาตราริคเตอร์ 1–2.9 ที่ระยะใกล้ (หรือขนาดใหญ่กว่ามากในระยะไกล)",
     1.0, 8.0, "ไม่กำหนด (เฝ้าระวังพื้นหลัง)", "≥ 1 สถานี",
     "ไม่คาดว่าจะได้รับแรงสั่นสะเทือนที่มีผลกระทบ ระบบกำลังตรวจสอบเหตุการณ์ ไม่ต้องดำเนินการฉุกเฉิน",
     "แดชบอร์ดภายใน", "ไม่มีเสียง แสดงสถานะสีเขียว", "var(--status-good)"),
    (2, "รับรู้แรงสั่น", 3.0, 4.99, "III–IV",
     "คล้ายรถบรรทุกหรือรถไฟวิ่งผ่าน ประตู หน้าต่าง และวัตถุแขวนอาจสั่นไหว โดยทั่วไปยังไม่เกิดความเสียหาย",
     "ใกล้เคียงมาตราริคเตอร์ 3–4.9 ที่ระยะใกล้ถึงปานกลาง",
     8.1, 65.6, "≥ 55%", "≥ 2 สถานี",
     "อาจรู้สึกถึงแรงสั่นสะเทือนเล็กน้อย ตั้งสติ อยู่ห่างจากกระจก ชั้นวาง และวัตถุที่อาจตก ติดตามการอัปเดตจากระบบ",
     "แอปพลิเคชัน · แดชบอร์ด", "เสียงแจ้งเตือนสั้น 1 ครั้ง พร้อมข้อความข้อมูล", "var(--status-info)"),
    (3, "เฝ้าระวัง", 5.0, 5.99, "V",
     "คนส่วนใหญ่รู้สึกได้ ของแขวนแกว่ง ของชิ้นเล็กอาจเคลื่อนหรือตก ภาชนะอาจแตก แต่ความเสียหายโดยทั่วไปเล็กน้อย",
     "ใกล้เคียงมาตราริคเตอร์ 4–5.9 ที่ระยะไม่ไกล",
     66.0, 123.0, "≥ 70%", "≥ 3 สถานี",
     "คาดว่าจะรู้สึกแรงสั่นชัดเจน หยุดกิจกรรมเสี่ยง ปิดเตาหากทำได้ทันที และเตรียม “หมอบ–กำบัง–ยึดจับ” ห้ามใช้ลิฟต์",
     "แอป · แจ้งเตือนสั่น (Push + Vibrate)", "เสียง 2 ครั้งทุก 10 วินาที พร้อมสั่นโทรศัพท์", "var(--status-watch)"),
    (4, "ป้องกันตนทันที", 6.0, 6.99, "VI",
     "ทุกคนรู้สึกได้ เฟอร์นิเจอร์อาจเคลื่อน ปูนหรือผนังแตกร้าวเล็กน้อย อาคารที่ไม่แข็งแรงอาจเริ่มเสียหาย",
     "ใกล้เคียงมาตราริคเตอร์ 5–6.9 ที่ระยะใกล้",
     124.0, 231.0, "≥ 80%", "≥ 5 สถานี",
     "แรงสั่นสะเทือนอาจก่อความเสียหาย — หมอบ กำบัง ยึดจับทันที อยู่ภายในอาคาร ไม่วิ่งออกนอกอาคารระหว่างกำลังสั่น และอยู่ห่างจากกระจก",
     "แอป · SMS · LINE Alert · เสียงพูดในแอป", "เสียง 3 จังหวะทุก 5 วินาที พร้อมเสียงพูด “เตรียมหมอบ กำบัง ยึดจับ”", "var(--status-warn)"),
    (5, "อันตรายรุนแรง", 7.0, 8.99, "VII–VIII",
     "ยืนลำบาก สิ่งของและเฟอร์นิเจอร์ล้ม อาคารทั่วไปเสียหาย อาคารอ่อนแออาจพังบางส่วน ปล่องไฟหรือผนังอาจหล่น",
     "ใกล้เคียงมาตราริคเตอร์ 6–7.0+ ที่ระยะใกล้ศูนย์กลาง",
     232.0, 812.0, "≥ 88%", "≥ 6 สถานี",
     "แรงสั่นรุนแรงมาก — ป้องกันศีรษะและคอทันที หลังหยุดสั่นให้ออกจากอาคารที่เสียหายโดยใช้บันได ไปยังพื้นที่โล่ง ระวังไฟฟ้า ก๊าซรั่ว เศษวัสดุ และอาฟเตอร์ช็อก",
     "Cell Broadcast · SMS · แอป · ไซเรนพื้นที่ · โทรทัศน์/วิทยุ", "เสียงสลับเร็ว พร้อมหน้าจอเต็มและนับเวลาคลื่นถึง", "var(--status-critical)"),
    (6, "วิกฤตฉุกเฉิน", 9.0, None, "IX–XII",
     "อาคารที่ออกแบบดีอาจเสียหายหนัก อาคารจำนวนมากพัง ระบบสาธารณูปโภคและเส้นทางเสียหาย อาจมีดินถล่มหรือพื้นดินแตก",
     "ใกล้เคียงมาตราริคเตอร์ 7.0 ขึ้นไป ที่ระยะใกล้ศูนย์กลางมาก หรือศูนย์กลางอยู่ในพื้นที่โดยตรง",
     818.0, None, "≥ 93%", "≥ 7 สถานี หลายภูมิภาค",
     "ภาวะวิกฤต — รักษาชีวิตเป็นอันดับแรก หมอบ–กำบัง–ยึดจับจนหยุดสั่น จากนั้นออกจากสิ่งปลูกสร้างที่เสียหาย ไปยังจุดปลอดภัย ช่วยผู้บาดเจ็บเท่าที่ปลอดภัย และปฏิบัติตามคำสั่งทางการ",
     "Cell Broadcast ทุกเครือข่าย · ไซเรนแห่งชาติ · สื่อทุกช่องทาง · ประสานหน่วยงานฉุกเฉิน",
     "ไซเรนสลับเสียงพูดต่อเนื่อง จนผู้ใช้กดยืนยันรับทราบ", "var(--status-extreme)"),
]

# The simulated detection network: exactly 7 stations, one per named
# province, as explicitly requested -- a deliberately small, real-city
# network rather than the earlier arbitrary 15-station spread. CNX-118
# (เชียงใหม่) doubles as DEFAULT_FOCUS_STATION and BKK-201 (กรุงเทพฯ) as
# REFERENCE_STATION in server/simulator.py -- keep both IDs in sync if this
# list changes again.
STATIONS = [
    ("CNX-118", "เชียงใหม่", 18.788, 98.985),
    ("PLK-014", "พิษณุโลก", 16.827, 100.259),
    ("TAK-009", "ตาก", 16.877, 99.126),
    ("BKK-201", "กรุงเทพฯ", 13.756, 100.502),
    ("KKN-022", "ขอนแก่น", 16.446, 102.833),
    ("CHB-031", "ชลบุรี", 13.361, 100.985),
    ("SGK-005", "สงขลา", 7.189, 100.595),
]

STATION_REGIONS = [
    ("ภาคเหนือ", 512, 498), ("ภาคกลาง", 398, 389),
    ("กรุงเทพฯ และปริมณฑล", 344, 341), ("ภาคตะวันออกเฉียงเหนือ", 301, 284),
    ("ภาคใต้", 287, 279),
]

FAULTS = [
    ("รอยเลื่อนแม่จัน", "เชียงราย", 20.15, 99.60, 20.20, 100.10),
    ("รอยเลื่อนพะเยา", "พะเยา", 19.25, 99.75, 19.05, 100.05),
    ("รอยเลื่อนเถิน", "ลำปาง", 18.15, 99.30, 17.95, 99.70),
    ("รอยเลื่อนเมย–วังเชียงใหม่", "ตาก", 16.90, 98.40, 17.50, 98.70),
    ("รอยเลื่อนศรีสวัสดิ์", "กาญจนบุรี", 14.35, 98.85, 14.60, 99.20),
    ("รอยเลื่อนสามองค์เจดีย์", "กาญจนบุรี", 14.30, 98.30, 14.60, 98.75),
    ("รอยเลื่อนระนอง", "ระนอง", 10.20, 98.85, 9.50, 98.60),
    ("รอยเลื่อนคลองมะรุ่ย", "สุราษฎร์ธานี", 9.20, 98.75, 8.50, 98.95),
]

# "Time to shaking, by city" table: the same 7 named provinces as STATIONS
# above, as explicitly requested. mmi_label here is only the DB seed value --
# server/routes/situation.py always recomputes the live predicted MMI per
# city from the current event's real distance (mmi_label_for()), so this
# column is never actually shown as-is.
CITIES = [
    ("เชียงใหม่", 18.788, 98.985, "-"),
    ("พิษณุโลก", 16.827, 100.259, "-"),
    ("ตาก", 16.877, 99.126, "-"),
    # Exact name "กรุงเทพมหานคร" is matched verbatim in several places in
    # frontend/index.html ("คุณอยู่ที่นี่" badge, userCountdown, the
    # situationTimer tick, renderLocationGuidance's bkkCity lookup) -- do not
    # rename without updating those.
    ("กรุงเทพมหานคร", 13.756, 100.502, "-"),
    ("ขอนแก่น", 16.446, 102.833, "-"),
    ("ชลบุรี", 13.361, 100.985, "-"),
    ("สงขลา", 7.189, 100.595, "-"),
]

RISK = [
    ("เชียงราย", 82), ("พะเยา", 71), ("เชียงใหม่", 74), ("ตาก", 63),
    ("ลำปาง", 58), ("กาญจนบุรี", 68), ("ระนอง", 55), ("สุราษฎร์ธานี", 46),
    ("นครราชสีมา", 31), ("กรุงเทพมหานคร", 38), ("ภูเก็ต", 34),
]

SOURCES_STATIC = [
    ("TMD", "var(--series-tmd)", 10, 45, 90, 5, "กรมอุตุนิยมวิทยา — เรียลไทม์", -0.1),
    ("GISTDA", "var(--series-gistda)", 9, 1200, 91, 2, "ข้อมูลดาวเทียม (InSAR) หลังเหตุการณ์ ~20 นาที", 0.0),
    ("NASA", "var(--series-nasa)", 15, 180, 82, 10, "ยังไม่เชื่อมต่อ API จริง — ใช้ค่าอ้างอิงประกอบการสาธิต", 0.2),
]

SERVICES = [
    ("API Gateway", None, None),
    ("Ingestion Service (MQTT)", None, None),
    ("Edge AI Model Service", None, None),
    ("Alert Dispatch Engine", "watch", "ผู้ให้บริการ SMS รายหนึ่งหน่วงเวลา"),
    ("Calibration Service", None, None),
    ("Database / Storage Cluster", None, None),
]

ROLES = [
    ("admin", 4, "สิทธิ์เต็ม: ตั้งค่าระบบ, นโยบายแจ้งเตือน, จัดการผู้ใช้"),
    ("operator", 23, "ดูข้อมูลเรียลไทม์, ยืนยัน/ยกเลิกการแจ้งเตือน"),
    ("auditor", 6, "อ่านอย่างเดียว: Audit Log และรายงานย้อนหลัง"),
    ("partner", 11, "อ่านอย่างเดียวผ่าน API: ข้อมูลสาธารณะเท่านั้น"),
]

DEMO_USERS = [
    ("admin.wanchana", "enviro2026", "admin", "Wanchana (Admin)"),
    ("operator.suda", "enviro2026", "operator", "Suda (Operator)"),
    ("auditor.kritt", "enviro2026", "auditor", "Kritt (Auditor)"),
    ("partner.api", "enviro2026", "partner", "External Partner"),
]

# Real physical hardware node(s) -- see server/routes/nodes.py and
# firmware/prototype_node/prototype_node.ino. `api_key` here is a DEMO
# default for this project's single physical prototype; it and the matching
# NODE_API_KEY #define in the firmware should both be replaced with a real
# secret before the node ever leaves a trusted network. lat/lng default to
# เชียงใหม่ (same as simulated station CNX-118) purely because the node has
# no GPS of its own -- update them (via the DB, or a future admin endpoint)
# to wherever this node is actually installed.
REAL_NODES = [
    # node_id,   name,                                  api_key,                      lat,    lng,    region
    ("PROTO-01", "Prototype-node (Heltec V4 + GY-91)", "enviro-proto-01-demo-key", 18.788, 98.985, "เชียงใหม่"),
]

# 7 simulated "real-shaped" nodes for the สถานีตรวจวัด page -- explicitly
# requested alongside the one genuine PROTO-01 prototype above, at the same
# 7 provinces as STATIONS (the older, separate simulated seismic network),
# so the two agree on where these places are. Marked is_simulated=1 so the
# dashboard can label them honestly rather than passing them off as real
# hardware. Continuously generated by server/node_simulator.py through the
# exact same ingestion/analysis code (routes/nodes.py apply_node_telemetry)
# a genuine HTTP upload goes through -- not static/canned rows; api_key is
# unused for these (the simulator calls apply_node_telemetry() directly,
# bypassing the HTTP auth check entirely) but kept non-empty since the
# column is NOT NULL.
SIMULATED_REAL_NODES = [
    # node_id,        name,                            api_key,                     lat,     lng,      region
    ("SIM-CNX-118", "เชียงใหม่",             "internal-simulated-node", 18.788, 98.985,  "เชียงใหม่"),
    ("SIM-PLK-014", "พิษณุโลก",             "internal-simulated-node", 16.827, 100.259, "พิษณุโลก"),
    ("SIM-TAK-009", "ตาก",                   "internal-simulated-node", 16.877, 99.126,  "ตาก"),
    ("SIM-BKK-201", "กรุงเทพมหานคร (มจพ.)", "internal-simulated-node", 13.756, 100.502, "กรุงเทพฯ"),
    ("SIM-KKN-022", "ขอนแก่น",               "internal-simulated-node", 16.446, 102.833, "ขอนแก่น"),
    ("SIM-CHB-031", "ชลบุรี",                "internal-simulated-node", 13.361, 100.985, "ชลบุรี"),
    ("SIM-SGK-005", "สงขลา",                 "internal-simulated-node", 7.189,  100.595, "สงขลา"),
]


def _ensure_column(conn, table, column, decl):
    """`CREATE TABLE IF NOT EXISTS` (used below) is a no-op once a table
    already exists, so a column added to schema.sql after this project's
    first run would otherwise never reach an already-initialized DB. Adds
    it with ALTER TABLE if missing; harmless/no-op once it's there."""
    cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
        conn.commit()


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    fresh = not os.path.exists(DB_PATH)
    conn = get_conn()
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    _ensure_column(conn, "real_nodes", "is_simulated", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "real_nodes", "paused", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "real_node_log", "accel_x", "REAL")
    _ensure_column(conn, "real_node_log", "accel_y", "REAL")
    _ensure_column(conn, "real_node_log", "accel_z", "REAL")

    if fresh or conn.execute("SELECT COUNT(*) c FROM stations").fetchone()["c"] == 0:
        seed(conn)
    else:
        # `real_nodes` was added after this project's original seed gate
        # above -- an already-initialized DB (stations already populated)
        # would otherwise never get its default row. INSERT OR IGNORE makes
        # this a no-op once the row exists, so it's safe on every startup.
        seed_real_nodes(conn)
    conn.close()


def seed_real_nodes(conn):
    ts = now_iso()
    conn.executemany(
        "INSERT OR IGNORE INTO real_nodes(node_id,name,api_key,lat,lng,region,created_at,is_simulated) VALUES (?,?,?,?,?,?,?,0)",
        [(node_id, name, key, lat, lng, region, ts) for node_id, name, key, lat, lng, region in REAL_NODES],
    )
    conn.executemany(
        "INSERT OR IGNORE INTO real_nodes(node_id,name,api_key,lat,lng,region,created_at,is_simulated) VALUES (?,?,?,?,?,?,?,1)",
        [(node_id, name, key, lat, lng, region, ts) for node_id, name, key, lat, lng, region in SIMULATED_REAL_NODES],
    )
    conn.commit()


def seed(conn):
    ts = now_iso()
    conn.executemany(
        "INSERT OR IGNORE INTO stations(id,region,lat,lng,status,installed_at) VALUES (?,?,?,?, 'online', ?)",
        [(sid, region, lat, lng, ts) for sid, region, lat, lng in STATIONS],
    )
    conn.executemany(
        "INSERT OR IGNORE INTO station_regions(region,total,online) VALUES (?,?,?)",
        STATION_REGIONS,
    )
    conn.executemany(
        "INSERT OR IGNORE INTO fault_lines(name,region,lat1,lng1,lat2,lng2) VALUES (?,?,?,?,?,?)",
        FAULTS,
    )
    conn.executemany(
        "INSERT OR IGNORE INTO levels(lv,name,mmi_min,mmi_max,mmi_roman,severity_desc,mag_ref,pga_min,pga_max,"
        "ai_conf,nodes_min,message,channels,siren,color) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        LEVELS,
    )
    conn.executemany(
        "INSERT OR IGNORE INTO cities(name,lat,lng,mmi_label) VALUES (?,?,?,?)", CITIES
    )
    conn.executemany(
        "INSERT OR IGNORE INTO risk_scores(region,score) VALUES (?,?)", RISK
    )
    conn.execute(
        "INSERT OR IGNORE INTO model_performance(id,version,precision,recall,f1,accuracy,tp,fp,fn,tn) "
        "VALUES (1,'v3.2.1',96.4,94.8,95.6,97.1,1284,47,70,15820)"
    )
    conn.executemany(
        "INSERT OR IGNORE INTO sources_static(name,color_var,depth,latency_sec,confidence,loc_err_km,note,mag_offset) "
        "VALUES (?,?,?,?,?,?,?,?)",
        SOURCES_STATIC,
    )
    conn.executemany(
        "INSERT OR IGNORE INTO services(name,forced_status,note) VALUES (?,?,?)", SERVICES
    )
    conn.executemany(
        "INSERT OR IGNORE INTO roles(role,users_count,permissions) VALUES (?,?,?)", ROLES
    )
    conn.execute(
        "INSERT OR IGNORE INTO detector_config(id,stalta_threshold,pga_calibration) VALUES (1, 3.5, 5.0)"
    )
    conn.execute(
        "INSERT OR IGNORE INTO telegram_config(id,bot_token,chat_id,enabled) VALUES (1, '', '', 0)"
    )
    conn.execute(
        "INSERT OR IGNORE INTO backups(ts,size_bytes,path) VALUES (?,?,?)",
        (ts, 214_000_000_000 // 1000, "seed"),
    )
    for username, password, role, display in DEMO_USERS:
        conn.execute(
            "INSERT OR IGNORE INTO users(username,password_hash,role,display_name) VALUES (?,?,?,?)",
            (username, generate_password_hash(password), role, display),
        )
    seed_real_nodes(conn)
    conn.execute(
        "INSERT INTO audit_log(ts, username, action) VALUES (?, 'system', 'เริ่มต้นระบบและสร้างฐานข้อมูลครั้งแรก')",
        (ts,),
    )
    conn.commit()
