"""Secret key, CSRF protection, error pages, current-user injection, and login_required."""
import os
import secrets
import logging
from functools import wraps

from werkzeug.exceptions import HTTPException
from flask import request, render_template, abort, redirect, url_for, session, current_app

from .db import connect

logger = logging.getLogger("ResumeScreening")

SECRET_KEY_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".secret_key")


def get_or_create_secret_key():
    """Uses FLASK_SECRET_KEY if set, else a persisted random key in .secret_key."""
    env_key = os.environ.get("FLASK_SECRET_KEY")
    if env_key:
        return env_key
    if os.path.exists(SECRET_KEY_FILE):
        try:
            with open(SECRET_KEY_FILE, "r", encoding="utf-8") as f:
                key = f.read().strip()
                if len(key) >= 32:
                    return key
        except Exception:
            pass
    # Generate and persist a cryptographic 32-byte key
    new_key = secrets.token_hex(32)
    try:
        with open(SECRET_KEY_FILE, "w", encoding="utf-8") as f:
            f.write(new_key)
    except Exception as e:
        logger.warning(f"Could not persist secret key to {SECRET_KEY_FILE}: {e}")
    return new_key


def get_or_create_csrf_token():
    """Retrieves or creates a session-bound CSRF token."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def _inject_csrf_and_user():
    user = None
    if "user_id" in session:
        try:
            with connect() as conn:
                cur = conn.execute("SELECT id, username, email FROM users WHERE id = ?", (session["user_id"],))
                row = cur.fetchone()
                if row:
                    user = {"id": row[0], "username": row[1], "email": row[2]}
        except Exception as e:
            logger.error(f"Error querying current user: {e}")
    return {
        "user": user,
        "csrf_token": get_or_create_csrf_token
    }


def _csrf_protect():
    """Enforces CSRF token validation on all state-changing requests."""
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        # Allow disabling CSRF in test environments
        if current_app.config.get("TESTING") and not current_app.config.get("WTF_CSRF_ENABLED", True):
            return None

        sent_token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        session_token = session.get("csrf_token")

        if not session_token or not sent_token or not secrets.compare_digest(str(sent_token), str(session_token)):
            logger.warning(f"CSRF validation failed for {request.path} from IP {request.remote_addr}")
            # Usually a page left open until the session expired (8 hours), or opened before
            # a log-out in another tab: explain how to recover instead of a bare 403.
            return _error_page(403, "Page Expired",
                               "This page was open too long or your session ended, so the form can't be "
                               "sent. Go back, refresh the page, and try again.")


def _error_page(code, title, message):
    return render_template("error.html", code=code, title=title, message=message), code


# Pages only load their own scripts/styles plus Google Fonts.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data:; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)


def _security_headers(response):
    response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    return response


def register_security(app):
    """Wires CSRF, security headers, the template context, and custom error pages into `app`."""
    app.context_processor(_inject_csrf_and_user)
    app.before_request(_csrf_protect)
    app.after_request(_security_headers)

    @app.errorhandler(HTTPException)
    def other_http_error(e):
        # Every other status (405, 429, ...) gets the same styled page as 403/404
        return _error_page(e.code or 500, e.name, e.description or "")

    @app.errorhandler(400)
    def bad_request_error(e):
        return _error_page(400, "Bad Request",
                           getattr(e, "description", "The server could not understand the request."))

    @app.errorhandler(403)
    def forbidden_error(e):
        return _error_page(403, "Forbidden",
                           getattr(e, "description", "You do not have permission to access this resource."))

    @app.errorhandler(404)
    def not_found_error(e):
        return _error_page(404, "Page Not Found",
                           getattr(e, "description", "The requested resource could not be found."))

    @app.errorhandler(413)
    def request_entity_too_large(e):
        return _error_page(413, "File Too Large",
                           "The uploaded file exceeds the 16MB limit. Please upload a smaller resume.")

    @app.errorhandler(500)
    def internal_server_error(e):
        logger.error(f"Internal 500 error encountered: {e}")
        return _error_page(500, "Internal Server Error",
                           "An unexpected error occurred. Please try again later.")
