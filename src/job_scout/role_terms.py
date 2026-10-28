"""Small, conservative search-term expansion for common geoscience roles."""
from __future__ import annotations

import re


# Seniority labels can make job boards return too few results when the same role
# is advertised without "Senior", "Lead", "Principal" or "Staff" in its title.
# Keep the exact query first, then try the professional role without that prefix.
_SENIORITY_PREFIX = re.compile(
    r"^(?:senior|sr\\.?|lead|principal|staff)\\s+(.+)$",
    flags=re.IGNORECASE,
)


def search_query_variants(search_term: str) -> list[str]:
    """Return the exact query and, for senior-qualified titles, a broader role query.

    The original query always comes first. Only explicit seniority prefixes are
    removed, and unrelated role terms are never generated.
    """
    query = re.sub(r"\\s+", " ", str(search_term or "")).strip()
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
    """Return deduplicated query variants for geology roles, keeping the user's query first.

    This is intentionally narrow: it does not semantically broaden unrelated
    professions. Exact user wording always comes first so source queries preserve
    the original intent before trying adjacent role terminology.
    """
    query = re.sub(r"\s+", " ", str(search_term or "")).strip()
    if not query:
        return []

    folded = query.casefold()
    is_hydro = bool(re.search(r"hydrogeolog|ground[\s-]?water", folded))
    is_geology = is_hydro or bool(
        re.search(r"geolog|geoscien|geophysic", folded)
    )
    if not is_geology:
        return [query]

    if is_hydro:
        family = [
            "hydrogeologist",
            "hydrogeology",
            "hydrogeological",
            "groundwater",
            "ground water",
            "geologist",
            "geoscientist",
            "engineering geologist",
        ]
    else:
        family = [
            "geologist",
            "geology",
            "geological",
            "geoscientist",
            "geoscience",
            "engineering geologist",
            "environmental geologist",
            "exploration geologist",
            "hydrogeologist",
            "groundwater",
        ]

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
    """Match a geology search against title/tag text, including compound role names."""
    text = re.sub(r"\s+", " ", str(candidate_text or "")).casefold()
    for variant in role_search_variants(search_term):
        pattern = r"(?<!\w)" + re.escape(variant.casefold()) + r"(?!\w)"
        if re.search(pattern, text):
            return True
    return False
