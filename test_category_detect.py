"""Test category detection using the Cross-Encoder model from app.py."""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

# Import the single-layer Cross-Encoder detection function
from app import detect_category

# --- Test Cases ---
test_cases = [
    # (query, expected_category)
    # Singular role names
    ("give me the top 1 engineer", "ENGINEERING"),
    ("find the best doctor", "HEALTHCARE"),
    ("show me a lawyer", "ADVOCATE"),
    ("top 1 designer", "DESIGNER"),
    ("best teacher", "TEACHER"),
    ("find a pilot", "AVIATION"),
    ("need a chef", "CHEF"),
    ("get me a nurse", "HEALTHCARE"),

    # Plural role names
    ("give me top 3 preeminent doctors", "HEALTHCARE"),
    ("top 5 engineers", "ENGINEERING"),
    ("best nurses", "HEALTHCARE"),
    ("show me developers", "ENGINEERING"),
    ("find lawyers", "ADVOCATE"),
    ("list all teachers", "TEACHER"),
    ("select 3 designers", "DESIGNER"),
    ("top 10 programmers", "ENGINEERING"),

    # Category names (direct)
    ("top 5 from engineering", "ENGINEERING"),
    ("healthcare candidates", "HEALTHCARE"),
    ("show me banking resumes", "BANKING"),
    ("aviation department", "AVIATION"),
    ("finance team", "FINANCE"),

    # Abbreviations
    ("IT candidates", "INFORMATION-TECHNOLOGY"),
    ("HR department", "HR"),
    ("BPO resumes", "BPO"),
    ("BD team", "BUSINESS-DEVELOPMENT"),
    ("PR candidates", "PUBLIC-RELATIONS"),

    # Synonyms
    ("find a coder", "ENGINEERING"),
    ("need a mechanic", "AUTOMOBILE"),
    ("best farmer", "AGRICULTURE"),
    ("show me artists", "ARTS"),
    ("gym trainers", "FITNESS"),
    ("find an attorney", "ADVOCATE"),
    ("medical staff", "HEALTHCARE"),
    ("software developers", "ENGINEERING"),

    # Multi-word categories
    ("digital media candidates", "DIGITAL-MEDIA"),
    ("information technology", "INFORMATION-TECHNOLOGY"),
    ("public relations", "PUBLIC-RELATIONS"),
    ("business development", "BUSINESS-DEVELOPMENT"),

    # Tricky / edge case queries
    ("select 5 preeminent engineering candidate", "ENGINEERING"),
    ("tell me the highest qualified engineer top 1", "ENGINEERING"),
    ("give me top 3 preeminent doctors", "HEALTHCARE"),
    ("find the most experienced accountants", "ACCOUNTANT"),
    ("show me highly skilled consultants", "CONSULTANT"),

    # Queries with tech terms
    ("c++ developer", "ENGINEERING"),
    ("go developer", "ENGINEERING"),
    ("python programmer", "ENGINEERING"),

    # Queries with clear domain keywords
    ("find someone good with cooking and baking", "CHEF"),
]

# --- Run Tests ---
print("=" * 90)
print(f"{'QUERY':<55} {'EXPECTED':<22} {'GOT':<22} {'STATUS'}")
print("=" * 90)

passed = 0
failed = 0

for query, expected in test_cases:
    result = detect_category(query)
    status = "✅ PASS" if result == expected else "❌ FAIL"
    if result == expected:
        passed += 1
    else:
        failed += 1
    print(f"{query:<55} {str(expected):<22} {str(result):<22} {status}")

print("=" * 90)
print(f"\nResults: {passed} passed, {failed} failed out of {passed + failed} tests")
if failed == 0:
    print("🎉 ALL TESTS PASSED!")
else:
    print(f"⚠️  {failed} test(s) need attention")
