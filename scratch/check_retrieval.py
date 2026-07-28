import sys
sys.path.insert(0, ".")
from app import detect_category
from evaluate_ragas import search_candidates

queries = [
    "Who has experience in software testing and cross platform development?",
    "Who is skilled in cybersecurity and cloud infrastructure?",
    "Who is a data scientist with machine learning and python experience?",
]

for q in queries:
    cat = detect_category(q)
    rankings = search_candidates(q, category=cat, rerank=True)
    print(f"\nQuery: {q}")
    print(f"Detected: {cat}")
    for i, r in enumerate(rankings[:3]):
        print(f"  Result {i+1}: {r['preview'][:150]}...")
    print("-" * 80)
