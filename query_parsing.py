"""Recruiter query understanding: category detection, result counts, and noise filtering.

Pure functions with no Flask dependency, shared by the web app and the
evaluation scripts.
"""
import re
import logging

from chroma_search import get_cross_encoder
from skills_config import SKILLS_BY_CATEGORY

logger = logging.getLogger("ResumeScreening")

# Short technical terms that are meaningful despite being under 3 characters
# (or that would otherwise be filtered as noise).
SHORT_TECH_TERMS = {"c++", "c#", ".net", "go", "r", "js", "ts", "ui", "ux", "it",
                    "hr", "pr", "bd", "ml", "ai", "db"}

NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
             "seven": 7, "eight": 8, "nine": 9, "ten": 10}

SKIP_WORDS = {"the","a","an","in","on","at","to","for","with","from","by","and",
    "top","best","resume","resumes","candidate","candidates","list","show","give",
    "find","search","need","want","get","all","any","not","but","have","most",
    "matching","skills","experience","work","job","description","background",
    "team","role","skill","of","is","are","it","this","that",
    "looking","using","including","based","able","will","can","also",
    "well","per","year","years","new","like","make","made","one","each",
    "every","both","either","neither","some","few","several","many"}

INTENT_NOISE = {"show","list","find","search","need","want","get","give","me",
    "top","best","one","two","three","four","five","six","seven","eight",
    "nine","ten","each","every","per","all","both","neither","either",
    "any","some","few","several","many"}


# ── Category detection ──────────────────────────────────────────────────────

_CAT_DESCRIPTIONS = {
    "ACCOUNTANT": "The category for this query is ACCOUNTANT. Includes accounting, bookkeeper, auditor, tax consultant, CA, CPA, bookkeeping, payroll, audit.",
    "ADVOCATE": "The category for this query is ADVOCATE. Includes lawyer, attorney, legal counsel, solicitor, legal advisor, corporate lawyer, litigation, legal research, contract drafting.",
    "AGRICULTURE": "The category for this query is AGRICULTURE. Includes farmer, agronomist, agricultural scientist, horticulturist, farm manager, crop management, farming, agronomy.",
    "APPAREL": "The category for this query is APPAREL. Includes fashion, garment, textile, fashion designer, merchandiser, clothing, apparel designer, fashion design, garment construction.",
    "ARTS": "The category for this query is ARTS. Includes artist, painter, sculptor, illustrator, creative, fine arts, visual arts, digital art, graphic design, animation.",
    "AUTOMOBILE": "The category for this query is AUTOMOBILE. Includes automotive, mechanic, auto engineer, vehicle, car, motor, auto mechanics, engine repair, electric vehicles.",
    "AVIATION": "The category for this query is AVIATION. Includes pilot, flight, airline, aircraft, cabin crew, air traffic controller, flight attendant, aerospace, flight operations.",
    "BANKING": "The category for this query is BANKING. Includes banker, bank officer, loan officer, credit analyst, financial services, bank, investment banker, credit analysis, risk management.",
    "BPO": "The category for this query is BPO. Includes business process outsourcing, call center, customer support, customer service representative, telecaller, helpdesk, technical support.",
    "BUSINESS-DEVELOPMENT": "The category for this query is BUSINESS-DEVELOPMENT. Includes sales development, biz dev, partnerships, growth manager, business strategist, lead generation.",
    "CHEF": "The category for this query is CHEF. Includes cook, culinary, kitchen, baker, pastry chef, sous chef, head chef, food, culinary arts, cooking, menu planning.",
    "CONSTRUCTION": "The category for this query is CONSTRUCTION. Includes builder, site engineer, civil contractor, project manager construction, mason, civil engineering, structural engineering, blueprint.",
    "CONSULTANT": "The category for this query is CONSULTANT. Includes consulting, management consultant, strategy consultant, business analyst, advisor, strategic planning, management consulting.",
    "DESIGNER": "The category for this query is DESIGNER. Includes ui designer, ux designer, graphic designer, web designer, product designer, visual designer, figma, prototyping, wireframing.",
    "DIGITAL-MEDIA": "The category for this query is DIGITAL-MEDIA. Includes digital marketing, social media manager, content creator, seo specialist, online marketing, google ads, content strategy, copywriter.",
    "ENGINEERING": "The category for this query is ENGINEERING. Includes engineer, software engineer, software developer, programmer, coder, developer, devops engineer, data engineer, backend engineer, frontend engineer, full stack developer, software engineering, tech.",
    "FINANCE": "The category for this query is FINANCE. Includes financial analyst, investment analyst, portfolio manager, treasury, CFO, financial planner, wealth manager, financial modeling, valuation.",
    "FITNESS": "The category for this query is FITNESS. Includes personal trainer, gym instructor, fitness coach, yoga instructor, sports trainer, wellness coach, personal training, strength training.",
    "HEALTHCARE": "The category for this query is HEALTHCARE. Includes doctor, nurse, physician, medical, hospital, health, clinical, pharmacist, surgeon, therapist, patient care, nursing, surgery.",
    "HR": "The category for this query is HR. Includes human resources, recruiter, talent acquisition, hr manager, hr executive, people operations, hiring manager, recruitment, onboarding.",
    "INFORMATION-TECHNOLOGY": "The category for this query is INFORMATION-TECHNOLOGY. Includes IT support, system administrator, network administrator, sysadmin, cybersecurity, cloud computing, aws, linux, infrastructure.",
    "PUBLIC-RELATIONS": "The category for this query is PUBLIC-RELATIONS. Includes pr, communications, media relations, press, corporate communications, pr manager, spokesperson, press release.",
    "SALES": "The category for this query is SALES. Includes salesperson, sales executive, account executive, sales manager, business sales, lead generation, account management, closing.",
    "TEACHER": "The category for this query is TEACHER. Includes educator, professor, instructor, tutor, lecturer, teaching, academic, faculty, university professor, lecturing, classroom management.",
}


