"""Minimal environment passed to the public dashboard's scraper subprocess.

Do not forward API tokens, mail credentials, bot secrets, host credentials, or
arbitrary parent-process settings to a subprocess that processes user queries.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping


_SAFE_PARENT_KEYS = {
    "PATH",
    "HOME",
    "USERPROFILE",
    "SYSTEMROOT",
    "WINDIR",
    "TEMP",
    "TMP",
    "TMPDIR",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
}


def build_scraper_subprocess_env(
    parent_env: Mapping[str, str],
    target_title: str,
    src_dir: str | Path,
) -> dict[str, str]:
    """Return an allowlisted environment for the job-search subprocess."""
    env = {
        key: value
        for key, value in parent_env.items()
        if key.upper() in _SAFE_PARENT_KEYS
    }
    env["PYTHONUNBUFFERED"] = "1"
    env["JOBSCOUT_TARGET_TITLE"] = str(target_title or "")
    # Do not inherit an arbitrary PYTHONPATH from the hosting/user environment.
    env["PYTHONPATH"] = str(Path(src_dir).resolve())
    return env
