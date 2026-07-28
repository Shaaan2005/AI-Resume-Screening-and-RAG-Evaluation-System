from model_loader import model
from sklearn.metrics.pairwise import cosine_similarity


def get_similarity(job_description, resume_text):

    jd_embedding = model.encode(job_description)

    resume_embedding = model.encode(resume_text)

    similarity = cosine_similarity(
        [jd_embedding],
        [resume_embedding]
    )[0][0]

    return round(similarity * 100, 2)