"""Conditional adjusted-close cross-check via Alpha Vantage.

The domain was approved for CR-13 on 2026-11-05 **only** for this check and
**only** with a real API key. ``apikey=demo`` is never accepted as data.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any

from pipeline.http import CachedHttpClient, HttpError
from pipeline.util import safe_float, write_json

ENV_KEY = "ALPHAVANTAGE_API_KEY"
DEFAULT_TICKERS = ["MSFT", "GOOGL"]
ERROR_KEYS = ("Error Message", "Information", "Note")


def available_api_key() -> str | None:
    key = os.environ.get(ENV_KEY, "").strip()
    if not key or key.lower() == "demo":
        return None
    return key


def adjusted_url(ticker: str, key: str) -> str:
    return (
        "https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED"
        f"&symbol={ticker}&outputsize=compact&apikey={key}"
    )


def parse_daily_adjusted(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    series = (payload or {}).get("Time Series (Daily)") or {}
    rows: list[dict[str, Any]] = []
    for trade_date, item in series.items():
        if not isinstance(item, dict):
            continue
        adjusted = safe_float(item.get("5. adjusted close"))
        close = safe_float(item.get("4. close"))
        if adjusted is None:
            continue
        rows.append(
            {
                "trade_date": trade_date,
                "close": close,
                "adjusted_close": adjusted,
                "volume": safe_float(item.get("6. volume")),
            }
        )
    rows.sort(key=lambda row: row["trade_date"])
    return rows


def fetch_adjusted_closes(
    *,
    client: CachedHttpClient,
    tickers: list[str] | None = None,
    raw_dir: Path,
    as_of: str | None = None,
) -> dict[str, Any]:
    """Return adjusted closes when a real key exists, otherwise unverified state."""
    key = available_api_key()
    result: dict[str, Any] = {
        "available": False,
        "reason": (
            f"{ENV_KEY} is not set (or equals the demo key); adjusted-close "
            "cross-check was not run. The demo key is not accepted as data."
        ),
        "rows_by_ticker": {},
        "artifacts": {},
        "errors": {},
        "as_of": as_of,
    }
    if key is None:
        return result

    result["available"] = True
    result["reason"] = ""
    for ticker in tickers or DEFAULT_TICKERS:
        url = adjusted_url(ticker, key)
        try:
            response = client.get(url)
            payload = response.json()
            problems = {name: payload.get(name) for name in ERROR_KEYS if payload.get(name)}
            if problems:
                raise ValueError(f"Alpha Vantage returned a notice: {problems}")
            rows = parse_daily_adjusted(payload)
            if len(rows) < 30:
                raise ValueError(f"only {len(rows)} adjusted-close rows returned")
            artifact = {
                "ticker": ticker,
                "source_url": response.url,
                "http_status": response.status,
                "fetched_at": response.fetched_at,
                "response_sha256": response.sha256,
                "as_of": as_of,
                "rows": rows,
            }
            path = raw_dir / "prices" / "alphavantage" / f"{ticker}.json"
            write_json(path, artifact)
            result["rows_by_ticker"][ticker] = rows
            result["artifacts"][ticker] = {
                "path": path.relative_to(raw_dir.parents[1]).as_posix(),
                "source_url": response.url,
                "http_status": response.status,
                "response_sha256": response.sha256,
                "fetched_at": response.fetched_at,
            }
        except (HttpError, ValueError, KeyError, TypeError) as exc:
            result["errors"][ticker] = str(exc)
    return result
