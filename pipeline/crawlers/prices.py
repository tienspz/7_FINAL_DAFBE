"""Price and corporate-action crawler using yfinance."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import time as time_module
from typing import Any

import pandas as pd
import yfinance as yf

from pipeline.http import MUTABLE_DATA_CACHE_MAX_AGE_SECONDS
from pipeline.util import sha256_bytes, utc_now_iso

PRICE_TICKERS = ["MSFT", "GOOGL", "SPY", "QQQ"]
INSTRUMENT_TYPES = {"MSFT": "stock", "GOOGL": "stock", "SPY": "etf", "QQQ": "etf"}


@dataclass
class PriceBundle:
    prices: pd.DataFrame
    corporate_actions: pd.DataFrame
    combined_path: Path
    ticker_paths: dict[str, Path]


def _chart_url(ticker: str, start: date, end: date) -> str:
    period1 = int(datetime.combine(start, time.min, tzinfo=timezone.utc).timestamp())
    period2 = int(datetime.combine(end + timedelta(days=1), time.min, tzinfo=timezone.utc).timestamp())
    return (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        f"?period1={period1}&period2={period2}&interval=1d&events=div%2Csplits"
    )


def fetch_prices(
    *,
    tickers: list[str],
    start: date,
    end: date,
    raw_dir: Path,
    as_of: str,
    refresh: bool = False,
    max_age_seconds: int | None = MUTABLE_DATA_CACHE_MAX_AGE_SECONDS,
) -> PriceBundle:
    prices_dir = raw_dir / "prices"
    prices_dir.mkdir(parents=True, exist_ok=True)
    combined_path = prices_dir / f"prices_{as_of}.csv"
    ticker_paths: dict[str, Path] = {}
    frames: list[pd.DataFrame] = []
    actions: list[pd.DataFrame] = []
    last_request_at = 0.0

    for ticker in tickers:
        ticker_path = prices_dir / f"{ticker}_{as_of}.csv"
        ticker_paths[ticker] = ticker_path
        cache_fresh = False
        if ticker_path.exists() and max_age_seconds is not None:
            cache_fresh = time_module.time() - ticker_path.stat().st_mtime <= max_age_seconds
        if ticker_path.exists() and not refresh and (max_age_seconds is None or cache_fresh):
            frame = pd.read_csv(ticker_path)
            frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.date
            frames.append(frame)
            action_rows = frame[(frame["dividends"].fillna(0) != 0) | (frame["stock_splits"].fillna(0) != 0)]
            if not action_rows.empty:
                actions.append(action_rows[["ticker", "trade_date", "dividends", "stock_splits", "source_url", "evidence_url", "fetched_at", "response_sha256"]].copy())
            continue

        elapsed = time_module.monotonic() - last_request_at
        if last_request_at and elapsed < 1.0:
            time_module.sleep(1.0 - elapsed)
        history = yf.Ticker(ticker).history(
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
            auto_adjust=False,
            actions=True,
        )
        last_request_at = time_module.monotonic()
        if history.empty:
            raise RuntimeError(f"yfinance returned no rows for {ticker}")
        history = history.reset_index()
        date_column = "Date" if "Date" in history.columns else history.columns[0]
        history["trade_date"] = pd.to_datetime(history[date_column]).dt.date
        for column in ["Open", "High", "Low", "Close", "Adj Close", "Volume", "Dividends", "Stock Splits"]:
            if column not in history.columns:
                history[column] = 0.0
        frame = pd.DataFrame(
            {
                "ticker": ticker,
                "instrument_type": INSTRUMENT_TYPES.get(ticker, "stock"),
                "trade_date": history["trade_date"],
                "open": history["Open"],
                "high": history["High"],
                "low": history["Low"],
                "close": history["Close"],
                "adj_close": history["Adj Close"],
                "volume": history["Volume"],
                "dividends": history["Dividends"],
                "stock_splits": history["Stock Splits"],
            }
        )
        frame = frame.sort_values("trade_date").reset_index(drop=True)
        # Hash the canonical price payload before adding run metadata.
        canonical = frame.to_csv(index=False).encode("utf-8")
        response_sha256 = sha256_bytes(canonical)
        fetched_at = utc_now_iso()
        frame["as_of"] = as_of
        frame["price_source"] = "yfinance"
        frame["source_url"] = f"https://finance.yahoo.com/quote/{ticker}/history/"
        frame["evidence_url"] = _chart_url(ticker, start, end)
        frame["fetched_at"] = fetched_at
        frame["response_sha256"] = response_sha256
        frame["parser_version"] = "1.0.0"
        frame.to_csv(ticker_path, index=False)
        frames.append(frame)

        action_rows = frame[(frame["dividends"].fillna(0) != 0) | (frame["stock_splits"].fillna(0) != 0)].copy()
        if not action_rows.empty:
            actions.append(action_rows[["ticker", "trade_date", "dividends", "stock_splits", "source_url", "evidence_url", "fetched_at", "response_sha256"]])

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values(["ticker", "trade_date"]).reset_index(drop=True)
    combined.to_csv(combined_path, index=False)

    if actions:
        action_frame = pd.concat(actions, ignore_index=True)
        action_frame["action_type"] = action_frame.apply(
            lambda row: "split" if float(row["stock_splits"] or 0) != 0 else "dividend",
            axis=1,
        )
        action_frame["value"] = action_frame.apply(
            lambda row: float(row["stock_splits"] or 0) if row["action_type"] == "split" else float(row["dividends"] or 0),
            axis=1,
        )
        action_frame = action_frame.rename(columns={"trade_date": "action_date"})
        action_frame = action_frame[
            ["ticker", "action_date", "action_type", "value", "source_url", "evidence_url", "fetched_at", "response_sha256"]
        ]
        action_frame.to_csv(prices_dir / "corporate_actions.csv", index=False)
    else:
        action_frame = pd.DataFrame(
            columns=["ticker", "action_date", "action_type", "value", "source_url", "evidence_url", "fetched_at", "response_sha256"]
        )
        action_frame.to_csv(prices_dir / "corporate_actions.csv", index=False)

    return PriceBundle(prices=combined, corporate_actions=action_frame, combined_path=combined_path, ticker_paths=ticker_paths)
