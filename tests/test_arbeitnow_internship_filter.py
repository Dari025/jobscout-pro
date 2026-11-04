from job_scout.scrapers.arbeitnow import _matches_term


def test_internship_query_rejects_full_time_data_analyst():
    row = {"title": "Data Analyst", "job_types": ["Full-Time"], "tags": ["Data", "Analytics"]}
    assert not _matches_term(row, "Data Analyst Intern")


def test_internship_query_accepts_explicit_intern_title_or_type():
    assert _matches_term(
        {"title": "Data Analyst Intern", "job_types": ["Full-Time"]},
        "Data Analyst Intern",
    )
    assert _matches_term(
        {"title": "Data Analyst", "job_types": ["Internship"]},
        "Data Analyst Intern",
    )


def test_non_internship_search_keeps_normal_full_time_roles():
    assert _matches_term(
        {"title": "Data Analyst", "job_types": ["Full-Time"]},
        "Data Analyst",
    )
