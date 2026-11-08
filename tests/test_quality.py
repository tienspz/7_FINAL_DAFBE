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


def test_quality_report_lists_excluded_quarters_with_reasons():
    settings = make_settings({"MSFT": {}})
    quarter = make_quarter("2025-Q1")
    row = {
        "calendar_key": quarter.key,
        "period_end": "2025-03-31",
        "fiscal_year": 2025,
        "fiscal_quarter": "Q3",
        "metrics": {
            "revenue": make_metric(100_000_000.0, quality="ok"),
            "capex": make_metric(20_000_000.0, quality="low", reason="YTD Q2 minus Q1"),
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
    assert report["summary"]["excluded_quarters"] == 1
    excluded = report["excluded_quarters"][0]
    assert excluded["calendar_key"] == "2025-Q1"
    assert excluded["metrics"][0]["metric"] == "capex"
    assert "YTD" in excluded["metrics"][0]["reason"]


def test_net_income_bridge_flags_nonoperating_gains_from_sec_facts():
    from pipeline.verify.quality import build_net_income_bridge
    from tests.helpers import make_fact

    settings = make_settings(
        {"GOOGL": {}},
        diagnostic_tags={
            "GOOGL": {
                "nonoperating_income": {"kind": "flow", "unit": "USD", "tags": [{"tag": "NonoperatingIncomeExpense"}]},
                "unrealized_equity_gains": {"kind": "flow", "unit": "USD", "tags": [{"tag": "EquitySecuritiesFvNiUnrealizedGainLoss"}]},
            }
        },
    )
    facts = [
        make_fact(ticker="GOOGL", metric="operating_income", tag="OperatingIncomeLoss", start="2026-01-01", end="2026-03-31", period_type="quarter", value=39_696_000_000.0),
        make_fact(ticker="GOOGL", metric="nonoperating_income", tag="NonoperatingIncomeExpense", start="2026-01-01", end="2026-03-31", period_type="quarter", value=37_716_000_000.0),
        make_fact(ticker="GOOGL", metric="pretax_income", tag="PretaxIncome", start="2026-01-01", end="2026-03-31", period_type="quarter", value=77_412_000_000.0),
        make_fact(ticker="GOOGL", metric="income_tax_expense", tag="IncomeTaxExpenseBenefit", start="2026-01-01", end="2026-03-31", period_type="quarter", value=14_834_000_000.0),
        make_fact(ticker="GOOGL", metric="net_income", tag="NetIncomeLoss", start="2026-01-01", end="2026-03-31", period_type="quarter", value=62_578_000_000.0),
        make_fact(ticker="GOOGL", metric="unrealized_equity_gains", tag="EquitySecuritiesFvNiUnrealizedGainLoss", start="2026-01-01", end="2026-03-31", period_type="quarter", value=105_000_000.0),
    ]
    bridge = build_net_income_bridge(facts=facts, expected_keys=["2026-Q1"], settings=settings)
    quarter = bridge["companies"][0]["quarters"][0]
    assert quarter["calendar_key"] == "2026-Q1"
    assert quarter["nonoperating_share_of_pretax"] == pytest.approx(0.4872, abs=1e-4)
    assert quarter["one_off_flag"] is True
    assert quarter["net_income_musd"] == pytest.approx(62_578.0)
