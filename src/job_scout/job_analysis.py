"""Explainable job analysis for optional salary, seniority and work-mode filters.

This module deliberately does not invent missing requirements, compensation or
seniority. It extracts explicit evidence from structured fields and descriptions.
"""
from __future__ import annotations

import html
import json
import re
from typing import Any


CURRENCY_SIGNS = {
    "€": "EUR",
    "eur": "EUR",
    "£": "GBP",
    "gbp": "GBP",
    "$": "USD",
    "usd": "USD",
    "us$": "USD",
    "cad": "CAD",
    "c$": "CAD",
    "aud": "AUD",
    "a$": "AUD",
    "chf": "CHF",
}

INTERVAL_LABELS = {
    "year": "año",
    "yearly": "año",
    "annual": "año",
    "annually": "año",
    "month": "mes",
    "monthly": "mes",
    "week": "semana",
    "weekly": "semana",
    "day": "día",
    "daily": "día",
    "hour": "hora",
    "hourly": "hora",
}

ANNUALIZATION = {
    "year": 1.0,
    "yearly": 1.0,
    "annual": 1.0,
    "annually": 1.0,
    "month": 12.0,
    "monthly": 12.0,
    "week": 52.0,
    "weekly": 52.0,
    "day": 260.0,
    "daily": 260.0,
    "hour": 2080.0,
    "hourly": 2080.0,
}

EXPERIENCE_BANDS = (
    "Prácticas / beca",
    "Junior / entrada",
    "Intermedio",
    "Senior / lead",
)

CONTRACT_TYPES = (
    "Prácticas / beca",
    "Tiempo parcial",
    "Tiempo completo",
    "Contrato / freelance",
    "Temporal",
)

WORK_MODES = ("Remoto", "Híbrido", "Presencial")

SKILLS = {
    "SQL": (r"\bsql\b",),
    "Python": (r"\bpython\b",),
    "R": (r"\br programming\b", r"\blanguage r\b", r"\bR\b"),
    "Excel": (r"\bexcel\b", r"\bspreadsheets?\b"),
    "Power BI": (r"\bpower\s*bi\b",),
    "Tableau": (r"\btableau\b",),
    "Statistics": (r"\bstatistics?\b", r"\bestad[ií]stic[ao]s?\b"),
    "Econometrics": (r"\beconometrics?\b", r"\beconometr[ií]a\b"),
    "Machine learning": (r"\bmachine learning\b", r"\baprendizaje autom[aá]tico\b"),
    "Python pandas": (r"\bpandas\b",),
    "Data visualization": (r"\bdata visuali[sz]ation\b", r"\bvisualizaci[oó]n de datos\b"),
    "Forecasting": (r"\bforecasting\b", r"\bprevisi[oó]n\b"),
    "Cloud / Azure": (r"\bazure\b", r"\baws\b", r"\bgcp\b", r"\bcloud\b"),
    "Machine learning frameworks": (r"\bscikit.learn\b", r"\btensorflow\b", r"\bpytorch\b"),
    "Communication": (r"\bcommunication skills?\b", r"\bcomunicaci[oó]n\b"),
    "Degree": (r"\bbachelor'?s?\b", r"\bmaster'?s?\b", r"\bdegree\b", r"\bgrado\b", r"\blicenciatura\b", r"\bm[aá]ster\b"),
}

# Keep salary parsing conservative: a currency or clear salary context is required.
_NUMBER = r"(?:\d{1,3}(?:[.,\s]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)(?:\s*[kK])?"
_CURRENCY = r"€|£|US\$|C\$|A\$|\bEUR\b|\bUSD\b|\bGBP\b|\bCAD\b|\bAUD\b|\bCHF\b"


def _text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if value != value:  # NaN
            return ""
    except Exception:
        pass
    return html.unescape(str(value)).strip()


def _parse_number(value: str) -> float | None:
    raw = re.sub(r"\s", "", value or "")
    if not raw:
        return None
    multiplier = 1000.0 if raw.lower().endswith("k") else 1.0
    if multiplier != 1.0:
        raw = raw[:-1]
    if "," in raw and "." in raw:
        # The rightmost separator is the decimal separator; the other is thousands.
        decimal = "," if raw.rfind(",") > raw.rfind(".") else "."
        thousands = "." if decimal == "," else ","
        raw = raw.replace(thousands, "").replace(decimal, ".")
    elif "," in raw or "." in raw:
        sep = "," if "," in raw else "."
        left, right = raw.rsplit(sep, 1)
        if len(right) == 3 and left.replace(sep, "").isdigit():
            raw = left.replace(sep, "") + right
        else:
            raw = left.replace(sep, "") + "." + right
    try:
        return float(raw) * multiplier
    except ValueError:
        return None