def cross_encoder_category_detect(query, threshold=0.3):
    """Semantic category detection using cross-encoder."""
    if not query or len(query.strip()) < 3:
        return None

    ce = get_cross_encoder()
    if ce is None:
        return None

    try:
        cats = list(_CAT_DESCRIPTIONS.keys())
        pairs = [(query, _CAT_DESCRIPTIONS[cat]) for cat in cats]
        scores = ce.predict(pairs)

        best_idx = int(scores.argmax())
        best_score = float(scores[best_idx])
        best_cat = cats[best_idx]

        logger.info(f"[CROSS-ENCODER CATEGORY] Query: '{query}' -> {best_cat} (score: {best_score:.4f})")
        return best_cat if best_score > threshold else None
    except Exception as e:
        logger.warning(f"Category detection failed: {e}")
        return None


def detect_category(job_description):
    """Semantic category detection using Cross-Encoder model."""
    return cross_encoder_category_detect(job_description)


# ── Query parsing ───────────────────────────────────────────────────────────

# A number followed by "years"/"months" is experience, not a result count ("need 2 years of python")
_NOT_DURATION = r'(?!\s*\+|\s*(?:years?|yrs?|months?|mos?)\b)'
MAX_REQUESTED = 50


def parse_requested_count(text):
    """How many results the recruiter asked for ("top 5", "three candidates"), or None.

    Ignores experience durations ("need 2 years", "3+ yrs") and nonsense counts
    (0 or below), and caps the count at MAX_REQUESTED.
    """
    t = text.lower()
    verbs = r'\b(top|best|select|choose|pick|find|show|give|get|need|want)\s+'
    nums = '|'.join(NUM_WORDS)
    for pattern, as_word in (
        (verbs + r'(\d+)\b' + _NOT_DURATION, False),
        (verbs + r'(' + nums + r')\b' + _NOT_DURATION, True),
        (r'\b(\d+)' + _NOT_DURATION + r'\s+(?:[a-z+#.-]+\s+){0,2}(?:resume|result|candidate|profile|people)s?\b', False),
        (r'\b(' + nums + r')' + _NOT_DURATION + r'\s+(?:[a-z+#.-]+\s+){0,2}(?:resume|result|candidate|profile|people)s?\b', True),
    ):
        match = re.search(pattern, t)
        if match:
            value = match.groups()[-1]
            n = NUM_WORDS[value] if as_word else int(value)
            return min(n, MAX_REQUESTED) if n > 0 else None
    return None


def extract_words(text):
    """Utility to extract all query terms including short/special tech words."""
    words = re.findall(r'[a-zA-Z0-9+#.-]+', text.lower())
    cleaned = []
    for w in words:
        w = w.strip(".,;:!?()")
        if w:
            cleaned.append(w)
    return cleaned


def meaningful_terms(text):
    """Query terms that carry search meaning (tech acronyms or 3+ chars, not filler)."""
    return [w for w in extract_words(text)
            if (w in SHORT_TECH_TERMS or len(w) >= 3) and w not in SKIP_WORDS]


def extract_search_intent(query):
    """Strips department names and filler, leaving the skills/role to search for."""
    t = query.lower()
    for cat in SKILLS_BY_CATEGORY:
        name = cat.lower().replace("-", " ")
        t = re.sub(rf'\b{re.escape(name)}\b', '', t)
    clean = [w for w in meaningful_terms(t) if w not in INTENT_NOISE]
    return " ".join(clean) if clean else None


# "it" and "r" are also ordinary English / a lone letter, so they only count as
# tech terms when written as "IT" / "R"; otherwise "asdfgh it" would pass as a query.
_AMBIGUOUS_TERMS = {"it": "IT", "r": "R"}


def is_garbage(text):
    """True for empty input or keyboard mashing with no real words."""
    if not text or not text.strip():
        return True
    words = extract_words(text)
    if not words:
        return not bool(re.search(r'[a-zA-Z0-9]', text))
    original_tokens = set(re.findall(r'[A-Za-z0-9+#.-]+', text))
    real = 0
    for w in words:
        if w in _AMBIGUOUS_TERMS:
            real += _AMBIGUOUS_TERMS[w] in original_tokens
            continue
        if w in SHORT_TECH_TERMS:
            real += 1
            continue
        # Filter out unpronounceable keyboard mashing (5+ consecutive consonants) or keyboard walks
        if re.search(r'[bcdfghjklmnpqrstvwxyz]{5,}', w):
            continue
        if re.search(r'^(asdf|qwerty|zxcv|1234)', w):
            continue
        if len(w) >= 3 and any(v in w for v in "aeiouy") and w not in SKIP_WORDS:
            real += 1
    return real == 0
