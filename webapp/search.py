"""Home page, smart candidate search, and resume downloads."""
import os
import re
import logging

from flask import Blueprint, request, render_template, send_from_directory, abort, current_app, session
from werkzeug.utils import secure_filename

import resume_engine
from chroma_search import search_candidates, get_collection, RESUMES_DIR, _dataset_names
from query_parsing import (detect_category, extract_search_intent, is_garbage,
                           meaningful_terms, parse_requested_count)
from skills_config import SKILLS_BY_CATEGORY

from .history import load_history
from .security import login_required

logger = logging.getLogger("ResumeScreening")

bp = Blueprint("search", __name__)

# "best python developers" / "top accountants" without a number
DEFAULT_TOP_N = 5


def _stats():
    """Live numbers for the home page (instead of hard-coded ones)."""
    collection = get_collection()
    return {
        "resumes": len(_dataset_names()),
        "departments": len(SKILLS_BY_CATEGORY),
        "skills": len(resume_engine.skills),
        "chunks": collection.count() if collection else 0,
    }


@bp.route("/")
@login_required
def home():
    return render_template("index.html", recent=load_history(session.get("user_id")), stats=_stats())


def _results(job_description, msg, category=None):
    """Renders an empty result page with a message."""
    return render_template("search_results.html",
        category=category, rankings=[], total_candidates=0,
        job_description=job_description, msg=msg)


def _key(r):
    return (r.get("source"), r.get("file") or r["resume"])


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
    owner = session.get("user_id")

    all_dept = bool(re.search(r'\b(all|every)\s+departments?\b', job_description.lower()))
    category = None
    multi_msg = None

    if all_dept:
        multi_msg = f"Showing results across {len(SKILLS_BY_CATEGORY)} departments"
        rankings, seen = [], set()
        for cat in SKILLS_BY_CATEGORY:
            for r in search_candidates(search_intent, category=cat, owner=owner):
                if _key(r) not in seen:
                    seen.add(_key(r))
                    rankings.append(r)
        rankings.sort(key=lambda x: x["similarity"], reverse=True)
    else:
        category = detect_category(job_description)
        if category is None:
            multi_msg = ("Couldn't tell which department you meant, so this searches all departments. "
                         "Add one (e.g. \"from finance\") to narrow it down.")
        rankings = search_candidates(search_intent, category=category, owner=owner)

    if not rankings:
        return _results(job_description, f"No candidates found in {category or 'any department'}", category)

    requested = parse_requested_count(job_description)
    msg = None
    if requested is None and all_dept and "each" in job_description.lower():
        requested = 1
    if requested is None and re.search(r'\b(best|top)\b', job_description.lower()):
        requested = DEFAULT_TOP_N

    if requested and all_dept:
        # Limit to `requested` candidates per department
        limited, per_cat = [], {}
        for r in rankings:
            rcat = r.get("category", "")
            if per_cat.get(rcat, 0) < requested:
                limited.append(r)
                per_cat[rcat] = per_cat.get(rcat, 0) + 1
        rankings = limited
    elif requested:
        if requested > len(rankings):
            msg = f"Only {len(rankings)} candidates found in {category or 'the database'} (requested {requested})"
        rankings = rankings[:requested]

    for i, r in enumerate(rankings, 1):
        r["rank"] = i

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
    """Serves a sample resume from resumes/<category>/, with path traversal protection."""
    if category not in SKILLS_BY_CATEGORY:
        abort(404, description="Invalid department category.")

    safe_filename = secure_filename(filename)
    if not safe_filename or safe_filename != filename:
        abort(404, description="Invalid filename characters detected.")

    safe_dir = os.path.join(RESUMES_DIR, category)
    if not os.path.isdir(safe_dir):
        abort(404, description="Department directory not found.")

    return send_from_directory(safe_dir, safe_filename)


@bp.route("/my-uploads/<filename>")
@login_required
def download_upload(filename):
    """Serves one of the current user's own uploaded resumes (never anyone else's)."""
    safe_filename = secure_filename(filename)
    if not safe_filename or safe_filename != filename:
        abort(404, description="Invalid filename characters detected.")
    if not safe_filename.startswith(f"{session['user_id']}_"):
        abort(404, description="File not found.")  # someone else's upload: don't reveal it exists
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], safe_filename)
