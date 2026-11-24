"""Candidate retrieval: dense vector search, with optional cross-encoder re-ranking.

Pipeline (see search_candidates):
  1. Dense retrieval over resume chunks in ChromaDB (all-mpnet-base-v2, cosine)
  2. Chunk -> resume aggregation (best chunk wins; retrieved chunks are kept for re-ranking)
  3. Optional: cross-encoder re-ranking of the top-N resumes
  4. Optional: hybrid blend with a keyword score (term-coverage or BM25)

Re-ranking is OFF by default. On benchmark/run_benchmark.py (48 labeled queries),
dense retrieval alone scored best (nDCG@10 0.516) while the previous STS cross-encoder
re-ranker lowered it to 0.408 and was 10-20x slower; no re-ranker tested clearly beat
dense alone. See benchmark/RESULTS.md. Set RESUME_RERANK=1 to turn re-ranking on.
"""
import os
import math
import re
import logging
import threading

import chromadb
import numpy as np
import torch
from sentence_transformers import CrossEncoder

from model_loader import model
from scoring import Baseline, recommend

logger = logging.getLogger("ResumeScreening")

_client = None
_collection_lock = threading.Lock()
_collection = None
_cross_encoders = {}
_bm25_cache = {}

# Cross-encoder used for category detection (scores query vs. category description).
CATEGORY_MODEL = "cross-encoder/stsb-distilroberta-base"

# Re-ranking is opt-in (see module docstring for the benchmark evidence).
RERANK_ENABLED = os.environ.get("RESUME_RERANK", "0") == "1"

# Re-ranker used when enabled: a search-tuned model (MS MARCO). It tied dense retrieval
# on P@5 in the benchmark and is ~2x faster than the old STS model.
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

HYBRID_ALPHA = 0.0        # Keyword weight when re-ranking; blending did not help in the benchmark
KEYWORD_MODE = "overlap"  # "overlap" (share of query terms present) or "bm25"
RERANK_TOP_N = 30         # How many dense-retrieval results the cross-encoder re-scores

KEYWORD_STOP = {"the","and","for","with","from","this","that","have","will","can",
    "are","not","but","all","any","each","every","some","few","many","top","best",
    "one","two","three","four","five","six","seven","eight","nine","ten","show",
    "list","find","get","need","want","use","using","able","based","also","well",
    "per","new","like","make","made","resume","resumes","candidate","candidates",
    "job","work","experience","skill","skills","team","role","department","looking",
    "background","description","search","give","me"}

SHORT_TECH_TERMS = {"c++", "c#", ".net", "go", "r", "js", "ts", "ui", "ux", "it",
                    "hr", "pr", "bd", "ml", "ai", "db"}


ROOT = os.path.dirname(os.path.abspath(__file__))
RESUMES_DIR = os.path.join(ROOT, "resumes")


def _index_path():
    """Index folder: CHROMA_PATH if set (relative paths resolve against the project root)."""
    return os.path.join(ROOT, os.environ.get("CHROMA_PATH", "chromadb_data"))


def _dataset_names():
    names = set()
    if os.path.isdir(RESUMES_DIR):
        for cat in os.listdir(RESUMES_DIR):
            folder = os.path.join(RESUMES_DIR, cat)
            if os.path.isdir(folder):
                names.update(os.listdir(folder))
    return names


def tag_untagged_uploads(collection):
    """One-time migration for indexes built before uploads had owners.

    Records whose file isn't one of the sample resumes are tagged as uploads with
    owner "legacy", which hides them from every user's search instead of showing
    them to everyone. Sample resumes need no tag (they pass the non-upload filter).
    """
    try:
        got = collection.get(include=["metadatas"])
    except Exception as e:
        logger.warning(f"Could not read index for migration: {e}")
        return 0
    dataset = _dataset_names()
    ids = [i for i, m in zip(got["ids"], got["metadatas"])
           if "source" not in m and m.get("resume") not in dataset]
    if ids:
        collection.update(ids=ids, metadatas=[{"source": "upload", "owner": "legacy"}] * len(ids))
        logger.info(f"Tagged {len(ids)} pre-existing uploaded chunks as legacy (hidden from search)")
    return len(ids)


