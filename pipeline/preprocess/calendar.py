"""Calendar-quarter helpers for MSFT and GOOGL."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from pipeline.config import Settings
from pipeline.util import fiscal_info, iter_quarters, quarter_end, quarter_key


@dataclass(frozen=True)
class CalendarQuarter:
    key: str
    start: date
    end: date

    @property
    def year(self) -> int:
        return self.start.year

    @property
    def quarter(self) -> int:
        return (self.start.month - 1) // 3 + 1


def analysis_quarters(settings: Settings) -> list[CalendarQuarter]:
    analysis = settings.thresholds["analysis"]
    keys = iter_quarters(
        int(analysis["start_year"]),
        int(analysis["start_quarter"]),
        int(analysis["end_year"]),
        int(analysis["end_quarter"]),
    )
    out: list[CalendarQuarter] = []
    for key in keys:
        end = quarter_end(key)
        start = date(end.year, ((end.month - 1) // 3) * 3 + 1, 1)
        out.append(CalendarQuarter(key=key, start=start, end=end))
    return out


def fiscal_fields(ticker: str, period_end: date) -> dict[str, object]:
    fiscal_year, fiscal_quarter = fiscal_info(ticker, period_end)
    return {
        "fiscal_year": fiscal_year,
        "fiscal_quarter": fiscal_quarter,
        "calendar_key": quarter_key(period_end),
        "period_end_offset_days": (period_end - quarter_end(quarter_key(period_end))).days,
    }
