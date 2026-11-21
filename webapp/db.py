"""SQLite user store helpers."""
import sqlite3
import logging

from flask import current_app

logger = logging.getLogger("ResumeScreening")


def init_db(path):
    """Creates the users table and unique email index if missing."""
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT UNIQUE, email TEXT, password TEXT)")
        try:
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        except Exception as e:
            logger.warning(f"Index creation warning: {e}")
        conn.commit()


def connect():
    """Opens a connection to the configured user database."""
    return sqlite3.connect(current_app.config["DATABASE"])
