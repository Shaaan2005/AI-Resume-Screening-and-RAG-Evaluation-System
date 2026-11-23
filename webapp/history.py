"""Each user's recent analyses, shown on their home page (last 10 uploads)."""
import logging
from datetime import datetime

from .db import connect

logger = logging.getLogger("ResumeScreening")


def load_history(user_id, limit=10):
    """The user's most recent analyses, newest first. Other users' uploads never appear."""
    if user_id is None:
        return []
    try:
        with connect() as conn:
            rows = conn.execute(
                "SELECT filename, score, recommendation, created_at FROM analyses "
                "WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit)).fetchall()
    except Exception as e:
        logger.warning(f"Could not load history: {e}")
        return []
    return [{"filename": f, "score": s, "recommendation": r, "timestamp": t} for f, s, r, t in rows]


def save_history(user_id, filename, score, recommendation):
    """Records one analysis. `score` and `recommendation` must be the pair shown to the user."""
    try:
        with connect() as conn:
            conn.execute(
                "INSERT INTO analyses (user_id, filename, score, recommendation, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, filename, round(float(score), 2), recommendation,
                 datetime.now().strftime("%d %b %Y, %I:%M %p")))
            conn.commit()
    except Exception as e:
        logger.warning(f"Could not save history: {e}")
