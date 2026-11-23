"""Home page, smart candidate search, and resume downloads."""
import os
import re
import logging

from flask import Blueprint, request, render_template, send_from_directory, abort, current_app, session
from werkzeug.utils import secure_filename

import resume_engine
from chroma_search import search_candidates, get_collection, RESUMES_DIR, _dataset_names
from query_parsing import (MAX_REQUESTED, detect_category, extract_search_intent, is_garbage,
                           meaningful_terms, named_departments, parse_requested_count, search_text)
from scoring import CONSIDER_AT
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


# Results shown when the query gives no count ("chef", "python developer with flask")
DEFAULT_RESULTS = 10
MAX_QUERY_CHARS = 2000
_COUNT_RE = re.compile(r"\b(?:top|best|show|give|find|get|need|want|select|choose|pick)\s+(-?\d+)\b")
_JOINED_RE = re.compile(r"\b(?:and|or)\b|[,&/]")


def _search_departments(query, categories, owner):
    """Searches several departments and merges the results, best first, without duplicates."""
    rankings, seen = [], set()
    for cat in categories:
        for r in search_candidates(query, category=cat, owner=owner):
            if _key(r) not in seen:
                seen.add(_key(r))
                rankings.append(r)
    rankings.sort(key=lambda x: x["similarity"], reverse=True)
    return rankings


def _count_note(query):
    """Explains a count that can't be used as typed ("top 0", "top -3", "top 500")."""
    m = _COUNT_RE.search(query.lower())
    if not m:
        return None
    n = int(m.group(1))
    if n <= 0:
        return f"\"{m.group(0)}\" isn't a valid number of results, so this shows the top {DEFAULT_TOP_N}."
    if n > MAX_REQUESTED:
        return f"Results are limited to {MAX_REQUESTED} per search."
    return None


@bp.route("/search", methods=["GET", "POST"])
@login_required
def search():
    # GET as well as POST: a search is read-only, so its URL can be refreshed, bookmarked and shared
    job_description = request.values.get("job_description", "").strip()
    if not job_description:
        return _results("", "Please enter a search query.")

    if len(job_description) > MAX_QUERY_CHARS:
        return _results(job_description[:200] + "…",
            f"Searches are limited to {MAX_QUERY_CHARS:,} characters. Paste the key requirements instead.")

    if is_garbage(job_description):
        return _results(job_description,
            "That doesn't look like a valid search — try something like 'top 5 from engineering'")

    if not meaningful_terms(job_description):
        return _results(job_description,
            "Please be more specific — try adding skills or a department name")

    search_intent = search_text(job_description)
    logger.info(f"[SMART SEARCH] Query: '{job_description}' -> Intent: '{search_intent}'")
    owner = session.get("user_id")
    lowered = job_description.lower()

    all_dept = bool(re.search(r'\b(all|every)\s+departments?\b', lowered))
    named = named_departments(job_description)
    # "top 3 from chef and sales": several departments joined by and/or/commas are all searched.
    # ("fashion designer" names two departments without a joining word, so it stays one search.)
    several = not all_dept and len(named) > 1 and bool(_JOINED_RE.search(lowered))
    category = None
    multi_msg = None
    per_department = all_dept or several

    if all_dept:
        multi_msg = f"Showing results across {len(SKILLS_BY_CATEGORY)} departments"
        rankings = _search_departments(search_intent, list(SKILLS_BY_CATEGORY), owner)
    elif several:
        multi_msg = "Showing results from " + " and ".join(named)
        rankings = _search_departments(search_intent, named, owner)
    else:
        category = detect_category(job_description)
        if category is None:
            multi_msg = ("No department matched this search, so it covers all departments. "
                         "Add one (e.g. \"from finance\") or a job title to narrow it down.")
        rankings = search_candidates(search_intent, category=category, owner=owner)

    if not rankings:
        return _results(job_description, f"No candidates found in {category or 'any department'}", category)

    requested = parse_requested_count(job_description)
    notes = [_count_note(job_description)]
    if requested is None and all_dept and "each" in lowered:
        requested = 1
    if requested is None:
        requested = DEFAULT_TOP_N if re.search(r'\b(best|top)\b', lowered) else DEFAULT_RESULTS

    if per_department:
        # `requested` candidates per department
        limited, per_cat = [], {}
        for r in rankings:
            rcat = r.get("category", "")
            if per_cat.get(rcat, 0) < requested:
                limited.append(r)
                per_cat[rcat] = per_cat.get(rcat, 0) + 1
        rankings = limited
    else:
        if requested > len(rankings):
            notes.append(f"Only {len(rankings)} candidates found in {category or 'the database'} (requested {requested}).")
        rankings = rankings[:requested]

    for i, r in enumerate(rankings, 1):
        r["rank"] = i

    # "top 3 from engineering" names a department but no requirements. A SHORTLIST/REJECT
    # verdict would only measure how well a resume matches the word "engineering", so
    # rank by general fit and leave the verdict out.
    requirements = [w for w in (extract_search_intent(job_description) or "").split() if re.search(r"[a-z]", w)]
    browse = not requirements  # numbers alone ("top 500") aren't requirements
    if browse:
        for r in rankings:
            r["recommendation"] = ""
        notes.append("No skills or requirements given, so these are ranked by general fit without "
                     "SHORTLIST/REJECT verdicts. Add requirements (e.g. \"chef with pastry experience\") to get them.")
    else:
        best = max(r["similarity"] for r in rankings)
        if best < CONSIDER_AT:
            notes.append(f"No strong matches: the best resume scores {best:.0f}% (CONSIDER starts at {CONSIDER_AT:.0f}%). "
                         "These are the closest resumes available, but the collection may have no one for this role.")

    collection = get_collection()
    total_candidates = collection.count() if collection else 0

    return render_template("search_results.html",
        category=category,
        rankings=rankings,
        total_candidates=total_candidates,
        job_description=job_description,
        msg=" ".join(n for n in notes if n) or None,
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
