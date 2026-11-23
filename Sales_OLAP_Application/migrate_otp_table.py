"""
migrate_otp_table.py — Add otp_attempts table and phone column to app_users.
Run once; safe to re-run (IF NOT EXISTS guards).
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "pharmatrack_dw.sqlite"

def run():
    con = sqlite3.connect(str(DB_PATH))
    con.execute("PRAGMA foreign_keys = ON;")
    cur = con.cursor()

    # 1. Add otp_attempts table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS otp_attempts (
            attempt_id      TEXT PRIMARY KEY,
            user_id         INTEGER NOT NULL,
            otp_hash        TEXT NOT NULL,
            created_at      TEXT NOT NULL,
            expires_at      TEXT NOT NULL,
            verified        INTEGER DEFAULT 0,
            attempts        INTEGER DEFAULT 0,
            channel         TEXT DEFAULT 'email',
            message_id      TEXT,
            delivery_status TEXT DEFAULT 'pending',
            destination_masked TEXT
        )
    """)
    print("otp_attempts table: OK")

    # 2. Add phone column to app_users if missing
    cols = [r[1] for r in cur.execute("PRAGMA table_info(app_users)").fetchall()]
    if "phone" not in cols:
        cur.execute("ALTER TABLE app_users ADD COLUMN phone TEXT DEFAULT NULL")
        print("app_users.phone column: added")
    else:
        print("app_users.phone column: already exists")

    con.commit()
    con.close()
    print("Migration complete.")

if __name__ == "__main__":
    run()
