"""Evaluation dashboard: shows the saved retrieval benchmark results instantly.

The numbers come from benchmark/results.json, written by
`python benchmark/run_benchmark.py`. Nothing is computed while the page loads.
(LLM-judged RAGAS scoring is available from the command line: evaluate_ragas.py.)
"""
import os
import json
import logging

from flask import Blueprint, render_template, current_app

from .security import login_required

logger = logging.getLogger("ResumeScreening")

bp = Blueprint("evaluate", __name__)


def load_benchmark(path):
    """Returns the parsed benchmark results, or None if missing/unreadable."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        logger.warning(f"Could not read benchmark results {path}: {e}")
        return None


def _summarise(results):
    """Picks out the current default and the original setup for the headline cards."""
    configs = results.get("configs", [])
    current = next((c for c in configs if c.get("kwargs") == {"rerank": False}), None)
    original = next((c for c in configs if "[old]" in c.get("label", "")), None)
    for c in configs:
        c["is_current"] = c is current
        c["is_original"] = c is original
        c["label"] = c["label"].replace(" [old]", "")
    return current, original


@bp.route("/evaluate")
@login_required
def evaluate_dashboard():
    results = load_benchmark(current_app.config["BENCHMARK_RESULTS"])
    if results is None:
        return render_template("evaluate.html", results=None)

    current, original = _summarise(results)
    return render_template("evaluate.html",
                           results=results,
                           current=current,
                           original=original,
                           pipeline=results.get("pipeline") or {})
