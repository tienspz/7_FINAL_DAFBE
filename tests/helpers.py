"""Test helpers for constructing pipeline inputs."""

from __future__ import annotations

from datetime import date
from typing import Any

from pipeline.config import Settings
from pipeline.preprocess.calendar import CalendarQuarter
from pipeline.preprocess.facts import MetricValue
from pipeline.util import quarter_key


def make_settings(
    companies: dict[str, Any],
    *,
    thresholds: dict[str, Any] | None = None,
    segment_map: dict[str, Any] | None = None,
    split_adjustments: dict[str, Any] | None = None,
) -> Settings:
    return Settings(
        concept_map={"companies": companies, "split_adjustments": split_adjustments or {}},
        segment_map=segment_map or {"companies": {}},
        source_registry={},
        allowlist={},
        thresholds=thresholds
        or {
            "quality": {
                "segment_sum_tolerance": 0.005,
                "filing_lag_days": 120,
                "q4_residual_ok": 0.005,
                "q4_residual_low": 0.02,
            }
        },
    )


def make_fact(
    *,
    ticker: str,
    metric: str,
    tag: str,
    start: str,
    end: str,
    period_type: str,
    value: float,
    filed: str = "2025-01-01",
    accession: str = "0000000000-25-000001",
    form: str = "10-Q",
    calendar_key: str | None = None,
    is_original: bool = True,
    verified: bool = True,
    unit: str = "USD",
    fact_id: str | None = None,
) -> dict[str, Any]:
    return {
        "fact_id": fact_id or f"{ticker}-{metric}-{start}-{end}",
        "ticker": ticker,
        "metric": metric,
        "xbrl_tag": tag,
        "unit": unit,
        "period_start": start,
        "period_end": end,
        "period_type": period_type,
        "calendar_key": calendar_key or quarter_key(date.fromisoformat(end)),
        "value_usd": value,
        "value_raw": value,
        "filed_date": filed,
        "accession_number": accession,
        "form": form,
        "source_url": f"https://www.sec.gov/Archives/edgar/data/1/{accession}/",
        "is_original": is_original,
        "verified": verified,
    }


def make_metric(
    value: float | None,
    *,
    quality: str = "ok",
    unit: str = "USD",
    verified: bool = True,
    tag: str = "TestTag",
    source_url: str = "https://www.sec.gov/example",
    accession: str = "0000000000-25-000001",
    derived: bool = False,
    reason: str = "",
) -> MetricValue:
    return MetricValue(
        value=value,
        unit=unit,
        source_url=source_url,
        accession_number=accession,
        xbrl_tag=tag,
        form="10-Q",
        filed_date="2025-01-01",
        period_end="2025-03-31",
        derived=derived,
        verified=verified,
        quality_flag=quality,
        reason=reason,
    )


def make_quarter(key: str) -> CalendarQuarter:
    year, q = key.split("-Q")
    month = (int(q) - 1) * 3 + 1
    start = date(int(year), month, 1)
    if month == 10:
        end = date(int(year), 12, 31)
    elif month == 7:
        end = date(int(year), 9, 30)
    elif month == 4:
        end = date(int(year), 6, 30)
    else:
        end = date(int(year), 3, 31)
    return CalendarQuarter(key=key, start=start, end=end)
