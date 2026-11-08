"""Reconciliation checks for quarterly facts, prices, and segments."""

from __future__ import annotations

import random
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


def _compare_close_series(
    *,
    frame: Any,
    rows: list[dict[str, Any]],
    price_field: str,
    secondary_field: str,
    tolerance: float,
    min_days: int,
    sample_size: int | None = None,
    seed: int = 0,
) -> dict[str, Any] | None:
    """Compare two close series on a seeded random sample of trading days."""
    prices: dict[str, float] = {}
    for row in frame.itertuples():
        trade_date = getattr(row, "trade_date", None)
        value = getattr(row, price_field, None)
        if trade_date is None or value is None:
            continue
        key = trade_date.isoformat() if hasattr(trade_date, "isoformat") else str(trade_date)
        prices[key] = float(value)

    pairs: list[tuple[str, float, float]] = []
    for row in rows:
        trade_date = row.get("trade_date")
        source_value = row.get(secondary_field)
        if trade_date in prices and source_value is not None:
            pairs.append((trade_date, prices[trade_date], float(source_value)))
    pairs.sort()
    available = len(pairs)
    target = sample_size or min_days
    if available > target:
        pairs = sorted(random.Random(seed).sample(pairs, target))
    if not pairs:
        return None

    differences = [abs(price - source) / max(abs(source), 1e-9) for _, price, source in pairs]
    matched = sum(1 for difference in differences if difference <= tolerance)
    ratio = matched / len(differences)
    status = "ok" if matched == len(differences) and len(differences) >= min_days else (
        "low" if ratio >= 0.9 else "fail"
    )
    return {
        "status": status,
        "compared_days": len(differences),
        "available_days": available,
        "matched_days": matched,
        "max_relative_difference": max(differences),
        "window_start": pairs[0][0],
        "window_end": pairs[-1][0],
        "sample_method": "seeded_random" if available > target else "all_available",
        "sample_seed": seed,
    }


def reconcile_adjusted_selfcheck(
    *,
    selfchecks: dict[str, dict[str, Any]],
    settings: Settings,
) -> list[dict[str, Any]]:
    """Recompute adjusted close from close plus dividends and report deviation."""
    tolerance = float(
        settings.thresholds["quality"].get("adjusted_close_selfcheck_tolerance", 0.001)
    )
    checks: list[dict[str, Any]] = []
    for ticker, result in selfchecks.items():
        maximum = result.get("max_relative_difference")
        split_ok = result.get("split_continuity_ok") is not False
        status = "ok" if maximum is not None and maximum <= tolerance and split_ok else "fail"
        checks.append(
            _check(
                "adjusted_close_selfcheck",
                status,
                (
                    f"{ticker}: adjusted close recomputed from close + dividends; "
                    f"max relative difference {maximum:.6%} (tolerance {tolerance:.3%}); "
                    f"split continuity={result.get('split_continuity_ok')}"
                ),
                ticker=ticker,
                max_relative_difference=maximum,
                mean_relative_difference=result.get("mean_relative_difference"),
                tolerance=tolerance,
                dividend_events=result.get("dividend_events"),
                split_events=result.get("split_events"),
                split_continuity_ok=result.get("split_continuity_ok"),
                method=result.get("method"),
            )
        )
    return checks


