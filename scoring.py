"""One rule, used on every page, for turning a match score into a recommendation.

The match score is the cosine similarity between the job description and the
resume's best-matching chunk, x 100 (the same number search ranks by).

Thresholds were calibrated on the benchmark (48 labeled queries x 242 resumes,
where only ~4% of pairs are from the right job category):
  score >= 60  -> 57% of resumes are from the right category  -> SHORTLIST
  score >= 50  -> 29% (7x the base rate)                      -> CONSIDER
  below 50                                                     -> REJECT
A typical right-category resume scores ~53, so it lands on CONSIDER and strong
matches reach SHORTLIST.
"""

SHORTLIST_AT = 60.0
CONSIDER_AT = 50.0


def recommend(score):
    """SHORTLIST / CONSIDER / REJECT for a 0-100 match score."""
    if score >= SHORTLIST_AT:
        return "SHORTLIST"
    if score >= CONSIDER_AT:
        return "CONSIDER"
    return "REJECT"


def band(score):
    """Colour class for a score, consistent with recommend()."""
    return {"SHORTLIST": "green", "CONSIDER": "yellow", "REJECT": "red"}[recommend(score)]
