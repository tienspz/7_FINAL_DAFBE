"""Conditional adjusted-close cross-check via Tiingo daily prices."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from pipeline.http import CachedHttpClient, HttpError, MUTABLE_DATA_CACHE_MAX_AGE_SECONDS
from pipeline.util import safe_float, write_json

ENV_KEY = "TIINGO_API_KEY"
DEFAULT_TICKERS = ["MSFT", "GOOGL", "SPY", "QQQ"]
LOOKBACK_DAYS = 90
MIN_ROWS = 30


def available_api_key() -> str | None:
    key = os.environ.get(ENV_KEY, "").strip()
    return key or None


def prices_url(ticker: str, *, start: date, end: date) -> str:
    query = urlencode(
        {
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "format": "json",
        }
    )
    return f"https://api.tiingo.com/tiingo/daily/{ticker}/prices?{query}"


def parse_daily_prices(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        raise ValueError("Tiingo returned a non-list daily price response")

    rows: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        raw_date = item.get("date")
        try:
            trade_date = datetime.fromisoformat(
                str(raw_date).replace("Z", "+00:00")
            ).date().isoformat()
        except ValueError:
            continue
        adjusted = safe_float(item.get("adjClose"))
        if adjusted is None:
            continue
        rows.append(
            {
                "trade_date": trade_date,
                "close": safe_float(item.get("close")),
                "adjusted_close": adjusted,
                "volume": safe_float(item.get("volume")),
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
    refresh: bool = False,
) -> dict[str, Any]:
    """Fetch adjusted-close rows with a real Tiingo token, or report unverified."""
    key = available_api_key()
    result: dict[str, Any] = {
        "provider": "Tiingo",
        "available": False,
        "reason": (
            f"{ENV_KEY} is not set; adjusted-close cross-check was not run."
        ),
        "rows_by_ticker": {},
        "artifacts": {},
        "errors": {},
        "as_of": as_of,
    }
    if key is None:
        return result

    end = date.fromisoformat(as_of) if as_of else date.today()
    start = end - timedelta(days=LOOKBACK_DAYS)
    result["available"] = True
    result["reason"] = ""
    for ticker in tickers or DEFAULT_TICKERS:
        url = prices_url(ticker, start=start, end=end)
        try:
            response = client.get(
                url,
                refresh=refresh,
                max_age_seconds=MUTABLE_DATA_CACHE_MAX_AGE_SECONDS,
                headers={"Authorization": f"Token {key}"},
            )
            rows = parse_daily_prices(response.json())
            if len(rows) < MIN_ROWS:
                raise ValueError(
                    f"only {len(rows)} adjusted-close rows returned for {ticker}"
                )
            artifact = {
                "ticker": ticker,
                "provider": "Tiingo",
                "source_url": response.url,
                "http_status": response.status,
                "fetched_at": response.fetched_at,
                "response_sha256": response.sha256,
                "as_of": as_of,
                "rows": rows,
            }
            path = raw_dir / "prices" / "tiingo" / f"{ticker}.json"
            write_json(path, artifact)
            result["rows_by_ticker"][ticker] = rows
            result["artifacts"][ticker] = {
                "path": path.relative_to(raw_dir.parents[1]).as_posix(),
                "provider": "Tiingo",
                "source_url": response.url,
                "http_status": response.status,
                "response_sha256": response.sha256,
                "fetched_at": response.fetched_at,
            }
        except (HttpError, ValueError, KeyError, TypeError) as exc:
            result["errors"][ticker] = str(exc)
    return result
