#!/usr/bin/env python3
"""Detect and commit substantive data changes from the hourly crawl.

The pipeline writes a fresh ``generated_at`` and snapshot version on every run.
Committing those fields every hour would create noisy, large history. This
helper fingerprints only semantic inputs (CSV rows without fetch metadata plus
pipeline/config code) and commits at most once per UTC day.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
FINGERPRINT_PATH = ROOT / ".github" / "aicor_fingerprint"
LAST_COMMIT_PATH = ROOT / ".github" / "aicor_last_commit"
VOLATILE_COLUMNS = {"run_id", "fetched_at", "response_sha256"}

FINGERPRINT_CSV = [
    "data/raw/sec/filings.csv",
    "data/raw/sec/facts.csv",
    "data/raw/sec/segments.csv",
    "data/raw/prices/corporate_actions.csv",
    "data/verified/prices_processed.csv",
]
FINGERPRINT_GLOBS = [
    "config/*.yaml",
    "pipeline/**/*.py",
    "scripts/acceptance_check.py",
    "requirements.txt",
]
FINGERPRINT_FILES = [
    "data/verified/sync_log.jsonl",
]
COMMIT_PATHS = [
    "data/raw/sec",
    "data/verified/sync_log.jsonl",
    "data/raw/prices/corporate_actions.csv",
    "data/raw/prices/nasdaq",
    "data/raw/prices/alphavantage",
    "data/verified/company_financials.csv",
    "data/verified/segment_financials.csv",
    "data/verified/manifest.json",
    "data/verified/link_report.json",
    "data/verified/reconcile_report.json",
    "data/verified/quality_report.json",
    "data/verified/ai_events_report.json",
    "web/public/data",
    "docs/evidence",
    ".github/aicor_fingerprint",
    ".github/aicor_last_commit",
]


def _normalized_csv_digest(path: Path) -> str:
    rows: list[str] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            clean = {key: value for key, value in row.items() if key not in VOLATILE_COLUMNS}
            rows.append(json.dumps(clean, sort_keys=True, ensure_ascii=False, separators=(",", ":")))
    rows.sort()
    digest = hashlib.sha256()
    for line in rows:
        digest.update(line.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iter_code_files() -> Iterable[Path]:
    seen: set[Path] = set()
    for pattern in FINGERPRINT_GLOBS:
        for path in sorted(ROOT.glob(pattern)):
            if path.is_file() and path not in seen:
                seen.add(path)
                yield path


def compute_fingerprint() -> str:
    digest = hashlib.sha256()
    for relative in FINGERPRINT_CSV:
        path = ROOT / relative
        if not path.exists():
            digest.update(f"csv:{relative}:missing\n".encode("utf-8"))
            continue
        digest.update(f"csv:{relative}:{_normalized_csv_digest(path)}\n".encode("utf-8"))
    for path in _iter_code_files():
        relative = path.relative_to(ROOT).as_posix()
        digest.update(f"code:{relative}:{_file_digest(path)}\n".encode("utf-8"))
    for relative in FINGERPRINT_FILES:
        path = ROOT / relative
        if path.exists():
            digest.update(f"file:{relative}:{_file_digest(path)}\n".encode("utf-8"))
        else:
            digest.update(f"file:{relative}:missing\n".encode("utf-8"))
    return digest.hexdigest()


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.strip() + "\n", encoding="utf-8", newline="\n")


def _emit_output(name: str, value: str) -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if not output:
        return
    with open(output, "a", encoding="utf-8") as handle:
        handle.write(f"{name}={value}\n")


def _run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True)
    if check and result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(args)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def _snapshot_version() -> str:
    manifest = ROOT / "web" / "public" / "data" / "manifest.json"
    if not manifest.exists():
        return "unknown"
    try:
        return json.loads(manifest.read_text(encoding="utf-8")).get("snapshot_version", "unknown")
    except (OSError, json.JSONDecodeError):
        return "unknown"


def check() -> int:
    current = compute_fingerprint()
    saved = _read_text(FINGERPRINT_PATH)
    changed = current != saved
    _emit_output("changed", "true" if changed else "false")
    print(f"fingerprint current={current}")
    print(f"fingerprint saved={saved or '(missing)'}")
    print("semantic data changed" if changed else "no semantic data change")
    return 0


def commit(*, force: bool) -> int:
    current = compute_fingerprint()
    saved = _read_text(FINGERPRINT_PATH)
    if current == saved and not force:
        print("no semantic data change; nothing to commit")
        return 0

    today = datetime.now(timezone.utc).date().isoformat()
    last_commit = _read_text(LAST_COMMIT_PATH)
    if last_commit == today and not force:
        print(f"a data commit already happened on {today}; waiting for the next UTC day")
        return 0

    _write_text(FINGERPRINT_PATH, current)
    _write_text(LAST_COMMIT_PATH, today)

    paths = [path for path in COMMIT_PATHS if (ROOT / path).exists()]
    _run(["git", "config", "user.name", "github-actions[bot]"])
    _run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"])
    _run(["git", "add", "--", *paths])
    staged = _run(["git", "diff", "--cached", "--quiet"], check=False)
    if staged.returncode == 0:
        print("no staged changes after fingerprint update")
        return 0

    message = f"chore(data): refresh snapshot {_snapshot_version()} ({today} UTC) [skip ci]"
    _run(["git", "commit", "-m", message])
    print(message)

    for attempt in range(1, 4):
        pushed = _run(["git", "push", "origin", "HEAD:main"], check=False)
        if pushed.returncode == 0:
            print("pushed data commit")
            return 0
        print(f"push attempt {attempt} failed:\n{pushed.stderr.strip()}", file=sys.stderr)
        if attempt == 3:
            break
        rebased = _run(["git", "pull", "--rebase", "origin", "main"], check=False)
        if rebased.returncode != 0:
            _run(["git", "rebase", "--abort"], check=False)
            print(f"rebase failed:\n{rebased.stderr.strip()}", file=sys.stderr)
            break
    print("could not push data commit", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Report whether semantic data changed")
    mode.add_argument("--commit", action="store_true", help="Commit and push if changed and due")
    parser.add_argument("--force", action="store_true", help="Ignore the once-per-UTC-day gate")
    args = parser.parse_args(argv)
    if args.check:
        return check()
    return commit(force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
