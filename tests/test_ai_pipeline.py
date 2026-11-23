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


def _matches(meta, where):
    """Evaluates the subset of ChromaDB `where` filters the app uses.

    Like ChromaDB, `$ne` also matches records that don't have the field.
    """
    if "$and" in where:
        return all(_matches(meta, w) for w in where["$and"])
    if "$or" in where:
        return any(_matches(meta, w) for w in where["$or"])
    (field, cond), = where.items()
    if isinstance(cond, dict) and "$ne" in cond:
        return meta.get(field) != cond["$ne"]
    return meta.get(field) == cond


class _FakeCollection:
    """Minimal ChromaDB stand-in: returns fixed chunks best-first."""

    def __init__(self, rows):
        # rows: (resume, category, distance, text[, extra metadata]), sorted best-first
        self.rows = rows

    def _meta(self, r):
        meta = {"resume": r[0], "category": r[1], "chunk": 0}
        if len(r) > 4:
            meta.update(r[4])
        return meta

    def count(self):
        return len(self.rows)

    def query(self, **kwargs):
        where = kwargs.get("where")
        rows = [r for r in self.rows if not where or _matches(self._meta(r), where)]
        return {
            "ids": [[f"{r[0]}_chunk0" for r in rows]],
            "distances": [[r[2] for r in rows]],
            "metadatas": [[self._meta(r) for r in rows]],
            "documents": [[r[3] for r in rows]],
        }

    def get(self, include=None):
        return {"documents": [r[3] for r in self.rows],
                "metadatas": [self._meta(r) for r in self.rows]}


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


# ── Visibility, scoring and parsing fixes ───────────────────────────────────

_MIXED_ROWS = [
    ("E1.pdf", "ENGINEERING", 0.35, "python engineer"),                                  # 65 -> SHORTLIST
    ("mine.pdf", "", 0.40, "my python resume", {"source": "upload", "owner": "1", "file": "1_aaa.pdf"}),
    ("theirs.pdf", "", 0.30, "their python resume", {"source": "upload", "owner": "2", "file": "2_bbb.pdf"}),
    ("legacy.pdf", "", 0.20, "old upload", {"source": "upload", "owner": "legacy"}),
    ("C1.pdf", "CHEF", 0.45, "chef"),                                                    # 55 -> CONSIDER
    ("A1.pdf", "ACCOUNTANT", 0.60, "accountant"),                                        # 40 -> REJECT
]


def test_uploads_are_only_visible_to_their_owner():
    ranked = search_candidates("python", owner=1, collection=_FakeCollection(_MIXED_ROWS))
    names = [r["resume"] for r in ranked]
    assert "mine.pdf" in names
    assert "theirs.pdf" not in names and "legacy.pdf" not in names
    mine = next(r for r in ranked if r["resume"] == "mine.pdf")
    assert mine["source"] == "upload" and mine["file"] == "1_aaa.pdf" and mine["category"] == ""


def test_no_uploads_without_an_owner():
    ranked = search_candidates("python", collection=_FakeCollection(_MIXED_ROWS))
    assert {r["source"] for r in ranked} == {"dataset"}


def test_own_uploads_included_even_when_department_filter_applies():
    """An upload has no reliable department, so the owner's uploads ignore the filter."""
    ranked = search_candidates("python", category="ENGINEERING", owner=1,
                               collection=_FakeCollection(_MIXED_ROWS))
    assert [r["resume"] for r in ranked] == ["E1.pdf", "mine.pdf"]


def test_recommendation_always_matches_the_score_shown():
    ranked = search_candidates("python", collection=_FakeCollection(_MIXED_ROWS))
    by_name = {r["resume"]: r for r in ranked}
    assert by_name["E1.pdf"]["recommendation"] == "SHORTLIST"
    assert by_name["C1.pdf"]["recommendation"] == "CONSIDER"
    assert by_name["A1.pdf"]["recommendation"] == "REJECT"


