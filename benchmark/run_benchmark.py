"""Retrieval benchmark: compares ranking configurations on labeled recruiter queries.

Usage:
    python benchmark/run_benchmark.py            # reuse the benchmark index if present
    python benchmark/run_benchmark.py --rebuild  # rebuild it from resumes/

Relevance: a retrieved resume counts as relevant when its dataset category matches
the query's labeled category (benchmark/queries.json, 2 queries x 24 categories).

The benchmark uses its own index (benchmark/.index) built only from resumes/, so
resumes uploaded through the web app never affect the numbers.

Queries are split into a dev set (first query per category) used to choose settings
and a held-out test set (second query per category) used to confirm them.
"""
import os
import sys
import json
import math
import time
import argparse
import statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import chromadb  # noqa: E402

import chroma_search  # noqa: E402
from chroma_search import search_candidates, RERANK_TOP_N  # noqa: E402
from query_parsing import detect_category, search_text  # noqa: E402

INDEX_PATH = os.path.join("benchmark", ".index")
QUERIES_PATH = os.path.join("benchmark", "queries.json")
RESULTS_MD = os.path.join("benchmark", "RESULTS.md")
RESULTS_JSON = os.path.join("benchmark", "results.json")

STSB = "cross-encoder/stsb-distilroberta-base"
MSMARCO = "cross-encoder/ms-marco-MiniLM-L-6-v2"
BGE = "BAAI/bge-reranker-base"

# (label, search_candidates kwargs)
CONFIGS = [
    ("Dense only (no re-ranking)",               dict(rerank=False)),
    ("STS cross-encoder + 30% overlap [old]",    dict(rerank=True, reranker=STSB, alpha=0.3, keyword_mode="overlap")),
    ("STS cross-encoder only",                   dict(rerank=True, reranker=STSB, alpha=0.0)),
    ("MS MARCO MiniLM only",                     dict(rerank=True, reranker=MSMARCO, alpha=0.0)),
    ("MS MARCO MiniLM + 30% overlap",            dict(rerank=True, reranker=MSMARCO, alpha=0.3, keyword_mode="overlap")),
    ("MS MARCO MiniLM + 30% BM25",               dict(rerank=True, reranker=MSMARCO, alpha=0.3, keyword_mode="bm25")),
    ("BGE reranker base only",                   dict(rerank=True, reranker=BGE, alpha=0.0)),
    ("BGE reranker base + 30% BM25",             dict(rerank=True, reranker=BGE, alpha=0.3, keyword_mode="bm25")),
]

OLD_DEFAULT = dict(rerank=True, reranker=STSB, alpha=0.3, keyword_mode="overlap")
NEW_DEFAULT = dict(rerank=False)

# Dense-score weights for blending: final = w * dense + (1 - w) * cross-encoder
BLEND_WEIGHTS = [0.0, 0.5, 0.7, 0.8, 0.9, 1.0]

ALPHAS = [0.0, 0.1, 0.2, 0.3, 0.5]


# ── Metrics ─────────────────────────────────────────────────────────────────

def precision_at(rel, k):
    return sum(rel[:k]) / k


def reciprocal_rank(rel):
    for i, r in enumerate(rel, 1):
        if r:
            return 1.0 / i
    return 0.0


def ndcg_at(rel, k, n_relevant):
    dcg = sum(r / math.log2(i + 1) for i, r in enumerate(rel[:k], 1))
    ideal = sum(1 / math.log2(i + 1) for i in range(1, min(k, n_relevant) + 1))
    return dcg / ideal if ideal else 0.0


def per_query_rows(queries, rankings_per_query):
    """Per-query detail for the dashboard: P@5, first relevant rank, top-5 categories."""
    rows = []
    for q, ranking in zip(queries, rankings_per_query):
        rel = [int(r["category"] == q["category"]) for r in ranking]
        first = next((i for i, r in enumerate(rel, 1) if r), None)
        rows.append({
            "query": q["query"],
            "category": q["category"],
            "p5": precision_at(rel, 5),
            "first_relevant_rank": first,
            "top5": [r["category"] for r in ranking[:5]],
        })
    return rows


def score_run(queries, rankings_per_query, category_sizes):
    rows = []
    for q, ranking in zip(queries, rankings_per_query):
        rel = [int(r["category"] == q["category"]) for r in ranking]
        rows.append({
            "p5": precision_at(rel, 5),
            "p10": precision_at(rel, 10),
            "mrr": reciprocal_rank(rel),
            "ndcg10": ndcg_at(rel, 10, category_sizes[q["category"]]),
        })
    return {m: statistics.mean(r[m] for r in rows) for m in ("p5", "p10", "mrr", "ndcg10")}


# ── Runs ────────────────────────────────────────────────────────────────────

def get_index(rebuild):
    if rebuild or not os.path.isdir(INDEX_PATH):
        from vector_store import build_index
        print(f"Building benchmark index at {INDEX_PATH} ...")
        return build_index(db_path=INDEX_PATH)
    return chromadb.PersistentClient(path=INDEX_PATH).get_collection("resumes")


