"""Pytest fixtures and configuration for AI Resume Screening test suite."""
import os
import io
import shutil
import tempfile
import sqlite3
import pytest
from werkzeug.security import generate_password_hash

# Set testing environment variable
os.environ["FLASK_SECRET_KEY"] = "test-secret-key-32-bytes-secure-random"

from webapp import create_app


@pytest.fixture(scope="session")
def test_app():
    """Builds a Flask app whose database (accounts + history) and uploads live in a temp dir."""
    temp_dir = tempfile.mkdtemp()
    temp_db_path = os.path.join(temp_dir, "test_users.db")

    flask_app = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,  # Disabled by default in tests; enabled in security tests
        "DATABASE": temp_db_path,
        "UPLOAD_FOLDER": os.path.join(temp_dir, "uploads"),
    })

    # create_app() builds the schema; seed a pre-existing test user
    with sqlite3.connect(temp_db_path) as conn:
        conn.execute(
            "INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
            ("existinguser", "existing@example.com", generate_password_hash("ValidPass123"))
        )
        conn.commit()

    yield flask_app

    shutil.rmtree(temp_dir, ignore_errors=True)


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
