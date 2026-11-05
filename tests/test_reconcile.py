"""Reconciliation tests for fiscal Q4 and identity checks."""

from datetime import date

from pipeline.verify.reconcile import reconcile_financials

from tests.helpers import make_fact, make_metric, make_settings


def row(quarter: str, revenue: float) -> dict:
    return {
        "calendar_key": quarter,
        "period_end": None,
        "fiscal_quarter": None,
        "metrics": {"revenue": make_metric(revenue)},
        "derived": {"fcf": None},
    }


def test_msft_q4_residual_uses_fiscal_prior_quarters():
    settings = make_settings({"MSFT": {}})
    rows = {
        "MSFT": [
            row("2022-Q3", 100.0),
            row("2022-Q4", 110.0),
            row("2023-Q1", 120.0),
            row("2023-Q2", 170.0),
        ]
    }
    rows["MSFT"][3]["fiscal_quarter"] = "Q4"
    facts = [
        make_fact(
            ticker="MSFT",
            metric="revenue",
            tag="Revenue",
            start="2022-07-01",
            end="2023-06-30",
            period_type="annual",
            value=500.0,
            form="10-K",
        )
    ]

    checks = reconcile_financials(
        rows_by_ticker=rows,
        facts=facts,
        settings=settings,
        snapshot_date=date(2026, 11, 5),
    )

    q4_checks = [check for check in checks if check["check"] == "q4_residual"]
    assert len(q4_checks) == 1
    assert q4_checks[0]["status"] == "ok"
    assert q4_checks[0]["residual"] == 0.0


def test_fcf_identity_and_negative_revenue_are_checked():
    settings = make_settings({"MSFT": {}})
    rows = {
        "MSFT": [
            {
                "calendar_key": "2025-Q1",
                "period_end": None,
                "fiscal_quarter": "Q3",
                "metrics": {
                    "revenue": make_metric(-1.0),
                    "cfo": make_metric(100.0),
                    "capex": make_metric(30.0),
                },
                "derived": {"fcf": 70.0},
            }
        ]
    }
    checks = reconcile_financials(
        rows_by_ticker=rows,
        facts=[],
        settings=settings,
        snapshot_date=date(2026, 11, 5),
    )
    assert any(check["check"] == "negative_value" and check["status"] == "fail" for check in checks)
    assert not any(check["check"] == "fcf_identity" for check in checks)
