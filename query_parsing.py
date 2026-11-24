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
    "ACCOUNTANT": "The category for this query is ACCOUNTANT. Roles: accountant, bookkeeper, auditor, accounts payable and receivable clerk, tax preparer, CPA, CA. Ledgers, journal entries, reconciliations, invoices, month-end close, tax returns, payroll, audits.",
    "ADVOCATE": "The category for this query is ADVOCATE. Roles: lawyer, attorney, advocate, legal counsel, solicitor, litigator, paralegal. Court cases, motions, pleadings, legal research, contracts, NDAs, agreements, compliance, disputes.",
    "AGRICULTURE": "The category for this query is AGRICULTURE. Roles: farmer, agronomist, crop scientist, farm manager, horticulturist, grower. Crops, soil, irrigation, livestock, dairy, greenhouse, harvest, seeds, pest control, yields.",
    "APPAREL": "The category for this query is APPAREL. Roles: fashion designer, garment technologist, pattern maker, textile merchandiser, clothing buyer. Garments, fabrics, knitwear, sewing, fit samples, trims, collections, mills.",
    "ARTS": "The category for this query is ARTS. Roles: artist, painter, illustrator, sculptor, musician, music teacher, art instructor, curator, performer. Painting, drawing, music, recitals, galleries, exhibitions, theatre, fine arts.",
    "AUTOMOBILE": "The category for this query is AUTOMOBILE. Roles: automotive mechanic, auto technician, body shop painter, collision repair technician, service advisor. Cars, vehicles, engines, brakes, transmissions, suspension, dealerships.",
    "AVIATION": "The category for this query is AVIATION. Roles: pilot, cabin crew, flight attendant, ramp agent, aircraft maintenance technician, flight dispatcher, air traffic controller. Airlines, aircraft, airports, baggage, flights.",
    "BANKING": "The category for this query is BANKING. Roles: banker, bank teller, loan officer, relationship manager, credit analyst, branch manager. Bank branches, deposits, accounts, mortgages, loans, credit, retail banking.",
    "BPO": "The category for this query is BPO. Roles: call center agent, customer support associate, chat support, help desk agent, telecaller, customer service representative. Outsourced support, tickets, SLAs, inbound and outbound calls, shifts.",
    "BUSINESS-DEVELOPMENT": "The category for this query is BUSINESS-DEVELOPMENT. Roles: business development manager, partnerships lead, growth manager, lead generation specialist. New markets, B2B deals, channel partners, prospecting enterprise accounts, alliances.",
    "CHEF": "The category for this query is CHEF. Roles: chef, cook, sous chef, pastry chef, baker, kitchen lead, line cook. Kitchens, menus, food preparation, plating, desserts, banquets, restaurants, food safety.",
    "CONSTRUCTION": "The category for this query is CONSTRUCTION. Roles: construction manager, site supervisor, foreman, civil engineer, quantity surveyor, contractor, builder. Building sites, concrete, framing, subcontractors, safety inspections, cost estimates.",
    "CONSULTANT": "The category for this query is CONSULTANT. Roles: management consultant, strategy consultant, business analyst, ERP and SAP implementation consultant, advisor. Client engagements, process improvement, workshops, operations, transformation.",
    "DESIGNER": "The category for this query is DESIGNER. Roles: graphic designer, UI/UX designer, web designer, brand designer, visual designer. Logos, branding, style guides, packaging, layouts, Figma, Illustrator, prototypes, wireframes.",
    "DIGITAL-MEDIA": "The category for this query is DIGITAL-MEDIA. Roles: digital marketer, social media manager, content creator, video editor, SEO specialist, paid ads specialist, marketing manager. Campaigns, Instagram, YouTube, Google Ads, video production, motion graphics.",
    "ENGINEERING": "The category for this query is ENGINEERING. Roles: mechanical engineer, electrical engineer, manufacturing engineer, quality engineer, design engineer, engineering technician. CAD, SolidWorks, AutoCAD, PLC, prototypes, failure analysis, manufactured parts.",
    "FINANCE": "The category for this query is FINANCE. Roles: financial analyst, FP&A analyst, investment analyst, treasury analyst, portfolio manager, CFO. Budgets, forecasting, variance reports, valuation models, equity research, cash flow.",
    "FITNESS": "The category for this query is FITNESS. Roles: personal trainer, fitness instructor, yoga instructor, pilates instructor, strength coach, gym trainer. Workouts, exercise programs, group classes, HIIT, spin, wellness.",
    "HEALTHCARE": "The category for this query is HEALTHCARE. Roles: medical staff, nurse, doctor, physician, pharmacist, pharmacy technician, medical coder, medical billing specialist, therapist. Patients, hospitals, clinics, prescriptions, ICD-10, medical records.",
    "HR": "The category for this query is HR. Roles: human resources generalist, recruiter, talent acquisition partner, HR manager, payroll and benefits administrator, people operations. Hiring, interviews, onboarding, employee relations, policies.",
    "INFORMATION-TECHNOLOGY": "The category for this query is INFORMATION-TECHNOLOGY. Roles: software developer, programmer, backend developer, Python developer, Java developer, software engineer, systems administrator, network administrator, IT support, help desk technician. Servers, Active Directory, cloud, APIs, databases, cybersecurity.",
    "PUBLIC-RELATIONS": "The category for this query is PUBLIC-RELATIONS. Roles: public relations specialist, press officer, communications manager, media spokesperson. Press releases, media relations, journalists, reputation, crisis communications, interviews.",
    "SALES": "The category for this query is SALES. Roles: sales representative, account executive, inside sales rep, field sales, sales manager. Cold calling, quotas, demos, renewals, closing deals, CRM pipelines, retail accounts.",
    "TEACHER": "The category for this query is TEACHER. Roles: teacher, educator, tutor, lecturer, professor, kindergarten teacher. Schools, classrooms, lesson plans, students, exams, literacy, curriculum.",
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


