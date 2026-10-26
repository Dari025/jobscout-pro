from jobscout_links import professional_domain_mismatch, score_job


def _config(target_title=""):
    terms = [part.strip() for part in target_title.split(",") if part.strip()]
    return {
        "profile": {
            "target_title": target_title,
            "keywords": {"critical": [], "strong": [], "moderate": [], "weak": []},
            "title_signals": [],
        },
        "search": {"terms": terms},
    }


IGME_CV = """
Head of Science at Instituto Geológico y Minero de España (IGME).
Geoscientist and geologist specialising in geology, geochemistry,
hydrogeology, mineral resources, geological mapping and earth sciences.
Led scientific research projects and multidisciplinary teams.
"""

ONCOLOGY_JOB = {
    "title": "Oncology Research Scientist",
    "company": "Example Biomed",
    "description": (
        "Clinical oncology research, cancer biology, clinical trials, "
        "patient outcomes and biomedical laboratory studies."
    ),
}

GEOSCIENCE_JOB = {
    "title": "Senior Geoscientist — Mineral Resources",
    "company": "Example Earth Sciences",
    "description": (
        "Geological mapping, geochemistry, hydrogeology, mineral exploration "
        "and earth sciences research."
    ),
}


def test_igme_cv_is_flagged_for_unrelated_oncology_role():
    mismatch = professional_domain_mismatch(ONCOLOGY_JOB, _config(), IGME_CV)
    assert mismatch is not None
    assert mismatch["cv_domain"] == "Geociencias"
    assert mismatch["job_domain"] == "Salud / biomedicina"


def test_igme_cv_is_not_flagged_for_geoscience_role():
    assert professional_domain_mismatch(GEOSCIENCE_JOB, _config(), IGME_CV) is None


def test_igme_cv_score_for_oncology_is_capped():
    score = score_job(ONCOLOGY_JOB, _config(), IGME_CV)
    assert score <= 24


def test_igme_cv_ranks_geoscience_above_oncology():
    good = score_job(GEOSCIENCE_JOB, _config(), IGME_CV)
    bad = score_job(ONCOLOGY_JOB, _config(), IGME_CV)
    assert good > bad


def test_explicit_career_change_target_can_override_domain_warning():
    config = _config("Oncology Research Scientist")
    assert professional_domain_mismatch(ONCOLOGY_JOB, config, IGME_CV) is None


def test_generic_scientist_word_does_not_create_domain_mismatch():
    generic_job = {
        "title": "Research Scientist",
        "company": "Example Institute",
        "description": "Scientific research and reporting across multidisciplinary teams.",
    }
    assert professional_domain_mismatch(generic_job, _config(), IGME_CV) is None


def test_compound_geoscientist_title_matches_generic_scientist_target():
    config = _config("Scientist")
    job = {
        "title": "Geoscientist",
        "company": "Example Earth Sciences",
        "description": "Geoscience and geological research.",
    }
    assert score_job(job, config) == 100


def test_one_explicit_target_among_multiple_roles_overrides_domain_warning():
    config = _config("Senior Geoscientist, Oncology Research Scientist")
    assert professional_domain_mismatch(ONCOLOGY_JOB, config, IGME_CV) is None
