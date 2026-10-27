import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import job_scout.notifications as notifications
from job_scout.notifications import (
    NotificationError,
    build_top_jobs_digest,
    render_digest_text,
    render_email_html,
    send_email_digest,
    send_telegram_digest,
)


def sample_jobs():
    return [
        {
            "title": "Data Analyst",
            "company": "Example Co",
            "calculated_score": 82,
            "job_url": "https://example.com/jobs/123",
            "salary": "",
            "experience_level": "No indicado",
            "employment_type_label": "No indicado",
            "work_mode_label": "No indicado",
            "duration_band": "No indicado",
            "requirements": ["SQL", "Python"],
            "description": "Analyse business data.",
        },
        {
            "title": "Junior Product Analyst",
            "company": "Another Co",
            "calculated_score": 71,
            "job_url": "https://example.com/jobs/456",
            "salary": "€30,000–35,000/año",
            "salary_known": True,
            "salary_eur_year_min": 30000,
            "experience_level": "Junior / entrada",
            "employment_type_label": "Tiempo completo",
            "work_mode_label": "Híbrido",
            "duration_band": "Indefinido / largo plazo",
            "description": "SQL and stakeholder management.",
        },
    ]


def test_build_top_digest_sorts_caps_and_reports_unknowns_as_checks():
    jobs = sample_jobs() + [
        {"title": f"Job {i}", "company": "Company", "calculated_score": i}
        for i in range(20)
    ]
    digest = build_top_jobs_digest(jobs)
    assert len(digest) == 10
    assert digest[0]["title"] == "Data Analyst"
    assert digest[0]["score"] == 82
    assert any("Salario no indicado" in item for item in digest[0]["cons"])
    assert any("Experiencia requerida" in item for item in digest[0]["cons"])
    assert digest[0]["job_url"] == "https://example.com/jobs/123"


def test_rendered_digest_has_pros_cons_and_no_cv_text():
    entry = build_top_jobs_digest(sample_jobs())[0]
    text = render_digest_text([entry])
    assert "A favor:" in text
    assert "A revisar:" in text
    assert "Abrir anuncio" not in text
    assert "SQL" in text


def test_email_html_escapes_untrusted_job_text():
    entry = build_top_jobs_digest([{
        "title": "<script>alert(1)</script>",
        "company": "Example",
        "calculated_score": 60,
        "job_url": "https://example.com/job",
    }])[0]
    html = render_email_html([entry])
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_telegram_requires_destination():
    try:
        send_telegram_digest(build_top_jobs_digest(sample_jobs()), "", "")
    except NotificationError as exc:
        assert "configurar" in str(exc)
    else:
        raise AssertionError("expected missing Telegram configuration to fail")


def test_telegram_sends_chunks_and_does_not_leak_token(monkeypatch):
    calls = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": True}

    def fake_post(url, json, timeout):
        calls.append((url, json, timeout))
        return Response()

    monkeypatch.setattr(notifications.requests, "post", fake_post)
    token = "fake-test-token"
    count = send_telegram_digest(
        build_top_jobs_digest(sample_jobs()),
        token,
        "123456",
    )
    assert count >= 1
    assert all("/botfake-test-token/" in item[0] for item in calls)
    assert all(len(item[1]["text"]) <= notifications.TELEGRAM_MESSAGE_LIMIT for item in calls)


def test_email_requires_all_credentials():
    try:
        send_email_digest(
            build_top_jobs_digest(sample_jobs()),
            smtp_host="",
            smtp_port=587,
            smtp_username="",
            smtp_password="",
            sender="",
            recipient="person@example.com",
        )
    except NotificationError as exc:
        assert "SMTP" in str(exc)
    else:
        raise AssertionError("expected missing SMTP configuration to fail")


def test_email_delivery_uses_starttls_and_sends_multipart_digest(monkeypatch):
    observed = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            observed["host"] = host
            observed["port"] = port

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def ehlo(self):
            observed["ehlo"] = observed.get("ehlo", 0) + 1

        def starttls(self, context):
            observed["tls"] = context is not None

        def login(self, username, password):
            observed["login"] = (username, password)

        def send_message(self, message):
            observed["message"] = message

    monkeypatch.setattr(notifications.smtplib, "SMTP", FakeSMTP)
    send_email_digest(
        build_top_jobs_digest(sample_jobs()),
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_username="sender@example.com",
        smtp_password="test-app-password",
        sender="sender@example.com",
        recipient="destination@example.com",
    )
    assert observed["host"] == "smtp.example.com"
    assert observed["tls"] is True
    assert observed["login"] == ("sender@example.com", "test-app-password")
    assert observed["message"].get_content_type() == "multipart/alternative"
    assert observed["message"]["To"] == "destination@example.com"
