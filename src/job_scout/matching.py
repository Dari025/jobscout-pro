"""Shared term matching for job text.

Single source of truth for comparing keywords against job text. Both the CLI
scorer and the Streamlit dashboard must agree on what counts as a match, so
normalisation and whole-word matching live here instead of being copied.

Two entry points exist for a reason: ``contains_term`` is the safe one and
normalises whatever it receives; ``contains_normalised_term`` assumes the
haystack is already the output of ``normalise_words`` and skips that work. The
dashboard scores every vacancy against every keyword on each rerun, so
renormalising a multi-kilobyte description per keyword dominates the runtime.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from typing import Any

_EMPTY_VALUES = {"", "none", "nan", "null", "#", "n/a", "na"}


def _text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in _EMPTY_VALUES else text


def normalise_words(value: Any) -> str:
    """Lowercase and strip accents, collapsing whitespace into single spaces."""
    value = unicodedata.normalize("NFKD", _text(value).casefold())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", value)


@lru_cache(maxsize=1024)
def _term_pattern(normalised_term: str) -> re.Pattern[str]:
    """Compile the whole-word pattern for an already normalised term."""
    body = re.escape(normalised_term).replace(r"\ ", r"\s+")
    return re.compile(r"(?<!\w)" + body + r"(?!\w)")


def contains_normalised_term(normalised_haystack: str, term: Any) -> bool:
    """Match a term against a haystack that is already normalised.

    Only use this when the haystack went through ``normalise_words``; passing
    raw text would miss accent and case differences.
    """
    normalized_term = normalise_words(term)
    if not normalized_term:
        return False
    # Single-character skills such as "R" must be whole words; never match
    # the letter inside ordinary words ("remote", "research", etc.).
    return _term_pattern(normalized_term).search(normalised_haystack) is not None


def contains_term(haystack: Any, term: Any) -> bool:
    """Return True when ``term`` appears in ``haystack`` as a whole word."""
    return contains_normalised_term(normalise_words(haystack), term)
