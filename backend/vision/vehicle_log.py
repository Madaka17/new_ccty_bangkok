import sqlite3
import threading
from datetime import datetime, timedelta


class VehicleLog:
    """Hourly count of vehicles that passed each camera, persisted in SQLite."""

    def __init__(self, path):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS hourly (
                hour        TEXT NOT NULL,   -- local time, 'YYYY-MM-DDTHH:00'
                camid       TEXT NOT NULL,
                title       TEXT,
                cars        INTEGER NOT NULL DEFAULT 0,
                motorcycles INTEGER NOT NULL DEFAULT 0,
                trucks      INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (hour, camid)
            )""")
        # Short round-robin samples from the survey; hourly counts for these cameras are
        # estimated on read as passed / seconds * 3600
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS samples (
                ts          INTEGER NOT NULL,   -- unix seconds
                hour        TEXT NOT NULL,
                camid       TEXT NOT NULL,
                title       TEXT,
                seconds     REAL NOT NULL,
                cars        INTEGER NOT NULL DEFAULT 0,
                motorcycles INTEGER NOT NULL DEFAULT 0,
                trucks      INTEGER NOT NULL DEFAULT 0,
                visible     REAL,
                moving_pct  INTEGER,
                level       TEXT
            )""")
        self.conn.execute("CREATE INDEX IF NOT EXISTS samples_hour ON samples (hour, camid)")
        # Camera-detected incidents (accident / breakdown) confirmed by vision
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS incidents (
                id          TEXT PRIMARY KEY,
                ts          INTEGER NOT NULL,
                cleared_ts  INTEGER,
                camid       TEXT NOT NULL,
                title       TEXT,
                latitude    REAL,
                longitude   REAL,
                kind        TEXT NOT NULL,
                confidence  REAL,
                description TEXT,
                stopped_s   INTEGER,
                persons_near INTEGER
            )""")
        # Manual-vs-AI accuracy checks entered on the live page
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS accuracy_checks (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                ts           INTEGER NOT NULL,
                camid        TEXT NOT NULL,
                title        TEXT,
                manual_count INTEGER NOT NULL,
                ai_count     INTEGER NOT NULL,
                abs_error    INTEGER NOT NULL,
                accuracy_pct REAL,
                duration_s   INTEGER,
                note         TEXT
            )""")
        self.conn.commit()

    @staticmethod
    def _hour(dt=None):
        return (dt or datetime.now()).strftime('%Y-%m-%dT%H:00')

    # ------------------------------------------------------------------ accuracy checks
    @staticmethod
    def _accuracy(manual, ai):
        """Absolute error and accuracy (%) of the AI count against the manual count."""
        err = abs(int(manual) - int(ai))
        if manual <= 0:
            acc = 100.0 if err == 0 else 0.0
        else:
            acc = max(0.0, 100.0 - err * 100.0 / manual)
        return err, round(acc, 1)

    def add_accuracy_check(self, camid, title, manual_count, ai_count, duration_s=None, note=None):
        err, acc = self._accuracy(manual_count, ai_count)
        with self.lock:
            cur = self.conn.execute(
                "INSERT INTO accuracy_checks (ts, camid, title, manual_count, ai_count, abs_error, accuracy_pct, duration_s, note) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (int(datetime.now().timestamp()), camid, title, int(manual_count), int(ai_count), err, acc, duration_s, note))
            self.conn.commit()
            return self._accuracy_row(cur.lastrowid)

    def _accuracy_row(self, rid):
        r = self.conn.execute("SELECT id, ts, camid, title, manual_count, ai_count, abs_error, accuracy_pct, duration_s, note "
                              "FROM accuracy_checks WHERE id = ?", (rid,)).fetchone()
        return self._accuracy_dict(r) if r else None

    @staticmethod
    def _accuracy_dict(r):
        return {'id': r[0], 'ts': r[1], 'camid': r[2], 'title': r[3], 'manual_count': r[4], 'ai_count': r[5],
                'abs_error': r[6], 'accuracy_pct': r[7], 'duration_s': r[8], 'note': r[9]}

    def delete_accuracy_check(self, rid):
        with self.lock:
            n = self.conn.execute("DELETE FROM accuracy_checks WHERE id = ?", (rid,)).rowcount
            self.conn.commit()
        return n > 0

    def accuracy_checks(self, limit=50):
        """Latest checks plus the summary row: MAE, mean accuracy, totals."""
        with self.lock:
            rows = self.conn.execute(
                "SELECT id, ts, camid, title, manual_count, ai_count, abs_error, accuracy_pct, duration_s, note "
                "FROM accuracy_checks ORDER BY ts DESC, id DESC LIMIT ?", (limit,)).fetchall()
        items = [self._accuracy_dict(r) for r in rows]
        n = len(items)
        summary = None
        if n:
            manual = sum(i['manual_count'] for i in items)
            ai = sum(i['ai_count'] for i in items)
            mae = sum(i['abs_error'] for i in items) / n
            summary = {
                'count': n,
                'manual_total': manual,
                'ai_total': ai,
                'mae': round(mae, 1),
                'mean_accuracy_pct': round(sum(i['accuracy_pct'] or 0 for i in items) / n, 1),
                'overall_accuracy_pct': self._accuracy(manual, ai)[1],
            }
        return {'items': items, 'summary': summary}

    def add(self, camid, title, cars=0, motorcycles=0, trucks=0):
        if not camid or not (cars or motorcycles or trucks):
            return
        with self.lock:
            self.conn.execute("""
                INSERT INTO hourly (hour, camid, title, cars, motorcycles, trucks)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(hour, camid) DO UPDATE SET
                    title = excluded.title,
                    cars = cars + excluded.cars,
                    motorcycles = motorcycles + excluded.motorcycles,
                    trucks = trucks + excluded.trucks
                """, (self._hour(), camid, title, cars, motorcycles, trucks))
            self.conn.commit()

    def add_sample(self, sm):
        with self.lock:
            self.conn.execute("""
                INSERT INTO samples (ts, hour, camid, title, seconds, cars, motorcycles, trucks, visible, moving_pct, level)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (sm['ts'], self._hour(), sm['camid'], sm['title'], sm['seconds'], sm['cars'], sm['motorcycles'],
                 sm['trucks'], sm['visible'], sm['moving_pct'], sm['level']))
            # keep 60 days
            self.conn.execute("DELETE FROM samples WHERE ts < ?", (sm['ts'] - 60 * 86400,))
            self.conn.commit()

    def latest_samples(self):
        """Most recent sample per camera, as dicts shaped like SurveyManager samples."""
        with self.lock:
            rows = self.conn.execute("""
                SELECT s.ts, s.camid, s.title, s.seconds, s.cars, s.motorcycles, s.trucks, s.visible, s.moving_pct, s.level
                FROM samples s JOIN (SELECT camid, MAX(ts) AS ts FROM samples GROUP BY camid) m
                  ON m.camid = s.camid AND m.ts = s.ts""").fetchall()
        out = []
        for ts, camid, title, sec, c, m, t, vis, mov, lvl in rows:
            out.append({'camid': camid, 'title': title, 'ts': ts, 'seconds': sec, 'cars': c, 'motorcycles': m,
                        'trucks': t, 'passed': c + m + t, 'rate_per_min': round((c + m + t) * 60.0 / max(1.0, sec), 1),
                        'visible': vis, 'moving_pct': mov, 'level': lvl, 'error': ''})
        return out

    def add_incident(self, inc):
        with self.lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO incidents (id, ts, camid, title, latitude, longitude, kind, confidence, description, stopped_s, persons_near)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (inc['id'], inc['ts'], inc['camid'], inc['title'], inc.get('latitude'), inc.get('longitude'),
                 inc['kind'], inc.get('confidence'), inc.get('description'), inc.get('stopped_s'), inc.get('persons_near')))
            self.conn.commit()

    def clear_incident(self, incident_id):
        with self.lock:
            self.conn.execute("UPDATE incidents SET cleared_ts = ? WHERE id = ?", (int(datetime.now().timestamp()), incident_id))
            self.conn.commit()

    def active_incidents(self, max_age=45 * 60):
        """Incidents not yet cleared and younger than max_age (restart recovery)."""
        since = int(datetime.now().timestamp()) - max_age
        with self.lock:
            rows = self.conn.execute("""SELECT id, ts, camid, title, latitude, longitude, kind, confidence, description, stopped_s, persons_near
                                        FROM incidents WHERE cleared_ts IS NULL AND ts >= ?""", (since,)).fetchall()
        return [{'id': r[0], 'source': 'camera', 'ts': r[1], 'last_seen': r[1], 'camid': r[2], 'title': r[3], 'latitude': r[4],
                 'longitude': r[5], 'kind': r[6], 'confidence': r[7], 'description': r[8], 'stopped_s': r[9],
                 'persons_near': r[10], 'image': f"/api/incidents/{r[0]}/image"} for r in rows]

    def recent_incidents(self, hours=24):
        """Camera incidents (active and cleared) from the last `hours`, newest first."""
        since = int(datetime.now().timestamp()) - hours * 3600
        with self.lock:
            rows = self.conn.execute("""SELECT id, ts, cleared_ts, camid, title, latitude, longitude, kind, confidence, description, stopped_s, persons_near
                                        FROM incidents WHERE ts >= ? ORDER BY ts DESC""", (since,)).fetchall()
        return [{'id': r[0], 'source': 'camera', 'ts': r[1], 'cleared_ts': r[2], 'camid': r[3], 'title': r[4],
                 'latitude': r[5], 'longitude': r[6], 'kind': r[7], 'confidence': r[8], 'description': r[9],
                 'stopped_s': r[10], 'persons_near': r[11], 'image': f"/api/incidents/{r[0]}/image"} for r in rows]

    def history(self, range_='24h', date=None, camid=None):
        """Per-camera totals plus a time series.

        range_: '24h' -> hourly buckets for the last 24 hours (default)
                '7d' / '30d' -> daily buckets
        date:   'YYYY-MM-DD' -> hourly buckets for that day (overrides range_)
        Returns {'bucket': 'hour'|'day', 'keys': [...], 'cameras': [...]}; each camera has
        'series': {key: {cars, motorcycles, trucks, total}} so the client can draw bars in order.
        """
        now = datetime.now()
        if date:
            day = datetime.strptime(date, '%Y-%m-%d')
            bucket = 'hour'
            keys = [self._hour(day + timedelta(hours=h)) for h in range(24)]
            lo, hi = keys[0], keys[-1]
            key_of = lambda hour: hour
        elif range_ in ('7d', '30d'):
            days = 7 if range_ == '7d' else 30
            bucket = 'day'
            start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
            keys = [(start + timedelta(days=d)).strftime('%Y-%m-%d') for d in range(days)]
            lo, hi = self._hour(start), self._hour(now)
            key_of = lambda hour: hour[:10]
        else:
            bucket = 'hour'
            start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=23)
            keys = [self._hour(start + timedelta(hours=h)) for h in range(24)]
            lo, hi = keys[0], keys[-1]
            key_of = lambda hour: hour

        sql = "SELECT hour, camid, title, cars, motorcycles, trucks FROM hourly WHERE hour >= ? AND hour <= ?"
        args = [lo, hi]
        if camid:
            sql += " AND camid = ?"
            args.append(camid)
        est_sql = ("SELECT hour, camid, MAX(title), SUM(cars), SUM(motorcycles), SUM(trucks), SUM(seconds) "
                   "FROM samples WHERE hour >= ? AND hour <= ?" + (" AND camid = ?" if camid else "") +
                   " GROUP BY hour, camid ORDER BY hour")
        with self.lock:
            rows = self.conn.execute(sql + " ORDER BY hour", args).fetchall()
            est_rows = self.conn.execute(est_sql, args).fetchall()

        cams = {}
        real = set()

        def add(hour, cid, title, c, m, t, est):
            cam = cams.setdefault(cid, {'camid': cid, 'title': title, 'cars': 0, 'motorcycles': 0, 'trucks': 0,
                                        'total': 0, 'estimated': False, 'series': {}})
            cam['title'] = title or cam['title']
            cam['cars'] += c
            cam['motorcycles'] += m
            cam['trucks'] += t
            cam['total'] += c + m + t
            cam['estimated'] = cam['estimated'] or est
            b = cam['series'].setdefault(key_of(hour), {'cars': 0, 'motorcycles': 0, 'trucks': 0, 'total': 0, 'est': False})
            b['cars'] += c
            b['motorcycles'] += m
            b['trucks'] += t
            b['total'] += c + m + t
            b['est'] = b['est'] or est

        for hour, cid, title, c, m, t in rows:
            real.add((hour, cid))
            add(hour, cid, title, c, m, t, False)
        # Survey estimates fill hours that have no continuous count for that camera
        for hour, cid, title, c, m, t, sec in est_rows:
            if (hour, cid) in real or not sec:
                continue
            k = 3600.0 / sec
            add(hour, cid, title, round(c * k), round(m * k), round(t * k), True)
        items = sorted(cams.values(), key=lambda x: x['total'], reverse=True)
        return {'bucket': bucket, 'keys': keys, 'current_hour': self._hour(now), 'cameras': items}
