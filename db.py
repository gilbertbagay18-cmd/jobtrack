import os
import sqlite3

def get_db():
    conn = sqlite3.connect(os.environ.get("DATABASE_PATH", "jobtrack.db"))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company TEXT NOT NULL,
        position TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Applied',
        date_applied TEXT,
        job_description TEXT,
        notes TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS password_resets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        token_hash TEXT NOT NULL UNIQUE,
        expires_at TEXT NOT NULL,
        used_at TEXT,
        created_at TEXT NOT NULL)""")
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(applications)")]
    for col, typ in (("interview_at", "TEXT"), ("location", "TEXT"), ("user_id", "INTEGER")):
        if col not in cols:
            conn.execute("ALTER TABLE applications ADD COLUMN " + col + " " + typ)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_apps_user ON applications(user_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_resets_user ON password_resets(user_id)")
    conn.commit()
    conn.close()
