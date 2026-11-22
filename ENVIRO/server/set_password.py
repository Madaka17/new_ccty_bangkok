"""Set the password of an existing ENVIRO account.

Run from ENVIRO/:  python -m server.set_password <username>
"""
import getpass
import sys

from werkzeug.security import generate_password_hash

from . import db as dbmod

MIN_LENGTH = 12


def set_password(username, password):
    """Store a new hash for `username`. Returns False when no such user exists."""
    conn = dbmod.get_conn()
    try:
        cur = conn.execute(
            "UPDATE users SET password_hash=? WHERE username=?",
            (generate_password_hash(password), username),
        )
        if cur.rowcount != 1:
            conn.rollback()
            return False
        conn.execute(
            "INSERT INTO audit_log(ts, username, action) VALUES (?, 'system', ?)",
            (dbmod.now_iso(), f"เปลี่ยนรหัสผ่านของ {username} แล้ว"),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python -m server.set_password <username>", file=sys.stderr)
        return 2
    username = args[0]
    first = getpass.getpass("New password: ")
    second = getpass.getpass("Repeat new password: ")
    if first != second:
        print("The two passwords do not match.", file=sys.stderr)
        return 1
    if len(first) < MIN_LENGTH:
        print(f"The password must be at least {MIN_LENGTH} characters.", file=sys.stderr)
        return 1
    if not set_password(username, first):
        print(f"No user named {username!r}.", file=sys.stderr)
        return 1
    print(f"Password for {username} changed.")
    print("หมายเหตุ: session ที่ล็อกอินอยู่แล้วยังใช้ได้จนกว่าจะรีสตาร์ท ENVIRO server กรุณารีสตาร์ท ENVIRO server")
    return 0


if __name__ == "__main__":
    sys.exit(main())
