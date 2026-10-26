import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from job_scout.job_analysis import (
    analyze_job,
    analyze_salary,
    infer_employment_type,
    infer_experience,
    infer_work_mode,
    job_matches_optional_filters,
)


def test_salary_from_structured_metadata_normalizes_month_to_eur_year():
    result = analyze_salary({
        "comp_min": 2500,
        "comp_max": 3000,
        "comp_currency": "EUR",
        "comp_interval": "monthly",
    })

    assert result["salary_eur_year_min"] == 30000
    assert result["salary_display"] == "€2,500–3,000/mes"
    assert result["salary_known"] is True


def test_salary_from_description_supports_k_format_and_requires_period():
    result = analyze_salary({
        "description": "Compensation: €30k–€42k per year, depending on experience."
    })

    assert result["salary_eur_year_min"] == 30000
    assert result["salary_currency"] == "EUR"
    assert result["salary_interval"] == "year"


def test_non_eur_salary_is_not_compared_as_eur():
    result = analyze_salary({
        "comp_min": 60000,
        "comp_max": 70000,
        "comp_currency": "USD",
        "comp_interval": "yearly",
    })

    assert result["salary_display"] == "$60,000–70,000/año"
    assert result["salary_eur_year_min"] is None


def test_unknown_salary_is_not_invented():
    result = analyze_salary({
        "title": "Junior Data Analyst",
        "description": "Salary is competitive. Please apply with your CV.",
    })

    assert result["salary_eur_year_min"] is None
    assert result["salary_known"] is False


def test_experience_inference_keeps_explicit_evidence_and_unknowns():
    intern = infer_experience({
        "title": "Data Analyst Intern",
        "description": "Great opportunity to learn."
    })
    mid = infer_experience({
        "title": "Data Analyst",
        "description": "Requires 3-5 years of relevant experience."
    })
    unknown = infer_experience({
        "title": "Business Analyst",
        "description": "Work with stakeholders and prepare reports."
    })

    assert intern["experience_level"] == "Prácticas / beca"
    assert mid["experience_min_years"] == 3
    assert mid["experience_max_years"] == 5
    assert mid["experience_level"] == "Intermedio"
    assert unknown["experience_level"] == "No indicado"


def test_contract_and_work_mode_inference():
    contract = infer_employment_type({
        "title": "Part-time Business Analyst",
        "description": "Flexible hours."
    })
    remote = infer_work_mode({
        "title": "Data Analyst",
        "description": "This is a fully remote position."
    })
    hybrid = infer_work_mode({
        "title": "Data Analyst",
        "description": "Hybrid working, three days in office."
    })

    assert contract["employment_type_label"] == "Tiempo parcial"
    assert remote["work_mode_label"] == "Remoto"
    assert hybrid["work_mode_label"] == "Híbrido"


def test_cv_comparison_is_evidence_based_and_optional():
    result = analyze_job({
        "title": "Junior Data Analyst",
        "description": "Required: SQL, Python and Power BI. Hybrid role."
    }, cv_text="Economics graduate with SQL and Python experience.", target_terms=["Data Analyst"])

    assert result["experience_level"] == "Junior / entrada"
    assert "SQL" in result["requirements"]
    assert "Python" in result["requirements"]
    assert "Power BI" in result["requirements"]
    assert "SQL" in result["cv_matches"]
    assert "Python" in result["cv_matches"]
    assert "Power BI" in result["cv_unconfirmed"]
    assert result["work_mode_label"] == "Híbrido"
    assert result["target_title_matches"] == ["Data Analyst"]

    without_cv = analyze_job({
        "title": "Data Analyst",
        "description": "SQL and Python"
    })
    assert without_cv["cv_matches"] == []
    assert without_cv["cv_unconfirmed"] == []


def test_optional_filters_are_noops_when_disabled_and_keep_unknowns_by_default():
    job = {
        "salary_eur_year_min": None,
        "experience_level": "No indicado",
        "employment_type_label": "No indicado",
        "work_mode_label": "No indicado",
    }

    assert job_matches_optional_filters(job, {})
    assert job_matches_optional_filters(job, {
        "min_salary_eur_year": 30000,
        "experience_level": "Junior / entrada",
        "employment_type": "Prácticas / beca",
        "work_mode": "Remoto",
    })


def test_salary_and_experience_filters_apply_to_known_values_only_unless_strict():
    job = {
        "salary_eur_year_min": 28000,
        "experience_level": "Junior / entrada",
        "employment_type_label": "Tiempo parcial",
        "work_mode_label": "Remoto",
    }
    assert job_matches_optional_filters(job, {"min_salary_eur_year": 25000})
    assert not job_matches_optional_filters(job, {"min_salary_eur_year": 30000})
    assert job_matches_optional_filters(job, {"experience_level": "Junior / entrada"})
    assert not job_matches_optional_filters(job, {"experience_level": "Senior / lead"})

    unknown = {
        "salary_eur_year_min": None,
        "experience_level": "No indicado",
        "employment_type_label": "No indicado",
        "work_mode_label": "No indicado",
    }
    assert not job_matches_optional_filters(unknown, {
        "min_salary_eur_year": 25000, "include_unknown_salary": False
    })
    assert not job_matches_optional_filters(unknown, {
        "experience_level": "Junior / entrada", "include_unknown_experience": False
    })
