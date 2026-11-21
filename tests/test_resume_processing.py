"""Tests for Resume Text Extraction, Chunking, and Skill Analysis."""
import os
import tempfile
import pytest
from resume_engine import extract_resume_text, analyze_resume, chunk_text


def test_chunk_text_standard():
    """Verifies that chunk_text splits a document into chunks of specified word count."""
    text = "word " * 450
    chunks = chunk_text(text, chunk_size=200)
    assert len(chunks) == 3
    assert len(chunks[0].split()) == 200
    assert len(chunks[1].split()) == 200
    assert len(chunks[2].split()) == 50


def test_chunk_text_empty():
    """Verifies chunk_text handles empty or whitespace input safely."""
    assert chunk_text("") == []
    assert chunk_text("   \n\t  ") == []
    assert chunk_text(None) == []


def test_extract_resume_text_nonexistent():
    """Verifies that non-existent file returns empty string rather than crashing."""
    result = extract_resume_text("non_existent_path_to_resume_123.pdf")
    assert result == ""


def test_extract_resume_text_corrupted_pdf():
    """Verifies that corrupted PDF file returns empty string gracefully."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"This is definitely not a valid PDF header or content")
        temp_path = f.name

    try:
        text = extract_resume_text(temp_path)
        assert text == ""
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_extract_resume_text_unsupported_format():
    """Verifies that unsupported formats (e.g. .txt, .exe) return empty string."""
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        f.write(b"Some plain text")
        temp_path = f.name

    try:
        text = extract_resume_text(temp_path)
        assert text == ""
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_analyze_resume_empty_or_missing():
    """Verifies analyze_resume returns REJECT and 0 score for missing/empty files."""
    result = analyze_resume("nonexistent_file.pdf")
    assert result["score"] == 0.0
    assert result["skills"] == []
    assert result["recommendation"] == "REJECT"


def test_analyze_resume_scoring_logic(monkeypatch):
    """Verifies score calculation and recommendation bands."""
    import resume_engine
    # Set known skills for deterministic testing
    monkeypatch.setattr(resume_engine, "skills", ["python", "flask", "docker", "sql", "aws"])

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"%PDF-1.4\n")
        temp_path = f.name

    try:
        # Mock extract_resume_text to return different skill sets
        monkeypatch.setattr(resume_engine, "extract_resume_text", lambda path: "expert in python flask docker sql aws")
        high_res = analyze_resume(temp_path)
        assert high_res["score"] == 100.0
        assert high_res["recommendation"] == "SHORTLIST"

        monkeypatch.setattr(resume_engine, "extract_resume_text", lambda path: "developer with python and flask skills")
        mid_res = analyze_resume(temp_path)
        assert mid_res["score"] == 40.0
        assert mid_res["recommendation"] == "CONSIDER"

        monkeypatch.setattr(resume_engine, "extract_resume_text", lambda path: "no matching words here")
        low_res = analyze_resume(temp_path)
        assert low_res["score"] == 0.0
        assert low_res["recommendation"] == "REJECT"
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
