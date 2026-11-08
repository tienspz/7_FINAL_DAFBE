"""BT1-BT5 statistical tests with small-n warnings.

The module is the only place where hypothesis tests are computed (SPEC 3.8).
Quality filtering follows DR-04.8 / FR-52: in the default ``exclude_low`` mode
any observation whose underlying reported metrics are not ``quality_flag=ok``
is dropped and listed with its reason; ``label_low`` keeps it but records the
flag.  Stationarity follows FR-30a: every series used in a correlation is
ADF-tested, and both series are first-differenced when either fails at level.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.regression.linear_model import OLS
from statsmodels.tools import add_constant
from statsmodels.tsa.stattools import adfuller

QUALITY_MODE_EXCLUDE = "exclude_low"
QUALITY_MODE_LABEL = "label_low"
QUALITY_MODES = (QUALITY_MODE_EXCLUDE, QUALITY_MODE_LABEL)

# Metrics that must be usable for a derived field to be usable.
QUALITY_INPUTS: dict[str, tuple[str, ...]] = {
    "revenue_growth_yoy": ("revenue",),
    "net_income_growth_yoy": ("net_income",),
    "rd_growth_yoy": ("rd_expense",),
    "capex_growth_yoy": ("capex",),
    "fcf_growth_yoy": ("cfo", "capex"),
    "operating_margin": ("operating_income", "revenue"),
    "rd_intensity": ("rd_expense", "revenue"),
    "capex_intensity": ("capex", "revenue"),
    "stock_return_quarter": (),
}
GROWTH_FIELDS = {
    "revenue_growth_yoy",
    "net_income_growth_yoy",
    "rd_growth_yoy",
    "capex_growth_yoy",
    "fcf_growth_yoy",
}


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
    decision: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    if decision is None:
        decision = "reject_h0" if p_value is not None and p_value < alpha else "fail_to_reject_h0"
    return {
        "bt_code": bt_code,
        "test_name": test_name,
        "statistic": statistic,
        "p_value": p_value,
        "p_adjusted": None,
        "n": n,
        "alpha": alpha,
        "decision": decision,
        "note": note,
        **extra,
    }


def _metric_identity_ok(metric: Any) -> bool:
    """True only when a derived metric's SEC components reproduce its value."""
    method = getattr(metric, "derivation_method", None) or ""
    if not getattr(metric, "derived", False) or not method:
        return False
    value = metric.value
    if value is None:
        return False
    if getattr(metric, "unit", "") == "USD":
        value = value / 1_000_000.0
    roles = {
        component.get("role"): component.get("value")
        for component in (getattr(metric, "components", None) or [])
        if component.get("value") is not None
    }
    if method.startswith("YTD") and roles.get("ytd") is not None:
        residual = abs(roles["ytd"] - (sum(v for r, v in roles.items() if r != "ytd") + value))
    elif method.startswith("FY") and roles.get("annual") is not None:
        residual = abs(roles["annual"] - (sum(v for r, v in roles.items() if r != "annual") + value))
    else:
        return False
    return residual <= 0.01


def _quality_problem(row: dict[str, Any], field: str, mode: str) -> str | None:
    problems: list[str] = []
    for name in QUALITY_INPUTS.get(field, ()):
        metric = row.get("metrics", {}).get(name)
        if metric is None or metric.value is None:
            problems.append(f"{name} unavailable")
            continue
        if metric.quality_flag == "ok":
            continue
        if mode == QUALITY_MODE_LABEL and metric.derived and _metric_identity_ok(metric):
            continue
        problems.append(f"{name} quality_flag={metric.quality_flag}")
    return "; ".join(problems) if problems else None


def _field_quality_problem(
    rows: list[dict[str, Any]], index: int, field: str, mode: str
) -> str | None:
    """Quality reason for a derived value, including its t-4 YoY base."""
    if index < 0 or index >= len(rows):
        return None
    offsets = (0, 4) if field in GROWTH_FIELDS else (0,)
    problems: list[str] = []
    for offset in offsets:
        position = index - offset
        if position < 0:
            continue
        problem = _quality_problem(rows[position], field, mode)
        if problem:
            label = "current" if offset == 0 else "t-4"
            problems.append(f"{label}: {problem}")
    return "; ".join(problems) if problems else None


def _field_quality_label(rows: list[dict[str, Any]], index: int, field: str) -> str | None:
    """Low-quality label for an observation kept in mode B."""
    if index < 0 or index >= len(rows):
        return None
    offsets = (0, 4) if field in GROWTH_FIELDS else (0,)
    labels: list[str] = []
    for offset in offsets:
        position = index - offset
        if position < 0:
            continue
        for name in QUALITY_INPUTS.get(field, ()):
            metric = rows[position].get("metrics", {}).get(name)
            if metric is not None and metric.value is not None and metric.quality_flag != "ok":
                labels.append(
                    f"{'current' if offset == 0 else 't-4'}: {name} quality_flag={metric.quality_flag}"
                )
    return "; ".join(labels) if labels else None


def _masked_series(
    rows: list[dict[str, Any]], field: str, mode: str
) -> tuple[np.ndarray, list[str | None], list[str | None]]:
    values: list[float] = []
    statuses: list[str | None] = []
    labels: list[str | None] = []
    for index, row in enumerate(rows):
        value = row.get("derived", {}).get(field)
        values.append(math.nan if value is None else float(value))
        status = _field_quality_problem(rows, index, field, mode)
        statuses.append(status)
        labels.append(_field_quality_label(rows, index, field))
        if status and mode == QUALITY_MODE_EXCLUDE:
            values[-1] = math.nan
    return np.array(values, dtype=float), statuses, labels