def get_collection():
    """Returns the app's ChromaDB collection (created if missing)."""
    global _client, _collection
    if _collection is not None:
        return _collection
    # The server handles requests on several threads. Without the lock, two requests
    # on a fresh server could both try to create the collection; the second one failed
    # with "already exists" and its search silently returned no results.
    with _collection_lock:
        if _collection is None:
            try:
                # CHROMA_PATH lets a public demo search its own clean index (see vector_store.py)
                _client = chromadb.PersistentClient(path=_index_path())
                collection = _client.get_or_create_collection(
                    name="resumes", metadata={"hnsw:space": "cosine"})
                tag_untagged_uploads(collection)
                _collection = collection
            except Exception as e:
                logger.error(f"Failed to initialize ChromaDB collection: {e}")
                return None
    return _collection


def get_reranker(name=None):
    """Lazily loads (and caches) a cross-encoder by Hugging Face model name."""
    name = name or RERANKER_MODEL
    if name not in _cross_encoders:
        try:
            _cross_encoders[name] = CrossEncoder(name)
        except Exception as e:
            logger.error(f"Failed to load CrossEncoder model {name}: {e}")
            return None
    return _cross_encoders[name]


def get_cross_encoder():
    """Cross-encoder used for category detection (kept separate from the re-ranker)."""
    return get_reranker(CATEGORY_MODEL)


# ── Keyword scoring ─────────────────────────────────────────────────────────

def _query_terms(query):
    """Meaningful lowercase query terms (keeps short tech terms like c++, go, ml)."""
    terms = []
    for w in re.findall(r'[a-zA-Z0-9+#.-]+', (query or "").lower()):
        w = w.strip(".,;:!?()")
        if w and (w in SHORT_TECH_TERMS or len(w) >= 3) and w not in KEYWORD_STOP:
            terms.append(w)
    return terms


def _tokenize(text):
    return [w.strip(".,;:!?()") for w in re.findall(r'[a-z0-9+#.-]+', text.lower())]


def keyword_match_score(query, document):
    """Returns the fraction of meaningful query terms that appear in the document (0.0-1.0)."""
    if not query or not document:
        return 0.0
    terms = _query_terms(query)
    if not terms:
        return 0.5
    doc_lower = document.lower()
    matches = sum(1 for t in terms if t in doc_lower)
    return round(matches / len(terms), 4)


def _bm25_index(collection):
    """BM25 index over whole resumes (all chunks joined), cached until the collection changes."""
    from rank_bm25 import BM25Okapi

    key = (id(collection), collection.count())
    if key not in _bm25_cache:
        got = collection.get(include=["documents", "metadatas"])
        texts = {}
        for doc, meta in zip(got["documents"], got["metadatas"]):
            name = meta.get("resume", "")
            texts.setdefault(name, []).append((meta.get("chunk", 0), doc))
        names = sorted(texts)
        corpus = [_tokenize(" ".join(d for _, d in sorted(texts[n]))) for n in names]
        _bm25_cache.clear()
        _bm25_cache[key] = (BM25Okapi(corpus), {n: i for i, n in enumerate(names)})
    return _bm25_cache[key]


def _bm25_scores(query, names, collection):
    """BM25 scores for `names`, normalised to 0-1 by the best score among them."""
    bm25, index = _bm25_index(collection)
    raw = bm25.get_scores(_query_terms(query))
    scores = {n: float(raw[index[n]]) if n in index else 0.0 for n in names}
    top = max(scores.values(), default=0.0)
    return {n: (s / top if top > 0 else 0.0) for n, s in scores.items()}


# ── Search ──────────────────────────────────────────────────────────────────

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"(?<![\w(])(?:\+?\(?\d[\d\s().-]{7,}\d)(?!\w)")


def mask_contacts(text):
    """Hides email addresses and phone numbers in text shown to other users."""
    text = _EMAIL_RE.sub("[email hidden]", text)
    # 9+ digits: phone numbers, but not year ranges like "2010 - 2014" (8 digits)
    return _PHONE_RE.sub(lambda m: "[phone hidden]" if sum(c.isdigit() for c in m.group()) >= 9
                         else m.group(), text)


