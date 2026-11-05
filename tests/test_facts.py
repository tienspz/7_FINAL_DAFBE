"""Quarterly fact selection, YTD conversion, Q4 derivation, and tag switches."""

import pytest

from pipeline.preprocess.facts import build_company_quarters

from tests.helpers import make_fact, make_quarter, make_settings


REVENUE = {
    "revenue": {
        "kind": "flow",
        "unit": "USD",
        "tags": [{"tag": "RevenueFromContractWithCustomerExcludingAssessedTax"}],
    }
}


def test_msft_fiscal_q4_is_annual_minus_fiscal_q1_q3():
    settings = make_settings({"MSFT": REVENUE})
    facts = [
        make_fact(ticker="MSFT", metric="revenue", tag="Revenue", start="2025-07-01", end="2025-09-30", period_type="quarter", value=100.0),
        make_fact(ticker="MSFT", metric="revenue", tag="Revenue", start="2025-10-01", end="2025-12-31", period_type="quarter", value=110.0),
        make_fact(ticker="MSFT", metric="revenue", tag="Revenue", start="2026-01-01", end="2026-03-31", period_type="quarter", value=120.0),
        make_fact(ticker="MSFT", metric="revenue", tag="Revenue", start="2025-07-01", end="2026-06-30", period_type="annual", value=500.0, form="10-K"),
    ]

    rows = build_company_quarters(
        ticker="MSFT",
        facts=facts,
        settings=settings,
        quarters=[make_quarter("2026-Q2")],
    )

    revenue = rows[0]["metrics"]["revenue"]
    assert revenue.value == 170.0
    assert revenue.derived is True
    assert revenue.quality_flag == "ok"
    assert rows[0]["fiscal_year"] == 2026
    assert rows[0]["fiscal_quarter"] == "Q4"
    assert "residual 0.0000%" in revenue.reason


def test_googl_ytd_q2_and_q3_are_converted_to_quarters():
    settings = make_settings({"GOOGL": REVENUE})
    facts = [
        make_fact(ticker="GOOGL", metric="revenue", tag="Revenue", start="2025-01-01", end="2025-03-31", period_type="quarter", value=100.0),
        make_fact(ticker="GOOGL", metric="revenue", tag="Revenue", start="2025-01-01", end="2025-06-30", period_type="ytd", value=220.0),
        make_fact(ticker="GOOGL", metric="revenue", tag="Revenue", start="2025-01-01", end="2025-09-30", period_type="ytd", value=360.0),
    ]

    rows = build_company_quarters(
        ticker="GOOGL",
        facts=facts,
        settings=settings,
        quarters=[make_quarter("2025-Q2"), make_quarter("2025-Q3")],
    )

    q2 = rows[0]["metrics"]["revenue"]
    q3 = rows[1]["metrics"]["revenue"]
    assert q2.value == 120.0
    assert q2.derived is True
    assert q2.quality_flag == "low"
    assert "YTD Q2 minus Q1" == q2.reason
    assert q3.value == 140.0
    assert q3.derived is True
    assert q3.quality_flag == "low"
    assert "YTD Q3 minus Q1 and Q2" == q3.reason


def test_revenue_tag_switch_is_flagged_at_transition():
    settings = make_settings({"GOOGL": REVENUE})
    facts = [
        make_fact(
            ticker="GOOGL",
            metric="revenue",
            tag="RevenueFromContractWithCustomerExcludingAssessedTax",
            start="2025-01-01",
            end="2025-03-31",
            period_type="quarter",
            value=100.0,
        ),
        make_fact(
            ticker="GOOGL",
            metric="revenue",
            tag="Revenues",
            start="2025-04-01",
            end="2025-06-30",
            period_type="quarter",
            value=110.0,
        ),
    ]

    rows = build_company_quarters(
        ticker="GOOGL",
        facts=facts,
        settings=settings,
        quarters=[make_quarter("2025-Q1"), make_quarter("2025-Q2")],
    )

    assert rows[0]["metrics"]["revenue"].tag_switch is False
    transition = rows[1]["metrics"]["revenue"]
    assert transition.tag_switch is True
    assert transition.quality_flag == "low"
    assert "XBRL tag switch" in transition.reason


def test_total_debt_sums_components_and_falls_back_to_total_tag():
    definitions = {
        "total_debt": {
            "kind": "instant",
            "unit": "USD",
            "aggregation": "sum",
            "tags": [{"tag": "LongTermDebtCurrent"}, {"tag": "LongTermDebtNoncurrent"}],
            "fallback_tags": [{"tag": "LongTermDebt"}],
        }
    }
    settings = make_settings({"GOOGL": definitions})
    quarter = make_quarter("2025-Q1")

    summed_facts = [
        make_fact(ticker="GOOGL", metric="total_debt", tag="LongTermDebtCurrent", start="", end="2025-03-31", period_type="instant", value=200.0),
        make_fact(ticker="GOOGL", metric="total_debt", tag="LongTermDebtNoncurrent", start="", end="2025-03-31", period_type="instant", value=300.0),
    ]
    summed = build_company_quarters(ticker="GOOGL", facts=summed_facts, settings=settings, quarters=[quarter])
    assert summed[0]["metrics"]["total_debt"].value == 500.0
    assert summed[0]["metrics"]["total_debt"].quality_flag == "ok"

    fallback_facts = [
        make_fact(ticker="GOOGL", metric="total_debt", tag="LongTermDebt", start="", end="2025-03-31", period_type="instant", value=450.0),
    ]
    fallback = build_company_quarters(ticker="GOOGL", facts=fallback_facts, settings=settings, quarters=[quarter])
    debt = fallback[0]["metrics"]["total_debt"]
    assert debt.value == 450.0
    assert debt.quality_flag == "low"
    assert debt.reason == "fallback total-debt tag used"


