"""Price-window trimming and adjusted-close self-check tests."""

from datetime import date

import pandas as pd
import pytest

from pipeline.preprocess.prices import (
    adjusted_close_selfcheck,
    monthly_returns,
    quarterly_returns,
)


def price_frame(rows: list[tuple[str, float, float, float, float]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trade_date": date.fromisoformat(trade_date),
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "adj_close": adj_close,
                "volume": 1_000.0,
                "dividends": dividend,
                "stock_splits": split,
            }
            for trade_date, close, adj_close, dividend, split in rows
        ]
    )


def test_monthly_returns_drop_partial_current_month_and_keep_first_window_month():
    frame = price_frame(
        [
            ("2021-12-31", 100.0, 100.0, 0.0, 0.0),
            ("2022-01-31", 110.0, 110.0, 0.0, 0.0),
            ("2022-02-28", 121.0, 121.0, 0.0, 0.0),
            ("2022-03-15", 130.0, 130.0, 0.0, 0.0),
        ]
    )
    monthly = monthly_returns(frame, start=date(2022, 1, 1), as_of=date(2022, 3, 15))
    assert [row.trade_date.isoformat() for row in monthly.itertuples()] == [
        "2022-01-31",
        "2022-02-28",
    ]
    assert monthly.iloc[0]["return"] == pytest.approx(0.10)


def test_quarterly_returns_drop_unfinished_quarter():
    frame = price_frame(
        [
            ("2026-06-30", 100.0, 100.0, 0.0, 0.0),
            ("2026-09-30", 110.0, 110.0, 0.0, 0.0),
            ("2026-11-06", 120.0, 120.0, 0.0, 0.0),
        ]
    )
    quarterly = quarterly_returns(frame, as_of=date(2026, 11, 6))
    assert list(quarterly["calendar_key"]) == ["2026-Q3"]
    assert quarterly.iloc[0]["return"] == pytest.approx(0.10)


def test_adjusted_close_selfcheck_reproduces_dividend_recurrence_and_split():
    frame = price_frame(
        [
            ("2022-06-30", 100.0, 100.0, 0.0, 0.0),
            ("2022-07-18", 110.0, 115.0, 5.0, 20.0),
            ("2022-09-30", 121.0, 132.77272727272728, 6.0, 0.0),
        ]
    )
    result = adjusted_close_selfcheck(frame)
    assert result["max_relative_difference"] == pytest.approx(0.0, abs=1e-12)
    assert result["dividend_events"] == 2
    assert result["split_events"] == [{"trade_date": "2022-07-18", "ratio": 20.0}]
    assert result["split_continuity_ok"] is True
