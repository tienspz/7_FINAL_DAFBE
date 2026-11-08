import sqlite3
from datetime import date

import pytest

from scripts.acceptance_check import (
    check_sqlite_handoff,
    latest_completed_price_row,
    manifest_checksum,
    sha256_bytes,
)


def test_latest_completed_price_row_skips_the_current_incomplete_session():
    rows = [
        {"date": "2026-11-03", "close": 100.0},
        {"date": "2026-11-04", "close": 101.0},
        {"date": "2026-11-05", "close": 102.0},
    ]

    assert latest_completed_price_row(rows, today=date(2026, 11, 5)) == rows[1]


def test_latest_completed_price_row_fails_without_a_completed_session():
    with pytest.raises(ValueError, match="no completed trading date"):
        latest_completed_price_row(
            [{"date": "2026-11-05", "close": 102.0}], today=date(2026, 11, 5)
        )


def test_manifest_checksum_normalizes_windows_json_line_endings(tmp_path):
    path = tmp_path / "dashboard.json"
    canonical = b'{\n  "snapshot_version": "v1"\n}\n'
    path.write_bytes(canonical.replace(b"\n", b"\r\n"))

    assert manifest_checksum(path) == "sha256:" + sha256_bytes(canonical)


def test_sqlite_handoff_requires_manifest_metadata_match(tmp_path):
    database_path = tmp_path / "aicor.sqlite"
    manifest = {
        "schema_version": "1.0",
        "run_id": "run_current",
        "snapshot_version": "v20261107.1",
        "data_as_of": "2026-11-07",
        "generated_at": "2026-11-07T10:00:00Z",
        "row_counts": {
            "facts": 1,
            "filings": 1,
            "segments": 1,
            "financial_quarters": 38,
            "prices": 1,
        },
    }
    with sqlite3.connect(database_path) as connection:
        for table in ("facts", "filings", "segments", "company_financials", "prices"):
            connection.execute(f"CREATE TABLE {table} (value TEXT)")
            connection.execute(f"INSERT INTO {table} VALUES ('row')")
        connection.executemany(
            "INSERT INTO company_financials VALUES (?)",
            [("row",)] * 37,
        )
        connection.execute(
            "CREATE TABLE handoff_metadata (schema_version TEXT, run_id TEXT, "
            "snapshot_version TEXT, data_as_of TEXT, generated_at TEXT)"
        )
        connection.execute(
            "INSERT INTO handoff_metadata VALUES "
            "('1.0', 'run_previous', 'v20261107.1', '2026-11-07', '2026-11-07T10:00:00Z')"
        )

    passed, detail = check_sqlite_handoff(database_path, manifest)

    assert not passed
    assert "run_id" in detail

    with sqlite3.connect(database_path) as connection:
        connection.execute("DELETE FROM handoff_metadata")
        connection.execute(
            "INSERT INTO handoff_metadata VALUES "
            "('1.0', 'run_current', 'v20261107.1', '2026-11-07', '2026-11-07T10:00:00Z')"
        )

    passed, detail = check_sqlite_handoff(database_path, manifest)

    assert passed
    assert "run_current" in detail
