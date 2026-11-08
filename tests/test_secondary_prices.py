"""Allowlist enforcement and secondary close reconciliation tests."""

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from pipeline.crawlers.nasdaq import nasdaq_url, parse_money, parse_nasdaq_payload
from pipeline.http import AllowlistError, CachedHttpClient, domain_allowed
from pipeline.verify.reconcile import reconcile_prices
from tests.helpers import make_settings

QUALITY = {
    "quality": {
        "segment_sum_tolerance": 0.005,
        "filing_lag_days": 120,
        "q4_residual_ok": 0.005,
        "q4_residual_low": 0.02,
        "price_diff_tolerance": 0.001,
        "adjusted_close_diff_tolerance": 0.001,
        "min_price_days_for_reconciliation": 30,
    }
}


def price_frame(days: int = 40) -> pd.DataFrame:
    start = date(2026, 9, 1)
    return pd.DataFrame(
        {
            "trade_date": [start + timedelta(days=index) for index in range(days)],
            "close": [100.0 + index for index in range(days)],
            "adj_close": [100.0 + index for index in range(days)],
        }
    )


def secondary_rows(frame: pd.DataFrame, *, drift: float = 0.0) -> list[dict]:
    return [
        {
            "trade_date": row.trade_date.isoformat(),
            "close": float(row.close) * (1 + drift),
            "adjusted_close": float(row.adj_close) * (1 + drift),
        }
        for row in frame.itertuples()
    ]


def test_domain_allowed_matches_subdomains_only():
    allowed = ["sec.gov", "api.nasdaq.com", "api.tiingo.com", "yfinance"]
    assert domain_allowed("https://data.sec.gov/submissions/x.json", allowed)
    assert domain_allowed("https://api.nasdaq.com/api/quote/MSFT/historical", allowed)
    assert domain_allowed("https://api.tiingo.com/tiingo/daily/MSFT/prices", allowed)
    assert not domain_allowed("https://nasdaq.com/", allowed)
    assert not domain_allowed("https://evilsec.gov/", allowed)
    assert not domain_allowed("https://example.com/", allowed)


def test_client_rejects_unlisted_domain_before_any_network_call(tmp_path: Path):
    client = CachedHttpClient(
        cache_dir=tmp_path / "cache",
        user_agent="test",
        allowed_domains=["sec.gov"],
        enforce_allowlist=True,
    )
    with pytest.raises(AllowlistError):
        client.get("https://example.com/data.json")


def test_query_api_key_is_redacted_in_cache_url(tmp_path: Path):
    client = CachedHttpClient(
        cache_dir=tmp_path / "cache",
        user_agent="test",
        redact_query_keys=("apikey",),
    )
    stored = client._storage_url("https://www.alphavantage.co/query?symbol=MSFT&apikey=secret")
    assert "secret" not in stored
    assert "apikey=REDACTED" in stored


def test_nasdaq_payload_parsing():
    payload = {
        "data": {
            "tradesTable": {
                "rows": [
                    {"date": "11/03/2026", "close": "$520.99", "open": "$509.005", "high": "$523.44", "low": "$507.82", "volume": "20,010,170"},
                    {"date": "11/04/2026", "close": "$555.80", "open": "$543.695", "high": "$559.15", "low": "$542.30", "volume": "50,807,830"},
                ]
            }
        }
    }
    rows = parse_nasdaq_payload(payload)
    assert [row["trade_date"] for row in rows] == ["2026-11-03", "2026-11-04"]
    assert rows[-1]["close"] == pytest.approx(555.80)
    assert rows[-1]["volume"] == pytest.approx(50_807_830)
    assert parse_money("$1,234.50") == pytest.approx(1234.5)
    assert parse_money(None) is None


def test_nasdaq_url_uses_asset_class():
    assert "assetclass=etf" in nasdaq_url("SPY", date(2026, 9, 1), date(2026, 11, 5))
    assert "assetclass=stocks" in nasdaq_url("MSFT", date(2026, 9, 1), date(2026, 11, 5))


def test_secondary_close_ok_and_adjusted_unverified():
    settings = make_settings({}, thresholds=QUALITY)
    frame = price_frame()
    secondary = {
        "rows_by_ticker": {"MSFT": secondary_rows(frame)},
        "artifacts": {"MSFT": {"source_url": "https://api.nasdaq.com/x", "response_sha256": "a" * 64, "path": "data/raw/prices/nasdaq/MSFT.json"}},
        "errors": {},
    }
    adjusted = {
        "provider": "Tiingo",
        "available": False,
        "reason": "TIINGO_API_KEY is not set",
        "rows_by_ticker": {},
        "artifacts": {},
    }

    checks = reconcile_prices(
        price_analytics={"MSFT": {"rows": len(frame)}},
        settings=settings,
        prices_by_ticker={"MSFT": frame},
        secondary=secondary,
        adjusted=adjusted,
    )
    secondary_check = next(item for item in checks if item["check"] == "secondary_close")
    adjusted_check = next(item for item in checks if item["check"] == "secondary_adjusted_close")
    assert secondary_check["status"] == "ok"
    assert secondary_check["compared_days"] == 30
    assert secondary_check["max_relative_difference"] == 0.0
    assert adjusted_check["status"] == "unverified"
    assert "TIINGO_API_KEY" in adjusted_check["detail"]


def test_tiingo_adjusted_close_reconciles_with_provenance():
    settings = make_settings({}, thresholds=QUALITY)
    frame = price_frame()
    adjusted = {
        "provider": "Tiingo",
        "available": True,
        "rows_by_ticker": {"MSFT": secondary_rows(frame)},
        "artifacts": {
            "MSFT": {
                "source_url": "https://api.tiingo.com/tiingo/daily/MSFT/prices",
                "response_sha256": "b" * 64,
            }
        },
        "errors": {},
    }

    checks = reconcile_prices(
        price_analytics={"MSFT": {"rows": len(frame)}},
        settings=settings,
        prices_by_ticker={"MSFT": frame},
        adjusted=adjusted,
    )
    check = next(item for item in checks if item["check"] == "secondary_adjusted_close")

    assert check["status"] == "ok"
    assert check["compared_days"] == 30
    assert check["max_relative_difference"] == 0.0
    assert check["response_sha256"] == "b" * 64
    assert "Tiingo adjusted closes" in check["detail"]


def test_secondary_close_fails_on_real_drift_and_pending_without_rows():
    settings = make_settings({}, thresholds=QUALITY)
    frame = price_frame()
    drifted = {
        "rows_by_ticker": {"MSFT": secondary_rows(frame, drift=0.05)},
        "artifacts": {},
        "errors": {},
    }
    checks = reconcile_prices(
        price_analytics={"MSFT": {"rows": len(frame)}, "GOOGL": {"rows": 10}},
        settings=settings,
        prices_by_ticker={"MSFT": frame, "GOOGL": frame},
        secondary={"rows_by_ticker": {}, "artifacts": {}, "errors": {"GOOGL": "HTTP 403"}},
        adjusted={"provider": "Tiingo", "available": False, "reason": "missing key"},
    )
    assert any(item["check"] == "secondary_close" and item["status"] == "pending" for item in checks)

    drift_checks = reconcile_prices(
        price_analytics={"MSFT": {"rows": len(frame)}},
        settings=settings,
        prices_by_ticker={"MSFT": frame},
        secondary=drifted,
        adjusted={"provider": "Tiingo", "available": False, "reason": "missing key"},
    )
    assert next(item for item in drift_checks if item["check"] == "secondary_close")["status"] == "fail"
