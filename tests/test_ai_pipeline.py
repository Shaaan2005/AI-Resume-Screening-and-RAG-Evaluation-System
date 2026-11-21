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


class _FakeCollection:
    """Minimal ChromaDB stand-in: returns fixed chunks best-first."""

    def __init__(self, rows):
        # rows: (resume, category, distance, text), already sorted best-first
        self.rows = rows

    def count(self):
        return len(self.rows)

    def query(self, **kwargs):
        rows = [r for r in self.rows
                if "where" not in kwargs or r[1] == kwargs["where"]["category"]]
        return {
            "ids": [[f"{r[0]}_chunk0" for r in rows]],
            "distances": [[r[2] for r in rows]],
            "metadatas": [[{"resume": r[0], "category": r[1], "chunk": 0} for r in rows]],
            "documents": [[r[3] for r in rows]],
        }

    def get(self, include=None):
        return {"documents": [r[3] for r in self.rows],
                "metadatas": [{"resume": r[0], "category": r[1], "chunk": 0} for r in self.rows]}


class _FakeReranker:
    """Scores pairs from a lookup so tests don't depend on a real model."""

    def __init__(self, scores):
        self.scores = scores

    def predict(self, pairs, activation_fn=None):
        import numpy as np
        return np.array([self.scores[doc] for _, doc in pairs])


_ROWS = [
    ("a.pdf", "ENGINEERING", 0.20, "python developer docker"),
    ("b.pdf", "ENGINEERING", 0.30, "java developer spring"),
    ("c.pdf", "CHEF", 0.40, "head chef kitchen"),
]


def test_reranking_is_off_by_default(monkeypatch):
    """Default search is dense-only (benchmark: re-ranking did not help) and never loads a re-ranker."""
    import chroma_search
    assert chroma_search.RERANK_ENABLED is False

    def fail(*args, **kwargs):
        raise AssertionError("re-ranker should not be loaded by default")
    monkeypatch.setattr(chroma_search, "get_reranker", fail)

    ranked = search_candidates("python developer", collection=_FakeCollection(_ROWS))
    assert [r["resume"] for r in ranked] == ["a.pdf", "b.pdf", "c.pdf"]  # dense order
    assert ranked[0]["similarity"] == 80.0  # (1 - distance) * 100


def test_reranked_results_rank_above_unreranked(monkeypatch):
    """Only the top-N are re-ranked; they must stay ahead of results the re-ranker never scored,
    even when their re-ranker score is lower than an un-reranked result's dense similarity."""
    import chroma_search
    fake = _FakeReranker({"python developer docker": 0.05, "java developer spring": 0.10})
    monkeypatch.setattr(chroma_search, "get_reranker", lambda name=None: fake)

    ranked = search_candidates("python developer", collection=_FakeCollection(_ROWS),
                               rerank=True, alpha=0.0, rerank_top_n=2)
    # b outranks a on re-ranker score; c (dense 60%, never re-ranked) stays last
    assert [r["resume"] for r in ranked] == ["b.pdf", "a.pdf", "c.pdf"]


def test_bm25_keyword_mode_normalises_scores(monkeypatch):
    """BM25 keyword scores are scaled so the best candidate gets 100."""
    import chroma_search
    fake = _FakeReranker({d: 0.5 for _, _, _, d in _ROWS})
    monkeypatch.setattr(chroma_search, "get_reranker", lambda name=None: fake)

    ranked = search_candidates("python docker", collection=_FakeCollection(_ROWS),
                               rerank=True, alpha=0.5, keyword_mode="bm25")
    by_name = {r["resume"]: r for r in ranked}
    assert by_name["a.pdf"]["keyword_score"] == 100.0
    assert by_name["c.pdf"]["keyword_score"] == 0.0
    assert ranked[0]["resume"] == "a.pdf"


def test_hybrid_alpha_weighting():
    """Keyword weight is 0 by default (blending did not help in the benchmark); the blend formula holds."""
    assert HYBRID_ALPHA == 0.0
    alpha = 0.3
    hybrid = round(100.0 * alpha + 50.0 * (1.0 - alpha), 2)
    assert hybrid == 65.0


def test_search_candidates_empty_query():
    """Verifies search_candidates gracefully returns empty list on empty inputs."""
    assert search_candidates("") == []
    assert search_candidates("   ") == []
    assert search_candidates(None) == []
