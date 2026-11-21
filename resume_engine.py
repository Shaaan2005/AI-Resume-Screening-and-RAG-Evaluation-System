import os
import re
import logging
import pdfplumber
import docx

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

    return text.strip()


def _contains_skill(skill, text):
    """True if `skill` appears in `text` as a whole term.

    Plain `\\b` word boundaries break on skills like "c++" or "node.js", so we
    require that the characters around the match are not letters or digits.
    This stops "go" matching "good" and "java" matching "javascript".
    """
    pattern = r"(?<![a-z0-9])" + re.escape(skill) + r"(?![a-z0-9])"
    return re.search(pattern, text) is not None


def analyze_resume(path, category=None):
    """Analyzes resume text against a reference skill dictionary.

    If `category` matches a key in SKILLS_BY_CATEGORY, the resume is scored
    against that role's skills only. Otherwise it falls back to the global
    skills.txt list.

    Returns:
      {
         "score": float (0-100),
         "skills": list[str],
         "recommendation": "SHORTLIST" | "CONSIDER" | "REJECT"
      }
    """
    text = extract_resume_text(path).lower()
    if not text:
        return {
            "score": 0.0,
            "skills": [],
            "recommendation": "REJECT"
        }

    reference = SKILLS_BY_CATEGORY.get(category) if category else None
    if not reference:
        reference = skills

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
        "recommendation": recommendation
    }


def chunk_text(text, chunk_size=200):
    """Splits document text into overlapping or sequential word chunks."""
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