def _currency(value: str) -> str | None:
    lower = (value or "").strip().lower()
    for key in sorted(CURRENCY_SIGNS, key=len, reverse=True):
        if key in lower:
            return CURRENCY_SIGNS[key]
    return None


def _interval(text: str) -> str | None:
    lower = re.sub(r"[_-]+", " ", (text or "").casefold())
    if re.search(r"\b(per hour|an hour|hourly|/hour|per hr|hour)\b|por hora|hora", lower):
        return "hour"
    if re.search(r"\b(per day|daily|/day|day rate|per diem)\b|por d[ií]a|diari[oa]", lower):
        return "day"
    if re.search(r"\b(per week|weekly|/week|a week)\b|por semana|semanal", lower):
        return "week"
    if re.search(r"\b(per month|monthly|/month|a month)\b|por mes|mensual", lower):
        return "month"
    if re.search(r"\b(per year|per annum|yearly|annual(?:ly)?|/year|a year|p\.?a\.?)\b|por a[nñ]o|anual", lower):
        return "year"
    return None


def _display_salary(low: float | None, high: float | None, currency: str, interval: str | None) -> str:
    if low is None and high is None:
        return ""
    amount_low = f"{low:,.0f}" if low is not None else ""
    amount_high = f"{high:,.0f}" if high is not None else ""
    if amount_low and amount_high and low != high:
        amount = f"{amount_low}–{amount_high}"
    else:
        amount = amount_low or amount_high
    symbol = {"EUR": "€", "GBP": "£", "USD": "$", "CAD": "C$", "AUD": "A$", "CHF": "CHF "}.get(currency, currency + " ")
    per = f"/{INTERVAL_LABELS[interval]}" if interval in INTERVAL_LABELS else ""
    return f"{symbol}{amount}{per}"


def analyze_salary(row: dict[str, Any]) -> dict[str, Any]:
    """Extract disclosed salary; only EUR with known/defensible period is comparable."""
    raw_display = _text(row.get("salary"))
    currency = _text(row.get("comp_currency") or row.get("salary_currency")).upper() or None
    interval_raw = _text(row.get("comp_interval") or row.get("salary_interval")).lower()
    interval = interval_raw if interval_raw in ANNUALIZATION else None
    low = _parse_number(_text(row.get("comp_min") or row.get("min_amount"))) if _text(row.get("comp_min") or row.get("min_amount")) else None
    high = _parse_number(_text(row.get("comp_max") or row.get("max_amount"))) if _text(row.get("comp_max") or row.get("max_amount")) else None
    evidence = "campo salarial estructurado"

    # Legacy feeds sometimes store pay as a string rather than structured fields.
    text = raw_display
    if not text:
        text = _text(row.get("description"))
        evidence = "descripción del anuncio"
    if low is None and high is None and text:
        period = _interval(text)
        ranges = [
            rf"(?P<currency>{_CURRENCY})\s*(?P<low>{_NUMBER})\s*(?:-|–|—|to|hasta)\s*(?:{_CURRENCY}\s*)?(?P<high>{_NUMBER})",
            rf"(?P<low>{_NUMBER})\s*(?P<currency>{_CURRENCY})\s*(?:-|–|—|to|hasta)\s*(?P<high>{_NUMBER})\s*(?:{_CURRENCY})?",
            rf"(?P<currency>{_CURRENCY})\s*(?P<low>{_NUMBER})",
        ]
        for pattern in ranges:
            match = re.search(pattern, text, flags=re.I)
            if not match:
                continue
            groups = match.groupdict()
            low = _parse_number(groups.get("low") or "")
            high = _parse_number(groups.get("high") or "") if groups.get("high") else None
            currency = _currency(groups.get("currency") or "") or currency
            interval = period or interval
            if low is not None:
                evidence = "importe detectado en texto del anuncio"
                break

    if raw_display and low is None and high is None:
        # Keep an existing published salary string visible even when it cannot
        # be safely normalized to numeric values.
        return {
            "salary_display": raw_display,
            "salary_currency": currency,
            "salary_interval": interval,
            "salary_eur_year_min": None,
            "salary_eur_year_max": None,
            "salary_known": False,
            "salary_evidence": "importe publicado no normalizable",
        }

    if not currency and (low is not None or high is not None):
        currency = "EUR" if re.search(r"€|\bEUR\b|euros?", text, flags=re.I) else None
    currency = currency or "Moneda no indicada"
    salary_display = _display_salary(low, high, currency, interval) if low is not None or high is not None else raw_display
    annual_min = None
    annual_max = None
    if currency == "EUR" and interval in ANNUALIZATION:
        factor = ANNUALIZATION[interval]
        if low is not None:
            annual_min = low * factor
        if high is not None:
            annual_max = high * factor
        elif low is not None:
            annual_max = annual_min
    return {
        "salary_display": salary_display or raw_display,
        "salary_currency": currency,
        "salary_interval": interval,
        "salary_eur_year_min": annual_min,
        "salary_eur_year_max": annual_max,
        "salary_known": low is not None or high is not None,
        "salary_evidence": evidence if low is not None or high is not None else "sin cifra salarial verificable",
    }


