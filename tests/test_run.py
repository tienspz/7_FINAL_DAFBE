import sqlite3

import pandas as pd
import pytest

from pipeline.run import build_sqlite, original_fact_filing_references, write_csv


def test_write_csv_uses_lf_line_endings(tmp_path):
    csv_path = tmp_path / "facts.csv"
    write_csv(csv_path, [{"fact_id": "f1", "value": 1.0}])

    content = csv_path.read_bytes()
    assert b"\r\n" not in content
    assert content == b"fact_id,value\nf1,1.0\n"


def test_original_fact_filing_references_include_historical_filings_once():
    facts = [
        {
            "is_original": True,
            "source_url": "https://www.sec.gov/Archives/edgar/data/1/old/",
            "accession_number": "old-accession",
            "period_end": "2009-09-30",
        },
        {
            "is_original": True,
            "source_url": "https://www.sec.gov/Archives/edgar/data/1/old/",
            "accession_number": "old-accession",
            "period_end": "2009-06-30",
        },
        {
            "is_original": False,
            "source_url": "https://www.sec.gov/Archives/edgar/data/1/unneeded/",
            "accession_number": "unneeded-accession",
            "period_end": "2009-09-30",
        },
    ]

    assert original_fact_filing_references(facts) == [
        {
            "source_url": "https://www.sec.gov/Archives/edgar/data/1/old/",
            "accession_number": "old-accession",
            "report_date": "2009-09-30",
        }
    ]


def test_build_sqlite_keeps_previous_database_when_staging_write_fails(tmp_path, monkeypatch):
    database_path = tmp_path / "aicor.sqlite"
    connection = sqlite3.connect(database_path)
    with connection:
        connection.execute("CREATE TABLE preserved (value TEXT NOT NULL)")
        connection.execute("INSERT INTO preserved VALUES ('previous handoff')")
    connection.close()

    def fail_write(*args, **kwargs):
        raise RuntimeError("simulated SQLite staging failure")

    monkeypatch.setattr(pd.DataFrame, "to_sql", fail_write)

    with pytest.raises(RuntimeError, match="simulated SQLite staging failure"):
        build_sqlite(
            db_path=database_path,
            facts_rows=[{"fact_id": "new-fact"}],
            filing_rows_data=[],
            segment_rows=[],
            financial_rows=[],
            prices=pd.DataFrame(),
        )

    connection = sqlite3.connect(database_path)
    with connection:
        row = connection.execute("SELECT value FROM preserved").fetchone()
    connection.close()
    assert row == ("previous handoff",)
    assert sorted(path.name for path in tmp_path.iterdir()) == ["aicor.sqlite"]


def test_build_sqlite_replaces_handoff_with_expected_tables(tmp_path):
    database_path = tmp_path / "aicor.sqlite"
    build_sqlite(
        db_path=database_path,
        facts_rows=[{"fact_id": "new-fact"}],
        filing_rows_data=[{"accession_number": "new-filing"}],
        segment_rows=[{"segment_name": "cloud"}],
        financial_rows=[{"calendar_key": "2025-Q1"}],
        prices=pd.DataFrame([{"ticker": "MSFT"}]),
    )

    connection = sqlite3.connect(database_path)
    with connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in tables
        }
    connection.close()
    assert tables == {"facts", "filings", "segments", "company_financials", "prices"}
    assert all(count == 1 for count in counts.values())
