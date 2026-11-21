"""Security Audit & Vulnerability Regression Tests."""
import io
import pytest


def test_csrf_missing_token_rejected(csrf_client):
    """Verifies that state-changing POST requests without CSRF tokens are rejected with 403."""
    res = csrf_client.post("/login", data={
        "username": "existinguser",
        "password": "ValidPass123"
    })
    assert res.status_code == 403
    assert b"Forbidden" in res.data or b"CSRF" in res.data


def test_csrf_invalid_token_rejected(csrf_client):
    """Verifies that an invalid/tampered CSRF token is rejected with 403."""
    # First get a page to initialize a session
    csrf_client.get("/login")
    res = csrf_client.post("/login", data={
        "username": "existinguser",
        "password": "ValidPass123",
        "csrf_token": "tampered_fake_token_value_xyz123"
    })
    assert res.status_code == 403


def test_csrf_valid_token_accepted(csrf_client):
    """Verifies that matching session-bound CSRF token permits request execution."""
    # Initialize session and retrieve valid token
    csrf_client.get("/login")
    with csrf_client.session_transaction() as sess:
        token = sess.get("csrf_token")

    assert token is not None

    res = csrf_client.post("/login", data={
        "username": "existinguser",
        "password": "ValidPass123",
        "csrf_token": token
    }, follow_redirects=False)

    # Should succeed and redirect to home
    assert res.status_code == 302
    assert res.headers["Location"].endswith("/")


def test_password_never_stored_in_plaintext(test_app):
    """Verifies user passwords in SQLite are hashed using secure cryptographic hashes."""
    import sqlite3
    db_path = test_app.config["DATABASE"]
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute("SELECT password FROM users WHERE username = 'existinguser'")
        row = cur.fetchone()

    assert row is not None
    stored_hash = row[0]
    assert stored_hash != "ValidPass123"
    # Werkzeug hashes start with algorithm prefix e.g. 'scrypt:' or 'pbkdf2:'
    assert stored_hash.startswith("scrypt:") or stored_hash.startswith("pbkdf2:")


def test_session_cookie_security_flags(client):
    """Verifies that session cookies are configured with HttpOnly and SameSite."""
    client.post("/login", data={
        "username": "existinguser",
        "password": "ValidPass123"
    })
    # Inspect cookie in jar
    cookie = client.get_cookie("session")
    if cookie:
        assert cookie.http_only is True
        assert cookie.same_site in ("Lax", "Strict")


def test_custom_error_pages_no_stack_traces(client):
    """Verifies error responses return clean HTML pages without internal stack traces."""
    res = client.get("/non_existent_page_404_url")
    assert res.status_code == 404
    assert b"404" in res.data
    assert b"Traceback" not in res.data
    assert b"File \"" not in res.data
