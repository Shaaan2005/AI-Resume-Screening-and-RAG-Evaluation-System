from model_loader import model
from sklearn.metrics.pairwise import cosine_similarity
import logging

logger = logging.getLogger("ResumeScreening")


def get_similarity(job_description, resume_text):
    """Computes cosine similarity percentage between job description and resume text.
    
    Returns a float between 0.0 and 100.0. Safely returns 0.0 on empty inputs or model errors.
    """
    if not job_description or not isinstance(job_description, str) or not job_description.strip():
        return 0.0
    if not resume_text or not isinstance(resume_text, str) or not resume_text.strip():
        return 0.0

    try:
        jd_embedding = model.encode(job_description)
        resume_embedding = model.encode(resume_text)

        similarity = cosine_similarity(
            [jd_embedding],
            [resume_embedding]
        )[0][0]

        # Clamp between 0.0 and 100.0
        score = max(0.0, min(100.0, float(similarity) * 100))
        return round(score, 2)
    except Exception as e:
        logger.warning(f"Failed to calculate semantic similarity: {e}")
        return 0.0
