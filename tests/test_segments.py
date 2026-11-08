"""Segment table, Q4 derivation, and reconciliation tests."""

from pipeline.preprocess.segments import build_segment_table
from pipeline.util import quarter_end
from pipeline.verify.reconcile import reconcile_segments

from tests.helpers import make_metric, make_quarter, make_settings


def segment_fact(
    *,
    segment_name: str,
    value: float,
    calendar_key: str,
    period_type: str = "quarter",
    ticker: str = "GOOGL",
    scheme: str = "goog_3",
    metric: str = "revenue",
) -> dict:
    end = quarter_end(calendar_key).isoformat()
    return {
        "ticker": ticker,
        "calendar_key": calendar_key,
        "period_end": end,
        "segment_scheme": scheme,
        "segment_name": segment_name,
        "segment_member": f"{segment_name}Member",
        "metric": metric,
        "value_usd": value,
        "period_type": period_type,
        "source_url": "https://www.sec.gov/example",
        "accession_number": "0000000000-25-000001",
        "form": "10-Q",
        "filed_date": "2025-02-01",
        "evidence_url": "https://www.sec.gov/example.xml",
    }


def consolidated_row(quarter_key: str, revenue: float, ticker: str = "GOOGL") -> dict:
    return {
        "ticker": ticker,
        "calendar_key": quarter_key,
        "metrics": {"revenue": make_metric(revenue)},
    }


def test_segment_table_derives_q4_and_computes_sum_difference():
    settings = make_settings({})
    quarters = [make_quarter("2025-Q1"), make_quarter("2025-Q2"), make_quarter("2025-Q3"), make_quarter("2025-Q4")]
    facts = [
        segment_fact(segment_name="A", value=100_000_000.0, calendar_key="2025-Q1"),
        segment_fact(segment_name="A", value=110_000_000.0, calendar_key="2025-Q2"),
        segment_fact(segment_name="A", value=120_000_000.0, calendar_key="2025-Q3"),
        segment_fact(segment_name="A", value=500_000_000.0, calendar_key="2025-Q4", period_type="annual"),
    ]
    rows = build_segment_table(
        segment_facts=facts,
        quarters=quarters,
        consolidated_rows=[consolidated_row("2025-Q4", 500_000_000.0)],
        settings=settings,
    )
    q4 = next(row for row in rows if row["calendar_key"] == "2025-Q4")
    assert q4["value_musd"] == 170.0
    assert q4["derived"] is True
    assert q4["quality_flag"] == "low"


def test_segment_sum_uses_all_segments_in_the_same_group():
    settings = make_settings({})
    quarter = make_quarter("2025-Q1")
    facts = [
        segment_fact(segment_name="Google Services", value=800_000_000.0, calendar_key="2025-Q1"),
        segment_fact(segment_name="Google Cloud", value=150_000_000.0, calendar_key="2025-Q1"),
        segment_fact(segment_name="Other Bets", value=50_000_000.0, calendar_key="2025-Q1"),
    ]
    rows = build_segment_table(
        segment_facts=facts,
        quarters=[quarter],
        consolidated_rows=[consolidated_row("2025-Q1", 1_000_000_000.0)],
        settings=settings,
    )
    assert all(row["segment_sum_diff"] == 0.0 for row in rows)
    assert all(row["quality_flag"] == "ok" for row in rows)


def test_msft_new_segments_are_marked_not_comparable():
    settings = make_settings({})
    quarter = make_quarter("2026-Q3")
    facts = [
        segment_fact(
            segment_name="Agents & Infrastructure",
            value=500_000_000.0,
            calendar_key="2026-Q3",
            ticker="MSFT",
            scheme="msft_new_2",
        ),
    ]
    rows = build_segment_table(
        segment_facts=facts,
        quarters=[quarter],
        consolidated_rows=[consolidated_row("2026-Q3", 500_000_000.0, ticker="MSFT")],
        settings=settings,
    )
    assert rows[0]["comparable"] is False


def test_segment_reconciliation_deduplicates_warning_per_group():
    settings = make_settings({})
    rows = [
        {"ticker": "GOOGL", "calendar_key": "2025-Q1", "segment_scheme": "goog_3", "metric": "revenue", "segment_sum_diff": 0.01},
        {"ticker": "GOOGL", "calendar_key": "2025-Q1", "segment_scheme": "goog_3", "metric": "revenue", "segment_sum_diff": 0.01},
        {"ticker": "GOOGL", "calendar_key": "2025-Q1", "segment_scheme": "goog_3", "metric": "revenue", "segment_sum_diff": 0.01},
    ]
    checks = reconcile_segments(segment_rows=rows, settings=settings)
    assert len(checks) == 1
    assert checks[0]["status"] == "low"


def test_msft_fiscal_q4_segment_is_derived_from_annual_fact():
    settings = make_settings({})
    quarters = [make_quarter(key) for key in ("2024-Q3", "2024-Q4", "2025-Q1", "2025-Q2")]
    facts = [
        segment_fact(
            segment_name="Intelligent Cloud",
            value=100_000_000.0,
            calendar_key="2024-Q3",
            ticker="MSFT",
            scheme="msft_legacy_3",
        ),
        segment_fact(
            segment_name="Intelligent Cloud",
            value=110_000_000.0,
            calendar_key="2024-Q4",
            ticker="MSFT",
            scheme="msft_legacy_3",
        ),
        segment_fact(
            segment_name="Intelligent Cloud",
            value=120_000_000.0,
            calendar_key="2025-Q1",
            ticker="MSFT",
            scheme="msft_legacy_3",
        ),
        segment_fact(
            segment_name="Intelligent Cloud",
            value=500_000_000.0,
            calendar_key="2025-Q2",
            period_type="annual",
            ticker="MSFT",
            scheme="msft_legacy_3",
        ),
    ]
    rows = build_segment_table(
        segment_facts=facts,
        quarters=quarters,
        consolidated_rows=[consolidated_row("2025-Q2", 170_000_000.0, ticker="MSFT")],
        settings=settings,
    )
    q4 = next(row for row in rows if row["calendar_key"] == "2025-Q2")
    assert q4["value_musd"] == 170.0
    assert q4["derived"] is True
    assert q4["fiscal_quarter"] == "Q4"
    assert q4["comparable"] is True
    assert q4["annual_value_musd"] == 500.0
