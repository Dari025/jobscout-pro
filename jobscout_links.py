"""Safe job-link handling and deterministic SQLite discovery for JobScout.

A syntactically valid URL is not proof that the page belongs to the advertised job.
This module rejects known search/listing URLs so the UI never presents them as a
direct vacancy link, and keeps source links separate from application links.
"""
from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from urllib.parse import parse_qs, parse_qsl, unquote, urlencode, urlparse, urlunsplit
from typing import Any, Iterable


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
    if re.search(r"/(jobs?/)?(search|job-search|search-jobs|results)(/|$)", path):
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
    """Build a cross-source dedup key, preferring the concrete posting URL over source IDs."""
    job = canonicalize_row(row)
    source_url, apply_url = choose_job_links(job)
    chosen = source_url or apply_url
    if chosen:
        try:
            parsed = urlparse(chosen)
            host = (parsed.hostname or "").lower().rstrip(".")
            if host.startswith("www."):
                host = host[4:]
            # Keep identity query parameters (e.g. Indeed's jk) but drop tracking noise.
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
            return f"url:{normalized_url}"
        except (ValueError, TypeError):
            pass

    source = _text(job.get("source")).casefold()
    job_id = _text(job.get("id"))
    if job_id:
        return f"id:{source}:{job_id}"
    return "text:" + "|".join(
        _normalise_words(job.get(key))
        for key in ("title", "company", "location", "date_posted")
    )


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


def _normalise_words(value: Any) -> str:
    import unicodedata
    value = unicodedata.normalize("NFKD", _text(value).casefold())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", value)


def _contains_term(haystack: str, term: Any) -> bool:
    normalized_term = _normalise_words(term)
    if not normalized_term:
        return False
    # Single-character skills such as "R" must be whole words; never match
    # the letter inside ordinary words ("remote", "research", etc.).
    pattern = r"(?<!\w)" + re.escape(normalized_term).replace(r"\ ", r"\s+") + r"(?!\w)"
    return re.search(pattern, haystack) is not None


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
            if phrase in title:
                exact_scores.append(1.0)
                continue
            tokens = [token for token in phrase.split() if len(token) > 2]
            if tokens:
                exact_scores.append(sum(1 for token in tokens if _contains_term(title, token)) / len(tokens))
        if exact_scores:
            title_score = max(exact_scores)

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
                if _contains_term(text, keyword):
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
    return max(0, min(100, round(100 * weighted_sum / denominator)))
