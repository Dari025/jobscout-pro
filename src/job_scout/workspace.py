"""Neutral per-session configuration for the public multi-user dashboard."""
from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

import yaml


EMPTY_KEYWORDS = {
    "critical": [],
    "strong": [],
    "moderate": [],
    "weak": [],
}
EMPTY_COMPANY_TIERS = {"tier1": [], "tier2": [], "tier3": []}

SEARCH_LOCATION_OPTIONS = [
    "Madrid, Spain",
    "Barcelona, Spain",
    "Valencia, Spain",
    "Spain",
    "Remote, Europe",
]


def parse_target_terms(target_title: str) -> list[str]:
    """Parse only the titles entered by the current user; no implicit role defaults."""
    return list(dict.fromkeys(
        part.strip()
        for part in re.split(r"[/,;|\n]+", str(target_title or ""))
        if part.strip()
    ))


def build_workspace_config(
    base_config: dict[str, Any],
    workspace_dir: str | Path,
    target_title: str,
    search_locations: list[str] | tuple[str, ...],
) -> dict[str, Any]:
    """Create a neutral config and bind its SQLite database to one browser session.

    CV contents are deliberately not copied into the YAML. Uploaded CV text stays in
    Streamlit session memory and is only used for ranking in that same session.
    """
    workspace = Path(workspace_dir).expanduser().resolve()
    result = copy.deepcopy(base_config)

    profile = dict(result.get("profile") or {})
    profile.update({
        "name": "",
        "target_title": str(target_title or "").strip(),
        "resume_text": "",
        "keywords": copy.deepcopy(EMPTY_KEYWORDS),
        "target_companies": copy.deepcopy(EMPTY_COMPANY_TIERS),
        "title_signals": [],
        "target_levels": [],
    })
    result["profile"] = profile

    search = dict(result.get("search") or {})
    search["terms"] = parse_target_terms(target_title)
    valid_locations = set(SEARCH_LOCATION_OPTIONS)
    search["locations"] = list(dict.fromkeys(
        str(location).strip()
        for location in search_locations
        if str(location).strip() in valid_locations
    ))
    result["search"] = search

    result["db_path"] = str(workspace / "jobs.sqlite")
    result["config_name"] = "session"
    result["report_dir"] = str(workspace / "reports")
    return result


def write_workspace_config(
    base_config: dict[str, Any],
    workspace_dir: str | Path,
    target_title: str,
    search_locations: list[str] | tuple[str, ...],
) -> Path:
    """Write the per-session scraper config with no personal CV/profile data."""
    workspace = Path(workspace_dir).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    payload = build_workspace_config(
        base_config, workspace, target_title, search_locations
    )
    config_path = workspace / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return config_path
