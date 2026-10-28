from __future__ import annotations

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from job_scout.role_terms import search_query_variants
from jobscout_links import score_job


def _config(target_title: str) -> dict:
    return {
        "profile": {
            "target_title": target_title,
            "keywords": {"critical": [], "strong": [], "moderate": [], "weak": []},
            "title_signals": [],
        },
        "search": {"terms": [target_title]},
    }


def _internship_job() -> dict:
    return {
        "title": "Geology Intern",
        "company": "Earth Sciences Ltd",
        "description": "Geology and hydrogeology internship for students.",
        "experience_level": "Prácticas / beca",
        "employment_type_label": "Prácticas / beca",
        "job_type": ["internship"],
    }


def test_senior_search_keeps_exact_query_and_adds_unqualified_role():
    assert search_query_variants("Senior Hydrogeologist") == [
        "Senior Hydrogeologist",
        "Hydrogeologist",
    ]
    assert search_query_variants("Lead Data Analyst") == [
        "Lead Data Analyst",
        "Data Analyst",
    ]


def test_regular_queries_are_not_broadened():
    assert search_query_variants("Data Analyst") == ["Data Analyst"]
    assert search_query_variants("Geologist") == ["Geologist"]


def test_senior_target_caps_internship_relevance():
    senior_job = {
        "title": "Senior Geologist",
        "company": "Earth Sciences Ltd",
        "description": "Geology, hydrogeology and mineral resources.",
        "experience_level": "Senior / lead",
        "experience_min_years": 8,
        "employment_type_label": "Tiempo completo",
        "job_type": ["full_time"],
    }
    target = _config("Senior Geologist")

    senior_score = score_job(senior_job, target)
    internship_score = score_job(_internship_job(), target)

    assert senior_score > internship_score
    assert internship_score <= 15


def test_clear_senior_cv_also_deprioritizes_internships():
    target = _config("Geologist")
    cv_text = (
        "Senior Geologist with 12 years of experience in geology and hydrogeology."
    )

    assert score_job(_internship_job(), target, cv_text) <= 15


def test_general_search_does_not_automatically_penalize_internships():
    # Keep current behavior for users who have not specified seniority.
    score = score_job(_internship_job(), _config("Geologist"))
    assert score > 15
