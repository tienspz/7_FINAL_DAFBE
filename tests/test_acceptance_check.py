from datetime import date

import pytest

from scripts.acceptance_check import latest_completed_price_row


def test_latest_completed_price_row_skips_the_current_incomplete_session():
    rows = [
        {"date": "2026-11-03", "close": 100.0},
        {"date": "2026-11-04", "close": 101.0},
        {"date": "2026-11-05", "close": 102.0},
    ]

    assert latest_completed_price_row(rows, today=date(2026, 11, 5)) == rows[1]


def test_latest_completed_price_row_fails_without_a_completed_session():
    with pytest.raises(ValueError, match="no completed trading date"):
        latest_completed_price_row(
            [{"date": "2026-11-05", "close": 102.0}], today=date(2026, 11, 5)
        )
