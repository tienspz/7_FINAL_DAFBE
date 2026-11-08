"""Regression coverage for semantic snapshot publishing."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from scripts import ci_sync_data


def _configure_fixture(monkeypatch, tmp_path: Path) -> Path:
    data_file = tmp_path / "data" / "semantic.csv"
    data_file.parent.mkdir(parents=True)
    data_file.write_text("symbol,value\nAICOR,1\n", encoding="utf-8")
    monkeypatch.setattr(ci_sync_data, "ROOT", tmp_path)
    monkeypatch.setattr(ci_sync_data, "FINGERPRINT_PATH", tmp_path / ".github" / "aicor_fingerprint")
    monkeypatch.setattr(ci_sync_data, "LAST_COMMIT_PATH", tmp_path / ".github" / "aicor_last_commit")
    monkeypatch.setattr(ci_sync_data, "FINGERPRINT_CSV", ["data/semantic.csv"])
    monkeypatch.setattr(ci_sync_data, "FINGERPRINT_GLOBS", [])
    monkeypatch.setattr(
        ci_sync_data,
        "COMMIT_PATHS",
        ["data/semantic.csv", ".github/aicor_fingerprint", ".github/aicor_last_commit"],
    )
    return data_file


def test_changed_semantic_data_is_committed_even_if_today_already_has_commit(monkeypatch, tmp_path):
    data_file = _configure_fixture(monkeypatch, tmp_path)
    ci_sync_data._write_text(ci_sync_data.FINGERPRINT_PATH, ci_sync_data.compute_fingerprint())
    today = datetime.now(timezone.utc).date().isoformat()
    ci_sync_data._write_text(ci_sync_data.LAST_COMMIT_PATH, today)
    data_file.write_text("symbol,value\nAICOR,2\n", encoding="utf-8")

    commands: list[list[str]] = []

    def fake_run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        return subprocess.CompletedProcess(args, 1 if args[:3] == ["git", "diff", "--cached"] else 0, "", "")

    monkeypatch.setattr(ci_sync_data, "_run", fake_run)

    assert ci_sync_data.commit(force=False) == 0
    assert ["git", "commit", "-m", f"chore(data): refresh snapshot unknown ({today} UTC) [skip ci]"] in commands
    assert ["git", "push", "origin", "HEAD:main"] in commands
    assert ci_sync_data._read_text(ci_sync_data.LAST_COMMIT_PATH) == today


def test_unchanged_semantic_data_does_not_create_a_commit(monkeypatch, tmp_path):
    _configure_fixture(monkeypatch, tmp_path)
    fingerprint = ci_sync_data.compute_fingerprint()
    ci_sync_data._write_text(ci_sync_data.FINGERPRINT_PATH, fingerprint)

    def unexpected_run(*args, **kwargs):
        raise AssertionError("git should not run when semantic data is unchanged")

    monkeypatch.setattr(ci_sync_data, "_run", unexpected_run)

    assert ci_sync_data.commit(force=False) == 0


def test_sync_log_metadata_does_not_change_semantic_fingerprint(monkeypatch, tmp_path):
    _configure_fixture(monkeypatch, tmp_path)
    monkeypatch.setattr(ci_sync_data, "FINGERPRINT_CSV", [])
    log = tmp_path / "data" / "verified" / "sync_log.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text('{"run_id":"run-one","fetched_at":"2026-11-08T10:00:00Z"}\n', encoding="utf-8")
    before = ci_sync_data.compute_fingerprint()

    log.write_text('{"run_id":"run-two","fetched_at":"2026-11-08T11:00:00Z"}\n', encoding="utf-8")

    assert ci_sync_data.compute_fingerprint() == before
