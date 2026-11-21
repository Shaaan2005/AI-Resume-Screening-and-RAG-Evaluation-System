"""Home page, smart candidate search, and resume downloads."""
import os
import re
import logging

from flask import Blueprint, request, render_template, send_from_directory, abort
from werkzeug.utils import secure_filename

from chroma_search import search_candidates, get_collection
from query_parsing import (detect_category, extract_search_intent, is_garbage,
                           meaningful_terms, parse_requested_count)
from skills_config import SKILLS_BY_CATEGORY

from .history import load_history
from .security import login_required

logger = logging.getLogger("ResumeScreening")

bp = Blueprint("search", __name__)


@bp.route("/")
@login_required
def home():
    return render_template("index.html", recent=load_history())


def _results(job_description, msg, category=None):
    """Renders an empty result page with a message."""
    return render_template("search_results.html",
        category=category, rankings=[], total_candidates=0,
        job_description=job_description, msg=msg)


@bp.route("/search", methods=["POST"])
@login_required
def search():
    job_description = request.form.get("job_description", "").strip()
    if not job_description:
        return _results("", "Please enter a search query.")

    if is_garbage(job_description):
        return _results(job_description,
            "That doesn't look like a valid search — try something like 'top 5 from engineering'")

    if not meaningful_terms(job_description):
        return _results(job_description,
            "Please be more specific — try adding skills or a department name")

    search_intent = extract_search_intent(job_description) or job_description
    logger.info(f"[SMART SEARCH] Query: '{job_description}' -> Intent: '{search_intent}'")

    all_dept = bool(re.search(r'\b(all|every)\s+departments?\b', job_description.lower()))

    if all_dept:
        categories = list(SKILLS_BY_CATEGORY.keys())
    else:
        detected = detect_category(job_description)
        categories = [detected] if detected else []

    is_multi = all_dept or len(categories) > 1
    category = categories[0] if categories else None
    multi_msg = None
    if all_dept:
        multi_msg = f"Showing results across {len(categories)} departments"
    elif len(categories) > 1:
        multi_msg = f"Multiple departments detected: {', '.join(categories)}"

    if is_multi:
        all_rankings = []
        seen = set()
        for cat in categories:
            for r in search_candidates(search_intent, category=cat):
                if r["resume"] not in seen:
                    seen.add(r["resume"])
                    all_rankings.append(r)
        all_rankings.sort(key=lambda x: x["similarity"], reverse=True)
        for i, r in enumerate(all_rankings, 1):
            r["rank"] = i
        rankings = all_rankings
    else:
        rankings = search_candidates(search_intent, category=category)

    if not rankings:
        return _results(job_description, f"No candidates found in {category or 'database'}", category)

    requested = parse_requested_count(job_description)
    msg = None

    if requested is None and is_multi and "each" in job_description.lower():
        requested = 1
    if requested is None:
        if re.search(r'\b(best|top)\b', job_description.lower()):
            requested = 1

    if requested and is_multi:
        # Limit to `requested` candidates per department
        limited = []
        seen_cat = {}
        for r in rankings:
            rcat = r.get("category", "")
            seen_cat.setdefault(rcat, 0)
            if seen_cat[rcat] < requested:
                limited.append(r)
                seen_cat[rcat] += 1
        rankings = limited
    elif requested:
        if requested > len(rankings):
            msg = f"Only {len(rankings)} candidates found in {category or 'database'} (requested {requested})"
        rankings = rankings[:requested]

    collection = get_collection()
    total_candidates = collection.count() if collection else 0

    return render_template("search_results.html",
        category=category,
        rankings=rankings,
        total_candidates=total_candidates,
        job_description=job_description,
        msg=msg,
        multi_msg=multi_msg)


@bp.route("/resume/<category>/<filename>")
@login_required
def download_resume(category, filename):
    """Safely serves resume PDFs with strict path traversal protections."""
    # 1. Whitelist category against known categories
    if category not in SKILLS_BY_CATEGORY:
        abort(404, description="Invalid department category.")

    # 2. Strict filename sanitization
    safe_filename = secure_filename(filename)
    if not safe_filename or safe_filename != filename:
        abort(404, description="Invalid filename characters detected.")

    safe_dir = os.path.join(os.path.abspath("resumes"), category)
    if not os.path.isdir(safe_dir):
        abort(404, description="Department directory not found.")

    return send_from_directory(safe_dir, safe_filename)
