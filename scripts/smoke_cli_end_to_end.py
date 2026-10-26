"""Exercise the full CLI -> SQLite -> dashboard-reader path against a live source."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SRC))

from jobscout_links import load_jobs_from_sqlite


def main() -> int:
    template = yaml.safe_load((ROOT / "busqueda.example.yaml").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="jobscout-e2e-") as tmp:
        tmp_path = Path(tmp)
        db_path = tmp_path / "jobs.sqlite"
        config_path = tmp_path / "smoke-config.yaml"

        # Keep this test narrow and deterministic: one source, one query, one location.
        template["config_name"] = "default"
        template["db_path"] = str(db_path)
        template["search"]["terms"] = ["Data Analyst"]
        template["search"]["locations"] = ["Madrid, Spain"]
        template["search"]["sites"] = ["freehire"]
        template["search"]["results_per_site"] = 10
        template["search"]["hours_old"] = 720
        template["scraping"]["delay_min_seconds"] = 0
        template["scraping"]["delay_max_seconds"] = 0
        template["scraping"]["max_retries"] = 0
        template["scraping"]["request_timeout"] = 8
        template["scraping"]["max_pages"] = 1
        template["scraping"]["max_workers"] = 1
        template["scraping"]["fetch_descriptions"] = False
        config_path.write_text(yaml.safe_dump(template, sort_keys=False), encoding="utf-8")

        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join([str(SRC), str(ROOT), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
        env["PYTHONUNBUFFERED"] = "1"
        env["JOBSCOUT_TARGET_TITLE"] = "Data Analyst"
        command = [
            sys.executable, "-m", "job_scout.cli",
            "--config", str(config_path),
            "scrape", "--quick",
        ]
        print("RUN:", " ".join(command))
        try:
            completed = subprocess.run(
                command,
                cwd=ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=120,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            print("FAIL: CLI timed out after 120 seconds")
            if exc.stdout:
                print(exc.stdout)
            return 1

        print("----- CLI output -----")
        print(completed.stdout)
        print(f"CLI exit code: {completed.returncode}")
        print(f"Database path exists: {db_path.is_file()} ({db_path})")

        jobs, diagnostics = load_jobs_from_sqlite(
            {"db_path": str(db_path), "config_name": "default"},
            root=ROOT,
        )
        print("----- dashboard reader diagnostics -----")
        for item in diagnostics:
            print(item)
        print(f"Dashboard reader loaded {len(jobs)} jobs")
        print("Sample:", [
            {
                "title": job.get("title"),
                "company": job.get("company"),
                "location": job.get("location"),
                "source": job.get("source"),
                "job_url": job.get("job_url"),
            }
            for job in jobs[:3]
        ])

        if completed.returncode != 0:
            print("FAIL: real CLI search returned a non-zero exit code")
            return 1
        if not db_path.is_file():
            print("FAIL: CLI reported success but did not create the configured database")
            return 1
        if not jobs:
            print("FAIL: CLI ran but the same reader used by the dashboard cannot see any saved jobs")
            return 1
        print("PASS: live source -> CLI -> SQLite -> dashboard reader")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
