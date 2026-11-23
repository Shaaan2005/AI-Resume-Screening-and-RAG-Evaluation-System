"""One rule, used on every page, for turning a match score into a recommendation.

The match score is the cosine similarity between the query (or job description)
and a resume's best-matching section, x 100: the number search ranks by and the
one shown to the user.

A raw score mixes two things: how well the resume fits, and how the query is
worded (short or unusual queries score lower against every resume). So the
verdict compares the resume with the 242 sample resumes for the *same* query:
how many standard deviations its score sits above their average.

Calibrated on 120 labeled queries (benchmark/queries*.json) x 242 resumes:
  >= 2.5 above average -> 60% are from the right department -> SHORTLIST
  >= 1.5 above average -> 33% (8x the base rate)             -> CONSIDER
  otherwise                                                  -> REJECT
These match the precision of the previous fixed cutoffs (60 -> 62%, 50 -> 31%),
but separate right from wrong better (AUC 0.865 vs 0.786), so far fewer
realistic searches end with no candidate above REJECT (2 of 120 instead of 34).
"""
from dataclasses import dataclass

SHORTLIST_Z = 2.5
CONSIDER_Z = 1.5


@dataclass(frozen=True)
class Baseline:
    """How the sample resumes score against one query."""
    mean: float
    std: float
    count: int
    scores: tuple = ()  # every sample resume's score, ascending

    def cutoff(self, z):
        """The raw score a resume needs for `z` (e.g. CONSIDER_Z) on this query."""
        return round(self.mean + z * self.std, 2)

    def percentile(self, score):
        """Share of sample resumes (0-100) scoring below `score` on this query."""
        if not self.scores:
            return None
        below = sum(1 for s in self.scores if s < score)
        return round(100.0 * below / len(self.scores))


def recommend(score, baseline):
    """SHORTLIST / CONSIDER / REJECT for a 0-100 match score on a given query."""
    if baseline is None or baseline.std <= 0:
        return "REJECT" if score < 50 else "CONSIDER"  # no reference to compare with
    z = (score - baseline.mean) / baseline.std
    if z >= SHORTLIST_Z:
        return "SHORTLIST"
    if z >= CONSIDER_Z:
        return "CONSIDER"
    return "REJECT"


def band(recommendation):
    """Colour class for a recommendation (green / yellow / red)."""
    return {"SHORTLIST": "green", "CONSIDER": "yellow", "REJECT": "red"}.get(recommendation, "")