def run(queries, collection, **kwargs):
    """Returns (rankings per query, median latency in ms)."""
    rankings, latencies = [], []
    search_candidates(queries[0]["query"], collection=collection, **kwargs)  # warm-up / model load
    for q in queries:
        start = time.perf_counter()
        rankings.append(search_candidates(q["query"], collection=collection, **kwargs))
        latencies.append((time.perf_counter() - start) * 1000)
    return rankings, statistics.median(latencies)


def run_full_pipeline(queries, collection, **kwargs):
    """Mimics the web app's /search: detect category, filter to it, search the cleaned query."""
    rankings, correct = [], 0
    for q in queries:
        detected = detect_category(q["query"])
        correct += int(detected == q["category"])
        intent = search_text(q["query"])
        rankings.append(search_candidates(intent, category=detected, collection=collection, **kwargs))
    return rankings, correct / len(queries)


def blend(ranking, dense_weight):
    """Re-sorts the re-ranked head of a ranking by a dense/cross-encoder score blend."""
    head = [r for r in ranking if "semantic_score" in r][:RERANK_TOP_N]
    names = {r["resume"] for r in head}
    tail = [r for r in ranking if r["resume"] not in names]
    key = lambda r: dense_weight * (1 - r["distance"]) + (1 - dense_weight) * r["semantic_score"] / 100
    return sorted(head, key=key, reverse=True) + tail


