from model_loader import model
import chromadb
import os
import math
import re
import logging
import numpy as np
from sentence_transformers import CrossEncoder

logger = logging.getLogger("ResumeScreening")

_client = None
_collection = None
_cross_encoder = None

HYBRID_ALPHA = 0.3  # 30% Keyword + 70% Semantic (Semantic Weight = 1 - ALPHA)

KEYWORD_STOP = {"the","and","for","with","from","this","that","have","will","can",
    "are","not","but","all","any","each","every","some","few","many","top","best",
    "one","two","three","four","five","six","seven","eight","nine","ten","show",
    "list","find","get","need","want","use","using","able","based","also","well",
    "per","new","like","make","made","resume","resumes","candidate","candidates",
    "job","work","experience","skill","skills","team","role","department","looking",
    "background","description","search","give","me"}


def get_collection():
    """Returns the ChromaDB collection with persistent client.
    
    Creates the collection if not present, and handles connection failures gracefully.
    """
    global _client, _collection
    if _collection is None:
        try:
            _client = chromadb.PersistentClient(path="chromadb_data")
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


def get_cross_encoder():
    """Lazily loads and returns the Cross-Encoder model."""
    global _cross_encoder
    if _cross_encoder is None:
        try:
            _cross_encoder = CrossEncoder('cross-encoder/stsb-distilroberta-base')
        except Exception as e:
            logger.error(f"Failed to load CrossEncoder model: {e}")
            return None
    return _cross_encoder


def keyword_match_score(query, document):
    """Computes BM25-style keyword matching score between query and document text."""
    if not query or not document:
        return 0.0

    words = re.findall(r'[a-zA-Z0-9+#.-]+', query.lower())
    terms = []
    for w in words:
        w = w.strip(".,;:!?()")
        if not w:
            continue
        # Allow short technical terms or standard words of length >= 3
        if w in {"c++", "c#", ".net", "go", "r", "js", "ts", "ui", "ux", "it", "hr", "pr", "bd", "ml", "ai", "db"} or len(w) >= 3:
            if w not in KEYWORD_STOP:
                terms.append(w)
    if not terms:
        return 0.5
    doc_lower = document.lower()
    matches = sum(1 for t in terms if t in doc_lower)
    return round(matches / len(terms), 4)


def search_candidates(job_description, category=None, rerank=True):
    """Retrieves and re-ranks candidate resumes using vector search and cross-encoder.
    
    Pipeline:
      1. Dense vector search via ChromaDB (cosine distance)
      2. Deduplication and chunk aggregation
      3. Cross-Encoder semantic scoring
      4. Hybrid weighting: 30% Keyword + 70% Cross-Encoder
    """
    if not job_description or not job_description.strip():
        return []

    collection = get_collection()
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

    first_pass_n = min(count, 200)

    query_params = {
        "query_embeddings": [query_embedding],
        "n_results": first_pass_n,
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

    seen_resumes = {}

    for i in range(len(results["ids"][0])):
        chunk_id = results["ids"][0][i]
        distance = results["distances"][0][i] if results.get("distances") else 0.5
        meta = results["metadatas"][0][i] if results.get("metadatas") else {}
        doc = results["documents"][0][i] if results.get("documents") else ""

        resume_name = meta.get("resume", chunk_id)

        similarity = max(0.0, min(100.0, round((1.0 - distance) * 100, 2)))
        # Safeguard math.acos from floating point domain errors by clipping
        angle = round(math.degrees(math.acos(max(-1.0, min(1.0, similarity / 100)))), 1)

        if resume_name not in seen_resumes:
            preview = doc[:150] + "..." if len(doc) > 150 else doc
            seen_resumes[resume_name] = {
                "distance": round(distance, 4),
                "similarity": similarity,
                "angle": angle,
                "preview": preview,
                "full_text": doc,
                "recommendation": meta.get("recommendation", "REJECT"),
                "category": meta.get("category", "")
            }
        else:
            prev = seen_resumes[resume_name]
            prev["full_text"] += " " + doc
            if similarity > prev["similarity"]:
                prev["similarity"] = similarity
                prev["angle"] = angle
                prev["distance"] = round(distance, 4)
                new_preview = doc[:150] + "..." if len(doc) > 150 else doc
                prev["preview"] = new_preview

    if rerank and seen_resumes:
        try:
            ce = get_cross_encoder()
            if ce is not None:
                candidates = list(seen_resumes.items())
                candidates.sort(key=lambda x: x[1]["similarity"], reverse=True)
                top_n = min(30, len(candidates))
                top_candidates = candidates[:top_n]

                pairs = [(job_description, c[1]["full_text"]) for c in top_candidates]
                ce_scores = ce.predict(pairs)

                for i, (name, data) in enumerate(top_candidates):
                    raw = float(ce_scores[i])
                    sem_score = max(0.0, min(100.0, round(raw * 100, 2)))

                    kw_pct = keyword_match_score(job_description, data["full_text"])
                    kw_score = max(0.0, min(100.0, round(kw_pct * 100, 2)))

                    hybrid = round(kw_score * HYBRID_ALPHA + sem_score * (1.0 - HYBRID_ALPHA), 2)
                    hybrid = max(0.0, min(100.0, hybrid))

                    data["similarity"] = hybrid
                    data["angle"] = round(math.degrees(math.acos(max(-1.0, min(1.0, hybrid / 100)))), 1)
                    data["recommendation"] = "SHORTLIST" if hybrid >= 60 else ("CONSIDER" if hybrid >= 35 else "REJECT")
                    data["keyword_score"] = kw_score
                    data["semantic_score"] = sem_score
        except Exception as e:
            logger.warning(f"Re-ranking failed: {e}. Falling back to first-pass similarity scores.")

    sorted_resumes = sorted(seen_resumes.items(), key=lambda x: x[1]["similarity"], reverse=True)

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