def test_missing_q4_annual_fact_is_marked_missing():
    settings = make_settings({"MSFT": REVENUE})
    rows = build_company_quarters(
        ticker="MSFT",
        facts=[],
        settings=settings,
        quarters=[make_quarter("2024-Q2")],
    )
    revenue = rows[0]["metrics"]["revenue"]
    assert revenue.value is None
    assert revenue.quality_flag == "missing"
    assert "no 10-K annual fact" in revenue.reason


def test_googl_pre_split_eps_is_adjusted_but_reported_value_preserved():
    definitions = {
        "eps_diluted": {
            "kind": "flow",
            "unit": "USD/shares",
            "tags": [{"tag": "EarningsPerShareDiluted"}],
        }
    }
    settings = make_settings(
        {"GOOGL": definitions},
        split_adjustments={
            "GOOGL": {
                "eps_diluted": {
                    "split_date": "2022-07-18",
                    "ratio": 20,
                    "adjust_period_end_before": "2022-06-30",
                }
            }
        },
    )
    facts = [
        make_fact(
            ticker="GOOGL",
            metric="eps_diluted",
            tag="EarningsPerShareDiluted",
            start="2022-01-01",
            end="2022-03-31",
            period_type="quarter",
            value=24.62,
            unit="USD/shares",
        ),
        make_fact(
            ticker="GOOGL",
            metric="eps_diluted",
            tag="EarningsPerShareDiluted",
            start="2022-04-01",
            end="2022-06-30",
            period_type="quarter",
            value=1.21,
            filed="2022-07-26",
            unit="USD/shares",
        ),
    ]

    rows = build_company_quarters(
        ticker="GOOGL",
        facts=facts,
        settings=settings,
        quarters=[make_quarter("2022-Q1"), make_quarter("2022-Q2")],
    )

    q1 = rows[0]["metrics"]["eps_diluted"]
    assert q1.value == pytest.approx(1.231)
    assert q1.reported_value == pytest.approx(24.62)
    assert q1.split_adjustment == 20
    assert q1.quality_flag == "low"
    assert "split-adjusted 20:1" in q1.reason
    payload = q1.to_dict()
    assert payload["value"] == pytest.approx(1.231)
    assert payload["reported_value"] == pytest.approx(24.62)
    assert payload["split_adjustment"] == 20
    assert payload["unit"] == "USD/shares"

    # Q2 2022 was reported after the split and must not be divided again.
    q2 = rows[1]["metrics"]["eps_diluted"]
    assert q2.value == pytest.approx(1.21)
    assert q2.reported_value is None
    assert q2.split_adjustment is None
    assert q2.quality_flag == "ok"


def test_googl_q4_eps_subtracts_split_adjusted_quarters():
    definitions = {
        "eps_diluted": {
            "kind": "flow",
            "unit": "USD/shares",
            "tags": [{"tag": "EarningsPerShareDiluted"}],
        }
    }
    settings = make_settings(
        {"GOOGL": definitions},
        split_adjustments={
            "GOOGL": {
                "eps_diluted": {
                    "split_date": "2022-07-18",
                    "ratio": 20,
                    "adjust_period_end_before": "2022-06-30",
                }
            }
        },
    )
    facts = [
        make_fact(ticker="GOOGL", metric="eps_diluted", tag="EarningsPerShareDiluted", start="2022-01-01", end="2022-03-31", period_type="quarter", value=24.62, unit="USD/shares"),
        make_fact(ticker="GOOGL", metric="eps_diluted", tag="EarningsPerShareDiluted", start="2022-04-01", end="2022-06-30", period_type="quarter", value=1.21, unit="USD/shares"),
        make_fact(ticker="GOOGL", metric="eps_diluted", tag="EarningsPerShareDiluted", start="2022-07-01", end="2022-09-30", period_type="quarter", value=1.06, unit="USD/shares"),
        make_fact(ticker="GOOGL", metric="eps_diluted", tag="EarningsPerShareDiluted", start="2022-01-01", end="2022-12-31", period_type="annual", value=4.56, filed="2023-02-03", form="10-K", unit="USD/shares"),
    ]

    rows = build_company_quarters(
        ticker="GOOGL",
        facts=facts,
        settings=settings,
        quarters=[
            make_quarter("2022-Q1"),
            make_quarter("2022-Q2"),
            make_quarter("2022-Q3"),
            make_quarter("2022-Q4"),
        ],
    )

    q4 = rows[3]["metrics"]["eps_diluted"]
    assert q4.value == pytest.approx(4.56 - 1.231 - 1.21 - 1.06)
    assert q4.value > 0
    assert q4.derived is True
    assert q4.quality_flag == "ok"
    assert "residual 0.0000%" in q4.reason
    assert sum(row["metrics"]["eps_diluted"].value for row in rows) == pytest.approx(4.56)