def fmt(x):
    return f"{x:.3f}"


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rebuild", action="store_true", help="rebuild the benchmark index")
    args = parser.parse_args()

    with open(QUERIES_PATH, encoding="utf-8") as f:
        queries = json.load(f)
    dev = queries[0::2]
    test = queries[1::2]

    collection = get_index(args.rebuild)
    metas = collection.get(include=["metadatas"])["metadatas"]
    resumes = {(m["resume"], m["category"]) for m in metas}
    category_sizes = {}
    for _, cat in resumes:
        category_sizes[cat] = category_sizes.get(cat, 0) + 1
    print(f"Index: {len(resumes)} resumes, {len(metas)} chunks; {len(queries)} queries")

    results = {"configs": [], "alpha_sweep": [], "blend": [], "pipeline": None,
               "index": {"resumes": len(resumes), "chunks": len(metas)}, "queries": len(queries)}

    # 1. Compare configurations (retrieval over the whole index, no category filter)
    for label, kwargs in CONFIGS:
        rankings, latency = run(queries, collection, **kwargs)
        row = {
            "label": label,
            "all": score_run(queries, rankings, category_sizes),
            "dev": score_run(dev, rankings[0::2], category_sizes),
            "test": score_run(test, rankings[1::2], category_sizes),
            "latency_ms": latency,
            "kwargs": kwargs,
            "per_query": per_query_rows(queries, rankings),
        }
        results["configs"].append(row)
        print(f"{label:42s} P@5 {fmt(row['all']['p5'])}  MRR {fmt(row['all']['mrr'])}  "
              f"nDCG@10 {fmt(row['all']['ndcg10'])}  {latency:.0f} ms")

    # 2. Tune the keyword weight on the dev set for the best re-ranker, then check on test
    reranked = [c for c in results["configs"] if c["kwargs"].get("reranker")]
    best_reranker = max(reranked, key=lambda c: c["dev"]["ndcg10"])["kwargs"]["reranker"]
    for mode in ("overlap", "bm25"):
        for alpha in ALPHAS:
            if alpha == 0.0 and mode == "bm25":
                continue  # identical to overlap at alpha 0
            rankings, _ = run(queries, collection, rerank=True, reranker=best_reranker,
                              alpha=alpha, keyword_mode=mode)
            results["alpha_sweep"].append({
                "mode": mode, "alpha": alpha,
                "dev": score_run(dev, rankings[0::2], category_sizes),
                "test": score_run(test, rankings[1::2], category_sizes),
            })
    chosen = max(results["alpha_sweep"], key=lambda r: r["dev"]["ndcg10"])
    results["chosen"] = {"reranker": best_reranker, "mode": chosen["mode"], "alpha": chosen["alpha"]}
    print(f"Best keyword weight on dev: {best_reranker} {chosen['mode']} alpha={chosen['alpha']} "
          f"(test nDCG@10 {fmt(chosen['test']['ndcg10'])})")

    # 3. Blend dense similarity with cross-encoder scores (instead of replacing it)
    for reranker in (MSMARCO, BGE):
        raw, _ = run(queries, collection, rerank=True, reranker=reranker, alpha=0.0)
        for w in BLEND_WEIGHTS:
            blended = [blend(r, w) for r in raw]
            results["blend"].append({
                "reranker": reranker, "dense_weight": w,
                "all": score_run(queries, blended, category_sizes),
                "dev": score_run(dev, blended[0::2], category_sizes),
                "test": score_run(test, blended[1::2], category_sizes),
            })

    # 4. Full app pipeline (category detection + filter) with old and new defaults
    pipe = {}
    for name, kwargs in (("old", OLD_DEFAULT), ("new", NEW_DEFAULT)):
        rankings, detect_acc = run_full_pipeline(queries, collection, **kwargs)
        pipe[name] = {"detect_acc": detect_acc, "all": score_run(queries, rankings, category_sizes)}
    results["pipeline"] = pipe

    with open(RESULTS_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    write_markdown(results)
    print(f"Wrote {RESULTS_MD} and {RESULTS_JSON}")


def write_markdown(results):
    lines = [
        "# Retrieval Benchmark Results",
        "",
        "Generated by `python benchmark/run_benchmark.py`. "
        f"{results['queries']} labeled recruiter queries (2 per job category) against "
        f"{results['index']['resumes']} resumes ({results['index']['chunks']} chunks) from `resumes/`.",
        "",
        "A result is **relevant** when its dataset category matches the query's category. "
        "Retrieval is measured over the whole index with no category filter.",
        "",
        "- **P@5 / P@10**: share of the top 5 / 10 results that are relevant",
        "- **MRR**: 1 / rank of the first relevant result, averaged",
        "- **nDCG@10**: ranking quality of the top 10 (1.0 = perfect)",
        "- **Latency**: median per query on the machine that ran the benchmark",
        "",
        "## Configurations (all 48 queries)",
        "",
        "| Configuration | P@5 | P@10 | MRR | nDCG@10 | Latency (ms) |",
        "| :--- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for c in results["configs"]:
        a = c["all"]
        lines.append(f"| {c['label']} | {fmt(a['p5'])} | {fmt(a['p10'])} | {fmt(a['mrr'])} | "
                     f"{fmt(a['ndcg10'])} | {c['latency_ms']:.0f} |")

    ch = results["chosen"]
    lines += [
        "",
        "## Keyword weight with the best re-ranker (dev vs held-out test)",
        "",
        f"Re-ranker: `{ch['reranker']}`. Dev = first query per category, test = second.",
        "",
        "| Keyword score | Weight | Dev nDCG@10 | Test nDCG@10 | Test P@5 |",
        "| :--- | ---: | ---: | ---: | ---: |",
    ]
    for r in results["alpha_sweep"]:
        mark = " **(chosen)**" if (r["mode"], r["alpha"]) == (ch["mode"], ch["alpha"]) else ""
        lines.append(f"| {r['mode']} | {r['alpha']:.1f}{mark} | {fmt(r['dev']['ndcg10'])} | "
                     f"{fmt(r['test']['ndcg10'])} | {fmt(r['test']['p5'])} |")

    lines += [
        "",
        "## Blending dense and cross-encoder scores",
        "",
        "Instead of replacing the dense score, rank the re-ranked head by "
        "`w * dense + (1 - w) * cross-encoder`. `w = 1.0` is dense order.",
        "",
        "| Re-ranker | Dense weight | P@5 | MRR | nDCG@10 | Dev nDCG@10 | Test nDCG@10 |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for b in results["blend"]:
        a = b["all"]
        lines.append(f"| {b['reranker'].split('/')[-1]} | {b['dense_weight']:.1f} | {fmt(a['p5'])} | "
                     f"{fmt(a['mrr'])} | {fmt(a['ndcg10'])} | {fmt(b['dev']['ndcg10'])} | "
                     f"{fmt(b['test']['ndcg10'])} |")

    p = results["pipeline"]
    lines += [
        "",
        "## Full app pipeline (category detection + filtered search)",
        "",
        "What the web app's search does: detect the department, search only inside it. "
        "With category-level labels, these numbers are driven mostly by detection accuracy.",
        "",
        "| Search settings | Category detection accuracy | P@5 | MRR | nDCG@10 |",
        "| :--- | ---: | ---: | ---: | ---: |",
        f"| Old (STS + 30% overlap) | {fmt(p['old']['detect_acc'])} | {fmt(p['old']['all']['p5'])} | "
        f"{fmt(p['old']['all']['mrr'])} | {fmt(p['old']['all']['ndcg10'])} |",
        f"| New (dense only, current default) | {fmt(p['new']['detect_acc'])} | {fmt(p['new']['all']['p5'])} | "
        f"{fmt(p['new']['all']['mrr'])} | {fmt(p['new']['all']['ndcg10'])} |",
        "",
        "## Caveats",
        "",
        "- Category labels are a proxy for relevance: a strong Finance resume can be a fair "
        "answer to an Accounting query but counts as a miss here.",
        "- 48 queries is small; differences of a few points between configurations are within noise.",
        "- Category labels cannot measure ranking *within* a department (e.g. Python vs Java "
        "engineers), which is where a re-ranker could still help. That needs skill-level labels.",
        "",
    ]
    with open(RESULTS_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