def test_score_thresholds_and_colours_agree():
    from scoring import recommend, band
    assert recommend(60) == "SHORTLIST" and band(60) == "green"
    assert recommend(55) == "CONSIDER" and band(55) == "yellow"
    assert recommend(49.9) == "REJECT" and band(49.9) == "red"


def test_previews_hide_contact_details():
    from chroma_search import mask_contacts
    masked = mask_contacts("Reach me at jane@example.com or +91 98765 43210. Worked 2010 - 2014.")
    assert "jane@example.com" not in masked and "98765" not in masked
    assert "2010 - 2014" in masked  # year ranges are not phone numbers


def test_requested_count_ignores_experience_durations():
    assert parse_requested_count("need 2 years of python") is None
    assert parse_requested_count("want 3+ yrs java") is None
    assert parse_requested_count("2 years experience resumes") is None
    assert parse_requested_count("top 0 engineers") is None
    assert parse_requested_count("top 500 sales") == 50
    assert parse_requested_count("10 engineer resumes") == 10
    assert parse_requested_count("need 3 java developers") == 3


def test_named_department_beats_the_models_guess():
    """A department the recruiter names is used as-is (the model alone sent
    "top 5 from engineering" to CONSTRUCTION and "best 3 sales" to APPAREL)."""
    assert detect_category("top 5 from engineering") == "ENGINEERING"
    assert detect_category("best 3 sales with cold calling") == "SALES"
    assert detect_category("list all teachers") == "TEACHER"
    assert detect_category("IT candidates") == "INFORMATION-TECHNOLOGY"
    assert detect_category("it support") == "INFORMATION-TECHNOLOGY"
    assert detect_category("finance team") == "FINANCE"


def test_non_software_developers_are_not_engineering():
    assert detect_category("real estate developer with land acquisition experience") == "CONSTRUCTION"
    assert detect_category("business developer for new partnerships") == "BUSINESS-DEVELOPMENT"
    assert detect_category("martial arts trainer") != "ARTS"
    assert detect_category("web developer") == "ENGINEERING"


def test_search_text_keeps_the_sentence_and_drops_commands():
    from query_parsing import search_text
    assert search_text("Experienced HR recruiter for talent acquisition and onboarding") == \
        "Experienced HR recruiter for talent acquisition and onboarding"
    assert search_text("top 5 python developers with SQL and Django") == "python developers with SQL and Django"
    assert search_text("show me 10 engineer resumes") == "engineer"
    assert search_text("best 3 sales with cold calling") == "sales with cold calling"
    assert search_text("top 5") == "top 5"  # nothing left: fall back to the original


@pytest.fixture(scope="module")
def hr_collection(tmp_path_factory):
    """A real ChromaDB index of the sample HR resumes, built in a temp dir.

    The app's index (chromadb_data/) is gitignored and not built in CI, so tests
    must not depend on it: searching it there returns no results.
    """
    import os
    import shutil
    from vector_store import build_index

    resumes_dir = tmp_path_factory.mktemp("resumes")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    shutil.copytree(os.path.join(repo_root, "resumes", "HR"), resumes_dir / "HR")
    return build_index(db_path=str(tmp_path_factory.mktemp("chroma")), resumes_dir=str(resumes_dir))


def test_full_sentence_scores_higher_than_stripped_keywords(hr_collection):
    """The reason for search_text: keyword-only text scored ~12 points lower on the benchmark."""
    from query_parsing import search_text
    q = "Experienced HR recruiter for talent acquisition and onboarding"
    full = search_candidates(search_text(q), category="HR", collection=hr_collection)
    stripped = search_candidates(extract_search_intent(q), category="HR", collection=hr_collection)
    assert full and stripped, "HR test index returned no results"
    assert full[0]["similarity"] > stripped[0]["similarity"]


