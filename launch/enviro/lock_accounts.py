"""Replaces ENVIRO's published demo secrets before it goes online.

ENVIRO seeds four demo accounts with the password "enviro2026" and the PROTO-01 node with
"enviro-proto-01-demo-key", and both are printed in its README on GitHub. start.bat runs this before
every start, so a fresh database (deleting data\\enviro.db reseeds the demo values) is locked again too.
Each new password or node key is appended to ENVIRO\\data\\accounts.txt, which git ignores.
"""
import os
import secrets
import sys
from datetime import datetime

ENVIRO_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "ENVIRO"))
sys.path.insert(0, ENVIRO_DIR)

from werkzeug.security import check_password_hash, generate_password_hash  # noqa: E402

from server import db as dbmod  # noqa: E402

DEMO_PASSWORD = "enviro2026"
ACCOUNTS_FILE = os.path.join(ENVIRO_DIR, "data", "accounts.txt")


def main():
    dbmod.init_db()
    conn = dbmod.get_conn()
    lines = []

    for row in conn.execute("SELECT username, password_hash FROM users ORDER BY username").fetchall():
        if check_password_hash(row["password_hash"], DEMO_PASSWORD):
            password = secrets.token_urlsafe(12)
            conn.execute("UPDATE users SET password_hash=? WHERE username=?",
                         (generate_password_hash(password), row["username"]))
            lines.append(f"{row['username']:<20} password   {password}")

    for node_id, _name, demo_key, *_ in dbmod.REAL_NODES:
        row = conn.execute("SELECT api_key FROM real_nodes WHERE node_id=?", (node_id,)).fetchone()
        if row and row["api_key"] == demo_key:
            key = secrets.token_urlsafe(24)
            conn.execute("UPDATE real_nodes SET api_key=? WHERE node_id=?", (key, node_id))
            lines.append(f"{node_id:<20} X-Node-Key {key}")

    conn.commit()
    conn.close()

    if not lines:
        print("[*] Demo accounts are already locked. Logins: ENVIRO\\data\\accounts.txt")
        return
    with open(ACCOUNTS_FILE, "a", encoding="utf-8") as f:
        f.write(f"# {datetime.now():%Y-%m-%d %H:%M} demo secrets replaced by launch\\enviro\\lock_accounts.py\n")
        f.write("\n".join(lines) + "\n\n")
    print(f"[*] Replaced {len(lines)} demo secrets. New logins: ENVIRO\\data\\accounts.txt")


if __name__ == "__main__":
    main()
