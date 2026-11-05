"""BT1-BT5 statistical tests with small-n warnings."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.regression.linear_model import OLS
from statsmodels.tools import add_constant
from statsmodels.tsa.stattools import adfuller


def holm_adjust(p_values: list[float]) -> list[float]:
    if not p_values:
        return []
    order = sorted(range(len(p_values)), key=lambda index: p_values[index])
    adjusted = [1.0] * len(p_values)
    running = 0.0
    count = len(p_values)
    for rank, index in enumerate(order):
        value = min(1.0, (count - rank) * p_values[index])
        running = max(running, value)
        adjusted[index] = running
    return adjusted


def _result(
    *,
    bt_code: str,
    test_name: str,
    statistic: float | None,
    p_value: float | None,
    n: int,
    alpha: float,
    note: str = "",
    **extra: Any,
) -> dict[str, Any]:
    return {
        "bt_code": bt_code,
        "test_name": test_name,
        "statistic": statistic,
        "p_value": p_value,
        "p_adjusted": None,
        "n": n,
        "alpha": alpha,
        "decision": "reject_h0" if p_value is not None and p_value < alpha else "fail_to_reject_h0",
        "note": note,
        **extra,
    }


def bt1_excess_returns(
    *,
    price_analytics: dict[str, Any],
    tickers: list[str],
    benchmark: str,
    alpha: float,
) -> list[dict[str, Any]]:
    if benchmark not in price_analytics:
        return []
    benchmark_monthly = {
        row["trade_date"]: row["return"] for row in price_analytics[benchmark].get("monthly_returns", [])
    }
    results: list[dict[str, Any]] = []
    for ticker in tickers:
        if ticker not in price_analytics:
            continue
        stock_monthly = {
            row["trade_date"]: row["return"] for row in price_analytics[ticker].get("monthly_returns", [])
        }
        dates = sorted(set(stock_monthly) & set(benchmark_monthly))
        if len(dates) < 8:
            continue
        excess = np.array([stock_monthly[date] - benchmark_monthly[date] for date in dates], dtype=float)
        t_stat, t_p = stats.ttest_1samp(excess, 0.0)
        try:
            w_stat, w_p = stats.wilcoxon(excess, zero_method="wilcox")
        except ValueError:
            w_stat, w_p = None, None
        results.append(
            _result(
                bt_code="BT1",
                test_name=f"{ticker} monthly excess return vs {benchmark}",
                statistic=float(t_stat),
                p_value=float(t_p),
                n=len(dates),
                alpha=alpha,
                note="n >= 30 expected for monthly returns",
                wilcoxon_statistic=float(w_stat) if w_stat is not None else None,
                wilcoxon_p_value=float(w_p) if w_p is not None else None,
                mean_excess_return=float(excess.mean()),
                benchmark=benchmark,
            )
        )
    return results


def _aligned_series(
    rows_by_ticker: dict[str, list[dict[str, Any]]],
    ticker_a: str,
    ticker_b: str,
    field: str,
) -> tuple[list[str], np.ndarray, np.ndarray]:
    a = {row["calendar_key"]: row["derived"].get(field) for row in rows_by_ticker.get(ticker_a, [])}
    b = {row["calendar_key"]: row["derived"].get(field) for row in rows_by_ticker.get(ticker_b, [])}
    keys = sorted(key for key in set(a) & set(b) if a[key] is not None and b[key] is not None)
    return keys, np.array([a[key] for key in keys], dtype=float), np.array([b[key] for key in keys], dtype=float)


def bt2_paired_growth(
    *,
    rows_by_ticker: dict[str, list[dict[str, Any]]],
    tickers: list[str],
    alpha: float,
) -> list[dict[str, Any]]:
    if len(tickers) < 2:
        return []
    results: list[dict[str, Any]] = []
    for field, label in [("revenue_growth_yoy", "Revenue growth YoY"), ("net_income_growth_yoy", "Net income growth YoY")]:
        keys, a, b = _aligned_series(rows_by_ticker, tickers[0], tickers[1], field)
        if len(keys) < 4:
            continue
        stat, p_value = stats.ttest_rel(a, b)
        results.append(
            _result(
                bt_code="BT2",
                test_name=f"{label}: {tickers[0]} vs {tickers[1]}",
                statistic=float(stat),
                p_value=float(p_value),
                n=len(keys),
                alpha=alpha,
                note="paired quarters; n is small",
                mean_difference=float((a - b).mean()),
                quarters=keys,
            )
        )
    return results


def _adf(series: pd.Series) -> dict[str, Any]:
    clean = series.dropna().astype(float)
    if len(clean) < 8:
        return {"statistic": None, "p_value": None, "stationary": None, "transformation": "insufficient_n"}
    try:
        stat, p_value, *_ = adfuller(clean, regression="c", autolag="AIC")
        if p_value <= 0.05:
            return {"statistic": float(stat), "p_value": float(p_value), "stationary": True, "transformation": "level"}
        diff = clean.diff().dropna()
        stat_d, p_d, *_ = adfuller(diff, regression="c", autolag="AIC")
        return {
            "statistic": float(stat_d),
            "p_value": float(p_d),
            "stationary": bool(p_d <= 0.05),
            "transformation": "first_difference",
        }
    except Exception as exc:  # noqa: BLE001
        return {"statistic": None, "p_value": None, "stationary": None, "transformation": f"error: {exc}"}


def bt3_trend(
    *,
    rows_by_ticker: dict[str, list[dict[str, Any]]],
    alpha: float,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for ticker, rows in rows_by_ticker.items():
        ordered = sorted(rows, key=lambda row: row["calendar_key"])
        for field in ["rd_intensity", "capex_intensity"]:
            values = pd.Series([row["derived"].get(field) for row in ordered], dtype=float)
            valid = values.dropna()
            if len(valid) < 8:
                continue
            x = add_constant(np.arange(len(valid), dtype=float))
            model = OLS(valid.to_numpy(), x).fit(cov_type="HAC", cov_kwds={"maxlags": 4})
            adf = _adf(valid)
            results.append(
                _result(
                    bt_code="BT3",
                    test_name=f"{ticker} {field} linear trend (HAC)",
                    statistic=float(model.tvalues[1]),
                    p_value=float(model.pvalues[1]),
                    n=len(valid),
                    alpha=alpha,
                    note="HAC Newey-West maxlags=4; ADF result attached",
                    coefficient=float(model.params[1]),
                    r_squared=float(model.rsquared),
                    adf=adf,
                )
            )
    return results


def _correlation_family(
    *,
    bt_code: str,
    rows_by_ticker: dict[str, list[dict[str, Any]]],
    x_field: str,
    y_fields: list[str],
    max_lag: int,
    alpha: float,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for ticker, rows in rows_by_ticker.items():
        ordered = sorted(rows, key=lambda row: row["calendar_key"])
        frame = pd.DataFrame(
            {
                "x": [row["derived"].get(x_field) for row in ordered],
                **{field: [row["derived"].get(field) for row in ordered] for field in y_fields},
            },
            dtype=float,
        )
        for field in y_fields:
            for lag in range(max_lag + 1):
                pair = pd.DataFrame({"x": frame["x"], "y": frame[field].shift(-lag)}).dropna()
                if len(pair) < 5:
                    continue
                r, p_value = stats.spearmanr(pair["x"], pair["y"])
                results.append(
                    _result(
                        bt_code=bt_code,
                        test_name=f"{ticker} {x_field} vs {field} lag {lag}",
                        statistic=float(r),
                        p_value=float(p_value),
                        n=len(pair),
                        alpha=alpha,
                        note="Spearman; n < 30: reference only" if len(pair) < 30 else "Spearman",
                        ticker=ticker,
                        x=x_field,
                        y=field,
                        lag=lag,
                        method="spearman",
                    )
                )
    p_values = [item["p_value"] for item in results]
    for item, adjusted in zip(results, holm_adjust(p_values)):
        item["p_adjusted"] = adjusted
        item["decision"] = "reject_h0" if adjusted < alpha else "fail_to_reject_h0"
    return results


def run_all_tests(
    *,
    rows_by_ticker: dict[str, list[dict[str, Any]]],
    price_analytics: dict[str, Any],
    tickers: list[str],
    alpha: float,
    max_lag: int,
) -> dict[str, Any]:
    bt1 = bt1_excess_returns(price_analytics=price_analytics, tickers=tickers, benchmark="SPY", alpha=alpha)
    bt2 = bt2_paired_growth(rows_by_ticker=rows_by_ticker, tickers=tickers, alpha=alpha)
    bt3 = bt3_trend(rows_by_ticker=rows_by_ticker, alpha=alpha)
    bt4 = _correlation_family(
        bt_code="BT4",
        rows_by_ticker=rows_by_ticker,
        x_field="rd_growth_yoy",
        y_fields=["revenue_growth_yoy", "fcf_growth_yoy", "operating_margin"],
        max_lag=max_lag,
        alpha=alpha,
    )
    bt4 += _correlation_family(
        bt_code="BT4",
        rows_by_ticker=rows_by_ticker,
        x_field="capex_growth_yoy",
        y_fields=["revenue_growth_yoy", "fcf_growth_yoy", "operating_margin"],
        max_lag=max_lag,
        alpha=alpha,
    )
    bt5 = _correlation_family(
        bt_code="BT5",
        rows_by_ticker=rows_by_ticker,
        x_field="revenue_growth_yoy",
        y_fields=["stock_return_quarter"],
        max_lag=max_lag,
        alpha=alpha,
    )
    return {
        "schema_version": "1.0",
        "alpha": alpha,
        "warnings": [
            "BT4/BT5 have 11-15 observations at lags 0-4; results are reference only.",
            "Correlation does not imply causation.",
        ],
        "results": bt1 + bt2 + bt3 + bt4 + bt5,
    }
