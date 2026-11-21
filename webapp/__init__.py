"""Flask application factory for the AI Resume Screening web app."""
import os
import logging
from datetime import timedelta

from flask import Flask

from .db import init_db
from .security import get_or_create_secret_key, register_security


def _configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("app.log", encoding="utf-8"),
        ],
    )


def create_app(config=None):
    """Builds the Flask app. `config` overrides defaults (used by tests)."""
    _configure_logging()

    # Templates live at the repo root, one level above this package.
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app = Flask(__name__, template_folder=os.path.join(root, "templates"))

    app.secret_key = get_or_create_secret_key()
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16 MB max upload limit
        DATABASE="users.db",
        UPLOAD_FOLDER="uploads",
        HISTORY_FILE="recent_analyses.json",
        BENCHMARK_RESULTS=os.path.join(root, "benchmark", "results.json"),
    )
    if config:
        app.config.update(config)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    init_db(app.config["DATABASE"])

    register_security(app)

    from .auth import bp as auth_bp
    from .search import bp as search_bp
    from .upload import bp as upload_bp
    from .evaluate import bp as evaluate_bp

    for bp in (auth_bp, search_bp, upload_bp, evaluate_bp):
        app.register_blueprint(bp)

    return app
