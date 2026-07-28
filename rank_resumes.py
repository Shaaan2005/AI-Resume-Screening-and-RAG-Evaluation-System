import os
from resume_engine import extract_resume_text
from semantic_match import get_similarity

job_description = """
Looking for a Python Developer with Flask, SQL, Git,
FastAPI, Machine Learning, REST API development,
cloud deployment experience, and strong problem-solving skills.
"""

results = []

for filename in os.listdir("resumes"):

    if filename.endswith(".pdf"):

        pdf_path = os.path.join("resumes", filename)

        resume_text = extract_resume_text(pdf_path)

        score = get_similarity(
            job_description,
            resume_text
        )

        results.append({
            "resume": filename,
            "score": score
        })

results.sort(
    key=lambda x: x["score"],
    reverse=True
)

print("\n===== CANDIDATE RANKING =====\n")

rank = 1

for candidate in results:

    print(
        f"{rank}. {candidate['resume']} - {candidate['score']}%"
    )

    rank += 1py rank_resumes.py