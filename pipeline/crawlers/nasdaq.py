"""Secondary unadjusted-close crawler using the Nasdaq historical API.

``api.nasdaq.com`` was approved for CR-13 on 2026-11-05 as the replacement for
Stooq, which only returns a JavaScript challenge to server-side crawlers. The
API requires a browser-like User-Agent; the SEC User-Agent is not acceptable.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from pipeline.http import CachedHttpClient, HttpError, MUTABLE_DATA_CACHE_MAX_AGE_SECONDS
from pipeline.util import safe_float, write_json

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)

ASSET_CLASS = {"MSFT": "stocks", "GOOGL": "stocks", "SPY": "etf", "QQQ": "etf"}
MIN_COMPARE_DAYS = 30


def nasdaq_url(ticker: str, start: date, end: date) -> str:
    return (
        f"https://api.nasdaq.com/api/quote/{ticker}/historical"
        f"?assetclass={ASSET_CLASS.get(ticker, 'stocks')}"
        f"&fromdate={start.isoformat()}&todate={end.isoformat()}&limit=120"
    )


def parse_money(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).replace("$", "").replace(",", "").replace("%", "").strip()
    return safe_float(text)


def parse_nasdaq_date(value: Any) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_nasdaq_payload(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Convert a Nasdaq historical payload into sorted close rows."""
    data = (payload or {}).get("data") or {}
    table = data.get("tradesTable") or {}
    raw_rows = table.get("rows") or []
    rows: list[dict[str, Any]] = []
    for raw in raw_rows:
        trade_date = parse_nasdaq_date(raw.get("date"))
        close = parse_money(raw.get("close"))
        if trade_date is None or close is None:
            continue
        rows.append(
            {
                "trade_date": trade_date,
                "close": close,
                "open": parse_money(raw.get("open")),
                "high": parse_money(raw.get("high")),
                "low": parse_money(raw.get("low")),
                "volume": parse_money(raw.get("volume")),
            }
        )
    rows.sort(key=lambda row: row["trade_date"])
    return rows


def fetch_secondary_closes(
    *,
    client: CachedHttpClient,
    tickers: list[str],
    start: date,
    end: date,
    raw_dir: Path,
    refresh: bool = False,
) -> dict[str, Any]:
    """Fetch Nasdaq closes for every ticker and persist a hashed raw artifact.

    A ticker failure is recorded in ``errors`` and does not abort the pipeline;
    reconciliation then reports that ticker as pending instead of guessing.
    """
    out_dir = raw_dir / "prices" / "nasdaq"
    result: dict[str, Any] = {
        "rows_by_ticker": {},
        "artifacts": {},
        "errors": {},
        "checked_at": None,
    }
    for ticker in tickers:
        url = nasdaq_url(ticker, start, end)
        try:
            response = client.get(url, refresh=refresh, max_age_seconds=MUTABLE_DATA_CACHE_MAX_AGE_SECONDS)
            rows = parse_nasdaq_payload(response.json())
            if len(rows) < MIN_COMPARE_DAYS:
                raise ValueError(f"only {len(rows)} close rows returned (need {MIN_COMPARE_DAYS})")
            artifact = {
                "ticker": ticker,
                "source_url": response.url,
                "http_status": response.status,
                "fetched_at": response.fetched_at,
                "response_sha256": response.sha256,
                "window": {"start": start.isoformat(), "end": end.isoformat()},
                "rows": rows,
            }
            path = out_dir / f"{ticker}.json"
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
    result["checked_at"] = datetime.now().astimezone().isoformat()
    return result
