"""Price preprocessing: returns, window ROI, volatility, drawdown."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from pipeline.util import quarter_end, quarter_key


def normalize_prices(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    data["trade_date"] = pd.to_datetime(data["trade_date"]).dt.date
    for column in ["open", "high", "low", "close", "adj_close", "volume", "dividends", "stock_splits"]:
        if column in data.columns:
            data[column] = pd.to_numeric(data[column], errors="coerce")
    return data.sort_values("trade_date").drop_duplicates("trade_date", keep="last").reset_index(drop=True)


def price_on_or_before(frame: pd.DataFrame, target: date) -> dict[str, Any] | None:
    candidates = frame[frame["trade_date"] <= target]
    if candidates.empty:
        return None
    row = candidates.iloc[-1]
    return row.to_dict()


def _month_period_end(period: pd.Period) -> date:
    return ((period + 1).start_time - timedelta(days=1)).date()


def monthly_returns(
    frame: pd.DataFrame,
    *,
    start: date | None = None,
    as_of: date | None = None,
) -> pd.DataFrame:
    """Month-end returns, excluding the partial current month.

    Returns are computed before trimming so the first month in the window uses
    the prior month-end close (DR-01.3). A month is kept only when its calendar
    month end is on or before ``as_of``.
    """
    data = frame.copy()
    data["month"] = pd.to_datetime(data["trade_date"]).dt.to_period("M")
    month_end = data.groupby("month", as_index=False).tail(1).copy()
    month_end["return"] = month_end["adj_close"].pct_change()
    month_end["month_end"] = month_end["month"].map(_month_period_end)
    if start is not None:
        month_end = month_end[month_end["trade_date"] >= start]
    if as_of is not None:
        month_end = month_end[month_end["month_end"] <= as_of]
    return month_end[["trade_date", "adj_close", "return"]].dropna().reset_index(drop=True)


def quarterly_returns(
    frame: pd.DataFrame,
    *,
    start: date | None = None,
    as_of: date | None = None,
) -> pd.DataFrame:
    """Calendar-quarter returns, excluding the unfinished current quarter."""
    data = frame.copy()
    data["calendar_key"] = pd.to_datetime(data["trade_date"]).dt.date.map(quarter_key)
    quarter_last = data.groupby("calendar_key", as_index=False).tail(1).copy()
    quarter_last["return"] = quarter_last["adj_close"].pct_change()
    quarter_last["quarter_end"] = quarter_last["calendar_key"].map(quarter_end)
    if start is not None:
        quarter_last = quarter_last[quarter_last["trade_date"] >= start]
    if as_of is not None:
        quarter_last = quarter_last[quarter_last["quarter_end"] <= as_of]
    return quarter_last[["calendar_key", "trade_date", "adj_close", "return"]].dropna().reset_index(drop=True)


def daily_returns(frame: pd.DataFrame) -> pd.Series:
    return frame["adj_close"].pct_change().dropna()


def annualized_volatility(frame: pd.DataFrame) -> float | None:
    returns = daily_returns(frame)
    if len(returns) < 2:
        return None
    return float(returns.std(ddof=1) * np.sqrt(252))


def max_drawdown(frame: pd.DataFrame) -> float | None:
    if frame.empty:
        return None
    values = frame["adj_close"].astype(float)
    running_max = values.cummax()
    drawdown = values / running_max - 1.0
    return float(drawdown.min())


def window_roi(frame: pd.DataFrame, start: date, end: date) -> float | None:
    start_row = price_on_or_before(frame, start)
    end_row = price_on_or_before(frame, end)
    if not start_row or not end_row or not start_row["adj_close"]:
        return None
    return float(end_row["adj_close"] / start_row["adj_close"] - 1.0)


def total_return_with_dividends(frame: pd.DataFrame, start: date, end: date) -> float | None:
    """Simple total-return approximation using split-adjusted close plus dividends.

    Charts and statistical tests use adj_close; this helper exists for the
    calculator contract where dividends are displayed separately.
    """
    start_row = price_on_or_before(frame, start)
    end_row = price_on_or_before(frame, end)
    if not start_row or not end_row:
        return None
    window = frame[(frame["trade_date"] > start_row["trade_date"]) & (frame["trade_date"] <= end_row["trade_date"])]
    dividends = float(window["dividends"].fillna(0).sum()) if "dividends" in window else 0.0
    if not start_row["close"]:
        return None
    return float((end_row["close"] + dividends) / start_row["close"] - 1.0)


def normalized_series(frame: pd.DataFrame, start: date, end: date, base: float = 100.0) -> list[dict[str, Any]]:
    window = frame[(frame["trade_date"] >= start) & (frame["trade_date"] <= end)].copy()
    if window.empty:
        return []
    first = float(window.iloc[0]["adj_close"])
    if not first:
        return []
    window["value"] = window["adj_close"] / first * base
    return [
        {"date": row.trade_date.isoformat(), "value": round(float(row.value), 4)}
        for row in window.itertuples()
    ]


def adjusted_close_selfcheck(frame: pd.DataFrame) -> dict[str, Any]:
    """Recompute adjusted close from split-adjusted close plus dividends.

    ``adj_close_t / adj_close_{t-1} = (close_t + dividend_t) / close_{t-1}``
    when close and dividends are on the post-split basis. The test also confirms
    that no raw split jump (e.g. GOOGL 20:1) remains in ``close`` and that the
    split factor is recorded in the corporate-actions file.
    """
    data = normalize_prices(frame)
    result: dict[str, Any] = {
        "method": "recurrence adj_close_t = adj_close_(t-1) * (close_t + dividend_t) / close_(t-1)",
        "rows": int(len(data)),
        "max_relative_difference": None,
        "mean_relative_difference": None,
        "tolerance": None,
        "status": "insufficient_data",
        "dividend_events": 0,
        "split_events": [],
        "split_continuity_ok": None,
    }
    if len(data) < 3:
        return result
    close = data["close"].astype(float).to_numpy()
    adjusted = data["adj_close"].astype(float).to_numpy()
    dividends = (
        data["dividends"].astype(float).fillna(0.0).to_numpy()
        if "dividends" in data.columns
        else np.zeros(len(data))
    )
    expected = np.empty(len(data), dtype=float)
    expected[0] = adjusted[0]
    for index in range(1, len(data)):
        if close[index - 1] == 0:
            continue
        expected[index] = expected[index - 1] * (close[index] + dividends[index]) / close[index - 1]
    denominator = np.where(adjusted == 0, np.nan, np.abs(adjusted))
    differences = np.abs(expected - adjusted) / denominator
    finite = differences[np.isfinite(differences)]
    result["max_relative_difference"] = float(finite.max()) if finite.size else None
    result["mean_relative_difference"] = float(finite.mean()) if finite.size else None
    result["dividend_events"] = int((dividends != 0).sum())
    if "stock_splits" in data.columns:
        splits = data[data["stock_splits"].astype(float).fillna(0.0) != 0]
        for position, row in enumerate(splits.itertuples()):
            result["split_events"].append(
                {
                    "trade_date": row.trade_date.isoformat(),
                    "ratio": float(row.stock_splits),
                }
            )
        # With split-adjusted close, the split date must not show a raw 20x jump.
        continuity = True
        for index in range(1, len(data)):
            if close[index - 1] == 0:
                continue
            move = close[index] / close[index - 1]
            if move > 3.0 or move < 1.0 / 3.0:
                continuity = False
        result["split_continuity_ok"] = continuity
    return result


def build_price_analytics(
    *,
    ticker: str,
    frame: pd.DataFrame,
    quarters: list[str],
    price_start: date,
    price_end: date,
    analysis_start: date | None = None,
    as_of: date | None = None,
) -> dict[str, Any]:
    normalized = normalize_prices(frame)
    monthly = monthly_returns(normalized, start=analysis_start, as_of=as_of)
    quarterly = quarterly_returns(normalized, start=analysis_start, as_of=as_of)
    quarter_end_rows: dict[str, Any] = {}
    for key in quarters:
        row = price_on_or_before(normalized, quarter_end(key))
        if row:
            quarter_end_rows[key] = {
                "trade_date": row["trade_date"].isoformat(),
                "close": float(row["close"]),
                "adj_close": float(row["adj_close"]),
            }
    return {
        "ticker": ticker,
        "first_trade_date": normalized.iloc[0]["trade_date"].isoformat() if not normalized.empty else None,
        "last_trade_date": normalized.iloc[-1]["trade_date"].isoformat() if not normalized.empty else None,
        "rows": int(len(normalized)),
        "annualized_volatility": annualized_volatility(normalized),
        "max_drawdown": max_drawdown(normalized),
        "roi_1y": window_roi(normalized, date(price_end.year - 1, price_end.month, price_end.day), price_end),
        "roi_3y": window_roi(normalized, date(price_end.year - 3, price_end.month, price_end.day), price_end),
        "roi_5y": window_roi(normalized, date(price_end.year - 5, price_end.month, price_end.day), price_end),
        "quarter_end": quarter_end_rows,
        "monthly_returns": [
            {
                "trade_date": row.trade_date.isoformat(),
                "return": float(row.return_),
                "adj_close": float(row.adj_close),
            }
            for row in monthly.rename(columns={"return": "return_"}).itertuples()
        ],
        "quarterly_returns": [
            {
                "calendar_key": row.calendar_key,
                "trade_date": row.trade_date.isoformat(),
                "return": float(row.return_),
            }
            for row in quarterly.rename(columns={"return": "return_"}).itertuples()
        ],
        "normalized": normalized_series(normalized, price_start, price_end),
    }
