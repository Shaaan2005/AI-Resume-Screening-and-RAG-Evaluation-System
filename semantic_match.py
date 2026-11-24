from model_loader import model
from sklearn.metrics.pairwise import cosine_similarity
import logging

from resume_engine import chunk_text

logger = logging.getLogger("ResumeScreening")


def best_chunk_similarity(job_embedding, chunk_embeddings):
    """Highest cosine similarity (0-100) between a job embedding and any chunk embedding."""
    if chunk_embeddings is None or len(chunk_embeddings) == 0:
        return 0.0
    sims = cosine_similarity([job_embedding], chunk_embeddings)[0]
    return round(max(0.0, min(100.0, float(sims.max()) * 100)), 2)


def get_similarity(job_description, resume_text):
    """Match score (0-100) between a job description and a whole resume.

    The resume is split into the same chunks search uses and the best-matching
    chunk wins. (Embedding the resume in one go would silently cut it off: the
    model reads at most 384 tokens, roughly the first page.) This keeps upload
    scores on the same scale as search scores. Returns 0.0 on empty input or errors.
    """
    if not job_description or not isinstance(job_description, str) or not job_description.strip():
        return 0.0
    if not resume_text or not isinstance(resume_text, str) or not resume_text.strip():
        return 0.0

    try:
        chunks = chunk_text(resume_text)
        return best_chunk_similarity(model.encode(job_description), model.encode(chunks))
    except Exception as e:
        logger.warning(f"Failed to calculate semantic similarity: {e}")
        return 0.0
