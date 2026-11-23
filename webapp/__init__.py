"""Flask application factory for the AI Resume Screening web app."""
import os
import logging
from datetime import timedelta

from flask import Flask

from scoring import band
from .db import init_db
from .security import get_or_create_secret_key, register_security

# Project folder: all data paths resolve against it, so starting the app from
# another directory never creates fresh, empty copies of the database or uploads.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(os.path.join(ROOT, "app.log"), encoding="utf-8"),
        ],
    )


def create_app(config=None):
    """Builds the Flask app. `config` overrides defaults (used by tests)."""
    _configure_logging()

    root = ROOT
    app = Flask(__name__, template_folder=os.path.join(root, "templates"))

    app.secret_key = get_or_create_secret_key()
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16 MB max upload limit
        DATABASE=os.path.join(root, "users.db"),
        UPLOAD_FOLDER=os.path.join(root, "uploads"),
        BENCHMARK_RESULTS=os.path.join(root, "benchmark", "results.json"),
        # Public-demo mode (DEMO_MODE=1): uploaded resumes are scored but never
        # added to the shared search index, the recent-uploads list, or disk.
        DEMO_MODE=os.environ.get("DEMO_MODE", "0") == "1",
    )
    if app.config["DEMO_MODE"]:
        # Public visitors get their own account database, separate from local users.
        # Cookies: Hugging Face shows the app inside an iframe, where SameSite=Lax
        # cookies are dropped and login would silently fail; Secure needs HTTPS,
        # which every public host and tunnel provides.
        app.config.update(DATABASE=os.path.join(root, "demo_users.db"),
                          SESSION_COOKIE_SAMESITE="None", SESSION_COOKIE_SECURE=True)
    if config:
        app.config.update(config)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    init_db(app.config["DATABASE"])

    register_security(app)
    app.jinja_env.globals["score_band"] = band  # score colour, consistent with the recommendation

    from .auth import bp as auth_bp
    from .search import bp as search_bp
    from .upload import bp as upload_bp
    from .evaluate import bp as evaluate_bp

    for bp in (auth_bp, search_bp, upload_bp, evaluate_bp):
        app.register_blueprint(bp)

    return app
