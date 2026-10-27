import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from job_scout.config import KeywordConfig, ProfileConfig
from job_scout.matching import (
    contains_normalised_term,
    contains_term,
    normalise_words,
)
from job_scout.models import Job, Site
from job_scout.scorer import JobScorer


def test_single_letter_does_not_match_inside_words():
    haystack = "Remote research internship for a data team"
    assert not contains_term(haystack, "r")


def test_single_letter_matches_standalone_word():
    assert contains_term("r", "r")
    assert contains_term("R,", "r")
    assert contains_term("(R)", "r")
    assert contains_term("Experience with R, Python and SQL", "r")


def test_accents_are_ignored_in_both_directions():
    assert contains_term("España", "espana")
    assert contains_term("espana", "España")
    assert normalise_words("España") == "espana"


def test_multiword_term_tolerates_extra_whitespace():
    assert contains_term("data   analysis", "data analysis")
    assert contains_term("Data\nanalysis", "data analysis")


def test_empty_or_whitespace_term_never_matches():
    assert not contains_term("anything at all", "")
    assert not contains_term("anything at all", "   ")
    assert not contains_term("anything at all", None)


def test_fast_path_agrees_with_safe_path():
    """The optimised variant must never disagree with the safe one.

    ``contains_normalised_term`` skips re-normalising the haystack, which is the
    only difference between them; feeding it normalised text must give identical
    answers for every case the safe version covers.
    """
    haystacks = [
        "España, Madrid",
        "Remote research internship",
        "Experience with R, Python and SQL",
        "data   analysis",
        "Nada relevante aquí",
    ]
    terms = ["espana", "r", "data analysis", "python", "", "   ", None, "madrid"]
    for haystack in haystacks:
        normalised = normalise_words(haystack)
        for term in terms:
            assert contains_normalised_term(normalised, term) == contains_term(haystack, term)


def _profile(keywords):
    return ProfileConfig(
        name="Test",
        target_title="Data Analyst",
        keywords=KeywordConfig(critical=keywords),
    )


def _job(title, description):
    return Job(
        source=Site.FREEHIRE,
        source_id="test-1",
        url="https://example.com/jobs/1",
        title=title,
        company="Example",
        description=description,
    )


def test_scorer_does_not_award_points_for_letter_r_inside_words():
    scorer = JobScorer(_profile(["r"]))
    job = _job(
        "Intern",
        "Remote research role: prepare reports, review trends and run regression models.",
    )
    _, breakdown = scorer.score(job)
    assert breakdown["keyword"] == 0


def test_scorer_still_awards_points_for_real_r_keyword():
    scorer = JobScorer(_profile(["r"]))
    job = _job("Data Analyst", "Use R and Python for statistical analysis.")
    _, breakdown = scorer.score(job)
    assert breakdown["keyword"] > 0
