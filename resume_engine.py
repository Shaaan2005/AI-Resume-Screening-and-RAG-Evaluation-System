import pdfplumber
import docx

with open("skills.txt") as f:
    skills = [line.strip().lower() for line in f if line.strip()]

def analyze_resume(path):

    text = extract_resume_text(path).lower()

    matched_skills = []

    for skill in skills:

        if skill in text:
            matched_skills.append(skill)

    score = (len(matched_skills) / len(skills)) * 100

    if score >= 70:
        recommendation = "SHORTLIST"

    elif score >= 40:
        recommendation = "CONSIDER"

    else:
        recommendation = "REJECT"

    return {
        "score": round(score, 2),
        "skills": matched_skills,
        "recommendation": recommendation
    }


def extract_resume_text(path):

    text = ""

    if path.endswith(".pdf"):
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text

    elif path.endswith(".docx"):
        doc = docx.Document(path)
        for para in doc.paragraphs:
            text += para.text + "\n"
            
    return text


def chunk_text(text, chunk_size=200):
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size):
        chunk = " ".join(words[i:i+chunk_size])
        if chunk.strip():
            chunks.append(chunk)
    return chunks