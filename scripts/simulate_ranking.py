"""Reproducible synthetic evaluation of the JobScout relevance ranking.

No real CVs, personal data, network calls, or production vacancies are used.
Run with: python scripts/simulate_ranking.py
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobscout_links import professional_domain_mismatch, score_job


@dataclass(frozen=True)
class Scenario:
    name: str
    cv_text: str
    target_title: str
    relevant_title: str
    jobs: tuple[dict[str, str], ...]


SCENARIOS = (
    Scenario(
        name="Geociencias / IGME con objetivo genérico «Scientist»",
        cv_text=(
            "Head of Science at Instituto Geológico y Minero de España (IGME). "
            "Geoscientist and geologist specialising in geology, geochemistry, "
            "hydrogeology, mineral resources, geological mapping and earth sciences. "
            "Led scientific research projects, multidisciplinary teams, data analysis, "
            "scientific reporting, programme management and cross-team collaboration."
        ),
        target_title="Scientist",
        relevant_title="Senior Geoscientist",
        jobs=(
            {"title": "Oncology Research Scientist", "company": "Synthetic Biomed", "description": "Clinical oncology, cancer research, biomedical lab, clinical trials; research scientist leading scientific projects, multidisciplinary teams, data analysis, reporting and programme management."},
            {"title": "Senior Geoscientist", "company": "Synthetic Earth", "description": "Regional geological mapping, hydrogeology, mineral exploration and field surveys."},
            {"title": "Data Scientist", "company": "Synthetic Data", "description": "Machine learning models, data pipelines and business analytics."},
            {"title": "Research Scientist", "company": "Synthetic Institute", "description": "General multidisciplinary scientific research and reporting."},
        ),
    ),
    Scenario(
        name="Economía / analítica junior",
        cv_text=(
            "Economics graduate with econometrics, statistics, quantitative analysis, "
            "business analytics, forecasting and decision science. Beginning Python and SQL."
        ),
        target_title="Data Analyst",
        relevant_title="Junior Data Analyst",
        jobs=(
            {"title": "Senior Geoscientist", "company": "Synthetic Earth", "description": "Geology, geochemistry and mineral exploration."},
            {"title": "Junior Data Analyst", "company": "Synthetic Analytics", "description": "SQL, reporting, statistics and business performance analysis."},
            {"title": "Oncology Research Scientist", "company": "Synthetic Biomed", "description": "Clinical trials, cancer biology and medical laboratory research."},
            {"title": "Lawyer", "company": "Synthetic Legal", "description": "Legal advice, contracts and litigation."},
        ),
    ),
    Scenario(
        name="Investigación clínica / oncología",
        cv_text=(
            "Clinical research scientist in oncology, cancer biology, biomedical research, "
            "clinical trials, pharmacology and patient outcomes."
        ),
        target_title="Oncology Research Scientist",
        relevant_title="Oncology Research Scientist",
        jobs=(
            {"title": "Senior Geoscientist", "company": "Synthetic Earth", "description": "Geological mapping, geochemistry and hydrogeology."},
            {"title": "Oncology Research Scientist", "company": "Synthetic Biomed", "description": "Cancer research, clinical oncology, clinical trials and biomedical science."},
            {"title": "Software Engineer", "company": "Synthetic Systems", "description": "Backend services, APIs, software delivery and cloud infrastructure."},
            {"title": "Investment Analyst", "company": "Synthetic Capital", "description": "Portfolio analysis, valuation and investment research."},
        ),
    ),
    Scenario(
        name="Ingeniería de software",
        cv_text=(
            "Software engineer specialising in backend development, Python, APIs, cloud infrastructure, "
            "testing, databases, software architecture and continuous integration."
        ),
        target_title="Software Engineer",
        relevant_title="Software Engineer",
        jobs=(
            {"title": "Senior Geoscientist", "company": "Synthetic Earth", "description": "Geology, geochemistry and mineral exploration."},
            {"title": "Oncology Research Scientist", "company": "Synthetic Biomed", "description": "Cancer research, oncology and clinical trials."},
            {"title": "Software Engineer", "company": "Synthetic Systems", "description": "Backend engineering, APIs, databases, testing and cloud services."},
            {"title": "Lawyer", "company": "Synthetic Legal", "description": "Legal advice, contracts and litigation."},
        ),
    ),
    Scenario(
        name="Ciencias medioambientales",
        cv_text=(
            "Environmental scientist with experience in environmental impact assessment, ecology, "
            "biodiversity, conservation, climate science and environmental consulting."
        ),
        target_title="Environmental Scientist",
        relevant_title="Environmental Scientist",
        jobs=(
            {"title": "Oncology Research Scientist", "company": "Synthetic Biomed", "description": "Cancer research, clinical oncology and patient outcomes."},
            {"title": "Environmental Scientist", "company": "Synthetic Environment", "description": "Environmental impact assessment, biodiversity and ecology."},
            {"title": "Software Engineer", "company": "Synthetic Systems", "description": "Backend APIs, cloud infrastructure and software testing."},
            {"title": "Lawyer", "company": "Synthetic Legal", "description": "Commercial contracts and legal representation."},
        ),
    ),
    Scenario(
        name="Derecho",
        cv_text=(
            "Lawyer and legal counsel specialising in contracts, commercial law, regulatory advice, "
            "legal research, litigation and compliance."
        ),
        target_title="Lawyer",
        relevant_title="Lawyer",
        jobs=(
            {"title": "Senior Geoscientist", "company": "Synthetic Earth", "description": "Geological mapping and geochemistry."},
            {"title": "Lawyer", "company": "Synthetic Legal", "description": "Commercial contracts, legal advice and litigation."},
            {"title": "Oncology Research Scientist", "company": "Synthetic Biomed", "description": "Cancer biology and clinical trials."},
            {"title": "Data Scientist", "company": "Synthetic Data", "description": "Machine learning, data analysis and model evaluation."},
        ),
    ),
    Scenario(
        name="Finanzas / inversión",
        cv_text=(
            "Investment analyst with investment banking, portfolio analysis, equity research, valuation, "
            "financial modelling, capital markets and investment strategy."
        ),
        target_title="Investment Analyst",
        relevant_title="Investment Analyst",
        jobs=(
            {"title": "Senior Geoscientist", "company": "Synthetic Earth", "description": "Mineral resources and hydrogeology."},
            {"title": "Investment Analyst", "company": "Synthetic Capital", "description": "Valuation, equity research, portfolio analysis and capital markets."},
            {"title": "Oncology Research Scientist", "company": "Synthetic Biomed", "description": "Oncology, clinical trials and biomedical research."},
            {"title": "Software Engineer", "company": "Synthetic Systems", "description": "Software architecture, APIs and cloud infrastructure."},
        ),
    ),
    Scenario(
        name="Cambio de carrera declarado: geólogo a analista de datos",
        cv_text=(
            "Geologist with experience in geological mapping, geochemistry, hydrogeology and earth sciences. "
            "Explicitly retraining in data analysis and statistics and seeking an entry-level Data Analyst role."
        ),
        target_title="Data Analyst",
        relevant_title="Junior Data Analyst",
        jobs=(
            {"title": "Senior Geoscientist", "company": "Synthetic Earth", "description": "Geological mapping, mineral exploration and geochemistry."},
            {"title": "Junior Data Analyst", "company": "Synthetic Analytics", "description": "Data analysis, SQL, statistics and business reporting."},
            {"title": "Oncology Research Scientist", "company": "Synthetic Biomed", "description": "Clinical oncology and biomedical research."},
            {"title": "Software Engineer", "company": "Synthetic Systems", "description": "Production backend engineering and cloud services."},
        ),
    ),
)


def _config(target_title: str) -> dict:
    terms = [target_title]
    return {
        "profile": {
            "target_title": target_title,
            "keywords": {"critical": [], "strong": [], "moderate": [], "weak": []},
            "title_signals": [],
        },
        "search": {"terms": terms},
    }


def _unadjusted_broad_scientist_score(job: dict[str, str], cv_text: str) -> int:
    """Baseline component score before the professional-domain guard.

    This comparison is intentionally limited to the generic 'Scientist' trap
    scenario. Both titles match the requested word; only the unguarded CV-token
    overlap differentiates them.
    """
    import re
    import unicodedata

    def normalize(value: str) -> str:
        value = unicodedata.normalize("NFKD", value.casefold())
        return "".join(char for char in value if not unicodedata.combining(char))

    cv_tokens = {
        token for token in re.findall(r"\b[a-z0-9+#.-]+\b", normalize(cv_text))
        if len(token) > 2
    }
    job_text = normalize(" ".join(job.get(key, "") for key in ("title", "company", "description")))
    job_tokens = {token for token in re.findall(r"\b[a-z0-9+#.-]+\b", job_text) if len(token) > 2}
    if not cv_tokens or not job_tokens:
        cv_score = 0.0
    else:
        cv_score = len(cv_tokens & job_tokens) / len(cv_tokens)
    # Current base scorer weights an exact target title at 1.0 and CV overlap
    # at 0.2 when no explicit keyword tiers are configured.
    return round(100 * (1.0 + 0.2 * cv_score) / 1.2)


def run_simulation() -> tuple[int, int, list[str]]:
    passed = 0
    total = len(SCENARIOS)
    failures: list[str] = []
    print("JobScout synthetic ranking simulation (no real CVs or network calls)")
    print("=" * 96)
    print(f"{'Scenario':55} {'Relevant position':>18} {'Top score':>10}")
    print("-" * 96)

    for scenario in SCENARIOS:
        config = _config(scenario.target_title)
        ranked = sorted(
            (
                (
                    score_job(job, config, scenario.cv_text),
                    str(job["title"]),
                    professional_domain_mismatch(job, config, scenario.cv_text),
                )
                for job in scenario.jobs
            ),
            reverse=True,
        )
        rank = next(
            (index for index, item in enumerate(ranked, start=1) if item[1] == scenario.relevant_title),
            None,
        )
        top_score = ranked[0][0]
        display_name = scenario.name[:54]
        print(f"{display_name:55} {str(rank) + '/' + str(len(ranked)):>18} {top_score:>9}/100")
        if rank == 1:
            passed += 1
        else:
            failures.append(
                f"{scenario.name}: expected '{scenario.relevant_title}' at rank 1; "
                f"ranked list={[(title, score) for score, title, _ in ranked]}"
            )

        # For the IGME case, compare the unadjusted generic-title score with
        # the guarded score to demonstrate why domain-aware ranking matters.
        if scenario.name.startswith("Geociencias / IGME"):
            oncology = next(item for item in ranked if item[1] == "Oncology Research Scientist")
            baseline = sorted(
                (
                    (_unadjusted_broad_scientist_score(job, scenario.cv_text), str(job["title"]))
                    for job in scenario.jobs
                    if "scientist" in str(job["title"]).casefold()
                    or "geoscientist" in str(job["title"]).casefold()
                ),
                reverse=True,
            )
            baseline_top = baseline[0][1] if baseline else "n/a"
            print(
                "  Unadjusted broad-title baseline: "
                + " > ".join(f"{title} ({score})" for score, title in baseline)
            )
            print(
                "  Domain-guarded result: "
                + " > ".join(f"{title} ({score})" for score, title, _ in ranked)
            )
            if baseline_top != "Oncology Research Scientist":
                failures.append(
                    f"{scenario.name}: expected the constructed generic-title trap to rank oncology first "
                    f"without the domain guard; got {baseline_top}."
                )
            if oncology[0] > 24:
                failures.append(
                    f"{scenario.name}: unrelated oncology role scored {oncology[0]} (> 24)."
                )
            if oncology[2] is None:
                failures.append(f"{scenario.name}: expected a mismatch warning for oncology.")

    print("-" * 96)
    print(f"Top-1 relevant-role accuracy on synthetic benchmark: {passed}/{total} ({passed/total:.0%})")
    print("Interpretation: synthetic regression signal only, not measured real-world recommendation accuracy.")
    if failures:
        print("\nFAILURES:")
        for failure in failures:
            print(f"- {failure}")
    else:
        print("All synthetic acceptance checks passed.")
    return passed, total, failures


if __name__ == "__main__":
    passed, total, failures = run_simulation()
    raise SystemExit(0 if passed == total and not failures else 1)
