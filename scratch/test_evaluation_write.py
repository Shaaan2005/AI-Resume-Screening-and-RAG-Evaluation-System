import os
import json
from evaluate_ragas import get_heuristic_scorecard

results, avg_p, avg_r, avg_s = get_heuristic_scorecard()
print(f"Average Precision: {avg_p}")
print(f"Average Recall: {avg_r}")
print(f"Average Similarity: {avg_s}")
print("Results sample:")
print(json.dumps(results[:3], indent=2))

with open("test_cache.json", "w") as f:
    json.dump({
        "results": results,
        "avg_precision": avg_p,
        "avg_recall": avg_r,
        "avg_similarity": avg_s
    }, f, indent=4)