def infer_experience(row: dict[str, Any]) -> dict[str, Any]:
    """Infer broad experience band, showing evidence and preserving unknowns."""
    title = _text(row.get("title"))
    description = _text(row.get("description"))
    text = f"{title}\n{description}".casefold()
    years_min: int | None = None
    years_max: int | None = None
    evidence = ""

    range_patterns = [
        r"\b(?P<lo>\d{1,2})\s*(?:-|–|to)\s*(?P<hi>\d{1,2})\s*\+?\s*(?:years?|yrs?|a[nñ]os?)\s+(?:of\s+)?(?:relevant\s+)?experience",
        r"\b(?P<lo>\d{1,2})\s*(?:-|–|a)\s*(?P<hi>\d{1,2})\s*a[nñ]os?\s+de\s+experiencia",
    ]
    plus_patterns = [
        r"\b(?:at least|minimum(?: of)?|over|more than|at least)\s+(?P<lo>\d{1,2})\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?experience",
        r"\b(?P<lo>\d{1,2})\s*\+\s*(?:years?|yrs?)\s+(?:of\s+)?(?:relevant\s+)?experience",
        r"\b(?:m[ií]nimo de?\s+)?(?P<lo>\d{1,2})\s*\+?\s*a[nñ]os?\s+de\s+experiencia",
    ]
    for pattern in range_patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            years_min, years_max = int(match.group("lo")), int(match.group("hi"))
            evidence = match.group(0)
            break
    if years_min is None:
        for pattern in plus_patterns:
            match = re.search(pattern, text, flags=re.I)
            if match:
                years_min = int(match.group("lo"))
                evidence = match.group(0)
                break
    if years_min is None:
        single_patterns = (
            r"\b(?P<lo>\d{1,2})\s*(?:years?|yrs?)\s+(?:of\s+)?(?:relevant\s+)?experience",
            r"\b(?P<lo>\d{1,2})\s*a[nñ]os?\s+de\s+experiencia",
        )
        for pattern in single_patterns:
            match = re.search(pattern, text, flags=re.I)
            if match:
                years_min = int(match.group("lo"))
                evidence = match.group(0)
                break

    if re.search(r"\b(intern(ship)?|working student|student worker|trainee|apprentice|beca|pr[aá]cticas|pasant[ií]a|est[aá]gio)\b", text):
        level = "Prácticas / beca"
        level_evidence = "título o descripción menciona prácticas/beca"
    elif re.search(r"\b(senior|sr\.?|lead|principal|staff engineer|head of|director)\b", title, flags=re.I):
        level = "Senior / lead"
        level_evidence = "título de la vacante"
    elif re.search(r"\b(mid[\s-]?level|intermediate|experienced professional)\b", title, flags=re.I):
        level = "Intermedio"
        level_evidence = "título de la vacante"
    elif re.search(r"\b(junior|jr\.?|entry[\s-]?level|graduate|early[\s-]?career|new grad)\b", title, flags=re.I) or years_max is not None and years_max <= 2 or years_min is not None and years_min <= 1 and (years_max is None or years_max <= 2):
        level = "Junior / entrada"
        level_evidence = "mención junior/entry-level o requisito de experiencia inicial"
    elif years_min is not None and years_min >= 5:
        level = "Senior / lead"
        level_evidence = "años de experiencia requeridos"
    elif years_min is not None and years_min >= 2:
        level = "Intermedio"
        level_evidence = "años de experiencia requeridos"
    else:
        level = "No indicado"
        level_evidence = "el anuncio no permite asignar un nivel con suficiente confianza"

    return {
        "experience_level": level,
        "experience_min_years": years_min,
        "experience_max_years": years_max,
        "experience_evidence": evidence or level_evidence,
        "experience_level_evidence": level_evidence,
    }


