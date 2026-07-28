import sys
sys.path.insert(0, ".")
from app import detect_category
from evaluate_ragas import search_candidates

test_candidates = [
    # 1. Engineering Query
    {
        "query": "Who has experience in software testing and cross platform development?",
        "expected_category": "ENGINEERING",
        "key_skills": ["software testing", "cross platform", "testing strategies"]
    },
    # 2. IT / System Admin Query
    {
        "query": "Who is an IT specialist with system administration and helpdesk experience?",
        "expected_category": "INFORMATION-TECHNOLOGY",
        "key_skills": ["IT specialist", "helpdesk", "system administration", "technical support"]
    },
    # 3. HR / Recruiter Query
    {
        "query": "Who has experience in human resources recruitment and talent acquisition?",
        "expected_category": "HR",
        "key_skills": ["human resources", "recruitment", "hiring", "talent acquisition"]
    },
    # 4. Finance Query
    {
        "query": "Who has experience in financial analysis accounting and auditing?",
        "expected_category": "FINANCE",
        "key_skills": ["financial analysis", "accounting", "auditing", "budgeting"]
    }
]

for item in test_candidates:
    q = item["query"]
    cat = detect_category(q)
    rankings = search_candidates(q, category=cat, rerank=True)
    print(f"\n=======================================================")
    print(f"QUERY: '{q}'")
    print(f"EXPECTED: {item['expected_category']} | DETECTED: {cat}")
    print(f"Total retrieved candidates: {len(rankings)}")
    for i, r in enumerate(rankings[:3]):
        print(f"  [{i+1}] Score: {r.get('similarity', 0):.2f}% | Chunk: {r['preview'][:140]}...")
