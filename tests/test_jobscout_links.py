import sqlite3

from jobscout_links import canonicalize_row, choose_job_links, is_specific_job_url, load_jobs_from_sqlite, score_job


def test_rejects_linkedin_search_results():
    assert not is_specific_job_url("https://www.linkedin.com/jobs/search/?keywords=Data%20Analyst")


def test_accepts_specific_linkedin_vacancy():
    assert is_specific_job_url("https://www.linkedin.com/jobs/view/123456789/")


def test_rejects_root_and_generic_jobs_pages():
    assert not is_specific_job_url("https://www.linkedin.com/")
    assert not is_specific_job_url("https://www.indeed.com/jobs?q=data+analyst")


def test_keeps_source_and_application_links_separate():
    row = {
        "title": "Data Analyst",
        "company": "Example Ltd",
        "job_url": "https://www.linkedin.com/jobs/view/123456789/",
        "job_url_direct": "https://careers.example.com/jobs/data-analyst-123",
    }
    source, apply = choose_job_links(row)
    assert source == row["job_url"]
    assert apply == row["job_url_direct"]


def test_generic_url_does_not_become_vacancy_link():
    row = {
        "title": "Data Analyst",
        "company": "Example Ltd",
        "job_url": "https://www.linkedin.com/jobs/search/?keywords=Data%20Analyst",
    }
    assert choose_job_links(row) == ("", "")


def test_keyword_matching_does_not_treat_r_as_a_substring():
    config = {
        "profile": {
            "target_title": "Data Analyst Intern",
            "keywords": {
                "critical": ["economics", "data analysis"],
                "weak": ["r"],
            },
        },
        "search": {"terms": ["Data Analyst Intern"]},
    }
    job = {
        "title": "Data Analyst Intern",
        "company": "Example Ltd",
        "description": "Research and reporting for a data team. Remote collaboration.",
    }
    score = score_job(job, config)
    # Exact title should score well, but the single-letter skill R must not match "research".
    assert score >= 50
    assert score < 90


def test_database_loader_uses_jobs_table_and_normalizes_columns(tmp_path):
    db_path = tmp_path / "jobs.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE audit (message TEXT)")
        conn.execute("INSERT INTO audit VALUES ('not a vacancy')")
        conn.execute("CREATE TABLE jobs (title TEXT, company TEXT, location TEXT, job_url TEXT)")
        conn.execute(
            "INSERT INTO jobs VALUES (?, ?, ?, ?)",
            ("Data Analyst", "Example Ltd", "Madrid", "https://www.linkedin.com/jobs/view/123456789/"),
        )
    jobs, diagnostics = load_jobs_from_sqlite({"db_path": str(db_path)}, root=tmp_path)
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Data Analyst"
    assert jobs[0]["company"] == "Example Ltd"
    assert jobs[0]["job_url"].endswith("/123456789/")
    assert any("tabla 'jobs'" in item for item in diagnostics)
