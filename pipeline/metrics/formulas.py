"""Financial formulas from SPEC Appendix B.3."""

from __future__ import annotations

from typing import Any


def _value(metrics: dict[str, Any], name: str) -> float | None:
    metric = metrics.get(name)
    if metric is None:
        return None
    if hasattr(metric, "value"):
        return metric.value
    if isinstance(metric, dict):
        return metric.get("value")
    return None


def _safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _growth(current: float | None, prior: float | None) -> float | None:
    if current is None or prior in (None, 0):
        return None
    return current / prior - 1.0


def revenue_growth_yoy(rows: list[dict[str, Any]], index: int) -> float | None:
    if index < 4:
        return None
    current = _value(rows[index]["metrics"], "revenue")
    prior = _value(rows[index - 4]["metrics"], "revenue")
    return _growth(current, prior)


def operating_margin(metrics: dict[str, Any]) -> float | None:
    return _safe_div(_value(metrics, "operating_income"), _value(metrics, "revenue"))


def net_profit_margin(metrics: dict[str, Any]) -> float | None:
    return _safe_div(_value(metrics, "net_income"), _value(metrics, "revenue"))


def rd_intensity(metrics: dict[str, Any]) -> float | None:
    return _safe_div(_value(metrics, "rd_expense"), _value(metrics, "revenue"))


def capex_intensity(metrics: dict[str, Any]) -> float | None:
    return _safe_div(_value(metrics, "capex"), _value(metrics, "revenue"))


def free_cash_flow(metrics: dict[str, Any]) -> float | None:
    cfo = _value(metrics, "cfo")
    capex = _value(metrics, "capex")
    if cfo is None or capex is None:
        return None
    return cfo - capex


def fcf_margin(metrics: dict[str, Any]) -> float | None:
    return _safe_div(free_cash_flow(metrics), _value(metrics, "revenue"))


def effective_tax_rate(metrics: dict[str, Any]) -> float | None:
    tax = _value(metrics, "income_tax_expense")
    pretax = _value(metrics, "pretax_income")
    rate = _safe_div(tax, pretax)
    if rate is None:
        return None
    return min(max(rate, 0.0), 0.5)


def invested_capital(metrics: dict[str, Any]) -> float | None:
    debt = _value(metrics, "total_debt")
    equity = _value(metrics, "total_equity")
    cash = _value(metrics, "cash_and_st_investments")
    if debt is None or equity is None or cash is None:
        return None
    return debt + equity - cash


def nopat(metrics: dict[str, Any]) -> float | None:
    operating_income = _value(metrics, "operating_income")
    tax_rate = effective_tax_rate(metrics)
    if operating_income is None or tax_rate is None:
        return None
    return operating_income * (1.0 - tax_rate)


def average_two(current: float | None, prior: float | None) -> float | None:
    if current is None or prior is None:
        return None
    return (current + prior) / 2.0


def roe(metrics: dict[str, Any], prior_metrics: dict[str, Any] | None) -> float | None:
    net_income = _value(metrics, "net_income")
    equity = _value(metrics, "total_equity")
    prior_equity = _value(prior_metrics or {}, "total_equity")
    average = average_two(equity, prior_equity)
    return _safe_div(net_income, average)


def roic(metrics: dict[str, Any], prior_metrics: dict[str, Any] | None) -> float | None:
    profit = nopat(metrics)
    capital = invested_capital(metrics)
    prior_capital = invested_capital(prior_metrics or {})
    average = average_two(capital, prior_capital)
    return _safe_div(profit, average)


def trailing_eps(rows: list[dict[str, Any]], index: int) -> float | None:
    if index < 3:
        return None
    values = [_value(rows[index - offset]["metrics"], "eps_diluted") for offset in range(4)]
    if any(value is None for value in values):
        return None
    return float(sum(values))


def pe_trailing(price: float | None, eps: float | None) -> float | None:
    if price is None or eps is None or eps <= 0:
        return None
    return price / eps


def enrich_company_rows(
    *,
    ticker: str,
    rows: list[dict[str, Any]],
    price_analytics: dict[str, Any],
) -> list[dict[str, Any]]:
    quarter_returns = {
        item["calendar_key"]: item["return"] for item in price_analytics.get("quarterly_returns", [])
    }
    quarter_ends = price_analytics.get("quarter_end", {})
    for index, row in enumerate(rows):
        metrics = row["metrics"]
        prior_metrics = rows[index - 1]["metrics"] if index > 0 else None
        derived: dict[str, Any] = {}
        derived["revenue_growth_yoy"] = revenue_growth_yoy(rows, index)
        derived["operating_margin"] = operating_margin(metrics)
        derived["net_profit_margin"] = net_profit_margin(metrics)
        derived["rd_intensity"] = rd_intensity(metrics)
        derived["capex_intensity"] = capex_intensity(metrics)
        derived["fcf"] = free_cash_flow(metrics)
        derived["fcf_margin"] = fcf_margin(metrics)
        derived["effective_tax_rate"] = effective_tax_rate(metrics)
        derived["nopat"] = nopat(metrics)
        derived["invested_capital"] = invested_capital(metrics)
        derived["roe"] = roe(metrics, prior_metrics)
        derived["roic"] = roic(metrics, prior_metrics)
        derived["eps_trailing_4q"] = trailing_eps(rows, index)
        price_row = quarter_ends.get(row["calendar_key"])
        price = price_row["adj_close"] if price_row else None
        derived["price_quarter_end"] = price
        derived["pe_trailing"] = pe_trailing(price, derived["eps_trailing_4q"])
        derived["stock_return_quarter"] = quarter_returns.get(row["calendar_key"])
        if index >= 4:
            derived["net_income_growth_yoy"] = _growth(
                _value(metrics, "net_income"), _value(rows[index - 4]["metrics"], "net_income")
            )
            derived["rd_growth_yoy"] = _growth(
                _value(metrics, "rd_expense"), _value(rows[index - 4]["metrics"], "rd_expense")
            )
            derived["capex_growth_yoy"] = _growth(
                _value(metrics, "capex"), _value(rows[index - 4]["metrics"], "capex")
            )
            prior_fcf = free_cash_flow(rows[index - 4]["metrics"])
            derived["fcf_growth_yoy"] = _growth(derived["fcf"], prior_fcf)
        else:
            derived["net_income_growth_yoy"] = None
            derived["rd_growth_yoy"] = None
            derived["capex_growth_yoy"] = None
            derived["fcf_growth_yoy"] = None
        row["derived"] = derived
        row["ticker"] = ticker
    return rows
