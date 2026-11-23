import os
import re
import logging
import docx
import ftfy
import pdfplumber

from skills_config import SKILLS_BY_CATEGORY

logger = logging.getLogger("ResumeScreening")

# Load skills list safely at module level
_SKILLS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills.txt")


def _load_skills():
    """Loads standardized skill list from skills.txt."""
    try:
        with open(_SKILLS_FILE, encoding="utf-8") as f:
            return [line.strip().lower() for line in f if line.strip()]
    except FileNotFoundError:
        logger.warning(f"skills.txt not found at {_SKILLS_FILE}. Skill matching will be disabled.")
        return []
    except Exception as e:
        logger.warning(f"Could not read skills.txt: {e}")
        return []


skills = _load_skills()

# Many sample PDFs carry text that was mis-decoded before it reached us ("â€“" for "–",
# "Â·" for "·"). ftfy repairs most of it; these are sequences where one original byte
# was lost (it came out as a zero-width space), so ftfy can't recover them alone.
_LOST_BYTE_FIXES = {"â€\u200b": "”", "â—\u200b": "●", "ï¼\u200b": "-", "ï¼": "-"}
# Template placeholders left in some sample resumes ("Dedicated [job title] with ...")
_PLACEHOLDER = re.compile(r"\[(?:number|job title|objective|area|type|time period|company name|"
                          r"city|state|name of [^\]\n]{1,40})\]", re.I)


def clean_text(text):
    """Repairs garbled characters and removes template placeholders."""
    if not text:
        return ""
    for broken, fixed in _LOST_BYTE_FIXES.items():
        text = text.replace(broken, fixed)
    text = ftfy.fix_text(text).replace("\u200b", "").replace("\xa0", " ")
    text = re.sub(r"Â(?=\s|$)", "", text)  # a broken non-breaking space
    text = _PLACEHOLDER.sub("", text)
    return re.sub(r"[ \t]{2,}", " ", text)


def extract_resume_text(path):
    """Safely extracts text content from PDF or DOCX file.
    
    Handles corrupted files, missing files, empty files, and unexpected encodings gracefully.
    """
    if not path or not os.path.exists(path):
        logger.warning(f"Resume file not found: {path}")
        return ""

    text = ""
    lower_path = path.lower()

    if lower_path.endswith(".pdf"):
        try:
            with pdfplumber.open(path) as pdf:
                if not pdf.pages:
                    logger.info(f"PDF {path} has 0 pages.")
                    return ""
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
        except Exception as e:
            logger.warning(f"Failed to extract PDF text from {path}: {e}")
            return ""

    elif lower_path.endswith(".docx"):
        try:
            doc = docx.Document(path)
            for para in doc.paragraphs:
                if para.text:
                    text += para.text + "\n"
        except Exception as e:
            logger.warning(f"Failed to extract DOCX text from {path}: {e}")
            return ""

    return clean_text(text).strip()


def _contains_skill(skill, text):
    """True if `skill` appears in `text` as a whole term.

    Plain `\\b` word boundaries break on skills like "c++" or "node.js", so we
    require that the characters around the match are not letters or digits.
    This stops "go" matching "good" and "java" matching "javascript".
    """
    pattern = r"(?<![a-z0-9])" + re.escape(skill) + r"(?![a-z0-9])"
    return re.search(pattern, text) is not None


def analyze_resume(path, category=None, text=None, job_description=None):
    """Keyword check: which of the wanted skills appear in the resume.

    With a `job_description` that names known skills, those are the wanted
    skills ("9 of the 9 skills the job asks for"). Otherwise:

    If `category` matches a key in SKILLS_BY_CATEGORY, the resume is checked
    against that role's skills only. Otherwise it falls back to the global
    skills.txt list. Pass `text` if it was already extracted, to avoid
    reading the file twice.

    The score is skill coverage (matched / all skills for the role). It's
    shown as supporting detail; the app's SHORTLIST/CONSIDER/REJECT decision
    comes from the semantic match score (see scoring.py).

    Returns:
      {
         "score": float (0-100),
         "skills": list[str],
         "recommendation": "SHORTLIST" | "CONSIDER" | "REJECT"
      }
    """
    text = (text if text is not None else extract_resume_text(path)).lower()
    if not text:
        return {
            "score": 0.0,
            "skills": [],
            "recommendation": "REJECT"
        }

    role_skills = SKILLS_BY_CATEGORY.get(category) if category else None
    reference = role_skills or skills
    basis = "role" if role_skills else "all"
    if job_description:
        jd = job_description.lower()
        wanted = list(dict.fromkeys(s for s in list(role_skills or []) + list(skills) if _contains_skill(s, jd)))
        if wanted:
            # Measured against what the job asks for, not a role template the job may not need
            reference, basis = wanted, "job"

    matched_skills = [s for s in reference if _contains_skill(s, text)]

    if reference:
        score = (len(matched_skills) / len(reference)) * 100
    else:
        score = 0.0

    score = round(max(0.0, min(100.0, score)), 2)

    if score >= 70:
        recommendation = "SHORTLIST"
    elif score >= 40:
        recommendation = "CONSIDER"
    else:
        recommendation = "REJECT"

    return {
        "score": score,
        "skills": matched_skills,
        "recommendation": recommendation,
        "wanted": len(reference),
        "basis": basis,
        # Wanted skills the resume doesn't mention (shown as "missing" chips)
        "missing": [s for s in reference if s not in matched_skills],
    }


def chunk_text(text, chunk_size=200):
    """Splits document text into consecutive, non-overlapping chunks of `chunk_size` words."""
    if not text or not isinstance(text, str):
        return []

    words = text.split()
    if not words:
        return []

    chunks = []
    for i in range(0, len(words), chunk_size):
        chunk = " ".join(words[i:i + chunk_size]).strip()
        if chunk:
            chunks.append(chunk)
    return chunks
