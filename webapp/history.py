"""Each user's analyses: listed on their home page, reopenable and deletable."""
import json
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
                "SELECT id, filename, score, recommendation, created_at, details IS NOT NULL FROM analyses "
                "WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit)).fetchall()
    except Exception as e:
        logger.warning(f"Could not load history: {e}")
        return []
    return [{"id": i, "filename": f, "score": s, "recommendation": r, "timestamp": t, "can_open": bool(d)}
            for i, f, s, r, t, d in rows]


def save_history(user_id, filename, score, recommendation, details=None):
    """Records one analysis and returns its id (None if it couldn't be saved).

    `score` and `recommendation` must be the pair shown to the user; `details` is the
    result page's data, kept so the analysis can be reopened. Analysing the same file
    against the same job description again replaces the earlier row.
    """
    try:
        with connect() as conn:
            if details:
                for row_id, old in conn.execute(
                        "SELECT id, details FROM analyses WHERE user_id = ? AND filename = ? AND details IS NOT NULL",
                        (user_id, filename)).fetchall():
                    if json.loads(old).get("job_description") == details.get("job_description"):
                        conn.execute("DELETE FROM analyses WHERE id = ?", (row_id,))
            cur = conn.execute(
                "INSERT INTO analyses (user_id, filename, score, recommendation, created_at, details) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, filename, round(float(score), 2), recommendation,
                 datetime.now().strftime("%d %b %Y, %I:%M %p"), json.dumps(details) if details else None))
            conn.commit()
            return cur.lastrowid
    except Exception as e:
        logger.warning(f"Could not save history: {e}")
        return None


def load_analysis(user_id, analysis_id):
    """One of the user's own saved analyses as (details, created_at), or None."""
    with connect() as conn:
        row = conn.execute("SELECT details, created_at FROM analyses WHERE id = ? AND user_id = ?",
                           (analysis_id, user_id)).fetchone()
    if not row or not row[0]:
        return None
    return json.loads(row[0]), row[1]


def delete_analysis(user_id, analysis_id):
    """Deletes one of the user's own analyses; returns whether one was deleted."""
    with connect() as conn:
        n = conn.execute("DELETE FROM analyses WHERE id = ? AND user_id = ?", (analysis_id, user_id)).rowcount
        conn.commit()
    return n > 0