def _snippet(text, limit=150, mid_document=False):
    """Shortens `text` at a word boundary ("Culinary…", never "Culin…").

    `mid_document`: the text is a later chunk of the resume, so it starts
    mid-sentence; a leading "…" says so.
    """
    text = " ".join(text.split())
    lead = "…" if mid_document and text[:1].islower() else ""
    if len(text) <= limit:
        return lead + text
    cut = text[:limit].rsplit(" ", 1)[0]
    return lead + cut.rstrip(",;:-–") + "…"


def _angle(similarity_pct):
    """Angle in degrees for a 0-100 cosine-style score (clipped for acos safety)."""
    return round(math.degrees(math.acos(max(-1.0, min(1.0, similarity_pct / 100)))), 1)


def _rerank_recommendation(score):
    """Recommendation on the cross-encoder's 0-100 scale (only used with RESUME_RERANK=1)."""
    return "SHORTLIST" if score >= 60 else ("CONSIDER" if score >= 35 else "REJECT")


def _query(collection, embedding, n_results, where):
    """Runs one vector query; returns parallel lists (ids, distances, metadatas, documents)."""
    params = {"query_embeddings": [embedding], "n_results": n_results,
              "include": ["documents", "metadatas", "distances"]}
    if where:
        params["where"] = where
    r = collection.query(**params)
    if not r or not r.get("ids") or not r["ids"][0]:
        return [], [], [], []
    return r["ids"][0], r["distances"][0], r["metadatas"][0], r["documents"][0]


_BASELINE_CACHE = {}
_BASELINE_CACHE_SIZE = 128
_MATRIX_CACHE = {}


def _dataset_matrix(collection):
    """(resume names, unit-length chunk vectors) of the sample resumes, kept in memory.

    Reloaded when the collection's size changes (e.g. after re-indexing). Returns None
    when the collection can't provide embeddings (e.g. the test stand-in).
    """
    try:
        size = collection.count()
        key = id(collection)
        cached = _MATRIX_CACHE.get(key)
        if cached and cached[0] == size:
            return cached[1]
        got = collection.get(where={"source": {"$ne": "upload"}}, include=["embeddings", "metadatas"])
        vectors = np.asarray(got["embeddings"], dtype=np.float32)
        if vectors.ndim != 2 or not len(vectors):
            return None
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True).clip(min=1e-12)
        names = [(m or {}).get("resume") for m in got["metadatas"]]
        _MATRIX_CACHE[key] = (size, (names, vectors))
        return names, vectors
    except Exception:
        return None


def score_baseline(text, collection=None, embedding=None):
    """How every sample resume scores against `text` (mean, spread, all scores).

    Verdicts compare a resume with this baseline (see scoring.py). Cached per text,
    so an all-departments search computes it once rather than 24 times.
    """
    collection = collection if collection is not None else get_collection()
    if collection is None:
        return None
    key = (id(collection), text)
    if key in _BASELINE_CACHE:
        return _BASELINE_CACHE[key]
    if embedding is None:
        embedding = model.encode(text).tolist()
    best = {}
    matrix = _dataset_matrix(collection)
    if matrix is not None:
        # In memory: one matrix product instead of a second full index query (~70 ms)
        names, vectors = matrix
        q = np.asarray(embedding, dtype=np.float32)
        sims = vectors @ (q / (np.linalg.norm(q) or 1.0)) * 100
        for name, score in zip(names, sims.tolist()):
            if score > best.get(name, -1e9):
                best[name] = score
    else:
        r = collection.query(query_embeddings=[embedding], n_results=max(1, collection.count()),
                             where={"source": {"$ne": "upload"}}, include=["metadatas", "distances"])
        for meta, distance in zip(r["metadatas"][0], r["distances"][0]):
            name = (meta or {}).get("resume")
            score = (1.0 - distance) * 100
            if name and score > best.get(name, -1e9):
                best[name] = score
    if not best:
        return None
    scores = sorted(best.values())
    mean = sum(scores) / len(scores)
    std = (sum((s - mean) ** 2 for s in scores) / len(scores)) ** 0.5
    baseline = Baseline(round(mean, 4), round(std, 4), len(scores), tuple(round(s, 2) for s in scores))
    if len(_BASELINE_CACHE) >= _BASELINE_CACHE_SIZE:
        _BASELINE_CACHE.pop(next(iter(_BASELINE_CACHE)))
    _BASELINE_CACHE[key] = baseline
    return baseline


