from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-MiniLM-L6-v2')

job_description = """
Looking for Python Developer with Flask, SQL and Machine Learning skills
"""

resume_text = """
Experienced Python developer.
Worked with Flask APIs.
Strong SQL knowledge.
Built Machine Learning projects.py test_embeddings.py
"""             

job_embedding = model.encode(job_description)

resume_embedding = model.encode(resume_text)

print("Job Vector Length:", len(job_embedding))
print("Resume Vector Length:", len(resume_embedding))