def infer_employment_type(row: dict[str, Any]) -> dict[str, str]:
    """Map structured job-type metadata and explicit wording to a common label."""
    raw_types = row.get("job_type") or row.get("job_types") or row.get("employment_type") or ""
    if isinstance(raw_types, (list, tuple, set)):
        source = " ".join(str(value) for value in raw_types)
    else:
        source = _text(raw_types)
        try:
            decoded = json.loads(source)
            if isinstance(decoded, list):
                source = " ".join(str(value) for value in decoded)
        except (json.JSONDecodeError, TypeError):
            pass
    text = f"{_text(row.get('title'))} {_text(row.get('description'))} {source}".casefold()
    if re.search(r"\b(intern(ship)?|working student|student worker|trainee|beca|pr[aá]cticas|pasant[ií]a|est[aá]gio)\b", text):
        label = "Prácticas / beca"
        evidence = "título, descripción o metadato"
    elif re.search(r"\b(part[\s-]?time|parttime|half[\s-]?time|media jornada|tiempo parcial|teilzeit)\b", text):
        label = "Tiempo parcial"
        evidence = "título, descripción o metadato"
    elif re.search(r"\b(full[\s-]?time|fulltime|tiempo completo|jornada completa|vollzeit)\b", text):
        label = "Tiempo completo"
        evidence = "título, descripción o metadato"
    elif re.search(r"\b(contract|contractor|freelance|freelancer|aut[oó]nom[oa])\b", text):
        label = "Contrato / freelance"
        evidence = "título, descripción o metadato"
    elif re.search(r"\b(temporary|fixed[\s-]?term|temporal|contrato de sustituci[oó]n)\b", text):
        label = "Temporal"
        evidence = "título, descripción o metadato"
    else:
        label = "No indicado"
        evidence = "tipo de contrato no indicado"
    return {"employment_type_label": label, "employment_type_evidence": evidence}


DURATION_BANDS = (
    "Prácticas de verano (≤3 meses)",
    "Prácticas cortas (3–6 meses)",
    "6–12 meses",
    "Más de 12 meses",
    "Indefinido / largo plazo",
)


def infer_hours_per_week(row: dict[str, Any]) -> dict[str, Any]:
    """Extract weekly hours only when the vacancy states a numeric amount."""
    text = f"{_text(row.get('title'))} {_text(row.get('description'))}".casefold()
    range_patterns = (
        r"\b(?P<lo>\d{1,2})\s*(?:-|–|to|a)\s*(?P<hi>\d{1,2})\s*(?:hours?|hrs?|h)\s*(?:per|/)\s*week\b",
        r"\b(?P<lo>\d{1,2})\s*(?:-|–|a)\s*(?P<hi>\d{1,2})\s*horas?\s*(?:por|a la)\s*semana\b",
    )
    single_patterns = (
        r"\b(?P<lo>\d{1,2})\s*(?:hours?|hrs?|h)\s*(?:per|/)\s*week\b",
        r"\b(?P<lo>\d{1,2})\s*hours?\s*weekly\b",
        r"\b(?P<lo>\d{1,2})\s*horas?\s*(?:por|a la)\s*semana\b",
        r"\b(?P<lo>\d{1,2})\s*horas?\s*semanales\b",
    )
    for pattern in range_patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            low, high = int(match.group("lo")), int(match.group("hi"))
            if 1 <= low <= high <= 100:
                return {
                    "hours_per_week_min": low,
                    "hours_per_week_max": high,
                    "hours_per_week_label": f"{low}–{high} h/semana",
                    "hours_per_week_evidence": match.group(0),
                }
    for pattern in single_patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            hours = int(match.group("lo"))
            if 1 <= hours <= 100:
                return {
                    "hours_per_week_min": hours,
                    "hours_per_week_max": hours,
                    "hours_per_week_label": f"{hours} h/semana",
                    "hours_per_week_evidence": match.group(0),
                }
    return {
        "hours_per_week_min": None,
        "hours_per_week_max": None,
        "hours_per_week_label": "No indicado",
        "hours_per_week_evidence": "el anuncio no especifica horas semanales comparables",
    }


