import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from job_scout.runtime_env import build_scraper_subprocess_env


def test_scraper_env_does_not_forward_api_or_messaging_secrets(tmp_path):
    parent = {
        "PATH": "/usr/bin",
        "HOME": "/home/example",
        "GEMINI_API_KEY": "do-not-forward",
        "OPENAI_API_KEY": "do-not-forward",
        "TELEGRAM_BOT_TOKEN": "do-not-forward",
        "TELEGRAM_CHAT_ID": "123456",
        "SMTP_PASSWORD": "do-not-forward",
        "DATABASE_URL": "postgres://user:password@example/db",
        "JOBSCOUT_DB_PATH": "/other/users/jobs.sqlite",
        "JOBSCOUT_CONFIG": "/other/users/config.yaml",
        "PYTHONPATH": "/untrusted/path",
        "HTTP_PROXY": "http://proxy-with-secret@example:8080",
    }

    env = build_scraper_subprocess_env(parent, "Data Analyst", tmp_path / "src")

    assert env["PATH"] == "/usr/bin"
    assert env["HOME"] == "/home/example"
    assert env["JOBSCOUT_TARGET_TITLE"] == "Data Analyst"
    assert env["PYTHONUNBUFFERED"] == "1"
    assert env["PYTHONPATH"] == str((tmp_path / "src").resolve())
    for key in (
        "GEMINI_API_KEY", "OPENAI_API_KEY", "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID", "SMTP_PASSWORD", "DATABASE_URL",
        "JOBSCOUT_DB_PATH", "JOBSCOUT_CONFIG", "HTTP_PROXY",
    ):
        assert key not in env


def test_empty_title_is_passed_as_empty_not_an_inherited_default(tmp_path):
    env = build_scraper_subprocess_env(
        {"PATH": "/usr/bin", "JOBSCOUT_TARGET_TITLE": "Old User's Search"},
        "",
        tmp_path / "src",
    )
    assert env["JOBSCOUT_TARGET_TITLE"] == ""