# Words that name a department outright. When a query uses one, the recruiter has
# told us the department, so we trust it instead of the cross-encoder's guess
# (which, e.g., sent "top 5 from engineering" to CONSTRUCTION).
_NOT_NON_SOFTWARE = r"(?<!business )(?<!estate )(?<!property )(?<!land )(?<!housing )"
_DEPARTMENT_ALIASES = {
    "ACCOUNTANT": ["accountants?", "accounting"],
    "ADVOCATE": ["advocates?", "lawyers?", "attorneys?"],
    "AGRICULTURE": ["agriculture", "agricultural", "farmers?"],
    "APPAREL": ["apparel", "fashion", "garments?", "textiles?"],
    "ARTS": ["(?<!martial )arts", "artists?"],
    "AUTOMOBILE": ["automobiles?", "automotive"],
    "AVIATION": ["aviation", "pilots?"],
    "BANKING": ["banking", "bankers?"],
    "BPO": ["bpo", "call cent(?:er|re)s?"],
    "BUSINESS-DEVELOPMENT": ["business[ -]development", "business developers?"],
    "CHEF": ["chefs?", "cooks?", "culinary"],
    "CONSTRUCTION": ["construction", "(?:real estate|property|housing|land) developers?",
                     "(?:civil|site|structural) engineers?"],
    "CONSULTANT": ["consultants?", "consulting"],
    "DESIGNER": ["designers?"],
    # No Marketing department in the data: marketing roles are closest to DIGITAL-MEDIA
    "DIGITAL-MEDIA": ["digital[ -]media", "(?:digital |online |content |performance |product )?marketing",
                      "marketers?", "social media"],
    # engineering disciplines (the model alone sent "Mechanical Engineer" to AUTOMOBILE)
    "ENGINEERING": ["engineering", "(?:mechanical|electrical|electronics?|chemical|thermal|industrial|"
                    "manufacturing|hardware|quality|design|product) engineers?"],
    "FINANCE": ["finance"],
    "FITNESS": ["fitness"],
    "HEALTHCARE": ["health ?care", "doctors?", "nurses?", "physicians?"],
    "HR": ["hr", "human resources?", "recruiters?"],
    # Software roles belong here: the dataset's ENGINEERING resumes are mechanical/electrical.
    # "developer" alone means software, but not in "business / real estate / property developer".
    "INFORMATION-TECHNOLOGY": ["information[ -]technology",
                               "it (?:support|help ?desk|administrators?|infrastructure)",
                               _NOT_NON_SOFTWARE + "developers?", "programmers?",
                               "(?<!billing )(?<!medical )coders?",
                               "(?:software|qa|test|devops|backend|frontend|full[ -]stack) engineers?",
                               "(?:system|network|database)s? administrators?", "sysadmins?"],
    "PUBLIC-RELATIONS": ["public[ -]relations"],
    "SALES": ["sales", "salespe(?:rson|ople)"],
    "TEACHER": ["teachers?", "professors?", "tutors?", "lecturers?"],
}
# Abbreviations that are also everyday words, so they only count in capitals.
_DEPARTMENT_ACRONYMS = {"IT": "INFORMATION-TECHNOLOGY", "BD": "BUSINESS-DEVELOPMENT",
                        "PR": "PUBLIC-RELATIONS"}