def infer_duration(row: dict[str, Any]) -> dict[str, Any]:
    """Infer a duration band from explicit contract/placement wording only."""
    text = f"{_text(row.get('title'))} {_text(row.get('description'))}".casefold()
    if re.search(r"\b(indefinite|permanent|permanent contract|indefinido|indefinida|contrato fijo|long[- ]term|ongoing role)\b", text):
        return {
            "duration_band": "Indefinido / largo plazo",
            "duration_months_min": None,
            "duration_months_max": None,
            "duration_evidence": "el anuncio menciona una relación indefinida o de largo plazo",
        }
    patterns = (
        r"\b(?P<lo>\d{1,2})\s*(?:-|–|to|a)\s*(?P<hi>\d{1,2})\s*(?:months?|meses)\b",
        r"\b(?P<lo>\d{1,2})\s*(?:months?|meses)[- ](?:long|duration|internship|contract|pr[aá]cticas|de duraci[oó]n)\b",
        r"\b(?:duration|duraci[oó]n|internship|placement|contract|contrato|pr[aá]cticas|beca)[^.!?;]{0,55}?(?P<lo>\d{1,2})\s*(?:months?|meses)\b",
        r"\b(?P<lo>\d{1,2})\s*(?:months?|meses)\b",
    )
    months_min = months_max = None
    evidence = ""
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if not match:
            continue
        snippet = match.group(0)
        # Do not interpret a requirement for months of experience as job duration.
        if re.search(r"experience|experiencia", text[max(0, match.start()-18):min(len(text), match.end()+18)]):
            continue
        months_min = int(match.group("lo"))
        months_max = int(match.groupdict().get("hi") or months_min)
        if not (1 <= months_min <= months_max <= 120):
            months_min = months_max = None
            continue
        evidence = snippet
        break
    if months_min is None:
        return {
            "duration_band": "No indicado",
            "duration_months_min": None,
            "duration_months_max": None,
            "duration_evidence": "el anuncio no indica una duración verificable",
        }
    if months_max <= 3:
        band = "Prácticas de verano (≤3 meses)"
    elif months_max <= 6:
        band = "Prácticas cortas (3–6 meses)"
    elif months_min <= 12:
        band = "6–12 meses"
    else:
        band = "Más de 12 meses"
    return {
        "duration_band": band,
        "duration_months_min": months_min,
        "duration_months_max": months_max,
        "duration_evidence": evidence,
    }


def infer_work_mode(row: dict[str, Any]) -> dict[str, str]:
    """Infer mode only when the posting explicitly provides a clear signal."""
    text = f"{_text(row.get('title'))} {_text(row.get('description'))} {_text(row.get('location'))}".casefold()
    remote_flag = _text(row.get("is_remote")).casefold() in {"1", "true", "yes", "y", "remote"}
    if remote_flag or re.search(r"\b(remote|fully remote|remote-first|work from home|telework|teletrabajo|remoto|en remoto)\b", text):
        return {"work_mode_label": "Remoto", "work_mode_evidence": "anuncio o ubicación menciona remoto"}
    if re.search(r"\b(hybrid|h[ií]brido|h[ií]brida|3 days in office|days office|flexible office attendance)\b", text):
        return {"work_mode_label": "Híbrido", "work_mode_evidence": "anuncio menciona modalidad híbrida"}
    if re.search(r"\b(on[\s-]?site|onsite|in[\s-]?office|office[\s-]?based|presencial|en oficina)\b", text):
        return {"work_mode_label": "Presencial", "work_mode_evidence": "anuncio menciona presencialidad"}
    return {"work_mode_label": "No indicado", "work_mode_evidence": "modalidad no indicada claramente"}


