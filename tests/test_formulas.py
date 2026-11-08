"""Financial formula tests from SPEC Appendix B.3."""

import pytest

from pipeline.metrics.formulas import (
    effective_tax_rate,
    free_cash_flow,
    fcf_margin,
    invested_capital,
    net_profit_margin,
    nopat,
    operating_margin,
    pe_trailing,
    rd_intensity,
    revenue_growth_yoy,
    roe,
    roic,
    trailing_eps,
)
from pipeline.preprocess.facts import MetricValue

from tests.helpers import make_metric


def metrics(**values: float | None) -> dict[str, MetricValue]:
    return {name: make_metric(value) for name, value in values.items()}


def test_growth_and_margin_formulas():
    rows = [{"metrics": metrics(revenue=100.0)}] * 4 + [{"metrics": metrics(revenue=120.0)}]
    assert revenue_growth_yoy(rows, 4) == pytest.approx(0.2)
    assert operating_margin(metrics(revenue=1000.0, operating_income=250.0)) == pytest.approx(0.25)
    assert net_profit_margin(metrics(revenue=1000.0, net_income=180.0)) == pytest.approx(0.18)
    assert rd_intensity(metrics(revenue=1000.0, rd_expense=150.0)) == pytest.approx(0.15)


def test_fcf_and_margin():
    current = metrics(revenue=1000.0, cfo=300.0, capex=100.0)
    assert free_cash_flow(current) == 200.0
    assert fcf_margin(current) == pytest.approx(0.2)


def test_tax_rate_is_clamped_and_nopat_uses_it():
    taxed = metrics(operating_income=200.0, income_tax_expense=300.0, pretax_income=100.0)
    assert effective_tax_rate(taxed) == 0.5
    assert nopat(taxed) == 100.0

    negative = metrics(operating_income=200.0, income_tax_expense=-10.0, pretax_income=100.0)
    assert effective_tax_rate(negative) == 0.0
    assert nopat(negative) == 200.0


def test_invested_capital_and_roic_use_cash_and_short_term_investments():
    current = metrics(
        operating_income=300.0,
        income_tax_expense=60.0,
        pretax_income=300.0,
        total_debt=400.0,
        total_equity=1000.0,
        cash_and_st_investments=200.0,
    )
    prior = metrics(total_debt=300.0, total_equity=900.0, cash_and_st_investments=150.0)
    assert invested_capital(current) == 1200.0
    profit = nopat(current)
    expected = profit / ((1200.0 + invested_capital(prior)) / 2)
    assert roic(current, prior) == pytest.approx(expected)


def test_roe_uses_average_equity():
    current = metrics(net_income=120.0, total_equity=1000.0)
    prior = metrics(total_equity=800.0)
    assert roe(current, prior) == pytest.approx(120.0 / 900.0)


def test_trailing_eps_and_pe():
    rows = [
        {"metrics": metrics(eps_diluted=1.0)},
        {"metrics": metrics(eps_diluted=1.2)},
        {"metrics": metrics(eps_diluted=1.4)},
        {"metrics": metrics(eps_diluted=1.6)},
    ]
    assert trailing_eps(rows, 3) == pytest.approx(5.2)
    assert pe_trailing(52.0, 5.2) == pytest.approx(10.0)
    assert pe_trailing(52.0, None) is None
    assert pe_trailing(52.0, -1.0) is None
