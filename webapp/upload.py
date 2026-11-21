"""Single-resume upload: validate, score against a job description, and index."""
import os
import uuid
import logging
from datetime import datetime

from flask import Blueprint, request, render_template, current_app
from werkzeug.utils import secure_filename

from chroma_search import search_candidates, get_collection
from model_loader import model
from query_parsing import detect_category
from resume_engine import analyze_resume, extract_resume_text, chunk_text
from semantic_match import get_similarity

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


def _index_resume(unique_filename, resume_text, result, category):
    """Chunks, embeds, and upserts the uploaded resume into the vector store."""
    chunks = chunk_text(resume_text)
    if not chunks:
        return
    collection = get_collection()
    if not collection:
        return
    collection.upsert(
        ids=[f"{unique_filename}_chunk{idx}" for idx in range(len(chunks))],
        embeddings=[model.encode(chunk).tolist() for chunk in chunks],
        documents=chunks,
        metadatas=[{
            "resume": unique_filename,
            "chunk": idx,
            "total_chunks": len(chunks),
            "recommendation": result["recommendation"],
            "skill_score": result["score"],
            "category": category or ""
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
        header = file.read(16)
        file.seek(0)
    except Exception as e:
        logger.warning(f"File signature read error: {e}")
        return _error("Unable to read uploaded file format.", file.filename, job_description)
    if not header.startswith(FILE_SIGNATURES[ext]):
        kind = "PDF" if ext == ".pdf" else "DOCX"
        return _error(f"Invalid or corrupted {kind} file signature.", file.filename, job_description)

    # 3. Path traversal defense & unique filename generation
    clean_name = secure_filename(file.filename) or ("resume" + ext)
    unique_filename = f"{uuid.uuid4().hex[:8]}_{clean_name}"
    upload_folder = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_folder, exist_ok=True)
    file_path = os.path.join(upload_folder, unique_filename)
    file.save(file_path)

    try:
        category = detect_category(job_description)
        result = analyze_resume(file_path, category=category)
        resume_text = extract_resume_text(file_path)
        semantic_score = get_similarity(job_description, resume_text)

        keyword_pct = result['score']
        combined_score = round(keyword_pct * 0.4 + semantic_score * 0.6, 1)
        if combined_score >= 60:
            combined_rec = "SHORTLIST"
        elif combined_score >= 35:
            combined_rec = "CONSIDER"
        else:
            combined_rec = "REJECT"

        _index_resume(unique_filename, resume_text, result, category)

        rankings = search_candidates(job_description, category=category)
        collection = get_collection()
        total_candidates = collection.count() if collection else 0

        save_history({
            "filename": clean_name,
            "score": float(semantic_score),
            "recommendation": result["recommendation"],
            "timestamp": datetime.now().strftime("%d %b %Y, %I:%M %p")
        })

        return render_template("result.html",
            filename=clean_name,
            error=None,
            result=result,
            semantic_score=semantic_score,
            keyword_pct=keyword_pct,
            combined_score=combined_score,
            combined_rec=combined_rec,
            rankings=rankings,
            total_candidates=total_candidates,
            job_description=job_description,
            category=category)
    except Exception as e:
        logger.error(f"Error processing resume upload: {e}")
        return _error(f"Error analyzing resume: {str(e)}", clean_name, job_description)
