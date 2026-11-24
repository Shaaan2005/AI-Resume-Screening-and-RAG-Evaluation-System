"""Tests for Authentication & Session Management."""
import pytest


def test_register_success(client):
    """Verifies that a valid user can successfully register and is redirected to home."""
    res = client.post("/register", data={
        "username": "newdeveloper",
        "email": "newdev@domain.com",
        "password": "Password123"
    }, follow_redirects=False)

    assert res.status_code == 302
    assert res.headers["Location"].endswith("/")


def test_register_duplicate_username(client):
    """Verifies that duplicate usernames are rejected."""
    res = client.post("/register", data={
        "username": "existinguser",
        "email": "different@example.com",
        "password": "Password123"
    })
    assert res.status_code == 200
    assert b"Username already taken" in res.data


def test_register_duplicate_email(client):
    """Verifies that duplicate emails are rejected."""
    res = client.post("/register", data={
        "username": "anotheruniqueuser",
        "email": "existing@example.com",
        "password": "Password123"
    })
    assert res.status_code == 200
    assert b"Email address is already registered" in res.data or b"already registered" in res.data


def test_register_invalid_email(client):
    """Verifies that invalid email formats are rejected by regex validation."""
    invalid_emails = [
        "notanemail",
        "missingatsign.com",
        "@nodomain.com",
        "spaces in@email.com",
        "double@@domain.com"
    ]
    for email in invalid_emails:
        res = client.post("/register", data={
            "username": f"user_{abs(hash(email)) % 10000}",
            "email": email,
            "password": "Password123"
        })
        assert res.status_code == 200
        assert b"valid email address" in res.data


def test_register_weak_passwords(client):
    """Verifies password complexity rules: min 8 characters, letters & digits required."""
    weak_cases = [
        ("short1", "too short"),
        ("onlylettershere", "no digits"),
        ("1234567890", "no letters"),
        ("pass", "under 8 chars"),
    ]
    for pwd, desc in weak_cases:
        res = client.post("/register", data={
            "username": f"usr_{abs(hash(pwd)) % 10000}",
            "email": f"test_{abs(hash(pwd)) % 10000}@domain.com",
            "password": pwd
        })
        assert res.status_code == 200, f"Failed for {desc}"
        assert b"Password must be at least 8 characters long and contain both letters and numbers" in res.data


def test_register_missing_fields(client):
    """Verifies that missing username, email, or password shows an error."""
    res = client.post("/register", data={
        "username": "",
        "email": "test@domain.com",
        "password": "Password123"
    })
    assert res.status_code == 200
    assert b"All fields are required" in res.data


def test_register_invalid_username_format(client):
    """Verifies username whitelist (3-30 chars, alphanumeric + _ -)."""
    bad_usernames = ["a", "ab", "user name with spaces", "user<script>", "user!@#$"]
    for uname in bad_usernames:
        res = client.post("/register", data={
            "username": uname,
            "email": "valid@email.com",
            "password": "Password123"
        })
        assert res.status_code == 200
        assert b"Username must be 3-30 characters" in res.data


def test_login_success(client):
    """Verifies valid login redirects to home and establishes session."""
    res = client.post("/login", data={
        "username": "existinguser",
        "password": "ValidPass123"
    }, follow_redirects=False)

    assert res.status_code == 302
    assert res.headers["Location"].endswith("/")


def test_login_incorrect_password(client):
    """Verifies incorrect password fails with error message."""
    res = client.post("/login", data={
        "username": "existinguser",
        "password": "WrongPassword999"
    })
    assert res.status_code == 200
    assert b"Invalid username or password" in res.data


def test_login_nonexistent_user(client):
    """Verifies non-existent username fails with error message."""
    res = client.post("/login", data={
        "username": "ghost_user_9999",
        "password": "ValidPass123"
    })
    assert res.status_code == 200
    assert b"Invalid username or password" in res.data


def test_login_empty_fields(client):
    """Verifies submitting empty login form returns error."""
    res = client.post("/login", data={"username": "", "password": ""})
    assert res.status_code == 200
    assert b"Username and password are required" in res.data


def test_logout(authenticated_client):
    """Logging out (POST) clears the session and redirects to login."""
    res = authenticated_client.post("/logout", follow_redirects=False)
    assert res.status_code == 302
    assert res.headers["Location"].endswith("/login")

    # Following redirect should be on login page
    home_res = authenticated_client.get("/", follow_redirects=False)
    assert home_res.status_code == 302
    assert home_res.headers["Location"].endswith("/login")


def test_logout_rejects_get(authenticated_client):
    """A plain link (GET) can't log a user out, so other sites can't trigger it."""
    assert authenticated_client.get("/logout").status_code == 405
    assert authenticated_client.get("/").status_code == 200  # still logged in


def test_login_username_is_case_insensitive(client):
    """Registration treats usernames case-insensitively, so login does too."""
    res = client.post("/login", data={"username": "EXISTINGUSER", "password": "ValidPass123"})
    assert res.status_code == 302


def test_register_rejects_case_variant_of_existing_username(client):
    res = client.post("/register", data={
        "username": "ExistingUser", "email": "other@example.com", "password": "ValidPass123"})
    assert b"Username already taken" in res.data


def _clear_login_failures(app):
    import sqlite3
    with sqlite3.connect(app.config["DATABASE"]) as conn:
        conn.execute("DELETE FROM login_failures")
        conn.commit()


def test_login_is_throttled_after_repeated_failures(test_app, client):
    """After 5 wrong passwords, even the right one is refused for a while."""
    from webapp import auth
    _clear_login_failures(test_app)
    try:
        for _ in range(auth.MAX_FAILURES):
            res = client.post("/login", data={"username": "existinguser", "password": "WrongPass999"})
            assert b"Invalid username or password" in res.data
        res = client.post("/login", data={"username": "existinguser", "password": "ValidPass123"})
        assert res.status_code == 200
        assert b"Too many failed attempts" in res.data
    finally:
        _clear_login_failures(test_app)


def test_login_failures_are_stored_in_the_database(test_app, client):
    """Kept in SQLite, not process memory: a restart or another worker sees the same count."""
    import sqlite3
    _clear_login_failures(test_app)
    try:
        client.post("/login", data={"username": "ExistingUser", "password": "WrongPass999"})
        with sqlite3.connect(test_app.config["DATABASE"]) as conn:
            rows = conn.execute("SELECT username FROM login_failures").fetchall()
        assert rows == [("existinguser",)]
        client.post("/login", data={"username": "existinguser", "password": "ValidPass123"})
        with sqlite3.connect(test_app.config["DATABASE"]) as conn:
            assert conn.execute("SELECT COUNT(*) FROM login_failures").fetchone()[0] == 0  # cleared on success
    finally:
        _clear_login_failures(test_app)


def test_unauthorized_access(client):
    """Verifies that protected routes redirect unauthenticated users to /login."""
    # Test GET protected routes
    get_protected = ["/", "/evaluate", "/resume/ENGINEERING/E1.pdf"]
    for url in get_protected:
        res = client.get(url, follow_redirects=False)
        assert res.status_code == 302, f"GET {url} did not redirect"
        assert res.headers["Location"].endswith("/login")

    # Test POST protected routes
    post_protected = ["/search", "/upload"]
    for url in post_protected:
        res = client.post(url, data={"job_description": "python"}, follow_redirects=False)
        assert res.status_code == 302, f"POST {url} did not redirect"
        assert res.headers["Location"].endswith("/login")
