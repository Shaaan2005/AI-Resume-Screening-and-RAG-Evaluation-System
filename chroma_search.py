from model_loader import model
import chromadb
import os
import math
import re
import numpy as np
from sentence_transformers import CrossEncoder

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
    global _client, _collection
    if _collection is None:
        _client = chromadb.PersistentClient(path="chromadb_data")
        try:
            _collection = _client.get_collection(name="resumes")
        except:
            _collection = _client.create_collection(
                name="resumes",
                metadata={"hnsw:space": "cosine"}
            )
    return _collection

def get_cross_encoder():
    global _cross_encoder
    if _cross_encoder is None:
        _cross_encoder = CrossEncoder('cross-encoder/stsb-distilroberta-base')
    return _cross_encoder

def keyword_match_score(query, document):
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

    collection = get_collection()
    count = collection.count()
    if count == 0:
        return []

    query_embedding = model.encode(
        job_description
    ).tolist()

    first_pass_n = min(count, 200)

    query_params = {
        "query_embeddings": [query_embedding],
        "n_results": first_pass_n,
        "include": ["documents", "metadatas", "distances"]
    }

    if category:
        query_params["where"] = {"category": category}

    results = collection.query(**query_params)

    seen_resumes = {}

    for i in range(len(results["ids"][0])):

        chunk_id = results["ids"][0][i]
        distance = results["distances"][0][i]
        meta = results["metadatas"][0][i] if results["metadatas"] else {}
        doc = results["documents"][0][i] if results["documents"] else ""

        resume_name = meta.get("resume", chunk_id)

        similarity = round((1 - distance) * 100, 2)
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
            candidates = list(seen_resumes.items())
            candidates.sort(key=lambda x: x[1]["similarity"], reverse=True)
            top_n = min(30, len(candidates))
            top_candidates = candidates[:top_n]

            pairs = [(job_description, c[1]["full_text"]) for c in top_candidates]
            ce_scores = ce.predict(pairs)

            for i, (name, data) in enumerate(top_candidates):
                raw = float(ce_scores[i])
                sem_score = round(raw * 100, 2)

                kw_pct = keyword_match_score(job_description, data["full_text"])
                kw_score = round(kw_pct * 100, 2)

                hybrid = round(kw_score * HYBRID_ALPHA + sem_score * (1 - HYBRID_ALPHA), 2)

                if i < 5:
                    print(f"[HYBRID] {name}: keyword={kw_score}%  cross-encoder={sem_score}%  final={hybrid}%")

                data["similarity"] = hybrid
                # Safeguard math.acos from floating point domain errors by clipping
                data["angle"] = round(math.degrees(math.acos(max(-1.0, min(1.0, hybrid / 100)))), 1)
                data["recommendation"] = "SHORTLIST" if hybrid >= 60 else ("CONSIDER" if hybrid >= 35 else "REJECT")
                data["keyword_score"] = kw_score
                data["semantic_score"] = sem_score
        except Exception as e:
            print(f"[RERANK ERROR] Re-ranking failed: {e}. Falling back to first-pass similarity scores.")

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