def search_candidates(job_description, category=None, rerank=None, *, owner=None, collection=None,
                      reranker=None, alpha=None, keyword_mode=None, rerank_top_n=None):
    """Retrieves and ranks candidate resumes for a job description.

    Visibility: the sample resumes are searchable by everyone (filtered to `category`
    when given). Uploaded resumes are only ever returned to their `owner` (a user id),
    and are searched regardless of `category`, since a guessed department for an
    uploaded resume is unreliable. With owner=None, no uploads are returned.

    `rerank` defaults to RERANK_ENABLED (off unless RESUME_RERANK=1).
    Keyword arguments override the module defaults (used by the benchmark):
      collection    ChromaDB collection to search (default: the app's index)
      reranker      cross-encoder model name (default: RERANKER_MODEL)
      alpha         keyword weight in the hybrid score (default: HYBRID_ALPHA)
      keyword_mode  "overlap" or "bm25" (default: KEYWORD_MODE)
      rerank_top_n  number of dense results to re-rank (default: RERANK_TOP_N)
    """
    if not job_description or not job_description.strip():
        return []

    rerank = RERANK_ENABLED if rerank is None else rerank
    alpha = HYBRID_ALPHA if alpha is None else alpha
    keyword_mode = keyword_mode or KEYWORD_MODE
    rerank_top_n = rerank_top_n or RERANK_TOP_N

    collection = collection if collection is not None else get_collection()
    if collection is None:
        logger.warning("ChromaDB collection unavailable; returning empty results.")
        return []

    try:
        count = collection.count()
    except Exception as e:
        logger.error(f"Error accessing ChromaDB collection count: {e}")
        return []

    if count == 0:
        return []

    try:
        query_embedding = model.encode(job_description).tolist()
    except Exception as e:
        logger.error(f"Failed to generate query embedding: {e}")
        return []

    try:
        baseline = score_baseline(job_description, collection=collection, embedding=query_embedding)
    except Exception as e:
        logger.warning(f"Could not compute the score baseline: {e}")
        baseline = None

    not_upload = {"source": {"$ne": "upload"}}
    shared_filter = {"$and": [{"category": category}, not_upload]} if category else not_upload
    try:
        hits = list(zip(*_query(collection, query_embedding, min(count, 200), shared_filter)))
        if owner is not None:
            mine = {"$and": [{"source": "upload"}, {"owner": str(owner)}]}
            hits += list(zip(*_query(collection, query_embedding, min(count, 50), mine)))
    except Exception as e:
        logger.error(f"ChromaDB query execution failed: {e}")
        return []

    if not hits:
        return []
    hits.sort(key=lambda h: h[1])  # best (smallest distance) first across both queries

    # Stage 1: aggregate chunks per resume. Chunks arrive best-first, so the first
    # chunk seen for a resume is its best match and leads its re-ranking text.
    seen_resumes = {}
    for chunk_id, distance, meta, doc in hits:
        meta = meta or {}
        doc = doc or ""
        is_upload = meta.get("source") == "upload"
        key = meta.get("file", meta.get("resume", chunk_id)) if is_upload else meta.get("resume", chunk_id)
        similarity = max(0.0, min(100.0, round((1.0 - distance) * 100, 2)))

        if key not in seen_resumes:
            preview = mask_contacts(doc)
            seen_resumes[key] = {
                "name": meta.get("resume", chunk_id),
                "distance": round(distance, 4),
                "similarity": similarity,
                "angle": _angle(similarity),
                "preview": _snippet(preview, mid_document=meta.get("chunk", 0) > 0),
                "preview_full": preview[:600],
                "full_text": doc,
                # Verdict: this score compared with every sample resume's score for the same query
                "recommendation": recommend(similarity, baseline),
                "percentile": baseline.percentile(similarity) if baseline else None,
                # An upload's department: the original's if it copies a sample resume,
                # otherwise the department of the job it was analysed against
                "category": ((meta.get("duplicate_of", "").partition("/")[0] or meta.get("category", ""))
                             if is_upload else meta.get("category", "")),
                "source": "upload" if is_upload else "dataset",
                "file": meta.get("file", "") if is_upload else "",
                "duplicate_of": meta.get("duplicate_of", "") if is_upload else "",
                "reranked": False,
            }
        else:
            seen_resumes[key]["full_text"] += " " + doc

    # An upload that is a copy of a sample resume replaces it, so it isn't listed twice
    # A copy of a sample resume follows the department filter like the original would
    if category:
        # A department search only shows uploads tagged with that department
        seen_resumes = {k: r for k, r in seen_resumes.items()
                        if not (r["source"] == "upload" and r["category"] != category)}
    twins = {r["duplicate_of"] for r in seen_resumes.values() if r["duplicate_of"]}
    if twins:
        seen_resumes = {k: r for k, r in seen_resumes.items()
                        if r["source"] == "upload" or f"{r['category']}/{r['name']}" not in twins}

    # Stage 2: re-rank the top-N resumes with the cross-encoder (+ optional keyword blend)
    if rerank and seen_resumes:
        try:
            ce = get_reranker(reranker)
            if ce is not None:
                candidates = sorted(seen_resumes.items(), key=lambda x: x[1]["similarity"], reverse=True)
                top = candidates[:min(rerank_top_n, len(candidates))]

                pairs = [(job_description, data["full_text"]) for _, data in top]
                # Sigmoid maps every model's raw output onto 0-1 so scores are comparable
                ce_scores = ce.predict(pairs, activation_fn=torch.nn.Sigmoid())

                if alpha > 0 and keyword_mode == "bm25":
                    kw = _bm25_scores(job_description, [n for n, _ in top], collection)
                elif alpha > 0:
                    kw = {n: keyword_match_score(job_description, d["full_text"]) for n, d in top}
                else:
                    kw = {n: 0.0 for n, _ in top}

                for i, (name, data) in enumerate(top):
                    sem_score = max(0.0, min(100.0, round(float(ce_scores[i]) * 100, 2)))
                    kw_score = max(0.0, min(100.0, round(kw[name] * 100, 2)))
                    hybrid = round(kw_score * alpha + sem_score * (1.0 - alpha), 2)
                    hybrid = max(0.0, min(100.0, hybrid))

                    data["similarity"] = hybrid
                    data["angle"] = _angle(hybrid)
                    data["recommendation"] = _rerank_recommendation(hybrid)
                    data["keyword_score"] = kw_score
                    data["semantic_score"] = sem_score
                    data["reranked"] = True
        except Exception as e:
            logger.warning(f"Re-ranking failed: {e}. Falling back to first-pass similarity scores.")

    # Re-ranked resumes always come first: their scores are on a different scale from
    # the first-pass similarity of the ones the cross-encoder never looked at.
    sorted_resumes = sorted(seen_resumes.items(),
                            key=lambda x: (x[1]["reranked"], x[1]["similarity"]), reverse=True)

    rankings = []
    for rank, (key, data) in enumerate(sorted_resumes, 1):
        rankings.append({
            "rank": rank,
            "resume": data["name"],
            "distance": data["distance"],
            "similarity": data["similarity"],
            "angle": data["angle"],
            "preview": data["preview"],
            "preview_full": data["preview_full"],
            "recommendation": data["recommendation"],
            "category": data["category"],
            "source": data["source"],
            "file": data["file"],
            "duplicate_of": data["duplicate_of"],
            "percentile": data["percentile"],
            "keyword_score": data.get("keyword_score", data["similarity"]),
            "semantic_score": data.get("semantic_score", data["similarity"])
        })

    return rankings
