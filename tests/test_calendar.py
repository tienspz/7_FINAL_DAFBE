"""Calendar and fiscal-quarter mapping tests."""

from datetime import date

from pipeline.config import get_settings
from pipeline.preprocess.calendar import analysis_quarters
from pipeline.util import fiscal_info, quarter_key


def test_msft_fiscal_year_mapping():
    assert fiscal_info("MSFT", date(2022, 6, 30)) == (2022, "Q4")
    assert fiscal_info("MSFT", date(2022, 9, 30)) == (2023, "Q1")
    assert fiscal_info("MSFT", date(2022, 12, 31)) == (2023, "Q2")
    assert fiscal_info("MSFT", date(2023, 3, 31)) == (2023, "Q3")
    assert fiscal_info("MSFT", date(2026, 3, 31)) == (2026, "Q3")
    assert fiscal_info("MSFT", date(2026, 6, 30)) == (2026, "Q4")


def test_googl_uses_calendar_quarters():
    assert fiscal_info("GOOGL", date(2022, 3, 31)) == (2022, "Q1")
    assert fiscal_info("GOOGL", date(2024, 12, 31)) == (2024, "Q4")
    assert fiscal_info("GOOGL", date(2026, 9, 30)) == (2026, "Q3")


def test_analysis_window_is_nineteen_quarters():
    quarters = analysis_quarters(get_settings())
    assert len(quarters) == 19
    assert quarters[0].key == "2022-Q1"
    assert quarters[-1].key == "2026-Q3"
    assert [quarter.key for quarter in quarters] == [
        f"{year}-Q{q}"
        for year in range(2022, 2027)
        for q in range(1, 5)
        if (year, q) <= (2026, 3)
    ]


def test_quarter_key_uses_period_end_calendar_quarter():
    assert quarter_key(date(2022, 6, 30)) == "2022-Q2"
    assert quarter_key(date(2022, 7, 1)) == "2022-Q3"
