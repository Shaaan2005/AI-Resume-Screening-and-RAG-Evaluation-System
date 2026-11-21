"""Recent-analyses history shown on the home page (last 10 uploads)."""
import os
import json
import logging

from flask import current_app

logger = logging.getLogger("ResumeScreening")


def load_history():
    path = current_app.config["HISTORY_FILE"]
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError, OSError):
            return []
    return []


def save_history(entry):
    try:
        history = load_history()
        history.insert(0, entry)
        history = history[:10]
        with open(current_app.config["HISTORY_FILE"], "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not persist history: {e}")