def extract_requirements(row: dict[str, Any]) -> list[str]:
    """Return a small list of explicitly mentioned tools/requirements in the ad text."""
    text = f"{_text(row.get('title'))}\n{_text(row.get('description'))}"
    requirements: list[str] = []
    for label, patterns in SKILLS.items():
        if any(re.search(pattern, text, flags=re.I) for pattern in patterns):
            requirements.append(label)
    return requirements


def analyze_job(
    row: dict[str, Any],
    cv_text: str = "",
    target_terms: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    """Combine evidence-based extraction into one explainable card analysis."""
    salary = analyze_salary(row)
    experience = infer_experience(row)
    contract = infer_employment_type(row)
    mode = infer_work_mode(row)
    duration = infer_duration(row)
    hours = infer_hours_per_week(row)
    requirements = extract_requirements(row)
    cv = _text(cv_text).casefold()
    cv_matches = [
        skill for skill in requirements
        if cv and any(re.search(pattern, cv, flags=re.I) for pattern in SKILLS[skill])
    ]
    cv_unconfirmed = [skill for skill in requirements if skill not in cv_matches] if cv else []
    title = _text(row.get("title")).casefold()
    target_matches = [
        term for term in target_terms
        if term and (term.casefold() in title or any(
            token in title for token in term.casefold().split() if len(token) > 3
        ))
    ]
    notes = [
        salary["salary_evidence"],
        experience["experience_level_evidence"],
        contract["employment_type_evidence"],
        mode["work_mode_evidence"],
    ]
    return {
        **salary,
        **experience,
        **contract,
        **mode,
        **duration,
        **hours,
        "requirements": requirements,
        "cv_matches": cv_matches,
        "cv_unconfirmed": cv_unconfirmed,
        "target_title_matches": target_matches,
        "analysis_method": "extracción explicable de texto y metadatos",
        "analysis_notes": notes,
    }


def job_matches_optional_filters(job: dict[str, Any], options: dict[str, Any]) -> bool:
    """Apply optional filters while retaining unknown data unless the user opts out."""
    def matches(observed: Any, selected: Any, include_unknown: bool) -> bool:
        if not selected:
            return True
        value = _text(observed) or "No indicado"
        if value.casefold() in {"no indicado", "unknown", "none", "nan"}:
            return include_unknown
        values = set(selected) if isinstance(selected, (list, tuple, set)) else {selected}
        return value in values

    min_salary = options.get("min_salary_eur_year")
    max_salary = options.get("max_salary_eur_year")
    if min_salary is not None or max_salary is not None:
        salary_low = job.get("salary_eur_year_min")
        salary_high = job.get("salary_eur_year_max")
        try:
            missing_salary = salary_low is None or salary_low != salary_low
        except Exception:
            missing_salary = True
        if missing_salary:
            if not options.get("include_unknown_salary", True):
                return False
        else:
            # A range that overlaps the requested band is kept; do not reject it
            # just because its lower bound sits below the user's minimum.
            try:
                low_value = float(salary_low)
                high_value = float(salary_high) if salary_high is not None and salary_high == salary_high else low_value
            except (TypeError, ValueError):
                if not options.get("include_unknown_salary", True):
                    return False
            else:
                if min_salary is not None and high_value < float(min_salary):
                    return False
                if max_salary is not None and low_value > float(max_salary):
                    return False

    if not matches(job.get("experience_level"), options.get("experience_level"), options.get("include_unknown_experience", True)):
        return False
    if not matches(job.get("employment_type_label"), options.get("employment_type"), options.get("include_unknown_employment", True)):
        return False
    if not matches(job.get("work_mode_label"), options.get("work_mode"), options.get("include_unknown_work_mode", True)):
        return False
    if not matches(job.get("duration_band"), options.get("duration_band"), options.get("include_unknown_duration", True)):
        return False

    max_hours = options.get("max_hours_per_week")
    if max_hours is not None:
        observed_hours = job.get("hours_per_week_max")
        if observed_hours is None:
            observed_hours = job.get("hours_per_week_min")
        try:
            hours_unknown = observed_hours is None or observed_hours != observed_hours
        except Exception:
            hours_unknown = True
        if hours_unknown:
            if not options.get("include_unknown_hours", True):
                return False
        elif float(observed_hours) > float(max_hours):
            return False
    return True
