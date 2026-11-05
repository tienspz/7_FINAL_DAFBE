from __future__ import annotations

import os
import time
from datetime import date
from pathlib import Path

import pandas as pd

from pipeline.crawlers import prices


class FakeTicker:
    calls = 0

    def __init__(self, ticker: str):
        self.ticker = ticker

    def history(self, **kwargs):
        FakeTicker.calls += 1
        return pd.DataFrame(
            {
                "Open": [100.0],
                "High": [102.0],
                "Low": [99.0],
                "Close": [101.0],
                "Adj Close": [100.5],
                "Volume": [1000],
                "Dividends": [0.0],
                "Stock Splits": [0.0],
            },
            index=pd.DatetimeIndex(["2026-11-05"], name="Date"),
        )


def test_price_cache_refreshes_after_max_age(monkeypatch, tmp_path: Path):
    FakeTicker.calls = 0
    monkeypatch.setattr(prices.yf, "Ticker", FakeTicker)
    kwargs = {
        "tickers": ["MSFT"],
        "start": date(2026, 11, 1),
        "end": date(2026, 11, 5),
        "raw_dir": tmp_path / "raw",
        "as_of": "2026-11-05",
        "max_age_seconds": 3600,
    }

    prices.fetch_prices(**kwargs)
    prices.fetch_prices(**kwargs)
    assert FakeTicker.calls == 1

    path = kwargs["raw_dir"] / "prices" / "MSFT_2026-11-05.csv"
    old_time = time.time() - 7200
    os.utime(path, (old_time, old_time))
    prices.fetch_prices(**kwargs)

    assert FakeTicker.calls == 2
