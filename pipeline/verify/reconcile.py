"""Reconciliation checks for quarterly facts, prices, and segments."""

from __future__ import annotations

from datetime import date
from typing import Any

from pipeline.config import Settings
from pipeline.metrics.formulas import free_cash_flow
from pipeline.util import parse_date


def _check(name: str, status: str, detail: str, **extra: Any) -> dict[str, Any]:
    return {"check": name, "status": status, "detail": detail, **extra}


def _previous_quarter(qkey: str) -> str:
    year, q = qkey.split("-Q")
    q_num = int(q)
    if q_num == 1:
        return f"{int(year) - 1}-Q4"
    return f"{year}-Q{q_num - 1}"


def reconcile_financials(
    *,
    rows_by_ticker: dict[str, list[dict[str, Any]]],
    facts: list[dict[str, Any]],
    settings: Settings,
    snapshot_date: date,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for ticker, rows in rows_by_ticker.items():
        for row in rows:
            for metric_name in ("revenue", "rd_expense", "capex"):
                metric = row["metrics"].get(metric_name)
                if metric and metric.value is not None and metric.value < 0:
                    checks.append(
                        _check(
                            "negative_value",
                            "fail",
                            f"{ticker} {row['calendar_key']} {metric_name} is negative",
                            ticker=ticker,
                            quarter=row["calendar_key"],
                            metric=metric_name,
                            value=metric.value,
                        )
                    )
            for metric_name, metric in row["metrics"].items():
                if metric and metric.value is not None and metric.unit not in {"USD", "USD/shares"}:
                    checks.append(
                        _check(
                            "unit",
                            "fail",
                            f"{ticker} {row['calendar_key']} {metric_name} has unit {metric.unit}",
                            ticker=ticker,
                            quarter=row["calendar_key"],
                            metric=metric_name,
                        )
                    )
            cfo = row["metrics"].get("cfo")
            capex = row["metrics"].get("capex")
            if cfo and capex and cfo.value is not None and capex.value is not None:
                expected = free_cash_flow(row["metrics"])
                actual = row["derived"].get("fcf")
                if expected is None or actual is None or abs(expected - actual) > 1.0:
                    checks.append(
                        _check(
                            "fcf_identity",
                            "fail",
                            f"{ticker} {row['calendar_key']} FCF identity failed",
                            ticker=ticker,
                            quarter=row["calendar_key"],
                        )
                    )
            period_end = parse_date(row.get("period_end"))
            filed_dates = [
                parse_date(metric.filed_date)
                for metric in row["metrics"].values()
                if metric and metric.filed_date
            ]
            if period_end and filed_dates:
                lag = (max(filed_dates) - period_end).days
                if lag > settings.thresholds["quality"]["filing_lag_days"]:
                    checks.append(
                        _check(
                            "filing_lag",
                            "low",
                            f"{ticker} {row['calendar_key']} filing lag {lag} days",
                            ticker=ticker,
                            quarter=row["calendar_key"],
                            lag_days=lag,
                        )
                    )
                if max(filed_dates) > snapshot_date:
                    checks.append(
                        _check(
                            "future_data",
                            "fail",
                            f"{ticker} {row['calendar_key']} has a future filing date",
                            ticker=ticker,
                            quarter=row["calendar_key"],
                        )
                    )

        # Q4 residual: compare the derived Q4 plus fiscal Q1-Q3 with the 10-K annual fact.
        for row in rows:
            if row.get("fiscal_quarter") != "Q4":
                continue
            annual_facts = [
                fact
                for fact in facts
                if fact.get("ticker") == ticker
                and fact.get("metric") == "revenue"
                and fact.get("period_type") == "annual"
                and fact.get("calendar_key") == row["calendar_key"]
                and fact.get("is_original")
            ]
            if not annual_facts:
                continue
            annual = float(annual_facts[0]["value_usd"])
            prev1 = _previous_quarter(row["calendar_key"])
            prev2 = _previous_quarter(prev1)
            prev3 = _previous_quarter(prev2)
            q_values = []
            for qkey in (prev3, prev2, prev1):
                prior = next((candidate for candidate in rows if candidate["calendar_key"] == qkey), None)
                metric = prior["metrics"].get("revenue") if prior else None
                q_values.append(metric.value if metric else None)
            q4_metric = row["metrics"].get("revenue")
            if q4_metric and q4_metric.value is not None and all(value is not None for value in q_values):
                residual = abs((sum(q_values) + q4_metric.value) - annual) / abs(annual) if annual else 0.0
                status = "ok" if residual <= settings.thresholds["quality"]["q4_residual_ok"] else (
                    "low" if residual <= settings.thresholds["quality"]["q4_residual_low"] else "fail"
                )
                checks.append(
                    _check(
                        "q4_residual",
                        status,
                        f"{ticker} {row['calendar_key']} Q4 residual {residual:.4%}",
                        ticker=ticker,
                        quarter=row["calendar_key"],
                        residual=residual,
                    )
                )
    return checks


def reconcile_segments(
    *,
    segment_rows: list[dict[str, Any]],
    settings: Settings,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for row in segment_rows:
        diff = row.get("segment_sum_diff")
        if diff is None:
            continue
        group_key = (
            row["ticker"],
            row["calendar_key"],
            row["segment_scheme"],
            row["metric"],
        )
        if group_key in seen:
            continue
        seen.add(group_key)
        if diff > settings.thresholds["quality"]["segment_sum_tolerance"]:
            checks.append(
                _check(
                    "segment_sum",
                    "low",
                    f"{row['ticker']} {row['calendar_key']} {row['segment_scheme']} {row['metric']} sum diff {diff:.4%}",
                    ticker=row["ticker"],
                    quarter=row["calendar_key"],
                    scheme=row["segment_scheme"],
                )
            )
    return checks


def reconcile_prices(
    *,
    price_analytics: dict[str, Any],
    settings: Settings,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for ticker, analytics in price_analytics.items():
        if not analytics.get("rows"):
            checks.append(_check("price_rows", "fail", f"{ticker} has no price rows", ticker=ticker))
        checks.append(
            _check(
                "secondary_close",
                "pending",
                f"{ticker}: Nasdaq API is outside the CR-13 allowlist; secondary close not run",
                ticker=ticker,
            )
        )
        checks.append(
            _check(
                "secondary_adjusted_close",
                "unverified",
                f"{ticker}: Alpha Vantage key not available; adjusted close cross-check not run",
                ticker=ticker,
            )
        )
    return checks
