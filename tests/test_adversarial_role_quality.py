from test_domain_ranking import _config

from jobscout_links import score_job


def test_hydrogeologist_cv_suppresses_administrative_groundwater_false_positive():
    row = {
        "title": "2nd Class Administrative Officer - Administrative Support for Groundwater Rights Review",
        "company": "Grupo Tragsa",
        "description": "Administrative support for groundwater rights review and water resource management.",
    }
    score = score_job(row, _config("Hydrogeologist"), "Hydrogeologist with aquifer assessment, hydrogeology and GIS.")
    assert score <= 14


def test_internship_search_suppresses_known_full_time_matches():
    row = {
        "title": "Business Analyst",
        "company": "Example Bank",
        "description": "Business analysis and reporting.",
        "employment_type_label": "Full-Time",
        "job_type": "full_time",
    }
    score = score_job(row, _config("Business Analyst Intern"), "Recent Economics graduate seeking an internship.")
    assert score <= 14
    row.pop("employment_type_label")
    assert score_job(row, _config("Business Analyst Intern"), "Recent Economics graduate seeking an internship.") <= 14


def test_internship_search_does_not_promote_jobs_with_unknown_employment_type():
    row = {
        "title": "Business Analyst",
        "company": "Example Bank",
        "description": "Business analysis and reporting.",
    }
    assert score_job(row, _config("Business Analyst Intern")) <= 14


def test_internship_search_keeps_a_real_internship_visible():
    row = {
        "title": "Business Analyst Intern",
        "company": "Example Bank",
        "description": "Business analysis and reporting.",
        "employment_type_label": "Internship",
        "job_type": "internship",
    }
    score = score_job(row, _config("Business Analyst Intern"), "Recent Economics graduate seeking an internship.")
    assert score >= 70


def test_mixed_senior_and_internship_targets_do_not_crash():
    row = {"title": "Business Analyst", "company": "Example", "employment_type_label": "Full-Time"}
    score = score_job(row, _config("Senior Business Analyst, Business Analyst Intern"))
    assert 0 <= score <= 100


def test_senior_head_of_data_science_is_suppressed_for_decision_science_intern():
    row = {
        "title": "Workforce Strategy Head, Enterprise Data Science & Artificial Intelligence",
        "company": "Novartis",
        "description": "Lead data science strategy and enterprise AI teams.",
    }
    score = score_job(row, _config("Decision Science Intern"), "Economics graduate and master student seeking an internship.")
    assert score <= 14


def test_mixed_internship_and_non_intern_targets_do_not_penalize_other_role():
    row = {
        "title": "Product Analyst",
        "company": "Example Product",
        "description": "Product analytics, SQL and experimentation.",
    }
    score = score_job(row, _config("Business Analyst Intern, Product Analyst"))
    assert score >= 70
