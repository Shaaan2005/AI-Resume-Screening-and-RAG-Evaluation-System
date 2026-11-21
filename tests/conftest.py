"""Pytest fixtures and configuration for AI Resume Screening test suite."""
import os
import io
import tempfile
import sqlite3
import pytest
from werkzeug.security import generate_password_hash

# Set testing environment variable
os.environ["FLASK_SECRET_KEY"] = "test-secret-key-32-bytes-secure-random"

from app import app as flask_app, DB_FILE, UPLOAD_FOLDER


@pytest.fixture(scope="session")
def test_app():
    """Configures the Flask app for testing with an isolated temporary database."""
    # Create a temporary test database
    db_fd, temp_db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)

    temp_upload = tempfile.mkdtemp()

    flask_app.config.update({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,  # Disabled by default in tests; enabled in security tests
        "DATABASE": temp_db_path,
        "UPLOAD_FOLDER": temp_upload,
    })

    # Initialize isolated schema
    with sqlite3.connect(temp_db_path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT UNIQUE, email TEXT, password TEXT)")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        # Insert a default pre-existing test user
        conn.execute(
            "INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
            ("existinguser", "existing@example.com", generate_password_hash("ValidPass123"))
        )
        conn.commit()

    # Point global DB_FILE in app to temporary DB
    import app as app_module
    old_db = app_module.DB_FILE
    old_upload = app_module.UPLOAD_FOLDER
    app_module.DB_FILE = temp_db_path
    app_module.UPLOAD_FOLDER = temp_upload

    yield flask_app

    # Cleanup
    app_module.DB_FILE = old_db
    app_module.UPLOAD_FOLDER = old_upload
    try:
        os.remove(temp_db_path)
    except OSError:
        pass


@pytest.fixture
def client(test_app):
    """A standard test client with CSRF disabled for functional route testing."""
    test_app.config["WTF_CSRF_ENABLED"] = False
    with test_app.test_client() as client:
        yield client


@pytest.fixture
def csrf_client(test_app):
    """A test client with CSRF protection strictly enabled for security tests."""
    test_app.config["WTF_CSRF_ENABLED"] = True
    with test_app.test_client() as client:
        yield client
    test_app.config["WTF_CSRF_ENABLED"] = False


@pytest.fixture
def authenticated_client(test_app):
    """A test client with an active authenticated session."""
    test_app.config["WTF_CSRF_ENABLED"] = False
    with test_app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["username"] = "existinguser"
        yield client


@pytest.fixture
def sample_pdf_bytes():
    """Generates a minimal valid PDF byte stream with a skills header."""
    return (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /Resources <<>> /MediaBox [0 0 612 792] /Contents 4 0 R >> endobj\n"
        b"4 0 obj << /Length 55 >> stream\n"
        b"BT /F1 12 Tf 72 712 Td (Python Flask SQL Developer Resume) ET\n"
        b"endstream endobj\n"
        b"xref\n0 5\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000216 00000 n \n"
        b"trailer << /Size 5 /Root 1 0 R >>\nstartxref\n323\n%%EOF\n"
    )


@pytest.fixture
def corrupted_pdf_bytes():
    """Generates an invalid/corrupted PDF stream."""
    return b"Not A Valid PDF File Stream Content XYZ123"
