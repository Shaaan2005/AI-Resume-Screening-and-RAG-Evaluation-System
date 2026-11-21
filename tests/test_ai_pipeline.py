"""Tests for AI/ML Pipeline: Semantic Match, Retrieval, Scoring & Category Intent."""
import pytest
from chroma_search import keyword_match_score, search_candidates, HYBRID_ALPHA
from semantic_match import get_similarity
from query_parsing import detect_category, is_garbage, extract_search_intent, parse_requested_count


def test_keyword_match_score():
    """Verifies BM25-style keyword matching calculates expected overlap."""
    doc = "Looking for a Senior Python Developer with Docker and SQL experience."
    score_high = keyword_match_score("Python Docker SQL", doc)
    assert score_high >= 0.9

    score_partial = keyword_match_score("Python React Kubernetes", doc)
    assert 0.3 <= score_partial <= 0.4

    score_none = keyword_match_score("Dentist surgery teeth", doc)
    assert score_none == 0.0


def test_keyword_match_tech_terms():
    """Verifies short technical terms (C++, Go, R, UI, AI) are retained and matched."""
    doc = "Developer skilled in C++ and Go programming languages."
    score = keyword_match_score("C++ Go", doc)
    assert score >= 0.9


def test_semantic_similarity_identical():
    """Verifies cosine similarity of identical texts approaches 100%."""
    text = "Machine Learning Engineer specialized in PyTorch and Deep Neural Networks."
    sim = get_similarity(text, text)
    assert sim >= 99.0


def test_semantic_similarity_different():
    """Verifies semantically dissimilar queries have significantly lower scores."""
    t1 = "Software Engineer specialized in distributed systems and cloud architecture."
    t2 = "Pastry chef baking artisan sourdough bread and French pastries."
    sim = get_similarity(t1, t2)
    assert sim < 40.0


def test_semantic_similarity_empty_inputs():
    """Verifies empty or None inputs safely return 0.0."""
    assert get_similarity("", "Sample text") == 0.0
    assert get_similarity("Sample query", "") == 0.0
    assert get_similarity(None, None) == 0.0


def test_category_detection_core_departments():
    """Verifies that Cross-Encoder detects department intents accurately."""
    cases = [
        ("Looking for a Python Developer with Docker and Kubernetes", "ENGINEERING"),
        ("Seeking HR recruiter with talent acquisition experience", "HR"),
        ("Chartered accountant for GST filing and tax audits", "ACCOUNTANT"),
    ]
    for query, expected_dept in cases:
        detected = detect_category(query)
        assert detected == expected_dept, f"Query '{query}' expected {expected_dept}, got {detected}"


def test_is_garbage_detection():
    """Verifies garbage query filter discriminates nonsense from valid terms."""
    assert is_garbage("asdfghjklqwerty") is True
    assert is_garbage("123456789") is True
    assert is_garbage("......") is True
    assert is_garbage("") is True

    # Valid short technical terms must NOT be flagged as garbage
    assert is_garbage("C++") is False
    assert is_garbage("Python developer") is False
    assert is_garbage("AI") is False


def test_extract_search_intent():
    """Verifies intent extraction removes category names and noise words."""
    query = "top 5 software engineers from engineering"
    intent = extract_search_intent(query)
    assert intent is not None
    assert "engineering" not in intent
    assert "software" in intent


def test_parse_requested_count():
    """Verifies parsing candidate count from natural language queries."""
    assert parse_requested_count("top 5 engineering resumes") == 5
    assert parse_requested_count("show three sales candidates") == 3
    assert parse_requested_count("best 10 developers") == 10
    assert parse_requested_count("give me a developer") is None


def test_hybrid_alpha_weighting():
    """Verifies HYBRID_ALPHA weighting configuration conforms to 30% kw + 70% sem."""
    assert HYBRID_ALPHA == 0.3
    kw_score = 100.0
    sem_score = 50.0
    hybrid = round(kw_score * HYBRID_ALPHA + sem_score * (1.0 - HYBRID_ALPHA), 2)
    assert hybrid == 65.0


def test_search_candidates_empty_query():
    """Verifies search_candidates gracefully returns empty list on empty inputs."""
    assert search_candidates("") == []
    assert search_candidates("   ") == []
    assert search_candidates(None) == []
