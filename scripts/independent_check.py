"""Independent recomputation of selected BT results with scipy/statsmodels only.

Reads the published dashboard data, rebuilds the series from source values, and
re-runs four tests without importing ``pipeline.stats.tests``. Results must match
the pipeline within 1e-6.

Usage:
    python -m scripts.independent_check
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.regression.linear_model import OLS
from statsmodels.tools import add_constant
from statsmodels.tsa.stattools import adfuller

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "web" / "public" / "data"
EVIDENCE = ROOT / "docs" / "evidence"
TOLERANCE = 1e-6


def load(name: str) -> Any:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def quarter_shift(key: str, offset: int) -> str:
    year, quarter = key.split("-Q")
    total = int(year) * 4 + int(quarter) - 1 + offset
    return f"{total // 4}-Q{total % 4 + 1}"


INPUTS = {
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
GROWTH = {
    "revenue_growth_yoy",
    "net_income_growth_yoy",
    "rd_growth_yoy",
    "capex_growth_yoy",
    "fcf_growth_yoy",
}


def rows_for(financials: dict[str, Any], ticker: str) -> list[dict[str, Any]]:
    rows = [row for row in financials["quarters"] if row["ticker"] == ticker]
    return sorted(rows, key=lambda row: row["calendar_key"])


def usable(field: str, row: dict[str, Any]) -> bool:
    for name in INPUTS[field]:
        metric = row.get("metrics", {}).get(name, {})
        if metric.get("value") is None or metric.get("quality_flag") != "ok":
            return False
    return True


def series(rows: list[dict[str, Any]], field: str) -> dict[str, float]:
    output: dict[str, float] = {}
    for index, row in enumerate(rows):
        value = row.get("derived_metrics", {}).get(field)
        if value is None or not usable(field, row):
            continue
        if field in GROWTH:
            if index < 4 or not usable(field, rows[index - 4]):
                continue
        output[row["calendar_key"]] = float(value)
    return output


def check_bt1() -> dict[str, Any]:
    tests = load("tests.json")
    manifest = load("manifest.json")
    result = next(item for item in tests["results"] if item["bt_code"] == "BT1" and "MSFT" in item["test_name"])
    frames = {}
    for ticker in ("MSFT", "SPY"):
        payload = load(f"prices/{ticker}.json")
        frame = pd.DataFrame(payload["rows"])
        frame["trade_date"] = pd.to_datetime(frame["trade_date"] if "trade_date" in frame else frame["date"])
        frames[ticker] = frame
    returns = {}
    for ticker, frame in frames.items():
        frame = frame.sort_values("trade_date").copy()
        frame["month"] = frame["trade_date"].dt.to_period("M")
        month_end = frame.groupby("month", as_index=False).tail(1)
        month_end["return"] = month_end["adj_close"].pct_change()
        month_end["month_end"] = month_end["month"].map(lambda period: (period + 1).start_time.date())
        month_end = month_end[month_end["month_end"] <= date.fromisoformat(manifest["data_as_of"])]
        returns[ticker] = {
            row.trade_date.date().isoformat(): float(row.return_)
            for row in month_end.rename(columns={"return": "return_"}).itertuples()
            if not np.isnan(row.return_)
            and row.trade_date.date().isoformat() >= "2022-01-01"
        }
    dates = sorted(set(returns["MSFT"]) & set(returns["SPY"]))
    excess = np.array([returns["MSFT"][key] - returns["SPY"][key] for key in dates])
    t_stat, t_p = stats.ttest_1samp(excess, 0.0)
    return {
        "test": "BT1 MSFT monthly excess return vs SPY",
        "n_pipeline": result["n"],
        "n_independent": len(dates),
        "p_pipeline": result["t_p_value"],
        "p_independent": float(t_p),
        "statistic_pipeline": result["t_statistic"],
        "statistic_independent": float(t_stat),
        "window_start": dates[0],
    }


def check_bt2() -> dict[str, Any]:
    financials = load("financials.json")
    tests = load("tests.json")
    result = next(
        item
        for item in tests["results"]
        if item["bt_code"] == "BT2" and item["test_name"].startswith("Revenue growth")
    )
    msft = series(rows_for(financials, "MSFT"), "revenue_growth_yoy")
    googl = series(rows_for(financials, "GOOGL"), "revenue_growth_yoy")
    keys = sorted(set(msft) & set(googl))
    a = np.array([msft[key] for key in keys])
    b = np.array([googl[key] for key in keys])
    difference = a - b
    t_stat, t_p = stats.ttest_rel(a, b)
    shapiro_stat, shapiro_p = stats.shapiro(difference)
    wilcoxon_stat, wilcoxon_p = stats.wilcoxon(difference, zero_method="wilcox")
    return {
        "test": "BT2 revenue growth MSFT vs GOOGL",
        "n_pipeline": result["n"],
        "n_independent": len(keys),
        "t_p_pipeline": result["t_p_value"],
        "t_p_independent": float(t_p),
        "shapiro_p_pipeline": result["shapiro_p_value"],
        "shapiro_p_independent": float(shapiro_p),
        "wilcoxon_p_pipeline": result["wilcoxon_p_value"],
        "wilcoxon_p_independent": float(wilcoxon_p),
    }


def adf_level(values: np.ndarray) -> float:
    return float(adfuller(pd.Series(values).dropna(), regression="c", autolag="AIC")[1])


def correlation_check() -> dict[str, Any]:
    financials = load("financials.json")
    tests = load("tests.json")
    result = next(item for item in tests["results"] if item["bt_code"] == "BT4" and item.get("p_value_raw") is not None)
    ticker, x_field, y_field, lag = result["ticker"], result["x"], result["y"], result["lag"]
    rows = rows_for(financials, ticker)
    x_map = series(rows, x_field)
    y_map = series(rows, y_field)
    index = {row["calendar_key"]: position for position, row in enumerate(rows)}
    x = np.array([x_map.get(row["calendar_key"], np.nan) for row in rows], dtype=float)
    y = np.array([y_map.get(row["calendar_key"], np.nan) for row in rows], dtype=float)
    differenced = bool(result["transformation"] == "first_difference")
    if differenced:
        x = np.concatenate(([np.nan], np.diff(x)))
        y = np.concatenate(([np.nan], np.diff(y)))
    pairs = []
    for key, position in sorted(index.items(), key=lambda item: item[1]):
        target = position + lag
        if target >= len(rows):
            continue
        xv, yv = x[position], y[target]
        if np.isnan(xv) or np.isnan(yv):
            continue
        pairs.append((xv, yv))
    xv = np.array([pair[0] for pair in pairs])
    yv = np.array([pair[1] for pair in pairs])
    rho, p_value = stats.spearmanr(xv, yv)
    return {
        "test": f"BT4 {ticker} {x_field} vs {y_field} lag {lag}",
        "transformation": result["transformation"],
        "n_pipeline": result["n"],
        "n_independent": len(pairs),
        "rho_pipeline": result["statistic"],
        "rho_independent": float(rho),
        "p_pipeline": result.get("p_value_raw"),
        "p_independent": float(p_value),
        "adf_level_p_x": adf_level(np.array([x_map.get(key, np.nan) for key in sorted(x_map)])),
    }


def check_bt3() -> dict[str, Any]:
    financials = load("financials.json")
    tests = load("tests.json")
    result = next(
        item
        for item in tests["results"]
        if item["bt_code"] == "BT3" and "MSFT rd_intensity" in item["test_name"]
    )
    rows = rows_for(financials, "MSFT")
    values = series(rows, "rd_intensity")
    positions = [index for index, row in enumerate(rows) if row["calendar_key"] in values]
    y = np.array([values[rows[index]["calendar_key"]] for index in positions])
    x = add_constant(np.array(positions, dtype=float))
    model = OLS(y, x).fit(cov_type="HAC", cov_kwds={"maxlags": 4})
    return {
        "test": "BT3 MSFT rd_intensity linear trend (HAC)",
        "n_pipeline": result["n"],
        "n_independent": len(values),
        "coefficient_pipeline": result["coefficient"],
        "coefficient_independent": float(model.params[1]),
        "p_pipeline": result.get("p_value_raw"),
        "p_independent": float(model.pvalues[1]),
    }


def main() -> int:
    checks = [check_bt1(), check_bt2(), correlation_check(), check_bt3()]
    failures = []
    for check in checks:
        for key, value in check.items():
            if key.endswith("_pipeline") and f"{key[:-9]}_independent" in check:
                independent = check[f"{key[:-9]}_independent"]
                if value is None or independent is None:
                    continue
                if abs(float(value) - float(independent)) > TOLERANCE:
                    failures.append(f"{check['test']}:{key} pipeline={value} independent={independent}")
        if check.get("n_pipeline") != check.get("n_independent"):
            failures.append(f"{check['test']}:n {check.get('n_pipeline')} != {check.get('n_independent')}")
    payload = {
        "tolerance": TOLERANCE,
        "checks": checks,
        "failures": failures,
        "result": "ok" if not failures else "fail",
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "independent_recheck.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
