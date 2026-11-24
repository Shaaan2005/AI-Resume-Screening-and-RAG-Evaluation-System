"""Login, registration, and logout routes."""
import re
import time
import sqlite3
import logging

from flask import Blueprint, request, render_template, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash

from .db import connect

logger = logging.getLogger("ResumeScreening")

bp = Blueprint("auth", __name__)

# Login throttling: after MAX_FAILURES failed attempts for the same username from the
# same IP within WINDOW seconds, further attempts are refused until the window passes.
# Stored in the database (login_failures), so restarts and multiple workers can't reset it.
MAX_FAILURES = 5
WINDOW = 15 * 60


def _attempt_key(username):
    return (request.remote_addr or "?", username.lower())


def _recent_failures(key):
    with connect() as conn:
        conn.execute("DELETE FROM login_failures WHERE at < ?", (time.time() - WINDOW,))
        conn.commit()
        return conn.execute("SELECT COUNT(*) FROM login_failures WHERE ip = ? AND username = ?",
                            key).fetchone()[0]


def _record_failure(key):
    with connect() as conn:
        conn.execute("INSERT INTO login_failures (ip, username, at) VALUES (?, ?, ?)", (*key, time.time()))
        conn.commit()


def _clear_failures(key):
    with connect() as conn:
        conn.execute("DELETE FROM login_failures WHERE ip = ? AND username = ?", key)
        conn.commit()


@bp.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("search.home"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        key = _attempt_key(username)
        if not username or not password:
            error = "Username and password are required"
        elif _recent_failures(key) >= MAX_FAILURES:
            logger.warning(f"Login throttled for '{username}' from {request.remote_addr}")
            error = "Too many failed attempts. Please wait 15 minutes and try again."
        else:
            try:
                with connect() as conn:
                    # Usernames are case-insensitive, matching how registration checks them
                    cur = conn.execute("SELECT id, username, password FROM users WHERE username = ? COLLATE NOCASE",
                                       (username,))
                    row = cur.fetchone()
                if row and check_password_hash(row[2], password):
                    _clear_failures(key)
                    session.clear()  # fresh session on login
                    session["user_id"] = row[0]
                    session["username"] = row[1]
                    session.permanent = True
                    logger.info(f"User '{row[1]}' logged in successfully.")
                    return redirect(url_for("search.home"))
                _record_failure(key)
                error = "Invalid username or password"
            except Exception as e:
                logger.error(f"Login database error: {e}")
                error = "An error occurred during login. Please try again."

    return render_template("login.html", error=error)


@bp.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("search.home"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        # 1. Field presence validation
        if not username or not email or not password:
            error = "All fields are required"
        # 2. Username format validation (alphanumeric, underscores, hyphens, 3-30 chars)
        elif not re.match(r'^[a-zA-Z0-9_-]{3,30}$', username):
            error = "Username must be 3-30 characters and contain only letters, numbers, underscores, or hyphens."
        # 3. Email format validation
        elif not re.match(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$', email) or len(email) > 254:
            error = "Please enter a valid email address."
        # 4. Password strength enforcement (min 8 chars, at least 1 letter, at least 1 digit)
        elif len(password) < 8 or not re.search(r'[A-Za-z]', password) or not re.search(r'[0-9]', password):
            error = "Password must be at least 8 characters long and contain both letters and numbers."
        else:
            try:
                with connect() as conn:
                    cur = conn.execute("SELECT id FROM users WHERE username = ? COLLATE NOCASE", (username,))
                    if cur.fetchone():
                        error = "Username already taken"
                    else:
                        cur = conn.execute("SELECT id FROM users WHERE email = ? COLLATE NOCASE", (email,))
                        if cur.fetchone():
                            error = "Email address is already registered"
                        else:
                            hashed_pw = generate_password_hash(password)
                            conn.execute(
                                "INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
                                (username, email, hashed_pw)
                            )
                            conn.commit()
                            cur = conn.execute("SELECT id FROM users WHERE username = ?", (username,))
                            session.clear()  # fresh session on sign-up, as on login
                            session["user_id"] = cur.fetchone()[0]
                            session["username"] = username
                            session.permanent = True
                            logger.info(f"New user registered: {username} ({email})")
                            return redirect(url_for("search.home"))
            except sqlite3.IntegrityError:
                error = "Username or email is already registered"
            except Exception as e:
                logger.error(f"Registration error: {e}")
                error = "Registration failed due to a server error. Please try again."

    return render_template("register.html", error=error)


@bp.route("/logout", methods=["POST"])
def logout():
    """POST-only (with the CSRF check every POST gets), so other sites can't log you out."""
    session.clear()
    return redirect(url_for("auth.login"))
