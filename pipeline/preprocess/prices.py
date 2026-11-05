"""Price preprocessing: returns, window ROI, volatility, drawdown."""

from __future__ import annotations

from datetime import date
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


def monthly_returns(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    data["month"] = pd.to_datetime(data["trade_date"]).dt.to_period("M")
    month_end = data.groupby("month", as_index=False).tail(1).copy()
    month_end["return"] = month_end["adj_close"].pct_change()
    return month_end[["trade_date", "adj_close", "return"]].dropna().reset_index(drop=True)


def quarterly_returns(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    data["calendar_key"] = pd.to_datetime(data["trade_date"]).dt.date.map(quarter_key)
    quarter_last = data.groupby("calendar_key", as_index=False).tail(1).copy()
    quarter_last["return"] = quarter_last["adj_close"].pct_change()
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


def build_price_analytics(
    *,
    ticker: str,
    frame: pd.DataFrame,
    quarters: list[str],
    price_start: date,
    price_end: date,
) -> dict[str, Any]:
    normalized = normalize_prices(frame)
    monthly = monthly_returns(normalized)
    quarterly = quarterly_returns(normalized)
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