def test_upload_that_copies_a_sample_resume_replaces_it():
    rows = [
        ("A1.pdf", "ACCOUNTANT", 0.30, "ledger"),
        ("copy.pdf", "", 0.30, "ledger", {"source": "upload", "owner": "1", "file": "1_x.pdf",
                                          "duplicate_of": "ACCOUNTANT/A1.pdf"}),
        ("A2.pdf", "ACCOUNTANT", 0.40, "tax"),
    ]
    names = [r["resume"] for r in search_candidates("ledger", owner=1, collection=_FakeCollection(rows))]
    assert names == ["copy.pdf", "A2.pdf"]
    # other users still see the sample resume
    assert [r["resume"] for r in search_candidates("ledger", collection=_FakeCollection(rows))] == ["A1.pdf", "A2.pdf"]


def test_several_named_departments_are_settled_by_the_model():
    assert detect_category("fashion designer") in {"APPAREL", "DESIGNER"}


def test_ambiguous_short_words_need_capitals():
    assert is_garbage("asdfgh it") is True
    assert is_garbage("qwrtzx r") is True
    assert is_garbage("IT support") is False
    assert is_garbage("R developer") is False


def test_upload_match_score_reads_the_whole_resume():
    """The best chunk wins, so a match at the end of a long resume still counts."""
    filler = " ".join(["gardening landscaping lawn care hedge trimming"] * 120)  # ~720 words
    resume = filler + " senior python developer building django rest apis and docker deployments"
    assert get_similarity("python django developer", resume) > get_similarity("python django developer", filler) + 10



# ── Audit fixes ─────────────────────────────────────────────────────────────

def test_no_department_for_queries_with_no_job_words():
    assert detect_category("hello world") is None
    assert detect_category("best 5 astronaut") is None
    assert detect_category("need a mechanic") == "AUTOMOBILE"  # real queries still resolve


def test_engineering_disciplines_are_engineering():
    assert detect_category("Mechanical Engineer with AutoCAD, SolidWorks") == "ENGINEERING"
    assert detect_category("civil engineer for bridge projects") == "CONSTRUCTION"


def test_garbled_text_and_placeholders_are_cleaned():
    from resume_engine import clean_text
    assert clean_text("Company Name â€“ City") == "Company Name – City"
    assert clean_text("achieved Â·Â Maintained") == "achieved · Maintained"
    assert clean_text("Dedicated [job title] with 5 years") == "Dedicated with 5 years"


def test_snippets_end_on_a_whole_word():
    from chroma_search import _snippet
    s = _snippet("word " * 60)
    assert s.endswith("word…") and len(s) <= 151


def test_keyword_match_uses_the_job_descriptions_skills(tmp_path):
    from resume_engine import analyze_resume
    r = analyze_resume("x.pdf", category="ENGINEERING", text="python docker kubernetes microservices",
                       job_description="Need python and docker")
    assert r["basis"] == "job" and r["wanted"] == 2 and r["score"] == 100.0
    assert "microservices" not in r["skills"]  # not asked for by the job



def test_copied_upload_takes_the_originals_department():
    rows = [("E1.pdf", "ENGINEERING", 0.30, "devops"),
            ("devops.pdf", "", 0.30, "devops", {"source": "upload", "owner": "1", "file": "1_d.pdf",
                                                "duplicate_of": "ENGINEERING/E1.pdf"})]
    eng = search_candidates("devops", category="ENGINEERING", owner=1, collection=_FakeCollection(rows))
    assert [(r["resume"], r["category"], r["duplicate_of"]) for r in eng] == \
        [("devops.pdf", "ENGINEERING", "ENGINEERING/E1.pdf")]  # the page labels it "copy of E1.pdf"
    assert eng[0]["preview_full"]  # hover text for the shortened snippet
    auto = search_candidates("devops", category="AUTOMOBILE", owner=1, collection=_FakeCollection(rows))
    assert auto == []  # not listed under a department the original isn't in


def test_engineering_tools_count_as_job_skills():
    from resume_engine import analyze_resume
    r = analyze_resume("x", category="ENGINEERING", text="autocad and solidworks drawings",
                       job_description="Mechanical Engineer with AutoCAD, SolidWorks")
    assert r["basis"] == "job" and r["skills"] == ["autocad", "solidworks"]
