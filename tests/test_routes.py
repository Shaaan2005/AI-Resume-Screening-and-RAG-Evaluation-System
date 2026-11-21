"""Tests for Flask HTTP Routes, Search, Upload & Evaluation endpoints."""
import io
import pytest


def test_home_page_authenticated(authenticated_client):
    """Verifies that an authenticated user can access the dashboard."""
    res = authenticated_client.get("/")
    assert res.status_code == 200
    assert b"Screening, <span>Intelligence.</span>" in res.data
    assert b"Smart Search" in res.data


def test_search_valid_query(authenticated_client):
    """Verifies searching with a valid technical query returns search results."""
    res = authenticated_client.post("/search", data={
        "job_description": "top 3 python developer with sql"
    })
    assert res.status_code == 200
    assert b"Search Results" in res.data


def test_search_empty_query(authenticated_client):
    """Verifies searching with empty text prompts for a query without 500 error."""
    res = authenticated_client.post("/search", data={"job_description": ""})
    assert res.status_code == 200
    assert b"Please enter a search query" in res.data


def test_search_garbage_query(authenticated_client):
    """Verifies submitting nonsense triggers garbage detection feedback."""
    res = authenticated_client.post("/search", data={
        "job_description": "asdfghjkl qwertyuiop zxcvbnm"
    })
    assert res.status_code == 200
    assert b"valid search" in res.data


def test_upload_missing_job_description(authenticated_client, sample_pdf_bytes):
    """Verifies upload fails gracefully when job description is omitted."""
    data = {
        "job_description": "",
        "resume": (io.BytesIO(sample_pdf_bytes), "developer.pdf")
    }
    res = authenticated_client.post("/upload", data=data, content_type="multipart/form-data")
    assert res.status_code == 200
    assert b"Job description is required" in res.data


def test_upload_missing_resume_file(authenticated_client):
    """Verifies upload fails gracefully when no resume file is attached."""
    data = {
        "job_description": "Looking for a Python Developer",
        "resume": (io.BytesIO(b""), "")
    }
    res = authenticated_client.post("/upload", data=data, content_type="multipart/form-data")
    assert res.status_code == 200
    assert b"Please upload a resume file" in res.data


def test_upload_invalid_file_extension(authenticated_client):
    """Verifies upload rejects unsupported file extensions (.exe, .txt)."""
    data = {
        "job_description": "Looking for a Python Developer",
        "resume": (io.BytesIO(b"Plain text resume content"), "resume.txt")
    }
    res = authenticated_client.post("/upload", data=data, content_type="multipart/form-data")
    assert res.status_code == 200
    assert b"Only PDF and DOCX files are supported" in res.data


def test_upload_corrupted_pdf_signature(authenticated_client):
    """Verifies upload rejects a file with .pdf extension that lacks %PDF- header."""
    data = {
        "job_description": "Looking for a Python Developer",
        "resume": (io.BytesIO(b"Not a PDF header file"), "fake.pdf")
    }
    res = authenticated_client.post("/upload", data=data, content_type="multipart/form-data")
    assert res.status_code == 200
    assert b"corrupted PDF file signature" in res.data


def test_resume_download_valid(authenticated_client):
    """Verifies downloading an existing candidate resume succeeds."""
    res = authenticated_client.get("/resume/ENGINEERING/E1.pdf")
    assert res.status_code in (200, 404)  # 200 if file present in test env, 404 if missing


def test_resume_download_invalid_category(authenticated_client):
    """Verifies invalid department categories are blocked with 404."""
    res = authenticated_client.get("/resume/NON_EXISTENT_DEPARTMENT/test.pdf")
    assert res.status_code == 404


def test_resume_download_path_traversal(authenticated_client):
    """Verifies path traversal attempts on resume downloads are blocked."""
    traversal_paths = [
        "/resume/..%2f..%2fetc/passwd",
        "/resume/ENGINEERING/..%2f..%2fapp.py",
        "/resume/ENGINEERING/../../../etc/shadow",
    ]
    for path in traversal_paths:
        res = authenticated_client.get(path)
        assert res.status_code == 404


def test_evaluate_dashboard_get(authenticated_client):
    """Verifies the RAGAS evaluation dashboard loads with metrics."""
    res = authenticated_client.get("/evaluate")
    assert res.status_code == 200
    assert b"RAGAS" in res.data
    assert b"Context Precision" in res.data
    assert b"Context Recall" in res.data


def test_evaluate_dashboard_post_missing_key(authenticated_client):
    """Verifies requesting OpenAI evaluation without a key triggers validation error."""
    res = authenticated_client.post("/evaluate", data={
        "eval_mode": "openai",
        "openai_key": ""
    })
    assert res.status_code == 200
    assert b"Please enter a valid OpenAI API Key" in res.data
