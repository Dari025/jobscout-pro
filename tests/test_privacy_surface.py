from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_does_not_request_external_google_fonts():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "fonts.googleapis.com" not in source
    assert "fonts.gstatic.com" not in source


def test_optional_cv_ai_requires_a_separate_consent_and_explicit_action():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'key="ai_cv_consent_clean"' in source
    assert 'key="groq_api_key_input"' in source
    assert 'type="password"' in source
    assert "disabled=(not st.session_state.get(\"ai_cv_consent_clean\", False) or not api_key.strip())" in source
    assert "if analyze_clicked:" in source
    assert "review_cv_with_groq(" in source


def test_arbeitnow_source_has_required_attribution_link():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'source_name.casefold() == "arbeitnow"' in source
    assert "https://www.arbeitnow.com/" in source
