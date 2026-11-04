"""Small, conservative search-term expansion for common geoscience roles."""
from __future__ import annotations

import re

# Seniority labels can make job boards return too few results when the same role
# is advertised without "Senior", "Lead", "Principal" or "Staff" in its title.
# Keep the exact query first, then try the professional role without that prefix.
_SENIORITY_PREFIX = re.compile(
    r"^(?:senior|sr\.?|lead|principal|staff)\s+(.+)$",
    flags=re.IGNORECASE,
)


def search_query_variants(search_term: str) -> list[str]:
    """Return the exact query and, for senior-qualified titles, a broader role query.

    The original query always comes first. Only explicit seniority prefixes are
    removed, and unrelated role terms are never generated.
    """
    query = re.sub(r"\s+", " ", str(search_term or "")).strip()
    if not query:
        return []

    variants = [query]
    match = _SENIORITY_PREFIX.match(query)
    if match:
        base_title = match.group(1).strip(" -–—:,")
        if base_title and base_title.casefold() != query.casefold():
            variants.append(base_title)

    output: list[str] = []
    seen: set[str] = set()
    for candidate in variants:
        key = candidate.casefold()
        if key not in seen:
            seen.add(key)
            output.append(candidate)
    return output


def role_search_variants(search_term: str) -> list[str]:
    """Return conservative role synonyms, preserving the user's exact query first.

    The aliases are deliberately curated rather than generated from isolated
    words. This helps job boards find adjacent professional titles without
    turning "Data Analyst" into every job that merely mentions "data".
    """
    query = re.sub(r"\s+", " ", str(search_term or "")).strip()
    if not query:
        return []

    folded = query.casefold()
    family: list[str] = []

    is_hydro = bool(re.search(r"hydrogeolog|ground[\s-]?water", folded))
    is_geology = is_hydro or bool(re.search(r"geolog|geoscien|geophysic", folded))
    if is_geology:
        if is_hydro:
            family = [
                "hydrogeologist", "hydrogeology", "hydrogeological",
                "groundwater", "groundwater specialist", "groundwater engineer",
                "groundwater modeller", "groundwater modeler",
                "groundwater consultant", "ground water specialist",
                "geologist", "geoscientist", "engineering geologist",
            ]
        else:
            family = [
                "geologist", "geology", "geological", "geoscientist",
                "geoscience", "engineering geologist", "environmental geologist",
                "exploration geologist", "hydrogeologist",
                "groundwater specialist", "groundwater engineer",
                "groundwater modeller", "groundwater modeler",
            ]
    else:
        alias_groups = (
            ("data analyst", (
                "business intelligence analyst", "bi analyst",
                "reporting analyst", "analytics analyst", "data reporting analyst",
            )),
            ("decision science", (
                "decision scientist", "data science", "operations research analyst",
                "quantitative analyst", "decision analyst",
            )),
            ("hr specialist", (
                "human resources specialist", "hr generalist",
                "people operations specialist", "recruitment specialist",
            )),
            ("customer support", (
                "customer service specialist", "customer care specialist",
                "technical support specialist", "customer success specialist",
            )),
            ("customer success", (
                "customer support specialist", "customer service specialist",
            )),
            ("software engineer", (
                "software developer", "software programmer",
            )),
            ("backend engineer", (
                "backend developer", "back-end developer",
            )),
            ("financial analyst", (
                "finance analyst", "fp&a analyst", "financial planning analyst",
            )),
            ("supply chain analyst", (
                "logistics analyst", "procurement analyst", "demand planner",
                "inventory analyst",
            )),
        )
        for trigger, aliases in alias_groups:
            if trigger in folded:
                family.extend(aliases)

    output: list[str] = []
    seen: set[str] = set()
    for candidate in [query, *family]:
        normalized = re.sub(r"\s+", " ", candidate).strip()
        key = normalized.casefold()
        if key and key not in seen:
            seen.add(key)
            output.append(normalized)
    return output


def role_matches_text(search_term: str, candidate_text: str) -> bool:
    """Match a role query against a title using complete professional aliases."""
    text = re.sub(r"\s+", " ", str(candidate_text or "")).casefold()
    for variant in role_search_variants(search_term):
        # Broad standalone terms help query providers but are too noisy to
        # qualify a title (e.g. "administrative officer - groundwater rights").
        if variant.casefold() in {"groundwater"}:
            continue
        pattern = r"(?<!\w)" + re.escape(variant.casefold()) + r"(?!\w)"
        if re.search(pattern, text):
            return True
    return False