def _quarter_shift(key: str, offset: int) -> str:
    year, quarter = key.split("-Q")
    total = int(year) * 4 + (int(quarter) - 1) + offset
    return f"{total // 4}-Q{total % 4 + 1}"


def bt1_excess_returns(
    *,
    price_analytics: dict[str, Any],
    tickers: list[str],
    benchmark: str,
    alpha: float,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    """Excess monthly returns over the analysis window.

    Monthly returns are trimmed to completed calendar months inside the
    analysis window (SPEC 3.1 / DR-01.3); the partial current month is never
    used.
    """
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
        dates = sorted(
            date
            for date in set(stock_monthly) & set(benchmark_monthly)
            if (start_date is None or date >= start_date)
            and (end_date is None or date <= end_date)
        )
        if len(dates) < 8:
            continue
        excess = np.array([stock_monthly[date] - benchmark_monthly[date] for date in dates], dtype=float)
        t_stat, t_p = stats.ttest_1samp(excess, 0.0)
        shapiro_stat, shapiro_p = (
            stats.shapiro(excess) if len(excess) >= 3 else (None, None)
        )
        use_wilcoxon = shapiro_p is not None and float(shapiro_p) < alpha
        wilcoxon_stat: float | None = None
        wilcoxon_p: float | None = None
        try:
            w_stat, w_p = stats.wilcoxon(excess, zero_method="wilcox")
            wilcoxon_stat, wilcoxon_p = float(w_stat), float(w_p)
        except ValueError:
            pass
        if use_wilcoxon and wilcoxon_p is not None:
            statistic, p_value, test_used = wilcoxon_stat, wilcoxon_p, "wilcoxon_signed_rank"
        else:
            statistic, p_value, test_used = float(t_stat), float(t_p), "one_sample_t"
        mean = float(excess.mean())
        standard_error = float(excess.std(ddof=1) / math.sqrt(len(excess))) if len(excess) > 1 else 0.0
        critical = float(stats.t.ppf(1 - alpha / 2, len(excess) - 1)) if len(excess) > 1 else 0.0
        results.append(
            _result(
                bt_code="BT1",
                test_name=f"{ticker} monthly excess return vs {benchmark}",
                statistic=statistic,
                p_value=p_value,
                n=len(dates),
                alpha=alpha,
                note=(
                    f"Window {dates[0]}..{dates[-1]} ({len(dates)} completed months, 2022-Q1 onward); "
                    f"Shapiro-Wilk p={shapiro_p:.4g}; test={test_used}; "
                    + ("n >= 30" if len(dates) >= 30 else "n < 30: reference only")
                ),
                window_start=dates[0],
                window_end=dates[-1],
                mean_excess_return=mean,
                ci_low=mean - critical * standard_error,
                ci_high=mean + critical * standard_error,
                shapiro_statistic=float(shapiro_stat) if shapiro_stat is not None else None,
                shapiro_p_value=float(shapiro_p) if shapiro_p is not None else None,
                test_used=test_used,
                wilcoxon_statistic=wilcoxon_stat,
                wilcoxon_p_value=wilcoxon_p,
                excluded_quarters=[],
                t_statistic=float(t_stat),
                t_p_value=float(t_p),
                benchmark=benchmark,
            )
        )
    return results


def _aligned_series(
    rows_by_ticker: dict[str, list[dict[str, Any]]],
    ticker_a: str,
    ticker_b: str,
    field: str,
    quality_mode: str,
) -> tuple[list[str], np.ndarray, np.ndarray, list[dict[str, Any]]]:
    rows_a = sorted(rows_by_ticker.get(ticker_a, []), key=lambda row: row["calendar_key"])
    rows_b = sorted(rows_by_ticker.get(ticker_b, []), key=lambda row: row["calendar_key"])
    index_a = {row["calendar_key"]: row for row in rows_a}
    index_b = {row["calendar_key"]: row for row in rows_b}
    problems: dict[str, str | None] = {}
    labels: dict[str, str | None] = {}
    for ticker, rows in ((ticker_a, rows_a), (ticker_b, rows_b)):
        for position, row in enumerate(rows):
            problem = _field_quality_problem(rows, position, field, quality_mode)
            if problem:
                problems[f"{ticker}|{row['calendar_key']}"] = problem
            label = _field_quality_label(rows, position, field)
            if label:
                labels[f"{ticker}|{row['calendar_key']}"] = label
    keys = sorted(
        key
        for key in set(index_a) & set(index_b)
        if index_a[key]["derived"].get(field) is not None
        and index_b[key]["derived"].get(field) is not None
        and not (
            quality_mode == QUALITY_MODE_EXCLUDE
            and (
                f"{ticker_a}|{key}" in problems
                or f"{ticker_b}|{key}" in problems
            )
        )
    )
    overlap = set(index_a) & set(index_b)
    excluded = [
        {
            "ticker": key.split("|")[0],
            "calendar_key": key.split("|")[1],
            "reason": reason,
        }
        for key, reason in sorted(problems.items())
        if key.split("|")[1] in overlap
    ]
    low_quality = [
        {
            "ticker": key.split("|")[0],
            "calendar_key": key.split("|")[1],
            "reason": reason,
        }
        for key, reason in sorted(labels.items())
        if key.split("|")[1] in overlap
    ]
    return (
        keys,
        np.array([index_a[key]["derived"][field] for key in keys], dtype=float),
        np.array([index_b[key]["derived"][field] for key in keys], dtype=float),
        excluded,
        low_quality,
    )


def _paired_test(
    *,
    a: np.ndarray,
    b: np.ndarray,
    alpha: float,
) -> dict[str, Any]:
    difference = a - b
    stat, p_value = stats.ttest_rel(a, b)
    shapiro_stat, shapiro_p = (
        stats.shapiro(difference) if len(difference) >= 3 else (None, None)
    )
    use_wilcoxon = shapiro_p is not None and float(shapiro_p) < alpha
    wilcoxon_stat: float | None = None
    wilcoxon_p: float | None = None
    try:
        w_stat, w_p = stats.wilcoxon(difference, zero_method="wilcox")
        wilcoxon_stat, wilcoxon_p = float(w_stat), float(w_p)
    except ValueError:
        pass
    if use_wilcoxon and wilcoxon_p is not None:
        chosen_stat, chosen_p, test_used = wilcoxon_stat, wilcoxon_p, "wilcoxon_signed_rank"
    else:
        chosen_stat, chosen_p, test_used = float(stat), float(p_value), "paired_t"
    mean = float(difference.mean())
    standard_error = (
        float(difference.std(ddof=1) / math.sqrt(len(difference))) if len(difference) > 1 else 0.0
    )
    critical = (
        float(stats.t.ppf(1 - alpha / 2, len(difference) - 1)) if len(difference) > 1 else 0.0
    )
    return {
        "statistic": chosen_stat,
        "p_value": chosen_p,
        "test_used": test_used,
        "t_statistic": float(stat),
        "t_p_value": float(p_value),
        "shapiro_statistic": float(shapiro_stat) if shapiro_stat is not None else None,
        "shapiro_p_value": float(shapiro_p) if shapiro_p is not None else None,
        "wilcoxon_statistic": wilcoxon_stat,
        "wilcoxon_p_value": wilcoxon_p,
        "mean_difference": mean,
        "ci_low": mean - critical * standard_error,
        "ci_high": mean + critical * standard_error,
    }


def bt2_paired_growth(
    *,
    rows_by_ticker: dict[str, list[dict[str, Any]]],
    tickers: list[str],
    alpha: float,
    quality_mode: str = QUALITY_MODE_EXCLUDE,
    one_off_quarters: dict[str, dict[str, str]] | None = None,
    label_suffix: str = "",
    fields: list[tuple[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Paired company comparison. Shapiro-Wilk decides t-test vs Wilcoxon."""
    if len(tickers) < 2:
        return []
    results: list[dict[str, Any]] = []
    fields = fields or [
        ("revenue_growth_yoy", "Revenue growth YoY"),
        ("net_income_growth_yoy", "Net income growth YoY"),
    ]
    for field, label in fields:
        keys, a, b, excluded, low_quality = _aligned_series(
            rows_by_ticker, tickers[0], tickers[1], field, quality_mode
        )
        one_off_removed: list[dict[str, Any]] = []
        if one_off_quarters:
            keep: list[int] = []
            for position, key in enumerate(keys):
                hit = None
                for ticker in tickers:
                    mapping = one_off_quarters.get(ticker, {})
                    for candidate in (key, _quarter_shift(key, -4)):
                        if candidate in mapping:
                            hit = {
                                "ticker": ticker,
                                "calendar_key": candidate,
                                "reason": mapping[candidate],
                            }
                            break
                    if hit:
                        break
                if hit:
                    one_off_removed.append(hit)
                else:
                    keep.append(position)
            keys = [keys[position] for position in keep]
            a = a[keep]
            b = b[keep]
        if len(keys) < 4:
            results.append(
                _result(
                    bt_code="BT2",
                    test_name=f"{label}{label_suffix}: {tickers[0]} vs {tickers[1]}",
                    statistic=None,
                    p_value=None,
                    n=len(keys),
                    alpha=alpha,
                    decision="insufficient_data",
                    note="fewer than 4 paired quarters after quality filtering; no test run",
                    quarters=keys,
                    excluded_quarters=excluded + one_off_removed,
                    low_quality_quarters=low_quality,
                    quality_mode=quality_mode,
                )
            )
            continue
        outcome = _paired_test(a=a, b=b, alpha=alpha)
        note = (
            f"paired quarters; Shapiro-Wilk p={outcome['shapiro_p_value']:.4g}; "
            f"decision rule: Wilcoxon when Shapiro p<{alpha}, else paired t-test; "
            f"test={outcome['test_used']}; n is small"
        )
        if label_suffix:
            note += "; one-off non-operating quarters removed from both sides (see evidence)"
        results.append(
            _result(
                bt_code="BT2",
                test_name=f"{label}{label_suffix}: {tickers[0]} vs {tickers[1]}",
                statistic=outcome["statistic"],
                p_value=outcome["p_value"],
                n=len(keys),
                alpha=alpha,
                note=note,
                quarters=keys,
                excluded_quarters=excluded + one_off_removed,
                low_quality_quarters=low_quality,
                quality_mode=quality_mode,
                **{
                    name: value
                    for name, value in outcome.items()
                    if name not in {"statistic", "p_value"}
                },
            )
        )
    return results


def _adf(series: pd.Series | np.ndarray) -> dict[str, Any]:
    """ADF at level; report the first difference when the level is not stationary."""
    clean = (
        series.dropna().astype(float)
        if isinstance(series, pd.Series)
        else pd.Series(series).dropna().astype(float)
    )
    base = {
        "n": int(len(clean)),
        "regression": "c",
        "autolag": "AIC",
        "statistic": None,
        "p_value": None,
        "stationary": None,
        "transformation": "insufficient_n",
        "level_statistic": None,
        "level_p_value": None,
        "level_stationary": None,
        "differenced_statistic": None,
        "differenced_p_value": None,
        "differenced_stationary": None,
    }
    if len(clean) < 8:
        return base
    try:
        level_stat, level_p, *_ = adfuller(clean, regression="c", autolag="AIC")
        base["level_statistic"] = float(level_stat)
        base["level_p_value"] = float(level_p)
        base["level_stationary"] = bool(level_p <= 0.05)
        if level_p <= 0.05:
            base.update(
                statistic=float(level_stat),
                p_value=float(level_p),
                stationary=True,
                transformation="level",
            )
            return base
        diff = clean.diff().dropna()
        stat_d, p_d, *_ = adfuller(diff, regression="c", autolag="AIC")
        base.update(
            statistic=float(stat_d),
            p_value=float(p_d),
            stationary=bool(p_d <= 0.05),
            transformation="first_difference",
            differenced_statistic=float(stat_d),
            differenced_p_value=float(p_d),
            differenced_stationary=bool(p_d <= 0.05),
        )
        return base
    except Exception as exc:  # noqa: BLE001
        base["transformation"] = f"error: {exc}"
        return base


def _moving_block_bootstrap_p(
    values: np.ndarray,
    positions: np.ndarray,
    *,
    iterations: int,
    block_length: int,
    seed: int,
) -> float | None:
    """Residual moving-block bootstrap p-value for a linear trend under H0."""
    y = np.asarray(values, dtype=float)
    x = np.asarray(positions, dtype=float)
    if len(y) < 8 or iterations < 1:
        return None
    design = add_constant(x)
    observed = float(OLS(y, design).fit().params[1])
    residuals = y - y.mean()
    n = len(residuals)
    block = max(1, min(int(block_length), n))
    starts_needed = math.ceil(n / block)
    rng = np.random.default_rng(seed)
    exceed = 0
    for _ in range(iterations):
        starts = rng.integers(0, n - block + 1, size=starts_needed)
        indices = np.concatenate([np.arange(start, start + block) for start in starts])[:n]
        simulated = y.mean() + residuals[indices]
        slope = float(OLS(simulated, design).fit().params[1])
        if abs(slope) >= abs(observed) - 1e-12:
            exceed += 1
    return (exceed + 1) / (iterations + 1)


def bt3_trend(
    *,
    rows_by_ticker: dict[str, list[dict[str, Any]]],
    alpha: float,
    quality_mode: str = QUALITY_MODE_EXCLUDE,
    bootstrap_iterations: int = 1000,
    block_length: int = 4,
    bootstrap_seed: int = 20261107,
) -> list[dict[str, Any]]:
    """Trend on level (HAC) and drift on first differences, reported separately."""
    results: list[dict[str, Any]] = []
    for ticker, rows in rows_by_ticker.items():
        ordered = sorted(rows, key=lambda row: row["calendar_key"])
        for field in ["rd_intensity", "capex_intensity"]:
            values, statuses, labels = _masked_series(ordered, field, quality_mode)
            valid_positions = [index for index, value in enumerate(values) if not math.isnan(value)]
            valid = np.array([values[index] for index in valid_positions], dtype=float)
            excluded = [
                {
                    "ticker": ticker,
                    "calendar_key": ordered[index]["calendar_key"],
                    "reason": statuses[index],
                }
                for index, status in enumerate(statuses)
                if status
            ]
            low_quality = [
                {
                    "ticker": ticker,
                    "calendar_key": ordered[index]["calendar_key"],
                    "reason": labels[index],
                }
                for index, label in enumerate(labels)
                if label
            ]
            adf = _adf(valid)
            unreliable = (
                adf.get("level_stationary") is False
                and adf.get("differenced_stationary") is False
            )
            note_parts = [
                "HAC Newey-West maxlags=4",
                f"ADF level p={adf['level_p_value']}; first-difference p={adf['differenced_p_value']}; "
                f"used={adf['transformation']}",
                f"n_effective={len(valid)}",
            ]
            if len(valid) <= 20:
                note_parts.append("p-value tiệm cận, chỉ tham khảo")
            if unreliable:
                note_parts.append(
                    f"{ticker} {field} is non-stationary after first differencing; "
                    "trend p-values are unreliable and excluded from conclusions"
                )
            if len(valid) < 8:
                results.append(
                    _result(
                        bt_code="BT3",
                        test_name=f"{ticker} {field} linear trend (HAC)",
                        statistic=None,
                        p_value=None,
                        n=len(valid),
                        alpha=alpha,
                        decision="insufficient_data",
                        note="; ".join(note_parts + ["fewer than 8 usable quarters; no trend test"]),
                        adf=adf,
                        excluded_quarters=excluded,
                        low_quality_quarters=low_quality,
                        quality_mode=quality_mode,
                        n_effective=len(valid),
                        trend_on_level=None,
                        drift_on_difference=None,
                        unreliable_nonstationary=unreliable,
                    )
                )
                continue
            positions = np.array(valid_positions, dtype=float)
            level_design = add_constant(positions)
            level_model = OLS(valid, level_design).fit(cov_type="HAC", cov_kwds={"maxlags": 4})
            level_p = float(level_model.pvalues[1])
            bootstrap_p = _moving_block_bootstrap_p(
                valid,
                positions,
                iterations=bootstrap_iterations,
                block_length=block_length,
                seed=bootstrap_seed + len(valid) + len(results),
            )
            differences = np.diff(valid)
            drift_model = OLS(differences, np.ones((len(differences), 1))).fit(
                cov_type="HAC", cov_kwds={"maxlags": 4}
            )
            drift_p = float(drift_model.pvalues[0])
            trend_on_level = {
                "n": len(valid),
                "coefficient": float(level_model.params[1]),
                "statistic": float(level_model.tvalues[1]),
                "p_value": level_p,
                "p_value_raw": level_p,
                "p_value_display": _format_p_value(level_p),
                "bootstrap_p_value": bootstrap_p,
                "bootstrap_iterations": bootstrap_iterations,
                "block_length": block_length,
                "r_squared": float(level_model.rsquared),
            }
            drift_on_difference = {
                "n": len(differences),
                "coefficient": float(drift_model.params[0]),
                "statistic": float(drift_model.tvalues[0]),
                "p_value": drift_p,
                "p_value_raw": drift_p,
                "p_value_display": _format_p_value(drift_p),
            }
            if unreliable:
                decision = "unreliable_nonstationary"
            else:
                decision = "reject_h0" if level_p < alpha else "fail_to_reject_h0"
            results.append(
                _result(
                    bt_code="BT3",
                    test_name=f"{ticker} {field} linear trend (HAC)",
                    statistic=float(level_model.tvalues[1]),
                    p_value=level_p,
                    n=len(valid),
                    alpha=alpha,
                    note="; ".join(note_parts),
                    decision=decision,
                    coefficient=float(level_model.params[1]),
                    r_squared=float(level_model.rsquared),
                    adf=adf,
                    n_effective=len(valid),
                    excluded_quarters=excluded,
                    low_quality_quarters=low_quality,
                    quality_mode=quality_mode,
                    trend_on_level=trend_on_level,
                    drift_on_difference=drift_on_difference,
                    unreliable_nonstationary=unreliable,
                    exploratory=unreliable,
                )
            )
    return results


def _format_p_value(value: float | None) -> str | None:
    if value is None:
        return None
    return "< 0.001" if value < 0.001 else f"{value:.4g}"


def _pairs_at_lag(
    x_values: np.ndarray, y_values: np.ndarray, lag: int
) -> list[tuple[int, int, float, float]]:
    pairs: list[tuple[int, int, float, float]] = []
    for index in range(len(x_values)):
        target = index + lag
        if target >= len(y_values):
            break
        x_value = x_values[index]
        y_value = y_values[target]
        if math.isnan(x_value) or math.isnan(y_value):
            continue
        pairs.append((index, target, float(x_value), float(y_value)))
    return pairs


def _permutation_spearman_p(
    x_values: np.ndarray,
    y_values: np.ndarray,
    *,
    iterations: int,
    seed: int,
) -> float | None:
    if len(x_values) < 4 or iterations < 1:
        return None
    ranks_x = stats.rankdata(x_values).astype(float)
    ranks_y = stats.rankdata(y_values).astype(float)
    x_centered = ranks_x - ranks_x.mean()
    y_centered = ranks_y - ranks_y.mean()
    denominator = math.sqrt(float((x_centered ** 2).sum() * (y_centered ** 2).sum()))
    if denominator == 0:
        return None
    observed = float((x_centered * y_centered).sum() / denominator)
    rng = np.random.default_rng(seed)
    exceed = 0
    for _ in range(iterations):
        permutation = rng.permutation(y_centered)
        rho = float((x_centered * permutation).sum() / denominator)
        if abs(rho) >= abs(observed) - 1e-12:
            exceed += 1
    return (exceed + 1) / (iterations + 1)


def _correlation_variant(
    x_values: np.ndarray, y_values: np.ndarray, lag: int
) -> dict[str, Any]:
    pairs = _pairs_at_lag(x_values, y_values, lag)
    if len(pairs) < 8:
        return {"n": len(pairs), "rho": None, "p_value": None}
    xv = np.array([pair[2] for pair in pairs], dtype=float)
    yv = np.array([pair[3] for pair in pairs], dtype=float)
    rho, p_value = stats.spearmanr(xv, yv)
    return {"n": len(pairs), "rho": float(rho), "p_value": float(p_value)}


def _holm_family_size(p_values: list[float], family_size: int) -> list[float]:
    if not p_values:
        return []
    padded = list(p_values) + [1.0] * max(0, family_size - len(p_values))
    return holm_adjust(padded)[: len(p_values)]


def _apply_correlation_holm(
    results: list[dict[str, Any]],
    *,
    alpha: float,
    primary: str,
    max_lag: int,
) -> None:
    lag_families: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    bt_families: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in results:
        lag_families.setdefault((item["ticker"], item["x"], item["y"]), []).append(item)
        bt_families.setdefault((item["ticker"], item["bt_code"]), []).append(item)
    for key, family in lag_families.items():
        testable = [item for item in family if item["p_value"] is not None]
        adjusted = _holm_family_size(
            [item["p_value"] for item in testable], max_lag + 1
        )
        for item, value in zip(testable, adjusted):
            item["p_adj_lag_family"] = value
            item["holm_family_lag"] = f"{key[0]}|{key[1]}|{key[2]}|lags0-{max_lag}"
            item["holm_family_lag_size"] = max_lag + 1
        for item in family:
            item.setdefault("p_adj_lag_family", None)
            item.setdefault("holm_family_lag", f"{key[0]}|{key[1]}|{key[2]}|lags0-{max_lag}")
            item.setdefault("holm_family_lag_size", max_lag + 1)
    for key, family in bt_families.items():
        combinations = len({(item["x"], item["y"]) for item in family})
        family_size = combinations * (max_lag + 1)
        testable = [item for item in family if item["p_value"] is not None]
        adjusted = _holm_family_size([item["p_value"] for item in testable], family_size)
        for item, value in zip(testable, adjusted):
            item["p_adj_bt_family"] = value
            item["holm_family_bt"] = f"{key[0]}|{key[1]}|all|m={family_size}"
            item["holm_family_bt_size"] = family_size
        for item in family:
            item.setdefault("p_adj_bt_family", None)
            item.setdefault("holm_family_bt", f"{key[0]}|{key[1]}|all|m={family_size}")
            item.setdefault("holm_family_bt_size", family_size)
            if item["p_value"] is None:
                item["decision"] = "insufficient_data"
                item["p_adjusted"] = None
                item["exploratory"] = True
            else:
                strict = (
                    item["p_adj_bt_family"]
                    if primary == "bt"
                    else item["p_adj_lag_family"]
                )
                item["p_adjusted"] = strict
                item["holm_primary"] = primary
                if strict is not None and strict < alpha and not item.get("fragile"):
                    item["decision"] = "reject_h0"
                    item["exploratory"] = False
                else:
                    item["decision"] = "exploratory"
                    item["exploratory"] = True
            item["note"] = (
                item.get("note", "")
                + f"; Holm lag family m={item.get('holm_family_lag_size')} "
                f"p_adj={item.get('p_adj_lag_family')}; Holm BT family "
                f"m={item.get('holm_family_bt_size')} p_adj={item.get('p_adj_bt_family')}; "
                f"primary={primary}; fragile={bool(item.get('fragile'))}"
            )


def _correlation_family(
    *,
    bt_code: str,
    rows_by_ticker: dict[str, list[dict[str, Any]]],
    x_field: str,
    y_fields: list[str],
    max_lag: int,
    alpha: float,
    quality_mode: str = QUALITY_MODE_EXCLUDE,
    fragility_max_n: int = 15,
    permutation_iterations: int = 10000,
    permutation_seed: int = 20261107,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for ticker, rows in rows_by_ticker.items():
        ordered = sorted(rows, key=lambda row: row["calendar_key"])
        x_raw, x_status, x_labels = _masked_series(ordered, x_field, quality_mode)
        adf_x = _adf(x_raw)
        for field in y_fields:
            y_raw, y_status, y_labels = _masked_series(ordered, field, quality_mode)
            adf_y = _adf(y_raw)
            differenced = bool(
                adf_x.get("level_stationary") is False or adf_y.get("level_stationary") is False
            )
            x_series = np.concatenate(([math.nan], np.diff(x_raw))) if differenced else x_raw
            y_series = np.concatenate(([math.nan], np.diff(y_raw))) if differenced else y_raw
            x_diff = np.concatenate(([math.nan], np.diff(x_raw)))
            y_diff = np.concatenate(([math.nan], np.diff(y_raw)))
            for lag in range(max_lag + 1):
                pairs = _pairs_at_lag(x_series, y_series, lag)
                excluded: list[dict[str, Any]] = []
                low_quality: list[dict[str, Any]] = []
                for index, target, _, _ in pairs:
                    for metric, position, statuses, labels in (
                        (x_field, index, x_status, x_labels),
                        (field, target, y_status, y_labels),
                    ):
                        if statuses[position]:
                            entry = {
                                "ticker": ticker,
                                "calendar_key": ordered[position]["calendar_key"],
                                "metric": metric,
                                "reason": statuses[position],
                            }
                            if entry not in excluded:
                                excluded.append(entry)
                        if labels[position]:
                            entry = {
                                "ticker": ticker,
                                "calendar_key": ordered[position]["calendar_key"],
                                "metric": metric,
                                "reason": labels[position],
                            }
                            if entry not in low_quality:
                                low_quality.append(entry)
                n_effective = len(pairs)
                note = (
                    f"Lag family={ticker}|{x_field}|{field}|lags0-{max_lag} (m={max_lag + 1}); "
                    f"lag {lag}; n_eff={n_effective}; "
                    f"ADF x level p={adf_x['level_p_value']}, y level p={adf_y['level_p_value']}; "
                    f"transformation={'first_difference' if differenced else 'level'}; "
                    + ("n < 30: reference only" if n_effective < 30 else "n >= 30")
                )
                extra: dict[str, Any] = {
                    "ticker": ticker,
                    "x": x_field,
                    "y": field,
                    "lag": lag,
                    "method": "spearman",
                    "n_effective": n_effective,
                    "transformation": "first_difference" if differenced else "level",
                    "adf": {"x": adf_x, "y": adf_y},
                    "excluded_quarters": excluded,
                    "low_quality_quarters": low_quality,
                    "quality_mode": quality_mode,
                    "p_adj_lag_family": None,
                    "p_adj_bt_family": None,
                    "fragile": False,
                    "fragility_evaluated": False,
                    "exploratory": True,
                }
                if n_effective < 8:
                    results.append(
                        _result(
                            bt_code=bt_code,
                            test_name=f"{ticker} {x_field} vs {field} lag {lag}",
                            statistic=None,
                            p_value=None,
                            n=n_effective,
                            alpha=alpha,
                            decision="insufficient_data",
                            note=note + "; fewer than 8 usable pairs after quality filtering",
                            **extra,
                        )
                    )
                    continue
                x_values = np.array([pair[2] for pair in pairs], dtype=float)
                y_values = np.array([pair[3] for pair in pairs], dtype=float)
                rho, p_value = stats.spearmanr(x_values, y_values)
                rho = float(rho)
                p_value = float(p_value)
                level = _correlation_variant(x_raw, y_raw, lag)
                difference = _correlation_variant(x_diff, y_diff, lag)
                fragility_evaluated = n_effective < fragility_max_n
                permutation_p = (
                    _permutation_spearman_p(
                        x_values,
                        y_values,
                        iterations=permutation_iterations,
                        seed=permutation_seed + lag + len(results),
                    )
                    if fragility_evaluated
                    else None
                )
                fragile = False
                reasons: list[str] = []
                if fragility_evaluated:
                    flags = [p_value < alpha]
                    for label, variant in (("level", level), ("first_difference", difference)):
                        if variant["p_value"] is not None:
                            flags.append(variant["p_value"] < alpha)
                    if permutation_p is not None:
                        flags.append(permutation_p < alpha)
                    fragile = len(set(flags)) > 1
                    if fragile:
                        reasons.append("significance changes across level/difference/permutation")
                extra.update(
                    {
                        "level_rho": level["rho"],
                        "level_p_value": level["p_value"],
                        "difference_rho": difference["rho"],
                        "difference_p_value": difference["p_value"],
                        "permutation_p_value": permutation_p,
                        "fragility_evaluated": fragility_evaluated,
                        "fragile": fragile,
                        "fragility_reasons": reasons,
                    }
                )
                note += (
                    f"; fragility={'evaluated' if fragility_evaluated else 'not_evaluated'}"
                    f" fragile={fragile}"
                )
                results.append(
                    _result(
                        bt_code=bt_code,
                        test_name=f"{ticker} {x_field} vs {field} lag {lag}",
                        statistic=rho if not math.isnan(rho) else None,
                        p_value=p_value if not math.isnan(p_value) else None,
                        n=n_effective,
                        alpha=alpha,
                        note=note,
                        **extra,
                    )
                )
    # Seed the lag-family columns here; the caller merges the stricter BT-wide
    # family after both x-variable blocks have been computed.
    families: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for item in results:
        families.setdefault((item["ticker"], item["x"], item["y"]), []).append(item)
    for (ticker, x_field, y_field), family in families.items():
        testable = [item for item in family if item["p_value"] is not None]
        adjusted = _holm_family_size([item["p_value"] for item in testable], max_lag + 1)
        for item, value in zip(testable, adjusted):
            item["p_adj_lag_family"] = value
            item["p_adjusted"] = value
            item["holm_family_lag"] = f"{ticker}|{x_field}|{y_field}|lags0-{max_lag}"
            item["holm_family_lag_size"] = max_lag + 1
    return results


def _compute_mode(
    *,
    rows_by_ticker: dict[str, list[dict[str, Any]]],
    price_analytics: dict[str, Any],
    tickers: list[str],
    alpha: float,
    max_lag: int,
    quality_mode: str,
    bt1_start: str | None,
    bt1_end: str | None,
    one_off_quarters: dict[str, dict[str, str]] | None,
    holm_primary: str = "bt",
    fragility_max_n: int = 15,
    permutation_iterations: int = 10000,
    permutation_seed: int = 20261107,
    bt3_bootstrap_iterations: int = 1000,
    bt3_block_length: int = 4,
    bt3_bootstrap_seed: int = 20261107,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    bt1 = bt1_excess_returns(
        price_analytics=price_analytics,
        tickers=tickers,
        benchmark="SPY",
        alpha=alpha,
        start_date=bt1_start,
        end_date=bt1_end,
    )
    bt2 = bt2_paired_growth(
        rows_by_ticker=rows_by_ticker,
        tickers=tickers,
        alpha=alpha,
        quality_mode=quality_mode,
    )
    if one_off_quarters:
        bt2 += bt2_paired_growth(
            rows_by_ticker=rows_by_ticker,
            tickers=tickers,
            alpha=alpha,
            quality_mode=quality_mode,
            one_off_quarters=one_off_quarters,
            label_suffix=" (excl. one-off quarters)",
            fields=[("net_income_growth_yoy", "Net income growth YoY")],
        )
    bt3 = bt3_trend(
        rows_by_ticker=rows_by_ticker,
        alpha=alpha,
        quality_mode=quality_mode,
        bootstrap_iterations=bt3_bootstrap_iterations,
        block_length=bt3_block_length,
        bootstrap_seed=bt3_bootstrap_seed,
    )
    common = {
        "max_lag": max_lag,
        "alpha": alpha,
        "quality_mode": quality_mode,
        "fragility_max_n": fragility_max_n,
        "permutation_iterations": permutation_iterations,
        "permutation_seed": permutation_seed,
    }
    bt4 = _correlation_family(
        bt_code="BT4",
        rows_by_ticker=rows_by_ticker,
        x_field="rd_growth_yoy",
        y_fields=["revenue_growth_yoy", "fcf_growth_yoy", "operating_margin"],
        **common,
    )
    bt4 += _correlation_family(
        bt_code="BT4",
        rows_by_ticker=rows_by_ticker,
        x_field="capex_growth_yoy",
        y_fields=["revenue_growth_yoy", "fcf_growth_yoy", "operating_margin"],
        **common,
    )
    bt5 = _correlation_family(
        bt_code="BT5",
        rows_by_ticker=rows_by_ticker,
        x_field="revenue_growth_yoy",
        y_fields=["stock_return_quarter"],
        **common,
    )
    _apply_correlation_holm(bt4, alpha=alpha, primary=holm_primary, max_lag=max_lag)
    _apply_correlation_holm(bt5, alpha=alpha, primary=holm_primary, max_lag=max_lag)
    return bt2 + bt3, bt1 + bt2 + bt3 + bt4 + bt5


def run_all_tests(
    *,
    rows_by_ticker: dict[str, list[dict[str, Any]]],
    price_analytics: dict[str, Any],
    tickers: list[str],
    alpha: float,
    max_lag: int,
    quality_mode: str = QUALITY_MODE_LABEL,
    quality_mode_primary: str | None = None,
    bt1_start: str | None = None,
    bt1_end: str | None = None,
    one_off_quarters: dict[str, dict[str, str]] | None = None,
    comparison_modes: tuple[str, ...] = QUALITY_MODES,
    holm_primary: str = "bt",
    fragility_max_n: int = 15,
    permutation_iterations: int = 10000,
    permutation_seed: int = 20261107,
    bt3_bootstrap_iterations: int = 1000,
    bt3_block_length: int = 4,
    bt3_bootstrap_seed: int = 20261107,
) -> dict[str, Any]:
    primary_letter = (
        quality_mode_primary.upper()
        if quality_mode_primary in {"A", "B"}
        else ("B" if quality_mode == QUALITY_MODE_LABEL else "A")
    )
    mode = QUALITY_MODE_LABEL if primary_letter == "B" else QUALITY_MODE_EXCLUDE
    mode_by_letter = {"A": QUALITY_MODE_EXCLUDE, "B": QUALITY_MODE_LABEL}
    computed: dict[str, list[dict[str, Any]]] = {}
    for candidate in QUALITY_MODES:
        _, candidate_results = _compute_mode(
            rows_by_ticker=rows_by_ticker,
            price_analytics=price_analytics,
            tickers=tickers,
            alpha=alpha,
            max_lag=max_lag,
            quality_mode=candidate,
            bt1_start=bt1_start,
            bt1_end=bt1_end,
            one_off_quarters=one_off_quarters,
            holm_primary=holm_primary,
            fragility_max_n=fragility_max_n,
            permutation_iterations=permutation_iterations,
            permutation_seed=permutation_seed,
            bt3_bootstrap_iterations=bt3_bootstrap_iterations,
            bt3_block_length=bt3_block_length,
            bt3_bootstrap_seed=bt3_bootstrap_seed,
        )
        computed[candidate] = candidate_results
    results = computed[mode]
    comparison: list[dict[str, Any]] = []
    for candidate in comparison_modes:
        if candidate == mode:
            continue
        for item in computed.get(candidate, []):
            if item["bt_code"] not in {"BT2", "BT3", "BT4", "BT5"}:
                continue
            comparison.append(
                {
                    "quality_mode": candidate,
                    "bt_code": item["bt_code"],
                    "test_name": item["test_name"],
                    "n": item["n"],
                    "p_value": item["p_value"],
                    "p_adjusted": item["p_adjusted"],
                    "decision": item["decision"],
                    "excluded_quarters": item.get("excluded_quarters", []),
                    "low_quality_quarters": item.get("low_quality_quarters", []),
                }
            )
    # Every hypothesis-test row carries both modes side by side so a reader can
    # see whether the quality decision changes the conclusion.
    indexed = {
        candidate: {(item["bt_code"], item["test_name"]): item for item in items}
        for candidate, items in computed.items()
    }
    for item in results:
        if item["bt_code"] not in {"BT2", "BT3", "BT4", "BT5"}:
            continue
        decisions = {}
        for letter, candidate in mode_by_letter.items():
            other = indexed[candidate].get((item["bt_code"], item["test_name"]))
            if other is None:
                continue
            item[f"mode_{letter}_n"] = other["n"]
            item[f"mode_{letter}_p_value_raw"] = other["p_value"]
            item[f"mode_{letter}_p_adjusted_raw"] = other["p_adjusted"]
            item[f"mode_{letter}_decision"] = other["decision"]
            decisions[letter] = other["decision"]
        item["mode_sensitive"] = len(set(decisions.values())) > 1
    return {
        "schema_version": "1.2",
        "alpha": alpha,
        "quality_mode": mode,
        "quality_mode_primary": primary_letter,
        "quality_mode_default": "B",
        "quality_mode_description": {
            QUALITY_MODE_EXCLUDE: (
                "Mode A: quarters whose underlying metrics are not quality_flag=ok are removed "
                "from the test and listed in excluded_quarters with a reason (DR-04.8, FR-52)."
            ),
            QUALITY_MODE_LABEL: (
                "Mode B: derived quarters with identity_ok=true are kept and labelled; low-quality "
                "quarters with any other reason are still excluded (DR-04.8, FR-52)."
            ),
        },
        "holm_family": (
            "Two Holm families are stored: lag (company x x-variable x y-variable, m=5) and "
            "BT-wide (company x BT, m=30 for BT4); the stricter BT-wide family drives decision."
        ),
        "holm_primary": holm_primary,
        "fragility_max_n": fragility_max_n,
        "permutation_iterations": permutation_iterations,
        "warnings": [
            "BT4/BT5: every x and y series is ADF-tested; when either is non-stationary at level, both "
            "series are first-differenced before Spearman and the effective n is reported.",
            "Holm correction is stored for the lag family (m=5) and the company-wide BT family "
            "(BT4 m=30, BT5 m=5); the stricter BT family drives decision.",
            "A BT4/BT5 result is called reject_h0 only when the strict Holm family rejects and the "
            "level/first-difference/permutation sensitivity check is not fragile; otherwise exploratory.",
            "Quality mode B (label_low) is primary; A (exclude_low) is the sensitivity analysis. "
            "Only derived quarters with identity_ok=true are retained in B; other low-quality reasons "
            "are excluded in both modes.",
            "n after YoY/lag/differencing is reported; n < 30 means reference only.",
            "Correlation does not imply causation.",
        ],
        "quality_mode_comparison": comparison,
        "results": results,
    }


def present_p_values(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep raw p-values for machines and expose a reader-safe display value."""
    def convert(container: dict[str, Any]) -> None:
        for key in ("p_value", "p_adjusted"):
            raw = container.get(key)
            if isinstance(raw, (int, float)):
                container[f"{key}_raw"] = float(raw)
                container[f"{key}_display"] = _format_p_value(float(raw))
                container[key] = container[f"{key}_display"]
        for name in ("trend_on_level", "drift_on_difference"):
            if isinstance(container.get(name), dict):
                convert(container[name])

    for result in payload.get("results", []):
        convert(result)
    for row in payload.get("quality_mode_comparison", []):
        convert(row)
    return payload
