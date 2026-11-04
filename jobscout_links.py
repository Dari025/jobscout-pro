"""Safe job-link handling and deterministic SQLite discovery for JobScout.

A syntactically valid URL is not proof that the page belongs to the advertised job.
This module rejects known search/listing URLs so the UI never presents them as a
direct vacancy link, and keeps source links separate from application links.
"""
from __future__ import annotations

import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, parse_qsl, unquote, urlencode, urlparse, urlunsplit

_SRC_DIR = Path(__file__).resolve().parent / "src"
if _SRC_DIR.is_dir() and str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from job_scout.matching import (
    contains_normalised_term as _contains_norm_term,
)
from job_scout.matching import (
    normalise_words as _normalise_words,
)
from job_scout.role_terms import role_search_variants


def _text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"", "none", "nan", "null", "#", "n/a", "na"} else text


def _norm_column(name: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


ALIASES = {
    "title": ("title", "jobtitle", "position", "jobname", "puesto", "nombre", "vacancytitle"),
    "company": ("company", "companyname", "employer", "empresa", "organisation", "organization"),
    "location": ("location", "joblocation", "ubicacion", "city", "workplace"),
    "description": ("description", "jobdescription", "summary", "descripcion", "details"),
    "job_url": ("joburl", "url", "link", "sourceurl", "postingurl", "originalurl", "joburloriginal"),
    "job_url_direct": ("joburldirect", "applyurl", "applicationurl", "directurl", "urlapply"),
    "source": ("site", "source", "jobboard", "jobsite", "portal"),
    "date_posted": ("dateposted", "postedat", "posteddate", "date", "publicationdate"),
    "salary": ("salary", "salarysource", "compensation", "pay"),
    "id": ("id", "jobid", "externalid", "sourceid"),
}

SOURCE_URL_KEYS = ("job_url", "source_url", "posting_url", "original_url", "url", "link")
APPLY_URL_KEYS = ("job_url_direct", "apply_url", "application_url", "direct_url")


def is_specific_job_url(value: Any) -> bool:
    """Return True only for an absolute HTTP(S) URL that doesn't look like a search page."""
    raw = _text(value)
    if not raw or any(ch.isspace() for ch in raw):
        return False
    try:
        parsed = urlparse(raw)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return False
        if parsed.username or parsed.password:
            return False
        host = parsed.hostname.lower().rstrip(".")
        if host in {"localhost", "127.0.0.1", "::1"} or "." not in host:
            return False
        path = unquote(parsed.path or "/").lower()
        query = {k.lower(): v for k, v in parse_qs(parsed.query, keep_blank_values=False).items()}
    except (ValueError, TypeError):
        return False

    # Known redirects/search endpoints can look like job links but take users to a search.
    if host == "google.com" or host.endswith(".google.com") or host == "bing.com" or host.endswith(".bing.com"):
        if path == "/search" or path.startswith("/search/"):
            return False
    # Workday's canonical posting URL contains /search/job/{location}/{slug};
    # that is a concrete vacancy, unlike a generic /jobs/search listing page.
    workday_detail = bool(re.search(r"/search/job/[^/]+/[^/]+", path))
    if not workday_detail and re.search(r"/(jobs?/)?(search|job-search|search-jobs|results)(/|$)", path):
        return False
    if path in {"/", "/jobs", "/jobs/", "/job", "/job/", "/careers", "/careers/",
                "/career", "/career/", "/openings", "/job-openings", "/vacancies",
                "/vacancy", "/search", "/search/"}:
        return False

    if "linkedin.com" in host:
        if path.startswith("/jobs/search") or path.startswith("/jobs/collections"):
            return False
        if path.startswith("/jobs/") and not re.search(r"/jobs/view/[^/]+", path):
            return False
    if host.endswith("indeed.com"):
        if path.rstrip("/") in {"/jobs", "/m/jobs", "/career", "/careers"}:
            return False
        if path.rstrip("/") in {"/viewjob", "/m/viewjob"} and not query.get("jk"):
            return False
        if path.rstrip("/") == "/rc/clk" and not query.get("jk"):
            return False
    if "glassdoor." in host:
        if path in {"/job-listing", "/job-listing/", "/jobs", "/jobs/", "/jobs.htm"}:
            return False
        if path.startswith("/job/") and not re.search(r"/job/[^/]+", path):
            return False
    if "ziprecruiter.com" in host and path.rstrip("/") in {"/jobs", "/jobs/search"}:
        return False
    # Query-only searches should never masquerade as a direct vacancy link.
    if path in {"/jobs", "/job", "/careers"} and any(k in query for k in ("q", "query", "keywords", "search", "searchterm")):
        return False
    return True


def choose_job_links(row: dict[str, Any]) -> tuple[str, str]:
    """Return (source_listing_url, direct_apply_url), rejecting generic search URLs."""
    norm = {_norm_column(k): v for k, v in row.items()}
    lookup: dict[str, Any] = {}
    for canonical, aliases in ALIASES.items():
        for alias in aliases:
            if alias in norm and _text(norm[alias]):
                lookup[canonical] = norm[alias]
                break

    source = ""
    direct = ""
    for key in SOURCE_URL_KEYS:
        value = lookup.get("job_url") if key == "job_url" else norm.get(_norm_column(key))
        if is_specific_job_url(value):
            source = _text(value)
            break
    for key in APPLY_URL_KEYS:
        value = lookup.get("job_url_direct") if key == "job_url_direct" else norm.get(_norm_column(key))
        if is_specific_job_url(value):
            direct = _text(value)
            break
    if source and direct and source.rstrip("/") == direct.rstrip("/"):
        direct = ""
    return source, direct


def best_job_url(row: dict[str, Any]) -> str:
    """Return an exact-looking source page, otherwise a distinct application URL."""
    source, direct = choose_job_links(row)
    return source or direct


def canonical_job_identity(row: dict[str, Any]) -> str:
    """Build a stable cross-source identity, preferring a full posting fingerprint.

    Job aggregators often expose the same employer vacancy under different
    tracking URLs or separate mirror URLs. Title, employer, location and
    publication date provide a useful cross-source key when all are present.
    """
    job = canonicalize_row(row)
    source_url, apply_url = choose_job_links(job)
    chosen = source_url or apply_url

    text_parts = tuple(
        _normalise_words(job.get(key))
        for key in ("title", "company", "location", "date_posted")
    )
    if all(text_parts):
        return "text:" + "|".join(text_parts)

    normalized_url = ""
    if chosen:
        try:
            parsed = urlparse(chosen)
            host = (parsed.hostname or "").lower().rstrip(".").removeprefix("www.")
            query_pairs = [
                (key, value)
                for key, value in parse_qsl(parsed.query, keep_blank_values=False)
                if not key.lower().startswith("utm_")
                and key.lower() not in {"trk", "trackingid", "ref", "referrer", "campaignid"}
            ]
            query_pairs.sort()
            netloc = host
            if parsed.port and not (
                (parsed.scheme.lower() == "https" and parsed.port == 443)
                or (parsed.scheme.lower() == "http" and parsed.port == 80)
            ):
                netloc = f"{host}:{parsed.port}"
            normalized_url = urlunsplit((
                parsed.scheme.lower(),
                netloc,
                (parsed.path or "/").rstrip("/") or "/",
                urlencode(query_pairs),
                "",
            ))
        except (ValueError, TypeError):
            normalized_url = chosen

    if normalized_url:
        return f"url:{normalized_url}"
    source = _text(job.get("source")).casefold()
    job_id = _text(job.get("id"))
    if job_id:
        return f"id:{source}:{job_id}"
    return "text:" + "|".join(text_parts)


def canonicalize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Map differing scraper schemas into stable fields used by the dashboard/notifier."""
    norm = {_norm_column(k): v for k, v in row.items()}
    result: dict[str, Any] = {}
    for canonical, aliases in ALIASES.items():
        result[canonical] = ""
        for alias in aliases:
            if alias in norm and _text(norm[alias]):
                result[canonical] = norm[alias]
                break
    # The upstream SQLite schema stores structured location components, not a single display field.
    if not _text(norm.get("location")):
        location_parts = []
        for key in ("city", "state", "country"):
            value = _text(norm.get(key))
            if value and value not in location_parts:
                location_parts.append(value)
        remote_value = _text(norm.get("isremote")).lower()
        is_remote = remote_value in {"1", "true", "yes", "y", "remote"}
        result["location"] = ", ".join(location_parts) + (" (Remote)" if is_remote else "")
    elif _text(norm.get("isremote")) and _text(norm.get("isremote")).lower() in {"1", "true", "yes", "y", "remote"}:
        if "remote" not in _text(result["location"]).lower():
            result["location"] = _text(result["location"]) + " (Remote)"

    # Preserve source metadata used by the explainable job analysis. Older
    # dashboard normalization used to discard salary amounts, currencies,
    # intervals and employment-type fields stored in the upstream SQLite schema.
    metadata_aliases = {
        "comp_min": ("compmin", "minamount", "salarymin", "minimumsalary"),
        "comp_max": ("compmax", "maxamount", "salarymax", "maximumsalary"),
        "comp_currency": ("compcurrency", "salarycurrency", "currency"),
        "comp_interval": ("compinterval", "salaryinterval", "payinterval", "interval"),
        "job_type": ("jobtype", "jobtypes", "employmenttype", "employmenttypes"),
        "is_remote": ("isremote", "remote", "workremote"),
        "country": ("country", "countrycode"),
        "city": ("city",),
        "state": ("state", "region", "province"),
    }
    for target, aliases in metadata_aliases.items():
        for alias in aliases:
            if alias in norm and _text(norm[alias]):
                result[target] = norm[alias]
                break

    source_url, apply_url = choose_job_links(row)
    result["job_url"] = source_url
    result["job_url_direct"] = apply_url
    result["has_specific_link"] = bool(source_url or apply_url)
    return result


def load_config(config_path: str | Path | None = None) -> tuple[dict[str, Any], Path | None]:
    """Load a local YAML configuration without embedding credentials in code."""
    import yaml

    candidates: list[Path] = []
    if config_path:
        candidates.append(Path(config_path).expanduser())
    elif os.getenv("JOBSCOUT_CONFIG"):
        candidates.append(Path(os.environ["JOBSCOUT_CONFIG"]).expanduser())
    else:
        candidates.extend([Path("busqueda.yaml"), Path("config.yaml"), Path("busqueda.example.yaml")])
    for path in candidates:
        if path.is_file():
            try:
                with path.open("r", encoding="utf-8") as handle:
                    data = yaml.safe_load(handle) or {}
                if isinstance(data, dict):
                    return data, path.resolve()
            except (OSError, ValueError, yaml.YAMLError):
                continue
    return {}, None


def database_candidates(config: dict[str, Any] | None = None, root: Path | None = None) -> list[Path]:
    """List deterministic DB paths; avoid recursive scans that may pick an unrelated database."""
    config = config or {}
    root = (root or Path.cwd()).resolve()
    paths: list[Path] = []
    env_path = _text(os.getenv("JOBSCOUT_DB_PATH"))
    configured_path = _text(config.get("db_path"))
    if env_path:
        paths.append(Path(env_path).expanduser())
    if configured_path:
        paths.append(Path(configured_path).expanduser())
    local_appdata = _text(os.getenv("LOCALAPPDATA"))
    xdg_data = _text(os.getenv("XDG_DATA_HOME"))
    if local_appdata:
        paths.extend([Path(local_appdata) / "job_scout" / "jobs.db",
                      Path(local_appdata) / "job_scout" / "busqueda.db"])
    if xdg_data:
        paths.extend([Path(xdg_data) / "job-scout" / "jobs.db",
                      Path(xdg_data) / "job-scout" / "busqueda.db"])
    home = Path.home()
    paths.extend([
        root / "jobs.db", root / "busqueda.db", root / "data" / "jobs.db",
        root / "src" / "job_scout" / "jobs.db",
        home / ".local" / "share" / "job-scout" / "job-scout.db",
        home / ".local" / "share" / "job-scout" / "jobs.db",
        home / ".local" / "share" / "job-scout" / "busqueda.db",
        home / ".job_scout" / "job-scout.db", home / ".job_scout" / "jobs.db",
        home / "job_scout" / "job-scout.db", home / "job_scout" / "jobs.db",
    ])
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        normalized = str(path.expanduser().resolve()).casefold()
        if normalized not in seen:
            seen.add(normalized)
            unique.append(path.expanduser())
    return unique


def load_jobs_from_sqlite(config: dict[str, Any] | None = None,
                          root: Path | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    """Load vacancies, strictly isolating any explicitly configured database path.

    In a multi-user hosted app, an explicit db_path is a privacy boundary: if that
    session's DB is missing or empty, never fall back to a shared/default DB.
    """
    diagnostics: list[str] = []
    configured_path = _text((config or {}).get("db_path"))
    env_path = _text(os.getenv("JOBSCOUT_DB_PATH"))
    strict_path = configured_path or env_path
    if strict_path:
        paths_to_check = [Path(strict_path).expanduser()]
    else:
        paths_to_check = database_candidates(config, root)
    for db_path in paths_to_check:
        if not db_path.is_file():
            diagnostics.append(f"No encontrada: {db_path}")
            continue
        table_candidates: list[tuple[int, list[dict[str, Any]], str]] = []
        try:
            # Read-only URI prevents the dashboard from modifying job-scout's database.
            db_uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
            with sqlite3.connect(db_uri, uri=True, timeout=5) as connection:
                tables = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
                for (table_name,) in tables:
                    safe_table = '"' + str(table_name).replace('"', '""') + '"'
                    cursor = connection.execute(f"SELECT * FROM {safe_table}")
                    column_names = [item[0] for item in cursor.description or []]
                    raw_rows = [dict(zip(column_names, values)) for values in cursor.fetchall()]
                    normalized_rows = []
                    for row in raw_rows:
                        clean = canonicalize_row(row)
                        if _text(clean.get("title")) and _text(clean.get("company")):
                            normalized_rows.append(clean)
                    if normalized_rows:
                        # Prefer the expected jobs table; otherwise choose the valid table with most rows.
                        preference = 1_000_000 if str(table_name).casefold() in {"jobs", "job"} else 0
                        table_candidates.append((preference + len(normalized_rows), normalized_rows, str(table_name)))
            if table_candidates:
                _, rows, table = max(table_candidates, key=lambda item: item[0])
                diagnostics.append(f"Usada: {db_path} | tabla '{table}' | {len(rows)} ofertas con título y empresa")
                return rows, diagnostics
            diagnostics.append(f"Sin tabla válida de ofertas: {db_path}")
        except (sqlite3.Error, OSError, ValueError) as exc:
            diagnostics.append(f"Error leyendo {db_path}: {exc}")
    return [], diagnostics


# Domain signals are deliberately narrow: generic terms such as "scientist",
# "research", "analysis", "data" and "remote" must not identify a profession.
_DOMAIN_LABELS = {
    "geosciences": "Geociencias",
    "health_biomedical": "Salud / biomedicina",
    "life_sciences": "Ciencias de la vida",
    "economics_analytics": "Economía / analítica",
    "software_it": "Software / tecnología",
    "information_security": "Ciberseguridad / seguridad informática",
    "environmental_science": "Medioambiente",
    "finance_accounting": "Finanzas / contabilidad",
    "law": "Derecho",
    "marketing_sales": "Marketing / ventas",
    "education": "Educación / academia",
    "engineering": "Ingeniería",
    "hr_people": "Recursos humanos",
    "customer_support": "Atención al cliente",
    "operations_supply_chain": "Operaciones / cadena de suministro",
    "sales": "Ventas / desarrollo de negocio",
    "design_creative": "Diseño / creatividad",
    "hospitality": "Hostelería",
    "retail": "Comercio minorista",
    "administration": "Administración / oficina",
    "construction_trades": "Construcción / oficios",
}

_DOMAIN_SIGNALS = {
    "geosciences": (
        ("instituto geologico y minero", 5.0), ("geological survey", 4.0),
        ("igme", 5.0), ("geoscientist", 4.0), ("geologist", 3.5),
        ("geology", 3.0), ("geological", 2.0), ("geochemistry", 3.0),
        ("geochemist", 3.0), ("hydrogeology", 3.0), ("geophysics", 3.0),
        ("geophysicist", 3.0), ("mineral exploration", 2.5),
        ("mineral resources", 2.5), ("earth sciences", 2.0),
        ("earth science", 2.0), ("mining geology", 3.0),
        ("geological mapping", 2.5), ("geotecnia", 2.0),
        ("hidrogeologia", 3.0), ("geoquimica", 3.0), ("geologia", 3.0),
    ),
    "health_biomedical": (
        ("oncology", 4.0), ("oncologist", 4.0), ("oncologia", 4.0),
        ("cancer research", 4.0), ("clinical oncology", 4.0),
        ("clinical trial", 3.0), ("clinical research", 2.5),
        ("patient care", 2.0), ("hospital", 2.0), ("medical doctor", 3.0),
        ("biomedical", 2.5), ("pharmacology", 3.0),
        ("pharmaceutical", 2.0), ("nursing", 2.0), ("pathology", 2.0),
        ("radiology", 2.0), ("ensayos clinicos", 3.0),
        ("investigacion clinica", 2.5), ("atencion al paciente", 2.0),
    ),
    "life_sciences": (
        ("molecular biology", 3.0), ("cell biology", 3.0),
        ("biotechnology", 3.0), ("biochemistry", 3.0),
        ("microbiology", 3.0), ("genomics", 3.0), ("proteomics", 3.0),
        ("genetics", 2.5), ("biologist", 2.5), ("life sciences", 2.5),
        ("biologia molecular", 3.0), ("biotecnologia", 3.0),
        ("bioquimica", 3.0), ("microbiologia", 3.0),
    ),
    "economics_analytics": (
        ("economist", 3.0), ("economics", 3.0), ("econometrics", 3.0),
        ("econometric", 3.0), ("data analyst", 3.0), ("business analyst", 3.0),
        ("product analyst", 3.0), ("business intelligence", 3.0),
        ("data science", 3.0), ("data scientist", 3.0),
        ("decision science", 3.0), ("risk analyst", 3.0),
        ("quantitative analyst", 3.0), ("operations research", 3.0),
        ("economic research", 3.0), ("financial analyst", 2.5),
        ("economia", 3.0), ("econometria", 3.0), ("analitica de datos", 3.0),
    ),
    "software_it": (
        ("software engineer", 3.0), ("software developer", 3.0),
        ("frontend developer", 3.0), ("backend developer", 3.0),
        ("full stack", 3.0), ("devops", 3.0), ("cybersecurity", 3.0),
        ("cloud engineer", 3.0), ("site reliability", 3.0),
        ("computer science", 2.5), ("programmer", 2.5),
        ("ingeniero de software", 3.0), ("desarrollador de software", 3.0),
    ),
    "information_security": (
        ("information security", 3.0), ("security operations", 3.0),
        ("ict security", 3.0), ("soc analyst", 3.0),
        ("cyber security", 3.0), ("security engineer", 3.0),
        ("security analyst", 3.0), ("penetration tester", 3.0),
        ("threat intelligence", 2.5), ("seguridad informatica", 3.0),
        ("ciberseguridad", 3.0),
    ),
    "environmental_science": (
        ("environmental scientist", 3.0), ("environmental science", 3.0),
        ("environmental impact", 2.5), ("environmental consultant", 3.0),
        ("ecologist", 3.0), ("ecology", 2.5), ("biodiversity", 2.5),
        ("conservation biology", 3.0), ("climate science", 2.5),
        ("environmental assessment", 2.5), ("medio ambiente", 2.5),
        ("impacto ambiental", 2.5), ("ecologia", 2.5), ("biodiversidad", 2.5),
    ),
    "finance_accounting": (
        ("investment banking", 3.0), ("investment analyst", 3.0),
        ("equity research", 3.0), ("portfolio manager", 3.0),
        ("accountant", 2.5), ("accounting", 2.5), ("controller", 2.5),
        ("actuary", 3.0), ("treasury analyst", 3.0),
        ("contable", 2.5), ("contabilidad", 2.5),
    ),
    "law": (
        ("legal counsel", 3.0), ("lawyer", 3.0), ("attorney", 3.0),
        ("solicitor", 3.0), ("barrister", 3.0), ("paralegal", 2.5),
        ("abogado", 3.0), ("asesor juridico", 3.0),
    ),
    "marketing_sales": (
        ("marketing manager", 3.0), ("growth marketing", 3.0),
        ("brand marketing", 3.0), ("sales representative", 3.0),
        ("account executive", 3.0), ("business development", 2.5),
        ("talent acquisition", 2.5), ("seo specialist", 2.5),
        ("director comercial", 3.0), ("marketing digital", 3.0),
    ),
    "education": (
        ("school teacher", 3.0), ("university lecturer", 3.0),
        ("professor of", 2.5), ("teacher", 2.0), ("lecturer", 2.5),
        ("academic faculty", 2.5), ("profesor", 2.0), ("docente", 2.0),
    ),
    "engineering": (
        ("mechanical engineer", 3.0), ("electrical engineer", 3.0),
        ("civil engineer", 3.0), ("chemical engineer", 3.0),
        ("industrial engineer", 3.0), ("process engineer", 3.0),
        ("manufacturing engineer", 3.0), ("quality engineer", 2.5),
        ("ingeniero industrial", 3.0), ("ingeniero mecanico", 3.0),
        ("ingeniero civil", 3.0), ("ingeniero electrico", 3.0),
    ),
    "hr_people": (
        ("human resources", 3.0), ("hr generalist", 3.0),
        ("hr business partner", 3.0), ("people operations", 3.0),
        ("talent acquisition", 3.0), ("recruitment specialist", 2.5),
        ("recruiter", 2.5), ("payroll specialist", 2.5),
        ("recursos humanos", 3.0), ("seleccion de personal", 3.0),
    ),
    "customer_support": (
        ("customer support", 3.0), ("customer service", 3.0),
        ("customer care", 3.0), ("technical support", 3.0),
        ("help desk", 2.5), ("helpdesk", 2.5), ("service desk", 2.5),
        ("customer success", 2.5), ("atencion al cliente", 3.0),
        ("servicio al cliente", 3.0), ("soporte tecnico", 3.0),
    ),
    "operations_supply_chain": (
        ("supply chain", 3.0), ("logistics", 2.5),
        ("procurement", 3.0), ("demand planner", 3.0),
        ("inventory planning", 3.0), ("warehouse supervisor", 2.5),
        ("operations research", 2.5), ("cadena de suministro", 3.0),
        ("compras", 2.5), ("logistica", 2.5),
    ),
    "sales": (
        ("sales development", 3.0), ("sales representative", 3.0),
        ("account executive", 3.0), ("account manager", 2.5),
        ("business development", 3.0), ("inside sales", 3.0),
        ("field sales", 2.5), ("commercial manager", 2.5),
        ("ventas", 2.5), ("desarrollo de negocio", 3.0),
    ),
    "design_creative": (
        ("ux designer", 3.0), ("ui designer", 3.0),
        ("product designer", 3.0), ("graphic designer", 3.0),
        ("visual designer", 2.5), ("interaction designer", 3.0),
        ("service designer", 2.5), ("disenador grafico", 3.0),
    ),
    "hospitality": (
        ("hotel manager", 3.0), ("front desk", 2.5),
        ("receptionist", 2.5), ("restaurant manager", 3.0),
        ("head chef", 3.0), ("chef de cuisine", 3.0),
        ("waiter", 2.5), ("bartender", 2.5), ("barista", 2.5),
        ("housekeeping", 2.5), ("hosteleria", 3.0),
    ),
    "retail": (
        ("retail manager", 3.0), ("store manager", 3.0),
        ("store supervisor", 2.5), ("retail sales", 3.0),
        ("sales associate", 2.5), ("shop assistant", 2.5),
        ("cashier", 2.5), ("merchandising", 2.5),
        ("stock replenishment", 2.5), ("dependiente", 2.5),
        ("comercio minorista", 3.0),
    ),
    "administration": (
        ("administrative assistant", 3.0), ("office manager", 3.0),
        ("executive assistant", 3.0), ("office administrator", 2.5),
        ("administrative officer", 2.5), ("asistente administrativo", 3.0),
        ("administrativo", 2.5),
    ),
    "construction_trades": (
        ("electrician", 3.0), ("plumber", 3.0), ("welder", 3.0),
        ("hvac technician", 3.0), ("maintenance technician", 2.5),
        ("construction manager", 2.5), ("site manager", 2.5),
        ("carpenter", 2.5), ("electricista", 3.0),
        ("fontanero", 3.0), ("soldador", 3.0),
    ),
}


def _domain_scores(value: Any) -> dict[str, float]:
    """Score distinctive professional-domain signals in text, not generic vocabulary."""
    text = _normalise_words(value)
    return {
        family: sum(weight for term, weight in signals if _contains_norm_term(text, term))
        for family, signals in _DOMAIN_SIGNALS.items()
    }


def _select_primary_domain(scores: dict[str, float], minimum: float = 2.0) -> str | None:
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    if not ranked or ranked[0][1] < minimum:
        return None
    # If two domains are similarly represented (e.g. environmental geoscience),
    # stay conservative rather than applying a potentially incorrect penalty.
    if len(ranked) > 1 and ranked[1][1] >= ranked[0][1] * 0.82:
        return None
    return ranked[0][0]


def _primary_cv_domain(cv_text: str) -> str | None:
    return _select_primary_domain(_domain_scores(cv_text), minimum=2.0)


def _primary_job_domain(title: str, description: str) -> str | None:
    title_scores = _domain_scores(title)
    description_scores = _domain_scores(description)
    combined = {
        family: title_scores.get(family, 0.0) * 3.0 + description_scores.get(family, 0.0)
        for family in _DOMAIN_SIGNALS
    }
    return _select_primary_domain(combined, minimum=4.0)


def _explicit_target_domains(config: dict[str, Any]) -> set[str]:
    """Return every distinct domain explicitly requested by the user.

    A user may intentionally target several fields during a career transition;
    do not collapse those preferences to a single dominant domain.
    """
    profile = config.get("profile", {}) if isinstance(config.get("profile", {}), dict) else {}
    search = config.get("search", {}) if isinstance(config.get("search", {}), dict) else {}
    phrases: list[str] = []
    target = _text(profile.get("target_title"))
    if target:
        # The app accepts multiple titles separated by commas, slashes, or semicolons.
        phrases.extend(
            part.strip() for part in re.split(r"[/,;|\\n]+", target) if part.strip()
        )
    terms = search.get("terms", [])
    if isinstance(terms, list):
        phrases.extend(_text(item) for item in terms if _text(item))
    signals = profile.get("title_signals", [])
    if isinstance(signals, list):
        phrases.extend(
            _text(item.get("pattern")) for item in signals
            if isinstance(item, dict) and _text(item.get("pattern"))
        )
    domains: set[str] = set()
    for phrase in phrases:
        domain = _select_primary_domain(_domain_scores(phrase), minimum=2.0)
        if domain:
            domains.add(domain)
    return domains


def professional_domain_mismatch(
    row: dict[str, Any],
    config: dict[str, Any] | None = None,
    cv_text: str = "",
) -> dict[str, str] | None:
    """Return a warning when a CV and vacancy clearly belong to different domains.

    An explicit target in that vacancy's domain overrides the warning, so a
    deliberate career change is not automatically penalized.
    """
    config = config or {}
    profile = config.get("profile", {}) if isinstance(config.get("profile", {}), dict) else {}
    cv = cv_text or _text(profile.get("resume_text", ""))
    if not cv.strip():
        return None

    job = canonicalize_row(row)
    cv_domain = _primary_cv_domain(cv)
    job_domain = _primary_job_domain(
        _text(job.get("title")), _text(job.get("description"))
    )
    if not cv_domain or not job_domain or cv_domain == job_domain:
        return None

    if job_domain in _explicit_target_domains(config):
        return None

    return {
        "cv_domain": _DOMAIN_LABELS.get(cv_domain, cv_domain),
        "job_domain": _DOMAIN_LABELS.get(job_domain, job_domain),
        "reason": (
            f"El CV presenta señales de { _DOMAIN_LABELS.get(cv_domain, cv_domain) }, "
            f"pero la oferta parece centrarse en { _DOMAIN_LABELS.get(job_domain, job_domain) }."
        ),
    }


def _title_phrase_matches(title: str, phrase: str) -> bool:
    """Match whole phrases/words, allowing the compound 'geoscientist' for 'scientist'.

    ``title`` must already be normalised (see ``score_job``).
    """
    if _contains_norm_term(title, phrase):
        return True
    # "Scientist" is commonly compounded in legitimate job titles (e.g. geoscientist).
    if phrase in {"scientist", "scientists"}:
        return re.search(r"(?<!\w)[a-z-]*scientists?(?!\w)", title) is not None
    return False



def _role_alias_title_score(title: str, target_titles: list[str]) -> float:
    """Give related job titles a strong, but sub-exact, relevance score."""
    best = 0.0
    for target_phrase in target_titles:
        variants = role_search_variants(target_phrase)
        for alias in variants[1:]:
            normalized_alias = _normalise_words(alias)
            if not normalized_alias:
                continue
            if _contains_norm_term(title, normalized_alias) or _title_phrase_matches(title, normalized_alias):
                best = max(best, 0.80)
                break
    return best


def _matches_target_role(title: str, target_phrase: str) -> bool:
    """Match a real role phrase/alias, not just one generic shared word."""
    normalized = _normalise_words(target_phrase)
    role = _INTERNSHIP_SIGNAL_RE.sub(" ", normalized)
    role = " ".join(role.split())
    tokens = [token for token in role.split() if len(token) > 2]
    if not tokens:
        return False
    if _contains_norm_term(title, role) or _title_phrase_matches(title, role):
        return True
    if _role_alias_title_score(title, [role]) >= 0.80:
        return True
    return all(_contains_norm_term(title, token) for token in tokens)


_SENIORITY_SIGNAL_RE = re.compile(
    r"(?<!\w)(?:senior|sr\.?|lead|principal|staff|head|director|chief|"
    r"vice president|vp|managing director)(?!\w)",
    flags=re.IGNORECASE,
)
_EARLY_CAREER_SIGNAL_RE = re.compile(
    r"(?<!\w)(?:junior|jr\.?|entry[\s-]?level|graduate|trainee|"
    r"early[\s-]?career|new grad|apprentice)(?!\w)",
    flags=re.IGNORECASE,
)
_INTERNSHIP_SIGNAL_RE = re.compile(
    r"(?<!\w)(?:intern(?:ship)?|practicas?|beca|working student)(?!\w)",
    flags=re.IGNORECASE,
)


def _has_senior_experience_evidence(text: str) -> bool:
    """Detect clear senior CV evidence without treating any long CV as senior."""
    normalized = _normalise_words(text)
    if not normalized:
        return False
    if re.search(
        r"(?<!\w)(?:head of|director|chief|vice president|managing director)(?!\w)",
        normalized,
    ):
        return True
    # A passing mention of "senior colleagues" anywhere in a CV is not enough.
    # Check for a senior-level role signal near the profile section instead.
    opening = normalized[:1800]
    has_role_context = re.search(
        r"(?<!\w)(?:analyst|scientist|economist|engineer|consultant|manager|"
        r"specialist|researcher|geologist|geophysicist|advisor|adviser|executive|"
        r"accountant|architect|officer|product owner|project lead)(?!\w)",
        opening,
    )
    if _SENIORITY_SIGNAL_RE.search(opening) and has_role_context:
        return True
    # A long track record alone is a conservative signal; five years can still
    # be intermediate, so require eight years unless a senior title is present.
    years_patterns = (
        r"(?<!\w)(?:8|9|[1-9]\d)\+?\s*(?:years?|yrs?|anos?)\b.{0,45}\b(?:of )?(?:relevant )?(?:work )?experience\b",
        r"\b(?:experience|experiencia)\b.{0,35}\b(?:8|9|[1-9]\d)\+?\s*(?:years?|yrs?|anos?)\b",
    )
    return any(re.search(pattern, normalized) for pattern in years_patterns)


def _has_early_career_evidence(text: str) -> bool:
    """Detect a genuinely early-career CV without treating every student as junior."""
    normalized = _normalise_words(text)
    if not normalized or _has_senior_experience_evidence(text):
        return False
    opening = normalized[:2600]
    explicit_early = re.search(
        r"(?<!\\w)(?:recent graduate|new graduate|graduate student|final year student|"
        r"undergraduate student|master'?s student|currently studying|entry level candidate|"
        r"seeking an internship|seeking internship|early career|recien graduado|"
        r"reci[eé]n titulado|estudiante de master|estudiante universitario|"
        r"busco practicas|buscando practicas)(?!\\w)",
        opening,
    )
    short_experience = re.search(
        r"(?<!\\w)(?:0|1|2)\\s*(?:-|to|a)\\s*(?:1|2)\\s*(?:years?|yrs?|anos?)\\b",
        normalized,
    )
    return bool(explicit_early or short_experience)


def _infer_target_seniority(target_titles: list[str], cv_text: str) -> str | None:
    """Infer the desired level from explicit role titles or strong CV evidence."""
    target_text = " | ".join(_normalise_words(item) for item in target_titles)
    wants_senior = bool(_SENIORITY_SIGNAL_RE.search(target_text))
    wants_early = bool(
        _EARLY_CAREER_SIGNAL_RE.search(target_text)
        or _INTERNSHIP_SIGNAL_RE.search(target_text)
        or _has_early_career_evidence(cv_text)
    )
    if wants_senior and wants_early:
        # Mixed explicit targets should not trigger a global level penalty.
        return None
    if wants_senior:
        return "senior"
    if wants_early:
        return "early"
    return "senior" if _has_senior_experience_evidence(cv_text) else None


def _infer_job_seniority(row: dict[str, Any], title: str, description: str) -> str | None:
    """Infer the advertised level using title, structured metadata and experience evidence."""
    title_text = _normalise_words(title)
    experience_level = _normalise_words(row.get("experience_level"))
    employment_type = _normalise_words(row.get("employment_type_label"))
    structured_type = _normalise_words(row.get("job_type"))
    combined = " ".join(
        part for part in (title_text, experience_level, employment_type, structured_type) if part
    )

    if (
        _INTERNSHIP_SIGNAL_RE.search(combined)
        or "practicas beca" in employment_type
        or "internship" in structured_type
    ):
        return "internship"
    if (
        _EARLY_CAREER_SIGNAL_RE.search(title_text)
        or _EARLY_CAREER_SIGNAL_RE.search(experience_level)
    ):
        return "junior"
    if (
        _SENIORITY_SIGNAL_RE.search(title_text)
        or "senior lead" in experience_level
        or "principal" in experience_level
    ):
        return "senior"

    years_min = row.get("experience_min_years")
    try:
        years_min = float(years_min) if years_min not in (None, "") else None
    except (TypeError, ValueError):
        years_min = None
    if years_min is not None and years_min >= 5:
        return "senior"

    normalized_description = _normalise_words(description)
    if re.search(
        r"\b(?:at least|minimum(?: of)?|over|more than|al menos|minimo de?)\s*[5-9]\+?\s*(?:years?|yrs?|anos?)\b.{0,35}\bexperience\b",
        normalized_description,
    ):
        return "senior"
    return None


def score_job(row: dict[str, Any], config: dict[str, Any] | None = None,
              cv_text: str = "") -> int:
    """Return a transparent 0–100 relevance index (not a hiring probability).

    Uses only target terms and keyword tiers that are actually present in the
    user's configuration plus the uploaded/configured CV. No invented stack.
    """
    config = config or {}
    profile = config.get("profile", {}) if isinstance(config.get("profile", {}), dict) else {}
    search = config.get("search", {}) if isinstance(config.get("search", {}), dict) else {}
    job = canonicalize_row(row)
    title = _normalise_words(job.get("title"))
    description = _normalise_words(job.get("description"))
    company = _normalise_words(job.get("company"))
    text = " ".join(part for part in (title, company, description) if part)

    target_titles = []
    target = _text(profile.get("target_title"))
    if target:
        target_titles.append(target)
    terms = search.get("terms", [])
    if isinstance(terms, list):
        target_titles.extend(_text(term) for term in terms if _text(term))
    signals = profile.get("title_signals", [])
    if isinstance(signals, list):
        target_titles.extend(_text(item.get("pattern")) for item in signals
                             if isinstance(item, dict) and _text(item.get("pattern")))
    target_titles = list(dict.fromkeys(target_titles))

    title_score = 0.0
    if title and target_titles:
        exact_scores = []
        for target_phrase in target_titles:
            phrase = _normalise_words(target_phrase)
            if not phrase:
                continue
            if _contains_norm_term(title, phrase) or _title_phrase_matches(title, phrase):
                exact_scores.append(1.0)
                continue
            tokens = [token for token in phrase.split() if len(token) > 2]
            if tokens:
                matched = sum(1 for token in tokens if _contains_norm_term(title, token))
                if matched == len(tokens):
                    exact_scores.append(0.90)
                elif matched == 1:
                    # One generic shared word (e.g. "data" or "analyst") is
                    # weak evidence, not half a role match.
                    exact_scores.append(0.22)
                else:
                    exact_scores.append(0.55 * matched / len(tokens))
        if exact_scores:
            title_score = max(exact_scores)
        # Search adapters can deliberately return a close role variant (e.g.
        # "Groundwater Specialist" for "Hydrogeologist"). Keep it relevant
        # without scoring it above an exact title match.
        title_score = max(title_score, _role_alias_title_score(title, target_titles))

    keyword_config = profile.get("keywords", {})
    tier_weights = {"critical": 5.0, "strong": 3.0, "moderate": 1.5, "weak": 1.0}
    total_weight = matched_weight = 0.0
    if isinstance(keyword_config, dict):
        for tier, weight in tier_weights.items():
            values = keyword_config.get(tier, [])
            if not isinstance(values, list):
                continue
            for keyword in values:
                keyword = _text(keyword)
                if not keyword:
                    continue
                total_weight += weight
                if _contains_norm_term(text, keyword):
                    matched_weight += weight
    keyword_score = matched_weight / total_weight if total_weight else None

    cv = _normalise_words(cv_text or profile.get("resume_text", ""))
    cv_score: float | None = None
    if cv and text:
        # Deterministic token overlap; vocabulary intersections only, no external model.
        cv_tokens = {w for w in re.findall(r"\b[a-z0-9+#.-]+\b", cv) if len(w) > 2}
        job_tokens = {w for w in re.findall(r"\b[a-z0-9+#.-]+\b", text) if len(w) > 2}
        if cv_tokens and job_tokens:
            cv_score = len(cv_tokens & job_tokens) / len(cv_tokens)

    components: list[tuple[float, float]] = []
    # Do not pretend an unconfigured signal exists. A missing CV does not get
    # replaced with made-up skills such as Python or SQL.
    if target_titles:
        components.append((title_score, 0.55 if keyword_score is not None else 1.0))
    if keyword_score is not None:
        components.append((keyword_score, 0.35 if target_titles else 1.0))
    if cv_score is not None:
        components.append((cv_score, 0.10 if target_titles and keyword_score is not None else 0.20))
    if not components:
        return 0
    weighted_sum = sum(value * weight for value, weight in components)
    denominator = sum(weight for _, weight in components)
    score = max(0, min(100, round(100 * weighted_sum / denominator)))
    mismatch = professional_domain_mismatch(job, config, cv_text)
    if mismatch:
        # A clear cross-domain mismatch should not outrank suitable roles just because
        # the vacancy repeats generic words like "scientist" or "research".
        # Keep clear cross-domain mismatches below the dashboard's default
        # 20-point display threshold; they remain in the database for diagnosis.
        score = min(score, 14)
    else:
        # Reward a distinctive domain match when the user's target title is broad
        # (for example, "Scientist"), so a geoscience CV prefers geoscience over a
        # generic research job that happens to repeat the same broad title.
        cv_domain = _primary_cv_domain(cv_text or _text(profile.get("resume_text", "")))
        job_domain = _primary_job_domain(title, description)
        if cv_domain and job_domain == cv_domain:
            score = min(100, score + 8)

    # Don't let broad keyword overlap make internships dominate a senior search.
    # The penalty is only activated by an explicit senior target or clear CV evidence.
    target_seniority = _infer_target_seniority(
        target_titles, cv_text or _text(profile.get("resume_text", ""))
    )
    job_seniority = _infer_job_seniority(row, title, description)
    if target_seniority == "senior":
        if job_seniority == "internship":
            score = min(score, 15)
        elif job_seniority == "junior":
            score = min(score, 30)
        elif job_seniority == "senior":
            score = min(100, score + 5)
    elif target_seniority == "early":
        # A recent graduate or explicit junior/intern search should not be led
        # by senior vacancies with the same generic job title.
        if job_seniority == "senior":
            # Keep senior vacancies below the default display threshold for an early-career profile.
            score = min(score, 14)

    internship_targets = [
        item for item in target_titles
        if _INTERNSHIP_SIGNAL_RE.search(_normalise_words(item))
    ]
    non_internship_targets = [
        item for item in target_titles
        if not _INTERNSHIP_SIGNAL_RE.search(_normalise_words(item))
    ]
    internship_role_match = any(
        _matches_target_role(title, item) for item in internship_targets
    )
    another_role_match = any(
        _matches_target_role(title, item) for item in non_internship_targets
    )
    if internship_targets and not another_role_match:
        if not internship_role_match or job_seniority != "internship":
            # Do not let a generic title ("Intern - Global Payroll") or a
            # non-intern role ("Business Analyst") fill a specific internship
            # search. The user must explicitly target that other role or the
            # posting must carry positive evidence that it is an internship.
            score = min(score, 14)
    return score
