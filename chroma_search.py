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

import chromadb
import torch
from sentence_transformers import CrossEncoder

from model_loader import model

logger = logging.getLogger("ResumeScreening")

_client = None
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


def get_collection():
    """Returns the ChromaDB collection with persistent client.

    Creates the collection if not present, and handles connection failures gracefully.
    """
    global _client, _collection
    if _collection is None:
        try:
            # CHROMA_PATH lets a public demo search its own clean index (see vector_store.py)
            _client = chromadb.PersistentClient(path=os.environ.get("CHROMA_PATH", "chromadb_data"))
            try:
                _collection = _client.get_collection(name="resumes")
            except Exception:
                _collection = _client.create_collection(
                    name="resumes",
                    metadata={"hnsw:space": "cosine"}
                )
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

def _angle(similarity_pct):
    """Angle in degrees for a 0-100 cosine-style score (clipped for acos safety)."""
    return round(math.degrees(math.acos(max(-1.0, min(1.0, similarity_pct / 100)))), 1)


def _recommendation(score):
    return "SHORTLIST" if score >= 60 else ("CONSIDER" if score >= 35 else "REJECT")


def search_candidates(job_description, category=None, rerank=None, *, collection=None,
                      reranker=None, alpha=None, keyword_mode=None, rerank_top_n=None):
    """Retrieves and ranks candidate resumes for a job description.

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

    query_params = {
        "query_embeddings": [query_embedding],
        "n_results": min(count, 200),
        "include": ["documents", "metadatas", "distances"]
    }
    if category:
        query_params["where"] = {"category": category}

    try:
        results = collection.query(**query_params)
    except Exception as e:
        logger.error(f"ChromaDB query execution failed: {e}")
        return []

    if not results or "ids" not in results or not results["ids"] or not results["ids"][0]:
        return []

    # Stage 1: aggregate chunks per resume. Chunks arrive best-first, so the first
    # chunk seen for a resume is its best match and leads its re-ranking text.
    seen_resumes = {}
    for i in range(len(results["ids"][0])):
        chunk_id = results["ids"][0][i]
        distance = results["distances"][0][i] if results.get("distances") else 0.5
        meta = results["metadatas"][0][i] if results.get("metadatas") else {}
        doc = results["documents"][0][i] if results.get("documents") else ""

        resume_name = meta.get("resume", chunk_id)
        similarity = max(0.0, min(100.0, round((1.0 - distance) * 100, 2)))

        if resume_name not in seen_resumes:
            seen_resumes[resume_name] = {
                "distance": round(distance, 4),
                "similarity": similarity,
                "angle": _angle(similarity),
                "preview": doc[:150] + "..." if len(doc) > 150 else doc,
                "full_text": doc,
                "recommendation": meta.get("recommendation", "REJECT"),
                "category": meta.get("category", ""),
                "reranked": False,
            }
        else:
            seen_resumes[resume_name]["full_text"] += " " + doc

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
                    data["recommendation"] = _recommendation(hybrid)
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
    for rank, (name, data) in enumerate(sorted_resumes, 1):
        rankings.append({
            "rank": rank,
            "resume": name,
            "distance": data["distance"],
            "similarity": data["similarity"],
            "angle": data["angle"],
            "preview": data["preview"],
            "recommendation": data["recommendation"],
            "category": data["category"],
            "keyword_score": data.get("keyword_score", data["similarity"]),
            "semantic_score": data.get("semantic_score", data["similarity"])
        })

    return rankings