def reconcile_prices(
    *,
    price_analytics: dict[str, Any],
    settings: Settings,
    prices_by_ticker: dict[str, Any] | None = None,
    secondary: dict[str, Any] | None = None,
    adjusted: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    quality = settings.thresholds["quality"]
    tolerance = float(quality["price_diff_tolerance"])
    adjusted_tolerance = float(quality.get("adjusted_close_diff_tolerance", tolerance))
    min_days = int(quality.get("min_price_days_for_reconciliation", 30))
    sample_size = int(quality.get("price_reconciliation_sample_size", min_days))
    seed = int(quality.get("price_sample_seed", 0))
    secondary = secondary or {}
    adjusted = adjusted or {}
    checks: list[dict[str, Any]] = []

    for ticker, analytics in price_analytics.items():
        if not analytics.get("rows"):
            checks.append(_check("price_rows", "fail", f"{ticker} has no price rows", ticker=ticker))
        frame = (prices_by_ticker or {}).get(ticker)
        artifact = (secondary.get("artifacts") or {}).get(ticker) or {}
        secondary_rows = (secondary.get("rows_by_ticker") or {}).get(ticker) or []
        error = (secondary.get("errors") or {}).get(ticker)

        comparison = (
            _compare_close_series(
                frame=frame,
                rows=secondary_rows,
                price_field="close",
                secondary_field="close",
                tolerance=tolerance,
                min_days=min_days,
                sample_size=sample_size,
                seed=seed,
            )
            if frame is not None and secondary_rows
            else None
        )
        if comparison:
            checks.append(
                _check(
                    "secondary_close",
                    comparison["status"],
                    (
                        f"{ticker}: {comparison['matched_days']}/{comparison['compared_days']} Nasdaq closes "
                        f"within {tolerance:.3%} (max {comparison['max_relative_difference']:.4%}); "
                        f"seeded random sample from {comparison['available_days']} available days"
                    ),
                    ticker=ticker,
                    compared_days=comparison["compared_days"],
                    available_days=comparison["available_days"],
                    matched_days=comparison["matched_days"],
                    max_relative_difference=comparison["max_relative_difference"],
                    window_start=comparison["window_start"],
                    window_end=comparison["window_end"],
                    sample_method=comparison["sample_method"],
                    sample_seed=comparison["sample_seed"],
                    source_url=artifact.get("source_url"),
                    response_sha256=artifact.get("response_sha256"),
                    artifact=artifact.get("path"),
                )
            )
        else:
            reason = f" ({error})" if error else ""
            checks.append(
                _check(
                    "secondary_close",
                    "pending",
                    f"{ticker}: Nasdaq secondary close not available{reason}",
                    ticker=ticker,
                    source_url=artifact.get("source_url"),
                    response_sha256=artifact.get("response_sha256"),
                )
            )

        adjusted_artifact = (adjusted.get("artifacts") or {}).get(ticker) or {}
        adjusted_rows = (adjusted.get("rows_by_ticker") or {}).get(ticker) or []
        provider = adjusted.get("provider", "external provider")
        adjusted_error = (adjusted.get("errors") or {}).get(ticker)
        adjusted_comparison = (
            _compare_close_series(
                frame=frame,
                rows=adjusted_rows,
                price_field="adj_close",
                secondary_field="adjusted_close",
                tolerance=adjusted_tolerance,
                min_days=min_days,
                sample_size=sample_size,
                seed=seed,
            )
            if frame is not None and adjusted.get("available") and adjusted_rows
            else None
        )
        if adjusted_comparison:
            checks.append(
                _check(
                    "secondary_adjusted_close",
                    adjusted_comparison["status"],
                    (
                        f"{ticker}: {adjusted_comparison['matched_days']}/{adjusted_comparison['compared_days']} "
                        f"{provider} adjusted closes within {adjusted_tolerance:.3%}"
                    ),
                    ticker=ticker,
                    compared_days=adjusted_comparison["compared_days"],
                    matched_days=adjusted_comparison["matched_days"],
                    max_relative_difference=adjusted_comparison["max_relative_difference"],
                    source_url=adjusted_artifact.get("source_url"),
                    response_sha256=adjusted_artifact.get("response_sha256"),
                )
            )
        else:
            reason = adjusted_error or adjusted.get("reason") or (
                f"{provider} adjusted-close cross-check was not run"
            )
            checks.append(
                _check(
                    "secondary_adjusted_close",
                    "unverified",
                    f"{ticker}: {reason}",
                    ticker=ticker,
                    source_url=adjusted_artifact.get("source_url"),
                    response_sha256=adjusted_artifact.get("response_sha256"),
                )
            )
    return checks
