import time

print("Starting time test...")
t0 = time.time()

print("Importing math and json...")
import math
import json
import os
print(f"Time: {time.time() - t0:.4f}s")

t1 = time.time()
print("Checking cache file existence...")
EVAL_CACHE_FILE = "evaluation_cache.json"
exists = os.path.exists(EVAL_CACHE_FILE)
print(f"Cache file exists: {exists}. Time: {time.time() - t1:.4f}s")

if exists:
    t2 = time.time()
    print("Reading cache file...")
    with open(EVAL_CACHE_FILE, "r") as f:
        cache_data = json.load(f)
        results = cache_data["results"]
        avg_precision = cache_data["avg_precision"]
        avg_recall = cache_data["avg_recall"]
        avg_similarity = cache_data["avg_similarity"]
    print(f"Finished reading cache. Time: {time.time() - t2:.4f}s")

t3 = time.time()
print("Importing evaluate_ragas...")
from evaluate_ragas import get_heuristic_scorecard, get_real_ragas_scorecard
print(f"Finished importing. Time: {time.time() - t3:.4f}s")

print(f"Total script run time: {time.time() - t0:.4f}s")
