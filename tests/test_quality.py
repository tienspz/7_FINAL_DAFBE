"""Quality report aggregation tests."""

import pytest

from pipeline.verify.quality import build_quality_report

from tests.helpers import make_metric, make_quarter, make_settings


def test_quality_summary_counts_missing_low_and_verified_cells():
    settings = make_settings({"MSFT": {}})
    quarter = make_quarter("2025-Q1")
    row = {
        "calendar_key": quarter.key,
        "period_end": "2025-03-31",
        "fiscal_year": 2025,
        "fiscal_quarter": "Q3",
        "metrics": {
            "revenue": make_metric(100_000_000.0, quality="ok", verified=True),
            "capex": make_metric(20_000_000.0, quality="low", verified=True),
            "cfo": make_metric(None, quality="missing", verified=False),
        },
    }

    report = build_quality_report(
        settings=settings,
        quarters=[quarter],
        rows_by_ticker={"MSFT": [row]},
        facts=[],
        segment_rows=[],
        snapshot_version="vtest",
    )

    summary = report["summary"]
    assert summary["quarters_expected_per_company"] == 1
    assert summary["quarters_expected_total"] == 1
    assert summary["quarters_present"] == 1
    assert summary["missing_metric_cells"] == 1
    assert summary["low_metric_cells"] == 1
    assert summary["verified_ratio"] == pytest.approx(2 / 3)
    assert report["companies"][0]["quarters"][0]["metrics"]["revenue"]["value"] == 100.0


def test_quality_report_flags_missing_quarter():
    settings = make_settings({"MSFT": {}})
    report = build_quality_report(
        settings=settings,
        quarters=[make_quarter("2025-Q1")],
        rows_by_ticker={"MSFT": []},
        facts=[],
        segment_rows=[],
        snapshot_version="vtest",
    )
    assert report["summary"]["quarters_present"] == 0
    assert report["summary"]["missing_metric_cells"] == 1
    assert report["companies"][0]["quarters"][0]["missing"] is True
