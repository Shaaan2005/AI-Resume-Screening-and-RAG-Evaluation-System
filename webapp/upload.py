"""Single-resume upload: validate, score against a job description, and index privately."""
import os
import hashlib
import logging

from flask import Blueprint, request, render_template, current_app, session
from werkzeug.utils import secure_filename

from chroma_search import search_candidates, get_collection
from model_loader import model
from query_parsing import detect_category
from resume_engine import analyze_resume, extract_resume_text, chunk_text
from scoring import recommend
from semantic_match import best_chunk_similarity

from .history import save_history
from .security import login_required

logger = logging.getLogger("ResumeScreening")

bp = Blueprint("upload", __name__)

ALLOWED_EXTENSIONS = {".pdf", ".docx"}
FILE_SIGNATURES = {".pdf": b"%PDF-", ".docx": b"PK\x03\x04"}


def _error(message, filename="", job_description=""):
    """Renders the result page in an error state with zeroed scores."""
    return render_template("result.html", error=message,
                           filename=filename, result={"score": 0, "skills": [], "recommendation": "REJECT"},
                           semantic_score=0, keyword_pct=0, combined_score=0, combined_rec="REJECT",
                           rankings=[], total_candidates=0, job_description=job_description, category=None)


def stored_name(user_id, content, ext):
    """Owner id + content fingerprint: re-uploading the same file reuses one entry."""
    return f"{user_id}_{hashlib.sha256(content).hexdigest()[:16]}{ext}"


# Cosine distance below which two chunks are the same text (identical text gives ~0)
SAME_TEXT_DISTANCE = 0.01


def _dataset_twin(collection, embeddings):
    """"CATEGORY/name" of the sample resume this upload is a copy of, or "".

    Lets search show the owner one entry ("Your upload") instead of two.
    """
    try:
        r = collection.query(query_embeddings=[embeddings[0].tolist()], n_results=1,
                             where={"source": {"$ne": "upload"}}, include=["metadatas", "distances"])
    except Exception as e:
        logger.warning(f"Duplicate check failed: {e}")
        return ""
    if r["ids"] and r["ids"][0] and r["distances"][0][0] < SAME_TEXT_DISTANCE:
        meta = r["metadatas"][0][0]
        return f"{meta.get('category', '')}/{meta.get('resume', '')}"
    return ""


def _index_resume(owner, stored, display_name, chunks, embeddings, keyword_result):
    """Adds the uploaded resume to the search index, visible only to its owner.

    Chunk ids derive from the stored name, so uploading the same file again
    replaces its entries instead of adding duplicates. No department is stored:
    guessing one from a resume was right <50% of the time on the benchmark, so
    the owner's uploads are searched across all departments instead.
    """
    collection = get_collection()
    if not collection or not chunks:
        return
    twin = _dataset_twin(collection, embeddings)
    collection.upsert(
        ids=[f"upload_{stored}_chunk{idx}" for idx in range(len(chunks))],
        embeddings=embeddings.tolist(),
        documents=chunks,
        metadatas=[{
            "resume": display_name,
            "file": stored,
            "source": "upload",
            "owner": str(owner),
            "chunk": idx,
            "total_chunks": len(chunks),
            "skill_score": keyword_result["score"],
            "category": "",
            "duplicate_of": twin,
        } for idx in range(len(chunks))]
    )


@bp.route("/upload", methods=["POST"])
@login_required
def upload():
    job_description = request.form.get("job_description", "").strip()
    if not job_description:
        return _error("Job description is required.")

    file = request.files.get("resume")
    if not file or not file.filename:
        return _error("Please upload a resume file.", job_description=job_description)

    # 1. Extension whitelist
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return _error("Only PDF and DOCX files are supported.", file.filename, job_description)

    # 2. Magic-byte signature validation
    try:
        content = file.read()
    except Exception as e:
        logger.warning(f"File read error: {e}")
        return _error("Unable to read uploaded file format.", file.filename, job_description)
    if not content.startswith(FILE_SIGNATURES[ext]):
        kind = "PDF" if ext == ".pdf" else "DOCX"
        return _error(f"Invalid or corrupted {kind} file signature.", file.filename, job_description)

    # 3. Safe display name; storage name = owner + content hash (no path from the user)
    owner = session["user_id"]
    clean_name = secure_filename(file.filename) or ("resume" + ext)
    demo_mode = current_app.config.get("DEMO_MODE", False)
    stored = stored_name(owner, content, ext)
    upload_folder = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_folder, exist_ok=True)
    file_path = os.path.join(upload_folder, stored)
    already_stored = os.path.exists(file_path)  # same file uploaded before by this user
    with open(file_path, "wb") as f:
        f.write(content)

    try:
        category = detect_category(job_description)  # the role being hired for
        resume_text = extract_resume_text(file_path)
        if not resume_text:
            # Scanned or image-only PDFs have no text layer: without this check they got
            # a 0% score and REJECT, which looks like a bad candidate rather than a bad file.
            if not demo_mode and not already_stored:  # demo uploads are removed in `finally`
                os.remove(file_path)
            return _error("No text could be read from this file. It may be a scanned image; "
                          "please upload a PDF or DOCX with selectable text.", clean_name, job_description)
        keyword_result = analyze_resume(file_path, category=category, text=resume_text)

        # One score drives everything shown: best-chunk similarity, same scale as search
        chunks = chunk_text(resume_text)
        embeddings = model.encode(chunks) if chunks else []
        match_score = best_chunk_similarity(model.encode(job_description), embeddings)
        match_rec = recommend(match_score)

        if not demo_mode:
            _index_resume(owner, stored, clean_name, chunks, embeddings, keyword_result)

        rankings = search_candidates(job_description, category=category, owner=owner)
        collection = get_collection()
        total_candidates = collection.count() if collection else 0

        if not demo_mode:
            save_history(owner, clean_name, match_score, match_rec)

        return render_template("result.html",
            filename=clean_name,
            error=None,
            result=keyword_result,
            semantic_score=match_score,
            keyword_pct=keyword_result["score"],
            combined_score=match_score,
            combined_rec=match_rec,
            rankings=rankings,
            total_candidates=total_candidates,
            job_description=job_description,
            category=category)
    except Exception:
        logger.exception("Error processing resume upload")
        return _error("Something went wrong while analyzing this resume. Please try again or use a different file.",
                      clean_name, job_description)
    finally:
        if demo_mode:
            try:
                os.remove(file_path)  # visitors' resumes never stay on the server
            except OSError as e:
                logger.warning(f"Could not delete demo upload {file_path}: {e}")
