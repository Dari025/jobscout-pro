import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_streamlit_dashboard_starts_without_user_data_or_database():
    from streamlit.testing.v1 import AppTest

    app_test = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not app_test.exception, "\n".join(
        str(exception.value) for exception in app_test.exception
    )


def test_dashboard_includes_accessibility_styles():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert ":focus-visible" in source
    assert "prefers-reduced-motion:reduce" in source
    assert "min-height:44px" in source
    assert "@media (max-width:768px)" in source
