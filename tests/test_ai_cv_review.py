from __future__ import annotations

import json
from unittest.mock import Mock, patch

import pytest

from job_scout.ai_cv_review import (
    DEFAULT_MODEL,
    MAX_CV_CHARS_FOR_AI,
    CVReviewError,
    redact_cv_contact_details,
    review_cv_with_groq,
    validate_review_payload,
)


def test_redacts_email_url_and_phone():
    value, counts = redact_cv_contact_details(
        "Ada Lovelace | ada@example.com | +34 600 123 456 | https://linkedin.com/in/ada"
    )
    assert "ada@example.com" not in value
    assert "600 123 456" not in value
    assert "https://linkedin.com" not in value
    assert counts == {"emails": 1, "phones": 1, "urls": 1}


def test_review_requires_text_and_key_without_network():
    with pytest.raises(CVReviewError, match="CV"):
        review_cv_with_groq("", "key")
    with pytest.raises(CVReviewError, match="clave"):
        review_cv_with_groq("CV con experiencia", "")


def test_validate_payload_bounds_scores_and_lists():
    result = validate_review_payload({
        "overall_score": 130,
        "summary": " x " * 1000,
        "strengths": [f"p{i}" for i in range(20)],
        "sections": [{"name": "Claridad", "score": -10, "finding": "Bien"}],
        "skills_detected": [{"skill": "Python", "evidence": "Proyecto académico"}],
    })
    assert result["overall_score"] == 100
    assert len(result["summary"]) <= 900
    assert len(result["strengths"]) == 8
    assert result["sections"][0]["score"] == 0
    assert result["skills_detected"][0]["skill"] == "Python"


def test_rejects_non_object_model_output():
    with pytest.raises(CVReviewError, match="formato"):
        validate_review_payload(["not", "json object"])


def test_calls_groq_with_redacted_text_and_json_mode():
    payload = {
        "overall_score": 82,
        "summary": "CV claro y bien enfocado.",
        "sections": [{"name": "Experiencia", "score": 80, "finding": "Incluye ejemplos."}],
        "strengths": ["Formación relevante"],
        "improvements": ["Cuantificar resultados"],
        "missing_evidence": [],
        "ats_issues": [],
        "role_families": ["Data Analyst"],
        "skills_detected": [{"skill": "SQL", "evidence": "Proyecto", "confidence": "Alta"}],
        "warnings": [],
    }
    response = Mock(status_code=200)
    response.json.return_value = {"choices": [{"message": {"content": json.dumps(payload)}}]}
    with patch("job_scout.ai_cv_review.httpx.post", return_value=response) as request:
        result = review_cv_with_groq(
            "Jane Doe\njane@example.com\n+34 600 123 456\nEconomist with SQL",
            "gsk_test_key",
        )

    request.assert_called_once()
    sent = request.call_args.kwargs["json"]
    prompt = sent["messages"][1]["content"]
    assert "jane@example.com" not in prompt
    assert "600 123 456" not in prompt
    assert sent["model"] == DEFAULT_MODEL
    assert sent["response_format"] == {"type": "json_object"}
    assert result["overall_score"] == 82
    assert result["redactions"]["emails"] == 1


@pytest.mark.parametrize(
    ("status", "message"),
    [
        (401, "clave"),
        (429, "límite gratuito"),
        (500, "temporal"),
    ],
)
def test_groq_http_errors_are_safe(status, message):
    response = Mock(status_code=status)
    with patch("job_scout.ai_cv_review.httpx.post", return_value=response), pytest.raises(CVReviewError, match=message):
        review_cv_with_groq("CV con texto", "gsk_test_key")


def test_cv_text_is_truncated_before_external_transmission():
    response = Mock(status_code=200)
    response.json.return_value = {"choices": [{"message": {"content": '{"overall_score": 50}'}}]}
    long_text = "A" * (MAX_CV_CHARS_FOR_AI + 100)
    with patch("job_scout.ai_cv_review.httpx.post", return_value=response) as request:
        result = review_cv_with_groq(long_text, "gsk_test_key")
    prompt = request.call_args.kwargs["json"]["messages"][1]["content"]
    sent_text = prompt.split("<CV_NO_CONFIABLE>", 1)[1].split("</CV_NO_CONFIABLE>", 1)[0].strip()
    assert len(sent_text) == MAX_CV_CHARS_FOR_AI
    assert result["characters_reviewed"] == MAX_CV_CHARS_FOR_AI