_ALIAS_PATTERNS = {cat: re.compile(r"(?<![\w-])(?:" + "|".join(words) + r")(?![\w-])", re.I)
                   for cat, words in _DEPARTMENT_ALIASES.items()}


def named_departments(query):
    """Departments the query names directly ("from engineering", "best 3 sales", "IT")."""
    found = [cat for cat, pattern in _ALIAS_PATTERNS.items() if pattern.search(query)]
    found += [cat for word, cat in _DEPARTMENT_ACRONYMS.items()
              if re.search(rf"\b{word}\b", query) and cat not in found]
    return found


def department_alternatives(query, chosen, n=2):
    """The next most likely departments after `chosen`, for "Not right? Try ..." links."""
    ce = get_cross_encoder()
    if ce is None or not query:
        return []
    cats = list(_CAT_DESCRIPTIONS)
    try:
        scores = ce.predict([(query, _CAT_DESCRIPTIONS[c]) for c in cats])
    except Exception as e:
        logger.warning(f"Could not rank alternative departments: {e}")
        return []
    ranked = [cats[i] for i in sorted(range(len(cats)), key=lambda i: -scores[i])]
    return [c for c in ranked if c != chosen][:n]


def detect_category(job_description):
    """The department a query is about.

    A department named in the query wins. If it names several ("fashion
    designer"), the cross-encoder picks between just those; if it names none,
    the cross-encoder picks from all departments.
    """
    if not job_description:
        return None
    named = named_departments(job_description)
    if len(named) == 1:
        return named[0]
    if named:
        ce = get_cross_encoder()
        if ce is not None:
            scores = ce.predict([(job_description, _CAT_DESCRIPTIONS[c]) for c in named])
            return named[int(scores.argmax())]
    if not job_words(job_description):
        # Nothing job-related to go on ("hello world", "best 5 astronaut"). The model
        # would still pick a department (usually FITNESS), so say none matched instead.
        return None
    return cross_encoder_category_detect(job_description)


# Words that make a query job-related: every skill plus the words describing each
# department. On the 70+ labeled test queries every real one contains one, while
# 14 of 15 nonsense queries contain none. (The model's confidence could not tell
# them apart: "hello world" scored higher than half the real queries.)
_GENERIC_WORDS = {"category", "query", "includes", "this", "manager", "management", "experience",
                  "experienced", "senior", "junior", "lead", "team", "work", "good", "best", "need",
                  "someone", "person", "people", "professional", "specialist", "officer", "executive",
                  "assistant", "analyst", "coordinator"}


def _stem(word):
    for suffix in ("ing", "ers", "er", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def _build_job_vocabulary():
    vocab = set()
    for description in _CAT_DESCRIPTIONS.values():
        vocab |= {_stem(w) for w in re.findall(r"[a-z+#]+", description.lower().split("roles:", 1)[1])
                  if len(w) >= 3}
    for skills in SKILLS_BY_CATEGORY.values():
        for skill in skills:
            vocab |= {_stem(w) for w in re.findall(r"[a-z+#]+", skill.lower()) if len(w) >= 3}
    return vocab - {_stem(w) for w in _GENERIC_WORDS | SKIP_WORDS | INTENT_NOISE}


_JOB_VOCABULARY = _build_job_vocabulary()


def job_words(query):
    """The words in a query that relate to some job or skill (empty for "hello world")."""
    return [w for w in re.findall(r"[a-z+#]+", query.lower()) if _stem(w) in _JOB_VOCABULARY]


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


_COMMAND = re.compile(
    r"\b(?:top|best|show|give|find|list|get|select|pick|choose)\b(?:\s+me)?(?:\s+(?:the|all))?"
    r"(?:\s*(?:\d+|" + "|".join(NUM_WORDS) + r")\b)?", re.I)
_RESULT_NOUNS = re.compile(r"\b(?:resumes?|candidates?|profiles?|results?)\b|\b(?:all|every)\s+departments?\b", re.I)


def search_text(query):
    """The text to embed for a search: the query minus "top 5" / "show me" / "resumes".

    Everything else stays, because the embedding model reads natural sentences
    best. Stripping down to keywords (`extract_search_intent`) both ranked worse
    (benchmark P@5 0.48 vs 0.56) and scored ~12 points lower, which pushed
    good matches under the SHORTLIST/CONSIDER thresholds.
    """
    t = _RESULT_NOUNS.sub(" ", _COMMAND.sub(" ", query))
    t = re.sub(r"\s+", " ", t).strip(" ,.;:")
    t = re.sub(r"^(?:from|in|of|for|among)\s+", "", t, flags=re.I)  # "from chef" -> "chef"
    return t if meaningful_terms(t) else query


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
