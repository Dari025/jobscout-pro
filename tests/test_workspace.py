import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from job_scout.workspace import build_workspace_config, parse_target_terms, write_workspace_config


def test_empty_user_query_does_not_inherit_template_search_terms(tmp_path):
    template = {
        "profile": {
            "name": "Previous Person",
            "target_title": "Data Science / Decision Science",
            "resume_text": "private old CV text",
            "keywords": {"critical": ["economics"], "strong": ["python"]},
            "title_signals": [{"pattern": "Data Science", "points": 10}],
            "target_companies": {"tier1": ["Old Company"]},
        },
        "search": {
            "terms": ["Data Science Intern", "Junior Data Analyst"],
            "locations": ["Madrid, Spain", "Remote, Europe"],
            "sites": ["freehire", "arbeitnow"],
        },
    }

    config = build_workspace_config(template, tmp_path / "session-one", "", [])

    assert config["profile"]["name"] == ""
    assert config["profile"]["target_title"] == ""
    assert config["profile"]["resume_text"] == ""
    assert config["profile"]["keywords"] == {
        "critical": [], "strong": [], "moderate": [], "weak": []
    }
    assert config["profile"]["title_signals"] == []
    assert config["search"]["terms"] == []
    assert config["search"]["locations"] == []
    assert config["db_path"] == str((tmp_path / "session-one" / "jobs.sqlite").resolve())
    # Building the user's config never mutates the shared neutral template.
    assert template["search"]["terms"] == ["Data Science Intern", "Junior Data Analyst"]


def test_workspace_uses_only_current_users_titles_and_locations(tmp_path):
    template = {
        "profile": {"name": "", "target_title": "Old Role", "resume_text": ""},
        "search": {
            "terms": ["Data Science Intern"],
            "locations": ["Remote, Europe"],
            "sites": ["freehire", "arbeitnow"],
        },
    }

    config = build_workspace_config(
        template,
        tmp_path / "session-two",
        "Product Analyst, Economics Analyst / Risk Analyst",
        ["Madrid, Spain", "Remote, Europe", "Fake Region"],
    )

    assert config["search"]["terms"] == [
        "Product Analyst", "Economics Analyst", "Risk Analyst"
    ]
    assert config["search"]["locations"] == ["Madrid, Spain", "Remote, Europe"]
    assert config["profile"]["target_title"] == "Product Analyst, Economics Analyst / Risk Analyst"
    assert config["search"]["sites"] == ["freehire", "arbeitnow"]


def test_separate_sessions_get_distinct_database_paths_and_no_cv_is_written(tmp_path):
    template = {
        "profile": {
            "name": "Example",
            "target_title": "Data Analyst",
            "resume_text": "sensitive CV text must not be written",
            "keywords": {"critical": ["statistics"]},
        },
        "search": {"terms": ["Data Science"], "locations": ["Madrid, Spain"], "sites": ["freehire"]},
    }

    path_a = write_workspace_config(
        template, tmp_path / "session-a", "Data Analyst", ["Madrid, Spain"]
    )
    path_b = write_workspace_config(
        template, tmp_path / "session-b", "Business Analyst", ["Remote, Europe"]
    )

    assert path_a != path_b
    assert path_a.exists() and path_b.exists()
    config_a_text = path_a.read_text(encoding="utf-8")
    assert "sensitive CV text must not be written" not in config_a_text

    import yaml

    config_a = yaml.safe_load(config_a_text)
    config_b = yaml.safe_load(path_b.read_text(encoding="utf-8"))
    assert config_a["db_path"] != config_b["db_path"]
    assert config_a["search"]["terms"] == ["Data Analyst"]
    assert config_b["search"]["terms"] == ["Business Analyst"]
    assert config_a["search"]["locations"] == ["Madrid, Spain"]
    assert config_b["search"]["locations"] == ["Remote, Europe"]


def test_parse_target_terms_only_returns_explicit_nonempty_terms():
    assert parse_target_terms("") == []
    assert parse_target_terms("  ") == []
    assert parse_target_terms("Data Analyst, Product Analyst / Risk Analyst") == [
        "Data Analyst", "Product Analyst", "Risk Analyst"
    ]


def test_stale_workspace_cleanup_removes_only_expired_uuid_directories(tmp_path):
    import os
    import time

    from job_scout.workspace import (
        cleanup_stale_session_workspaces,
        touch_session_workspace,
    )

    root = tmp_path / "jobscout-pro-sessions"
    current = root / ("a" * 32)
    stale = root / ("b" * 32)
    unrelated = root / "keep-me"
    touch_session_workspace(root, current)
    touch_session_workspace(root, stale)
    unrelated.mkdir(parents=True)

    old_time = time.time() - 48 * 3600
    os.utime(stale / ".last_seen", (old_time, old_time))

    removed = cleanup_stale_session_workspaces(
        root, current, ttl_hours=24, now=time.time()
    )

    assert removed == 1
    assert current.exists()
    assert not stale.exists()
    assert unrelated.exists()


def test_cleanup_preserves_current_workspace_even_if_old(tmp_path):
    import os
    import time

    from job_scout.workspace import cleanup_stale_session_workspaces, touch_session_workspace

    root = tmp_path / "sessions"
    current = root / ("c" * 32)
    touch_session_workspace(root, current)
    old_time = time.time() - 72 * 3600
    os.utime(current / ".last_seen", (old_time, old_time))

    assert cleanup_stale_session_workspaces(root, current, ttl_hours=24) == 0
    assert current.exists()
