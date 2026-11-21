"""Retrieval evaluation dashboard (heuristic baseline + optional real RAGAS run)."""
import os
import json
import math
import logging

from flask import Blueprint, request, render_template, current_app

from .security import login_required

logger = logging.getLogger("ResumeScreening")

bp = Blueprint("evaluate", __name__)


def _pct(value):
    """Converts a 0-1 score to a rounded percentage; NaN/None become None."""
    if value is None or math.isnan(float(value)):
        return None
    return round(float(value) * 100, 2)


def _load_or_compute_heuristic(force_recalc):
    """Returns (results, precision, recall, similarity), using the JSON cache when allowed."""
    from evaluate_ragas import get_heuristic_scorecard

    cache_file = current_app.config["EVAL_CACHE_FILE"]
    if not force_recalc and os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cache = json.load(f)
            if cache.get("results") is not None:
                return (cache["results"], cache.get("avg_precision", 0.0),
                        cache.get("avg_recall", 0.0), cache.get("avg_similarity", 0.0))
        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")

    logger.info("Recalculating heuristic evaluation scorecard...")
    results, precision, recall, similarity = get_heuristic_scorecard()
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({
                "results": results,
                "avg_precision": precision,
                "avg_recall": recall,
                "avg_similarity": similarity
            }, f, indent=4)
    except Exception as e:
        logger.warning(f"Failed to save evaluation cache: {e}")
    return results, precision, recall, similarity


def _nan_to_zero(value):
    return 0.0 if value is None or math.isnan(value) else value


@bp.route("/evaluate", methods=["GET", "POST"])
@login_required
def evaluate_dashboard():
    from evaluate_ragas import get_real_ragas_scorecard

    error_msg = None
    success_msg = None
    is_real_ragas = False

    force_recalc = (request.args.get("recalculate") == "true")
    results, avg_precision, avg_recall, avg_similarity = _load_or_compute_heuristic(force_recalc)

    if force_recalc:
        success_msg = "Successfully recalculated baseline heuristic metrics across the benchmark suite!"

    if request.method == "POST":
        eval_mode = request.form.get("eval_mode", "openai").strip()
        openai_key = request.form.get("openai_key", "").strip()

        if eval_mode == "openai" and not openai_key:
            error_msg = "Please enter a valid OpenAI API Key to run RAGAS."
        else:
            try:
                if eval_mode == "ollama":
                    logger.info("Running RAGAS evaluation using local Ollama (Llama 3)...")
                    r_results, r_precision, r_recall = get_real_ragas_scorecard(use_ollama=True)
                else:
                    logger.info("Running RAGAS evaluation using OpenAI API Key...")
                    r_results, r_precision, r_recall = get_real_ragas_scorecard(openai_key=openai_key)

                if not r_results:
                    error_msg = "RAGAS evaluation failed. Please verify that your selected judge model is running."
                elif eval_mode == "openai" and (math.isnan(r_precision) or math.isnan(r_recall)):
                    error_msg = "Ragas returned NaN scores. Please verify your OpenAI billing quota."
                else:
                    results = []
                    for row in r_results:
                        row = dict(row)
                        for metric in ("context_precision", "context_recall"):
                            if metric in row:
                                row[metric] = _nan_to_zero(row[metric])
                        results.append(row)
                    avg_precision = r_precision
                    avg_recall = r_recall
                    is_real_ragas = True
                    judge = "local Ollama (Llama 3)" if eval_mode == "ollama" else "OpenAI LLM"
                    success_msg = f"Successfully computed actual RAGAS metrics using {judge} Judge!"
            except Exception as e:
                error_msg = f"Error during Ragas evaluation: {str(e)}"

    return render_template("evaluate.html",
                           results=results,
                           avg_precision=_pct(avg_precision) or 0.0,
                           avg_recall=_pct(avg_recall) or 0.0,
                           avg_similarity=_pct(avg_similarity),
                           is_real_ragas=is_real_ragas,
                           error_msg=error_msg,
                           success_msg=success_msg)
