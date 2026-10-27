"""Small, conservative search-term expansion for common geoscience roles."""
from __future__ import annotations

import re


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
