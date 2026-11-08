from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from pipeline.crawlers.tiingo import (
    ENV_KEY,
    fetch_adjusted_closes,
    parse_daily_prices,
    prices_url,
)
from pipeline.http import HttpError


def tiingo_payload(rows: int = 35) -> list[dict[str, object]]:
    return [
        {
            "date": (datetime(2026, 10, 1) + timedelta(days=index)).isoformat() + "Z",
            "close": 100 + index,
            "adjClose": 99 + index,
            "volume": 1000 + index,
        }
        for index in range(1, rows + 1)
    ]


class StubResponse:
    url = "https://api.tiingo.com/tiingo/daily/MSFT/prices?startDate=2026-08-08"
    status = 200
    fetched_at = "2026-11-07T12:00:00Z"
    sha256 = "a" * 64

    def __init__(self, payload: object):
        self.payload = payload

    def json(self):
        return self.payload


class StubClient:
    def __init__(self, response: StubResponse | None = None, error: Exception | None = None):
        self.response = response or StubResponse(tiingo_payload())
        self.error = error
        self.calls: list[dict[str, object]] = []

    def get(self, url: str, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if self.error:
            raise self.error
        return self.response


def test_parse_daily_prices_uses_adjusted_close_and_normalizes_dates():
    rows = parse_daily_prices(
        [
            {"date": "2026-11-06T00:00:00.000Z", "close": 500, "adjClose": 495},
            {"date": "2026-11-05", "close": 490, "adjClose": 485},
            {"date": "invalid", "close": 1, "adjClose": 1},
        ]
    )

    assert rows == [
        {"trade_date": "2026-11-05", "close": 490.0, "adjusted_close": 485.0, "volume": None},
        {"trade_date": "2026-11-06", "close": 500.0, "adjusted_close": 495.0, "volume": None},
    ]


def test_prices_url_has_date_range_and_no_token():
    url = prices_url("MSFT", start=date(2026, 8, 8), end=date(2026, 11, 6))

    assert "startDate=2026-08-08" in url
    assert "endDate=2026-11-06" in url
    assert "token=" not in url


def test_fetch_uses_token_header_and_writes_no_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    token = "temporary-token-value"
    monkeypatch.setenv(ENV_KEY, token)
    client = StubClient()
    raw_dir = tmp_path / "data" / "raw"

    result = fetch_adjusted_closes(
        client=client,
        tickers=["MSFT"],
        raw_dir=raw_dir,
        as_of="2026-11-06",
    )

    assert result["available"] is True
    assert len(result["rows_by_ticker"]["MSFT"]) == 35
    assert client.calls[0]["headers"] == {"Authorization": f"Token {token}"}
    assert token not in str(client.calls[0]["url"])
    artifact = raw_dir / "prices" / "tiingo" / "MSFT.json"
    assert token not in artifact.read_text(encoding="utf-8")
    assert result["artifacts"]["MSFT"]["response_sha256"] == "a" * 64


def test_fetch_without_token_is_unverified_and_does_not_call_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv(ENV_KEY, raising=False)
    client = StubClient()

    result = fetch_adjusted_closes(client=client, raw_dir=tmp_path / "data" / "raw")

    assert result["available"] is False
    assert ENV_KEY in result["reason"]
    assert client.calls == []


def test_fetch_records_provider_error_without_leaking_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    token = "temporary-token-value"
    monkeypatch.setenv(ENV_KEY, token)
    client = StubClient(error=HttpError("https://api.tiingo.com/prices", 401, "HTTP 401"))

    result = fetch_adjusted_closes(
        client=client,
        tickers=["MSFT"],
        raw_dir=tmp_path / "data" / "raw",
        as_of="2026-11-06",
    )

    assert result["available"] is True
    assert "HTTP 401" in result["errors"]["MSFT"]
    assert token not in json.dumps(result)


def test_parse_daily_prices_rejects_non_list_payload():
    with pytest.raises(ValueError, match="non-list"):
        parse_daily_prices({"error": "unauthorized"})
