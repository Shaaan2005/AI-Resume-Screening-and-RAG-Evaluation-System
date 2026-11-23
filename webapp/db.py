"""SQLite user store helpers."""
import sqlite3
import logging

from flask import current_app

logger = logging.getLogger("ResumeScreening")


def init_db(path):
    """Creates tables and indexes if missing (safe to run on an existing database)."""
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT UNIQUE, email TEXT, password TEXT)")
        for sql in (
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)",
            # Usernames are unique regardless of case ("Shaan1" and "SHAAN1" are the same user)
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username_nocase ON users(username COLLATE NOCASE)",
        ):
            try:
                conn.execute(sql)
            except Exception as e:
                logger.warning(f"Index creation warning: {e}")
        # Each user's own upload history (replaces the old shared recent_analyses.json)
        conn.execute("""CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            score REAL NOT NULL,
            recommendation TEXT NOT NULL,
            created_at TEXT NOT NULL)""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_analyses_user ON analyses(user_id, id)")
        # Failed logins, kept in the database so the lockout survives restarts and
        # is shared by every server process (gunicorn workers).
        conn.execute("""CREATE TABLE IF NOT EXISTS login_failures (
            ip TEXT NOT NULL,
            username TEXT NOT NULL,
            at REAL NOT NULL)""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_login_failures ON login_failures(ip, username, at)")
        conn.commit()


def connect():
    """Opens a connection to the configured user database."""
    return sqlite3.connect(current_app.config["DATABASE"])
