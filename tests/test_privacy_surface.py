from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_does_not_request_external_google_fonts():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "fonts.googleapis.com" not in source
    assert "fonts.gstatic.com" not in source
