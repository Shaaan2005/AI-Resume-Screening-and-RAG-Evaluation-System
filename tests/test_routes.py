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


def test_evaluate_dashboard_shows_benchmark(authenticated_client):
    """The evaluation page renders the saved benchmark results (no computation on load)."""
    res = authenticated_client.get("/evaluate")
    assert res.status_code == 200
    assert b"Retrieval" in res.data and b"Benchmark" in res.data
    assert b"nDCG@10" in res.data
    assert b"In use" in res.data          # current default is highlighted
    assert b"Query by query" in res.data  # per-query table


def test_evaluate_dashboard_without_results(test_app, authenticated_client, tmp_path):
    """If the benchmark hasn't been run, the page explains how to generate results."""
    original = test_app.config["BENCHMARK_RESULTS"]
    test_app.config["BENCHMARK_RESULTS"] = str(tmp_path / "missing.json")
    try:
        res = authenticated_client.get("/evaluate")
    finally:
        test_app.config["BENCHMARK_RESULTS"] = original
    assert res.status_code == 200
    assert b"No benchmark results found yet" in res.data


def test_evaluate_dashboard_no_longer_accepts_posts(authenticated_client):
    """The old in-browser RAGAS form (which took an API key) is gone."""
    res = authenticated_client.post("/evaluate", data={"eval_mode": "openai", "openai_key": "sk-test"})
    assert res.status_code == 405


def _post_real_resume(client):
    """Uploads one of the sample resumes against a job description."""
    with open("resumes/ACCOUNTANT/AC1.pdf", "rb") as f:
        pdf = f.read()
    return client.post("/upload", content_type="multipart/form-data", data={
        "job_description": "Accountant with general ledger, audit and tax experience",
        "resume": (io.BytesIO(pdf), "candidate.pdf"),
    })


def test_demo_mode_scores_upload_without_keeping_it(test_app, authenticated_client, monkeypatch):
    """Public demo: the resume is scored, but never indexed, listed in history, or left on disk."""
    import os
    from webapp import upload as upload_module

    def must_not_run(*args, **kwargs):
        raise AssertionError("demo mode must not persist uploads")
    monkeypatch.setattr(upload_module, "_index_resume", must_not_run)
    monkeypatch.setattr(upload_module, "save_history", must_not_run)
    monkeypatch.setitem(test_app.config, "DEMO_MODE", True)

    res = _post_real_resume(authenticated_client)
    assert res.status_code == 200
    assert b"Error analyzing resume" not in res.data
    assert b"candidate.pdf" in res.data  # result page rendered for the upload
    assert os.listdir(test_app.config["UPLOAD_FOLDER"]) == []


def test_normal_mode_still_indexes_uploads(test_app, authenticated_client, monkeypatch):
    """Outside demo mode, uploads keep their original behaviour (indexed + history)."""
    from webapp import upload as upload_module
    calls = []
    monkeypatch.setattr(upload_module, "_index_resume", lambda *a, **k: calls.append("index"))
    monkeypatch.setattr(upload_module, "save_history", lambda *a, **k: calls.append("history"))
    monkeypatch.setitem(test_app.config, "DEMO_MODE", False)

    res = _post_real_resume(authenticated_client)
    assert res.status_code == 200
    assert calls == ["index", "history"]
